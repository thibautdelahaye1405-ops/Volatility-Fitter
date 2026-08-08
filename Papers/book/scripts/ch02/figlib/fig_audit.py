"""Figures F12 + F14: the analytic Jacobian audit and strike convexity.

F12 fig_jacobian  -- one-pass analytic price sensitivities dC/dtheta on the
                     SPY deep-dive node vs independent central finite
                     differences: heat map + per-column relative error.
F14 fig_butterfly -- the same node's call curve is convex in STRIKE (chord
                     test) and its discrete butterflies reproduce the
                     continuous Breeden-Litzenberger density.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.jacobian import call_price_rows, slice_sensitivities
from volfit.models.lqd.quadrature import build_slice

import data
from figstyle import PALETTE, ROW2, callout, panel, save
from macros import STORE, num, sci


def fig_jacobian() -> str:
    """F12: envelope-cancellation sensitivities vs central differences."""
    node = data.node(*data.SPY_DEC)
    theta = node.params.to_vector()
    k = node.k

    slice_, d_az, d_dadz = slice_sensitivities(node.params, n_points=8001)
    _, analytic = call_price_rows(slice_, d_az, d_dadz, k)  # (n, P)

    central = np.empty_like(analytic)
    for j in range(theta.size):
        step = 2e-6 * max(1.0, abs(float(theta[j])))
        plus, minus = theta.copy(), theta.copy()
        plus[j] += step
        minus[j] -= step
        c_plus = build_slice(LQDParams.from_vector(plus)).call_price(k)
        c_minus = build_slice(LQDParams.from_vector(minus)).call_price(k)
        central[:, j] = (c_plus - c_minus) / (2.0 * step)

    denom = np.maximum(np.linalg.norm(central, axis=0), 1e-14)
    rel_err = np.linalg.norm(analytic - central, axis=0) / denom
    labels = ["$L$", "$R$"] + [rf"$a_{{{n}}}$" for n in range(2, node.order + 1)]

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    normalized = analytic / np.maximum(
        np.max(np.abs(analytic), axis=0), 1e-14)
    image = axes[0].imshow(normalized, origin="lower", aspect="auto",
                           cmap="RdBu_r", vmin=-1.0, vmax=1.0,
                           interpolation="nearest")
    axes[0].set_xticks(np.arange(theta.size), labels, fontsize=6.0)
    rows = np.linspace(0, k.size - 1, 6).astype(int)
    axes[0].set_yticks(rows, [f"{k[i]:+.2f}" for i in rows], fontsize=7.0)
    axes[0].grid(False)
    axes[0].set_xlabel("parameter")
    axes[0].set_ylabel(r"quoted log-moneyness $k$")
    bar = fig.colorbar(image, ax=axes[0], fraction=0.05, pad=0.03)
    bar.set_label("column-normalized $\\partial C/\\partial\\theta$",
                  fontsize=7.5)
    bar.ax.tick_params(labelsize=7.0)
    panel(axes[0], "a", "where each parameter moves prices")

    axes[1].bar(np.arange(theta.size), rel_err, color=PALETTE["model"],
                width=0.7)
    axes[1].axhline(1e-6, color=PALETTE["ink"], ls=":", lw=0.9)
    axes[1].text(0.3, 1.35e-6, "one part per million", fontsize=7.0,
                 color=PALETTE["muted"])
    axes[1].set_yscale("log")
    axes[1].set_xticks(np.arange(theta.size), labels, fontsize=6.0)
    axes[1].set_xlabel("parameter")
    axes[1].set_ylabel("column relative error vs central FD")
    panel(axes[1], "b", "an independent derivative check")

    save(fig, "fig_jacobian")

    STORE.add("jacobian", "JacobianMaxRelErr", sci(float(rel_err.max())),
              "worst column relative error, analytic vs central FD")
    STORE.add("jacobian", "JacobianParams", str(theta.size),
              "parameter count P on the test node")
    STORE.add("jacobian", "JacobianStrikes", str(k.size),
              "quoted strikes on the test node")
    return f"jacobian check: max column rel err {rel_err.max():.1e}"


def fig_butterfly() -> str:
    """F14: strike convexity and discrete butterflies on SPY 2026-12-18."""
    node = data.node(*data.SPY_DEC)
    slice_ = node.slice
    y = np.linspace(0.70, 1.32, 400)  # strike / forward
    calls = np.asarray(slice_.call_price(np.log(y)))

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    axes[0].plot(y, calls, color=PALETTE["model"], label="model call $c(K/F)$")
    axes[0].plot(y, np.maximum(1.0 - y, 0.0), color=PALETTE["muted"], ls="--",
                 lw=1.0, label="intrinsic $(1 - K/F)^+$")
    y1, y2 = 0.88, 1.12
    c1, c2 = (float(slice_.call_price(np.log(v))) for v in (y1, y2))
    chord_y = np.linspace(y1, y2, 120)
    chord = c1 + (c2 - c1) * (chord_y - y1) / (y2 - y1)
    axes[0].plot(chord_y, chord, color=PALETTE["data"], ls=":", lw=1.2,
                 label="secant chord")
    axes[0].fill_between(chord_y, slice_.call_price(np.log(chord_y)), chord,
                         color=PALETTE["data"], alpha=0.12, lw=0.0)
    callout(axes[0], "convex: the curve stays below",
            xy=(1.0, float(np.interp(1.0, chord_y, chord))),
            xytext=(1.02, 0.11))
    axes[0].set_xlabel(r"strike / forward $K/F$")
    axes[0].set_ylabel("normalized call value")
    axes[0].legend(loc="upper right", fontsize=7.0)
    panel(axes[0], "a", "convexity in strike")

    width = 0.01
    fly = (np.asarray(slice_.call_price(np.log(y - width)))
           - 2.0 * calls
           + np.asarray(slice_.call_price(np.log(y + width)))) / width**2
    x_grid, f_x = slice_.density()
    f_strike = np.interp(np.log(y), x_grid, f_x) / y
    axes[1].plot(y, f_strike, color=PALETTE["model"],
                 label="continuous density")
    axes[1].scatter(y[::14], fly[::14], s=10, color=PALETTE["data"], zorder=4,
                    label=f"butterflies, width {width:.2f}")
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.7)
    axes[1].set_xlabel(r"central strike / forward $K/F$")
    axes[1].set_ylabel("density in strike")
    axes[1].legend(loc="upper right", fontsize=7.0)
    panel(axes[1], "b", "butterflies recover the density")

    save(fig, "fig_butterfly")

    rel = np.abs(fly - f_strike) / np.maximum(f_strike, 1e-12)
    STORE.add("butterfly", "ButterflyMin", sci(float(fly.min())),
              "smallest discrete butterfly value on the test strip")
    STORE.add("butterfly", "ButterflyWidth", num(width, 2),
              "butterfly half-structure width in strike/forward units")
    STORE.add("butterfly", "ButterflyDensityRelErrPct",
              num(100.0 * float(rel.max()), 2),
              "worst relative gap butterflies vs continuous density, %")
    return (f"butterfly: min {fly.min():.2e}, density gap "
            f"{100 * rel.max():.2f}%")
