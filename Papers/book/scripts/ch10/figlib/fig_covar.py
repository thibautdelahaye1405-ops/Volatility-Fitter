"""Figure 10.6 -- the observation budget is built, not asserted.

A synthetic 21-quote chain fitted by the quadratic family whose parameters
ARE the three handles.  Panel (a): the quadratic contract -- the stated
per-quote noise is swept and the delta-method ATM sd follows with log-log
slope one (double the noise, double the sd, quadruple the variance).
Panel (b): a two-strike contradiction is dialed up; the realized-misfit
multiple inflates the observation variance, and the computed curvature gain
falls while the level gain barely moves -- no threshold anywhere.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
from figstyle import PALETTE
from macros import STORE, num

N_Q = 21
K_Q = np.linspace(-0.25, 0.25, N_Q)
TRUTH = (0.20, -0.30, 0.60)     # sigma(k) = a + b k + c k^2
NOISE = 0.0030                  # base stated per-quote noise (30 vol bp)
INFL_CAP = 25.0
# The stated prediction budget (per-handle sd): a four-day-old state under
# the audit's walk scale reads the level to sqrt(4)*30 = 60 bp; the
# curvature diffuses little.
SD_PRED = np.array([0.0060, 0.03, 0.15])
KINK_PAIR = (12, 13)            # adjacent strikes kinked +/- eps


def _design(k: np.ndarray) -> np.ndarray:
    return np.column_stack([np.ones_like(k), k, k * k])


def _handle_sds(noise_sd: float) -> np.ndarray:
    """Delta-method sds of (level, skew, curvature) -- exact, linear model."""
    a_w = _design(K_Q) / noise_sd
    info = a_w.T @ a_w
    cov = np.linalg.inv(info)
    grads = np.array([[1.0, 0.0, 0.0],    # level = theta0
                      [0.0, 1.0, 0.0],    # skew = theta1
                      [0.0, 0.0, 2.0]])   # curvature = 2 theta2
    return np.sqrt(np.einsum("ij,jk,ik->i", grads, cov, grads))


def fig_flt_covar() -> str:
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the quadratic contract.
    noises = np.geomspace(0.0010, 0.0100, 12)
    sd_level = np.array([_handle_sds(s)[0] for s in noises])
    ax_a.loglog(1e4 * noises, 1e4 * sd_level, "o-", ms=3.5,
                color=PALETTE["model"], lw=1.3)
    slope = float(np.polyfit(np.log(noises), np.log(sd_level), 1)[0])
    figstyle.callout(
        ax_a, f"log-log slope {slope:.3f}:\ndouble the stated noise,\n"
              "quadruple the variance",
        (1e4 * noises[7], 1e4 * sd_level[7]),
        (1e4 * noises[1], 1e4 * sd_level[9]),
    )
    ax_a.set_xlabel(r"stated per-quote noise $\varepsilon$ (vol bp)")
    ax_a.set_ylabel("ATM observation sd (vol bp)")
    figstyle.panel(ax_a, "a", "covariance in stated noise units")

    # (b) contradiction prices itself.
    kinks = np.linspace(0.0, 0.030, 61)   # up to 3 vol points
    gain_curv, gain_level, multiples = [], [], []
    base_sds = _handle_sds(NOISE)
    for eps in kinks:
        vols = (TRUTH[0] + TRUTH[1] * K_Q + TRUTH[2] * K_Q ** 2).copy()
        vols[KINK_PAIR[0]] += eps
        vols[KINK_PAIR[1]] -= eps
        a_w = _design(K_Q) / NOISE
        theta, *_ = np.linalg.lstsq(a_w, vols / NOISE, rcond=None)
        chi2 = float(np.sum((a_w @ theta - vols / NOISE) ** 2))
        mult = float(np.clip(chi2 / (N_Q - 3), 1.0, INFL_CAP))
        multiples.append(mult)
        sds = base_sds * np.sqrt(mult)
        gain_level.append(SD_PRED[0] ** 2 / (SD_PRED[0] ** 2 + sds[0] ** 2))
        gain_curv.append(SD_PRED[2] ** 2 / (SD_PRED[2] ** 2 + sds[2] ** 2))
    ax_b.plot(1e2 * kinks, gain_level, color=PALETTE["model"], lw=1.5,
              label="level gain")
    ax_b.plot(1e2 * kinks, gain_curv, color=PALETTE["third"], lw=1.5,
              label="curvature gain")
    ax_b.set_xlabel("two-strike kink size (vol points)")
    ax_b.set_ylabel(r"computed gain $\mathcal{K}$")
    ax_b.set_ylim(0, 1.0)
    i_end = -1
    figstyle.callout(
        ax_b, f"misfit multiple {multiples[i_end]:.0f}\n(capped at "
              f"{INFL_CAP:.0f})",
        (1e2 * kinks[i_end], gain_curv[i_end]),
        (1e2 * kinks[i_end] - 1.4, gain_curv[i_end] - 0.16),
    )
    ax_b.legend(loc="lower left")
    figstyle.panel(ax_b, "b", "a contradiction turns the dial itself")

    figstyle.save(fig, "fig_flt_covar")

    STORE.add("covar", "FiltCovarSlope", num(slope, 3),
              "log-log slope of ATM observation sd in stated noise")
    STORE.add("covar", "FiltCovarNq", str(N_Q), "synthetic chain quote count")
    STORE.add("covar", "FiltCovarBaseSdBp", num(1e4 * base_sds[0], 1),
              "clean-chain ATM observation sd (vol bp) at 30 bp noise")
    STORE.add("covar", "FiltCovarGainCurvClean", num(gain_curv[0], 2),
              "curvature gain on the clean chain")
    STORE.add("covar", "FiltCovarGainCurvKinked", num(gain_curv[i_end], 2),
              "curvature gain at the 3-point kink")
    STORE.add("covar", "FiltCovarGainLevelClean", num(gain_level[0], 2),
              "level gain on the clean chain")
    STORE.add("covar", "FiltCovarGainLevelKinked", num(gain_level[i_end], 2),
              "level gain at the 3-point kink")
    STORE.add("covar", "FiltCovarMultMax", num(multiples[i_end], 0),
              "misfit multiple at the 3-point kink (after the cap)")
    return (f"slope {slope:.3f}; curv gain {gain_curv[0]:.2f}->"
            f"{gain_curv[i_end]:.2f}, level {gain_level[0]:.2f}->"
            f"{gain_level[i_end]:.2f}, mult {multiples[i_end]:.0f}")
