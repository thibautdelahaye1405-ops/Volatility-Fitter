"""Figure 10.5 -- the case file through the scalar filter update.

The chapter's running vignette: a transported prediction meets a data-only
morning read whose curvature was bent by one stale strike.  Per handle, the
posterior lands on the prediction-to-observation segment exactly at its
gain; the level moves to the market, the manufactured curvature kink is
barely admitted.  All numbers computed by estimation.filter_update.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import estimation
import figstyle
from figstyle import PALETTE
from macros import STORE, num

# The vignette's stated moments (level in vol, skew and curvature unitless).
HANDLES = ("level", "skew", "curvature")
M_PRED = np.array([0.200, -0.35, 0.10])
SD_PRED = np.array([0.0030, 0.08, 0.05])
Z_OBS = np.array([0.204, -0.37, 0.55])
SD_OBS = np.array([0.0015, 0.05, 0.30])


def fig_flt_update() -> str:
    posts, vposts, gains = [], [], []
    for i in range(3):
        m, v, g = estimation.filter_update(
            M_PRED[i], SD_PRED[i] ** 2, Z_OBS[i], SD_OBS[i] ** 2)
        posts.append(m)
        vposts.append(v)
        gains.append(g)
    posts = np.asarray(posts)
    gains = np.asarray(gains)
    sd_posts = np.sqrt(np.asarray(vposts))

    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=figstyle.ROW2, width_ratios=[1.5, 1.0])

    # (a) each handle on its normalized prediction->observation segment:
    # 0 = prediction, 1 = observation; the posterior sits at the gain.
    y = np.arange(3)[::-1]
    ax_a.hlines(y, 0.0, 1.0, color=PALETTE["grid"], lw=2.5, zorder=1)
    ax_a.plot(np.zeros(3), y, "o", ms=6, color=PALETTE["alt"], zorder=3,
              label="prediction")
    ax_a.plot(np.ones(3), y, "s", ms=6, color=PALETTE["data"], zorder=3,
              label="observation")
    ax_a.plot(gains, y, "D", ms=6, color=PALETTE["model"], zorder=4,
              label="posterior")
    for i, name in enumerate(HANDLES):
        ax_a.annotate(name, (-0.06, y[i]), ha="right", va="center",
                      fontsize=8.5)
        ax_a.annotate(rf"$\mathcal{{K}}={gains[i]:.2f}$",
                      (gains[i], y[i] + 0.22), ha="center", fontsize=7.5,
                      color=PALETTE["model"])
    ax_a.set_xlim(-0.42, 1.12)
    ax_a.set_ylim(-1.35, 2.7)
    ax_a.set_yticks([])
    ax_a.set_xlabel("position between prediction (0) and observation (1)")
    ax_a.legend(loc="lower center", fontsize=7.0, ncol=3)
    figstyle.panel(ax_a, "a", "the posterior sits at the gain")

    # (b) the computed gains.
    ax_b.bar([h.replace("curvature", "curv.") for h in HANDLES], gains,
             color=[PALETTE["model"], PALETTE["model"], PALETTE["model"]],
             width=0.55, alpha=0.9)
    for i, g in enumerate(gains):
        ax_b.annotate(f"{g:.2f}", (i, g + 0.03), ha="center", fontsize=8.0)
    ax_b.set_ylim(0, 1.0)
    ax_b.set_ylabel(r"gain $\mathcal{K}$")
    figstyle.panel(ax_b, "b", "trust, computed per handle")

    figstyle.save(fig, "fig_flt_update")

    STORE.add("update", "FiltCaseGainLevel", num(gains[0], 2),
              "computed gain of the ATM level")
    STORE.add("update", "FiltCaseGainSkew", num(gains[1], 2),
              "computed gain of the skew")
    STORE.add("update", "FiltCaseGainCurv", num(gains[2], 3),
              "computed gain of the curvature")
    STORE.add("update", "FiltCasePostLevelPct", num(1e2 * posts[0], 2),
              "posterior ATM level (%)")
    STORE.add("update", "FiltCasePostSkew", num(posts[1], 3),
              "posterior skew")
    STORE.add("update", "FiltCasePostCurv", num(posts[2], 3),
              "posterior curvature")
    STORE.add("update", "FiltCasePostSdLevelBp", num(1e4 * sd_posts[0], 0),
              "posterior ATM sd (vol bp)")
    return ("gains " + "/".join(f"{g:.3f}" for g in gains)
            + f"; post level {1e2 * posts[0]:.2f}%")
