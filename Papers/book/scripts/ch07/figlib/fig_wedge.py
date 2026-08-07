"""Figure 7.1: the naive inversion books the premium as volatility."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num, sci

# The running synthetic board (appendix 7.A): American calls on a
# 6%-dividend-yield name against a 2% rate, true volatility 25%.
S, R, Q, SIGMA, T = 100.0, 0.02, 0.06, 0.25, 0.5
STRIKES = np.arange(60.0, 140.0 + 1.0, 2.5)
K_WEX = 90.0


def fig_deam_wedge() -> str:
    F = S * np.exp((R - Q) * T)
    D = np.exp(-R * T)
    n_k = STRIKES.size
    is_call = np.ones(n_k, dtype=bool)

    # "Quotes": converged-tree American prices at the true volatility.
    a_ref = np.array([tree.crr_price(True, S, K, T, SIGMA, R, Q,
                                     n=tree.N_REF, american=True)
                      for K in STRIKES])
    e_ref = np.array([tree.crr_price(True, S, K, T, SIGMA, R, Q,
                                     n=tree.N_REF, american=False)
                      for K in STRIKES])
    premium = a_ref - e_ref

    # Naive: European Black inversion of the American price.
    sig_naive = tree.implied_vol_black(a_ref, is_call, STRIKES, F, D, T)
    # De-Americanized: the root through the American tree at scalar depth.
    sig_star = tree.deamericanize_batch(a_ref, is_call, STRIKES, S, T, R, Q,
                                        n=tree.N_SCALAR)

    bias_bp = 1e4 * (sig_naive - SIGMA)
    root_err_bp = 1e4 * (sig_star - SIGMA)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax_a.axhline(100.0 * SIGMA, color=PALETTE["ink"], lw=0.9, ls=":",
                 zorder=2, label="true volatility 25%")
    ax_a.plot(STRIKES, 100.0 * sig_naive, ".-", color=PALETTE["data"],
              lw=1.1, ms=3.4, zorder=4, label="naive European inversion")
    ax_a.plot(STRIKES, 100.0 * sig_star, ".-", color=PALETTE["model"],
              lw=1.1, ms=3.4, zorder=5, label="de-Americanized $\\sigma^*$")
    i_max = int(np.nanargmax(bias_bp))
    figstyle.callout(ax_a, f"{bias_bp[i_max]:.0f} vol bp of phantom\n"
                           "volatility, deepest in the money",
                     (STRIKES[i_max] + 1.0, 100.0 * sig_naive[i_max] - 1.0),
                     (STRIKES[i_max] + 8.0, 100.0 * sig_naive[i_max] - 12.0))
    ax_a.set_xlabel("strike $K$ (dollars)")
    ax_a.set_ylabel("implied volatility (%)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the same quotes, read two ways")

    ax_b.plot(STRIKES, premium, ".-", color=PALETTE["model"], lw=1.1,
              ms=3.4, zorder=4)
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_b.axvline(F, color=PALETTE["muted"], lw=0.9, ls="--", zorder=2)
    figstyle.callout(ax_b, "forward $F$", (F, float(premium.max()) * 0.55),
                     (F + 9.0, float(premium.max()) * 0.62))
    ax_b.set_xlabel("strike $K$ (dollars)")
    ax_b.set_ylabel("premium $A-E$ (dollars)")
    figstyle.panel(ax_b, "b", "the premium itself, in dollars")

    figstyle.save(fig, "fig_deam_wedge")

    # ---- the worked single strike (scalar depth, Section 7.4's numbers)
    a_wex = tree.crr_price(True, S, K_WEX, T, SIGMA, R, Q,
                           n=tree.N_SCALAR, american=True)
    e_wex = tree.crr_price(True, S, K_WEX, T, SIGMA, R, Q,
                           n=tree.N_SCALAR, american=False)
    sig_naive_wex = float(tree.implied_vol_black(
        np.array([a_wex]), np.array([True]), np.array([K_WEX]), F, D, T)[0])
    sig_star_wex = float(tree.deamericanize_batch(
        np.array([a_wex]), np.array([True]), np.array([K_WEX]), S, T, R, Q,
        n=tree.N_SCALAR)[0])

    STORE.add("wedge", "DeamWedgeMaxBiasBp", num(float(np.nanmax(bias_bp)), 0),
              "largest naive-inversion bias across the board (vol bp)")
    STORE.add("wedge", "DeamWedgeMaxPremiumDollars",
              num(float(premium.max()), 2),
              "largest early-exercise premium on the board (dollars)")
    STORE.add("wedge", "DeamWedgeAtmBiasBp",
              num(float(bias_bp[np.argmin(np.abs(STRIKES - F))]), 0),
              "naive bias at the strike nearest the forward (vol bp)")
    STORE.add("wedge", "DeamWedgeRootRmsBp",
              num(float(np.sqrt(np.nanmean(root_err_bp**2))), 1),
              "rms error of the recovered sigma* across the board (vol bp;"
              " scalar-depth inversion of converged-tree quotes)")
    STORE.add("wedge", "DeamWedgeForward", num(F, 2),
              "forward of the running synthetic board (dollars)")
    STORE.add("wedge", "DeamWexAmDollars", num(a_wex, 4),
              "worked strike: American tree price at the true vol (dollars)")
    STORE.add("wedge", "DeamWexEuDollars", num(e_wex, 4),
              "worked strike: European leg at the same vol (dollars)")
    STORE.add("wedge", "DeamWexPremiumDollars", num(a_wex - e_wex, 4),
              "worked strike: the premium A - E (dollars)")
    STORE.add("wedge", "DeamWexPremiumPct", num(100.0 * (a_wex - e_wex) / a_wex, 1),
              "worked strike: premium as a share of the option's value (%)")
    STORE.add("wedge", "DeamWexNaivePct", num(100.0 * sig_naive_wex, 2),
              "worked strike: naive European implied vol (%)")
    STORE.add("wedge", "DeamWexBiasBp",
              num(1e4 * (sig_naive_wex - SIGMA), 0),
              "worked strike: naive bias over the true 25% (vol bp)")
    STORE.add("wedge", "DeamWexRootPct", num(100.0 * sig_star_wex, 2),
              "worked strike: the recovered de-Americanized root (%)")
    return (f"max bias {np.nanmax(bias_bp):.0f} bp, "
            f"wex A={a_wex:.4f} E={e_wex:.4f}")
