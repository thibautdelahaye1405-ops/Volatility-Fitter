"""F2 -- the two signs on one move (section 9.2).

One full-width panel: the frozen hero smile before and after a +4% forward
move under sticky-strike.  A fixed strike keeps its vol but its LABEL
slides to k - H (filled to open marker, the quote rule); the new curve at
any k READS the old curve at k + H (the curve rule).  Opposite directions,
both correct.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
from figstyle import PALETTE
from macros import STORE, num

_H = +0.04
_SPAN = (-0.15, 0.10)
_K_QUOTE = 0.02      # the tracked fixed strike (today's label)
_K_READ = -0.08      # where the curve rule is illustrated


def fig_ssr_signs() -> str:
    sm = data9.hero()

    fig, ax = plt.subplots(figsize=figstyle.ONE)
    k_old = np.linspace(*_SPAN, 401)
    ax.plot(k_old, 100.0 * sm.iv(k_old), color=PALETTE["data"], lw=1.7,
            label="today's curve", zorder=3)
    k_new = np.linspace(_SPAN[0] - _H, _SPAN[1] - _H, 401)
    ax.plot(k_new, 100.0 * sm.iv(k_new + _H), color=PALETTE["model"],
            lw=1.5, label=f"after a {100*_H:+.0f}% move (sticky-strike)",
            zorder=3)

    # The quote rule: same vol, label slides left to k - H.
    vol_q = float(sm.iv(np.array([_K_QUOTE]))[0])
    ax.plot([_K_QUOTE], [100.0 * vol_q], "o", ms=5.5,
            color=PALETTE["data"], zorder=5)
    ax.plot([_K_QUOTE - _H], [100.0 * vol_q], "o", ms=5.5, mfc="white",
            mec=PALETTE["model"], mew=1.2, zorder=5)
    ax.annotate(
        "", xy=(_K_QUOTE - _H + 0.004, 100.0 * vol_q),
        xytext=(_K_QUOTE - 0.004, 100.0 * vol_q),
        arrowprops={"arrowstyle": "->", "color": PALETTE["ink"], "lw": 1.1},
    )
    ax.annotate(
        "the quote rule:\nsame vol, new label $k-H$",
        xy=(_K_QUOTE - 0.5 * _H, 100.0 * vol_q + 0.10), ha="center",
        va="bottom", fontsize=7.5, color=PALETTE["ink"],
    )

    # The curve rule: the new curve at k reads the old curve at k + H.
    vol_r = float(sm.iv(np.array([_K_READ + _H]))[0])
    ax.plot([_K_READ + _H], [100.0 * vol_r], "s", ms=4.5,
            color=PALETTE["data"], zorder=5)
    ax.plot([_K_READ], [100.0 * vol_r], "s", ms=4.5, mfc="white",
            mec=PALETTE["model"], mew=1.2, zorder=5)
    ax.annotate(
        "", xy=(_K_READ + 0.004, 100.0 * vol_r),
        xytext=(_K_READ + _H - 0.004, 100.0 * vol_r),
        arrowprops={"arrowstyle": "->", "color": PALETTE["muted"], "lw": 1.1,
                    "linestyle": "--"},
    )
    ax.annotate(
        "the curve rule:\nnew curve at $k$ reads old at $k+H$",
        xy=(_K_READ + 0.5 * _H, 100.0 * vol_r - 0.16), ha="center",
        va="top", fontsize=7.5, color=PALETTE["muted"],
    )

    ax.set_xlabel(r"log-moneyness $k$ (prevailing forward)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(loc="upper right", fontsize=7.5)
    figstyle.save(fig, "fig_ssr_signs")

    STORE.add("signs", "SsrSignMovePct", f"{100*_H:.0f}",
              "the sign figure's move, % (up)")
    STORE.add("signs", "SsrSignQuoteVolPct", num(100.0 * vol_q, 1),
              "vol of the tracked fixed strike, %")
    return f"quote {_K_QUOTE:+.2f} -> {_K_QUOTE - _H:+.2f}"
