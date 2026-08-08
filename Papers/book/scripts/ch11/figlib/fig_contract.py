"""F2: the contract -- amplitude and trust are separate dials.

The clean synthetic ladder (3M / 6M / 1Y, variance times 0.25 / 0.5 / 1.0),
6M lit at +1 vol point.  The calendar amplitudes are the maturity ratios:
the 3M receiver hears beta 2, the 1Y node is tied by the (6M <- 1Y) factor
at beta 2, so its implied move is +0.5.  Sweeping the relation precision
across three decades moves the posterior means not at all; the bands fall
as the inverse square root.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import solver
from figstyle import PALETTE, panel
from macros import STORE, sci

TAUS = {"3M": 0.25, "6M": 0.5, "1Y": 1.0}
CLAMP_VAR = 1e-8          # the lit node is clamped (certified fresh print)


def _solve(p: float):
    prob = solver.Problem(n=3)          # order: 3M, 6M, 1Y
    prob.edge(0, 1, p, TAUS["6M"] / TAUS["3M"])   # 3M <- 6M, beta 2
    prob.edge(1, 2, p, TAUS["1Y"] / TAUS["6M"])   # 6M <- 1Y, beta 2
    prob.observe(1, 1.0, CLAMP_VAR)
    return solver.solve(prob)


def fig_gr_contract() -> str:
    ps = np.logspace(0, 3, 25)          # vol-points^-2
    m3, m1y, s3, s1y = [], [], [], []
    for p in ps:
        post = _solve(p)
        m3.append(post.mean[0]), m1y.append(post.mean[2])
        s3.append(post.sd()[0]), s1y.append(post.sd()[2])
    m3, m1y, s3, s1y = map(np.asarray, (m3, m1y, s3, s1y))

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax = axes[0]
    ax.semilogx(ps, m3, color=PALETTE["model"], label="3M (amplitude 2)")
    ax.semilogx(ps, m1y, color=PALETTE["alt"], label="1Y (amplitude 1/2)")
    ax.axhline(2.0, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.axhline(0.5, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.set_ylim(0.0, 2.4)
    ax.set_xlabel(r"relation precision $p$ (vol pts$^{-2}$)")
    ax.set_ylabel("posterior mean (vol pts)")
    ax.legend(loc="center right")
    panel(ax, "a", "the mean ignores the trust dial")

    ax = axes[1]
    ax.loglog(ps, s3, color=PALETTE["model"], label="3M")
    ax.loglog(ps, s1y, color=PALETTE["alt"], label="1Y")
    ax.loglog(ps, 1.0 / np.sqrt(ps), color=PALETTE["ink"], lw=0.8, ls=":",
              label=r"$1/\sqrt{p}$")
    ax.set_xlabel(r"relation precision $p$ (vol pts$^{-2}$)")
    ax.set_ylabel("posterior sd (vol pts)")
    ax.legend(loc="lower left")
    panel(ax, "b", "the band is what trust buys")

    figstyle.save(fig, "fig_gr_contract")

    # Locks: the means are the configured amplitudes across the whole sweep.
    STORE.add("contract", "GrContractFlat",
              sci(max(np.abs(m3 - 2.0).max(), np.abs(m1y - 0.5).max()), 1),
              "max deviation of the swept posterior means from +2.00 / +0.50")
    ratio = s3 / s1y
    STORE.add("contract", "GrContractSdRatio",
              f"{ratio.mean():.2f}",
              "measured 3M/1Y posterior sd ratio (the beta-squared units law)")
    return "contract sweep locked"
