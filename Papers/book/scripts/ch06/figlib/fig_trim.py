"""Figure 6.3: the residual trim catching one stale quote -- and the masking
variant (coherent staleness) it cannot catch, quoted as macros in the text."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data6
import figstyle
from figstyle import PALETTE
from macros import STORE, num

STALE_DOLLARS = 1.20   # the staged stale deep put: mid marked this much high
STALE_STRIKE = 75.0
MASK_DR = 0.02         # coherent variant: the put wing quotes a carry off by this
MASK_WING = 80.0       # ... on every strike at or below this


def _staged_board() -> tuple[data6.Board, np.ndarray]:
    bd = data6.board()
    pi = bd.Pi.copy()
    pi[bd.K == STALE_STRIKE] -= STALE_DOLLARS  # put mid too HIGH -> Pi too low
    return bd, pi


def _masked_board() -> tuple[data6.Board, np.ndarray, np.ndarray]:
    """The put wing re-marked at a coherently wrong carry (same D', F')."""
    bd = data6.board()
    r2, t = bd.r + MASK_DR, bd.t
    D2 = np.exp(-r2 * t)
    F2 = bd.S * np.exp((r2 - bd.qd) * t)
    pi = bd.Pi.copy()
    wing = bd.K <= MASK_WING
    pi[wing] = np.round((D2 * (F2 - bd.K[wing])) / 0.01) * 0.01
    return bd, pi, wing


def fig_fwd_trim() -> str:
    bd, pi = _staged_board()
    F_raw, D_raw, a_raw, b_raw = data6.ols(bd.K, pi)
    r_raw = -np.log(D_raw) / bd.t
    F_trim, D_trim, keep = data6.trim_fit(bd.K, pi)
    a_t = D_trim * F_trim
    resid_t = pi - (a_t - D_trim * bd.K)
    scale = max(1.4826 * np.median(np.abs(resid_t[keep])), 0.01)
    n_sig = float(np.abs(resid_t[~keep]).max() / scale)

    raw_err = 1e4 * (F_raw / bd.F - 1.0)
    trim_err = 1e4 * (F_trim / bd.F - 1.0)

    # The masking variant: numbers only (quoted in the text).
    bdm, pim, wing = _masked_board()
    F_m, D_m, keep_m = data6.trim_fit(bdm.K, pim)
    r_m = -np.log(D_m) / bdm.t
    mask_out = int((~keep_m).sum())
    mask_err = 1e4 * (F_m / bdm.F - 1.0)

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the board with one stale deep put; raw vs trimmed line.
    stale = ~keep
    ax_a.plot(bd.K[keep], pi[keep], ".", color=PALETTE["data"], ms=3.4,
              zorder=4, label="quotes")
    ax_a.plot(bd.K[stale], pi[stale], "o", ms=6.0, mfc="none",
              mec=PALETTE["ink"], mew=1.1, zorder=5, label="stale put")
    kk = np.array([bd.K.min(), bd.K.max()])
    ax_a.plot(kk, a_t - D_trim * kk, color=PALETTE["model"], lw=1.2,
              zorder=3, label="trimmed fit")
    ax_a.set_xlabel("strike $K$ (dollars)")
    ax_a.set_ylabel(r"$\Pi(K)$ (dollars)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "one stale deep put on the board")

    # (b) residuals against the trimmed fit, with the +-4 sigma-hat band.
    ax_b.axhspan(-4 * scale, 4 * scale, color=PALETTE["band"], alpha=0.7,
                 lw=0, zorder=0, label=r"$\pm4\hat\sigma$ band")
    ax_b.plot(bd.K[keep], resid_t[keep], ".", color=PALETTE["data"], ms=3.4,
              zorder=4)
    ax_b.plot(bd.K[stale], resid_t[stale], "o", ms=6.0, mfc="none",
              mec=PALETTE["ink"], mew=1.1, zorder=5)
    figstyle.callout(ax_b, rf"$\approx{n_sig:.0f}\,\hat\sigma$ out",
                     (STALE_STRIKE, float(resid_t[stale][0]) + 0.05),
                     (STALE_STRIKE + 12.0, float(resid_t[stale][0]) + 0.35))
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.7, zorder=1)
    ax_b.set_xlabel("strike $K$ (dollars)")
    ax_b.set_ylabel("residual (dollars)")
    ax_b.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "residuals to the trimmed fit")

    figstyle.save(fig, "fig_fwd_trim")

    STORE.add("trim", "FwdTrimStaleDollars", num(STALE_DOLLARS, 2),
              "size of the staged stale-put error (dollars)")
    STORE.add("trim", "FwdTrimRawRatePct", num(100 * r_raw, 1),
              "implied rate of the raw (untrimmed) fit (percent)")
    STORE.add("trim", "FwdTrimRawErrBp", num(abs(raw_err), 0),
              "forward error of the raw fit (bp, absolute)")
    STORE.add("trim", "FwdTrimErrBp", num(abs(trim_err), 1),
              "forward error after the trim (bp, absolute)")
    STORE.add("trim", "FwdTrimNOut", str(int((~keep).sum())),
              "points trimmed in the staged single-outlier experiment")
    STORE.add("trim", "FwdTrimSigmaOut", num(n_sig, 0),
              "the stale quote's distance in robust sigmas")
    STORE.add("trim", "FwdMaskDeltaRatePct", num(100 * MASK_DR, 0),
              "carry error of the coherent stale wing (percent)")
    STORE.add("trim", "FwdMaskNWing", str(int(wing.sum())),
              "number of coherently stale wing quotes")
    STORE.add("trim", "FwdMaskNOut", str(mask_out),
              "points trimmed in the masking experiment")
    STORE.add("trim", "FwdMaskRatePct", num(100 * r_m, 1),
              "implied rate under coherent staleness (percent)")
    STORE.add("trim", "FwdMaskFwdErrBp", num(abs(mask_err), 0),
              "forward error under coherent staleness (bp, absolute)")
    return (f"trim: raw {raw_err:+.0f} bp/r {100*r_raw:.1f}% -> "
            f"{trim_err:+.1f} bp ({int((~keep).sum())} out, {n_sig:.0f} sig); "
            f"mask: {mask_out} out, r {100*r_m:.2f}%, F {mask_err:+.1f} bp")
