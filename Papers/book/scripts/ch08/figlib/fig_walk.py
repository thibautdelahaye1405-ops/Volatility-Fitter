"""F2 -- one walk, two rulers: the discrete time change of section 8.2.

Sixty trading days of independent normal returns, each ordinary day
carrying one day-unit of variance and the event day carrying five.
Panel (a): cumulative return against the trading-day index -- the +-1 sd
envelope kinks at the event day.
Panel (b): the same paths against accumulated variance (variance days) --
the envelope is one smooth square root; the event day is simply a longer
stretch of the same walk.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
from figstyle import PALETTE
from macros import STORE, num

N_DAYS = 30          # trading days on the board
EVENT_DAY = 20       # the scheduled event's day index (1-based)
EVENT_UNITS = 5.0    # the event day carries five ordinary days of variance
DAILY_PCT = 2.0      # one ordinary day's return sd, in percent
N_PATHS = 5          # simulated paths (one highlighted)
SEED = 8             # the chapter's fixed seed (appendix 8.A)


def fig_clk_walk() -> str:
    day_var = np.ones(N_DAYS)
    day_var[EVENT_DAY - 1] = EVENT_UNITS          # extra days land here
    tau_days = np.cumsum(day_var)                 # the variance clock
    cal_days = np.arange(1, N_DAYS + 1)           # the calendar clock

    rng = np.random.default_rng(SEED)
    sd = DAILY_PCT * np.sqrt(day_var)             # per-day return sd in %
    steps = rng.standard_normal((N_PATHS, N_DAYS)) * sd
    paths = np.cumsum(steps, axis=1)

    env = DAILY_PCT * np.sqrt(tau_days)           # +-1 sd envelope in %

    STORE.add("walk", "ClkWalkDays", num(N_DAYS, 0), "trading days simulated")
    STORE.add("walk", "ClkWalkEventDay", num(EVENT_DAY, 0),
              "index of the event day")
    STORE.add("walk", "ClkWalkEventUnits", num(EVENT_UNITS, 0),
              "day-units of variance on the event day")
    STORE.add("walk", "ClkWalkDailyPct", num(DAILY_PCT, 0),
              "one ordinary day's return sd (%)")
    STORE.add("walk", "ClkWalkEnvKinkPct",
              num(env[EVENT_DAY - 1] - env[EVENT_DAY - 2]),
              "envelope jump across the event day (% points)")
    STORE.add("walk", "ClkWalkPaths", num(N_PATHS, 0), "paths drawn")

    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=figstyle.ROW2, sharey=True
    )

    for ax, x, tag, title, xlab in (
        (ax_a, cal_days, "a", "against the calendar",
         "trading day"),
        (ax_b, tau_days, "b", "against accumulated variance",
         "variance days (accumulated)"),
    ):
        ax.fill_between(x, -env, env, color=PALETTE["band"], alpha=0.8,
                        lw=0, zorder=0)
        ax.plot(x, env, color=PALETTE["muted"], lw=1.0, zorder=2)
        ax.plot(x, -env, color=PALETTE["muted"], lw=1.0, zorder=2)
        for p in range(N_PATHS - 1):
            ax.plot(x, paths[p], color=PALETTE["model"], lw=0.7, alpha=0.35,
                    zorder=3)
        ax.plot(x, paths[-1], color=PALETTE["model"], lw=1.4, zorder=4)
        ax.set_xlabel(xlab)
        figstyle.panel(ax, tag, title)

    ax_a.set_ylabel("cumulative return  (%)")
    ax_a.axvline(EVENT_DAY, color=PALETTE["data"], lw=0.9, ls=":", zorder=1)
    figstyle.callout(
        ax_a, "event day:\nthe envelope kinks",
        (EVENT_DAY, env[EVENT_DAY - 1]),
        (2.0, env[EVENT_DAY - 1] + 4.0),
    )
    ax_b.axvspan(tau_days[EVENT_DAY - 2], tau_days[EVENT_DAY - 1],
                 color=PALETTE["data"], alpha=0.12, lw=0, zorder=1)
    figstyle.callout(
        ax_b, "the same day, now\nfive units wide -- no kink",
        (0.5 * (tau_days[EVENT_DAY - 2] + tau_days[EVENT_DAY - 1]),
         -env[EVENT_DAY - 1]),
        (2.0, -env[-1] - 4.0),
    )

    figstyle.save(fig, "fig_clk_walk")
    return f"envelope kink {env[EVENT_DAY-1]-env[EVENT_DAY-2]:.2f}%"
