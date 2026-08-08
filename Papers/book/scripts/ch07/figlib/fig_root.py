"""Figure 7.4: the inversion is well posed -- and where no root exists."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num

# American puts under a positive rate (appendix 7.A constants).
S, T, R, Q, SIGMA_TRUE = 100.0, 0.5, 0.04, 0.0, 0.25
K_OTM, K_ITM, K_DEEP = 80.0, 110.0, 160.0
SIG_GRID = np.linspace(0.02, 0.9, 120)


def _curve(K: float) -> np.ndarray:
    flags = np.zeros(SIG_GRID.size, dtype=bool)
    ks = np.full(SIG_GRID.size, K)
    return tree.crr_batch(flags, S, ks, T, SIG_GRID, R, Q, n=tree.N_SCALAR,
                          american=True)


def fig_deam_root() -> str:
    curves = {K: _curve(K) for K in (K_OTM, K_ITM, K_DEEP)}
    quotes = {
        K: tree.crr_price(False, S, K, T, SIGMA_TRUE, R, Q, n=tree.N_REF,
                          american=True)
        for K in (K_OTM, K_ITM)
    }
    # The deep strike's market quote sits AT the exercise floor.
    intr_deep = K_DEEP - S
    a_deep_true = tree.crr_price(False, S, K_DEEP, T, SIGMA_TRUE, R, Q,
                                 n=tree.N_REF, american=True)
    plateau_gap = a_deep_true - intr_deep   # should be ~0: it IS the floor

    fig, ax = plt.subplots(figsize=figstyle.ONE)
    colors = {K_OTM: PALETTE["model"], K_ITM: PALETTE["alt"],
              K_DEEP: PALETTE["data"]}
    labels = {K_OTM: f"$K={K_OTM:.0f}$ (out of the money)",
              K_ITM: f"$K={K_ITM:.0f}$ (in the money)",
              K_DEEP: f"$K={K_DEEP:.0f}$ (deep in the money)"}
    for K, curve in curves.items():
        ax.plot(100.0 * SIG_GRID, curve, color=colors[K], lw=1.3,
                label=labels[K])
    for K, quote in quotes.items():
        root = float(tree.deamericanize_batch(
            np.array([quote]), np.array([False]), np.array([K]),
            S, T, R, Q, n=tree.N_SCALAR)[0])
        ax.plot([100.0 * root], [quote], "o", ms=5.0, mfc="white",
                mec=PALETTE["ink"], mew=1.2, zorder=5)
    ax.axhline(intr_deep, color=PALETTE["data"], lw=0.9, ls="--", zorder=2)
    figstyle.callout(ax,
                     "quote at the intrinsic floor: the curve never\n"
                     "crosses it from above -- no root, no volatility",
                     (34.0, intr_deep + 0.6), (30.0, 44.0))
    figstyle.callout(ax, "unique root $\\sigma^*$",
                     (100.0 * SIGMA_TRUE + 1.0, quotes[K_ITM] + 0.5),
                     (12.0, 24.0))
    ax.set_xlabel("volatility $\\sigma$ (%)")
    ax.set_ylabel("American tree price $A(\\sigma)$ (dollars)")
    ax.legend(loc="upper left", fontsize=7.2)
    ax.set_title("three quotes meet the map "
                 "$\\sigma \\mapsto A(\\sigma)$ (puts, $r=4\\%$)",
                 loc="left", fontsize=9.0, pad=5.0)

    figstyle.save(fig, "fig_deam_root")

    STORE.add("root", "DeamRootQuoteOtm", num(quotes[K_OTM], 2),
              "converged put price at K=80 (dollars)")
    STORE.add("root", "DeamRootQuoteItm", num(quotes[K_ITM], 2),
              "converged put price at K=110 (dollars)")
    STORE.add("root", "DeamRootPlateauGapCents", num(100.0 * plateau_gap, 2),
              "time value of the K=160 put at the true vol (cents): "
              "the quote IS the intrinsic floor")
    STORE.add("root", "DeamRootDeepIntr", num(intr_deep, 0),
              "intrinsic value of the deep put (dollars)")
    return (f"quotes {quotes[K_OTM]:.2f}/{quotes[K_ITM]:.2f}, "
            f"plateau gap {plateau_gap * 100:.2f} cents")
