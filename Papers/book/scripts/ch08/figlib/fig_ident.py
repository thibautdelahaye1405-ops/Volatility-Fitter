"""F6 -- what the peak rule can deliver: the planted-event study.

Synthetic boards whose truth is known: a flat clock volatility plus one
planted event, read by the chapter's detector.
Panel (a): recovered vs planted size on a dense board (28-day bracketing
interval) at 40% and 20% volatility and on a quarterly board (91-day
interval): exact above each board's floor, exactly zero below it, and
the same at every volatility.
Panel (b): the floor itself -- max(half a day, 3% of the interval's
width) -- against the interval width, with a 2-day event as the yardstick.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import clock8
import figstyle
from figstyle import PALETTE
from macros import STORE, num

WEEKLY_DAYS = np.array([7.0, 14.0, 28.0, 56.0, 91.0, 182.0, 365.0])
QUARTERLY_DAYS = np.array([91.0, 182.0, 273.0, 365.0])
EVENT_WEEKLY = 40.0      # inside the (28, 56] interval
EVENT_QUARTERLY = 120.0  # inside the (91, 182] interval
PLANTED = np.arange(0.0, 10.01, 0.25)
FIXED_PLANT = 2.0
WIDTHS = np.linspace(1.0, 120.0, 400)


def _recover(days: np.ndarray, event_day: float, sigma: float,
             planted: float) -> float:
    """Plant one event on a flat-clock board and return the read size."""
    t = days / 365.0
    tau_days = days + np.where(days >= event_day, planted, 0.0)
    w = sigma**2 * tau_days / 365.0
    N = clock8.detect(t, w)
    return float(N[np.searchsorted(days, event_day)])


def fig_clk_ident() -> str:
    boards = [
        ("dense, 40% vol", WEEKLY_DAYS, EVENT_WEEKLY, 0.40,
         PALETTE["model"], "-", 1.8),
        ("dense, 20% vol", WEEKLY_DAYS, EVENT_WEEKLY, 0.20,
         PALETTE["alt"], "--", 1.2),
        ("quarterly, 20% vol", QUARTERLY_DAYS, EVENT_QUARTERLY, 0.20,
         PALETTE["data"], "-", 1.5),
    ]
    curves = {
        label: np.array([
            _recover(days, ev, sig, p) for p in PLANTED
        ])
        for label, days, ev, sig, _, _, _ in boards
    }
    width_dense = float(np.diff(WEEKLY_DAYS)[np.searchsorted(
        WEEKLY_DAYS, EVENT_WEEKLY) - 1])          # 28 days
    width_quart = float(np.diff(QUARTERLY_DAYS)[np.searchsorted(
        QUARTERLY_DAYS, EVENT_QUARTERLY) - 1])    # 91 days
    floor_dense = clock8.floor_days(width_dense)
    floor_quart = clock8.floor_days(width_quart)

    # Macro'd study facts.
    strong = curves["dense, 40% vol"]
    weak = curves["dense, 20% vol"]
    quart = curves["quarterly, 20% vol"]
    live_d = PLANTED >= floor_dense
    live_q = PLANTED >= floor_quart
    err = max(
        float(np.max(np.abs(strong[live_d] - PLANTED[live_d]))),
        float(np.max(np.abs(weak[live_d] - PLANTED[live_d]))),
        float(np.max(np.abs(quart[live_q] - PLANTED[live_q]))),
    )
    STORE.add("ident", "ClkIdentDenseWidthD", num(width_dense, 0),
              "width of the dense board's event-bearing interval (days)")
    STORE.add("ident", "ClkIdentQuartWidthD", num(width_quart, 0),
              "width of the quarterly board's event-bearing interval (days)")
    STORE.add("ident", "ClkIdentFloorDenseD", num(floor_dense, 2),
              "smallest event the rule reports on the dense board (days)")
    STORE.add("ident", "ClkIdentFloorQuartD", num(floor_quart, 2),
              "smallest event the rule reports on the quarterly board (days)")
    STORE.add("ident", "ClkIdentMaxErrD", f"{err:.1e}",
              "largest |recovered - planted| above the floors, all boards")
    STORE.add("ident", "ClkIdentVolDiffD",
              f"{float(np.max(np.abs(strong - weak))):.1e}",
              "largest difference between the 40% and 20% recoveries (days)")
    STORE.add("ident", "ClkIdentWallWidthD",
              num(FIXED_PLANT / clock8.MIN_REL_EXCESS, 0),
              "interval width beyond which a 2-day event is below the floor")
    # Flat input: exactly no events.
    t_flat = WEEKLY_DAYS / 365.0
    n_flat = clock8.detect(t_flat, 0.20**2 * t_flat)
    STORE.add("ident", "ClkIdentFlatDays", num(n_flat.sum(), 3),
              "days installed on a flat 20% ladder (exactly zero)")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) recovered vs planted.
    ax_a.plot([0, 10], [0, 10], color=PALETTE["muted"], lw=0.9, ls=":",
              label="truth")
    for label, _, _, _, color, ls, lw in boards:
        ax_a.plot(PLANTED, curves[label], color=color, lw=lw, ls=ls,
                  label=label)
    ax_a.axvline(floor_dense, color=PALETTE["alt"], lw=0.7, ls=":")
    ax_a.axvline(floor_quart, color=PALETTE["data"], lw=0.7, ls=":")
    figstyle.callout(ax_a, f"floor {floor_dense:.2f} d",
                     (floor_dense, 0.3), (0.4, 5.2))
    figstyle.callout(ax_a, f"floor {floor_quart:.2f} d",
                     (floor_quart, 0.3), (4.6, 1.2))
    ax_a.set_xlabel("planted event size  (extra days)")
    ax_a.set_ylabel("recovered size  (extra days)")
    ax_a.legend(loc="upper left", fontsize=7.0)
    figstyle.panel(ax_a, "a", "exact above the floor, zero below")

    # (b) the floor against the interval width.
    floors = np.array([clock8.floor_days(wd) for wd in WIDTHS])
    ax_b.plot(WIDTHS, floors, color=PALETTE["ink"], lw=1.5,
              label=r"floor $\max(1/2,\,0.03\,d)$")
    ax_b.axhline(FIXED_PLANT, color=PALETTE["muted"], lw=0.9, ls="--",
                 label="a 2-day event")
    for wd, fl, color, name in ((width_dense, floor_dense, PALETTE["alt"],
                                 "dense"),
                                (width_quart, floor_quart, PALETTE["data"],
                                 "quarterly")):
        ax_b.plot([wd], [fl], "o", ms=5.0, color=color, zorder=5)
        ax_b.annotate(name, (wd, fl), xytext=(wd + 3.0, fl - 0.45),
                      fontsize=7.0, color=color)
    wall = FIXED_PLANT / clock8.MIN_REL_EXCESS
    ax_b.axvline(wall, color=PALETTE["muted"], lw=0.7, ls=":")
    figstyle.callout(ax_b, f"2 days is under the floor\nbeyond {wall:.0f}-day intervals",
                     (wall, FIXED_PLANT), (8.0, 2.9))
    ax_b.set_xlabel("width of the bracketing interval  (days)")
    ax_b.set_ylabel("smallest reportable event  (days)")
    ax_b.set_ylim(0.0, 4.0)
    ax_b.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the wall is in the listing, not the vol")

    figstyle.save(fig, "fig_clk_ident")
    return (f"floors {floor_dense:.2f}/{floor_quart:.2f} d, "
            f"max err {err:.1e} d")
