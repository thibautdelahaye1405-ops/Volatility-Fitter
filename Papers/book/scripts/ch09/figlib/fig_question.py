"""F1 -- the question (section 9.1): three tomorrows through one smile.

Panel (a): today's frozen SPY December 2026 fitted smile with its prepared
mid quotes, and the three canonical tomorrows after a -4% forward move --
all consistent with every price quoted today.  Panel (b): the vol of ONE
fixed strike (today's k = -0.10 put) as a function of the move, under the
three regimes: three straight lines of slope (R-1) s0, crossing at H = 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import data3  # importable once data9 has extended sys.path
import figstyle
from figstyle import PALETTE, REGIME_COLORS, REGIME_NAMES
from macros import STORE, num

_H = data9.H_FAN
_SPAN = (-0.20, 0.12)


def fig_ssr_question() -> str:
    sm = data9.hero()
    node = data3.node(*data9.HERO)
    assert sm.k_lo < _SPAN[0] + _H and sm.k_hi > _SPAN[1], "fit span too narrow"

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) today's smile and the three tomorrows -----------------------------
    ax = axes[0]
    k = np.linspace(*_SPAN, 401)
    sel = (node.k >= _SPAN[0]) & (node.k <= _SPAN[1])
    ax.plot(node.k[sel], 100.0 * node.iv_mid[sel], "o", ms=2.4,
            color=PALETTE["data"], alpha=0.45, zorder=2)
    ax.plot(k, 100.0 * sm.iv(k), color=PALETTE["data"], lw=1.7,
            label="today", zorder=4)
    for regime in data9.REGIMES:
        iv_new = data9.transport_vol(sm, _H, regime)
        ax.plot(k, 100.0 * iv_new(k), color=REGIME_COLORS[regime], lw=1.2,
                label=REGIME_NAMES[regime], zorder=3)
    ax.set_xlabel(r"log-moneyness $k$ (prevailing forward)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax, "a", f"three tomorrows after a {100*_H:+.0f}% move")

    # (b) one fixed strike, three answers -----------------------------------
    ax = axes[1]
    h_grid = np.linspace(-0.05, 0.05, 101)
    vol0 = float(sm.iv(np.array([data9.K_MARK]))[0])
    for regime in data9.REGIMES:
        vol_line = vol0 + (regime - 1.0) * sm.s0 * h_grid
        ax.plot(100.0 * h_grid, 100.0 * vol_line,
                color=REGIME_COLORS[regime], lw=1.3,
                label=REGIME_NAMES[regime])
    ax.axvline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.plot([0.0], [100.0 * vol0], "o", ms=4.5, color=PALETTE["data"],
            zorder=5)
    spread_bp = 2.0 * abs(sm.s0 * _H) * 1e4
    figstyle.callout(
        ax, f"{spread_bp:.0f} vol bp apart\nat a {100*_H:+.0f}% move",
        xy=(100.0 * _H, 100.0 * (vol0 + sm.s0 * _H)),
        xytext=(-4.6, 100.0 * vol0 + 0.62),
    )
    ax.set_xlabel(r"forward move $H$ (%)")
    ax.set_ylabel(f"vol at today's $k={data9.K_MARK:.2f}$ strike (%)")
    figstyle.panel(ax, "b", "the same quote, three futures")

    figstyle.save(fig, "fig_ssr_question")

    STORE.add("question", "SsrHeroDays", f"{sm.days:d}",
              "hero node: calendar days to expiry")
    STORE.add("question", "SsrHeroAtmPct", num(100.0 * sm.atm_vol, 1),
              "hero node ATM implied vol, %")
    STORE.add("question", "SsrHeroSkew", num(sm.s0, 3),
              "hero node ATM skew s0 (vol per unit log-moneyness)")
    STORE.add("question", "SsrFanMovePct", f"{abs(100*_H):.0f}",
              "the fan's forward move magnitude, % (down)")
    STORE.add("question", "SsrMarkVolPct", num(100.0 * vol0, 1),
              "today's vol at the marked k=-0.10 strike, %")
    STORE.add("question", "SsrMarkSpreadBp", f"{spread_bp:.0f}",
              "spread of the marked strike's vol across regimes at the fan "
              "move, vol bp")
    return f"s0={sm.s0:+.3f}, mark spread {spread_bp:.0f} bp"
