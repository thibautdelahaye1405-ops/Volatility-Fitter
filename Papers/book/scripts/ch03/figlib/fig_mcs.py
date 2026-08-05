"""Chapter 3 MCS figure: the zero-wing mechanism and the WW fit (F7).

The WW target is built in TOTAL-VARIANCE space so its wings are exactly
linear (Lee-admissible everywhere) and its Durrleman factor has a positive
analytic tail limit; the generator verifies min g_D > 0 for the target AND
the fitted slice on a wide grid from analytic jets before writing anything.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from volfit.models.sigmoid.calibrate import calibrate_sigmoid
from volfit.models.sigmoid.kernels import hat, hat_p, hat_pp, phi

from figstyle import PALETTE, ROW3, panel, save
from fits import MCS_WING_PENALTY, g_mcs
from macros import STORE, num

# WW target in total variance: hyperbolic base + two Gaussian shoulders.
#   w(k) = A0 + BETA sqrt(k^2 + VS^2) + AMP [e^{-((k-C)/S)^2} + e^{-((k+C)/S)^2}]
TAU = 0.25
A0, BETA, VS = 0.008, 0.012, 0.15
AMP, CC, SS = 0.0025, 0.28, 0.11


def _target(k: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(w, w', w'') of the WW target, analytically."""
    k = np.asarray(k, dtype=float)
    r = np.sqrt(k * k + VS**2)
    w = A0 + BETA * r
    wp = BETA * k / r
    wpp = BETA * VS**2 / r**3
    for sgn in (+1.0, -1.0):
        u = (k - sgn * CC) / SS
        e = np.exp(-u * u)
        w = w + AMP * e
        wp = wp + AMP * e * (-2.0 * u / SS)
        wpp = wpp + AMP * e * (4.0 * u * u - 2.0) / SS**2
    return w, wp, wpp


def _g_of(w, wp, wpp, k) -> np.ndarray:
    return ((1.0 - k * wp / (2.0 * w)) ** 2
            - 0.25 * wp**2 * (1.0 / w + 0.25) + 0.5 * wpp)


def fig_mcs_mechanism() -> str:
    # --- verify the target is globally admissible (analytic jets, wide grid)
    k_wide = np.linspace(-12.0, 12.0, 9601)
    g_t = _g_of(*_target(k_wide), k_wide)
    if g_t.min() <= 0.0:
        raise RuntimeError(f"WW target not admissible: min g {g_t.min():.4f}")
    STORE.add("mcs", "McsTargetGmin", num(float(g_t.min()), 3),
              "min g_D of the WW target on |k|<=12 (analytic jets)")
    STORE.add("mcs", "McsTargetTailG", num((4.0 - BETA**2) / 16.0, 3),
              "analytic tail limit of the WW target's g_D")

    # --- quotes and the two fits
    kq = np.linspace(-0.50, 0.50, 61)
    wq = _target(kq)[0]
    base = calibrate_sigmoid(kq, wq, TAU, n_cores=0,
                             wing_penalty=MCS_WING_PENALTY)
    full = calibrate_sigmoid(kq, wq, TAU, n_cores=2,
                             wing_penalty=MCS_WING_PENALTY)
    iv_t = np.sqrt(wq / TAU)
    err0 = 1e4 * np.max(np.abs(base.vol(kq) - iv_t))
    err2 = 1e4 * np.max(np.abs(full.vol(kq) - iv_t))
    g_fit = g_mcs(full, np.linspace(-2.0, 2.0, 2001))
    STORE.add("mcs", "McsBaseMaxErrBp", num(float(err0), 1),
              "max IV miss of the convex base (M=0) on the WW target, vol bp")
    STORE.add("mcs", "McsFullMaxErrBp", num(float(err2), 1),
              "max IV miss of the M=2 fit on the WW target, vol bp")
    STORE.add("mcs", "McsFitGmin", num(float(g_fit.min()), 3),
              "min g_D of the M=2 fit on |k|<=2 (analytic jets)")
    STORE.add("mcs", "McsCores", str(len(full.cores)),
              "cores actually placed by the M=2 fit")

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    # (a) the log-cosh primitive and its affine asymptote
    ax = axes[0]
    u = np.linspace(-3.0, 3.0, 601)
    kap = 4.0
    ax.plot(u, phi(u, kap), color=PALETTE["model"],
            label=r"$\mathcal{A}_\kappa(\bar\zeta)$")
    ax.plot(u, 2.0 / kap * np.abs(u) - 4.0 * np.log(2.0) / kap**2,
            ls="--", lw=0.9, color=PALETTE["muted"], label="affine asymptote")
    ax.set_xlabel(r"$\bar\zeta$")
    ax.legend(loc="upper center", fontsize=7)
    panel(ax, "a", r"asymptotically affine ($\kappa=4$)")

    # (b) the kernel and its first two derivatives all vanish in the tails
    ax = axes[1]
    z = np.linspace(-4.0, 4.0, 801)
    c0, h0 = 0.0, 0.8
    ax.plot(z, hat(z, c0, h0, kap), color=PALETTE["model"],
            label=r"$\mathcal{B}$")
    ax.plot(z, hat_p(z, c0, h0, kap), color=PALETTE["data"], lw=1.0,
            label=r"$\mathcal{B}'$")
    ax.plot(z, hat_pp(z, c0, h0, kap), color=PALETTE["alt"], lw=1.0,
            label=r"$\mathcal{B}''$")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xlabel(r"$\zeta$")
    ax.legend(loc="upper right", fontsize=7)
    panel(ax, "b", "the kernel is silent in both tails")

    # (c) the WW fit: convex base misses, two hats seat the shoulders
    ax = axes[2]
    kk = np.linspace(-0.62, 0.62, 601)
    ax.plot(kq, 100 * iv_t, "o", ms=2.4, color=PALETTE["data"],
            alpha=0.75, label="WW target")
    ax.plot(kk, 100 * base.vol(kk), color=PALETTE["muted"], lw=1.1,
            label=rf"base $M=0$ ({err0:.0f} bp)")
    ax.plot(kk, 100 * full.vol(kk), color=PALETTE["model"],
            label=rf"$M=2$ ({err2:.1f} bp)")
    for core in full.cores:
        kc = core.c * full.sigma_ref * np.sqrt(TAU)
        ax.axvline(kc, color=PALETTE["model"], lw=0.6, ls=":", alpha=0.7)
    ax.set_xlabel(r"$k$"); ax.set_ylabel("implied vol (%)")
    ax.legend(loc="upper center", fontsize=7)
    panel(ax, "c", "superposition on a WW smile")

    save(fig, "fig_mcs_mechanism")
    return f"base {err0:.0f} bp -> R=2 {err2:.1f} bp, fit min g {g_fit.min():.3f}"
