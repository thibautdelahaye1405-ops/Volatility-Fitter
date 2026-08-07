"""F4 -- an earnings week on paper: the crush as a reading error.

A synthetic name whose clock volatility is flat at 30% with one event
(four extra days) scheduled at day 10.
Panel (a): the ATM term structure across expiries, read on both clocks --
flat on the variance clock, the familiar event hump on the calendar.
Panel (b): one fixed expiry (day 14) re-read on successive valuation days
-- the calendar reading ramps INTO the event and collapses the morning
after, while the clock reading never moves.  No price moved either.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
from figstyle import PALETTE
from macros import STORE, num

SIGMA_CLK = 0.30     # flat clock volatility of the synthetic name
EVENT_DAY = 10.0     # event date, calendar days from the start
EXTRA_DAYS = 4.0     # N_e
EXPIRY_DAY = 14.0    # the fixed expiry panel (b) tracks


def _tau_rem(t_rem_days: np.ndarray, event_ahead: np.ndarray) -> np.ndarray:
    """Remaining variance days: remaining calendar days + N_e if ahead."""
    return t_rem_days + np.where(event_ahead, EXTRA_DAYS, 0.0)


def fig_clk_crush() -> str:
    # (a) term structure at the start of the week.
    T_days = np.linspace(1.0, 56.0, 1101)
    tau_days = T_days + np.where(T_days >= EVENT_DAY, EXTRA_DAYS, 0.0)
    sig_cal = SIGMA_CLK * np.sqrt(tau_days / T_days)
    weekly = np.arange(7.0, 57.0, 7.0)
    tau_w = weekly + np.where(weekly >= EVENT_DAY, EXTRA_DAYS, 0.0)
    sig_w = SIGMA_CLK * np.sqrt(tau_w / weekly)

    # (b) the fixed expiry read on valuation days s = 0..13.  The event
    # resolves overnight between day 10 and day 11.
    s = np.arange(0.0, EXPIRY_DAY)
    t_rem = EXPIRY_DAY - s
    ahead = s <= EVENT_DAY
    tau_rem = _tau_rem(t_rem, ahead)
    reading = SIGMA_CLK * np.sqrt(tau_rem / t_rem)

    peak_term = float(sig_cal[np.argmin(np.abs(T_days - EVENT_DAY))])
    ramp0 = float(reading[0])
    peak_path = float(reading[int(EVENT_DAY)])
    post = float(reading[int(EVENT_DAY) + 1])
    STORE.add("crush", "ClkCrushTermPeakPct", num(peak_term * 100, 1),
              "term-structure hump peak at the event-day expiry (%)")
    STORE.add("crush", "ClkCrushRampStartPct", num(ramp0 * 100, 1),
              "day-0 calendar reading of the day-14 expiry (%)")
    STORE.add("crush", "ClkCrushPeakPct", num(peak_path * 100, 1),
              "last pre-event calendar reading of the day-14 expiry (%)")
    STORE.add("crush", "ClkCrushPostPct", num(post * 100, 1),
              "morning-after calendar reading (%)")
    STORE.add("crush", "ClkCrushDropBp", num((peak_path - post) * 1e4, 0),
              "the overnight crush of the reading (vol bp)")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) two readings of one term structure.
    ax_a.plot(T_days, sig_cal * 100, color=PALETTE["data"], lw=1.6,
              label="calendar reading")
    ax_a.plot(weekly, sig_w * 100, "o", color=PALETTE["data"], ms=4.0)
    ax_a.axhline(SIGMA_CLK * 100, color=PALETTE["model"], lw=1.4,
                 label="clock reading (flat)")
    ax_a.axvline(EVENT_DAY, color=PALETTE["muted"], lw=0.9, ls=":")
    ax_a.set_ylim(29.1, 36.2)
    figstyle.callout(
        ax_a, "expiries that dodge\nthe event", (7.3, 29.95), (14.0, 29.45),
    )
    ax_a.set_xlabel("calendar days to expiry")
    ax_a.set_ylabel("ATM implied vol  (%)")
    ax_a.legend(loc="upper right")
    figstyle.panel(ax_a, "a", "one term structure, two readings")

    # (b) the crush path of one expiry.
    ax_b.step(s, reading * 100, where="post", color=PALETTE["data"], lw=1.6,
              label="calendar reading")
    ax_b.plot(s, reading * 100, "o", color=PALETTE["data"], ms=3.4)
    ax_b.axhline(SIGMA_CLK * 100, color=PALETTE["model"], lw=1.4,
                 label="clock reading")
    ax_b.axvline(EVENT_DAY + 0.5, color=PALETTE["muted"], lw=0.9, ls=":")
    figstyle.callout(
        ax_b,
        f"the crush: $-${(peak_path - post) * 1e4:.0f} vol bp\n"
        "overnight, on schedule",
        (EVENT_DAY + 0.8, post * 100 + 0.3),
        (0.3, post * 100 + 1.3),
    )
    ax_b.set_xlabel("valuation day (expiry at day 14)")
    ax_b.set_ylabel("ATM implied vol  (%)")
    ax_b.legend(loc="upper left")
    figstyle.panel(ax_b, "b", "one expiry through the event")

    figstyle.save(fig, "fig_clk_crush")
    return f"crush {(peak_path - post) * 1e4:.0f} bp"
