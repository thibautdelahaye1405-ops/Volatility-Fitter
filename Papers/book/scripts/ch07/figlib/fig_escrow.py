"""Figure 7.5: a dividend at a date is not a dividend smeared into carry."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num, sci

# One cash dividend (appendix 7.A): d1 = $6 with ex-date at 0.35 years, on
# a heavy payer against a 2% rate -- chosen so the smeared yield clearly
# exceeds the rate and its invented pre-ex-date premium is visible.
S, R, SIGMA = 100.0, 0.02, 0.25
DIV_T, DIV_D = 0.35, 6.0
T_A = 0.5                                   # panel (a) expiry
K_B = 85.0                                  # panel (b) fixed ITM call strike
KS_A = np.arange(60.0, 117.5, 2.5)
TS_B = np.arange(0.05, 1.0 + 1e-9, 0.025)


def _cash_premium(K: float, t: float) -> float:
    a = tree.crr_price_escrow(True, S, K, t, SIGMA, R, [(DIV_T, DIV_D)],
                              n=tree.N_SCALAR, american=True)
    e = tree.crr_price_escrow(True, S, K, t, SIGMA, R, [(DIV_T, DIV_D)],
                              n=tree.N_SCALAR, american=False)
    return a - e


def _yield_premium(K: float, t: float, q: float) -> float:
    a = tree.crr_price(True, S, K, t, SIGMA, R, q, n=tree.N_SCALAR,
                       american=True)
    e = tree.crr_price(True, S, K, t, SIGMA, R, q, n=tree.N_SCALAR,
                       american=False)
    return a - e


def fig_deam_escrow() -> str:
    # Forward of the cash schedule at t = 0.5, and the yield that matches it.
    pv0 = DIV_D * np.exp(-R * DIV_T)
    f_cash_a = (S - pv0) * np.exp(R * T_A)
    q_match = R - np.log(f_cash_a / S) / T_A
    # The flat smear: the schedule's one-year-equivalent yield, used for
    # every expiry in panel (b).
    f_cash_1y = (S - pv0) * np.exp(R * 1.0)
    q_flat = R - np.log(f_cash_1y / S) / 1.0

    prem_cash_a = np.array([_cash_premium(K, T_A) for K in KS_A])
    prem_yield_a = np.array([_yield_premium(K, T_A, q_match) for K in KS_A])

    prem_cash_b = np.array([_cash_premium(K_B, t) for t in TS_B])
    prem_flat_b = np.array([_yield_premium(K_B, t, q_flat) for t in TS_B])

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax_a.plot(KS_A, prem_cash_a, ".-", color=PALETTE["model"], lw=1.1,
              ms=3.2, label="cash dividend at its date")
    ax_a.plot(KS_A, prem_yield_a, ".-", color=PALETTE["alt"], lw=1.1,
              ms=3.2, label="same forward, smeared yield")
    ax_a.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_a.set_xlabel("strike $K$ (dollars)")
    ax_a.set_ylabel("premium $A-E$ (dollars)")
    ax_a.legend(loc="upper right", fontsize=7.2)
    figstyle.panel(ax_a, "a", f"calls at $t={T_A}$: one forward, "
                              "two premiums")

    ax_b.plot(TS_B, prem_cash_b, "-", color=PALETTE["model"], lw=1.3,
              label="cash dividend at its date")
    ax_b.plot(TS_B, prem_flat_b, "-", color=PALETTE["alt"], lw=1.3,
              label=f"flat yield $q_d={100.0 * q_flat:.1f}\\%$")
    ax_b.axvline(DIV_T, color=PALETTE["muted"], lw=0.9, ls="--", zorder=1)
    figstyle.callout(ax_b, "ex-date: nothing to capture\nbefore it",
                     (DIV_T - 0.02, 0.08),
                     (0.52, float(prem_cash_b.max()) * 0.40))
    ax_b.set_xlabel("expiry $t$ (years)")
    ax_b.set_ylabel("premium $A-E$ (dollars)")
    ax_b.legend(loc="upper left", fontsize=7.2)
    figstyle.panel(ax_b, "b", f"the $K={K_B:.0f}$ call across expiries")

    figstyle.save(fig, "fig_deam_escrow")

    # ratio where the comparison is meaningful (yield premium above 1 cent)
    mask = prem_yield_a > 0.01
    ratio = float(np.max(prem_cash_a[mask] / prem_yield_a[mask]))
    pre_ex = TS_B < DIV_T
    STORE.add("escrow", "DeamEscrowFwd", num(f_cash_a, 2),
              "forward of the cash schedule at t=0.5 (dollars)")
    STORE.add("escrow", "DeamEscrowQeqPct", num(100.0 * q_match, 2),
              "yield matching that forward at t=0.5 (%/yr)")
    STORE.add("escrow", "DeamEscrowFlatQPct", num(100.0 * q_flat, 2),
              "the schedule's one-year-equivalent flat yield (%/yr)")
    STORE.add("escrow", "DeamEscrowRatioMax", num(ratio, 1),
              "largest cash-to-yield premium ratio on panel (a), where the"
              " yield premium exceeds one cent")
    STORE.add("escrow", "DeamEscrowCashPreExMax",
              sci(float(np.max(np.abs(prem_cash_b[pre_ex]))), 1),
              "largest cash-model premium before the ex-date (dollars; "
              "Merton verbatim)")
    STORE.add("escrow", "DeamEscrowFlatPreExMax",
              num(float(np.max(prem_flat_b[pre_ex])), 2),
              "largest flat-yield premium before the ex-date (dollars; "
              "invented)")
    return (f"ratio {ratio:.1f}x, flat pre-ex "
            f"{np.max(prem_flat_b[pre_ex]):.2f}")
