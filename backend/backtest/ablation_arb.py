"""R3 (convex de-Am) x R6 (put-wing penalty) ablation on SIV wing arbitrage.

FINDINGS_calibration_arb follow-up. R3 (`volfit/calib/convex_deam.py`) repairs the
non-convex de-Americanized call *inputs*; R6 (`models/sigmoid/calibrate.py`
`wing_penalty`) regularizes the SIV *output* wing. Both defend the SAME put-wing
butterfly pathology (F4: 64% of SIV g<0 lives in the put wing) from opposite ends,
and both ship default-on — so on any given illiquid node it is not known which one
actually removes the arb, nor whether they are redundant.

This isolates that by fitting every American node under the 2x2

    {R3 off, R3 on} x {R6 off, R6 on}   -> "neither" / "R3" / "R6" / "both"

and measuring the analytic Durrleman g(k) on an EXTENDED grid that reaches
``pad_z`` standardized-moneyness units past the traded range (where the wing
violations actually live), plus the in-sample and leave-every-3rd-out RMS so the
precision COST of each defence is visible next to the arb it removes.

The arb is read from the model's own analytic ``gatheral_g`` (no finite-difference
reconstruction noise — the R2 lesson). ``ablate_node`` takes a live ``AppState`` and
is fixture-independent, so the same code runs against captured fixtures (below) or a
synthetic American chain (the test).

    python -m backtest.ablation_arb --regime spike_aug2024
    python -m backtest.ablation_arb --regime spike_aug2024 --assets EEM,EFA --cores 2
"""

from __future__ import annotations

import argparse
import os
import statistics
from collections import defaultdict
from datetime import date

import numpy as np

from volfit.api.quotes import prepare_quotes
from volfit.api.service import variance_time
from volfit.api.state import AppState
from volfit.calib.rms import node_error_terms, rms
from volfit.calib.weights import resolve_weights
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.sigmoid.calibrate import WING_PENALTY_BASE

from backtest.replay import Fixture, list_fixtures, load_fixture, state_for_day

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

#: Production SIV hyperparameters (mirrors dispatch._SIG / volfit.api.schemas).
_SIG = dict(ridge=1e-2, mid_anchor_weight=0.05)

#: R6 at the shipped default (sivWingPenaltyPct = 100 -> base strength).
_R6_ON = WING_PENALTY_BASE

#: How far past the traded log-moneyness range (in ATM std units) the arb grid
#: reaches — matched to R6's own penalty pad (calibrate._WING_PAD = 2.0) so the
#: metric scores exactly the wing region the penalty is meant to discipline.
_PAD_Z = 2.0

#: MATERIAL butterfly threshold on the extended grid: a Durrleman g below -_ARB_G_TOL
#: is a genuine violation. It is deliberately NOT dispatch's tight 1e-6 — the SIV base
#: carries benign g~1e-2 in the far (>2z) extrapolation even on a clean node, while
#: genuine dense-quote violations run O(1-10) and R6-repaired residuals settle at
#: O(1e-2) (FINDINGS: -10.2 -> -0.008). 0.05 sits in that gap, so it separates real
#: arb from benign wing curvature. The continuous median min_g / put_min_g remain the
#: primary, threshold-free signal; this only drives the binary arb-rate / repaired-frac.
_ARB_G_TOL = 0.05

#: The four ablation cells: (label, R3 convex-de-Am on?, R6 wing-penalty strength).
_CONFIGS: tuple[tuple[str, bool, float], ...] = (
    ("neither", False, 0.0),
    ("R3", True, 0.0),
    ("R6", False, _R6_ON),
    ("both", True, _R6_ON),
)


def _prepared(state: AppState, ticker: str, expiry: date, convex_deam: bool):
    """PreparedQuotes for a node with the R3 convex-wing repair on/off.

    Replicates the resolution ``service.prepared_quotes`` does (forward, cash
    schedule, dual clock) but calls ``prepare_quotes`` directly so the ``convex_deam``
    flag can be toggled — the memoized service path is hard-wired to the default-on."""
    forward = state.resolved_forward(ticker, expiry)
    cash_divs = state.cash_dividend_schedule(ticker, expiry, forward.forward)
    t_cal = state.year_fraction(expiry)
    tau = variance_time(state, ticker, expiry, t_cal)
    return prepare_quotes(
        state.snapshot(ticker), expiry, forward, t_cal, cash_divs,
        tau=tau, convex_deam=convex_deam,
    )


def _ext_grid(k: np.ndarray, w_atm: float, pad_z: float = _PAD_Z) -> np.ndarray:
    """Log-moneyness grid over the traded range extended ``pad_z`` ATM-std each side.

    ``sqrt(w_atm)`` is the ATM standardized-moneyness scale (z = k / sqrt(w_atm)), so
    padding by ``pad_z * sqrt(w_atm)`` reaches ``pad_z`` z-units into the unquoted
    wings — the F4 region (median worst violation at z = -3.2)."""
    s = float(np.sqrt(max(w_atm, 1e-12)))
    return np.linspace(float(k.min()) - pad_z * s, float(k.max()) + pad_z * s, 201)


def _wing_arb(slice_, grid: np.ndarray) -> tuple[float, float, float]:
    """(min g, put-wing min g [k<0], fraction of the grid with g<0) — analytic."""
    g = np.asarray(slice_.gatheral_g(grid), float)
    ok = np.isfinite(g)
    g, gk = g[ok], grid[ok]
    if g.size == 0:
        return 0.0, 0.0, 0.0
    put = g[gk < 0.0]
    put_min = float(put.min()) if put.size else 0.0
    return float(g.min()), put_min, float(np.mean(g < 0.0))


def _fit(prepared, n_cores: int, wing_penalty: float, weights: np.ndarray):
    """Fit Multi-Core SIV at production defaults with the given R6 strength (mid)."""
    return calibrate_sigmoid(
        prepared.k, prepared.w_mid, prepared.tau, weights=weights,
        n_cores=n_cores, wing_penalty=wing_penalty, **_SIG,
    )


def _rms_bp(slice_, k, w, tau, weights) -> float:
    """In-sample weighted RMS vol error (bp), consistent with the mid objective."""
    if k.size == 0:
        return 0.0
    model_iv = np.sqrt(np.maximum(slice_.implied_w(k), 1e-12) / tau)
    quote_iv = np.sqrt(np.maximum(np.asarray(w, float), 1e-12) / tau)
    num, den = node_error_terms(model_iv, quote_iv, weights=weights, band=None)
    return rms(num, den) * 1e4


def _oos_rms_bp(prepared, n_cores, wing_penalty, weights) -> float | None:
    """Leave-every-3rd-strike-out RMS (bp) at this config (None if too few strikes)."""
    k, w, tau = prepared.k, prepared.w_mid, prepared.tau
    n = k.size
    if n < 9:
        return None
    held = np.arange(n) % 3 == 0
    kept = ~held
    wk = None if weights is None else np.asarray(weights)[kept]
    try:
        s = calibrate_sigmoid(k[kept], w[kept], tau, weights=wk, n_cores=n_cores,
                              wing_penalty=wing_penalty, **_SIG)
    except Exception:  # noqa: BLE001 - a failed OOS refit is a metric, not a crash
        return None
    return _rms_bp(s, k[held], w[held], tau, None if weights is None else weights[held])


def ablate_node(
    state: AppState, ticker: str, expiry: date, regime: str = "", sector: str = "",
    n_cores: int = 2, weight_scheme: str = "equal", pad_z: float = _PAD_Z,
    oos: bool = True,
) -> list[dict]:
    """One row per ablation cell for a node: R3xR6 arb + precision metrics.

    ``n_cores`` is the SIV flexibility that manufactures the wing arb (default 2, the
    production cap). ``oos=False`` skips the leave-every-3rd-out refit (halves the fit
    count — the CLI default, since in-sample RMS already carries the precision cost;
    opt back in with ``--oos``). Returns four rows tagged ``config`` in
    {neither, R3, R6, both}."""
    # Prepare the de-Am inputs once per R3 setting (shared across the R6 axis).
    prep = {r3: _prepared(state, ticker, expiry, r3) for r3 in (False, True)}
    base = prep[False]
    w_atm = float(np.interp(0.0, base.k, base.w_mid)) if base.k.size else 0.0
    grid = _ext_grid(base.k, w_atm, pad_z)

    rows: list[dict] = []
    for label, r3, r6 in _CONFIGS:
        prepared = prep[r3]
        weights = resolve_weights(weight_scheme, prepared.k, prepared.w_mid)
        row = dict(
            asset=ticker, as_of=state.reference_date.isoformat(), regime=regime,
            sector=sector, expiry=expiry.isoformat(), t=round(float(base.t), 5),
            n_cores=n_cores, config=label, r3=r3, r6=bool(r6),
            n_quotes=int(prepared.k.size), n_deam=int(prepared.n_deamericanized),
        )
        try:
            slice_ = _fit(prepared, n_cores, r6, weights)
            min_g, put_min_g, neg_frac = _wing_arb(slice_, grid)
            row.update(
                ok=True,
                min_g=round(min_g, 6), put_min_g=round(put_min_g, 6),
                neg_frac=round(neg_frac, 4), arb=bool(min_g < -_ARB_G_TOL),
                in_rmse_bp=round(_rms_bp(slice_, prepared.k, prepared.w_mid,
                                         prepared.tau, weights), 2),
                oos_rmse_bp=(_round(_oos_rms_bp(prepared, n_cores, r6, weights))
                             if oos else None),
            )
        except Exception as exc:  # noqa: BLE001 - a fit break is a recorded result
            row.update(ok=False, error=type(exc).__name__ + ": " + str(exc)[:120])
        rows.append(row)
    return rows


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 2)


# --------------------------------------------------------------------- driver

def _american_fixtures(regime: str, assets: set[str] | None) -> list[str]:
    """Captured fixture paths for the American nodes of interest in a regime."""
    paths = list_fixtures(regime=regime)
    keep: list[str] = []
    for p in paths:
        f = load_fixture(p)
        if f.exercise_style != "american":
            continue
        if assets and f.asset not in assets:
            continue
        keep.append(p)
    return keep


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def _summarize(rows: list[dict]) -> dict:
    """Aggregate the 2x2 over the ARB-PRONE population (nodes whose 'neither' cell is
    arbitraged) — the only nodes where the two defences have anything to do.

    Reports, per cell: median extended-grid min-g, median put-wing min-g, the arb
    rate (share still butterfly-violating), and median in / OOS RMS — so the arb
    removed sits next to the precision paid. Attribution = repair rate per cell."""
    by_node: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        if r.get("ok"):
            by_node[(r["asset"], r["expiry"], r["as_of"])][r["config"]] = r
    # Arb-prone = the baseline cell is a genuine violation.
    prone = [cells for cells in by_node.values()
             if cells.get("neither", {}).get("arb")]
    cells_summary: dict[str, dict] = {}
    for label, _r3, _r6 in _CONFIGS:
        got = [c[label] for c in prone if label in c]
        if not got:
            continue
        cells_summary[label] = dict(
            n=len(got),
            median_min_g=_median([g["min_g"] for g in got]),
            median_put_min_g=_median([g["put_min_g"] for g in got]),
            arb_rate=round(float(np.mean([g["arb"] for g in got])), 3),
            repaired_frac=round(float(np.mean([not g["arb"] for g in got])), 3),
            median_in_rmse_bp=_median([g["in_rmse_bp"] for g in got]),
            median_oos_rmse_bp=_median([g["oos_rmse_bp"] for g in got]),
        )
    return dict(n_nodes=len(by_node), n_arb_prone=len(prone), cells=cells_summary)


def _print_summary(summary: dict) -> None:
    print(f"\nnodes={summary['n_nodes']}  arb-prone (neither-cell g<0)="
          f"{summary['n_arb_prone']}")
    cells = summary["cells"]
    if not cells:
        print("  no arb-prone American nodes in this set — nothing to ablate.")
        return
    hdr = f"  {'cell':<8}{'n':>4}{'min_g':>10}{'put_g':>10}{'arb%':>7}" \
          f"{'repaired%':>11}{'in_bp':>8}{'oos_bp':>8}"
    print(hdr)
    for label, _r3, _r6 in _CONFIGS:
        c = cells.get(label)
        if not c:
            continue
        print(f"  {label:<8}{c['n']:>4}{_fmt(c['median_min_g']):>10}"
              f"{_fmt(c['median_put_min_g']):>10}{c['arb_rate']*100:>6.1f}%"
              f"{c['repaired_frac']*100:>10.1f}%{_fmt(c['median_in_rmse_bp']):>8}"
              f"{_fmt(c['median_oos_rmse_bp']):>8}")


def _fmt(x: float | None) -> str:
    return "-" if x is None else f"{x:g}"


def main() -> int:
    ap = argparse.ArgumentParser(description="R3xR6 SIV wing-arb ablation.")
    ap.add_argument("--regime", default="spike_aug2024")
    ap.add_argument("--assets", default=None,
                    help="comma-separated American assets (default: all American).")
    ap.add_argument("--cores", type=int, default=2, help="SIV cores (default 2).")
    ap.add_argument("--max-days", type=int, default=None,
                    help="cap the number of as-of days (speed; default all).")
    ap.add_argument("--oos", dest="oos", action="store_true", default=False,
                    help="also compute the leave-3rd-out OOS refit (2x the fits; "
                         "off by default — in-sample RMS already carries the cost).")
    args = ap.parse_args()
    assets = {a.strip() for a in args.assets.split(",")} if args.assets else None

    paths = _american_fixtures(args.regime, assets)
    if not paths:
        raise SystemExit(
            f"no American fixtures for regime={args.regime} assets={assets}. "
            "Capture first: python -m backtest.capture --universe pilot "
            f"--regimes {args.regime}")
    by_date: dict[date, list[Fixture]] = defaultdict(list)
    for p in paths:
        f = load_fixture(p)
        by_date[f.as_of].append(f)
    days = sorted(by_date)
    if args.max_days is not None:
        days = days[: args.max_days]
    n_fix = sum(len(by_date[d]) for d in days)
    print(f"{n_fix} American fixtures over {len(days)} days; cores={args.cores} "
          f"oos={args.oos}", flush=True)

    rows: list[dict] = []
    for as_of in days:
        fixtures = by_date[as_of]
        state = state_for_day(fixtures)
        for f in fixtures:
            for expiry in f.expiries:
                try:
                    rows.extend(ablate_node(state, f.asset, expiry, f.regime,
                                            f.sector, n_cores=args.cores, oos=args.oos))
                except Exception as exc:  # noqa: BLE001
                    rows.append(dict(asset=f.asset, expiry=expiry.isoformat(),
                                     ok=False, error=str(exc)[:140]))
        print(f"  {as_of}: {len(fixtures)} assets done", flush=True)

    summary = _summarize(rows)
    os.makedirs(RESULTS_DIR, exist_ok=True)
    import json

    out = os.path.join(RESULTS_DIR, f"{args.regime}_ablation_arb.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(dict(rows=rows, summary=summary), fh, default=str)
    _print_summary(summary)
    print(f"\nwrote {out}  ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
