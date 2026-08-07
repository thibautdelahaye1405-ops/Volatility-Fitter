"""F1 -- the opening puzzle: the frozen NVDA board on the calendar clock.

Panel (a): the calendar ATM implied-vol readings across the eight quoted
expiries -- the 18-day expiry dips below both its neighbours.
Panel (b): forward variance per calendar year, interval by interval -- the
pre-earnings lull and the hot earnings-bearing interval.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import clock8
import data8
import figstyle
from figstyle import PALETTE
from macros import STORE, num


def _steps(ax, t_days, f, color, label, lw=1.6, ls="-"):
    """Draw a forward-variance ladder as horizontal per-interval segments."""
    edges = np.concatenate([[0.0], t_days])
    for i, fi in enumerate(f):
        ax.plot(
            [edges[i], edges[i + 1]], [fi, fi],
            color=color, lw=lw, ls=ls, solid_capstyle="butt",
            label=label if i == 0 else None,
        )


def fig_clk_board() -> str:
    t, w, expiries = data8.ladder("NVDA")
    days = t * 365.0
    sigma_cal = np.sqrt(w / t)
    f_cal, _ = clock8.fwd_var(t, w, np.zeros(len(t)))

    # The three puzzle readings the text hand-walks (4d, 18d, 46d) plus the
    # 2-day node, and the hand computation of the two interval rates.
    i4, i18, i46 = 1, 2, 3
    STORE.add("board", "ClkBoardVolTwoDPct", num(sigma_cal[0] * 100),
              "NVDA 2-day calendar ATM vol (%)")
    STORE.add("board", "ClkBoardVolFourDPct", num(sigma_cal[i4] * 100),
              "NVDA 4-day calendar ATM vol (%)")
    STORE.add("board", "ClkBoardVolEighteenDPct", num(sigma_cal[i18] * 100),
              "NVDA 18-day calendar ATM vol (%)")
    STORE.add("board", "ClkBoardVolFortySixDPct", num(sigma_cal[i46] * 100),
              "NVDA 46-day calendar ATM vol (%)")
    STORE.add("board", "ClkBoardDipBp",
              num((sigma_cal[i4] - sigma_cal[i18]) * 1e4, 0),
              "drop from the 4-day to the 18-day reading (vol bp)")
    # Total variances in variance bp for the hand computation.
    for name, idx in (("Four", i4), ("Eighteen", i18), ("FortySix", i46)):
        STORE.add("board", f"ClkBoardW{name}Bp", num(w[idx] * 1e4, 1),
                  f"ATM total variance at the {name}-day expiry (var bp)")
    d_lull = days[i18] - days[i4]
    d_hot = days[i46] - days[i18]
    lull_day = (w[i18] - w[i4]) * 1e4 / d_lull
    hot_day = (w[i46] - w[i18]) * 1e4 / d_hot
    STORE.add("board", "ClkBoardLullDays", num(d_lull, 0),
              "calendar days in the lull interval (4d -> 18d)")
    STORE.add("board", "ClkBoardHotDays", num(d_hot, 0),
              "calendar days in the earnings interval (18d -> 46d)")
    STORE.add("board", "ClkBoardLullPerDay", num(lull_day),
              "lull interval: variance bp accrued per calendar day")
    STORE.add("board", "ClkBoardHotPerDay", num(hot_day),
              "earnings interval: variance bp accrued per calendar day")
    STORE.add("board", "ClkBoardHotOverLull", num(hot_day / lull_day),
              "ratio of the two accrual rates")
    STORE.add("board", "ClkBoardLullFwd", num(f_cal[i18], 4),
              "lull interval forward variance per calendar year")
    STORE.add("board", "ClkBoardHotFwd", num(f_cal[i46], 4),
              "earnings interval forward variance per calendar year")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) calendar ATM vol readings.
    ax_a.plot(days, sigma_cal * 100, color=PALETTE["data"], lw=1.3,
              marker="o", ms=4.5, zorder=3)
    ax_a.set_xscale("log")
    ax_a.set_xticks([2, 4, 18, 46, 137, 501])
    ax_a.set_xticklabels(["2", "4", "18", "46", "137", "501"])
    ax_a.minorticks_off()
    ax_a.set_xlabel("calendar days to expiry")
    ax_a.set_ylabel(r"calendar ATM vol $\sigma_{\rm cal}$  (%)")
    figstyle.callout(
        ax_a, "the dip:\n" + f"{sigma_cal[i18]*100:.1f}%",
        (days[i18], sigma_cal[i18] * 100),
        (days[i18] * 2.6, sigma_cal[i18] * 100 + 0.6),
    )
    figstyle.panel(ax_a, "a", "eight expiries, one afternoon (NVDA)")

    # (b) forward variance per calendar year, per interval.
    _steps(ax_b, days, f_cal, PALETTE["data"], None)
    ax_b.set_xscale("log")
    ax_b.set_xticks([2, 4, 18, 46, 137, 501])
    ax_b.set_xticklabels(["2", "4", "18", "46", "137", "501"])
    ax_b.minorticks_off()
    ax_b.axvspan(days[i18], days[i46], color=PALETTE["band"], alpha=0.75,
                 zorder=0)
    ax_b.set_xlabel("calendar days (intervals between expiries)")
    ax_b.set_ylabel(r"$\Delta w_i/\Delta t_i$  (variance / cal. year)")
    figstyle.callout(
        ax_b, "the lull", (0.5 * (days[i4] + days[i18]), f_cal[i18]),
        (6.0, f_cal[i18] - 0.045),
    )
    figstyle.callout(
        ax_b, "earnings inside", (0.5 * (days[i18] + days[i46]), f_cal[i46]),
        (40.0, f_cal[i46] + 0.03),
    )
    figstyle.panel(ax_b, "b", "the same board as accrual rates")

    figstyle.save(fig, "fig_clk_board")
    return f"dip {sigma_cal[i18]*100:.2f}% vs {sigma_cal[i4]*100:.2f}%"
