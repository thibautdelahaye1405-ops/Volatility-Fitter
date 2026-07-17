"""Graph leave-one-out backtest over captured fixtures (roadmap Phase 6).

The headline differentiator — extrapolating sparse smiles across the universe via
the graph — validated temporally on the captured day pairs. For each consecutive
pair (T-1, T):

  1. freeze T-1's full surface as the active prior per ticker
     (``capture_snapshot(lv=False)``);
  2. on day T, transport that prior under SSR regime R and form the lit-calibration
     innovation ``d = calibrated_T - transported_prior``;
  3. propagate it through the directed graph (``backtest.graph_edges``: calendar
     sqrt-T + index/ETF/name vol-normalized betas);
  4. compare the graph posterior for held-out nodes with their ACTUAL day-T
     calibration — all three handles (ATM / skew / curvature) + the reconstructed
     full-smile wing RMS — and against the pure transported-prior baseline (the
     graph's SKILL: does the signal beat the mechanical spot-transport?).

Two designs (both requested): **full-LOO** withholds each validation-clean node in
turn; **liquid-split** lights only indices/ETFs and scores the single names as dark
extrapolation targets (the real product use case).

The SSR sweep is **R in {0, 1}** by design (Q1): R=0 (sticky-moneyness) leaves an
underperformer's baseline vol unmoved and so OVER-credits the graph; R=1 (sticky-
strike) bakes in the full leverage and so UNDER-credits it. The truth is bracketed,
so both are reported. (R=2 omitted.)

Run::

    python -m backtest.graph_loo --regime spike_aug2024
    python -m backtest.graph_loo --regime spike_aug2024 --designs liquid_split \
        --regimes-r 0,1 --max-pairs 4
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

import numpy as np

from volfit.api import priors, service
from volfit.api.graph_extrapolation import _calibrated_handles, _node_t, solve
from volfit.api.graph_reconstruct import _retarget_slice
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState
from volfit.graph.hyper import standardized_residuals
from volfit.graph.idio import trailing_idio_sigma
from volfit.models.lqd.ortho import build_atm_coordinates

from backtest.graph_edges import EdgeConfig, asset_kind, build_directed_edges
from backtest.replay import list_fixtures, load_fixture

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
_R_NAME = {0.0: "sticky_moneyness", 1.0: "sticky_strike"}
ATM_BAND = 0.10  # |k| <= ATM_BAND is the ATM region; beyond it the scored wing.
HANDLES = ("atm", "skew", "curv")


# --------------------------------------------------------------- smile wing RMS
def _smile_rmse(state: AppState, tk: str, iso: str, fit_mode: str, handles) -> dict | None:
    """Retarget an arb-free LQD smile to ``handles`` and score it against the node's
    day-T quotes: ATM / wing / full RMS vol error (bp). ``None`` if the node has no
    calibration (no base coordinates) or the retarget fails."""
    record = service.fit_or_get(state, tk, iso, fit_mode)
    if record is None:
        return None
    prepared = record.prepared
    tau = float(prepared.tau)
    k = np.asarray(prepared.k, dtype=float)
    if k.size == 0:
        return None
    try:  # the Newton retarget can diverge on extreme posterior handles (A_R>1)
        chart = build_atm_coordinates(record.result.params, tau)
        sl = _retarget_slice(chart, handles, tau)
        if sl is None:
            return None
        model_iv = np.sqrt(np.maximum(sl.implied_w(k), 1e-12) / tau)
    except Exception:  # noqa: BLE001 — wing RMS is best-effort, skip on failure
        return None
    mid = np.asarray(prepared.iv_mid, dtype=float)
    err = (model_iv - mid) * 1e4
    atm = np.abs(k) <= ATM_BAND
    wing = ~atm

    def _rms(mask) -> float | None:
        e = err[mask]
        e = e[np.isfinite(e)]
        return float(np.sqrt(np.mean(e**2))) if e.size else None

    return {"atm": _rms(atm), "wing": _rms(wing), "full": _rms(np.ones_like(k, dtype=bool))}


# --------------------------------------------------------------- per-node score
def _score_node(state, full, held, idx, node, truth, fit_mode) -> dict | None:
    """One held-out node: graph vs transported-prior baseline on all handles + smile."""
    post = held.field.mean[idx]
    base = held.priors_meta[idx].handles
    sd = float(held.field.sd[idx, 0])
    obs_prec = full.obs_breakdowns[idx].precision[0] if idx in full.obs_breakdowns else None
    if obs_prec is None:  # dark node: the precision it WOULD carry, from its own chain
        rec = service.fit_or_get(state, node.ticker, node.expiry, fit_mode)
        if rec is None:
            return None
        from volfit.api.graph_extrapolation import _quote_stats
        from volfit.graph import precision as gprec

        rms = service.weighted_rms_error(state, node.ticker, node.expiry, rec, fit_mode)
        n_atm, rel = _quote_stats(rec.prepared)
        obs_prec = gprec.observation_precision(rms, n_atm, rel).precision[0]

    zeta = float(standardized_residuals(
        np.array([truth[0]]), np.array([post[0]]), np.array([sd * sd]), np.array([obs_prec])
    )[0])
    sm_g = _smile_rmse(state, node.ticker, node.expiry, fit_mode, post)
    sm_b = _smile_rmse(state, node.ticker, node.expiry, fit_mode, base)
    row = {
        "ticker": node.ticker, "expiry": node.expiry, "kind": asset_kind(node.ticker),
        "zeta": round(zeta, 4), "sd": round(sd, 6),
    }
    for h, c in zip(HANDLES, range(3)):
        row[f"res_{h}"] = round(float(post[c] - truth[c]), 6)       # graph residual
        row[f"base_{h}"] = round(float(base[c] - truth[c]), 6)      # baseline residual
    if sm_g is not None:
        for part in ("atm", "wing", "full"):
            row[f"wing_{part}_g"] = None if sm_g[part] is None else round(sm_g[part], 2)
            row[f"wing_{part}_b"] = (
                None if sm_b is None or sm_b[part] is None else round(sm_b[part], 2)
            )
    return row


# ------------------------------------------------------------- idio band floor
def _idio_sigma_map(entries, today_iso: str) -> dict[str, float]:
    """Strictly-causal per-ticker trailing idio sigma from previously SCORED rows
    (their ``base_atm`` = transported-prior residual = the node's innovation),
    with the same-kind cross-sectional pool as the shrink target — the exact
    estimator validated offline on the stored benchmark parts (2026-07-10).

    ``entries`` are ``(as_of_iso, ticker, kind, base_atm)`` accumulated across
    the run's day pairs (plus any seed from earlier chunk parts); only entries
    strictly before ``today_iso`` are used."""
    past = [(a, tk, kd, v) for (a, tk, kd, v) in entries if a < today_iso]
    if not past:
        return {}
    pool: dict[str, list] = defaultdict(list)
    own: dict[str, list] = defaultdict(list)
    kind_of: dict[str, str] = {}
    for a, tk, kd, v in past:
        pool[kd].append(v * v)
        own[tk].append((a, v))
        kind_of[tk] = kd
    out: dict[str, float] = {}
    for tk, tk_entries in own.items():
        p = pool[kind_of[tk]]
        s = trailing_idio_sigma(tk_entries, float(np.mean(p)) if p else None)
        if s is not None:
            out[tk] = s
    return out


# --------------------------------------------------------------- one (pair, R, design)
def _run_design(
    state, full, req, design: str, fit_mode: str, idio_sigma: dict[str, float] | None = None
) -> list[dict]:
    """Score either every validation-clean node (full_loo) or the dark single names
    (liquid_split) for one solved universe."""
    universe = full.universe
    rows: list[dict] = []
    if design == "liquid_split":
        for i, node in enumerate(universe.nodes):
            if node.lit:
                continue  # only the dark single-name targets are scored
            try:
                truth = _calibrated_handles(state, node.ticker, node.expiry, fit_mode)
                if truth is None:
                    continue
                r = _score_node(state, full, full, i, node, truth, fit_mode)
            except Exception:  # noqa: BLE001 — a degenerate node fit is a skipped score
                continue
            if r is not None:
                rows.append(r)
        return rows
    # full_loo: withhold each validation-clean node in turn.
    for i, node in enumerate(universe.nodes):
        if not full.calibrated[i] or not full.priors_meta[i].valid_for_validation:
            continue
        try:
            held = solve(state, req, hold_out=frozenset({node.name}), idio_atm_sigma=idio_sigma)
            if held is None:
                continue
            r = _score_node(state, full, held, i, node, full.obs_value_by_idx[i], fit_mode)
        except Exception:  # noqa: BLE001 — a degenerate node fit is a skipped score
            continue
        if r is not None:
            rows.append(r)
    return rows


def _setup_day(state_t, tickers, snaps, r_val: float, design: str) -> None:
    """Load the T-1 priors, set the SSR regime, and (liquid_split) light only the
    indices/ETFs, darkening single names.

    The lit calibration runs in persistence mode ``off`` (PURE market): the graph
    innovation ``d = calibrated - transported_prior`` must be the genuine market-vs-
    prior move, not a prior-anchored fit (which would double-count the prior and
    shrink the signal). The active prior still drives the graph BASELINE — that comes
    from ``state.active_prior`` via ``graph_nodes.resolve_priors``, independent of the
    calibration anchor mode."""
    for tk in tickers:
        if snaps.get(tk) is not None:
            state_t.set_active_prior(tk, snaps[tk], "saved")
    state_t.set_options(state_t.options().model_copy(
        update={"dynamicsRegime": _R_NAME[r_val], "priorPersistenceMode": "off"}
    ))
    if design == "liquid_split":
        for tk in tickers:
            dark = asset_kind(tk) == "name"
            for iso in [e.isoformat() for e in sorted(state_t.selected_expiries(tk))]:
                state_t.set_node_lit(tk, iso, not dark)


def run(
    regime: str,
    designs,
    r_values,
    max_pairs: int | None,
    cfg: EdgeConfig,
    pair_range: tuple[int, int] | None = None,
    eta_scale: float = 1.0,
    history_rows: list[dict] | None = None,
    lambda_scale: float = 0.0,
    nu: float = 0.1,
) -> list[dict]:
    """Score consecutive day pairs across the designs and SSR regimes.

    ``pair_range=(a, b)`` scores pairs ``a..b-1`` only (the benchmark pack's
    chunked/resumable driver); ``max_pairs`` keeps the historical prefix cut.
    ``eta_scale`` sets the solver's propagation reach (GraphExtrapolateRequest
    etaScale; default 1.0 = the production default — the 2026-07-09 sensitivity
    sweep showed reach, not precision, is the binding cross-asset lever).
    ``history_rows`` seeds the idio band floor's innovation history with rows
    scored by EARLIER chunks (matched on design/ssr; only rows dated strictly
    before a pair's day-T are ever used), so chunked pack runs reproduce the
    single-process estimator instead of cold-starting each chunk.
    ``lambda_scale``/``nu`` set the solver's OT flux weight + source allowance
    (GraphSolverParams; defaults 0.0/0.1 = OT off, byte-identical) — the R3
    item-14 OT ablation lever."""
    paths = list_fixtures(regime=regime)
    if not paths:
        raise SystemExit(f"no fixtures for regime={regime}")
    # All assets per date, and the consecutive (T-1 -> T) date pairs they share.
    by_date: dict = defaultdict(list)
    for p in paths:
        f = load_fixture(p)
        by_date[f.as_of].append(f)
    dates = sorted(by_date)
    pairs = list(zip(dates[:-1], dates[1:]))
    if pair_range is not None:
        pairs = pairs[pair_range[0] : pair_range[1]]
    elif max_pairs:
        pairs = pairs[:max_pairs]

    out: list[dict] = []
    # Idio-floor innovation history per (design, R) cell — seeded from earlier
    # chunks' rows, then extended with this run's own scored rows (base_atm is
    # the node's innovation vs the transported prior). Strictly causal: the map
    # handed to a pair's solves only ever sees rows dated before that pair's T.
    recs: dict[tuple, list] = defaultdict(list)
    for r in history_rows or []:
        if r.get("base_atm") is not None:
            recs[(r["design"], int(r["ssr"]))].append(
                (r["as_of"], r["ticker"], r["kind"], float(r["base_atm"]))
            )
    for d0, d1 in pairs:
        fx0, fx1 = by_date[d0], by_date[d1]
        tickers = sorted({f.asset for f in fx1})
        try:
            state0 = _state(fx0)
            snaps = {tk: priors.capture_snapshot(state0, tk, "mid", lv=False) for tk in tickers}
            for design in designs:
                for r_val in r_values:
                    state_t = _state(fx1)
                    _setup_day(state_t, tickers, snaps, r_val, design)
                    sigma, tmap = _baseline_maps(state_t)
                    edges = build_directed_edges(list(sigma), sigma, tmap, cfg)
                    req = GraphExtrapolateRequest(
                        edges=edges, etaScale=eta_scale,
                        lambdaScale=lambda_scale, nu=nu,
                    )
                    idio_sig = _idio_sigma_map(recs[(design, int(r_val))], d1.isoformat())
                    full = solve(state_t, req, idio_atm_sigma=idio_sig)
                    if full is None:
                        continue
                    for row in _run_design(state_t, full, req, design, full.fit_mode, idio_sig):
                        out.append(dict(row, regime=regime, as_of=d1.isoformat(),
                                        prior_as_of=d0.isoformat(),
                                        ssr=int(r_val), design=design))
                        if row.get("base_atm") is not None:
                            recs[(design, int(r_val))].append(
                                (d1.isoformat(), row["ticker"], row["kind"],
                                 float(row["base_atm"]))
                            )
        except Exception as exc:  # noqa: BLE001 — one bad pair never kills the sweep
            print(f"  {d1}: SKIPPED ({type(exc).__name__}: {str(exc)[:80]})", flush=True)
            continue
        print(f"  {d1}: {sum(1 for r in out if r['as_of'] == d1.isoformat())} scores", flush=True)
    return out


def _state(fixtures) -> AppState:
    from backtest.replay import state_for_day

    return state_for_day(fixtures)


def _baseline_maps(state) -> tuple[dict, dict]:
    """Per-node baseline ATM vol (for vol-normalizing betas) + calendar year-fraction,
    from a default-edge solve (topology-independent)."""
    sol = solve(state, GraphExtrapolateRequest())
    sigma: dict = {}
    tmap: dict = {}
    if sol is None:
        return sigma, tmap
    for i, node in enumerate(sol.universe.nodes):
        sigma[node.name] = float(sol.priors_meta[i].handles[0])
        tmap[node.name] = _node_t(state, node.expiry)
    return sigma, tmap


# --------------------------------------------------------------------- summary
def _agg(values) -> dict:
    a = np.array([v for v in values if v is not None], float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "mean": round(float(a.mean()), 4),
            "median": round(float(np.median(a)), 4), "std": round(float(a.std()), 4)}


def summarize(rows: list[dict]) -> list[dict]:
    """Aggregate by (design, ssr): per-handle graph vs baseline residual RMS + skill,
    smile wing RMS graph vs baseline, and ATM zeta calibration."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["design"], r["ssr"])].append(r)
    out: list[dict] = []
    for (design, ssr), g in sorted(groups.items()):
        rec = {"design": design, "ssr": ssr, "n": len(g)}
        for h in HANDLES:
            gr = np.array([x[f"res_{h}"] for x in g], float)
            ba = np.array([x[f"base_{h}"] for x in g], float)
            scale = 1e4 if h == "atm" else 1.0  # ATM in bp, skew/curv raw
            rec[f"{h}_graph_rms"] = round(float(np.sqrt(np.mean(gr**2))) * scale, 3)
            rec[f"{h}_base_rms"] = round(float(np.sqrt(np.mean(ba**2))) * scale, 3)
            rec[f"{h}_skill"] = round(rec[f"{h}_base_rms"] - rec[f"{h}_graph_rms"], 3)
        rec["wing_graph"] = _agg([x.get("wing_wing_g") for x in g]).get("median")
        rec["wing_base"] = _agg([x.get("wing_wing_b") for x in g]).get("median")
        rec["zeta_mean"] = _agg([x["zeta"] for x in g]).get("mean")
        rec["zeta_std"] = _agg([x["zeta"] for x in g]).get("std")
        out.append(rec)
    return out


def _write(rows, summary, name: str) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    base = os.path.join(RESULTS_DIR, name)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"rows": rows, "summary": summary}, fh, default=str, indent=2)
    return base


def main() -> int:
    ap = argparse.ArgumentParser(description="Graph leave-one-out backtest.")
    ap.add_argument("--regime", default="spike_aug2024")
    ap.add_argument("--designs", default="full_loo,liquid_split")
    ap.add_argument("--regimes-r", default="0,1", help="SSR R values to sweep (0 and/or 1)")
    ap.add_argument("--max-pairs", type=int, default=None)
    args = ap.parse_args()
    designs = tuple(d.strip() for d in args.designs.split(","))
    r_values = tuple(float(r) for r in args.regimes_r.split(","))
    print(f"regime={args.regime} designs={designs} R={r_values}", flush=True)

    rows = run(args.regime, designs, r_values, args.max_pairs, EdgeConfig())
    summary = summarize(rows)
    base = _write(rows, summary, f"{args.regime}_graph_loo")
    print(f"\nwrote {base}.json  ({len(rows)} scored nodes)\n")
    hdr = f"{'design':<14}{'R':>2}{'n':>5}{'atmGr':>8}{'atmBs':>8}{'atmSk':>8}{'wGr':>7}{'wBs':>7}{'zMean':>7}{'zStd':>7}"
    print(hdr)
    for s in summary:
        print(f"{s['design']:<14}{s['ssr']:>2}{s['n']:>5}{s['atm_graph_rms']:>8}"
              f"{s['atm_base_rms']:>8}{s['atm_skill']:>8}{str(s['wing_graph']):>7}"
              f"{str(s['wing_base']):>7}{str(s['zeta_mean']):>7}{str(s['zeta_std']):>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
