"""F6 -- the wings belong to the field, and the ratio measured (section 9.6).

Panel (a): two frozen fields that agree at the money -- same ATM vol, same
ATM log-slope -- one affine in log-strike, one affine in dollar strike;
dashed the fields, solid the smiles they produce today.  Panel (b): the two
fields' OWN answers to the same -5% move (each repriced through the
forward equation): identical at the money (the half-rule's 2 s0 H), and
different shapes in the wings -- flat against tilted.  Panel (c): the
realized ratio R_hat(T) across maturities: 2.00 at every maturity for the
straight-line field regardless of the move, and lifted to a computable
level 2 + 2cH/b -- flat in maturity, growing with the move -- once the
field is bent.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import figstyle
import synthlv
from figstyle import PALETTE
from macros import STORE, num

_H_RESP = -0.05       # panel (b): the response comparison move
_H_RATIO = -0.02      # panel (c): the realized-ratio move
_H_RATIO_BIG = -0.04  # panel (c): the doubled move for the bent field
_T_CMP = 0.25
_DT_FINE = 1.25e-4    # refined march step for the bp-scale panel
_SPAN = 0.30

_COL = {"logaffine": PALETTE["model"], "dollaraffine": PALETTE["third"]}
_LBL = {"logaffine": "log-strike field", "dollaraffine": "dollar-strike field"}


def fig_ssr_reprice() -> str:
    fig, axes = plt.subplots(1, 3, figsize=figstyle.ROW3)

    # (a) two fields, (nearly) one smile today ------------------------------
    ax = axes[0]
    kk = np.linspace(-_SPAN, _SPAN, 301)
    for gen in ("logaffine", "dollaraffine"):
        ax.plot(kk, 100.0 * synthlv.vol_loc(gen, np.exp(kk)),
                color=_COL[gen], lw=1.0, ls="--", alpha=0.75)
        k0, sig0 = synthlv.smile_at(gen, 0.0, _T_CMP, dt=_DT_FINE)
        ax.plot(k0, 100.0 * sig0, color=_COL[gen], lw=1.5, label=_LBL[gen])
    ax.plot([], [], color=PALETTE["muted"], lw=1.0, ls="--",
            label="fields (dashed)")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("volatility (%)")
    ax.legend(loc="upper right", fontsize=6.6)
    figstyle.panel(ax, "a", "two fields, one money")

    # (b) the two answers to the same move ----------------------------------
    ax = axes[1]
    resp = {}
    for gen in ("logaffine", "dollaraffine"):
        k, d_bp = synthlv.response(gen, _H_RESP, _T_CMP, dt=_DT_FINE)
        resp[gen] = (k, d_bp)
        ax.plot(k, d_bp, color=_COL[gen], lw=1.5, label=_LBL[gen])
    ax.axvline(0.0, color=PALETTE["muted"], lw=0.7, ls=":")
    atm_log = float(np.interp(0.0, *resp["logaffine"]))
    atm_dlr = float(np.interp(0.0, *resp["dollaraffine"]))
    figstyle.callout(
        ax, "same answer\nat the money",
        xy=(0.0, atm_log), xytext=(-0.27, atm_log - 26.0),
    )
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"$\sigma_{\rm new}-\sigma_{\rm old}$ (vol bp)")
    ax.legend(loc="upper left", fontsize=6.6)
    figstyle.panel(ax, "b", f"the same $H={100*_H_RESP:+.0f}\\%$ move")

    # (c) the realized ratio across maturities ------------------------------
    ax = axes[2]
    res_flat = synthlv.realized_ratio("logaffine", _H_RATIO)
    res_bent = synthlv.realized_ratio("bent", _H_RATIO)
    res_bent_big = synthlv.realized_ratio("bent", _H_RATIO_BIG)
    t_arr = np.array(sorted(res_flat))
    ratio_flat = np.array([res_flat[t]["ratio"] for t in t_arr])
    ratio_bent = np.array([res_bent[t]["ratio"] for t in t_arr])
    ratio_big = np.array([res_bent_big[t]["ratio"] for t in t_arr])
    pred = 2.0 + 2.0 * synthlv.CURV_LOC * _H_RATIO / synthlv.SLOPE_LOC
    pred_big = 2.0 + 2.0 * synthlv.CURV_LOC * _H_RATIO_BIG / synthlv.SLOPE_LOC
    ax.plot(t_arr, ratio_flat, "o-", color=PALETTE["muted"], lw=1.2,
            ms=3.4, label="straight field")
    ax.plot(t_arr, ratio_bent, "o-", color=PALETTE["ink"], lw=1.4,
            ms=3.6, label=f"bent, $H={100*_H_RATIO:+.0f}\\%$")
    ax.plot(t_arr, ratio_big, "o--", color=PALETTE["ink"], lw=1.1,
            ms=3.2, mfc="white", label=f"bent, $H={100*_H_RATIO_BIG:+.0f}\\%$")
    for level in (pred, pred_big):
        ax.axhline(level, color=PALETTE["alt"], lw=0.8, ls=":")
    ax.axhline(2.0, color=PALETTE["muted"], lw=0.8, ls="--")
    ax.annotate(r"$2+2cH/b$", xy=(0.60, pred_big),
                xytext=(0.60, pred_big - 0.018),
                fontsize=7.5, color=PALETTE["alt"])
    ax.set_ylim(1.975, 2.14)
    ax.set_xlabel(r"maturity $\tau$ (years)")
    ax.set_ylabel(r"realized ratio $\widehat{\mathcal{R}}(\tau)$")
    ax.legend(loc="center", bbox_to_anchor=(0.42, 0.30), fontsize=6.4)
    figstyle.panel(ax, "c", "the ratio is an output")

    figstyle.save(fig, "fig_ssr_reprice")

    # Wing separation of the two answers in panel (b).
    k_log, d_log = resp["logaffine"]
    k_dlr, d_dlr = resp["dollaraffine"]
    sep_put = float(abs(d_log[0] - d_dlr[0]))
    sep_call = float(abs(d_log[-1] - d_dlr[-1]))

    # dt-check at the comparison maturity for the bent field.
    res_fine = synthlv.realized_ratio("bent", _H_RATIO, dt=_DT_FINE)
    check = abs(res_fine[_T_CMP]["ratio"] - res_bent[_T_CMP]["ratio"])

    STORE.add("reprice", "SsrRepRespMovePct", f"{abs(100*_H_RESP):.0f}",
              "panel (b) response-comparison move magnitude, % (down)")
    STORE.add("reprice", "SsrRepRatioMovePct", f"{abs(100*_H_RATIO):.0f}",
              "panel (c) realized-ratio move magnitude, % (down)")
    STORE.add("reprice", "SsrRepTcmp", num(_T_CMP, 2),
              "maturity of the two-field comparison, years")
    STORE.add("reprice", "SsrRepAtmLogBp", f"{atm_log:+.0f}",
              "log-strike field: repriced ATM response to the move, vol bp")
    STORE.add("reprice", "SsrRepAtmDlrBp", f"{atm_dlr:+.0f}",
              "dollar-strike field: repriced ATM response to the move, "
              "vol bp")
    STORE.add("reprice", "SsrRepSepPutBp", f"{sep_put:.0f}",
              "wing separation of the two answers at k=-0.30, vol bp")
    STORE.add("reprice", "SsrRepSepCallBp", f"{sep_call:.0f}",
              "wing separation of the two answers at k=+0.30, vol bp")
    STORE.add("reprice", "SsrRepFlatShort", num(float(ratio_flat[0]), 2),
              "straight-line field: realized ratio at the shortest maturity")
    STORE.add("reprice", "SsrRepFlatLong", num(float(ratio_flat[-1]), 2),
              "straight-line field: realized ratio at the longest maturity")
    STORE.add("reprice", "SsrRepFlatSpread", num(
        float(np.max(ratio_flat) - np.min(ratio_flat)), 3),
              "straight-line field: max-min spread of the ratio across "
              "maturities")
    STORE.add("reprice", "SsrRepBentMean", num(float(np.mean(ratio_bent)), 2),
              "bent field: mean realized ratio across maturities at H=-2%")
    STORE.add("reprice", "SsrRepBentBigMean", num(float(np.mean(ratio_big)), 2),
              "bent field: mean realized ratio across maturities at H=-4%")
    STORE.add("reprice", "SsrRepBentPred", num(pred, 2),
              "closed-form prediction 2+2cH/b at H=-2%")
    STORE.add("reprice", "SsrRepBentBigPred", num(pred_big, 2),
              "closed-form prediction 2+2cH/b at H=-4%")
    STORE.add("reprice", "SsrRepAuditPct",
              num(100.0 * check / res_bent[_T_CMP]["ratio"], 2),
              "dt-check: relative change of the bent field's ratio at the "
              "comparison maturity between dt and dt/4, %")
    return (f"ATM {atm_log:+.0f}/{atm_dlr:+.0f} bp, "
            f"sep {sep_put:.0f}/{sep_call:.0f} bp, "
            f"flat {ratio_flat[0]:.2f}->{ratio_flat[-1]:.2f}, "
            f"bent {np.mean(ratio_bent):.2f}/{np.mean(ratio_big):.2f} "
            f"(pred {pred:.2f}/{pred_big:.2f})")
