"""F5: the anchor and the corroboration law.

A receiver hears k agreeing clamped sources at +1, all at precision p and
beta one, against a zero-innovation anchor of precision kappa.  The
transfer is kp/(kappa + kp): one source transfers p/(kappa+p), and every
independent corroborating source lifts the transfer toward one.  The
curves are the law; the dots are the production of this chapter's solver.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import solver
from figstyle import PALETTE, panel
from macros import STORE, sci

P = 1.0
KAPPAS = [0.0, 1.0, 3.0]          # kappa / p
COLORS = ["ink", "model", "third"]
CLAMP_VAR = 1e-8


def _transfer(k: int, kappa: float) -> float:
    prob = solver.Problem(n=k + 1)
    for s in range(1, k + 1):
        prob.edge(0, s, P, 1.0)
        prob.observe(s, 1.0, CLAMP_VAR)
    prob.kappa = np.array([kappa] + [0.0] * k)
    return float(solver.solve(prob).mean[0])


def fig_gr_anchor() -> str:
    fig, ax = plt.subplots(figsize=figstyle.ONE)
    ks = np.arange(1, 6)
    dev = 0.0
    for kappa, cname in zip(KAPPAS, COLORS):
        law = ks * P / (kappa + ks * P)
        solved = np.array([_transfer(int(k), kappa) for k in ks])
        dev = max(dev, float(np.abs(solved - law).max()))
        kk = np.linspace(0.75, 5.25, 100)
        ax.plot(kk, kk * P / (kappa + kk * P), color=PALETTE[cname], lw=1.2)
        ax.plot(ks, solved, "o", color=PALETTE[cname], ms=5,
                label=rf"$\kappa/p={kappa:g}$")
    ax.axhline(1.0, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.set_xticks(ks)
    ax.set_xlabel("number of agreeing corroborating sources")
    ax.set_ylabel("transfer per unit message")
    ax.set_ylim(0.0, 1.08)
    ax.legend(loc="lower right")
    figstyle.callout(
        ax, "one source: 1/4;  two: 2/5;  corroboration climbs",
        xy=(2.0, 2.0 / 5.0), xytext=(2.4, 0.18))
    figstyle.save(fig, "fig_gr_anchor")

    STORE.add("anchor", "GrAnchorLawGap", sci(dev, 1),
              "max gap between the solver's transfer and kp/(kappa+kp)")
    return "corroboration law locked"
