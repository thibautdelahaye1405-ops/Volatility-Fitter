"""Graph-LOO quarantine (backtest/graph_loo.py, benchmark integrity fix 2026-09-10).

The overnight `_lvop` sweep scored NaN for every node but one on six spike
days: one XOM node with an absurd fit (a merged adjusted option series) fed a
non-finite observation into the joint field solve, and the summary's
non-finite filter then silently scored 2,817 nodes as 4,298. Locks:

1. ``screen_solution`` names a calibrated node whose handles, observation
   precision or transported prior are non-finite, or whose ATM vol leaves
   ``ATM_VOL_SANE`` — with a reason each; a clean solution yields nothing.
2. ``solve_screened`` re-solves once with the flagged names withheld, returns
   the clean field, and raises naming the day when the field stays
   non-finite; a clean day solves exactly once (byte-identical path).
3. ``_score_node`` never returns a NaN row.
4. End to end on the synthetic app: two poisoned nodes are quarantined with
   their reasons, every other node scores finite, and without the poison the
   screened path returns the very rows the plain path returns.
5. The part file carries the ``quarantine`` list, ``load_quarantine`` reads
   it back, and the HTML report states the count.
"""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest

from backtest import benchmark_pack as bp
from backtest import graph_loo
from backtest.graph_edges import EdgeConfig
from volfit.api import priors, service
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


# ------------------------------------------------------------------- fakes
def _node(tk: str, iso: str, lit: bool = True):
    return SimpleNamespace(name=(tk, iso), ticker=tk, expiry=iso, lit=lit)


def _solution(handles: dict, precision: dict, prior: dict, field_mean=None, field_sd=None):
    """A fake ExtrapolationSolution over the nodes of ``handles`` (name -> y)."""
    names = list(handles)
    nodes = [_node(*n) for n in names]
    n = len(nodes)
    return SimpleNamespace(
        universe=SimpleNamespace(nodes=nodes),
        calibrated=[True] * n,
        obs_value_by_idx={i: np.asarray(handles[nm], float) for i, nm in enumerate(names)},
        obs_breakdowns={i: SimpleNamespace(precision=np.asarray(precision[nm], float))
                        for i, nm in enumerate(names) if nm in precision},
        priors_meta=tuple(SimpleNamespace(handles=np.asarray(prior[nm], float),
                                          valid_for_validation=True) for nm in names),
        field=SimpleNamespace(
            mean=np.zeros((n, 3)) if field_mean is None else np.asarray(field_mean, float),
            sd=np.full((n, 3), 0.03) if field_sd is None else np.asarray(field_sd, float),
        ),
        fit_mode="mid",
    )


OK_Y, OK_P, OK_PRIOR = [0.2, -0.1, 0.5], [1e4, 1e2, 1e1], [0.21, -0.1, 0.5]


def test_screen_flags_every_poison_with_a_reason():
    a, b, c, d, e, f = [("T", f"2026-0{i}-17") for i in range(1, 7)]
    sol = _solution(
        handles={a: OK_Y, b: [math.nan, -0.1, 0.5], c: [9.0, -0.1, 0.5], d: OK_Y, e: OK_Y, f: OK_Y},
        precision={a: OK_P, b: OK_P, c: OK_P, d: [math.inf, 1e2, 1e1], e: OK_P, f: OK_P},
        prior={a: OK_PRIOR, b: OK_PRIOR, c: OK_PRIOR, d: OK_PRIOR, e: [math.nan, 0, 0], f: [0.004, 0, 0]},
    )
    bad = dict(graph_loo.screen_solution(sol))
    assert a not in bad
    assert bad[b] == "non-finite calibrated handles"
    assert bad[c].startswith("calibrated atm vol 9 outside")
    assert bad[d] == "non-finite observation precision"
    assert bad[e] == "non-finite transported prior"
    assert bad[f].startswith("prior atm vol 0.004 outside")
    clean = _solution({a: OK_Y, d: OK_Y}, {a: OK_P, d: OK_P}, {a: OK_PRIOR, d: OK_PRIOR})
    assert graph_loo.screen_solution(clean) == []


def test_solve_screened_resolves_once_withholding_the_poison(monkeypatch):
    a, b = ("T", "2026-01-17"), ("T", "2026-02-20")
    calls: list[frozenset] = []

    def fake_solve(state, req, hold_out=frozenset(), idio_atm_sigma=None):
        calls.append(hold_out)
        poisoned = b not in hold_out
        return _solution(
            {a: OK_Y, b: [math.nan, 0.0, 0.0]}, {a: OK_P, b: OK_P}, {a: OK_PRIOR, b: OK_PRIOR},
            field_mean=np.full((2, 3), math.nan if poisoned else 0.0),
            field_sd=np.full((2, 3), math.nan if poisoned else 0.03),
        )

    monkeypatch.setattr(graph_loo, "solve", fake_solve)
    full, bad = graph_loo.solve_screened(None, GraphExtrapolateRequest(), None, "day X")
    assert bad == [(b, "non-finite calibrated handles")]
    assert calls == [frozenset(), frozenset({b})]  # screened, then re-solved once
    assert np.isfinite(full.field.mean).all() and np.isfinite(full.field.sd).all()

    # A field that stays non-finite raises, naming the day — never NaN rows.
    def stubborn(state, req, hold_out=frozenset(), idio_atm_sigma=None):
        return _solution({a: OK_Y, b: OK_Y}, {a: OK_P, b: OK_P}, {a: OK_PRIOR, b: OK_PRIOR},
                         field_mean=np.full((2, 3), math.nan))

    monkeypatch.setattr(graph_loo, "solve", stubborn)
    with pytest.raises(RuntimeError, match="day X: the graph field is non-finite"):
        graph_loo.solve_screened(None, GraphExtrapolateRequest(), None, "day X")

    # A clean day solves exactly once (the legacy path, byte-identical).
    calls.clear()

    def clean(state, req, hold_out=frozenset(), idio_atm_sigma=None):
        calls.append(hold_out)
        return _solution({a: OK_Y, b: OK_Y}, {a: OK_P, b: OK_P}, {a: OK_PRIOR, b: OK_PRIOR})

    monkeypatch.setattr(graph_loo, "solve", clean)
    full, bad = graph_loo.solve_screened(None, GraphExtrapolateRequest(), None, "day Y")
    assert bad == [] and calls == [frozenset()]


def test_score_node_never_returns_a_nan_row():
    a = ("T", "2026-01-17")
    full = _solution({a: OK_Y}, {a: OK_P}, {a: OK_PRIOR})
    held = _solution({a: OK_Y}, {a: OK_P}, {a: OK_PRIOR}, field_sd=np.full((1, 3), math.nan))
    node = full.universe.nodes[0]
    assert graph_loo._score_node(None, full, held, 0, node, np.asarray(OK_Y), "mid") is None
    held2 = _solution({a: OK_Y}, {a: OK_P}, {a: OK_PRIOR}, field_mean=np.full((1, 3), math.inf))
    assert graph_loo._score_node(None, full, held2, 0, node, np.asarray(OK_Y), "mid") is None


# ------------------------------------------------------------- end to end
def _calibrated_state() -> tuple[AppState, str, list[str]]:
    state = AppState(REF_DATE)
    tk = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(tk))]
    for iso in isos:
        service.calibrate_node(state, tk, iso, "mid")
    priors.save_all(state)
    priors.fetch_all(state)
    return state, tk, isos


def _poison(monkeypatch, state: AppState, tk: str, nan_iso: str, absurd_iso: str) -> None:
    """Make two nodes' CALIBRATED handles a NaN and a 900 % ATM vol, through the
    ATM-handle reader the solve uses (matched on the node's variance clock)."""
    from volfit.api import graph_extrapolation as ge

    taus = {iso: float(service.fit_or_get(state, tk, iso, "mid").prepared.tau)
            for iso in (nan_iso, absurd_iso)}
    real = ge.atm_handles

    def fake(slice_, t):
        h = real(slice_, t)
        for iso, sigma in ((nan_iso, math.nan), (absurd_iso, 9.0)):
            if math.isclose(float(t), taus[iso], rel_tol=0.0, abs_tol=1e-12):
                return dataclasses.replace(h, sigma0=sigma) if dataclasses.is_dataclass(h) else h
        return h

    monkeypatch.setattr(ge, "atm_handles", fake)


def test_end_to_end_quarantine_and_byte_identity(monkeypatch):
    state, tk, isos = _calibrated_state()
    assert len(isos) >= 4
    req = GraphExtrapolateRequest()

    # The plain path first (no poison): reference rows.
    plain = graph_loo.solve(state, req)
    assert plain is not None and np.isfinite(plain.field.mean).all()
    ref_rows = graph_loo._run_design(state, plain, req, "full_loo", "mid")
    assert ref_rows and all(np.isfinite([r["sd"], r["zeta"], r["res_atm"]]).all() for r in ref_rows)
    screened, bad = graph_loo.solve_screened(state, req, None, "clean day")
    assert bad == []
    assert graph_loo._run_design(state, screened, req, "full_loo", "mid") == ref_rows

    # Two poisoned nodes: a NaN handle and an absurd ATM vol.
    nan_iso, absurd_iso = isos[1], isos[2]
    _poison(monkeypatch, state, tk, nan_iso, absurd_iso)
    full, bad = graph_loo.solve_screened(state, req, None, "poisoned day")
    reasons = dict(bad)
    assert reasons[(tk, nan_iso)] == "non-finite calibrated handles"
    assert reasons[(tk, absurd_iso)].startswith("calibrated atm vol 9 outside")
    assert np.isfinite(full.field.mean).all() and np.isfinite(full.field.sd).all()
    names = frozenset(n for n, _ in bad)
    # The synthetic tickers share expiries, so the clock-matched poison hits the
    # sibling nodes too — every flagged node carries one of the two expiries.
    assert all(iso in (nan_iso, absurd_iso) for _, iso in names)
    rows = graph_loo._run_design(state, full, req, "full_loo", "mid", quarantined=names)
    scored = {(r["ticker"], r["expiry"]) for r in rows}
    assert scored.isdisjoint(names)
    assert len(rows) == len(ref_rows) - len(names)
    for r in rows:
        assert np.isfinite([r["sd"], r["zeta"], r["res_atm"], r["base_atm"]]).all()


# -------------------------------------------------------------- the pack
def _row(regime: str, as_of: str, design: str, ssr: int, tk: str, iso: str) -> dict:
    return dict(regime=regime, as_of=as_of, prior_as_of=as_of, design=design, ssr=ssr,
                ticker=tk, expiry=iso, kind="name", zeta=0.1, sd=0.03,
                res_atm=0.001, base_atm=0.002, res_skew=0.0, base_skew=0.0,
                res_curv=0.0, base_curv=0.0)


def test_part_file_report_and_loader_carry_the_quarantine(tmp_path, monkeypatch):
    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(bp, "_n_pairs", lambda regime: 1)

    def fake_loo(regime, designs, r_values, max_pairs, cfg, pair_range=None, **kw):
        log = kw.get("quarantine_log")
        assert log is not None  # the pack always passes the list
        log.append(dict(regime=regime, as_of="2024-08-05", prior_as_of="2024-08-02",
                        design="full_loo", ssr=0, ticker="XOM", expiry="2024-09-20",
                        reason="calibrated atm vol 1.7 outside [0.01, 4]"))
        return [_row(regime, "2024-08-05", "full_loo", 0, "AAPL", "2024-08-16")]

    monkeypatch.setattr(bp, "run_loo", fake_loo)
    bp.run_regime("spike_aug2024", ("full_loo",), (0.0,), chunk=1, cfg=EdgeConfig(), tag="_q")
    part = json.load(open(tmp_path / "spike_aug2024_pairs00-01_q.json", encoding="utf-8"))
    assert part["quarantine"][0]["ticker"] == "XOM" and len(part["rows"]) == 1
    q = bp.load_quarantine("spike_aug2024", tag="_q")
    assert len(q) == 1 and q[0]["reason"].startswith("calibrated atm vol")
    assert bp.load_quarantine("spike_aug2024", tag="") == []  # another sweep: nothing
    html = bp.build_report_html(bp.load_parts("spike_aug2024", tag="_q"), q)
    assert "1 quarantined" in html and "calibrated atm vol 1.7" in html
    html_path, json_path = bp.write_report(tag="_q")
    payload = json.load(open(json_path, encoding="utf-8"))
    assert payload["nQuarantined"] == 1 and payload["quarantinedByRegime"] == {"spike_aug2024": 1}
