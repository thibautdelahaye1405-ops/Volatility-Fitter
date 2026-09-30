"""F7 -- the frozen board under a scenario (section 9.7).

Panel (a): the frozen SPY ATM term structure and its three transported
versions under a -5% forward move -- each node's own fitted curve read at
k = R H: the fan is widest at the short end, where the skew is steepest.
Panel (b): the delta stakes across the same board -- the R=0 vs R=2
total-delta gap at each expiry's 25-delta put, with the smile's local
slope at that strike.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq
from scipy.special import ndtri

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
from blackutil import d_plus, phi
from figstyle import PALETTE, REGIME_COLORS, REGIME_NAMES
from macros import STORE, num

_H = -0.05
_D25 = float(ndtri(0.75))      # d_+ of a 25-delta put: Phi(d_+) = 0.75


def _k25(sm) -> float:
    """The 25-delta put strike of a node: Phi(d_+(k, w(k))) = 0.75."""
    def f(k):
        return float(d_plus(np.array([k]), sm.w(np.array([k])))[0]) - _D25
    return float(brentq(f, -1.5, 0.0))


def fig_ssr_scenario() -> str:
    board = data9.gallery("SPY")
    days = np.array([sm.days for sm in board], dtype=float)
    atm = np.array([sm.atm_vol for sm in board])
    s0 = np.array([sm.s0 for sm in board])

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the transported ATM term structure (the exact per-node transport:
    # each node's own fitted curve read at k = R H) -------------------------
    ax = axes[0]
    moved = {
        regime: np.array([float(sm.iv(np.array([regime * _H]))[0])
                          for sm in board])
        for regime in data9.REGIMES
    }
    for regime in data9.REGIMES:
        ax.plot(days, 100.0 * moved[regime], "o-",
                color=REGIME_COLORS[regime],
                lw=1.2, ms=3.0, label=REGIME_NAMES[regime], zorder=3)
    ax.plot(days, 100.0 * atm, "o--", color=PALETTE["data"], lw=1.0,
            ms=4.0, label="today", zorder=4)
    ax.set_xscale("log")
    ax.set_xlabel("calendar days to expiry (log scale)")
    ax.set_ylabel("ATM implied volatility (%)")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "a",
                   f"the board after $H={100*_H:+.0f}\\%$")

    # (b) the delta stakes across the board ---------------------------------
    ax = axes[1]
    k25 = np.array([_k25(sm) for sm in board])
    slope25 = np.array([
        float(data9.local_slope(sm, np.array([kk]))[0])
        for sm, kk in zip(board, k25)
    ])
    gap = 2.0 * phi(np.full_like(days, _D25)) * np.sqrt(
        np.array([sm.t for sm in board])) * np.abs(slope25)
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
              num(100.0 * moved[1.0][0], 1),
              "shortest expiry: sticky-strike ATM after the move, the fit "
              "read at k = H, %")
    STORE.add("scenario", "SsrScenShortRzeroPct",
              num(100.0 * moved[0.0][0], 1),
              "shortest expiry: sticky-moneyness ATM after the move "
              "(= today's, exactly), %")
    STORE.add("scenario", "SsrScenShortRtwoPct",
              num(100.0 * moved[2.0][0], 1),
              "shortest expiry: R=2 ATM after the move, the fit read at "
              "k = 2H, %")
    STORE.add("scenario", "SsrScenShortDays", f"{days[0]:.0f}",
              "shortest board expiry, days")
    STORE.add("scenario", "SsrScenShortSkew", num(float(s0[0]), 2),
              "shortest expiry's ATM skew s0")
    STORE.add("scenario", "SsrScenShortAtmMovePts",
              num((moved[2.0][0] - moved[0.0][0]) * 100.0, 1),
              "shortest expiry: spread of the ATM readings between R=0 and "
              "R=2 under the scenario, vol pts")
    STORE.add("scenario", "SsrScenShortLinearPts",
              num(abs(2.0 * s0[0] * _H) * 100.0, 1),
              "shortest expiry: the linear law's R=2 ATM response 2|s0 H|, "
              "vol pts")
    STORE.add("scenario", "SsrScenLongAtmMovePts",
              num((moved[2.0][-1] - moved[0.0][-1]) * 100.0, 1),
              "longest expiry: spread of the ATM readings between R=0 and "
              "R=2 under the scenario, vol pts")
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
    STORE.add("scenario", "SsrScenSlopeShort", num(float(slope25[0]), 2),
              "smile slope at the shortest expiry's 25-delta put")
    STORE.add("scenario", "SsrScenSlopeHero", num(float(slope25[hero_idx]), 3),
              "smile slope at the hero expiry's 25-delta put")
    STORE.add("scenario", "SsrScenSlopeLong", num(float(slope25[-1]), 3),
              "smile slope at the longest expiry's 25-delta put")
    return (f"short ATM spread {(moved[2.0][0]-moved[0.0][0])*100:.1f} pts, "
            f"gaps {100*gap[0]:.1f}->{100*gap[-1]:.1f} pts")
