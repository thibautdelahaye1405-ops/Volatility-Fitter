"""Figures and tables for Note 03 (Multi-Core Sigmoid, MCS).

Builds a synthetic WW-shaped smile (central trough + two shoulders + rising
wings) that a single hyperbola cannot fit, calibrates the production
Multi-Core Sigmoid slice to it, and renders the base/hat decomposition and the
Durrleman diagnostic. Also times the analytic vs finite-difference Jacobian.

The synthetic target is itself verified butterfly-clean: its Durrleman g is
computed from ANALYTIC jets (value/slope/curvature in closed form, no finite
differences) and asserted strictly positive on the plotted grid before any
fit runs. An earlier revision's target carried its own butterfly arbitrage
(g dipping to about -0.38 near the shoulders), which made the fitted slice's
"g >= 0" certificate impossible; the shoulder amplitudes/widths and the wing
slope were re-chosen so the target is genuinely admissible, and the assertion
locks that property. Outputs:

  fig_siv_fit.pdf        WW target, base-only (R=0), full MCS fit
  fig_siv_components.pdf sigmoid base + each signed hat
  fig_siv_g.pdf          Durrleman g(k) >= 0 for both the fit and the target
  siv_tables.tex         \\input-able macros
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.models.sigmoid.calibrate import (
    _RIDGE,
    _base_bounds,
    _base_init,
    _core_bounds,
    _eval_v,
    _fit,
    _reference_vol,
    _seed_cores,
    calibrate_sigmoid,
)
from volfit.models.sigmoid.jacobian import siv_residual_jacobian
from volfit.models.sigmoid.kernels import hat, siv_base

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, setup  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()
TEAL, RUST, SLATE, AMBER, VIOLET = (PALETTE["teal"], PALETTE["rust"],
                                    PALETTE["muted"], PALETTE["amber"],
                                    PALETTE["violet"])


#: WW target construction, GLOBALLY butterfly-clean and Lee-admissible: total
#: variance is an SVI-style hyperbolic base (rho = 0, m = 0) plus two Gaussian
#: shoulders — Gaussians vanish with all derivatives, so the w-wings are
#: EXACTLY linear with slope beta = _T_B <= 2 (Lee-admissible for every k, not
#: just a window), and g(k) -> (4 - beta^2)/16 > 0 in both tails. An earlier
#: revision built the target in VOL space with ~0.20|k| tails (w quadratic:
#: Lee eventually violated, cleanliness only per-window); this construction
#: makes the cleanliness claim global. `main` asserts g > 0 for target AND fit
#: on the wide grid |k| <= _WIDE_K before writing anything.
_T_A, _T_B, _T_SIG = 0.005, 0.055, 0.30       # base: a + b sqrt(k^2 + sig^2)
_T_AMP, _T_C, _T_S = 0.007, 0.20, 0.12        # shoulders: A exp(-((k-+c)/s)^2)
_WIDE_K = 12.0


def ww_target_wjets(k):
    """Analytic (w, w', w'') of the WW target TOTAL VARIANCE — no finite
    differences, and asymptotically linear by construction."""
    k = np.asarray(k, dtype=float)
    r = np.sqrt(k * k + _T_SIG * _T_SIG)
    w = _T_A + _T_B * r
    w1 = _T_B * k / r
    w2 = _T_B * _T_SIG * _T_SIG / r**3
    for c in (-_T_C, _T_C):
        u = k - c
        e = _T_AMP * np.exp(-((u / _T_S) ** 2))
        w = w + e
        w1 = w1 + e * (-2.0 * u / _T_S**2)
        w2 = w2 + e * (4.0 * u * u / _T_S**4 - 2.0 / _T_S**2)
    return w, w1, w2


def ww_target_vol(k, t):
    """A WW smile: hyperbolic-in-w wings with two shoulders flanking the trough."""
    return np.sqrt(ww_target_wjets(k)[0] / t)


def target_g(k, t):
    """Durrleman g of the target, from the analytic w-jets."""
    del t  # w-space jets need no clock
    w, w1, w2 = ww_target_wjets(k)
    return (1.0 - k * w1 / (2.0 * w)) ** 2 - 0.25 * w1**2 * (1.0 / w + 0.25) + 0.5 * w2


def main():
    t = 0.25
    k = np.linspace(-0.40, 0.40, 41)
    w = ww_target_wjets(k)[0]
    vol = np.sqrt(w / t)

    kk = np.linspace(-0.45, 0.45, 400)

    # The target must be admissible BEFORE anything is fitted to it: a target
    # that itself carries butterfly arbitrage makes the fit's g >= 0 claim
    # unattainable (the earlier-revision bug). The check is GLOBAL, not
    # per-window: dense wide grid + the analytic tail limit (4 - beta^2)/16.
    wide = np.linspace(-_WIDE_K, _WIDE_K, 60001)
    target_g_min = float(target_g(wide, t).min())
    tail_g = (4.0 - _T_B * _T_B) / 16.0
    assert target_g_min > 0.0 and tail_g > 0.0, (
        f"synthetic WW target carries butterfly arbitrage: min g = {target_g_min:.4f}"
    )
    g_target = target_g(kk, t)

    siv0 = calibrate_sigmoid(k, w, t, n_cores=0)
    siv = calibrate_sigmoid(k, w, t, n_cores=2)

    # The FIT must be globally clean too: its hats are zero-wing and its base
    # w-wings are linear, so the same wide-grid + tail-limit check applies.
    fit_g_min_wide = float(siv.gatheral_g(wide).min())
    assert siv.is_butterfly_free(wide), (
        f"two-core MCS fit violates the butterfly bound: min g = {fit_g_min_wide:.4f}"
    )

    # --- fit
    fig, ax = plt.subplots()
    ax.plot(kk, 100 * ww_target_vol(kk, t), color=SLATE, lw=2.2, label="WW target")
    ax.plot(kk, 100 * siv0.vol(kk), color=AMBER, ls=":", label="sigmoid base ($R{=}0$)")
    ax.plot(kk, 100 * siv.vol(kk), color=TEAL, ls="--", label="MCS ($R{=}2$)")
    ax.scatter(k, 100 * vol, s=14, color=RUST, zorder=5, label="quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"implied volatility (%)")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_siv_fit.pdf")
    plt.close(fig)

    # --- component decomposition (in variance)
    fig, ax = plt.subplots()
    zz = siv.z(kk)
    base_v, _, _ = siv_base(zz, siv.v0, siv.s0, siv.k0, siv.z0, siv.kappa_p, siv.kappa_c)
    ax.plot(kk, base_v, color=AMBER, label="sigmoid base")
    for i, core in enumerate(siv.cores):
        ax.plot(kk, core.alpha * hat(zz, core.c, core.h, core.kappa),
                color=[TEAL, VIOLET][i % 2], ls="--",
                label=fr"hat {i+1} ($\alpha={core.alpha:+.3f}$)")
    full_v, _, _ = siv.variance_z(zz)
    ax.plot(kk, full_v, color=SLATE, lw=1.0, alpha=0.6, label="total $v_R$")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"variance $v(z)$")
    ax.legend(frameon=False, fontsize=9)
    fig.savefig(OUT / "fig_siv_components.pdf")
    plt.close(fig)

    # --- g(k): the fitted slice AND the target it chased, both globally clean
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    g = siv.gatheral_g(kk)
    ax.axhline(0, color="black", lw=0.8)
    ax.plot(kk, g_target, color=SLATE, lw=1.2, ls=":", label="WW target (analytic)")
    ax.plot(kk, g, color=TEAL, label="MCS fit ($R{=}2$)")
    ax.fill_between(kk, g, 0, where=(g >= 0), color=TEAL, alpha=0.10)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.legend(frameon=False, fontsize=9)
    ax.set_title(r"$g(k)\geq 0$ globally (asserted to $|k|=12$ + positive tail"
                 r" limits): both curves butterfly-clean", fontsize=10)
    fig.savefig(OUT / "fig_siv_g.pdf")
    plt.close(fig)

    # --- timing: analytic vs FD on the final refine stage (R=2, mid)
    vol_q = np.sqrt(w / t)
    sigma_ref = _reference_vol(vol_q, k)
    z = k / (sigma_ref * np.sqrt(t))
    sqrt_w = np.ones_like(k)
    base = _fit(_base_init(z, w / t), *_base_bounds(z), z, vol_q, sqrt_w, 0)
    seeds = _seed_cores(z, w / t - _eval_v(base, z, 0), 2)
    theta0 = np.concatenate([base, *seeds])
    clo, chi = _core_bounds(z)
    lo = np.concatenate([_base_bounds(z)[0], clo, clo])
    hi = np.concatenate([_base_bounds(z)[1], chi, chi])
    theta0 = np.clip(theta0, lo, hi)

    def residuals(theta):
        mv = np.sqrt(np.maximum(_eval_v(theta, z, 2), 1e-8))
        res = sqrt_w * (mv - vol_q)
        return np.concatenate([res, np.sqrt(_RIDGE) * theta[6::4][:2]])

    def jac(theta):
        return siv_residual_jacobian(theta, z, 2, t, sqrt_w, None,
                                     MID_ANCHOR_WEIGHT, _RIDGE, None, None, np.sqrt(1e6))

    def run(j):
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            r = least_squares(residuals, theta0, bounds=(lo, hi), jac=j,
                              method="trf", xtol=1e-12, ftol=1e-12)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best, r

    run(jac)
    ta, ra = run(jac)
    tf, rf = run("2-point")

    max_err = float(np.max(np.abs(100 * (siv.vol(k) - vol)))) * 100  # in vol bp
    wl, wr = siv.wing_slopes()
    from volfit.models.sigmoid.calibrate import (
        _H_BOUNDS, _H_INIT, _KAPPA_BOUNDS, _KAPPA_INIT,
    )
    L = ["% Auto-generated by gen_siv.py — do not edit."]
    L.append(r"\newcommand{\sivhinit}{%.2f}" % _H_INIT)
    L.append(r"\newcommand{\sivkappainit}{%.1f}" % _KAPPA_INIT)
    L.append(r"\newcommand{\sivhlo}{%.2f}" % _H_BOUNDS[0])
    L.append(r"\newcommand{\sivhhi}{%.1f}" % _H_BOUNDS[1])
    L.append(r"\newcommand{\sivkappalo}{%.1f}" % _KAPPA_BOUNDS[0])
    L.append(r"\newcommand{\sivkappahi}{%.1f}" % _KAPPA_BOUNDS[1])
    L.append(r"\newcommand{\sivmaxerr}{%.2f}" % max_err)
    L.append(r"\newcommand{\sivbasemaxerr}{%.2f}"
             % (float(np.max(np.abs(100 * (siv0.vol(k) - vol)))) * 100))
    L.append(r"\newcommand{\sivncores}{%d}" % len(siv.cores))
    L.append(r"\newcommand{\sivridge}{%g}" % _RIDGE)
    L.append(r"\newcommand{\sivwingL}{%.3f}" % wl)
    L.append(r"\newcommand{\sivwingR}{%.3f}" % wr)
    L.append(r"\newcommand{\sivnparam}{%d}" % (6 + 4 * len(siv.cores)))
    L.append(r"\newcommand{\sivanalyticms}{%.1f}" % (1e3 * ta))
    L.append(r"\newcommand{\sivfdms}{%.1f}" % (1e3 * tf))
    L.append(r"\newcommand{\sivspeedup}{%.2f}" % (tf / ta))
    L.append(r"\newcommand{\sivcostdiff}{%.1e}" % abs(ra.cost - rf.cost))
    L.append(r"\newcommand{\sivtargetgmin}{%.2f}" % target_g_min)
    L.append(r"\newcommand{\sivfitgmin}{%.2f}" % fit_g_min_wide)
    L.append(r"\newcommand{\sivtargetbeta}{%.3f}" % _T_B)
    L.append(r"\newcommand{\sivtargettailg}{%.3f}" % tail_g)
    (OUT / "siv_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "siv_numbers.json").write_text(json.dumps(
        {"max_err_bp": max_err, "wing": [wl, wr],
         "speedup": tf / ta, "cores": len(siv.cores),
         "target_g_min_wide": target_g_min, "fit_g_min_wide": fit_g_min_wide,
         "target_beta": _T_B, "tail_g": tail_g},
        indent=2), encoding="utf-8")
    print("MCS WW fit max err %.2f bp (base %.2f bp); speedup %.2fx; "
          "wide-grid target min g %.3f, fit min g %.3f, tail limit %.3f"
          % (max_err, float(np.max(np.abs(100 * (siv0.vol(k) - vol)))) * 100,
             tf / ta, target_g_min, fit_g_min_wide, tail_g))


if __name__ == "__main__":
    main()
