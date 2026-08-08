"""Figure 10.2 -- the activation gate and why a ridge cannot replace it.

Panel (a): the gate for three sharpness exponents; past the requirement the
prior weight is exactly zero.  Panel (b): the prior's share of the
posterior -- a fixed-precision ridge keeps a share everywhere; the gated
prior carries exactly nothing once the coordinate is identified.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import estimation
import figstyle
from figstyle import PALETTE
from macros import STORE, num

REQUIRED = 1.0
LAM = 1.0  # the ridge's fixed prior precision; also the gated budget scale


def fig_flt_gate() -> str:
    prec = np.linspace(0.0, 2.2, 441)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the gate for three exponents.
    for gamma, color in [(0.5, PALETTE["alt"]), (1.0, PALETTE["model"]),
                         (2.0, PALETTE["third"])]:
        ax_a.plot(prec, estimation.gate(prec, REQUIRED, gamma), color=color,
                  lw=1.5, label=rf"$\gamma={gamma:g}$")
    ax_a.axvline(REQUIRED, color=PALETTE["muted"], lw=0.9, ls=":")
    ax_a.annotate("required\nprecision", (REQUIRED, 0.78), xytext=(1.28, 0.80),
                  fontsize=7.5, color=PALETTE["muted"],
                  arrowprops={"arrowstyle": "->", "color": PALETTE["muted"],
                              "lw": 0.9})
    ax_a.axhspan(-0.02, 0.0, xmin=REQUIRED / 2.2, color=PALETTE["ink"],
                 alpha=0.0)
    ax_a.set_xlabel(r"identification precision $\mathcal{I}$ "
                    r"(units of $\mathcal{I}_{\mathrm{req}}$)")
    ax_a.set_ylabel("gate value")
    ax_a.set_ylim(-0.03, 1.05)
    ax_a.legend(loc="upper right")
    figstyle.panel(ax_a, "a", "the gate: a dead zone, not a small weight")

    # (b) the prior's share of the posterior.
    ridge_share = LAM / (LAM + prec)
    gated_share = np.where(
        prec + LAM * estimation.gate(prec, REQUIRED, 1.0) > 0,
        LAM * estimation.gate(prec, REQUIRED, 1.0)
        / (LAM * estimation.gate(prec, REQUIRED, 1.0) + prec),
        1.0,
    )
    ax_b.plot(prec, ridge_share, color=PALETTE["third"], lw=1.5, ls="--",
              label="ridge (fixed weight)")
    ax_b.plot(prec, gated_share, color=PALETTE["model"], lw=1.5,
              label="gated prior")
    ax_b.axvline(REQUIRED, color=PALETTE["muted"], lw=0.9, ls=":")
    i2 = int(np.argmin(np.abs(prec - 2.0)))
    figstyle.callout(
        ax_b, f"ridge still carries\n{100 * ridge_share[i2]:.0f}% here",
        (2.0, ridge_share[i2]), (1.35, 0.55),
    )
    figstyle.callout(
        ax_b, "gated: exactly 0", (1.45, 0.0), (1.42, 0.24),
    )
    ax_b.set_xlabel(r"identification precision $\mathcal{I}$ "
                    r"(units of $\mathcal{I}_{\mathrm{req}}$)")
    ax_b.set_ylabel("the prior's share of the posterior")
    ax_b.set_ylim(-0.03, 1.05)
    ax_b.legend(loc="upper right")
    figstyle.panel(ax_b, "b", "gating versus shrinkage")

    figstyle.save(fig, "fig_flt_gate")

    STORE.add("gate", "PriorGateRidgeSharePct", num(100 * ridge_share[i2], 0),
              "posterior share a unit-weight ridge carries at twice the "
              "required precision")
    return f"ridge share at 2x requirement: {100 * ridge_share[i2]:.0f}%"
