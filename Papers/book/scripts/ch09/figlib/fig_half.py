"""F5 -- the regime that answers (section 9.5).

Panel (a): the half-rule measured -- the synthetic generator's volatility
line against the implied smile the forward equation produces at a short
maturity: half the slope.  Panel (b): freeze the field, move the forward
-4%: the implied smile slides along the generator, and the measured ATM
change matches 2 s0 H.  Panel (c): on the frozen hero smile, the midpoint
relabeling minus the linear R=2 transport across strikes at a -5% move --
zero at the money, first-order in the wings, larger on the put side.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
import synthlv
from figstyle import PALETTE
from macros import STORE, num

_T_SHORT = 0.10
_H_SYN = -0.04
_H_WING = -0.05
_SPAN_SYN = 0.25
_SPAN_HERO = (-0.24, 0.15)   # keeps ell(k, H) inside the hero quote span


def fig_ssr_half() -> str:
    # Synthetic world (the straight-line generator) -------------------------
    k0, sig0 = synthlv.smile_at("logaffine", 0.0, _T_SHORT)
    k1, sig1 = synthlv.smile_at("logaffine", _H_SYN, _T_SHORT)
    sel0 = np.abs(k0) <= _SPAN_SYN
    atm0, s0_syn = synthlv.atm_and_skew(k0, sig0)
    atm1, _ = synthlv.atm_and_skew(k1, sig1)
    ratio = s0_syn / synthlv.SLOPE_LOC
    moved_bp = (atm1 - atm0) * 1e4
    pred_bp = 2.0 * s0_syn * _H_SYN * 1e4

    fig, axes = plt.subplots(1, 3, figsize=figstyle.ROW3)

    # (a) the half-rule measured -------------------------------------------
    ax = axes[0]
    kk = k0[sel0]
    ax.plot(kk, 100.0 * synthlv.vol_loc("logaffine", np.exp(kk)),
            color=PALETTE["ink"], lw=1.2, ls="--", label="generator (local)")
    ax.plot(kk, 100.0 * sig0[sel0], color=PALETTE["model"], lw=1.5,
            label=f"implied, $\\tau={_T_SHORT:.2f}$")
    figstyle.callout(
        ax, f"slope {synthlv.SLOPE_LOC:+.2f}",
        xy=(-0.15, 100.0 * float(synthlv.vol_loc("logaffine",
                                                 np.exp(-0.15)))),
        xytext=(-0.10, 100.0 * float(synthlv.vol_loc("logaffine",
                                                     np.exp(-0.2)))))
    figstyle.callout(ax, f"slope {s0_syn:+.3f}",
                     xy=(0.12, 100.0 * np.interp(0.12, k0, sig0)),
                     xytext=(0.015, 100.0 * np.interp(0.12, k0, sig0) - 2.6))
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("volatility (%)")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "a", "the half-rule, measured")

    # (b) frozen field, moved forward ---------------------------------------
    ax = axes[1]
    sel1 = np.abs(k1) <= _SPAN_SYN
    ax.plot(k0[sel0], 100.0 * sig0[sel0], color=PALETTE["model"], lw=1.5,
            label="before")
    ax.plot(k1[sel1], 100.0 * sig1[sel1], color=PALETTE["third"], lw=1.5,
            label=f"after $H={100*_H_SYN:+.0f}\\%$")
    ax.plot([0.0], [100.0 * atm0], "o", ms=4.5, color=PALETTE["model"],
            zorder=5)
    ax.plot([0.0], [100.0 * atm1], "o", ms=4.5, color=PALETTE["third"],
            zorder=5)
    figstyle.callout(
        ax, f"ATM {moved_bp:+.0f} bp\n(2$s_0H$ = {pred_bp:+.0f} bp)",
        xy=(0.0, 100.0 * atm1), xytext=(0.045, 100.0 * atm1 + 1.6),
    )
    ax.set_xlabel(r"log-moneyness $k$ (prevailing forward)")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(loc="lower left", fontsize=6.8)
    figstyle.panel(ax, "b", "frozen field, moved forward")

    # (c) midpoint relabeling vs linear on the hero node --------------------
    ax = axes[2]
    sm = data9.hero()
    k = np.linspace(*_SPAN_HERO, 401)
    iv_hagan = data9.transport_hagan(sm, _H_WING)(k)
    iv_linear = data9.transport_vol(sm, _H_WING, 2.0)(k)
    gap_bp = (iv_hagan - iv_linear) * 1e4
    ax.plot(k, gap_bp, color=PALETTE["ink"], lw=1.5)
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.axvline(0.0, color=PALETTE["muted"], lw=0.7, ls=":")
    put_bp = float(gap_bp[0])
    call_bp = float(gap_bp[-1])
    figstyle.callout(ax, f"{put_bp:+.0f} bp", xy=(k[0] + 0.004, put_bp),
                     xytext=(k[0] + 0.03, put_bp * 0.55))
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("relabeling $-$ linear (vol bp)")
    figstyle.panel(ax, "c",
                   f"the wings disagree ($H={100*_H_WING:+.0f}\\%$)")

    figstyle.save(fig, "fig_ssr_half")

    STORE.add("half", "SsrHalfSlopeLoc", num(synthlv.SLOPE_LOC, 2),
              "generator vol slope per unit log-strike")
    STORE.add("half", "SsrHalfSlopeImp", num(s0_syn, 3),
              "measured implied ATM skew of the generator at tau=0.10")
    STORE.add("half", "SsrHalfRatio", num(ratio, 3),
              "measured implied-to-local slope ratio at tau=0.10")
    STORE.add("half", "SsrHalfAtmMoveBp", f"{moved_bp:+.0f}",
              "measured ATM change after the frozen-field -4% move, vol bp")
    STORE.add("half", "SsrHalfAtmPredBp", f"{pred_bp:+.0f}",
              "half-rule prediction 2 s0 H, vol bp")
    STORE.add("half", "SsrHalfGapPutBp", f"{abs(put_bp):.0f}",
              "relabeling-vs-linear gap at k=-0.24 under a -5% move, bp")
    STORE.add("half", "SsrHalfGapCallBp", f"{abs(call_bp):.0f}",
              "relabeling-vs-linear gap at k=+0.15 under a -5% move, bp")
    STORE.add("half", "SsrHalfMoveWingPct", f"{abs(100*_H_WING):.0f}",
              "the wing-gap panel's move magnitude, %")
    return (f"ratio {ratio:.3f}, ATM {moved_bp:+.0f}/{pred_bp:+.0f} bp, "
            f"wings {put_bp:+.0f}/{call_bp:+.0f} bp")
