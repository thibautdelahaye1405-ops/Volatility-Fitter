"""Figure 10.3 -- the information price of a basket.

Panel (a): a fixed budget of quotes spreads over a widening band; the ATM,
risk-reversal and butterfly baskets cross the requirement only when coverage
reaches their legs -- and the butterfly crosses first (the factor of four).
Panel (b): the dead-leg law -- one unquoted leg unidentifies the basket
however well the other is quoted.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import estimation
import figstyle
from figstyle import PALETTE
from macros import STORE, num

N_QUOTES = 9  # a nine-quote morning (the vignette's near-ATM cluster)
K_LEG = 0.18       # the wing legs of the RR/BF baskets
REQUIRED = 1.0

ATM = (np.array([0.0]), np.array([1.0]))
RR = (np.array([+K_LEG, -K_LEG]), np.array([+1.0, -1.0]))
BF = (np.array([+K_LEG, -K_LEG, 0.0]), np.array([0.5, 0.5, -1.0]))


def _precision(legs, coeffs, k_quotes) -> float:
    return estimation.basket_precision(
        coeffs, estimation.support(legs, k_quotes))


def fig_flt_basket() -> str:
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) widening band sweep.
    widths = np.linspace(0.01, 0.32, 160)
    prec = {"ATM": [], "RR": [], "BF": []}
    for w in widths:
        kq = np.linspace(-w, w, N_QUOTES)
        prec["ATM"].append(_precision(*ATM, kq))
        prec["RR"].append(_precision(*RR, kq))
        prec["BF"].append(_precision(*BF, kq))
    colors = {"ATM": PALETTE["data"], "RR": PALETTE["model"],
              "BF": PALETTE["alt"]}
    for name in ("ATM", "RR", "BF"):
        ax_a.semilogy(widths, prec[name], color=colors[name], lw=1.5,
                      label=name)
    ax_a.axhline(REQUIRED, color=PALETTE["muted"], lw=0.9, ls=":")
    ax_a.axvline(K_LEG, color=PALETTE["muted"], lw=0.9, ls="--")
    ax_a.annotate("wing legs", (K_LEG + 0.006, 0.055), fontsize=7.5,
                  color=PALETTE["muted"])
    ax_a.annotate("requirement", (0.015, REQUIRED * 1.25), fontsize=7.5,
                  color=PALETTE["muted"])
    ax_a.set_xlabel("quoted band half-width")
    ax_a.set_ylabel("identification precision  $\\mathcal{I}(O)$")
    ax_a.legend(loc="lower right")
    figstyle.panel(ax_a, "a", "a fixed quote budget over a widening band")

    # crossing points (first width where precision >= required).
    cross = {}
    for name in ("RR", "BF"):
        arr = np.asarray(prec[name])
        idx = np.argmax(arr >= REQUIRED)
        cross[name] = float(widths[idx]) if arr[idx] >= REQUIRED else np.nan

    # (b) the dead-leg law.
    s_call = 6.0
    s_put = np.linspace(1e-3, 6.0, 400)
    rr_prec = 1.0 / (1.0 / s_call + 1.0 / s_put)
    s_atm = 25.0
    bf_prec = 1.0 / (0.25 / s_call + 0.25 / s_put + 1.0 / s_atm)
    ax_b.plot(s_put, rr_prec, color=PALETTE["model"], lw=1.5,
              label="RR  ($\\omega=\\pm1$)")
    ax_b.plot(s_put, bf_prec, color=PALETTE["alt"], lw=1.5,
              label="BF  ($\\omega=\\frac{1}{2},\\frac{1}{2},-1$)")
    ax_b.axhline(REQUIRED, color=PALETTE["muted"], lw=0.9, ls=":")
    i01 = int(np.argmin(np.abs(s_put - 0.1)))
    figstyle.callout(
        ax_b, f"one dying leg:\n$\\mathcal{{I}}$(RR) = {rr_prec[i01]:.2f}",
        (0.1, rr_prec[i01]), (0.9, 1.9),
    )
    ax_b.set_xlabel("put-leg support  $\\mathcal{Q}_{\\mathrm{put}}$  "
                    "(call leg fixed at 6)")
    ax_b.set_ylabel("identification precision  $\\mathcal{I}(O)$")
    ax_b.legend(loc="upper left")
    figstyle.panel(ax_b, "b", "one dead leg unidentifies the basket")

    figstyle.save(fig, "fig_flt_basket")

    # the symmetric factor of four (equal wing support s, abundant ATM).
    s_sym = 3.0
    rr_sym = 1.0 / (2.0 / s_sym)
    bf_sym = 1.0 / (0.5 / s_sym)  # ATM support taken as infinite here
    STORE.add("basket", "PriorBasketRrDead", num(float(rr_prec[i01]), 2),
              "RR precision with call support 6, put support 0.1")
    STORE.add("basket", "PriorBasketCrossRr", num(cross["RR"], 2),
              "band half-width where the RR basket reaches the requirement")
    STORE.add("basket", "PriorBasketCrossBf", num(cross["BF"], 2),
              "band half-width where the BF basket reaches the requirement")
    STORE.add("basket", "PriorBasketFactor", num(bf_sym / rr_sym, 0),
              "BF-to-RR precision ratio on the same symmetric legs")
    STORE.add("basket", "PriorBasketLeg", num(K_LEG, 2),
              "wing-leg location of the sweep's baskets")
    return (f"RR crosses at {cross['RR']:.2f}, BF at {cross['BF']:.2f}; "
            f"dead-leg RR {rr_prec[i01]:.2f}")
