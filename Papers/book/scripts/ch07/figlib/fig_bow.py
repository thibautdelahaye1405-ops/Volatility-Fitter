"""Figure 7.6: Chapter 6's residual bow, explained and removed."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data7  # first: extends sys.path to the ch03/ch06 figure libraries
import data6  # noqa: E402
import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num


def _deam_pass(K, C, P, S, t, F_carry):
    """One de-Americanization sweep of the whole board under a given carry.

    Returns (prem_call, prem_put): NaN where the tree found no root.
    """
    q = data7.carry_yield(F_carry, S, t)
    mids = np.concatenate([C, P])
    flags = np.concatenate([np.ones(K.size, bool), np.zeros(K.size, bool)])
    ks2 = np.concatenate([K, K])
    sig = tree.deamericanize_batch(mids, flags, ks2, S, t, data7.R_CONV, q,
                                   n=tree.N_BATCH)
    prem = tree.premium_batch(sig, flags, ks2, S, t, data7.R_CONV, q,
                              n=tree.N_BATCH)
    return prem[:K.size], prem[K.size:]


def fig_deam_bow() -> str:
    node = data7.running_node()
    K, C, P = data7.chain_mids(*data7.RUNNING)
    S, t = node.spot, node.t
    Pi = C - P

    # The naive line of Chapter 6, reproduced exactly (all pairs).
    F0, _, a0, b0 = data6.ols(K, Pi)
    resid_meas_all = Pi - (a0 + b0 * K)

    # Two passes of the loop: carry from the current forward estimate,
    # de-Americanize, refit the (European) line, repeat.
    prem_c1, prem_p1 = _deam_pass(K, C, P, S, t, F0)
    keep1 = np.isfinite(prem_c1) & np.isfinite(prem_p1)
    Pi1 = (C - prem_c1) - (P - prem_p1)
    F1, _, _, _ = data6.ols(K[keep1], Pi1[keep1])

    prem_c2, prem_p2 = _deam_pass(K, C, P, S, t, F1)
    keep2 = np.isfinite(prem_c2) & np.isfinite(prem_p2)
    Pi2 = (C - prem_c2) - (P - prem_p2)
    F2, _, a2, b2 = data6.ols(K[keep2], Pi2[keep2])
    resid_deam = Pi2 - (a2 + b2 * K)

    # Panel (a) compares shapes on ONE population: the pairs where both
    # legs inverted.  Both the measured observable and the model premium
    # difference are detrended by their own least-squares line on that
    # population (a line absorbs any affine part; Section 7.6).
    _, _, am, bm = data6.ols(K[keep2], Pi[keep2])
    resid_meas = Pi - (am + bm * K)
    diff = prem_c2 - prem_p2
    bd, ad = np.polyfit(K[keep2], diff[keep2], 1)
    pred_arch = diff - (ad + bd * K)
    match_rms = float(np.sqrt(np.mean(
        (resid_meas[keep2] - pred_arch[keep2])**2)))
    rms_before = float(np.sqrt(np.mean(resid_meas_all**2)))
    rms_after = float(np.sqrt(np.mean(resid_deam[keep2]**2)))
    F_res = node.forward
    gap_bp = 1e4 * (F2 / F_res - 1.0)
    pass_bp = 1e4 * abs(F2 / F1 - 1.0)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # ---- (a) measured residuals vs the tree's prediction
    ax_a.plot(K[keep2], resid_meas[keep2], ".", color=PALETTE["data"],
              ms=3.2, zorder=4, label="measured residuals (as fig. 6.1b)")
    ax_a.plot(K[keep2], pred_arch[keep2], "-", color=PALETTE["model"],
              lw=1.3, zorder=5, label="tree premium difference, detrended")
    ax_a.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_a.set_xlabel("strike $K$ (dollars)")
    ax_a.set_ylabel("residual (dollars)")
    ax_a.legend(loc="lower left", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the bow is the premium difference")

    # ---- (b) the de-Americanized line's residuals, and the roots
    ax_b.plot(K[keep2], resid_deam[keep2], ".", color=PALETTE["model"],
              ms=3.2, zorder=4)
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_b.axvline(F0, color=PALETTE["muted"], lw=0.9, ls="--", zorder=2)
    ax_b.axvline(F2, color=PALETTE["model"], lw=0.9, zorder=3)
    ax_b.axvline(F_res, color=PALETTE["ink"], lw=0.9, ls=":", zorder=3)
    lo = float(np.min(resid_deam[keep2]))
    figstyle.callout(ax_b,
                     f"naive forward {F0:.0f} (dashed);\n"
                     f"de-Americanized {F2:.0f} (blue) lands\n"
                     f"{abs(gap_bp):.0f} bp from the stored one (dotted)",
                     (F2, lo * 0.45), (float(K.min()) + 8.0, lo * 0.88))
    ax_b.set_xlabel("strike $K$ (dollars)")
    ax_b.set_ylabel("residual (dollars)")
    figstyle.panel(ax_b, "b", "after the subtraction the line is straight")

    figstyle.save(fig, "fig_deam_bow")

    STORE.add("bow", "DeamBowNPairs", str(K.size),
              "paired strikes on the running node (as in fig. 6.1)")
    STORE.add("bow", "DeamBowNKept", str(int(keep2.sum())),
              "pairs where both legs inverted (plateau lanes dropped)")
    STORE.add("bow", "DeamBowNDropped", str(int((~keep2).sum())),
              "pairs dropped: at least one leg on the intrinsic plateau")
    STORE.add("bow", "DeamBowMatchRmsDollars", num(match_rms, 2),
              "rms mismatch between measured residuals and the predicted"
              " arch (dollars)")
    STORE.add("bow", "DeamBowRmsBeforeDollars", num(rms_before, 2),
              "rms residual of the naive line (dollars; fig. 6.1's 2.97)")
    STORE.add("bow", "DeamBowRmsAfterDollars", num(rms_after, 2),
              "rms residual after de-Americanization (dollars)")
    STORE.add("bow", "DeamBowFNaive", num(F0, 2),
              "naive parity root (dollars)")
    STORE.add("bow", "DeamBowFDeam", num(F2, 2),
              "de-Americanized parity root after two passes (dollars)")
    STORE.add("bow", "DeamBowFResolved", num(F_res, 2),
              "the snapshot's stored resolved forward (dollars)")
    STORE.add("bow", "DeamBowGapToResolvedBp", num(abs(gap_bp), 0),
              "de-Americanized root vs stored forward (bp of forward)")
    STORE.add("bow", "DeamBowPassDeltaBp", num(pass_bp, 1),
              "movement of the root between pass 1 and pass 2 (bp)")
    STORE.add("bow", "DeamBowNaiveGapBp",
              num(1e4 * (F_res / F0 - 1.0), 0),
              "naive root vs stored forward (bp; fig. 6.1's 68)")
    return (f"F0 {F0:.2f} -> F2 {F2:.2f} (resolved {F_res:.2f}, "
            f"gap {gap_bp:+.0f} bp), rms {rms_before:.2f} -> {rms_after:.2f}")
