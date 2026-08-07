"""Figure 6.7: the borrow's two closed forms -- materiality against maturity,
and the identifiability floor that decides whether a read is a measurement."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.stats import norm

import figstyle
from figstyle import PALETTE
from macros import STORE, num

SIGMA = 0.20        # flat ATM vol of the illustration
N_PAIRS = 20        # paired strikes behind the floor formula
NOISE_BP = (10.0, 50.0)   # quote-noise levels, bp of spot
HTB = (100.0, 1000.0)     # typical hard-to-borrow range, bp per year


def _sens_bp(t: np.ndarray) -> np.ndarray:
    """ATM vol move per 100 bp of borrow (vol bp): t * profile / sqrt(tau)."""
    d_plus = 0.5 * SIGMA * np.sqrt(t)
    return 1e4 * 0.01 * t * norm.cdf(d_plus) / (norm.pdf(d_plus) * np.sqrt(t))


def _floor_bp(t: np.ndarray, noise_bp: float) -> np.ndarray:
    """Smallest resolvable borrow (bp): forward level noise divided by t."""
    return noise_bp * np.sqrt(2.0) / (np.sqrt(N_PAIRS) * t)


def fig_fwd_borrow() -> str:
    t = np.linspace(0.02, 2.0, 400)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    sens = _sens_bp(t)
    ax_a.plot(t, sens, color=PALETTE["model"], lw=1.3)
    for tm, label in ((0.25, "3m"), (1.0, "1y")):
        v = float(_sens_bp(np.array([tm]))[0])
        ax_a.plot([tm], [v], "o", ms=4.5, color=PALETTE["ink"])
        ax_a.annotate(f"{label}: {v:.0f} bp", (tm, v),
                      xytext=(tm + 0.06, v - 14), fontsize=7.5,
                      color=PALETTE["ink"])
    ax_a.set_xlabel("maturity $t$ (years)")
    ax_a.set_ylabel("ATM vol per 100 bp of borrow (vol bp)")
    figstyle.panel(ax_a, "a", "materiality: borrow is a smile input")

    for noise, color in zip(NOISE_BP, (PALETTE["model"], PALETTE["alt"])):
        ax_b.plot(t, _floor_bp(t, noise), color=color, lw=1.3,
                  label=f"{noise:.0f} bp quote noise")
    ax_b.axhspan(HTB[0], HTB[1], color=PALETTE["band"], alpha=0.7, lw=0,
                 zorder=0)
    ax_b.text(1.30, np.sqrt(HTB[0] * HTB[1]), "typical hard-to-borrow\nlevels",
              fontsize=7.5, color=PALETTE["muted"], va="center")
    ax_b.set_yscale("log")
    ax_b.set_xlabel("maturity $t$ (years)")
    ax_b.set_ylabel(r"identifiability floor $b_{\min}$ (bp)")
    ax_b.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "precision: the smallest readable borrow")

    figstyle.save(fig, "fig_fwd_borrow")

    q = np.array([0.25])
    y = np.array([1.0])
    wk = np.array([1.0 / 52.0])
    STORE.add("borrow", "FwdBorrowSigmaPct", num(100 * SIGMA, 0),
              "flat ATM vol of the borrow illustration (%)")
    STORE.add("borrow", "FwdBorrowNPairs", str(N_PAIRS),
              "paired strikes behind the floor formula")
    STORE.add("borrow", "FwdBorrowSensQBp", num(float(_sens_bp(q)[0]), 0),
              "ATM vol per 100 bp of borrow at three months (vol bp)")
    STORE.add("borrow", "FwdBorrowSensYBp", num(float(_sens_bp(y)[0]), 0),
              "ATM vol per 100 bp of borrow at one year (vol bp)")
    STORE.add("borrow", "FwdBorrowFloorQBp",
              num(float(_floor_bp(q, NOISE_BP[0])[0]), 0),
              "identifiability floor at three months, 10 bp noise (bp)")
    STORE.add("borrow", "FwdBorrowFloorYBp",
              num(float(_floor_bp(y, NOISE_BP[0])[0]), 1),
              "identifiability floor at one year, 10 bp noise (bp)")
    STORE.add("borrow", "FwdBorrowFloorWideYBp",
              num(float(_floor_bp(y, NOISE_BP[1])[0]), 0),
              "identifiability floor at one year, 50 bp noise (bp)")
    STORE.add("borrow", "FwdBorrowFloorWeekBp",
              num(float(_floor_bp(wk, NOISE_BP[0])[0]), 0),
              "identifiability floor at one week, 10 bp noise (bp)")
    return (f"sens 3m {float(_sens_bp(q)[0]):.0f} / 1y "
            f"{float(_sens_bp(y)[0]):.0f} bp; floor 1y "
            f"{float(_floor_bp(y, NOISE_BP[0])[0]):.1f} bp")
