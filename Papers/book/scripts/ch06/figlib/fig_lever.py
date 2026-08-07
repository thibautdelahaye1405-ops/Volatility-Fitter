"""Figure 6.4: the lever-arm identity -- three level estimators under an
imposed discount error, on a deliberately asymmetric board."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data6
import figstyle
from figstyle import PALETTE
from macros import STORE, num

KERNEL_H = 0.10  # ATM kernel width in log-moneyness (centered at spot)


def _estimators(bd: data6.Board):
    """Three level readings of F at a possibly wrong discount D'."""
    Pi = bd.Pi_exact  # noiseless: the figure isolates the identity
    mu = np.exp(-0.5 * (np.log(bd.K / bd.S) / KERNEL_H) ** 2)
    mu = mu / mu.sum()

    def naive(D2: float) -> float:      # intercept-over-slope: a = D F exactly
        return bd.D * bd.F / D2

    def uniform(D2: float) -> float:
        return float(np.mean(bd.K + Pi / D2))

    def kernel(D2: float) -> float:
        return float(np.sum(mu * (bd.K + Pi / D2)))

    kbar_mu = float(np.sum(mu * bd.K))
    return (naive, uniform, kernel), kbar_mu


def fig_fwd_lever() -> str:
    bd = data6.board(k_lo=85.0, k_hi=140.0, tick=0.0)  # asymmetric, exact
    (naive, uniform, kernel), kbar_mu = _estimators(bd)
    kbar = float(np.mean(bd.K))

    dr = np.linspace(-0.02, 0.02, 41)
    D2 = bd.D * np.exp(-dr * bd.t)
    curves = {
        "intercept / slope": (naive, PALETTE["model"], -bd.F * (0.0 - 1.0)),
        "uniform level mean": (uniform, PALETTE["alt"], kbar - bd.F),
        "spot-kernel level mean": (kernel, PALETTE["third"], kbar_mu - bd.F),
    }

    fig, (ax_a, ax_b) = plt.subplots(
        1, 2, figsize=figstyle.ROW2, gridspec_kw={"width_ratios": [1.6, 1.0]}
    )

    slopes_bp = {}
    for name, (est, color, _) in curves.items():
        err = np.array([1e4 * (est(d) / bd.F - 1.0) for d in D2])
        ax_a.plot(100 * dr, err, color=color, lw=1.3, label=name)
        # bp of forward error per +1% of imposed rate error (measured slope)
        slopes_bp[name] = float(np.polyfit(100 * dr, err, 1)[0])
    # the identity, evaluated at a few points for the uniform estimator
    pick = dr[::8]
    ident = [1e4 * (1.0 - bd.D / (bd.D * np.exp(-x * bd.t))) * (kbar - bd.F)
             / bd.F for x in pick]
    ax_a.plot(100 * pick, ident, "o", ms=4.0, mfc="none",
              mec=PALETTE["ink"], mew=1.0, zorder=5,
              label="lever identity (uniform)")
    ax_a.set_xlabel("imposed rate error (%)")
    ax_a.set_ylabel("transmitted forward error (bp)")
    ax_a.legend(loc="upper left", fontsize=7.0)
    figstyle.panel(ax_a, "a", "what a wrong discount does to each estimator")

    # (b) the lever arms themselves.
    names = ["intercept /\nslope", "uniform\nmean", "spot-kernel\nmean"]
    levers = [bd.F, abs(kbar - bd.F), abs(kbar_mu - bd.F)]
    colors = [PALETTE["model"], PALETTE["alt"], PALETTE["third"]]
    bars = ax_b.bar(names, levers, color=colors, width=0.62)
    ax_b.set_yscale("log")
    ax_b.set_ylabel(r"lever arm $|\bar K_\mu - F|$ (dollars)")
    for bar, v in zip(bars, levers):
        ax_b.text(bar.get_x() + bar.get_width() / 2, v * 1.15, f"{v:.1f}",
                  ha="center", va="bottom", fontsize=7.5)
    ax_b.grid(axis="x", visible=False)
    figstyle.panel(ax_b, "b", "the lever arm of each")

    figstyle.save(fig, "fig_fwd_lever")

    STORE.add("lever", "FwdLeverNaiveBpPerPct",
              num(abs(slopes_bp["intercept / slope"]), 1),
              "forward error per 1% rate error, intercept-over-slope (bp)")
    STORE.add("lever", "FwdLeverUnifBpPerPct",
              num(abs(slopes_bp["uniform level mean"]), 1),
              "forward error per 1% rate error, uniform level mean (bp)")
    STORE.add("lever", "FwdLeverKernBpPerPct",
              num(abs(slopes_bp["spot-kernel level mean"]), 2),
              "forward error per 1% rate error, spot-kernel level mean (bp)")
    STORE.add("lever", "FwdLeverKbarDollars", num(kbar, 1),
              "mean strike of the asymmetric board (dollars)")
    STORE.add("lever", "FwdLeverKbarKernDollars", num(kbar_mu, 1),
              "kernel-weighted mean strike (dollars)")
    STORE.add("lever", "FwdLeverFwdDollars", num(bd.F, 1),
              "true forward of the asymmetric board (dollars)")
    STORE.add("lever", "FwdLeverUnifLeverDollars", num(abs(kbar - bd.F), 1),
              "lever arm of the uniform level mean (dollars)")
    STORE.add("lever", "FwdLeverKernLeverDollars", num(abs(kbar_mu - bd.F), 1),
              "lever arm of the spot-kernel level mean (dollars)")
    return (f"slopes bp/%: naive {slopes_bp['intercept / slope']:.1f}, "
            f"uniform {slopes_bp['uniform level mean']:.1f}, "
            f"kernel {slopes_bp['spot-kernel level mean']:.2f}")
