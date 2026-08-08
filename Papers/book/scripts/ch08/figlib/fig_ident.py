"""F6 -- what the inverse problem can deliver: the planted-event study.

Synthetic boards whose truth is known: a flat clock volatility plus one
planted event, solved by the chapter's calibrator.
Panel (a): recovered vs planted size on three boards -- a weekly
single-name board (40%), the same board at index vol (20%), and a
quarterly index board (20%).  The l1 prior's shrinkage and the
materiality threshold are both visible.
Panel (b): recovered size of a fixed 2-day event as the board's
volatility varies -- the sigma^4 materiality wall.
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
PLANTED = np.arange(0.0, 10.01, 0.5)
FIXED_PLANT = 2.0
VOLS = np.linspace(0.10, 0.50, 33)


def _recover(days: np.ndarray, event_day: float, sigma: float,
             planted: float) -> float:
    """Plant one event on a flat-clock board and return the solved size."""
    t = days / 365.0
    tau_days = days + np.where(days >= event_day, planted, 0.0)
    w = sigma**2 * tau_days / 365.0
    N = clock8.solve(t, w)
    return float(N[np.searchsorted(days, event_day)])


def fig_clk_ident() -> str:
    boards = [
        ("dense, 40% vol", WEEKLY_DAYS, EVENT_WEEKLY, 0.40,
         PALETTE["model"], "-"),
        ("dense, 20% vol", WEEKLY_DAYS, EVENT_WEEKLY, 0.20,
         PALETTE["alt"], "-"),
        ("quarterly, 20% vol", QUARTERLY_DAYS, EVENT_QUARTERLY, 0.20,
         PALETTE["data"], "-"),
    ]
    curves = {
        label: np.array([
            _recover(days, ev, sig, p) for p in PLANTED
        ])
        for label, days, ev, sig, _, _ in boards
    }

    # Macro'd study facts.
    strong = curves["dense, 40% vol"]
    weak = curves["dense, 20% vol"]
    quart = curves["quarterly, 20% vol"]
    mask = PLANTED >= 2.0  # shrinkage measured where recovery is live
    STORE.add("ident", "ClkIdentShrinkStrongD",
              num(np.max(PLANTED[mask] - strong[mask]), 2),
              "max shrinkage, dense board at 40% vol (planted >= 2d)")
    STORE.add("ident", "ClkIdentShrinkWeakD",
              num(np.max(PLANTED[mask] - weak[mask]), 2),
              "max shrinkage, dense board at 20% vol (planted >= 2d)")
    blind = PLANTED[quart <= 0.0]
    STORE.add("ident", "ClkIdentBlindD",
              num(blind.max() if blind.size else 0.0, 1),
              "largest planted event the quarterly 20% board misses (days)")
    # Flat input: exactly no events.
    t_flat = WEEKLY_DAYS / 365.0
    n_flat = clock8.solve(t_flat, 0.20**2 * t_flat)
    STORE.add("ident", "ClkIdentFlatDays", num(n_flat.sum(), 3),
              "days installed on a flat 20% ladder (exactly zero)")

    # (b) the materiality wall for a fixed 2-day event.
    wall = {
        "weekly": np.array([
            _recover(WEEKLY_DAYS, EVENT_WEEKLY, s, FIXED_PLANT)
            for s in VOLS
        ]),
        "quarterly": np.array([
            _recover(QUARTERLY_DAYS, EVENT_QUARTERLY, s, FIXED_PLANT)
            for s in VOLS
        ]),
    }
    first_w = VOLS[np.argmax(wall["weekly"] > 0.0)]
    first_q = VOLS[np.argmax(wall["quarterly"] > 0.0)]
    STORE.add("ident", "ClkIdentWallWeeklyPct", num(first_w * 100, 0),
              "lowest vol at which the dense board sees a 2-day event (%)")
    STORE.add("ident", "ClkIdentWallQuarterlyPct", num(first_q * 100, 0),
              "lowest vol at which the quarterly board sees it (%)")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) recovered vs planted.
    ax_a.plot([0, 10], [0, 10], color=PALETTE["muted"], lw=0.9, ls="--",
              label="truth")
    for label, _, _, _, color, ls in boards:
        ax_a.plot(PLANTED, curves[label], color=color, lw=1.5, ls=ls,
                  label=label)
    ax_a.set_xlabel("planted event size  (extra days)")
    ax_a.set_ylabel("recovered size  (extra days)")
    ax_a.legend(loc="upper left")
    figstyle.panel(ax_a, "a", "recovered vs planted, three boards")

    # (b) the materiality wall.
    ax_b.axhline(FIXED_PLANT, color=PALETTE["muted"], lw=0.9, ls="--",
                 label="truth (2 days)")
    ax_b.plot(VOLS * 100, wall["weekly"], color=PALETTE["alt"], lw=1.5,
              label="dense board")
    ax_b.plot(VOLS * 100, wall["quarterly"], color=PALETTE["data"], lw=1.5,
              label="quarterly board")
    ax_b.set_xlabel("board volatility  (%)")
    ax_b.set_ylabel("recovered size  (extra days)")
    ax_b.legend(loc="upper left")
    figstyle.panel(ax_b, "b", "a 2-day event vs the board's vol")

    figstyle.save(fig, "fig_clk_ident")
    return (f"shrink {np.max(PLANTED[mask]-weak[mask]):.2f}d, "
            f"quarterly blind to {blind.max() if blind.size else 0:.1f}d")
