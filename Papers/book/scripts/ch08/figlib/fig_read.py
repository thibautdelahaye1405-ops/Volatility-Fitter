"""F7 -- reading the frozen board's clock: NVDA twice, SPY once.

Panel (a): the NVDA ladder through year-end (candidates at the first five
expiries) -- the solver puts its budget against the earnings-bearing
interval and equalizes the short end.
Panel (b): the same board with candidates everywhere -- the solver
flattens every kink, buying hundreds of days; a perfectly flat ladder
purchased by telling the clock story about everything.
Panel (c): SPY, the index contrast -- a genuinely rising term structure
is left almost untouched.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import clock8
import data8
import figstyle
from figstyle import PALETTE
from macros import STORE, num


def _steps(ax, edges_days, f, color, lw=1.5, ls="-", label=None, alpha=1.0):
    for i, fi in enumerate(f):
        ax.plot(
            [edges_days[i], edges_days[i + 1]], [fi, fi],
            color=color, lw=lw, ls=ls, alpha=alpha, solid_capstyle="butt",
            label=label if i == 0 else None,
        )


def _xaxis(ax, ticks):
    ax.set_xscale("log")
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{d:.0f}" for d in ticks])
    ax.minorticks_off()


def fig_clk_read() -> str:
    t_n, w_n, exp_n = data8.ladder("NVDA")
    t_s, w_s, _ = data8.ladder("SPY")
    days_n = t_n * 365.0
    days_s = t_s * 365.0
    horizon = float(t_n[exp_n.index(data8.HORIZON_EXPIRY)])

    f0_n, _ = clock8.fwd_var(t_n, w_n, np.zeros(len(t_n)))
    f0_s, _ = clock8.fwd_var(t_s, w_s, np.zeros(len(t_s)))

    N_hero = clock8.solve(t_n, w_n, horizon=horizon)
    f_hero, _ = clock8.fwd_var(t_n, w_n, N_hero)
    N_full = clock8.solve(t_n, w_n)
    f_full, _ = clock8.fwd_var(t_n, w_n, N_full)
    N_spy = clock8.solve(t_s, w_s)
    f_spy, _ = clock8.fwd_var(t_s, w_s, N_spy)

    n_h = int(np.sum(t_n <= horizon + 1e-12))  # in-horizon interval count
    i_earn = 3                                 # the (18d, 46d] interval

    STORE.add("read", "ClkReadHeroEarnD", num(N_hero[i_earn], 1),
              "extra days the year-end solve puts on the earnings interval")
    STORE.add("read", "ClkReadHeroTotalD", num(N_hero.sum(), 1),
              "total extra days installed by the year-end solve")
    STORE.add("read", "ClkReadHeroShortD",
              num(N_hero[0] + N_hero[1], 1),
              "extra days on the two short-dated intervals combined")
    STORE.add("read", "ClkReadHeroSpreadBeforeBp",
              num(clock8.spread_bp(f0_n[:n_h]), 0),
              "in-horizon forward-variance spread before (var bp)")
    STORE.add("read", "ClkReadHeroSpreadAfterBp",
              num(clock8.spread_bp(f_hero[:n_h]), 0),
              "in-horizon forward-variance spread after (var bp)")
    STORE.add("read", "ClkReadHeroFlatLevel", num(f_hero[0], 4),
              "level the three pre-earnings intervals meet at (var/yr)")
    STORE.add("read", "ClkReadHeroEarnAfter", num(f_hero[i_earn], 4),
              "earnings interval forward variance after the solve (var/yr)")
    STORE.add("read", "ClkReadFullTotalD", num(N_full.sum(), 0),
              "total extra days installed with candidates everywhere")
    STORE.add("read", "ClkReadFullSpreadBeforeBp",
              num(clock8.spread_bp(f0_n), 0),
              "full-board spread before (var bp)")
    STORE.add("read", "ClkReadFullSpreadAfterBp",
              num(clock8.spread_bp(f_full), 0),
              "full-board spread after (var bp)")
    STORE.add("read", "ClkReadFullMarchD", num(N_full[5], 0),
              "extra days the unrestricted solve puts on Dec->Mar alone")
    STORE.add("read", "ClkReadSpyTotalD", num(N_spy.sum(), 1),
              "total extra days installed on the SPY board")
    STORE.add("read", "ClkReadSpySpreadBp", num(clock8.spread_bp(f0_s), 0),
              "SPY forward-variance spread left in place (var bp)")
    STORE.add("read", "ClkReadSpyMidVolPct",
              num(float(np.sqrt(np.median(f0_s))) * 100, 0),
              "SPY median forward variance quoted as a volatility (%)")
    STORE.add("read", "ClkReadSpyDecBp",
              num(float(np.max(np.maximum(-np.diff(f0_s), 0.0))) * 1e4, 0),
              "largest decrease anywhere in SPY's calendar ladder (var bp)")

    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=figstyle.ROW3)

    # Calendar ladders are drawn wide underneath so an untouched interval
    # shows orange peeking behind the thinner blue.
    # (a) NVDA through year-end.
    edges = np.concatenate([[1.5], days_n])  # log axis: start near 2d
    _steps(ax_a, edges[: n_h + 1], f0_n[:n_h], PALETTE["data"], lw=2.6,
           label="per calendar year")
    _steps(ax_a, edges[: n_h + 1], f_hero[:n_h], PALETTE["model"], lw=1.2,
           label="per variance year")
    _xaxis(ax_a, [2, 4, 18, 46, 137])
    ax_a.axvspan(days_n[2], days_n[3], color=PALETTE["band"], alpha=0.75,
                 zorder=0)
    ax_a.set_ylim(0.130, 0.205)
    figstyle.callout(
        ax_a, f"+{N_hero[i_earn]:.1f} days",
        (28.0, f_hero[i_earn]), (2.5, 0.150),
    )
    ax_a.set_ylabel("forward variance (per year)")
    ax_a.set_xlabel("calendar days")
    ax_a.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "NVDA, through year-end")

    # (b) NVDA, candidates everywhere.
    _steps(ax_b, edges, f0_n, PALETTE["data"], lw=2.6)
    _steps(ax_b, edges, f_full, PALETTE["model"], lw=1.2)
    _xaxis(ax_b, [2, 18, 46, 137, 501])
    figstyle.callout(
        ax_b, f"{N_full.sum():.0f} days installed:\nevery kink read as clock",
        (137.0, f_full[5]), (40.0, 0.135),
    )
    ax_b.set_xlabel("calendar days")
    figstyle.panel(ax_b, "b", "NVDA, no horizon")

    # (c) SPY.
    edges_s = np.concatenate([[1.5], days_s])
    _steps(ax_c, edges_s, f0_s, PALETTE["data"], lw=2.6)
    _steps(ax_c, edges_s, f_spy, PALETTE["model"], lw=1.2)
    _xaxis(ax_c, [2, 18, 46, 137, 501])
    figstyle.callout(
        ax_c, f"{N_spy.sum():.1f} day installed\nin total",
        (days_s[3] * 0.8, f_spy[3]), (2.5, 0.028),
    )
    ax_c.set_xlabel("calendar days")
    figstyle.panel(ax_c, "c", "SPY: the index keeps the calendar")

    figstyle.save(fig, "fig_clk_read")
    return (f"hero +{N_hero[i_earn]:.1f}d / full {N_full.sum():.0f}d / "
            f"SPY {N_spy.sum():.1f}d")
