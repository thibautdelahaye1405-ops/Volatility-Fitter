"""Figure: the model-free ceiling — Black calls along total-variance rays.

The demonstration evaluates B(k, beta k) far outside any tradeable range
(k up to 400), where the naive product e^k * Phi(d_-) underflows through
denormals and leaves visible spikes.  The panel therefore evaluates the
same Black formula in log space, exp(k + log Phi(d_-)), which is exact at
every argument drawn; the reference implementation never prices out here.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.special import log_ndtr, ndtr

import figstyle
from figstyle import PALETTE
from macros import STORE, num

BETAS = (1.2, 1.6, 2.0, 2.4, 2.8)
K_MAX = 400.0


def _ray_call(k: np.ndarray, beta: float) -> np.ndarray:
    """B(k, beta k) = Phi(d+) - exp(k + log Phi(d-)), stable at large k."""
    w = beta * k
    sq = np.sqrt(w)
    d_plus = -k / sq + 0.5 * sq
    d_minus = d_plus - sq
    return ndtr(d_plus) - np.exp(k + log_ndtr(d_minus))


def fig_vs_ceiling() -> str:
    k = np.geomspace(0.5, K_MAX, 600)

    fig, ax = plt.subplots(figsize=figstyle.ONE)
    colors = {1.2: PALETTE["model"], 1.6: PALETTE["alt"], 2.0: PALETTE["ink"],
              2.4: PALETTE["mcs"], 2.8: PALETTE["data"]}
    end = {}
    for beta in BETAS:
        c = _ray_call(k, beta)
        end[beta] = float(c[-1])
        style = {"lw": 1.6, "ls": "--"} if beta == 2.0 else {"lw": 1.3}
        ax.plot(k, c, color=colors[beta], label=rf"$\beta={beta}$", **style)
    for level, text in ((1.0, r"$\to 1$"), (0.5, r"$\to 1/2$"),
                        (0.0, r"$\to 0$")):
        ax.axhline(level, color=PALETTE["grid"], lw=0.7, zorder=0)
        ax.text(K_MAX * 1.06, level, text, va="center", fontsize=8.0,
                color=PALETTE["muted"])
    ax.set_xscale("log")
    ax.set_xlim(0.5, K_MAX * 1.35)
    ax.set_ylim(-0.04, 1.06)
    ax.set_xlabel("log-moneyness $k$ (log scale)")
    ax.set_ylabel(r"normalized call $B(k,\ \beta k)$")
    ax.legend(loc="center left", fontsize=7.5)
    ax.set_title("the far-out-of-the-money call along rays of slope $\\beta$",
                 loc="left", fontsize=9.0, pad=5.0)

    figstyle.save(fig, "fig_vs_ceiling")

    STORE.add("ceiling", "VsRayBelowLim", num(end[1.6], 3),
              f"B(k, 1.6 k) at k = {K_MAX:.0f} (heads to 0)")
    STORE.add("ceiling", "VsRayAtLim", num(end[2.0], 3),
              f"B(k, 2 k) at k = {K_MAX:.0f} (tends to 1/2; the second Black "
              "term dies only like 1/sqrt(k) on the boundary ray)")
    STORE.add("ceiling", "VsRayAboveLim", num(end[2.4], 3),
              f"B(k, 2.4 k) at k = {K_MAX:.0f} (heads to 1)")
    return (f"end values {end[1.6]:.3f} / {end[2.0]:.3f} / {end[2.4]:.3f}")
