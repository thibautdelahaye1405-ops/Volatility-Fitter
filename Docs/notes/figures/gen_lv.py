"""Figures and tables for Note 04 (Piecewise-affine Local Volatility).

Three sources of truth:
  (1) a synthetic round trip through the REAL affine calibrator: a known skewed
      local-variance surface is priced through the forward Dupire PDE, quotes
      are generated, and the surface is recovered from a flat seed;
  (2) the production benchmark fit on the static Bloomberg fixture (SPY, NVDA);
  (3) the production grid builder (_delta_strike_nodes /
      _augment_per_expiry_coverage) for the short-dated rescue diagram.

Outputs:
  fig_lv_surface.pdf  recovered local-volatility surface (heatmap)
  fig_lv_fit.pdf      per-expiry implied-vol fit (target vs recovered)
  fig_lv_rms.pdf      real Bloomberg per-expiry RMS (SPY, NVDA)
  fig_lv_rescue.pdf   per-expiry coverage floor: before/after vertices
  lv_tables.tex       \\input-able macros
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, save, setup  # noqa: E402

from volfit.core.black import implied_total_variance  # noqa: E402
from volfit.models.localvol.affine import (  # noqa: E402
    AffineVarianceSurface,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_calib import OptionQuote, calibrate_affine  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()
COLORS = [PALETTE["teal"], PALETTE["blue"], PALETTE["amber"], PALETTE["rust"]]
EXPIRIES = np.array([0.15, 0.30, 0.60, 1.00])


# ------------------------------------------------------------- round trip
def truth_surface():
    t_nodes = np.array([0.0, 0.5, 1.0])
    x_nodes = np.array([0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.7, 2.0])

    def loc_var(t, x):
        base = 0.035 + 0.05 * np.exp(-2.2 * (x - 0.7))   # skew: higher var low strike
        return float(np.clip(base, 0.0064, 0.16) * (1.0 + 0.08 * t))

    theta = np.array([[loc_var(t, x) for x in x_nodes] for t in t_nodes])
    return AffineVarianceSurface(t_nodes, x_nodes, theta)


def round_trip():
    """Synthetic quote-repricing round trip.

    Runs the LOW-LEVEL calibrator (TRF, banded march, custom dense grids) — an
    algorithm check, not the product path or its timing. Besides the quote
    repricing error it now measures the LOCAL-VARIANCE surface discrepancy on a
    dense grid over the quote-covered region: sparse vanillas do not uniquely
    identify the nodal grid, so low quote error is NOT surface recovery — the
    regularizers select one representative, and the note reports both numbers.
    """
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

    # Local-VOL surface discrepancy (vol points) on the quote-covered region.
    tt = np.linspace(float(EXPIRIES[0]), float(EXPIRIES[-1]), 41)
    xx = np.linspace(float(strikes[0]), float(strikes[-1]), 51)
    dvols = []
    for t in tt:
        truth_v = truth.variance(xx, float(t))
        rec_v = cal.surface.variance(xx, float(t))
        dvols.append(100.0 * (np.sqrt(np.maximum(rec_v, 0.0))
                              - np.sqrt(np.maximum(truth_v, 0.0))))
    dvol = np.concatenate(dvols)
    surf_err = dict(rms=float(np.sqrt(np.mean(dvol**2))), max=float(np.max(np.abs(dvol))))
    return cal, target, recovered, wall, surf_err


def fig_surface(cal):
    surf = cal.surface
    vol = np.sqrt(np.maximum(surf.theta, 1e-8)) * 100
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    im = ax.pcolormesh(surf.x_nodes, surf.t_nodes, vol, shading="gouraud",
                       cmap="viridis")
    ax.scatter(*np.meshgrid(surf.x_nodes, surf.t_nodes), s=7, color="white",
               alpha=0.55)
    ax.set_xlabel(r"normalized strike $x=K/F$")
    ax.set_ylabel(r"maturity $t$ (years)")
    cb = fig.colorbar(im, ax=ax)
    cb.set_label(r"local volatility $\sqrt{\nu}$ (%)")
    ax.set_title("Recovered piecewise-affine local-vol surface")
    ax.grid(False)
    save(fig, OUT / "fig_lv_surface.pdf")


def fig_fit(target, recovered):
    fig, ax = plt.subplots(figsize=(6.9, 4.0))
    for (T, (xs, iv)), c in zip(target.items(), COLORS):
        ax.plot(np.log(xs), 100 * iv, color=c, lw=2.0, label=fr"$T={T:.2f}$")
        xr, ivr = recovered[T]
        ax.plot(np.log(xr), 100 * ivr, color=c, ls="--", lw=1.2)
    ax.set_xlabel(r"log-moneyness $k=\log(K/F)$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title("Truth (solid) vs recovered (dashed)")
    ax.legend(ncol=2, loc="lower left")
    save(fig, OUT / "fig_lv_fit.pdf")


# ------------------------------------------------------------- benchmark
def benchmark():
    """Real production fit over the Bloomberg fixture (the PRODUCT path:
    calibrate_affine_surface with the shipped request defaults). Reports the
    in-operator surface RMS AND the converged-operator reprice (dt/4, dx/2) —
    the honest quality metric; in-operator residuals are blind to
    time-discretization error the optimizer compensates."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        from lv_benchmark import build_state
        from volfit.api.affine_fit import calibrate_affine_surface
        from volfit.api.schemas_affine import AffineFitRequest

        state = build_state()
        out = {}
        for ticker in ("SPY", "NVDA"):
            t0 = time.perf_counter()
            resp = calibrate_affine_surface(state, ticker, AffineFitRequest())
            out[ticker] = dict(
                surface_rms_bp=resp.surfaceRmsError * 1e4,
                converged_rms_bp=float(resp.rmsConvergedBp),
                converged_max_bp=float(resp.maxConvergedBp),
                wall_s=time.perf_counter() - t0,
                smiles=[
                    (s.expiry, s.rmsError * 1e4, float(s.rmsConvergedBp))
                    for s in resp.smiles
                ],
            )
        return out
    except Exception as exc:  # pragma: no cover
        # LOUD failure: the note must never silently retain stale numbers.
        import traceback

        print("!" * 72)
        print("BENCHMARK FAILED — Bloomberg-fixture macros will read UNAVAILABLE")
        print("   ", type(exc).__name__, exc)
        traceback.print_exc()
        print("!" * 72)
        return None


def fig_rms(bench):
    """Grouped per-expiry bars, in-operator AND converged reprice, per name.
    Expiry axes are per-name (SPY and NVDA ladders differ), so the two names
    get separate panels with full YYYY-MM-DD context in the panel title year."""
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6), sharey=True)
    width = 0.38
    for ax, (ticker, c) in zip(axes, [("SPY", PALETTE["teal"]),
                                      ("NVDA", PALETTE["rust"])]):
        if ticker not in bench:
            ax.set_title(f"{ticker}: unavailable")
            ax.set_axis_off()
            continue
        smiles = bench[ticker]["smiles"]
        labels = [e[5:] for e, _, _ in smiles]  # MM-DD; year in the title
        year = smiles[0][0][:4]
        in_op = [r for _, r, _ in smiles]
        conv = [r for _, _, r in smiles]
        xpos = np.arange(len(in_op))
        ax.bar(xpos - width / 2, in_op, width=width, color=c, label="in-operator")
        ax.bar(xpos + width / 2, conv, width=width, color=PALETTE["muted"],
               label="converged reprice")
        ax.set_xticks(xpos)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_xlabel(f"expiry ({year})")
        ax.set_title(ticker)
        ax.legend(fontsize=8)
    axes[0].set_ylabel("per-expiry RMS (vol bps)")
    fig.suptitle("Production local-vol fit, Bloomberg fixture", fontsize=11)
    fig.tight_layout()
    save(fig, OUT / "fig_lv_rms.pdf")


# ------------------------------------------------------------- rescue diagram
def rescue():
    """Run the PRODUCTION grid builder on a 6-day + 6-month universe."""
    from volfit.api.affine_fit import (
        _augment_per_expiry_coverage,
        _axis_scale,
        _delta_strike_nodes,
    )

    sigma = 0.20
    tau_wk, tau_6m = 6.0 / 365.0, 0.5
    # Traded ranges: +-2.5 ATM std for the weekly, a normal index range for 6M.
    k_wk = np.linspace(-2.5, 2.5, 21) * sigma * np.sqrt(tau_wk)
    k_6m = np.linspace(-0.35, 0.25, 25)
    rows = [
        ("wk", tau_wk, k_wk, np.full(k_wk.size, sigma**2 * tau_wk), None, None),
        ("6m", tau_6m, k_6m, np.full(k_6m.size, sigma**2 * tau_6m), None, None),
    ]
    sigma_star, t_star = _axis_scale(rows)
    k_lo, k_hi = float(k_6m[0]), float(k_6m[-1])
    base = _delta_strike_nodes(sigma_star, t_star, k_lo, k_hi, 12)
    aug = _augment_per_expiry_coverage(base, rows, 8)
    added = np.setdiff1d(np.round(aug, 12), np.round(base, 12))

    def in_range(nodes, k):
        lk = np.log(nodes)
        return int(np.count_nonzero((lk >= k.min()) & (lk <= k.max())))

    counts = {
        "wk": (in_range(base, k_wk), in_range(aug, k_wk)),
        "6m": (in_range(base, k_6m), in_range(aug, k_6m)),
    }

    lanes = [("6-day weekly", k_wk, 1.0), ("6-month expiry", k_6m, 0.0)]
    fig, axes = plt.subplots(1, 2, figsize=WIDE,
                             gridspec_kw={"width_ratios": [1.35, 1.0]})
    for panel, (ax, xlim) in enumerate(
        zip(axes, [(k_lo - 0.02, k_hi + 0.02),
                   (k_wk.min() * 1.7, k_wk.max() * 1.7)])
    ):
        for name, k, y in lanes:
            ax.axhspan(y - 0.16, y + 0.16, xmin=0, xmax=1, color="none")
            ax.fill_betweenx([y - 0.16, y + 0.16], k.min(), k.max(),
                             color=PALETTE["teal"], alpha=0.13)
            ax.plot(np.log(base), np.full(base.size, y), "o", ms=6,
                    color=PALETTE["muted"], label="delta axis" if y > 0 else None)
            if added.size:
                ax.plot(np.log(added), np.full(added.size, y), "D", ms=6,
                        color=PALETTE["rust"],
                        label="added by coverage floor" if y > 0 else None)
            ax.text(xlim[0] + 0.01 * (xlim[1] - xlim[0]), y + 0.26, name,
                    fontsize=10, color=PALETTE["ink"])
        ax.axvline(0.0, color=PALETTE["ink"], lw=0.7, ls=":")
        ax.set_yticks([])
        ax.set_ylim(-0.55, 1.75)
        ax.set_xlim(*xlim)
        ax.set_xlabel(r"log-moneyness $k$")
    axes[0].set_title("The delta axis serves the longest expiry")
    axes[1].set_title("Zoom: the weekly's traded range")
    axes[0].legend(loc="upper right", fontsize=9)
    axes[1].text(
        k_wk.max() * 1.55, 1.38,
        f"in-range: {counts['wk'][0]} $\\to$ {counts['wk'][1]}",
        ha="right", fontsize=10, color=PALETTE["ink"],
    )
    axes[1].text(
        k_wk.max() * 1.55, 0.28,
        "already $\\geq$ 8:\nno splits on its account",
        ha="right", fontsize=9, color=PALETTE["muted"],
    )
    fig.tight_layout(w_pad=2.0)
    save(fig, OUT / "fig_lv_rescue.pdf")
    print("rescue: weekly %d->%d in-range, 6m %d->%d, axis %d->%d nodes"
          % (*counts["wk"], *counts["6m"], base.size, aug.size))
    return counts


def _provenance():
    """Commit/config/runtime provenance stored with every regeneration."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[3],
        ).stdout.strip()
    except Exception:
        commit = "unknown"
    try:
        import numba
        numba_v = numba.__version__
    except Exception:
        numba_v = "absent"
    import scipy
    return dict(
        commit=commit,
        generated=time.strftime("%Y-%m-%d %H:%M"),
        python=platform.python_version(),
        numpy=np.__version__,
        scipy=scipy.__version__,
        numba=numba_v,
        machine=platform.machine(),
        round_trip_path="low-level calibrate_affine (TRF, banded march, custom grids)",
        benchmark_path="calibrate_affine_surface, AffineFitRequest() product defaults",
    )


# ------------------------------------------------------------- main
def main():
    print("Synthetic round trip ...")
    cal, target, recovered, wall, surf_err = round_trip()
    fig_surface(cal)
    fig_fit(target, recovered)
    max_err = max(
        np.max(np.abs(100 * (recovered[T][1] - target[T][1]))) * 100 for T in target
    )

    print("Rescue diagram (production grid builder) ...")
    rescue()

    print("Production Bloomberg benchmark ...")
    bench = benchmark()
    prov = _provenance()
    L = ["% Auto-generated by gen_lv.py — do not edit."]
    L.append(r"\newcommand{\lvrtmaxerr}{%.1f}" % max_err)
    L.append(r"\newcommand{\lvrtwall}{%.2f}" % wall)
    L.append(r"\newcommand{\lvrtnevals}{%d}" % cal.n_evals)
    L.append(r"\newcommand{\lvrtvtx}{%d}" % cal.surface.theta.size)
    L.append(r"\newcommand{\lvrtsurfrms}{%.2f}" % surf_err["rms"])
    L.append(r"\newcommand{\lvrtsurfmax}{%.2f}" % surf_err["max"])
    L.append(r"\newcommand{\lvgencommit}{%s}" % prov["commit"])
    L.append(r"\newcommand{\lvgendate}{%s}" % prov["generated"][:10])
    if bench:
        L.append(r"\newcommand{\lvspyrms}{%.1f}" % bench["SPY"]["surface_rms_bp"])
        L.append(r"\newcommand{\lvnvdarms}{%.1f}" % bench["NVDA"]["surface_rms_bp"])
        L.append(r"\newcommand{\lvspyconv}{%.1f}" % bench["SPY"]["converged_rms_bp"])
        L.append(r"\newcommand{\lvnvdaconv}{%.1f}" % bench["NVDA"]["converged_rms_bp"])
        fig_rms(bench)
        rows = [r"\begin{tabular}{lrrr}", r"\toprule",
                r"Name & in-op RMS (bp) & converged RMS (bp) & worst expiry (bp)\\",
                r"\midrule"]
        for ticker in ("SPY", "NVDA"):
            b = bench[ticker]
            worst = max(r for _, r, _ in b["smiles"])
            rows.append(
                rf"{ticker} & {b['surface_rms_bp']:.1f} & "
                rf"{b['converged_rms_bp']:.1f} & {worst:.1f}\\"
            )
        rows += [r"\bottomrule", r"\end{tabular}"]
        L.append(r"\newcommand{\lvbenchtable}{%s}" % " ".join(rows))
    else:
        # NEVER retain stale numbers: unavailable reads as unavailable.
        L.append(r"\newcommand{\lvspyrms}{(unavailable)}")
        L.append(r"\newcommand{\lvnvdarms}{(unavailable)}")
        L.append(r"\newcommand{\lvspyconv}{(unavailable)}")
        L.append(r"\newcommand{\lvnvdaconv}{(unavailable)}")
        L.append(r"\newcommand{\lvbenchtable}{(benchmark unavailable)}")
    (OUT / "lv_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "lv_numbers.json").write_text(
        json.dumps({"round_trip_max_err_bp": max_err, "wall_s": wall,
                    "n_evals": cal.n_evals,
                    "surface_recovery_volpts": surf_err,
                    "benchmark": bench, "provenance": prov}, indent=2),
        encoding="utf-8")
    print("round-trip max err %.1f bp (surface diff rms %.2f / max %.2f vol pts), "
          "wall %.2fs, nevals %d"
          % (max_err, surf_err["rms"], surf_err["max"], wall, cal.n_evals))


if __name__ == "__main__":
    main()
