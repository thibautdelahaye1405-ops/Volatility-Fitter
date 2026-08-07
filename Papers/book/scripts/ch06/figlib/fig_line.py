"""Figure 6.1: the parity line on the real running node, and its residuals."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data6
import figstyle
from figstyle import PALETTE
from macros import STORE, num


def fig_fwd_line() -> str:
    node = data6.running_node()
    K, Pi = data6.chain_pairs(*data6.RUNNING)
    F_hat, D_hat, a, b = data6.ols(K, Pi)
    r_hat = -np.log(D_hat) / node.t
    resid = Pi - (a + b * K)
    rms = float(np.sqrt(np.mean(resid**2)))
    span = float(Pi.max() - Pi.min())
    F_res = node.forward  # the reference implementation's resolved forward
    gap_bp = 1e4 * (F_res / F_hat - 1.0)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the observable is one straight line in strike.
    ax_a.plot(K, Pi, ".", color=PALETTE["data"], ms=3.2, zorder=4,
              label=r"quoted $\Pi(K)=\mathsf{C}-\mathsf{P}$")
    kk = np.array([K.min(), K.max()])
    ax_a.plot(kk, a + b * kk, color=PALETTE["model"], lw=1.2, zorder=3,
              label="least-squares line")
    ax_a.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_a.plot([F_hat], [0.0], marker="o", ms=5.0, mfc="none",
              mec=PALETTE["ink"], mew=1.1, zorder=5)
    figstyle.callout(ax_a, r"root $=\hat F$", (F_hat, 0.0),
                     (F_hat - 190.0, -95.0))
    ax_a.set_xlabel("strike $K$ (dollars)")
    ax_a.set_ylabel(r"$\Pi(K)$ (dollars)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the parity line (SPY December 2026)")

    # (b) the residuals: dollar-scale, one-signed arch -- not noise.
    ax_b.plot(K, resid, ".", color=PALETTE["data"], ms=3.2, zorder=4)
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_b.axvline(F_hat, color=PALETTE["muted"], lw=0.9, ls="--", zorder=2)
    ax_b.axvline(F_res, color=PALETTE["ink"], lw=0.9, zorder=2)
    top = float(resid.max())
    figstyle.callout(ax_b,
                     "naive root $\\hat F$ (dashed) and\n"
                     f"resolved $F$: {gap_bp:.0f} bp apart",
                     (F_hat, -3.4), (K.min() + 12.0, -4.5))
    figstyle.callout(ax_b, "the bow: early exercise\n(Chapter 7)",
                     (float(K[np.argmax(resid)]), top),
                     (K.min() + 30.0, top - 1.1))
    ax_b.set_xlabel("strike $K$ (dollars)")
    ax_b.set_ylabel("residual (dollars)")
    figstyle.panel(ax_b, "b", "residuals: structured, not noisy")

    figstyle.save(fig, "fig_fwd_line")

    STORE.add("line", "FwdLineNPairs", str(K.size),
              "paired strikes on the running node's raw chain")
    STORE.add("line", "FwdLineSpanDollars", num(span, 0),
              "range of the observable Pi across the board (dollars)")
    STORE.add("line", "FwdLineRmsDollars", num(rms, 2),
              "rms residual of the naive parity line (dollars)")
    STORE.add("line", "FwdLineResidMaxDollars", num(float(np.abs(resid).max()), 1),
              "largest single residual of the naive line (dollars)")
    STORE.add("line", "FwdLineStraightPct", num(100.0 * rms / span, 2),
              "rms residual as a percentage of the observable's range")
    STORE.add("line", "FwdLineFNaive", num(F_hat, 2),
              "naive whole-chain parity root (dollars)")
    STORE.add("line", "FwdLineFResolved", num(F_res, 2),
              "the reference implementation's resolved forward (dollars)")
    STORE.add("line", "FwdLineGapBp", num(gap_bp, 0),
              "resolved-minus-naive forward gap (bp of forward)")
    STORE.add("line", "FwdLineRateNaivePct", num(100.0 * r_hat, 2),
              "implied rate of the naive slope (percent)")
    STORE.add("line", "FwdLineSpotDollars", num(node.spot, 2),
              "SPY spot on the snapshot date (dollars)")
    STORE.add("line", "FwdLinePiMaxDollars", num(float(Pi.max()), 0),
              "largest portfolio price on the board (dollars)")
    STORE.add("line", "FwdLinePiMinAbsDollars", num(abs(float(Pi.min())), 0),
              "magnitude of the most negative portfolio price (dollars)")
    STORE.add("line", "FwdLineGapDollars", num(F_res - F_hat, 1),
              "resolved-minus-naive forward gap (dollars)")
    return f"F_hat {F_hat:.2f} vs resolved {F_res:.2f} ({gap_bp:+.0f} bp)"
