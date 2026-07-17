"""Figures and generated numbers for the alternative Note 02 rewrite.

The script is deliberately executable from the repository root.  All model
curves, calibrations, conversions and Jacobians come from production modules;
the only synthetic object is the explicitly labelled two-minimum stress case
used to show the geometric limitation of a single convex SVI hyperbola.

Outputs
-------
fig_svi_rewrite_anatomy.pdf
    The raw hyperbola together with its first two derivatives.
fig_svi_rewrite_raw_moves.pdf
    One-at-a-time raw-parameter perturbations.
fig_svi_rewrite_jw.pdf
    The five JW handles in the coordinates in which they actually live.
fig_svi_rewrite_inverse.pdf
    Inverse-map geometry and the singular ATM-at-the-minimum family.
fig_svi_rewrite_arbitrage.pdf
    The classical screens-pass-but-Durrleman-fails slice.
fig_svi_rewrite_recovery.pdf
    Production JW -> raw -> fit -> JW round-trip.
fig_svi_rewrite_rigidity.pdf
    A smooth two-minimum target that one convex SVI slice cannot reproduce.
fig_svi_rewrite_timing.pdf
    Analytic-vs-finite-difference Jacobian timing.
svi_rewrite_tables.tex / svi_rewrite_numbers.json
    Generated prose macros, tables and an auditable numerical payload.
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
from matplotlib.gridspec import GridSpec
from scipy.optimize import least_squares


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(OUT))

from style import PALETTE, callout, save, setup  # noqa: E402
from svi_rewrite_reference import raw_to_jw, jw_to_raw_checked  # noqa: E402
from volfit.calib.band import MID_ANCHOR_WEIGHT  # noqa: E402
from volfit.models.svi_jw.calibrate import (  # noqa: E402
    _LEE_SLOPE_MAX,
    _PENALTY,
    _init_theta,
    _penalties,
    _unpack,
    calibrate_svi,
)
from volfit.models.svi_jw.jacobian import svi_residual_jacobian  # noqa: E402
from volfit.models.svi_jw.svi import RawSVI, SVIJW, jw_to_raw  # noqa: E402


setup()
INK = PALETTE["ink"]
MUTED = PALETTE["muted"]
TEAL = PALETTE["teal"]
BLUE = PALETTE["blue"]
RUST = PALETTE["rust"]
AMBER = PALETTE["amber"]
VIOLET = PALETTE["violet"]
GREEN = PALETTE["green"]

TAU = 0.5
TARGET_JW = SVIJW(t=TAU, v=0.0425, psi=-0.25, p=0.75, c=0.25, v_tilde=0.034)

# Historical measurements are not recomputed by this figure script.  Their
# repository anchors are recorded here so the generated TeX, rather than the
# manuscript, owns the numbers.
HISTORICAL = {
    "nodes_per_regime": 1576,
    "svi_in_bp": 24.3,
    "svi_oos_bp": 26.8,
    "arb_fd_pct": 20.8,
    "arb_analytic_pct": 9.2,
    "lqd_arb_fd_pct": 28.3,
    "lqd_arb_analytic_pct": 0.0,
    "fit_fd_ms": 26.3,
    "fit_analytic_ms": 10.2,
    "source": "backend/backtest/FINDINGS_calibration_arb.md and Docs/deck/deck_template.html",
}


def panel_tag(ax, label: str) -> None:
    """Panel label inside the axes, clear of long lecture-style titles."""
    ax.text(
        0.015,
        0.975,
        label,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=11,
        fontweight="bold",
        zorder=20,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.8},
    )


def derivatives(raw: RawSVI, k: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.asarray(k, float) - raw.m
    r = np.sqrt(x * x + raw.sigma * raw.sigma)
    w = raw.total_variance(k)
    wp = raw.b * (raw.rho + x / r)
    wpp = raw.b * raw.sigma * raw.sigma / r**3
    return w, wp, wpp


def durrleman_g(raw: RawSVI, k: np.ndarray) -> np.ndarray:
    w, wp, wpp = derivatives(raw, k)
    return (
        (1.0 - k * wp / (2.0 * w)) ** 2
        - 0.25 * wp * wp * (1.0 / w + 0.25)
        + 0.5 * wpp
    )


def vertex(raw: RawSVI) -> tuple[float, float]:
    q = np.sqrt(1.0 - raw.rho * raw.rho)
    k_star = raw.m - raw.sigma * raw.rho / q
    w_star = raw.a + raw.b * raw.sigma * q
    return float(k_star), float(w_star)


def asymptotes(raw: RawSVI, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(k, float) - raw.m
    left = raw.a + raw.b * (raw.rho * x - x)
    right = raw.a + raw.b * (raw.rho * x + x)
    return left, right


def recovery_case() -> dict:
    target = jw_to_raw(TARGET_JW)
    k = np.linspace(-0.35, 0.30, 25)
    w_quotes = target.total_variance(k)
    fit = calibrate_svi(k, w_quotes, TAU)
    recovered = raw_to_jw(fit.raw, TAU)
    grid = np.linspace(-0.55, 0.50, 601)
    return {
        "target": target,
        "k": k,
        "w_quotes": w_quotes,
        "fit": fit,
        "jw": recovered,
        "grid": grid,
        "g": durrleman_g(fit.raw, grid),
    }


def timing_case(k: np.ndarray, w_quotes: np.ndarray) -> dict[str, float | int]:
    """Median-of-five warm timing of the same core residual under two Jacobians."""
    vol_quotes = np.sqrt(w_quotes / TAU)
    sqrt_weights = np.ones_like(k)

    def residual(theta: np.ndarray) -> np.ndarray:
        raw = _unpack(theta)
        model = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / TAU)
        return np.concatenate(
            (model - vol_quotes, _penalties(raw, _PENALTY, _LEE_SLOPE_MAX))
        )

    def jac(theta: np.ndarray) -> np.ndarray:
        return svi_residual_jacobian(
            theta,
            k,
            TAU,
            sqrt_weights,
            None,
            MID_ANCHOR_WEIGHT,
            _PENALTY,
            _LEE_SLOPE_MAX,
            None,
            None,
            0.0,
        )

    theta0 = _init_theta(k, w_quotes)

    def run(which) -> tuple[float, object]:
        samples: list[float] = []
        last = None
        for _ in range(6):
            start = time.perf_counter()
            last = least_squares(
                residual,
                theta0,
                jac=which,
                method="lm",
                xtol=1e-15,
                ftol=1e-15,
                gtol=1e-15,
            )
            samples.append(time.perf_counter() - start)
        return float(np.median(samples[1:])), last

    run(jac)  # import/cache warm-up
    analytic_s, analytic = run(jac)
    fd_s, fd = run("2-point")
    return {
        "analytic_ms": 1e3 * analytic_s,
        "fd_ms": 1e3 * fd_s,
        "speedup": fd_s / analytic_s,
        "analytic_cost": float(analytic.cost),
        "fd_cost": float(fd.cost),
        "cost_diff": abs(float(analytic.cost) - float(fd.cost)),
        "analytic_nfev": int(analytic.nfev),
        "fd_nfev": int(fd.nfev),
    }


def rigidity_case() -> dict:
    """Fit a smooth, positive two-minimum target with production raw SVI."""
    tau = 0.25
    k = np.linspace(-0.42, 0.42, 49)
    w = 0.018 + 0.050 * k * k - 0.010 * k + 0.010 * np.exp(-(k / 0.095) ** 2)
    fit = calibrate_svi(k, w, tau)
    iv_target = np.sqrt(w / tau)
    iv_fit = fit.raw.implied_vol(k, tau)
    error_bp = 1e4 * (iv_fit - iv_target)
    return {
        "tau": tau,
        "k": k,
        "w": w,
        "fit": fit,
        "error_bp": error_bp,
        "rms_bp": float(np.sqrt(np.mean(error_bp * error_bp))),
        "max_bp": float(np.max(np.abs(error_bp))),
    }


def figure_anatomy(raw: RawSVI) -> None:
    k = np.linspace(-0.75, 0.65, 700)
    w, wp, wpp = derivatives(raw, k)
    left, right = asymptotes(raw, k)
    k_star, w_star = vertex(raw)
    beta_l, beta_r = raw.wing_slopes()

    fig, axes = plt.subplots(1, 3, figsize=(7.8, 3.25))
    ax = axes[0]
    ax.plot(k, w, color=TEAL, label=r"$w(k)$")
    ax.plot(k[k < raw.m], left[k < raw.m], color=MUTED, ls=":")
    ax.plot(k[k > raw.m], right[k > raw.m], color=MUTED, ls=":")
    ax.scatter([k_star, 0.0], [w_star, raw.total_variance(0.0)],
               color=[RUST, AMBER], zorder=5)
    callout(ax, r"minimum $k_\star$", (k_star, w_star), (-0.58, w_star + 0.026))
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"total variance $w$")
    ax.set_title("one rounded hyperbola")
    panel_tag(ax, "A")

    ax = axes[1]
    ax.axhline(-beta_l, color=MUTED, ls=":")
    ax.axhline(beta_r, color=MUTED, ls=":")
    ax.plot(k, wp, color=BLUE)
    ax.text(-0.70, -beta_l + 0.004, r"$-\beta_L$", color=MUTED, fontsize=9)
    ax.text(0.47, beta_r + 0.004, r"$\beta_R$", color=MUTED, fontsize=9)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"$w'(k)$")
    ax.set_title("the slope turns once")
    panel_tag(ax, "B")

    ax = axes[2]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(k, 0.0, wpp, color=GREEN, alpha=0.15)
    ax.plot(k, wpp, color=GREEN)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"$w''(k)$")
    ax.set_title(r"strict convexity: $w''>0$")
    panel_tag(ax, "C")
    fig.subplots_adjust(wspace=0.38)
    save(fig, OUT / "fig_svi_rewrite_anatomy.pdf")


def figure_raw_moves(raw: RawSVI) -> None:
    k = np.linspace(-0.48, 0.42, 450)
    variants = [
        (r"raise $a$", RawSVI(raw.a + 0.008, raw.b, raw.rho, raw.m, raw.sigma),
         "vertical shift"),
        (r"increase $b$", RawSVI(raw.a, 1.35 * raw.b, raw.rho, raw.m, raw.sigma),
         "both wings steepen"),
        (r"increase $\rho$", RawSVI(raw.a, raw.b, raw.rho + 0.32, raw.m, raw.sigma),
         "left flattens, right steepens"),
        (r"move $m$ right", RawSVI(raw.a, raw.b, raw.rho, raw.m + 0.09, raw.sigma),
         "the rounded core translates"),
        (r"increase width $s$", RawSVI(raw.a, raw.b, raw.rho, raw.m, 1.8 * raw.sigma),
         "the turn becomes broader"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(7.6, 5.4), sharex=True)
    for i, (title, moved, lesson) in enumerate(variants):
        ax = axes.flat[i]
        ax.plot(k, raw.total_variance(k), color=MUTED, lw=1.5, label="baseline")
        ax.plot(k, moved.total_variance(k), color=TEAL, label="one change")
        ax.set_title(title, fontsize=11)
        ax.text(0.04, 0.06, lesson, transform=ax.transAxes, fontsize=8.5, color=MUTED)
        if i in (0, 3):
            ax.set_ylabel(r"$w(k)$")
        if i >= 3:
            ax.set_xlabel(r"$k$")
        panel_tag(ax, chr(ord("A") + i))
    ax = axes.flat[-1]
    ax.axis("off")
    ax.text(
        0.04,
        0.82,
        "Raw coordinates are excellent\nfor evaluation and differentiation,\n"
        "but only $a$ and $m$ act in isolation.\nThe other knobs move several\n"
        "visible features at once.",
        va="top",
        fontsize=11,
        color=INK,
        linespacing=1.35,
    )
    handles, labels = axes.flat[0].get_legend_handles_labels()
    ax.legend(handles, labels, loc="lower left")
    fig.subplots_adjust(wspace=0.28, hspace=0.38)
    save(fig, OUT / "fig_svi_rewrite_raw_moves.pdf")


def figure_jw(raw: RawSVI, jw: dict[str, float]) -> None:
    k = np.linspace(-0.48, 0.42, 600)
    iv = 100.0 * raw.implied_vol(k, TAU)
    w = raw.total_variance(k)
    k_star, _ = vertex(raw)
    min_iv = 100.0 * np.sqrt(jw["v_tilde"])
    atm_iv = 100.0 * np.sqrt(jw["v"])
    tangent_slope = 100.0 * jw["psi"] / np.sqrt(TAU)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.65))
    ax = axes[0]
    ax.plot(k, iv, color=TEAL)
    kt = np.linspace(-0.10, 0.10, 2)
    ax.plot(kt, atm_iv + tangent_slope * kt, color=AMBER, ls="--", lw=1.5)
    ax.scatter([0.0, k_star], [atm_iv, min_iv], color=[RUST, BLUE], zorder=5)
    callout(ax, r"ATM $\sqrt{v}$", (0.0, atm_iv), (0.11, atm_iv + 2.4))
    callout(ax, r"minimum $\sqrt{\widetilde{v}}$", (k_star, min_iv),
            (k_star + 0.12, min_iv - 0.2))
    ax.text(-0.43, 26.0, r"tangent slope $\psi/\sqrt{\tau}$", color=AMBER, fontsize=9)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title("level, skew and minimum live in IV")
    panel_tag(ax, "A")

    ax = axes[1]
    left, right = asymptotes(raw, k)
    ax.plot(k, w, color=TEAL)
    ax.plot(k[k < raw.m], left[k < raw.m], color=MUTED, ls=":")
    ax.plot(k[k > raw.m], right[k > raw.m], color=MUTED, ls=":")
    beta_l = jw["p"] * np.sqrt(jw["v"] * TAU)
    beta_r = jw["c"] * np.sqrt(jw["v"] * TAU)
    ax.annotate(
        rf"put slope $\beta_L=p\sqrt{{v\tau}}={beta_l:.3f}$",
        xy=(-0.39, raw.total_variance(-0.39)),
        xytext=(-0.45, raw.total_variance(-0.39) + 0.025),
        arrowprops={"arrowstyle": "->", "color": MUTED},
        fontsize=8.7,
        color=MUTED,
    )
    ax.annotate(
        rf"call slope $\beta_R=c\sqrt{{v\tau}}={beta_r:.3f}$",
        xy=(0.32, raw.total_variance(0.32)),
        xytext=(0.02, raw.total_variance(0.32) + 0.026),
        arrowprops={"arrowstyle": "->", "color": MUTED},
        fontsize=8.7,
        color=MUTED,
    )
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("the wing handles live in total variance")
    panel_tag(ax, "B")
    fig.subplots_adjust(wspace=0.32)
    save(fig, OUT / "fig_svi_rewrite_jw.pdf")


def figure_inverse(raw: RawSVI) -> None:
    jw = raw_to_jw(raw, TAU)
    rho = raw.rho
    chi = raw.m / np.sqrt(raw.m * raw.m + raw.sigma * raw.sigma)
    angle = np.linspace(-np.pi / 2.0, np.pi / 2.0, 400)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.65))
    ax = axes[0]
    ax.plot(np.sin(angle), np.cos(angle), color=MUTED)
    u_rho = np.array([rho, np.sqrt(1.0 - rho * rho)])
    u_chi = np.array([chi, np.sqrt(1.0 - chi * chi)])
    ax.plot([0, u_rho[0]], [0, u_rho[1]], color=BLUE)
    ax.plot([0, u_chi[0]], [0, u_chi[1]], color=RUST)
    ax.scatter([u_rho[0], u_chi[0]], [u_rho[1], u_chi[1]],
               color=[BLUE, RUST], zorder=5)
    ax.text(u_rho[0] - 0.18, u_rho[1] + 0.06, r"$u_\rho$", color=BLUE)
    ax.text(u_chi[0] + 0.04, u_chi[1] + 0.06, r"$u_\chi$", color=RUST)
    ax.annotate(
        r"gap $1-u_\rho\!\cdot u_\chi$",
        xy=(0.0, 0.96),
        xytext=(-0.60, 0.35),
        arrowprops={"arrowstyle": "->", "color": MUTED},
        fontsize=9,
        color=MUTED,
    )
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-1.08, 1.08)
    ax.set_ylim(0.0, 1.12)
    ax.set_xlabel(r"first coordinate: $\rho$ or $\chi$")
    ax.set_ylabel("positive square root")
    ax.set_title("the inverse denominator is an angle gap")
    panel_tag(ax, "A")

    ax = axes[1]
    tau, v, p, c = 0.5, 0.04, 0.5, 0.3
    w0 = v * tau
    b = 0.5 * np.sqrt(w0) * (p + c)
    rho0 = (c - p) / (c + p)
    k = np.linspace(-0.55, 0.50, 600)
    for width, color in zip((0.05, 0.15, 0.40), (RUST, TEAL, VIOLET)):
        m = rho0 * width / np.sqrt(1.0 - rho0 * rho0)
        a = w0 - b * width * np.sqrt(1.0 - rho0 * rho0)
        candidate = RawSVI(a=a, b=b, rho=rho0, m=m, sigma=width)
        ax.plot(k, 100.0 * candidate.implied_vol(k, tau), color=color,
                label=rf"width $s={width:.2f}$")
    ax.scatter([0.0], [100.0 * np.sqrt(v)], color=INK, zorder=6)
    ax.axvline(0.0, color=MUTED, lw=0.8, ls=":")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title(r"same $(v,0,p,c,v)$, different bodies")
    ax.legend(loc="upper right")
    panel_tag(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_svi_rewrite_inverse.pdf")


def figure_arbitrage(counter: RawSVI, result: dict[str, float]) -> None:
    k = np.linspace(-1.5, 1.5, 1600)
    w = counter.total_variance(k)
    g = durrleman_g(counter, k)
    k_star, w_star = vertex(counter)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.35))
    ax = axes[0]
    ax.plot(k, w, color=TEAL)
    ax.scatter([k_star], [w_star], color=RUST, zorder=5)
    ax.text(
        0.04,
        0.93,
        rf"minimum $={result['min_var']:.4f}>0$" + "\n" +
        rf"Lee slope $={result['lee']:.3f}<2$",
        transform=ax.transAxes,
        va="top",
        fontsize=9.3,
        color=GREEN,
    )
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"$w(k)$")
    ax.set_title("both cheap screens pass")
    panel_tag(ax, "A")

    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(k, g, 0.0, where=g < 0.0, color=RUST, alpha=0.20)
    ax.plot(k, g, color=BLUE)
    i = int(np.argmin(g))
    callout(ax, rf"$g={g[i]:.3f}$", (k[i], g[i]), (0.10, -0.18))
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title("but the implied density turns negative")
    panel_tag(ax, "B")
    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_svi_rewrite_arbitrage.pdf")


def figure_recovery(case: dict) -> None:
    target: RawSVI = case["target"]
    fit = case["fit"]
    k = case["k"]
    w_quotes = case["w_quotes"]
    grid = case["grid"]
    g = case["g"]

    fig = plt.figure(figsize=(7.7, 5.3))
    gs = GridSpec(2, 2, figure=fig, height_ratios=[1.45, 1.0], hspace=0.42, wspace=0.32)
    ax = fig.add_subplot(gs[0, :])
    ax.plot(grid, 100.0 * target.implied_vol(grid, TAU), color=MUTED, lw=2.5,
            label="production JW -> raw target")
    ax.plot(grid, 100.0 * fit.raw.implied_vol(grid, TAU), color=TEAL, ls="--",
            label="raw-SVI refit")
    ax.scatter(k, 100.0 * np.sqrt(w_quotes / TAU), color=RUST, s=18,
               zorder=5, label="noise-free quotes")
    ax.set_ylabel("implied volatility (%)")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.legend(ncol=3, loc="upper center")
    ax.set_title("the two coordinate systems round-trip through the production fit")
    panel_tag(ax, "A")

    ax = fig.add_subplot(gs[1, 0])
    err = 1e17 * (fit.raw.implied_vol(k, TAU) - np.sqrt(w_quotes / TAU))
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.stem(k, err, linefmt=RUST, markerfmt="o", basefmt=" ")
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"fit error ($10^{-13}$ vol bp)")
    ax.set_title("quote errors")
    panel_tag(ax, "B")

    ax = fig.add_subplot(gs[1, 1])
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(grid, 0.0, g, where=g >= 0.0, color=GREEN, alpha=0.14)
    ax.plot(grid, g, color=GREEN)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"$g(k)$")
    ax.set_title("butterfly diagnostic on the case grid")
    panel_tag(ax, "C")
    save(fig, OUT / "fig_svi_rewrite_recovery.pdf")


def figure_rigidity(case: dict) -> None:
    tau = case["tau"]
    k = case["k"]
    w = case["w"]
    fit = case["fit"]
    err = case["error_bp"]
    grid = np.linspace(k.min(), k.max(), 700)

    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True,
                             gridspec_kw={"height_ratios": [1.55, 1.0]})
    ax = axes[0]
    ax.plot(k, w, color=RUST, lw=2.4, label="two-minimum target")
    ax.plot(grid, fit.raw.total_variance(grid), color=TEAL, label="best raw-SVI fit")
    ax.scatter(k, w, color=RUST, s=10, alpha=0.45)
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("a single convex hyperbola cannot turn twice")
    ax.legend(loc="upper center", ncol=2)
    panel_tag(ax, "A")

    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(k, 0.0, err, color=RUST, alpha=0.12)
    ax.plot(k, err, color=RUST)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("IV error (vol bp)")
    ax.set_title(
        rf"geometric miss: RMS {case['rms_bp']:.1f} bp, max {case['max_bp']:.1f} bp",
        fontsize=10.5,
    )
    panel_tag(ax, "B")
    fig.subplots_adjust(hspace=0.18)
    save(fig, OUT / "fig_svi_rewrite_rigidity.pdf")


def figure_timing(timing: dict[str, float | int]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4))
    ax = axes[0]
    vals = [timing["fd_ms"], timing["analytic_ms"]]
    bars = ax.bar([0, 1], vals, color=[MUTED, TEAL], width=0.58)
    ax.set_xticks([0, 1], ["finite difference", "analytic"])
    ax.set_ylabel("milliseconds per synthetic fit")
    ax.set_title("fresh 25-quote microbenchmark")
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2f}",
                ha="center", va="bottom", fontsize=9)
    panel_tag(ax, "A")

    ax = axes[1]
    vals = [HISTORICAL["fit_fd_ms"], HISTORICAL["fit_analytic_ms"]]
    bars = ax.bar([0, 1], vals, color=[MUTED, TEAL], width=0.58)
    ax.set_xticks([0, 1], ["before", "analytic core"])
    ax.set_ylabel("milliseconds per real node")
    ax.set_title("historical spike-regime measurement")
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.1f}",
                ha="center", va="bottom", fontsize=9)
    panel_tag(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_svi_rewrite_timing.pdf")


def tex_table(rows: list[tuple[str, float]], first_heading: str) -> str:
    lines = [r"\begin{tabular}{lr}", r"\toprule", first_heading + r"\\", r"\midrule"]
    for name, value in rows:
        lines.append(rf"${name}$ & {value:+.6f}\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return " ".join(lines)


def write_numbers(case: dict, timing: dict, rigidity: dict, counter_result: dict) -> None:
    target: RawSVI = case["target"]
    fit = case["fit"]
    jw = case["jw"]
    beta_l, beta_r = fit.raw.wing_slopes()
    k_g = case["grid"][int(np.argmin(case["g"]))]
    target_vec = np.array([TARGET_JW.v, TARGET_JW.psi, TARGET_JW.p,
                           TARGET_JW.c, TARGET_JW.v_tilde])
    recovered_vec = np.array([jw["v"], jw["psi"], jw["p"], jw["c"], jw["v_tilde"]])
    jw_roundtrip = float(np.max(np.abs(target_vec - recovered_vec)))

    raw_rows = [
        ("a", fit.raw.a),
        ("b", fit.raw.b),
        (r"\rho", fit.raw.rho),
        ("m", fit.raw.m),
        ("s", fit.raw.sigma),
    ]
    jw_rows = [
        ("v", jw["v"]),
        (r"\psi", jw["psi"]),
        ("p", jw["p"]),
        ("c", jw["c"]),
        (r"\widetilde v", jw["v_tilde"]),
    ]

    macros = ["% Auto-generated by gen_svi_rewrite.py -- do not edit."]
    add = macros.append
    add(rf"\newcommand{{\svirwmaxerr}}{{{1e4 * fit.max_iv_error:.1e}}}")
    add(rf"\newcommand{{\svirwnfev}}{{{fit.n_evaluations:d}}}")
    add(rf"\newcommand{{\svirwjwerr}}{{{jw_roundtrip:.1e}}}")
    add(rf"\newcommand{{\svirwgmin}}{{{float(np.min(case['g'])):.3f}}}")
    add(rf"\newcommand{{\svirwgminloc}}{{{k_g:.2f}}}")
    add(rf"\newcommand{{\svirwwingL}}{{{beta_l:.4f}}}")
    add(rf"\newcommand{{\svirwwingR}}{{{beta_r:.4f}}}")
    add(rf"\newcommand{{\svirwcountermin}}{{{counter_result['min_var']:.4f}}}")
    add(rf"\newcommand{{\svirwcounterlee}}{{{counter_result['lee']:.3f}}}")
    add(rf"\newcommand{{\svirwcounterg}}{{{counter_result['gmin']:.3f}}}")
    add(rf"\newcommand{{\svirwcounterk}}{{{counter_result['kmin']:.2f}}}")
    add(rf"\newcommand{{\svirwrigidrms}}{{{rigidity['rms_bp']:.1f}}}")
    add(rf"\newcommand{{\svirwrigidmax}}{{{rigidity['max_bp']:.1f}}}")
    add(rf"\newcommand{{\svirwanalyticms}}{{{timing['analytic_ms']:.2f}}}")
    add(rf"\newcommand{{\svirwfdms}}{{{timing['fd_ms']:.2f}}}")
    add(rf"\newcommand{{\svirwspeedup}}{{{timing['speedup']:.2f}}}")
    add(rf"\newcommand{{\svirwcostdiff}}{{{timing['cost_diff']:.1e}}}")
    add(rf"\newcommand{{\svirwhistbefore}}{{{HISTORICAL['fit_fd_ms']:.1f}}}")
    add(rf"\newcommand{{\svirwhistafter}}{{{HISTORICAL['fit_analytic_ms']:.1f}}}")
    add(rf"\newcommand{{\svirwhistspeedup}}{{{HISTORICAL['fit_fd_ms']/HISTORICAL['fit_analytic_ms']:.2f}}}")
    add(rf"\newcommand{{\svirwhistin}}{{{HISTORICAL['svi_in_bp']:.1f}}}")
    add(rf"\newcommand{{\svirwhistoos}}{{{HISTORICAL['svi_oos_bp']:.1f}}}")
    add(rf"\newcommand{{\svirwnodes}}{{{HISTORICAL['nodes_per_regime']:,}}}")
    add(rf"\newcommand{{\svirwarbold}}{{{HISTORICAL['arb_fd_pct']:.1f}}}")
    add(rf"\newcommand{{\svirwarbnew}}{{{HISTORICAL['arb_analytic_pct']:.1f}}}")
    add(rf"\newcommand{{\svirwlqdarbold}}{{{HISTORICAL['lqd_arb_fd_pct']:.1f}}}")
    add(rf"\newcommand{{\svirwlqdarbnew}}{{{HISTORICAL['lqd_arb_analytic_pct']:.1f}}}")
    add(rf"\newcommand{{\svirwpenalty}}{{{_PENALTY:g}}}")
    add(rf"\newcommand{{\svirwleecap}}{{{_LEE_SLOPE_MAX:.1f}}}")
    add(r"\newcommand{\svirwrawtable}{" + tex_table(raw_rows, r"Parameter & Value") + "}")
    add(r"\newcommand{\svirwjwtable}{" + tex_table(jw_rows, r"Handle & Value") + "}")
    (OUT / "svi_rewrite_tables.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")

    payload = {
        "target_raw": target.__dict__,
        "fit_raw": fit.raw.__dict__,
        "recovered_jw": jw,
        "max_iv_error_bp": 1e4 * fit.max_iv_error,
        "jw_roundtrip_max_abs": jw_roundtrip,
        "recovery_g_min": float(np.min(case["g"])),
        "timing": timing,
        "rigidity": {"rms_bp": rigidity["rms_bp"], "max_bp": rigidity["max_bp"]},
        "counterexample": counter_result,
        "historical": HISTORICAL,
    }
    (OUT / "svi_rewrite_numbers.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def main() -> None:
    case = recovery_case()
    raw: RawSVI = case["fit"].raw
    jw = case["jw"]

    # Execute Appendix C's checked reference inverse against production on
    # several regular-domain points before any figure is published.
    reference_cases = [
        TARGET_JW,
        SVIJW(t=0.25, v=0.09, psi=0.10, p=0.40, c=0.60, v_tilde=0.07),
        SVIJW(t=2.0, v=0.03, psi=-0.05, p=0.30, c=0.28, v_tilde=0.028),
    ]
    for point in reference_cases:
        prod, ref = jw_to_raw(point), jw_to_raw_checked(point)
        np.testing.assert_allclose(
            [ref.a, ref.b, ref.rho, ref.m, ref.sigma],
            [prod.a, prod.b, prod.rho, prod.m, prod.sigma],
            rtol=2e-12, atol=2e-13,
        )

    counter = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
    counter_grid = np.linspace(-1.5, 1.5, 4001)
    counter_g = durrleman_g(counter, counter_grid)
    counter_result = {
        "min_var": vertex(counter)[1],
        "lee": counter.b * (1.0 + abs(counter.rho)),
        "gmin": float(np.min(counter_g)),
        "kmin": float(counter_grid[int(np.argmin(counter_g))]),
    }
    timing = timing_case(case["k"], case["w_quotes"])
    rigidity = rigidity_case()

    figure_anatomy(raw)
    figure_raw_moves(raw)
    figure_jw(raw, jw)
    figure_inverse(raw)
    figure_arbitrage(counter, counter_result)
    figure_recovery(case)
    figure_rigidity(rigidity)
    figure_timing(timing)
    write_numbers(case, timing, rigidity, counter_result)
    print(
        "SVI rewrite figures written; recovery max error "
        f"{1e4 * case['fit'].max_iv_error:.3f} vol bp, fresh Jacobian speed-up "
        f"{timing['speedup']:.2f}x"
    )


if __name__ == "__main__":
    main()
