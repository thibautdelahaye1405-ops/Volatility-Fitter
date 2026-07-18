"""Phase-0 empirical study for the precision-message graph redesign.

Answers, from the STORED benchmark rows (no recapture, no new solve), the two
Phase-0 exit questions of Docs/graph_precision_message_framework.md §23:

1. **Anchor mechanization** (§14.2): does realized innovation transfer RISE
   when a receiver has corroborating sources? Compare the through-origin
   slope of a dark name's normalized innovation on (a) the index alone vs
   (b) the equal-weight average of index + same-sector peers. A material
   uplift favours the node-linked (fixed-kappa, corroboration-adaptive)
   anchor; a flat slope favours the edge-linked (constant-transfer) anchor.
   Pre-registered bar: uplift >= 15% with both slopes t-significant.

2. **Initial numeric defaults** (§9.2/§9.4): the calendar relation-noise
   family under the alphaT=1 shape — fit the level, bucket squared residuals
   by sqrt(maturity gap), and fit Var(e) = (epsT + g)/p0 to seed
   `calendarPrecisionScale` (p0) and `calendarPrecisionEpsilon` (epsT) —
   plus cross-class message noise (index->name, sector-peer) in normalized
   and ATM-vol units.

Uses ALL stored full_loo days (this is a design study, not an adoption gate
— the gate is Phase 4's strict-time-split sweep). Innovations are knob-
independent (`base_atm` never sees the solve), so pooling tags is sound.

Run (from backend/, after any benchmark pack has populated results/)::

    python -m backtest.message_phase0          # writes results/message_phase0.json
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

import numpy as np

from backtest.graph_edges import asset_kind, asset_sector
from backtest.learn_betas import (
    _estimation_days,
    _expiry_panel,
    _innovation_panel,
    _load_rows,
    _sigma_table,
    _slope,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
DEFAULT_OUT = os.path.join(RESULTS_DIR, "message_phase0.json")

HUB = "SPX"
UPLIFT_BAR = 0.15  # pre-registered: corroboration uplift needed for node-linked
N_GAP_BUCKETS = 5
EPS_T_FLOOR = 0.01  # sqrt-years; guards a negative fitted intercept


# ----------------------------------------------------------------- utilities
def _r2_origin(x: np.ndarray, y: np.ndarray, b: float) -> float:
    """Through-origin R^2 (1 - SS_res / sum y^2)."""
    ss_tot = float(y @ y)
    if ss_tot <= 0.0:
        return 0.0
    resid = y - b * x
    return 1.0 - float(resid @ resid) / ss_tot


def _by_day(panel: dict, sigma: dict) -> dict[tuple, dict[str, float]]:
    """{(regime, day): {ticker: vol-normalized innovation}}."""
    out: dict[tuple, dict[str, float]] = defaultdict(dict)
    for (regime, day, tk), d in panel.items():
        s = sigma.get((regime, tk))
        if s:
            out[(regime, day)][tk] = d / s
    return out


# ------------------------------------------------- part A: corroboration test
def corroboration_study(by_day: dict) -> dict:
    """Single-source vs corroborated-predictor transfer slopes (§14.2)."""
    y1, x_idx = [], []          # name vs index alone (names WITH peers only,
    y2, x_peer = [], []         # so the three regressions share a population)
    y12, x_comb = [], []
    xb1, xb2, yb = [], [], []
    for z in by_day.values():
        if HUB not in z:
            continue
        for tk, z_tk in z.items():
            if asset_kind(tk) != "name":
                continue
            peers = [
                z[p] for p in z
                if p != tk and asset_kind(p) == "name"
                and asset_sector(p) == asset_sector(tk)
            ]
            if not peers:
                continue
            peer_bar = float(np.mean(peers))
            y1.append(z_tk), x_idx.append(z[HUB])
            y2.append(z_tk), x_peer.append(peer_bar)
            y12.append(z_tk), x_comb.append(0.5 * (z[HUB] + peer_bar))
            yb.append(z_tk), xb1.append(z[HUB]), xb2.append(peer_bar)

    x1, yy1 = np.array(x_idx), np.array(y1)
    x2, yy2 = np.array(x_peer), np.array(y2)
    xc, yyc = np.array(x_comb), np.array(y12)
    b1, t1, n1 = _slope(x1, yy1)
    b2, t2, n2 = _slope(x2, yy2)
    bc, tc, nc = _slope(xc, yyc)

    a1, a2 = np.array(xb1), np.array(xb2)
    yy = np.array(yb)
    gram = np.array([[a1 @ a1, a1 @ a2], [a1 @ a2, a2 @ a2]])
    rhs = np.array([a1 @ yy, a2 @ yy])
    biv = np.linalg.solve(gram, rhs) if np.linalg.det(gram) > 0 else np.array([0.0, 0.0])

    uplift = bc / b1 - 1.0 if b1 > 0 else float("nan")
    significant = abs(t1) >= 2.0 and abs(tc) >= 2.0
    verdict = (
        "node_linked" if significant and np.isfinite(uplift) and uplift >= UPLIFT_BAR
        else "edge_linked"
    )
    return {
        "indexOnly": {"b": round(b1, 4), "t": round(t1, 2), "n": n1,
                      "r2": round(_r2_origin(x1, yy1, b1), 4)},
        "peersOnly": {"b": round(b2, 4), "t": round(t2, 2), "n": n2,
                      "r2": round(_r2_origin(x2, yy2, b2), 4)},
        "combinedEqualWeight": {"b": round(bc, 4), "t": round(tc, 2), "n": nc,
                                "r2": round(_r2_origin(xc, yyc, bc), 4)},
        "bivariate": {"bIndex": round(float(biv[0]), 4),
                      "bPeers": round(float(biv[1]), 4),
                      "totalLoading": round(float(biv.sum()), 4)},
        "uplift": round(float(uplift), 4),
        "upliftBar": UPLIFT_BAR,
        "anchorVerdict": verdict,
    }


# ------------------------------------------- part B: calendar precision family
def _calendar_pairs(expiry_panel: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, gap) over adjacent ladder pairs in canonical short-receiver
    orientation: y = d_short, x = (t_long/t_short)^1 * d_long (alphaT=1),
    gap = sqrt(t_long - t_short) in sqrt-years."""
    ladders: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for (regime, day, tk, iso), d in expiry_panel.items():
        t = (date.fromisoformat(iso) - date.fromisoformat(day)).days / 365.0
        if t > 0:
            ladders[(regime, day, tk)].append((t, d))
    xs, ys, gaps = [], [], []
    for pts in ladders.values():
        pts.sort()
        for (t_s, d_s), (t_l, d_l) in zip(pts[:-1], pts[1:]):
            xs.append((t_l / t_s) * d_l)
            ys.append(d_s)
            gaps.append(np.sqrt(t_l - t_s))
    return np.array(xs), np.array(ys), np.array(gaps)


def calendar_precision_study(expiry_panel: dict) -> dict:
    """Fit the alphaT=1 level, then Var(residual) = (epsT + g)/p0 over
    sqrt-gap buckets -> calendarPrecisionScale / Epsilon defaults (§9.2)."""
    x, y, g = _calendar_pairs(expiry_panel)
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(g)
    x, y, g = x[m], y[m], g[m]
    b, t_stat, n = _slope(x, y)
    resid = y - b * x

    order = np.argsort(g)
    buckets = np.array_split(order, N_GAP_BUCKETS)
    bucket_rows = []
    gm, vv = [], []
    for idx in buckets:
        if idx.size < 20:
            continue
        gbar = float(np.mean(g[idx]))
        var = float(np.var(resid[idx]))
        bucket_rows.append({"gapSqrtYears": round(gbar, 4),
                            "residVar": round(var, 8), "n": int(idx.size),
                            "residRmsVolPts": round(np.sqrt(var) * 100, 3)})
        gm.append(gbar), vv.append(var)

    gm_a, vv_a = np.array(gm), np.array(vv)
    slope, intercept = np.polyfit(gm_a, vv_a, 1) if gm_a.size >= 2 else (np.nan, np.nan)
    p0 = 1.0 / slope if slope and slope > 0 else float("nan")
    eps_t = max(intercept / slope, EPS_T_FLOOR) if slope and slope > 0 else float("nan")

    # Shape preview only (the P4 sweep adjudicates): level + R^2 per alphaT.
    shapes = {}
    for alpha, (xa, ya) in _calendar_pairs_by_alpha(expiry_panel).items():
        ba, ta, na = _slope(xa, ya)
        shapes[str(alpha)] = {"level": round(ba, 4), "t": round(ta, 2),
                              "r2": round(_r2_origin(xa, ya, ba), 4), "n": na}

    return {
        "alphaT1Level": {"b": round(b, 4), "t": round(t_stat, 2), "n": n},
        "gapBuckets": bucket_rows,
        "fit": {"p0": round(p0, 2), "epsT": round(eps_t, 4),
                "model": "Var(e) = (epsT + sqrt(dT)) / p0, vol^2 units"},
        "tau1mVolPts": round(
            float(np.sqrt((eps_t + np.sqrt(1.0 / 12.0)) / p0)) * 100, 3
        ) if np.isfinite(p0) else None,
        "shapePreview": shapes,
    }


def _calendar_pairs_by_alpha(expiry_panel: dict) -> dict:
    """{alpha: (x, y)} with x = (t_l/t_s)^alpha * d_l, y = d_s."""
    ladders: dict[tuple, list[tuple[float, float]]] = defaultdict(list)
    for (regime, day, tk, iso), d in expiry_panel.items():
        t = (date.fromisoformat(iso) - date.fromisoformat(day)).days / 365.0
        if t > 0:
            ladders[(regime, day, tk)].append((t, d))
    out = {}
    for alpha in (0.0, 0.5, 1.0):
        xs, ys = [], []
        for pts in ladders.values():
            pts.sort()
            for (t_s, d_s), (t_l, d_l) in zip(pts[:-1], pts[1:]):
                xs.append((t_l / t_s) ** alpha * d_l)
                ys.append(d_s)
        x, y = np.array(xs), np.array(ys)
        m = np.isfinite(x) & np.isfinite(y)
        out[alpha] = (x[m], y[m])
    return out


# ------------------------------------------- part C: cross-class message noise
def cross_class_noise(by_day: dict, sigma: dict) -> dict:
    """Residual message noise per relation class -> precision defaults.

    Normalized-unit residual variance around the class's own predictive
    slope; converted to ATM-vol units with the median sigma scale so the
    defaults land in the spec's messagePrecision units (§9.4)."""
    idx_x, idx_y, peer_x, peer_y = [], [], [], []
    for z in by_day.values():
        for tk, z_tk in z.items():
            if asset_kind(tk) != "name":
                continue
            if HUB in z:
                idx_y.append(z_tk), idx_x.append(z[HUB])
            for p in z:
                if p != tk and asset_kind(p) == "name" and \
                        asset_sector(p) == asset_sector(tk):
                    peer_y.append(z_tk), peer_x.append(z[p])
    sigma_med = float(np.median(list(sigma.values()))) if sigma else float("nan")

    def _class(xs: list, ys: list) -> dict:
        x, y = np.array(xs), np.array(ys)
        b, t_stat, n = _slope(x, y)
        var_norm = float(np.var(y - b * x))
        var_vol = var_norm * sigma_med**2
        return {"b": round(b, 4), "t": round(t_stat, 2), "n": n,
                "residVarNorm": round(var_norm, 6),
                "residRmsVolPts": round(np.sqrt(var_vol) * 100, 3),
                "precisionVolUnits": round(1.0 / var_vol, 2) if var_vol > 0 else None}

    return {"sigmaMedian": round(sigma_med, 4),
            "indexToName": _class(idx_x, idx_y),
            "sectorPeer": _class(peer_x, peer_y)}


# ------------------------------------------------------------------------ run
def run(out_path: str = DEFAULT_OUT) -> dict:
    rows = _load_rows()
    est_days, _ = _estimation_days(rows, split=1.0)  # ALL days: design study
    panel = _innovation_panel(rows, est_days, ssr=0)
    sigma = _sigma_table(est_days)
    by_day = _by_day(panel, sigma)

    result = {
        "version": 1,
        "kind": "message_phase0",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "days": {r: len(d) for r, d in est_days.items()},
        "corroboration": corroboration_study(by_day),
        "calendarPrecision": calendar_precision_study(
            _expiry_panel(rows, est_days, ssr=0)
        ),
        "crossClassNoise": cross_class_noise(by_day, sigma),
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    return result


def _show(res: dict) -> None:
    c = res["corroboration"]
    print(f"message_phase0 - {res['generatedAt']} - days {res['days']}")
    print("\n[A] corroboration test (anchor mechanization, spec 14.2)")
    for k in ("indexOnly", "peersOnly", "combinedEqualWeight"):
        v = c[k]
        print(f"  {k:<22} b={v['b']:<8} t={v['t']:<8} n={v['n']:<7} r2={v['r2']}")
    bv = c["bivariate"]
    print(f"  bivariate              bIdx={bv['bIndex']} bPeers={bv['bPeers']} "
          f"total={bv['totalLoading']}")
    print(f"  uplift={c['uplift']} (bar {c['upliftBar']}) -> "
          f"ANCHOR VERDICT: {c['anchorVerdict']}")
    cal = res["calendarPrecision"]
    print("\n[B] calendar precision family (alphaT=1 shape, spec 9.2)")
    print(f"  level b={cal['alphaT1Level']['b']} t={cal['alphaT1Level']['t']} "
          f"n={cal['alphaT1Level']['n']}")
    for row in cal["gapBuckets"]:
        print(f"    gap sqrtY {row['gapSqrtYears']:<8} residVar {row['residVar']:<12} "
              f"rms {row['residRmsVolPts']} volpts  n={row['n']}")
    print(f"  fit: p0={cal['fit']['p0']} epsT={cal['fit']['epsT']} "
          f"-> tau(1M gap) ~ {cal['tau1mVolPts']} volpts")
    print("  shape preview (level, r2 by alphaT):")
    for a, v in cal["shapePreview"].items():
        print(f"    alphaT={a:<4} level={v['level']:<8} r2={v['r2']}")
    x = res["crossClassNoise"]
    print(f"\n[C] cross-class message noise (sigma_med {x['sigmaMedian']})")
    for k in ("indexToName", "sectorPeer"):
        v = x[k]
        print(f"  {k:<14} b={v['b']:<8} residRms {v['residRmsVolPts']} volpts "
              f"-> precision {v['precisionVolUnits']} (1/vol^2)  n={v['n']}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # cp1252 console guard
    except Exception:  # noqa: BLE001
        pass
    res = run()
    _show(res)
    print(f"\nwrote {DEFAULT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
