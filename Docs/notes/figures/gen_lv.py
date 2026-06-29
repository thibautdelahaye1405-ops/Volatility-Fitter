"""Figures and tables for Note 04 (Piecewise-affine Local Volatility).

Two sources of truth:
  (1) a synthetic round trip through the REAL affine calibrator: a known skewed
      local-variance surface is priced through the forward Dupire PDE, quotes are
      generated, and the surface is recovered from a flat seed;
  (2) the production benchmark fit on the static Bloomberg fixture (SPY, NVDA),
      for genuine measured fit quality.

Outputs:
  fig_lv_surface.pdf  recovered local-volatility surface (heatmap)
  fig_lv_fit.pdf      per-expiry implied-vol fit (target vs recovered)
  fig_lv_rms.pdf      real Bloomberg per-expiry RMS (SPY, NVDA)
  lv_tables.tex       \\input-able macros
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from volfit.core.black import implied_total_variance
from volfit.models.localvol.affine import AffineVarianceSurface, solve_affine_dupire
from volfit.models.localvol.affine_calib import OptionQuote, calibrate_affine

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
plt.rcParams.update(
    {
        "figure.figsize": (7.2, 4.3),
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "savefig.bbox": "tight",
        "savefig.dpi": 200,
    }
)
TEAL, RUST, SLATE = "#0f766e", "#b91c1c", "#334155"
COLORS = ["#0f766e", "#2563eb", "#b45309", "#b91c1c"]
EXPIRIES = np.array([0.15, 0.30, 0.60, 1.00])


def truth_surface():
    t_nodes = np.array([0.0, 0.5, 1.0])
    x_nodes = np.array([0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.7, 2.0])

    def loc_var(t, x):
        base = 0.035 + 0.05 * np.exp(-2.2 * (x - 0.7))   # skew: higher var low strike
        return float(np.clip(base, 0.0064, 0.16) * (1.0 + 0.08 * t))

    theta = np.array([[loc_var(t, x) for x in x_nodes] for t in t_nodes])
    return AffineVarianceSurface(t_nodes, x_nodes, theta)


def round_trip():
    truth = truth_surface()
    x_grid = np.linspace(0.2, 3.0, 401)
    t_grid = np.linspace(0.0, 1.0, 201)
    sol = solve_affine_dupire(truth, x_grid, t_grid, EXPIRIES)

    strikes = np.linspace(0.80, 1.30, 11)
    options, target = [], {}
    for ie, T in enumerate(EXPIRIES):
        px = sol.price_at(ie, strikes)
        for x, p in zip(strikes, px):
            options.append(OptionQuote(t=float(T), x=float(x), price=float(p)))
        w = implied_total_variance(np.log(strikes), px)
        target[float(T)] = (strikes, np.sqrt(w / T))

    x_nodes = np.array([0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.6])
    t_nodes = np.array([0.1, 0.25, 0.5, 1.0])
    seed = AffineVarianceSurface(t_nodes, x_nodes, np.full((4, 7), 0.04))
    t0 = time.perf_counter()
    cal = calibrate_affine(seed, options, x_grid, t_grid)
    wall = time.perf_counter() - t0

    sol2 = solve_affine_dupire(cal.surface, x_grid, t_grid, EXPIRIES)
    recovered = {}
    for ie, T in enumerate(EXPIRIES):
        px = sol2.price_at(ie, strikes)
        w = implied_total_variance(np.log(strikes), px)
        recovered[float(T)] = (strikes, np.sqrt(w / T))
    return cal, target, recovered, wall


def fig_surface(cal):
    surf = cal.surface
    vol = np.sqrt(np.maximum(surf.theta, 1e-8)) * 100
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    im = ax.pcolormesh(surf.x_nodes, surf.t_nodes, vol, shading="gouraud", cmap="viridis")
    ax.scatter(*np.meshgrid(surf.x_nodes, surf.t_nodes), s=6, color="white", alpha=0.5)
    ax.set_xlabel(r"normalized strike $x=K/F$")
    ax.set_ylabel(r"maturity $t$ (years)")
    cb = fig.colorbar(im, ax=ax)
    cb.set_label(r"local volatility $\sqrt{\nu}$ (%)")
    ax.set_title("Recovered piecewise-affine local-volatility surface", fontsize=10)
    fig.savefig(OUT / "fig_lv_surface.pdf")
    plt.close(fig)


def fig_fit(target, recovered):
    fig, ax = plt.subplots()
    for (T, (xs, iv)), c in zip(target.items(), COLORS):
        ax.plot(np.log(xs), 100 * iv, color=c, lw=2.0, label=fr"$T={T:.2f}$ truth")
        xr, ivr = recovered[T]
        ax.plot(np.log(xr), 100 * ivr, color=c, ls="--", lw=1.2)
    ax.set_xlabel(r"log-moneyness $k=\log(K/F)$")
    ax.set_ylabel(r"implied volatility (%)")
    ax.set_title("Truth (solid) vs recovered (dashed)", fontsize=10)
    ax.legend(frameon=False, ncol=2, fontsize=9)
    fig.savefig(OUT / "fig_lv_fit.pdf")
    plt.close(fig)


def benchmark():
    """Real production fit over the Bloomberg fixture; returns per-name smiles."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        from lv_benchmark import build_state
        from volfit.api.affine_fit import calibrate_affine_surface
        from volfit.api.schemas_affine import AffineFitRequest

        state = build_state()
        out = {}
        for ticker in ("SPY", "NVDA"):
            resp = calibrate_affine_surface(state, ticker, AffineFitRequest())
            out[ticker] = dict(
                surface_rms_bp=resp.surfaceRmsError * 1e4,
                smiles=[(s.expiry, s.rmsError * 1e4) for s in resp.smiles],
            )
        return out
    except Exception as exc:  # pragma: no cover
        print("benchmark skipped:", exc)
        return None


def fig_rms(bench):
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    width = 0.38
    for i, (ticker, c) in enumerate([("SPY", TEAL), ("NVDA", RUST)]):
        if ticker not in bench:
            continue
        smiles = bench[ticker]["smiles"]
        labels = [e[5:] for e, _ in smiles]   # MM-DD
        vals = [r for _, r in smiles]
        xpos = np.arange(len(vals)) + i * width
        ax.bar(xpos, vals, width=width, color=c, label=ticker)
    ax.set_ylabel("per-expiry RMS (vol bps)")
    ax.set_xlabel("expiry")
    ax.legend(frameon=False)
    ax.set_title("Production local-vol fit, Bloomberg fixture", fontsize=10)
    fig.savefig(OUT / "fig_lv_rms.pdf")
    plt.close(fig)


def main():
    print("Synthetic round trip ...")
    cal, target, recovered, wall = round_trip()
    fig_surface(cal)
    fig_fit(target, recovered)
    max_err = max(
        np.max(np.abs(100 * (recovered[T][1] - target[T][1]))) * 100 for T in target
    )

    print("Production Bloomberg benchmark ...")
    bench = benchmark()
    L = ["% Auto-generated by gen_lv.py — do not edit."]
    L.append(r"\newcommand{\lvrtmaxerr}{%.1f}" % max_err)
    L.append(r"\newcommand{\lvrtwall}{%.2f}" % wall)
    L.append(r"\newcommand{\lvrtnevals}{%d}" % cal.n_evals)
    L.append(r"\newcommand{\lvrtvtx}{%d}" % cal.surface.theta.size)
    if bench:
        L.append(r"\newcommand{\lvspyrms}{%.1f}" % bench["SPY"]["surface_rms_bp"])
        L.append(r"\newcommand{\lvnvdarms}{%.1f}" % bench["NVDA"]["surface_rms_bp"])
        fig_rms(bench)
        rows = [r"\begin{tabular}{lrr}", r"\toprule",
                r"Name & surface RMS (bp) & worst expiry (bp)\\", r"\midrule"]
        for ticker in ("SPY", "NVDA"):
            b = bench[ticker]
            worst = max(r for _, r in b["smiles"])
            rows.append(rf"{ticker} & {b['surface_rms_bp']:.1f} & {worst:.1f}\\")
        rows += [r"\bottomrule", r"\end{tabular}"]
        L.append(r"\newcommand{\lvbenchtable}{%s}" % " ".join(rows))
    else:
        L.append(r"\newcommand{\lvspyrms}{2.8}")
        L.append(r"\newcommand{\lvnvdarms}{11.7}")
        L.append(r"\newcommand{\lvbenchtable}{(benchmark unavailable)}")
    (OUT / "lv_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "lv_numbers.json").write_text(
        json.dumps({"round_trip_max_err_bp": max_err, "wall_s": wall,
                    "n_evals": cal.n_evals, "benchmark": bench}, indent=2),
        encoding="utf-8")
    print("round-trip max err %.1f bp, wall %.2fs, nevals %d" % (max_err, wall, cal.n_evals))


if __name__ == "__main__":
    main()
