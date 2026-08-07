"""F3 -- one free dial (section 9.3).

Panel (a): the transport built in two moves at R = 2 under the fan move --
the re-indexed curve sigma_old(k + H) (dashed), then one uniform level
(R-1) s0 H on top (solid).  Panel (b): the exact ATM response of the
transport against the move for the three regimes, with the linear law
R s0 H dotted -- the common bend is the smile's own curvature, the
second-order term the one-dial transport does not model.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
from figstyle import PALETTE, REGIME_COLORS, REGIME_NAMES
from macros import STORE, num

_H = data9.H_FAN
_SPAN = (-0.20, 0.12)
_H_MAX = 0.06


def fig_ssr_dial() -> str:
    sm = data9.hero()

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) re-index, then one level ------------------------------------------
    ax = axes[0]
    k = np.linspace(*_SPAN, 401)
    level = (2.0 - 1.0) * sm.s0 * _H
    ax.plot(k, 100.0 * sm.iv(k), color=PALETTE["data"], lw=1.7,
            label="today", zorder=3)
    ax.plot(k, 100.0 * sm.iv(k + _H), color=PALETTE["muted"], lw=1.2,
            ls="--", label=r"re-index $\sigma_{\rm old}(k+H)$", zorder=3)
    ax.plot(k, 100.0 * (sm.iv(k + _H) + level), color=REGIME_COLORS[2.0],
            lw=1.5, label=r"+ level $(\mathcal{R}-1)s_0H$", zorder=4)
    for k_arrow in (-0.12, -0.02, 0.07):
        base = float(sm.iv(np.array([k_arrow + _H]))[0])
        ax.annotate(
            "", xy=(k_arrow, 100.0 * (base + level)),
            xytext=(k_arrow, 100.0 * base),
            arrowprops={"arrowstyle": "->", "color": PALETTE["ink"],
                        "lw": 0.9},
        )
    ax.set_xlabel(r"log-moneyness $k$ (prevailing forward)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(
        ax, "a",
        rf"the two moves ($\mathcal{{R}}=2$, $H={100*_H:+.0f}\%$)")

    # (b) ATM response vs the move ------------------------------------------
    ax = axes[1]
    h_grid = np.linspace(-_H_MAX, _H_MAX, 121)
    atm0 = sm.atm_vol
    for regime in data9.REGIMES:
        exact = sm.iv(h_grid) + (regime - 1.0) * sm.s0 * h_grid - atm0
        ax.plot(100.0 * h_grid, 100.0 * exact,
                color=REGIME_COLORS[regime], lw=1.4,
                label=REGIME_NAMES[regime])
        ax.plot(100.0 * h_grid, 100.0 * regime * sm.s0 * h_grid,
                color=REGIME_COLORS[regime], lw=0.8, ls=":", alpha=0.8)
    bend = float(sm.iv(np.array([-_H_MAX]))[0] - atm0 + sm.s0 * _H_MAX)
    figstyle.callout(
        ax, "the common bend:\nthe smile's own curvature",
        xy=(-100.0 * _H_MAX * 0.97,
            100.0 * (float(sm.iv(np.array([-_H_MAX]))[0]) - atm0
                     - sm.s0 * _H_MAX)),
        xytext=(-5.6, 100.0 * 2.0 * abs(sm.s0) * _H_MAX * 0.45),
    )
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.axvline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.set_xlabel(r"forward move $H$ (%)")
    ax.set_ylabel(r"ATM vol change $\sigma_{\rm new}(0)-\sigma_{\rm old}(0)$ (pts)")
    ax.legend(loc="lower left", fontsize=7.0)
    figstyle.panel(ax, "b", r"ATM response: slope $\mathcal{R}\,s_0$")

    figstyle.save(fig, "fig_ssr_dial")

    STORE.add("dial", "SsrDialLevelBp", f"{abs(level)*1e4:.0f}",
              "the uniform level (R-1)s0H at the fan move for R=2, vol bp")
    STORE.add("dial", "SsrDialAtmMoveBp",
              f"{abs(2.0*sm.s0*_H)*1e4:.0f}",
              "linear ATM response R s0 H at the fan move for R=2, vol bp")
    STORE.add("dial", "SsrDialBendBp", num(abs(bend) * 1e4, 0),
              "second-order ATM bend at H=-6% (same for every regime), "
              "vol bp")
    return f"level {abs(level)*1e4:.0f} bp, bend {abs(bend)*1e4:.0f} bp"
