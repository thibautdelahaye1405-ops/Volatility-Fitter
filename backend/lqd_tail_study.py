"""LQD tail-stability study (committee revision R3, points 3 and 6).

The exponential skeleton makes A_L / A_R / Lee slopes powerful TAIL PRIORS;
this study measures how much they are OBSERVATIONS, by refitting one strike
strip under the perturbations a referee would apply:

- jackknife: drop the outermost 1-2 quotes on each side;
- basis order N and ridge lambda sweeps;
- quote noise: +-1 vol bp iid, many draws;
- multi-start: random offsets around the standard initializer (question 6:
  how many starts fail or reach materially different minima).

Per refit it records the tail ladder (A_L, A_R, Lee slopes), var-swap vol,
10-delta / 1-delta wing vols and the EFFECTIVE slope w(k)/|k| at those
strikes (traders price the wing at a delta, not at k -> inf), plus ATM-region
digitals. Output: a JSON fan consumed by the Note 01 figure generator and a
printed summary table.

Usage (from backend/, venv python):
    python lqd_tail_study.py                       # note's SSVI-shaped strip
    python lqd_tail_study.py --fixture <json> [--ticker SPY --node 3]
        # a surface-export fixture with embedded inputs (reference live file)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import norm

from volfit.calib.band import resolve_band
from volfit.models.lqd.basis import lee_slopes
from volfit.models.lqd.calibrate import calibrate_slice, logistic_init
from volfit.models.lqd.charts import build_chart

#: Committee-protocol sweep grids.
ORDERS = (6, 8, 10, 12, 16)
LAMBDAS = (0.0, 1e-8, 1e-6, 1e-4, 1e-2)
N_NOISE = 20
NOISE_VOL = 1e-4  # 1 vol bp
N_STARTS = 10
START_SCALE = 0.35  # logistic-chart offset std for multi-start


def ssvi_strip() -> tuple[np.ndarray, np.ndarray, float]:
    """The note's SPX-like SSVI-shaped oracle strip (Appendix: oracles)."""
    theta, rho, phi = 0.0356, -0.68, 2.40
    k = np.array([-0.28, -0.24, -0.20, -0.17, -0.14, -0.12, -0.10, -0.08,
                  -0.06, -0.05, -0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02,
                  0.03, 0.05, 0.07, 0.09, 0.12, 0.16, 0.20])
    w = 0.5 * theta * (1.0 + rho * phi * k
                       + np.sqrt((phi * k + rho) ** 2 + 1.0 - rho ** 2))
    w = (np.sqrt(w) + 1e-4 * (1.20 * np.sin(9 * k + 0.4)
                              + 0.55 * np.cos(21 * k))) ** 2
    return k, w, 0.25


def fixture_strip(path: str, ticker: str, node: int):
    """(k, w, t) plus the haircut band from a surface export with inputs."""
    with open(path) as f:
        fx = json.load(f)
    tk = next(t for t in fx["tickers"] if t["ticker"] == ticker)
    nd = tk["nodes"][node]
    cols = nd["inputs"]["preparedColumns"]
    arr = np.asarray(nd["inputs"]["prepared"], dtype=float)
    k = arr[:, cols.index("k")]
    iv_mid = arr[:, cols.index("ivMid")]
    tau = float(nd["tau"])
    band = resolve_band(
        arr[:, cols.index("ivBid")], iv_mid, arr[:, cols.index("ivAsk")],
        "haircut", haircut=fx["manifest"]["fitSettings"]["haircut"],
    )
    return k, iv_mid ** 2 * tau, tau, band


def _delta_strike(slice_, t: float, delta: float, sign: int) -> float:
    """Log-strike where the Black delta (call for sign>0, put for sign<0)
    equals ``delta``, solved by bisection on the fitted smile."""
    def excess(k: float) -> float:
        w = float(slice_.implied_w(np.asarray([k]))[0])
        d1 = (-k + 0.5 * w) / np.sqrt(w)
        return (norm.cdf(d1) if sign > 0 else norm.cdf(-d1)) - delta

    lo, hi = 0.0, sign * 2.5
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if excess(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def observe(result, t: float) -> dict:
    """The tail/wing observables of one converged fit."""
    s = result.slice
    beta_l, beta_r = lee_slopes(result.params)
    out = {
        "aL": s.a_left, "aR": s.a_right, "betaL": beta_l, "betaR": beta_r,
        "varSwapVol": float(np.sqrt(s.var_swap_strike() / t)),
        "maxIvErrBp": result.max_iv_error * 1e4,
        "cost": result.cost,
        "success": bool(result.success),
    }
    for delta, tag in ((0.10, "10d"), (0.01, "1d")):
        for sign, side in ((-1, "put"), (1, "call")):
            k = _delta_strike(s, t, delta, sign)
            w = float(s.implied_w(np.asarray([k]))[0])
            out[f"vol_{tag}_{side}"] = float(np.sqrt(w / t))
            out[f"slope_{tag}_{side}"] = w / abs(k) if k != 0.0 else np.nan
    return out


def run_study(k, w, t, band=None, n_order: int = 12, reg_lambda: float = 1e-6,
              seed: int = 20260719) -> dict:
    """The full committee protocol around one baseline configuration."""
    rng = np.random.default_rng(seed)
    base_kwargs = dict(t=t, n_order=n_order, reg_lambda=reg_lambda, band=band)

    def fit(kk, ww, **over):
        kwargs = dict(base_kwargs, **over)
        if band is not None and ("band" not in over) and kk.size != k.size:
            # jackknife: cut the band rows with the quotes
            keep = np.isin(k, kk)
            kwargs["band"] = type(band)(
                iv_lo=band.iv_lo[keep], iv_mid=band.iv_mid[keep],
                iv_hi=band.iv_hi[keep])
        return calibrate_slice(kk, ww, **kwargs)

    study: dict = {"baseline": observe(fit(k, w), t), "protocol": {
        "nQuotes": int(k.size), "nOrder": n_order, "regLambda": reg_lambda,
        "t": t, "kMin": float(k.min()), "kMax": float(k.max()),
    }}

    jack = {}
    for cut, tag in ((1, "drop1"), (2, "drop2")):
        jack[f"{tag}_left"] = observe(fit(k[cut:], w[cut:]), t)
        jack[f"{tag}_right"] = observe(fit(k[:-cut], w[:-cut]), t)
        jack[f"{tag}_both"] = observe(fit(k[cut:-cut], w[cut:-cut]), t)
    study["jackknife"] = jack

    study["orders"] = {
        str(n): observe(fit(k, w, n_order=n), t) for n in ORDERS
    }
    study["lambdas"] = {
        f"{lam:.0e}": observe(fit(k, w, reg_lambda=lam), t) for lam in LAMBDAS
    }

    noise = []
    sigma = np.sqrt(w / t)
    for _ in range(N_NOISE):
        pert = (sigma + rng.normal(0.0, NOISE_VOL, k.size)) ** 2 * t
        noise.append(observe(fit(k, pert), t))
    study["noise"] = noise

    starts, chart = [], build_chart(n_order, "logistic")
    psi0 = chart.from_theta(
        logistic_init(float(np.interp(0.0, k, w)), n_order).to_vector())
    for _ in range(N_STARTS):
        psi = psi0 + rng.normal(0.0, START_SCALE, psi0.size)
        from volfit.models.lqd.basis import LQDParams
        init = LQDParams.from_vector(chart.to_theta(psi))
        starts.append(observe(fit(k, w, init=init), t))
    study["multistart"] = starts
    return study


def summarize(study: dict) -> str:
    """Fan table: baseline vs the min..max range of each observable."""
    keys = ("aL", "aR", "betaL", "betaR", "varSwapVol",
            "vol_10d_put", "vol_1d_put", "slope_1d_put", "maxIvErrBp")
    fans = {key: [] for key in keys}
    for group in ("jackknife", "orders", "lambdas"):
        for obs in study[group].values():
            for key in keys:
                fans[key].append(obs[key])
    for group in ("noise", "multistart"):
        for obs in study[group]:
            for key in keys:
                fans[key].append(obs[key])
    lines = [f"{'observable':<14}{'baseline':>12}{'min':>12}{'max':>12}"
             f"{'spread%':>10}"]
    for key in keys:
        base, vals = study["baseline"][key], np.asarray(fans[key], dtype=float)
        spread = (vals.max() - vals.min()) / max(abs(base), 1e-12) * 100.0
        lines.append(f"{key:<14}{base:>12.5g}{vals.min():>12.5g}"
                     f"{vals.max():>12.5g}{spread:>10.1f}")
    n_fail = sum(not o["success"] for o in study["multistart"])
    costs = np.asarray([o["cost"] for o in study["multistart"]])
    lines.append(f"multi-start: {len(costs)} starts, {n_fail} failed, "
                 f"cost spread {costs.max() - costs.min():.3e}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fixture", help="surface-export JSON with inputs")
    ap.add_argument("--ticker", default="SPY")
    ap.add_argument("--node", type=int, default=3)
    ap.add_argument("--order", type=int, default=12)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent
                                         / "Docs/notes/figures/tail_study.json"))
    args = ap.parse_args()

    if args.fixture:
        k, w, t, band = fixture_strip(args.fixture, args.ticker, args.node)
        label = f"{args.ticker} node {args.node} ({args.fixture})"
    else:
        k, w, t = ssvi_strip()
        band, label = None, "SSVI-shaped synthetic strip (note oracle)"

    study = run_study(k, w, t, band=band, n_order=args.order)
    study["label"] = label
    Path(args.out).write_text(json.dumps(study, indent=1))
    print(f"tail-stability study: {label}")
    print(summarize(study))
    print(f"\nwritten: {args.out}")


if __name__ == "__main__":
    main()
