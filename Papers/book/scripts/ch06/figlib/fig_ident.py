"""Figure 6.2: the identifiability asymmetry, predicted and measured.

Seeded Monte Carlo on the running synthetic board: two-cent quote noise on
every mid, the plain least-squares fit per trial, and the scatter of the
implied rate versus the scatter of the forward, against the closed-form
standard deviations of Proposition [ols].
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import data6
import figstyle
from figstyle import PALETTE
from macros import STORE, num

TRIALS = 2000
EPS = 0.02          # quote-noise sd per mid, dollars (two cents)
SEED = 20260806
SHORT_T = 0.05      # the short-dated variant quoted in the text


def _mc(bd: data6.Board, rng: np.random.Generator
        ) -> tuple[np.ndarray, np.ndarray]:
    """Fitted (r_hat, F_hat) over TRIALS noisy copies of the board."""
    rates, fwds = np.empty(TRIALS), np.empty(TRIALS)
    for i in range(TRIALS):
        noise = rng.normal(0.0, EPS, size=(2, bd.K.size))
        pi = (bd.C_exact + noise[0]) - (bd.P_exact + noise[1])
        F, D, _, _ = data6.ols(bd.K, pi)
        rates[i] = -np.log(D) / bd.t
        fwds[i] = F
    return rates, fwds


def _predictions(bd: data6.Board) -> tuple[float, float, float, float]:
    """(sd_D, sd_r_bp, sd_F_bp, root_Skk) from the OLS formulas."""
    Kbar = float(np.mean(bd.K))
    Skk = float(np.sum((bd.K - Kbar) ** 2))
    sd_D = EPS * np.sqrt(2.0) / np.sqrt(Skk)
    sd_r_bp = 1e4 * sd_D / (bd.D * bd.t)
    level = EPS * np.sqrt(2.0) / (np.sqrt(bd.K.size) * bd.D * bd.F)
    lever = (bd.F - Kbar) / bd.F * sd_D / bd.D
    sd_F_bp = 1e4 * np.hypot(level, lever)
    return sd_D, sd_r_bp, sd_F_bp, np.sqrt(Skk)


def fig_fwd_ident() -> str:
    rng = np.random.default_rng(SEED)
    bd = data6.board()
    rates, fwds = _mc(bd, rng)
    _, sd_r_pred, sd_F_pred, root_skk = _predictions(bd)

    # The deterministic clean-board fit (cent rounding the only noise).
    F_c, D_c, _, _ = data6.ols(bd.K, bd.Pi)
    clean_fwd_bp = abs(1e4 * (F_c / bd.F - 1.0))
    clean_rate_bp = abs(1e4 * (-np.log(D_c) / bd.t - bd.r))

    rate_bp = 1e4 * (rates - bd.r)
    fwd_bp = 1e4 * (fwds / bd.F - 1.0)
    sd_r_meas = float(np.std(rate_bp, ddof=1))
    sd_F_meas = float(np.std(fwd_bp, ddof=1))

    # The short-dated variant: same board, same noise, t = SHORT_T.
    bd_short = data6.board(t=SHORT_T)
    rates_s, _ = _mc(bd_short, rng)
    sd_r_short = float(np.std(1e4 * (rates_s - bd_short.r), ddof=1))

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    for ax, vals, sd_pred, unit in (
        (ax_a, rate_bp, sd_r_pred, "rate error (bp)"),
        (ax_b, fwd_bp, sd_F_pred, "forward error (bp of $F$)"),
    ):
        ax.hist(vals, bins=41, color=PALETTE["model"], alpha=0.85,
                edgecolor="white", linewidth=0.3)
        for s in (-sd_pred, sd_pred):
            ax.axvline(s, color=PALETTE["ink"], lw=1.0, ls="--")
        ax.set_xlabel(unit)
        ax.set_ylabel("trials")
    ax_a.text(0.03, 0.95,
              f"measured sd {sd_r_meas:.1f} bp\npredicted {sd_r_pred:.1f} bp",
              transform=ax_a.transAxes, va="top", fontsize=7.5)
    ax_b.text(0.03, 0.95,
              f"measured sd {sd_F_meas:.2f} bp\npredicted {sd_F_pred:.2f} bp",
              transform=ax_b.transAxes, va="top", fontsize=7.5)
    figstyle.panel(ax_a, "a", "the implied rate: slope noise, divided by $t$")
    figstyle.panel(ax_b, "b", "the forward: level noise, nearly untouched")

    figstyle.save(fig, "fig_fwd_ident")

    STORE.add("ident", "FwdIdentTrials", str(TRIALS),
              "Monte Carlo trials in the identifiability experiment")
    STORE.add("ident", "FwdIdentEpsCents", num(100 * EPS, 0),
              "quote-noise sd per mid (cents)")
    STORE.add("ident", "FwdIdentNStrikes", str(bd.K.size),
              "paired strikes on the running synthetic board")
    STORE.add("ident", "FwdIdentRootSkk", num(root_skk, 0),
              "root strike dispersion sqrt(S_KK) (strike-dollars)")
    STORE.add("ident", "FwdIdentRateSdBp", num(sd_r_meas, 1),
              "measured sd of the implied rate (bp)")
    STORE.add("ident", "FwdIdentRatePredBp", num(sd_r_pred, 1),
              "predicted sd of the implied rate (bp)")
    STORE.add("ident", "FwdIdentFwdSdBp", num(sd_F_meas, 2),
              "measured sd of the forward (bp of F)")
    STORE.add("ident", "FwdIdentFwdPredBp", num(sd_F_pred, 2),
              "predicted sd of the forward (bp of F)")
    STORE.add("ident", "FwdIdentRatio", num(sd_r_meas / sd_F_meas, 0),
              "rate-to-forward scatter ratio (both in bp)")
    STORE.add("ident", "FwdIdentShortT", num(SHORT_T, 2),
              "year fraction of the short-dated variant")
    STORE.add("ident", "FwdIdentShortRateSdBp", num(sd_r_short, 0),
              "measured rate sd on the short-dated variant (bp)")
    STORE.add("ident", "FwdIdentLeverDollars", num(bd.F - float(np.mean(bd.K)), 2),
              "lever arm F minus mean strike on the running board (dollars)")
    STORE.add("ident", "FwdIdentCleanFwdErrBp", num(clean_fwd_bp, 2),
              "clean rounded-board forward recovery error (bp, absolute)")
    STORE.add("ident", "FwdIdentCleanRateErrBp", num(clean_rate_bp, 1),
              "clean rounded-board rate recovery error (bp, absolute)")
    return (f"rate sd {sd_r_meas:.1f} bp (pred {sd_r_pred:.1f}), "
            f"fwd sd {sd_F_meas:.2f} bp (pred {sd_F_pred:.2f}), "
            f"short-t {sd_r_short:.0f} bp")
