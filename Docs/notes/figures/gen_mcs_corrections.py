"""Figures and generated numbers for the "base and correction" edition of Note 03.

Angle: *superposition with a locality guarantee.*  A convex base owns the tails
(the wings, the Lee asymptotes --- Note 02's world); local corrections add body
detail the wings never feel.  The mathematical heart is that a centred second
difference annihilates affine functions, and the log-cosh primitive is
asymptotically affine, so the correction kernels are silent (value, slope,
curvature) in both tails.  The second act is capacity control: expressiveness
has diminishing returns and an arbitrage tax, so the flexible model must be
governed (identifiability cap, ridge, hard cap at two, put-wing penalty).

Every curve, fit, Jacobian and diagnostic comes from production modules; the
only synthetic objects are the explicitly-labelled targets (the globally clean
WW smile, and the noisy convex liquid smile used to expose over-fitting).

Outputs (next to this script)
-----------------------------
fig_mcscorr_whyww.pdf       a convex base leaves a structured local residual
fig_mcscorr_annihilate.pdf  the 2nd difference kills the affine tail (B,B',B''->0)
fig_mcscorr_superpose.pdf   base + two signed hats = the fit
fig_mcscorr_wingneutral.pdf the correction is local: tails coincide exactly
fig_mcscorr_capacity.pdf    underfit (WW) and overfit (noisy liquid) vs R
fig_mcscorr_wingarb.pdf     over-reach breaks convexity in the sparse wing; the
                            put-wing penalty repairs it
fig_mcscorr_gclean.pdf      Durrleman g of fit and target, globally clean
fig_mcscorr_timing.pdf      analytic vs finite-difference Jacobian
mcs_corrections_tables.tex  prose macros
mcs_corrections_numbers.json auditable payload
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(OUT))

from style import PALETTE, label_panel, save, setup  # noqa: E402
from mcs_corrections_reference import durrleman_g as ref_g  # noqa: E402
from mcs_corrections_reference import v_model as ref_v  # noqa: E402
from volfit.calib.band import MID_ANCHOR_WEIGHT  # noqa: E402
from volfit.models.sigmoid.calibrate import (  # noqa: E402
    _RIDGE, _H_BOUNDS, _H_INIT, _KAPPA_BOUNDS, _KAPPA_INIT,
    _WING_GRID, _WING_PAD, _WING_PUT_FACTOR, WING_PENALTY_BASE,
    _base_bounds, _base_init, _core_bounds, _eval_v, _fit, _reference_vol,
    _seed_cores, calibrate_sigmoid,
)
from volfit.models.sigmoid.jacobian import siv_residual_jacobian  # noqa: E402
from volfit.models.sigmoid.kernels import phi, hat, hat_p, hat_pp, siv_base  # noqa: E402
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv  # noqa: E402

setup()
INK = PALETTE["ink"]
MUTED = PALETTE["muted"]
TEAL = PALETTE["teal"]
BLUE = PALETTE["blue"]
RUST = PALETTE["rust"]
AMBER = PALETTE["amber"]
VIOLET = PALETTE["violet"]
GREEN = PALETTE["green"]

TAU = 0.25

# --- WW target: total variance = hyperbolic base + two Gaussian shoulders, so
# the w-wings are EXACTLY linear (slope beta = _T_B <= 2, Lee-admissible for all
# k) and g -> (4-beta^2)/16 > 0 in both tails. Globally clean, not per-window.
_T_A, _T_B, _T_SIG = 0.005, 0.055, 0.30
_T_AMP, _T_C, _T_S = 0.007, 0.20, 0.12
_WIDE_K = 12.0

# Historical backtest numbers (NOT recomputed here); anchors recorded so the
# generated TeX owns the numbers, not the manuscript.
HISTORICAL = {
    "oos_before": 13.99, "oos_after": 13.58,        # third-core OOS RMS (bp)
    "cost_rtwo": 514, "cost_rthree": 2023,          # per-fit cost (ms), that harness
    "put_pct": 64, "atm_pct": 4, "worst_z": -3.2,   # wing census (audited SIV-3 spike)
    "wing_min_before": -7.9, "wing_min_after": -0.02,
    "abl_none_g": -30, "abl_none_rms": 92,          # illiquid ablation, medians/38 nodes
    "abl_repair_rms": 25, "abl_penalty_rms": 749, "abl_both_rms": 225,
    "abl_flagged_pct": 26,
    "efa_none_rms": 75, "efa_none_g": -116, "efa_repair_rms": 18, "efa_repair_g": -12,
    "efa_penalty_rms": 726, "efa_both_rms": 34,
    "liq_flagged": "17 of 30", "liq_before": 10.9, "liq_after": 36.9, "liq_flagged_pct": 41,
    "source": "backend/backtest/FINDINGS_calibration_arb.md, ablation_arb.py",
}


# ---------------------------------------------------------------------------
# WW target (analytic total-variance jets) and helpers
# ---------------------------------------------------------------------------
def ww_wjets(k):
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


def ww_vol(k):
    return np.sqrt(ww_wjets(k)[0] / TAU)


def ww_target_g(k):
    w, w1, w2 = ww_wjets(k)
    return (1.0 - k * w1 / (2.0 * w)) ** 2 - 0.25 * w1**2 * (1.0 / w + 0.25) + 0.5 * w2


def base_of(fit: MultiCoreSiv) -> MultiCoreSiv:
    """The R=0 base of a fitted slice (drop the hats), same sigma_ref/t."""
    return MultiCoreSiv(fit.v0, fit.s0, fit.k0, fit.z0, fit.kappa_p, fit.kappa_c,
                        fit.sigma_ref, fit.t, cores=())


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def figure_whyww(fit0: MultiCoreSiv, k, vol_q) -> None:
    """Motivation: a convex base leaves a structured, local residual."""
    kk = np.linspace(-0.45, 0.45, 500)
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.4))

    ax = axes[0]
    ax.plot(kk, 100 * ww_vol(kk), color=MUTED, lw=2.3, label="WW target")
    ax.plot(kk, 100 * fit0.vol(kk), color=AMBER, ls="--", label=r"convex base ($R{=}0$)")
    ax.scatter(k, 100 * vol_q, s=13, color=RUST, zorder=5, label="quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title("a convex base misses the shoulders")
    ax.legend(loc="upper center", fontsize=8.3)
    label_panel(ax, "A")

    ax = axes[1]
    resid = 1e4 * (fit0.vol(kk) - ww_vol(kk))
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(kk, 0.0, resid, color=RUST, alpha=0.14)
    ax.plot(kk, resid, color=RUST)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("base residual (vol bp)")
    ax.set_title("a structured residual two hats absorb")
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.32)
    save(fig, OUT / "fig_mcscorr_whyww.pdf")


def figure_annihilate() -> None:
    """Mechanism: Phi is asymptotically affine, and the 2nd difference kills it."""
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))

    ax = axes[0]
    u = np.linspace(-6.0, 6.0, 600)
    kap = 2.5
    ax.plot(u, phi(u, kap), color=TEAL, label=r"$\Phi_\kappa(u)$")
    affine = 2.0 / kap * np.abs(u) - 4.0 / kap**2 * np.log(2.0)
    ax.plot(u, affine, color=MUTED, ls=":", lw=1.4,
            label=r"$\frac{2}{\kappa}|u|-\frac{4}{\kappa^2}\log 2$")
    ax.set_xlabel(r"$u$")
    ax.set_ylabel(r"$\Phi_\kappa$")
    ax.set_title("the primitive is asymptotically affine")
    ax.legend(loc="upper center", fontsize=8.6)
    label_panel(ax, "A")

    ax = axes[1]
    z = np.linspace(-6.0, 6.0, 700)
    c, h, ka = 0.0, 1.2, 2.5
    ax.axhline(0.0, color=INK, lw=0.7)
    ax.plot(z, hat(z, c, h, ka), color=TEAL, label=r"$B$")
    ax.plot(z, hat_p(z, c, h, ka), color=BLUE, ls="--", label=r"$B'$")
    ax.plot(z, hat_pp(z, c, h, ka), color=RUST, ls=":", label=r"$B''$")
    ax.set_xlabel(r"$z$")
    ax.set_ylabel("hat and derivatives")
    ax.set_title(r"$B,B',B''\to 0$ in both tails")
    ax.legend(loc="upper right", fontsize=8.6, ncol=1)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_mcscorr_annihilate.pdf")


def figure_superpose(fit: MultiCoreSiv) -> None:
    """base + two signed hats = the fit, in variance."""
    kk = np.linspace(-0.45, 0.45, 500)
    zz = fit.z(kk)
    base_v, _, _ = siv_base(zz, fit.v0, fit.s0, fit.k0, fit.z0, fit.kappa_p, fit.kappa_c)
    full_v, _, _ = fit.variance_z(zz)

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.plot(kk, base_v, color=AMBER, lw=2.0, label="convex base")
    colors = [TEAL, VIOLET]
    for i, core in enumerate(fit.cores):
        ax.plot(kk, core.alpha * hat(zz, core.c, core.h, core.kappa),
                color=colors[i % 2], ls="--", lw=1.6,
                label=rf"hat {i+1}: $\alpha={core.alpha:+.3f}$")
    ax.plot(kk, full_v, color=INK, lw=1.3, label=r"sum $v_R$")
    ax.axhline(0.0, color=INK, lw=0.6)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"variance $v(z)$")
    ax.set_title("the base owns the V; each signed hat adds one shoulder")
    ax.legend(loc="upper center", ncol=2, fontsize=9)
    save(fig, OUT / "fig_mcscorr_superpose.pdf")


def figure_wingneutral(fit: MultiCoreSiv) -> None:
    """The correction is local: base and base+hats share the wings exactly."""
    base = base_of(fit)
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))

    ax = axes[0]
    kk = np.linspace(-1.1, 1.1, 700)
    ax.plot(kk, base.implied_w(kk), color=AMBER, lw=1.8, label=r"base ($R{=}0$)")
    ax.plot(kk, fit.implied_w(kk), color=TEAL, ls="--", label=r"base $+$ hats")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("bodies differ, wings coincide")
    ax.legend(loc="upper center", fontsize=8.6)
    label_panel(ax, "A")

    ax = axes[1]
    kp = np.linspace(0.03, 10.0, 900)
    diff_r = 1e4 * (fit.implied_w(kp) - base.implied_w(kp))
    diff_l = 1e4 * (fit.implied_w(-kp) - base.implied_w(-kp))
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.plot(kp, diff_l, color=RUST, lw=2.4, label="put side")
    ax.plot(kp, diff_r, color=BLUE, ls="--", lw=1.6, label="call side")
    ax.set_xscale("log")
    ax.set_xlabel(r"$|k|$ (log scale)")
    ax.set_ylabel(r"$w_{\mathrm{full}}-w_{\mathrm{base}}$ (var bp $\times10^{4}$)")
    ax.set_title("the correction decays to zero")
    ax.legend(loc="upper right", fontsize=8.6)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_mcscorr_wingneutral.pdf")


def figure_capacity(cap: dict) -> None:
    """Two failure modes of the wrong core count: underfit (WW) and overfit (noisy)."""
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))

    ax = axes[0]
    Rs = cap["Rs"]
    ax.plot(Rs, cap["ww_err"], color=TEAL, marker="o")
    for R, e in zip(Rs, cap["ww_err"]):
        ax.annotate(f"{e:.1f}", (R, e), textcoords="offset points", xytext=(0, 6),
                    ha="center", fontsize=8.2, color=INK)
    ax.set_xticks(Rs)
    ax.set_ylim(bottom=0.0, top=max(cap["ww_err"]) * 1.18)
    ax.set_xlabel(r"cores $R$")
    ax.set_ylabel("WW max error (vol bp)")
    ax.set_title("too few: bias (the WW smile)")
    label_panel(ax, "A")

    ax = axes[1]
    ax.plot(Rs, cap["liq_ins"], color=MUTED, marker="s", label="in-sample")
    ax.plot(Rs, cap["liq_true"], color=RUST, marker="o", label="true-curve")
    ax.set_xticks(Rs)
    ax.set_xlabel(r"cores $R$")
    ax.set_ylabel("RMS vs noisy quotes (vol bp)")
    ax.set_title("too many: variance (a liquid smile)")
    ax.legend(loc="center right", fontsize=8.6)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.36)
    save(fig, OUT / "fig_mcscorr_capacity.pdf")


def figure_wingarb(arb: dict) -> None:
    """An arbitraged put-wing input breaks convexity; the penalty repairs it."""
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))
    kk = arb["kk"]
    lo = min(-0.6, arb["gmin"] * 1.25)
    ylim = (lo, 1.3)

    ax = axes[0]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.plot(kk, arb["g_off"], color=RUST)
    ax.fill_between(kk, arb["g_off"], 0.0, where=arb["g_off"] < 0.0, color=RUST, alpha=0.22)
    ax.scatter(arb["kq"][arb["kq"] <= -0.28], [0.0, 0.0], marker="v", s=40, color=INK, zorder=6)
    ax.set_ylim(*ylim)
    ax.annotate("arbitraged\nput quotes", xy=(-0.31, 0.03), xytext=(-0.30, 0.7),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.2, color=MUTED, ha="center")
    ax.annotate(rf"$g\to{arb['gmin']:.2f}$", xy=(arb["kmin"], max(arb["gmin"], lo * 0.98)),
                xytext=(arb["kmin"] + 0.02, lo * 0.6),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.4, color=RUST)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title("penalty off: a hat chases the kink")
    label_panel(ax, "A")

    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.plot(kk, arb["g_off"], color=MUTED, ls=":", label="penalty off")
    ax.plot(kk, arb["g_on"], color=TEAL, label="penalty on")
    ax.fill_between(kk, arb["g_on"], 0.0, where=arb["g_on"] >= 0.0, color=TEAL, alpha=0.10)
    ax.set_ylim(*ylim)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title("penalty on: pulled back to admissible")
    ax.legend(loc="lower center", fontsize=8.6)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.32)
    save(fig, OUT / "fig_mcscorr_wingarb.pdf")


def figure_gclean(fit: MultiCoreSiv) -> None:
    kk = np.linspace(-0.45, 0.45, 500)
    g = fit.gatheral_g(kk)
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.plot(kk, ww_target_g(kk), color=MUTED, ls=":", lw=1.3, label="WW target (analytic)")
    ax.plot(kk, g, color=TEAL, label=r"MCS fit ($R{=}2$)")
    ax.fill_between(kk, g, 0.0, where=g >= 0.0, color=TEAL, alpha=0.10)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title(r"both curves butterfly-clean (asserted to $|k|=12$ + positive tail limits)")
    ax.legend(loc="lower center", fontsize=9)
    save(fig, OUT / "fig_mcscorr_gclean.pdf")


def figure_timing(timing: dict) -> None:
    fig, ax = plt.subplots(figsize=(5.0, 3.5))
    vals = [timing["fd_ms"], timing["analytic_ms"]]
    bars = ax.bar([0, 1], vals, color=[MUTED, TEAL], width=0.6)
    ax.set_xticks([0, 1], ["finite difference", "analytic"])
    ax.set_ylabel("ms per final refine ($R{=}2$)")
    ax.set_ylim(top=max(vals) * 1.18)
    ax.set_title("closed-form Jacobian through the log-cosh")
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.1f}",
                ha="center", va="bottom", fontsize=9)
    save(fig, OUT / "fig_mcscorr_timing.pdf")


# ---------------------------------------------------------------------------
# Computations
# ---------------------------------------------------------------------------
def capacity_case(k, w_ww, vol_ww) -> dict:
    Rs = [0, 1, 2, 3]
    ww_err = []
    for R in Rs:
        fit = calibrate_sigmoid(k, w_ww, TAU, n_cores=R)
        ww_err.append(float(np.max(np.abs(1e4 * (fit.vol(k) - vol_ww)))))

    # Noisy convex liquid smile: truth = base-only MCS, quotes = truth + tick noise.
    truth = MultiCoreSiv(v0=0.040, s0=-0.030, k0=0.030, z0=0.0,
                         kappa_p=3.0, kappa_c=4.0, sigma_ref=0.20, t=TAU, cores=())
    kl = np.linspace(-0.30, 0.30, 21)
    rng = np.random.default_rng(0)
    vol_true = truth.vol(kl)
    vol_noisy = vol_true + rng.normal(0.0, 0.004, size=kl.size)  # ~40 vol bp ticks
    w_noisy = (vol_noisy**2) * TAU
    grid = np.linspace(-0.30, 0.30, 400)
    liq_ins, liq_true = [], []
    for R in Rs:
        fit = calibrate_sigmoid(kl, w_noisy, TAU, n_cores=R)
        liq_ins.append(float(np.sqrt(np.mean((1e4 * (fit.vol(kl) - vol_noisy)) ** 2))))
        liq_true.append(float(np.sqrt(np.mean((1e4 * (fit.vol(grid) - truth.vol(grid))) ** 2))))
    return {"Rs": Rs, "ww_err": ww_err, "liq_ins": liq_ins, "liq_true": liq_true}


def wingarb_case() -> dict:
    """An arbitraged put-wing input, fit penalty off vs on (deterministic).

    Truth is a convex base; the two deepest put quotes are pushed up (a localized
    non-convex kink, of the kind a per-strike de-Americanization can hand every
    model).  A hat chases that kink and breaks convexity in the put wing.  The
    same quotes refit with the put-wing penalty are pulled back to the admissible
    boundary there, at the cost of fitting the arbitraged quotes less.
    """
    truth = MultiCoreSiv(v0=0.045, s0=-0.050, k0=0.045, z0=0.0,
                         kappa_p=2.5, kappa_c=4.5, sigma_ref=0.21, t=TAU, cores=())
    kq = np.linspace(-0.34, 0.34, 19)
    vol_q = truth.vol(kq).copy()
    vol_q[kq <= -0.28] += 0.015  # arbitraged put-wing bump (~150 vol bp)
    w_q = (vol_q**2) * TAU
    off = calibrate_sigmoid(kq, w_q, TAU, n_cores=2, wing_penalty=0.0)
    on = calibrate_sigmoid(kq, w_q, TAU, n_cores=2, wing_penalty=100.0)
    kk = np.linspace(-0.45, 0.45, 500)
    g_off = off.gatheral_g(kk)
    g_on = on.gatheral_g(kk)
    imin = int(np.argmin(g_off))
    return {
        "kk": kk, "g_off": g_off, "g_on": g_on, "kq": kq,
        "k_lo": float(kq.min()), "k_hi": float(kq.max()),
        "kmin": float(kk[imin]), "gmin": float(g_off[imin]),
        "g_off_min": float(g_off.min()), "g_on_min": float(g_on.min()),
    }


def timing_case(k, w_ww) -> dict:
    """Analytic vs FD Jacobian on the R=2 final refine (matches gen_siv scope)."""
    vol_q = np.sqrt(w_ww / TAU)
    sigma_ref = _reference_vol(vol_q, k)
    z = k / (sigma_ref * np.sqrt(TAU))
    sqrt_w = np.ones_like(k)
    base = _fit(_base_init(z, w_ww / TAU), *_base_bounds(z), z, vol_q, sqrt_w, 0)
    seeds = _seed_cores(z, w_ww / TAU - _eval_v(base, z, 0), 2)
    theta0 = np.concatenate([base, *seeds])
    clo, chi = _core_bounds(z)
    lo = np.concatenate([_base_bounds(z)[0], clo, clo])
    hi = np.concatenate([_base_bounds(z)[1], chi, chi])
    theta0 = np.clip(theta0, lo, hi)

    def residuals(theta):
        mv = np.sqrt(np.maximum(_eval_v(theta, z, 2), 1e-8))
        return np.concatenate([sqrt_w * (mv - vol_q), np.sqrt(_RIDGE) * theta[6::4][:2]])

    def jac(theta):
        return siv_residual_jacobian(theta, z, 2, TAU, sqrt_w, None,
                                     MID_ANCHOR_WEIGHT, _RIDGE, None, None, np.sqrt(1e6))

    def run(j):
        best = None
        last = None
        for _ in range(4):
            t0 = time.perf_counter()
            last = least_squares(residuals, theta0, bounds=(lo, hi), jac=j,
                                 method="trf", xtol=1e-12, ftol=1e-12)
            best = (time.perf_counter() - t0) if best is None else min(best, time.perf_counter() - t0)
        return best, last

    run(jac)
    ta, ra = run(jac)
    tf, rf = run("2-point")
    return {"analytic_ms": 1e3 * ta, "fd_ms": 1e3 * tf, "speedup": tf / ta,
            "cost_diff": abs(float(ra.cost) - float(rf.cost))}


# ---------------------------------------------------------------------------
# Macros / payload
# ---------------------------------------------------------------------------
def sci(value: float, digits: int = 1) -> str:
    mant, exp = f"{value:.{digits}e}".split("e")
    return rf"\ensuremath{{{mant}\times10^{{{int(exp)}}}}}"


def write_numbers(fit0, fit2, k, vol_ww, cap, arb, timing, target_g_min, fit_g_min) -> None:
    wl, wr = fit2.wing_slopes()
    tail_g = (4.0 - _T_B * _T_B) / 16.0
    macros = ["% Auto-generated by gen_mcs_corrections.py -- do not edit."]
    add = macros.append
    add(rf"\newcommand{{\mcscorrmaxerr}}{{{float(np.max(np.abs(1e4*(fit2.vol(k)-vol_ww)))):.2f}}}")
    add(rf"\newcommand{{\mcscorrbasemaxerr}}{{{float(np.max(np.abs(1e4*(fit0.vol(k)-vol_ww)))):.2f}}}")
    add(rf"\newcommand{{\mcscorrwingL}}{{{wl:.3f}}}")
    add(rf"\newcommand{{\mcscorrwingR}}{{{wr:.3f}}}")
    add(rf"\newcommand{{\mcscorrncores}}{{{len(fit2.cores)}}}")
    add(rf"\newcommand{{\mcscorrnparam}}{{{6 + 4 * len(fit2.cores)}}}")
    add(rf"\newcommand{{\mcscorrridge}}{{{_RIDGE:g}}}")
    add(rf"\newcommand{{\mcscorrhinit}}{{{_H_INIT:.2f}}}")
    add(rf"\newcommand{{\mcscorrkappainit}}{{{_KAPPA_INIT:.1f}}}")
    add(rf"\newcommand{{\mcscorrhlo}}{{{_H_BOUNDS[0]:.2f}}}")
    add(rf"\newcommand{{\mcscorrhhi}}{{{_H_BOUNDS[1]:.1f}}}")
    add(rf"\newcommand{{\mcscorrkappalo}}{{{_KAPPA_BOUNDS[0]:.1f}}}")
    add(rf"\newcommand{{\mcscorrkappahi}}{{{_KAPPA_BOUNDS[1]:.1f}}}")
    add(rf"\newcommand{{\mcscorrtargetbeta}}{{{_T_B:.3f}}}")
    add(rf"\newcommand{{\mcscorrtargettailg}}{{{tail_g:.3f}}}")
    add(rf"\newcommand{{\mcscorrtargetgmin}}{{{target_g_min:.2f}}}")
    add(rf"\newcommand{{\mcscorrfitgmin}}{{{fit_g_min:.2f}}}")
    # capacity
    add(rf"\newcommand{{\mcscorrerrRzero}}{{{cap['ww_err'][0]:.1f}}}")
    add(rf"\newcommand{{\mcscorrerrRone}}{{{cap['ww_err'][1]:.1f}}}")
    add(rf"\newcommand{{\mcscorrerrRtwo}}{{{cap['ww_err'][2]:.1f}}}")
    add(rf"\newcommand{{\mcscorrerrRthree}}{{{cap['ww_err'][3]:.1f}}}")
    add(rf"\newcommand{{\mcscorrliqinsRthree}}{{{cap['liq_ins'][3]:.1f}}}")
    add(rf"\newcommand{{\mcscorrliqtrueRzero}}{{{cap['liq_true'][0]:.1f}}}")
    add(rf"\newcommand{{\mcscorrliqtrueRthree}}{{{cap['liq_true'][3]:.1f}}}")
    # wing arb demo
    add(rf"\newcommand{{\mcscorrarboff}}{{{arb['g_off_min']:.2f}}}")
    add(rf"\newcommand{{\mcscorrarbon}}{{{arb['g_on_min']:.2f}}}")
    # wing penalty constants
    add(rf"\newcommand{{\mcscorrwinggrid}}{{{_WING_GRID}}}")
    add(rf"\newcommand{{\mcscorrwingpad}}{{{_WING_PAD:.0f}}}")
    add(rf"\newcommand{{\mcscorrwingputfactor}}{{{_WING_PUT_FACTOR:.0f}}}")
    add(rf"\newcommand{{\mcscorrwingbase}}{{{WING_PENALTY_BASE:g}}}")
    # timing
    add(rf"\newcommand{{\mcscorranalyticms}}{{{timing['analytic_ms']:.1f}}}")
    add(rf"\newcommand{{\mcscorrfdms}}{{{timing['fd_ms']:.1f}}}")
    add(rf"\newcommand{{\mcscorrspeedup}}{{{timing['speedup']:.2f}}}")
    add(rf"\newcommand{{\mcscorrcostdiff}}{{{sci(timing['cost_diff'])}}}")
    # historical
    for key in ("oos_before", "oos_after", "cost_rtwo", "cost_rthree", "put_pct", "atm_pct",
                "wing_min_before", "wing_min_after", "abl_none_g", "abl_none_rms",
                "abl_repair_rms", "abl_penalty_rms", "abl_both_rms", "abl_flagged_pct",
                "efa_none_rms", "efa_none_g", "efa_repair_rms", "efa_repair_g",
                "efa_penalty_rms", "efa_both_rms", "liq_before", "liq_after", "liq_flagged_pct"):
        name = "mcscorr" + key.replace("_", "")
        val = HISTORICAL[key]
        add(rf"\newcommand{{\{name}}}{{{val}}}")
    add(rf"\newcommand{{\mcscorrworstz}}{{{HISTORICAL['worst_z']:.1f}}}")
    add(rf"\newcommand{{\mcscorrliqflagged}}{{{HISTORICAL['liq_flagged']}}}")
    (OUT / "mcs_corrections_tables.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")

    payload = {
        "ww_max_err_bp": float(np.max(np.abs(1e4 * (fit2.vol(k) - vol_ww)))),
        "base_max_err_bp": float(np.max(np.abs(1e4 * (fit0.vol(k) - vol_ww)))),
        "wing": [wl, wr], "capacity": cap, "wingarb": {
            "g_off_min": arb["g_off_min"], "g_on_min": arb["g_on_min"]},
        "timing": timing, "target_g_min": target_g_min, "fit_g_min": fit_g_min,
        "historical": HISTORICAL,
    }
    (OUT / "mcs_corrections_numbers.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    k = np.linspace(-0.40, 0.40, 41)
    w_ww = ww_wjets(k)[0]
    vol_ww = np.sqrt(w_ww / TAU)

    # Target must be globally clean BEFORE any fit (the earlier-revision bug).
    wide = np.linspace(-_WIDE_K, _WIDE_K, 60001)
    target_g_min = float(ww_target_g(wide).min())
    tail_g = (4.0 - _T_B * _T_B) / 16.0
    assert target_g_min > 0.0 and tail_g > 0.0, f"WW target arbitrageable: {target_g_min:.4f}"

    fit0 = calibrate_sigmoid(k, w_ww, TAU, n_cores=0)
    fit2 = calibrate_sigmoid(k, w_ww, TAU, n_cores=2)
    fit_g_min = float(fit2.gatheral_g(wide).min())
    assert fit2.is_butterfly_free(wide), f"two-core fit arbitrageable: {fit_g_min:.4f}"

    # Verify the Appendix D reference maps against production before drawing.
    base_vec = (fit2.v0, fit2.s0, fit2.k0, fit2.z0, fit2.kappa_p, fit2.kappa_c)
    cores_vec = [(c.alpha, c.c, c.h, c.kappa) for c in fit2.cores]
    zc = fit2.z(k)
    v_ref, _, _ = ref_v(zc, base_vec, cores_vec)
    v_prod, _, _ = fit2.variance_z(zc)
    np.testing.assert_allclose(v_ref, v_prod, rtol=0, atol=1e-13)
    g_ref = ref_g(zc, base_vec, cores_vec, TAU, fit2.sigma_ref)
    np.testing.assert_allclose(g_ref, fit2.gatheral_g(k), rtol=0, atol=1e-13)

    cap = capacity_case(k, w_ww, vol_ww)
    arb = wingarb_case()
    timing = timing_case(k, w_ww)

    figure_whyww(fit0, k, vol_ww)
    figure_annihilate()
    figure_superpose(fit2)
    figure_wingneutral(fit2)
    figure_capacity(cap)
    figure_wingarb(arb)
    figure_gclean(fit2)
    figure_timing(timing)
    write_numbers(fit0, fit2, k, vol_ww, cap, arb, timing, target_g_min, fit_g_min)
    print(
        f"MCS corrections figures written; R=2 WW err "
        f"{float(np.max(np.abs(1e4*(fit2.vol(k)-vol_ww)))):.2f} bp (base "
        f"{float(np.max(np.abs(1e4*(fit0.vol(k)-vol_ww)))):.2f}); speedup "
        f"{timing['speedup']:.2f}x; wing arb off {arb['g_off_min']:.2f} on {arb['g_on_min']:.2f}; "
        f"WW err vs R {cap['ww_err']}; liq true vs R {[round(x,1) for x in cap['liq_true']]}"
    )


if __name__ == "__main__":
    main()
