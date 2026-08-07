"""F3 -- the day-weighted clock and what it does to a reading.

One event worth four extra days, ten calendar days out.
Panel (a): the clock tau_days(t) -- calendar line, jump at the event,
parallel afterward; the normalized variant rescales the whole year.
Panel (b): the reading ratio sigma_cal / sigma = sqrt(tau/t) across
expiries -- one at the event date, largest just past it, decaying like
1 + N_e / (2 x 365 t).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import clock8
import figstyle
from figstyle import PALETTE
from macros import STORE, num

EVENT_DAY = 10.0     # t_e in calendar days
EXTRA_DAYS = 4.0     # N_e
EVENTS = [(EVENT_DAY / 365.0, EXTRA_DAYS)]


def fig_clk_clock() -> str:
    t_days = np.linspace(0.0, 30.0, 601)
    t = t_days / 365.0
    tau_plain = clock8.tau_years(t, EVENTS) * 365.0
    tau_norm = clock8.tau_years(t, EVENTS, normalize=True) * 365.0

    # Reading ratio across expiries (panel b), plus the worked numbers.
    T_days = np.linspace(1.0, 60.0, 1181)
    T = T_days / 365.0
    ratio = np.sqrt(clock8.tau_years(T, EVENTS) / T)
    approx = 1.0 + np.where(T_days >= EVENT_DAY, EXTRA_DAYS, 0.0) / (
        2.0 * T_days
    )

    peak = float(np.sqrt((EVENT_DAY + EXTRA_DAYS) / EVENT_DAY))
    two_weeks = float(np.sqrt((14.0 + EXTRA_DAYS) / 14.0))
    norm_factor = 365.0 / (365.0 + EXTRA_DAYS)
    STORE.add("clock", "ClkClockEventDay", num(EVENT_DAY, 0),
              "worked calendar: event date in calendar days")
    STORE.add("clock", "ClkClockExtraDays", num(EXTRA_DAYS, 0),
              "worked calendar: extra equivalent days N_e")
    STORE.add("clock", "ClkClockPeakRatio", num(peak, 3),
              "reading ratio sqrt(tau/t) at the event-day expiry")
    STORE.add("clock", "ClkClockPeakPct", num((peak - 1.0) * 100, 1),
              "the same peak as a percent lift of the reading")
    STORE.add("clock", "ClkClockRatioTwoWeeks", num(two_weeks, 3),
              "reading ratio at the 14-day expiry (the hand example)")
    STORE.add("clock", "ClkClockNormFactor", num(norm_factor, 4),
              "normalization factor 365/(365+4) for the worked calendar")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the clock itself.
    ax_a.plot(t_days, t_days, color=PALETTE["muted"], lw=1.0, ls="--",
              label=r"calendar  $\tau_{\rm days}=365\,t$")
    ax_a.plot(t_days, tau_plain, color=PALETTE["model"], lw=1.6,
              label="variance clock")
    ax_a.plot(t_days, tau_norm, color=PALETTE["model"], lw=1.1, ls=":",
              label="normalized")
    ax_a.axvline(EVENT_DAY, color=PALETTE["data"], lw=0.9, ls=":")
    figstyle.callout(
        ax_a, f"jump of {EXTRA_DAYS:.0f} days",
        (EVENT_DAY + 0.3, EVENT_DAY + EXTRA_DAYS - 0.8),
        (14.5, 7.5),
    )
    ax_a.set_xlabel("calendar days  $365\\,t$")
    ax_a.set_ylabel(r"variance days  $\tau_{\rm days}(t)$")
    ax_a.legend(loc="upper left")
    figstyle.panel(ax_a, "a", "the clock: jump, then parallel")

    # (b) the reading ratio across expiries.
    ax_b.plot(T_days, ratio, color=PALETTE["model"], lw=1.6,
              label=r"$\sqrt{\tau/t}$")
    ax_b.plot(T_days, approx, color=PALETTE["muted"], lw=1.0, ls="--",
              label=r"$1+N_e/(2\cdot 365\,t)$")
    ax_b.axvline(EVENT_DAY, color=PALETTE["data"], lw=0.9, ls=":")
    ax_b.axhline(1.0, color=PALETTE["grid"], lw=0.8)
    figstyle.callout(
        ax_b, f"peak {peak:.3f}\n(the event-day expiry)",
        (EVENT_DAY, peak), (20.0, peak - 0.02),
    )
    ax_b.set_xlabel("calendar days to expiry")
    ax_b.set_ylabel(r"reading ratio  $\sigma_{\rm cal}/\sigma$")
    ax_b.legend(loc="upper right")
    figstyle.panel(ax_b, "b", "what one event does to readings")

    figstyle.save(fig, "fig_clk_clock")
    return f"peak ratio {peak:.3f}"
