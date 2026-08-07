"""F7 -- the frozen board under a scenario (section 9.7).

Panel (a): the frozen SPY ATM term structure and its three transported
versions under a -5% forward move: the fan is widest at the short end,
where the skew is steepest.  Panel (b): the delta stakes across the same
board -- the R=0 vs R=2 total-delta gap at each expiry's 25-delta put.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import ndtri

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
from blackutil import phi
from figstyle import PALETTE, REGIME_COLORS, REGIME_NAMES
from macros import STORE, num

_H = -0.05
_D25 = float(ndtri(0.75))      # d_+ of a 25-delta put: Phi(d_+) = 0.75


def fig_ssr_scenario() -> str:
    board = data9.gallery("SPY")
    days = np.array([sm.days for sm in board], dtype=float)
    atm = np.array([sm.atm_vol for sm in board])
    s0 = np.array([sm.s0 for sm in board])

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the transported ATM term structure (the exact per-node transport:
    # each node's own fitted curve read at k = H, plus the level) -----------
    ax = axes[0]
    reindex = np.array([float(sm.iv(np.array([_H]))[0]) for sm in board])
    for regime in data9.REGIMES:
        moved = reindex + (regime - 1.0) * s0 * _H
        ax.plot(days, 100.0 * moved, "o-", color=REGIME_COLORS[regime],
                lw=1.2, ms=3.0, label=REGIME_NAMES[regime], zorder=3)
    ax.plot(days, 100.0 * atm, "o-", color=PALETTE["data"], lw=1.6,
            ms=4.0, label="today", zorder=4)
    ax.set_xscale("log")
    ax.set_xlabel("calendar days to expiry (log scale)")
    ax.set_ylabel("ATM implied volatility (%)")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "a",
                   f"the board after $H={100*_H:+.0f}\\%$")

    # (b) the delta stakes across the board ---------------------------------
    ax = axes[1]
    gap = 2.0 * phi(np.full_like(days, _D25)) * np.sqrt(
        np.array([sm.t for sm in board])) * np.abs(s0)
    ax.plot(days, 100.0 * gap, "o-", color=PALETTE["ink"], lw=1.4, ms=4.0)
    ax.set_xscale("log")
    ax.set_xlabel("calendar days to expiry (log scale)")
    ax.set_ylabel("delta gap at the 25-delta put (points)")
    figstyle.panel(ax, "b", "the stakes never fade")

    figstyle.save(fig, "fig_ssr_scenario")

    hero_idx = int(np.argmin(np.abs(days - data9.hero().days)))
    STORE.add("scenario", "SsrScenMovePct", f"{abs(100*_H):.0f}",
              "the board scenario's move magnitude, % (down)")
    STORE.add("scenario", "SsrScenShortTodayPct", num(100.0 * atm[0], 1),
              "shortest expiry: today's ATM vol, %")
    STORE.add("scenario", "SsrScenShortReindexPct",
              num(100.0 * reindex[0], 1),
              "shortest expiry: the re-index read sigma_old(H) "
              "(= sticky-strike ATM after the move), %")
    STORE.add("scenario", "SsrScenShortRzeroPct",
              num(100.0 * (reindex[0] - s0[0] * _H), 1),
              "shortest expiry: sticky-moneyness ATM after the move, %")
    STORE.add("scenario", "SsrScenShortRtwoPct",
              num(100.0 * (reindex[0] + s0[0] * _H), 1),
              "shortest expiry: sticky-local-vol ATM after the move, %")
    STORE.add("scenario", "SsrScenShortDays", f"{days[0]:.0f}",
              "shortest board expiry, days")
    STORE.add("scenario", "SsrScenShortSkew", num(float(s0[0]), 2),
              "shortest expiry's ATM skew s0")
    STORE.add("scenario", "SsrScenShortAtmMovePts",
              num(abs(2.0 * s0[0] * _H) * 100.0, 1),
              "shortest expiry: spread of the ATM readings between R=0 and "
              "R=2 under the scenario (= 2|s0 H|), vol pts")
    STORE.add("scenario", "SsrScenLongAtmMovePts",
              num(abs(2.0 * s0[-1] * _H) * 100.0, 1),
              "longest expiry's linear R=2 ATM response to the scenario "
              "(2|s0 H|), vol pts")
    STORE.add("scenario", "SsrScenLongSkew", num(float(s0[-1]), 2),
              "longest expiry's ATM skew s0")
    STORE.add("scenario", "SsrScenRootScaledSkew", num(
        abs(float(s0[0])) * np.sqrt(
            float(board[0].t) / float(board[hero_idx].t)), 2),
              "the two-day skew scaled by sqrt(tau) to the hero maturity "
              "(the 1/sqrt(tau)-decay prediction), absolute value")
    STORE.add("scenario", "SsrScenGapShortPts", num(100.0 * gap[0], 1),
              "25-delta-put delta gap at the shortest expiry, delta pts")
    STORE.add("scenario", "SsrScenGapLongPts", num(100.0 * gap[-1], 1),
              "25-delta-put delta gap at the longest expiry, delta pts")
    STORE.add("scenario", "SsrScenGapHeroPts",
              num(100.0 * gap[hero_idx], 1),
              "25-delta-put delta gap at the hero expiry, delta pts")
    return (f"short ATM move {abs(2.0*s0[0]*_H)*100:.1f} pts, "
            f"gaps {100*gap[0]:.1f}->{100*gap[-1]:.1f} pts")
