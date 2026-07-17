"""Learned shrunk betas (backtest.learn_betas) + the edge-override hook.

The estimator is locked on a SYNTHETIC stored-row panel with planted betas:
recovery through the vol-normalization, hard shrinkage toward the priors,
sign-flip auto-reject, the strict time-split (polluted evaluation days must
not move an estimate), and the artifact -> BetaOverrides -> edge-builder
path (an all-default override set reproduces the default edges exactly).
"""

import json
from datetime import date, timedelta

import numpy as np
import pytest

from backtest import learn_betas as lb
from backtest.graph_edges import BetaOverrides, EdgeConfig, build_directed_edges

REGIME = "r1"
SIGMA = {("r1", "SPX"): 0.2, ("r1", "AAPL"): 0.3, ("r1", "MSFT"): 0.3, ("r1", "NVDA"): 0.25}
BETA_TRUE = {"AAPL": 1.2, "MSFT": 0.9, "NVDA": -0.5}  # NVDA: the sign-flip case
N_DAYS = 20  # split 0.5 -> 10 estimation days (>= MIN_N per name)


def _synthetic_rows() -> list[dict]:
    """Stored-row panel: 20 days, SPX + 3 names, 2 expiries each (30/60d, the
    short expiry exactly sqrt(2) x the long — calendar mult 1). Days AFTER the
    split carry a POISONED beta (-9) that a leaky estimator would inhale."""
    rng = np.random.default_rng(20260718)
    rows: list[dict] = []
    for d in range(N_DAYS):
        as_of = date(2024, 1, d + 1)
        x = float(rng.normal(0.0, 0.02))  # index innovation (vol units)
        poisoned = d >= N_DAYS // 2
        for tk in ("SPX", "AAPL", "MSFT", "NVDA"):
            if tk == "SPX":
                base = x
            else:
                beta_vn = -9.0 if poisoned else BETA_TRUE[tk]
                beta_abs = beta_vn * SIGMA[(REGIME, tk)] / SIGMA[(REGIME, "SPX")]
                base = beta_abs * x + float(rng.normal(0.0, 5e-4))
            # 30d/60d expiries via REAL date offsets, the short leg exactly
            # sqrt(t_long/t_short) = sqrt(2) times the long: calendar mult 1.
            for days_out, d_val in ((60, base), (30, np.sqrt(2.0) * base)):
                iso = (as_of + timedelta(days=days_out)).isoformat()
                rows.append({
                    "regime": REGIME, "as_of": as_of.isoformat(), "ticker": tk,
                    "expiry": iso, "ssr": 0, "design": "full_loo",
                    "base_atm": -float(d_val),
                })
    return rows


@pytest.fixture()
def artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "_load_rows", _synthetic_rows)
    monkeypatch.setattr(lb, "_sigma_table", lambda est_days: dict(SIGMA))
    out = tmp_path / "learned_betas.json"
    art = lb.fit(split=0.5, ssr=0, out_path=str(out))
    return art, out


def test_slope_recovers_planted_beta():
    rng = np.random.default_rng(7)
    x = rng.normal(0.0, 1.0, 200)
    y = 1.7 * x + rng.normal(0.0, 0.05, 200)
    b, t, n = lb._slope(x, y)
    assert b == pytest.approx(1.7, abs=0.02)
    assert t > 10 and n == 200


def test_shrink_and_reject_rules():
    # Strong evidence: shrunk strictly between prior and raw, weighted n:K.
    c = lb.shrink_estimate(1.2, t=8.0, n=10, prior=0.7, cap=3.0)
    assert not c["rejected"]
    expected = (10 * 1.2 + lb.SHRINK_K * 0.7) / (10 + lb.SHRINK_K)
    assert c["beta"] == pytest.approx(expected, abs=1e-4)  # artifact rounds 4dp
    # Sign flip / thin data / instability: the prior EXACTLY.
    assert lb.shrink_estimate(-0.4, 9.0, 50, 0.7, 3.0)["beta"] == 0.7
    assert lb.shrink_estimate(-0.4, 9.0, 50, 0.7, 3.0)["reason"] == "sign_flip"
    assert lb.shrink_estimate(1.2, 8.0, 3, 0.7, 3.0)["reason"] == f"n<{lb.MIN_N}"
    assert lb.shrink_estimate(1.2, 0.5, 50, 0.7, 3.0)["reason"] == f"|t|<{lb.MIN_T:g}"


def test_fit_learns_shrinks_and_rejects(artifact):
    art, _ = artifact
    aapl = art["indexByName"]["AAPL"]
    assert not aapl["rejected"]
    assert aapl["raw"] == pytest.approx(1.2, abs=0.05)  # vol-normalization exact
    assert 0.8 < aapl["beta"] < 1.0  # hard-shrunk toward the 0.7 prior
    # The poisoned evaluation days (beta -9) did NOT leak into the estimate.
    nvda = art["indexByName"]["NVDA"]
    assert nvda["rejected"] and nvda["reason"] == "sign_flip"
    assert nvda["beta"] == EdgeConfig().beta_index  # prior exactly
    # ETF class is dormant on this panel -> prior exactly, named reason.
    assert art["etfBeta"]["rejected"] and art["etfBeta"]["beta"] == EdgeConfig().beta_etf
    # Calendar multiplier planted at exactly 1.
    assert art["calendarMult"]["raw"] == pytest.approx(1.0, abs=0.02)
    assert art["evalPairStart"] == {REGIME: N_DAYS // 2}


def test_load_overrides_round_trip(artifact):
    art, out = artifact
    ov = lb.load_overrides(str(out))
    assert ov.index_by_name["AAPL"] == art["indexByName"]["AAPL"]["beta"]
    assert ov.name_beta == art["nameBeta"]["beta"]
    assert ov.calendar_mult == art["calendarMult"]["beta"]


# ------------------------------------------------------ edge-builder overrides
_NODES = [("SPX", "2026-07-18"), ("AAPL", "2026-07-18"), ("AAPL", "2026-08-21")]
_SIGMA_MAP = {n: s for n, s in zip(_NODES, (0.15, 0.25, 0.24))}
_T_MAP = {n: t for n, t in zip(_NODES, (0.1, 0.1, 0.19))}


def _betas(edges):
    return {(e.fromTicker, e.fromExpiry, e.toTicker, e.toExpiry): e.betaAtmVol for e in edges}


def test_empty_overrides_reproduce_default_edges_exactly():
    base = build_directed_edges(_NODES, _SIGMA_MAP, _T_MAP, EdgeConfig())
    ov = build_directed_edges(
        _NODES, _SIGMA_MAP, _T_MAP, EdgeConfig(overrides=BetaOverrides())
    )
    assert [e.model_dump() for e in base] == [e.model_dump() for e in ov]


def test_learned_index_beta_reaches_only_its_name():
    cfg = EdgeConfig(overrides=BetaOverrides(index_by_name={"AAPL": 1.1}))
    base = _betas(build_directed_edges(_NODES, _SIGMA_MAP, _T_MAP, EdgeConfig()))
    over = _betas(build_directed_edges(_NODES, _SIGMA_MAP, _T_MAP, cfg))
    key = ("AAPL", "2026-07-18", "SPX", "2026-07-18")  # index informs the name
    assert over[key] == pytest.approx(1.1 * 0.25 / 0.15)
    assert over[key] != base[key]
    # Calendar edges untouched by an index-only override.
    cal = ("AAPL", "2026-07-18", "AAPL", "2026-08-21")
    assert over[cal] == base[cal]
    # The reverse edge stays the inverse of the overridden forward beta.
    rev = ("SPX", "2026-07-18", "AAPL", "2026-07-18")
    assert over[rev] == pytest.approx(1.0 / over[key])


def test_calendar_multiplier_scales_sqrt_t():
    cfg = EdgeConfig(overrides=BetaOverrides(calendar_mult=1.2))
    base = _betas(build_directed_edges(_NODES, _SIGMA_MAP, _T_MAP, EdgeConfig()))
    over = _betas(build_directed_edges(_NODES, _SIGMA_MAP, _T_MAP, cfg))
    cal = ("AAPL", "2026-07-18", "AAPL", "2026-08-21")
    assert over[cal] == pytest.approx(1.2 * base[cal])


def test_chunk_ranges_pair_start_and_tagged_parts(tmp_path, monkeypatch):
    from backtest import benchmark_pack as bp

    assert bp.chunk_ranges(10, 4, start=6) == [(6, 10)]
    assert bp.chunk_ranges(10, 4) == [(0, 4), (4, 8), (8, 10)]
    # load_parts tag filter: tagged and untagged parts must not mix.
    monkeypatch.setattr(bp, "RESULTS_DIR", str(tmp_path))
    row = {"regime": "r1", "as_of": "2024-01-02", "design": "full_loo",
           "ssr": 0, "ticker": "AAPL", "expiry": "2024-02-02", "base_atm": 0.01}
    (tmp_path / "r1_pairs00-02.json").write_text(
        json.dumps({"rows": [dict(row, src="plain")]}), encoding="utf-8")
    (tmp_path / "r1_pairs00-02_abl.json").write_text(
        json.dumps({"rows": [dict(row, src="abl")]}), encoding="utf-8")
    assert {r["src"] for r in bp.load_parts(tag="")} == {"plain"}
    assert {r["src"] for r in bp.load_parts(tag="_abl")} == {"abl"}
    assert len(bp.load_parts()) == 1  # untagged merge still dedups first-wins
