"""Figures and tables for Note 03 (Multi-Core SIV).

Builds a synthetic WW-shaped smile (central trough + two shoulders + rising
wings) that a single hyperbola cannot fit, calibrates the production Multi-Core
SIV slice to it, and renders the base/hat decomposition and the Durrleman
diagnostic. Also times the analytic vs finite-difference Jacobian. Outputs:

  fig_siv_fit.pdf       WW target, base-only (R=0), full MC-SIV fit
  fig_siv_components.pdf base SIV + each signed hat
  fig_siv_g.pdf         Durrleman g(k) >= 0
  siv_tables.tex        \\input-able macros
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


def ww_target_vol(k):
    """A WW smile: rising V wings with two shoulders flanking the ATM trough."""
    wings = 0.16 + 0.32 * (np.sqrt(k * k + 0.0009) - 0.03)
    shoulder_l = 0.028 * np.exp(-((k + 0.13) / 0.055) ** 2)
    shoulder_r = 0.024 * np.exp(-((k - 0.14) / 0.060) ** 2)
    return wings + shoulder_l + shoulder_r


def main():
    t = 0.25
    k = np.linspace(-0.40, 0.40, 41)
    vol = ww_target_vol(k)
    w = vol**2 * t

    siv0 = calibrate_sigmoid(k, w, t, n_cores=0)
    siv = calibrate_sigmoid(k, w, t, n_cores=2)

    kk = np.linspace(-0.45, 0.45, 400)

    # --- fit
    fig, ax = plt.subplots()
    ax.plot(kk, 100 * ww_target_vol(kk), color=SLATE, lw=2.2, label="WW target")
    ax.plot(kk, 100 * siv0.vol(kk), color=AMBER, ls=":", label="base SIV ($R{=}0$)")
    ax.plot(kk, 100 * siv.vol(kk), color=TEAL, ls="--", label="MC-SIV ($R{=}2$)")
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
    ax.plot(kk, base_v, color=AMBER, label="base SIV")
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

    # --- g(k)
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    g = siv.gatheral_g(kk)
    ax.axhline(0, color="black", lw=0.8)
    ax.plot(kk, g, color=TEAL)
    ax.fill_between(kk, g, 0, where=(g >= 0), color=TEAL, alpha=0.10)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title(r"$g(k)\geq 0$: the two-shoulder fit stays butterfly-free", fontsize=10)
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
    (OUT / "siv_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "siv_numbers.json").write_text(json.dumps(
        {"max_err_bp": max_err, "wing": [wl, wr],
         "speedup": tf / ta, "cores": len(siv.cores)}, indent=2), encoding="utf-8")
    print("MC-SIV WW fit max err %.2f bp (base %.2f bp); speedup %.2fx"
          % (max_err, float(np.max(np.abs(100 * (siv0.vol(k) - vol)))) * 100, tf / ta))


if __name__ == "__main__":
    main()
