"""Figures and generated numbers for the moment-bound edition of Note 02.

Angle: *the wings and the belly.*  A smile's wings are a reading of the
risk-neutral distribution's tails --- Lee's moment formula caps their slope at
2 --- and every cheap no-arbitrage guarantee raw SVI can give lives in the
wings.  The belly (the curvature near the money) is where a Lee-clean slice can
still hide butterfly arbitrage and where the jump-wing handles lose
identification.

Every curve, calibration, conversion and Jacobian comes from production
modules; the only synthetic objects are the two explicitly-labelled stress
targets (the two-minimum rigidity case and the wing-slope comparison), used to
expose geometric limits, never to stand in for a fit.

Outputs (next to this script)
-----------------------------
fig_svimom_wings.pdf      the far field is two straight rays; w(k)/|k| -> beta
fig_svimom_moments.pdf    Lee's cap inside the density: g(+-inf) = (4-beta^2)/16
fig_svimom_belly.pdf      Axel Vogt: clean tails, negative density in the belly
fig_svimom_handles.pdf    two tail handles p,c and three belly handles v,psi,vt
fig_svimom_singular.pdf   the psi=0 belly blind spot: same tails, different body
fig_svimom_entangle.pdf   raw parameters mix tail and belly moves
fig_svimom_recovery.pdf   production JW -> raw -> fit -> JW laboratory round trip
fig_svimom_rigidity.pdf   one belly, one turn: a two-minimum target defeats SVI
fig_svimom_timing.pdf     analytic vs finite-difference Jacobian timing
svi_moments_tables.tex    prose macros + recovered raw/JW tables
svi_moments_numbers.json  auditable numerical payload
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

from style import PALETTE, label_panel, save, setup  # noqa: E402
from svi_moments_reference import jw_to_raw_checked, raw_to_jw  # noqa: E402
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
#: Axel Vogt's classical screens-pass-but-arbitrageable slice (Gatheral-Jacquier
#: Example 3.1): both cheap tail screens pass, yet the belly density goes negative.
COUNTER = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)

# Historical measurements are NOT recomputed by this figure script; their
# repository anchors are recorded so the generated TeX, not the manuscript, owns
# the numbers.
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


# ---------------------------------------------------------------------------
# Geometry helpers (all closed-form from the raw slice)
# ---------------------------------------------------------------------------
def derivatives(raw: RawSVI, k: np.ndarray):
    x = np.asarray(k, float) - raw.m
    r = np.sqrt(x * x + raw.sigma * raw.sigma)
    w = raw.total_variance(k)
    wp = raw.b * (raw.rho + x / r)
    wpp = raw.b * raw.sigma * raw.sigma / r**3
    return w, wp, wpp


def durrleman_g(raw: RawSVI, k: np.ndarray) -> np.ndarray:
    w, wp, wpp = derivatives(raw, k)
    return (1.0 - k * wp / (2.0 * w)) ** 2 - 0.25 * wp * wp * (1.0 / w + 0.25) + 0.5 * wpp


def vertex(raw: RawSVI):
    q = np.sqrt(1.0 - raw.rho * raw.rho)
    return float(raw.m - raw.sigma * raw.rho / q), float(raw.a + raw.b * raw.sigma * q)


def asymptotes(raw: RawSVI, k: np.ndarray):
    x = np.asarray(k, float) - raw.m
    return raw.a + raw.b * (raw.rho - 1.0) * x, raw.a + raw.b * (raw.rho + 1.0) * x


# ---------------------------------------------------------------------------
# Production round trip, timing, and the two labelled stress cases
# ---------------------------------------------------------------------------
def recovery_case() -> dict:
    target = jw_to_raw(TARGET_JW)
    k = np.linspace(-0.35, 0.30, 25)
    w_quotes = target.total_variance(k)
    fit = calibrate_svi(k, w_quotes, TAU)
    grid = np.linspace(-0.55, 0.50, 601)
    return {
        "target": target,
        "k": k,
        "w_quotes": w_quotes,
        "fit": fit,
        "jw": raw_to_jw(fit.raw, TAU),
        "grid": grid,
        "g": durrleman_g(fit.raw, grid),
    }


def timing_case(k: np.ndarray, w_quotes: np.ndarray) -> dict:
    """Median-of-five warm timing of the same core residual under two Jacobians."""
    vol_quotes = np.sqrt(w_quotes / TAU)
    sqrt_weights = np.ones_like(k)

    def residual(theta):
        raw = _unpack(theta)
        model = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / TAU)
        return np.concatenate((model - vol_quotes, _penalties(raw, _PENALTY, _LEE_SLOPE_MAX)))

    def jac(theta):
        return svi_residual_jacobian(
            theta, k, TAU, sqrt_weights, None, MID_ANCHOR_WEIGHT,
            _PENALTY, _LEE_SLOPE_MAX, None, None, 0.0,
        )

    theta0 = _init_theta(k, w_quotes)

    def run(which):
        samples, last = [], None
        for _ in range(6):
            start = time.perf_counter()
            last = least_squares(residual, theta0, jac=which, method="lm",
                                 xtol=1e-15, ftol=1e-15, gtol=1e-15)
            samples.append(time.perf_counter() - start)
        return float(np.median(samples[1:])), last

    run(jac)  # warm-up
    analytic_s, analytic = run(jac)
    fd_s, fd = run("2-point")
    return {
        "analytic_ms": 1e3 * analytic_s,
        "fd_ms": 1e3 * fd_s,
        "speedup": fd_s / analytic_s,
        "cost_diff": abs(float(analytic.cost) - float(fd.cost)),
    }


def rigidity_case() -> dict:
    """A smooth, positive two-minimum target that one convex SVI slice cannot fit."""
    tau = 0.25
    k = np.linspace(-0.42, 0.42, 49)
    w = 0.018 + 0.050 * k * k - 0.010 * k + 0.010 * np.exp(-(k / 0.095) ** 2)
    fit = calibrate_svi(k, w, tau)
    iv_target = np.sqrt(w / tau)
    error_bp = 1e4 * (fit.raw.implied_vol(k, tau) - iv_target)
    return {
        "tau": tau, "k": k, "w": w, "fit": fit, "error_bp": error_bp,
        "rms_bp": float(np.sqrt(np.mean(error_bp * error_bp))),
        "max_bp": float(np.max(np.abs(error_bp))),
    }


def counter_facts() -> dict:
    grid = np.linspace(-1.6, 1.6, 4001)
    g = durrleman_g(COUNTER, grid)
    beta_l, beta_r = COUNTER.wing_slopes()
    return {
        "min_var": vertex(COUNTER)[1],
        "lee": COUNTER.b * (1.0 + abs(COUNTER.rho)),
        "gmin": float(np.min(g)),
        "kmin": float(grid[int(np.argmin(g))]),
        "g_tail_l": (4.0 - beta_l * beta_l) / 16.0,
        "g_tail_r": (4.0 - beta_r * beta_r) / 16.0,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def figure_wings(raw: RawSVI) -> None:
    """Thesis figure: the far field is two straight rays; w/|k| -> beta."""
    beta_l, beta_r = raw.wing_slopes()
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))

    ax = axes[0]
    k = np.linspace(-1.2, 1.1, 700)
    w = raw.total_variance(k)
    left, right = asymptotes(raw, k)
    ax.plot(k, w, color=TEAL, zorder=4)
    ax.plot(k[k < raw.m], left[k < raw.m], color=MUTED, ls=":")
    ax.plot(k[k > raw.m], right[k > raw.m], color=MUTED, ls=":")
    ax.set_ylim(0.0, float(w.max()) * 1.02)
    ax.annotate(rf"left ray, slope $\beta_L=b(1-\rho)={beta_l:.3f}$",
                xy=(-1.05, raw.total_variance(-1.05)),
                xytext=(-1.12, float(w.max()) * 0.60),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.6, color=MUTED)
    ax.annotate(rf"right ray, slope $\beta_R=b(1+\rho)={beta_r:.3f}$",
                xy=(1.0, raw.total_variance(1.0)),
                xytext=(-0.55, float(w.max()) * 0.86),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.6, color=MUTED)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("the wings are two straight rays")
    label_panel(ax, "A")

    ax = axes[1]
    kp = np.linspace(0.3, 30.0, 800)
    ax.plot(kp, raw.total_variance(-kp) / kp, color=RUST, label=r"$w(-k)/k$ (put wing)")
    ax.plot(kp, raw.total_variance(kp) / kp, color=BLUE, label=r"$w(k)/k$ (call wing)")
    ax.axhline(beta_l, color=RUST, ls=":", lw=1.1)
    ax.axhline(beta_r, color=BLUE, ls=":", lw=1.1)
    ax.text(29.0, beta_l + 0.005, r"$\beta_L$", color=RUST, ha="right", fontsize=9.5)
    ax.text(29.0, beta_r + 0.005, r"$\beta_R$", color=BLUE, ha="right", fontsize=9.5)
    ax.set_xscale("log")
    ax.set_ylim(0.0, max(beta_l, beta_r) * 1.55)
    ax.set_xlabel(r"$|k|$ (log scale)")
    ax.set_ylabel(r"$w/|k|$")
    ax.set_title(r"each wing reports one number")
    ax.legend(loc="upper right", fontsize=8.5)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.32)
    save(fig, OUT / "fig_svimom_wings.pdf")


def figure_moments() -> None:
    """Mechanism: the wing slope sets the sign of the density in the tail."""
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))

    ax = axes[0]
    beta = np.linspace(0.0, 3.0, 400)
    tail = (4.0 - beta * beta) / 16.0
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.plot(beta, tail, color=TEAL)
    ax.fill_between(beta, tail, 0.0, where=beta > 2.0, color=RUST, alpha=0.18)
    ax.axvline(2.0, color=MUTED, ls=":", lw=1.1)
    ax.scatter([2.0], [0.0], color=RUST, zorder=6)
    ax.annotate(r"Lee's cap $\beta=2$", xy=(2.0, 0.0), xytext=(2.05, 0.12),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=9, color=MUTED)
    ax.text(2.45, -0.10, "negative tail\ndensity", color=RUST, fontsize=8.6, ha="center")
    ax.set_xlabel(r"asymptotic wing slope $\beta$")
    ax.set_ylabel(r"$\lim_{|k|\to\infty} g(k)=(4-\beta^2)/16$")
    ax.set_title("the tail of the density factor")
    label_panel(ax, "A")

    ax = axes[1]
    # Follow the wing far out (log axis) so the two TAIL limits, the point of
    # the panel, are actually reached rather than squashed by the near spike.
    k = np.linspace(2.0, 120.0, 1200)
    for beta_val, color, lab in ((1.60, TEAL, r"$\beta=1.6$ (Lee-clean)"),
                                 (2.30, RUST, r"$\beta=2.3$ (over the cap)")):
        # symmetric wings (rho=0): both slopes equal b, so b = beta.
        slice_ = RawSVI(a=0.02, b=beta_val, rho=0.0, m=0.0, sigma=0.08)
        tail = (4.0 - beta_val * beta_val) / 16.0
        ax.plot(k, durrleman_g(slice_, k), color=color, label=lab)
        ax.axhline(tail, color=color, ls=":", lw=1.0)
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.set_xscale("log")
    ax.set_ylim(-0.16, 0.16)
    ax.text(120.0, 0.100, r"$\frac{4-\beta^2}{16}>0$", color=TEAL, ha="right", fontsize=9)
    ax.text(120.0, -0.068, r"$\frac{4-\beta^2}{16}<0$", color=RUST, ha="right", fontsize=9)
    ax.set_xlabel(r"log-moneyness $k$ (call wing)")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title("carried far into a slice's wing")
    ax.legend(loc="upper left", fontsize=8.5)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_svimom_moments.pdf")


def figure_belly(facts: dict) -> None:
    """Honesty centrepiece: clean tails, negative density in the belly."""
    k = np.linspace(-1.6, 1.6, 1600)
    w = COUNTER.total_variance(k)
    g = durrleman_g(COUNTER, k)
    k_star, w_star = vertex(COUNTER)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.35))
    ax = axes[0]
    ax.plot(k, w, color=TEAL)
    ax.scatter([k_star], [w_star], color=RUST, zorder=5)
    ax.text(0.03, 0.94,
            rf"minimum $={facts['min_var']:.4f}>0$" + "\n" +
            rf"Lee slope $={facts['lee']:.3f}<2$",
            transform=ax.transAxes, va="top", fontsize=9.2, color=GREEN)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("both cheap tail screens pass")
    label_panel(ax, "A")

    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.axhline(facts["g_tail_l"], color=MUTED, ls=":", lw=1.0)
    ax.plot(k, g, color=BLUE)
    ax.fill_between(k, g, 0.0, where=g < 0.0, color=RUST, alpha=0.22)
    i = int(np.argmin(g))
    ax.scatter([k[i]], [g[i]], color=RUST, zorder=6)
    ax.annotate(rf"$g={facts['gmin']:.3f}$ at $k\approx{facts['kmin']:.2f}$",
                xy=(k[i], g[i]), xytext=(0.15, -0.16),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=9, color=RUST)
    ax.text(-1.55, facts["g_tail_l"] + 0.012,
            r"both tails $g\to(4-\beta^2)/16>0$", color=MUTED, fontsize=8.4)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title("but the belly density turns negative")
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_svimom_belly.pdf")


def figure_handles(raw: RawSVI, jw: dict) -> None:
    """Two tail handles p,c live in total variance; three belly handles in IV."""
    k = np.linspace(-0.48, 0.42, 600)
    k_star, _ = vertex(raw)
    atm_iv = 100.0 * np.sqrt(jw["v"])
    min_iv = 100.0 * np.sqrt(jw["v_tilde"])
    tangent = 100.0 * jw["psi"] / np.sqrt(TAU)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.65))
    ax = axes[0]
    ax.plot(k, 100.0 * raw.implied_vol(k, TAU), color=TEAL)
    kt = np.linspace(-0.10, 0.10, 2)
    ax.plot(kt, atm_iv + tangent * kt, color=AMBER, ls="--", lw=1.5)
    ax.scatter([0.0, k_star], [atm_iv, min_iv], color=[RUST, BLUE], zorder=5)
    ax.set_ylim(top=float(100.0 * raw.implied_vol(-0.48, TAU)) + 2.2)
    ax.annotate(r"ATM $\sqrt{v}$", xy=(0.0, atm_iv), xytext=(0.10, atm_iv + 2.2),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=9, color=RUST)
    ax.annotate(r"minimum $\sqrt{\widetilde{v}}$", xy=(k_star, min_iv),
                xytext=(k_star + 0.11, min_iv - 0.3),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=9, color=BLUE)
    ax.text(-0.455, 24.4, r"slope $\psi/\sqrt{\tau}$", color=AMBER, fontsize=9)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title(r"three belly handles $v,\psi,\widetilde v$ in IV")
    label_panel(ax, "A")

    ax = axes[1]
    w = raw.total_variance(k)
    left, right = asymptotes(raw, k)
    ax.plot(k, w, color=TEAL)
    ax.plot(k[k < raw.m], left[k < raw.m], color=MUTED, ls=":")
    ax.plot(k[k > raw.m], right[k > raw.m], color=MUTED, ls=":")
    beta_l = jw["p"] * np.sqrt(jw["v"] * TAU)
    beta_r = jw["c"] * np.sqrt(jw["v"] * TAU)
    ax.annotate(rf"put handle $p$: slope $p\sqrt{{v\tau}}={beta_l:.3f}$",
                xy=(-0.39, raw.total_variance(-0.39)),
                xytext=(-0.46, raw.total_variance(-0.39) + 0.028),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.5, color=MUTED)
    ax.annotate(rf"call handle $c$: slope $c\sqrt{{v\tau}}={beta_r:.3f}$",
                xy=(0.32, raw.total_variance(0.32)),
                xytext=(-0.05, raw.total_variance(0.32) + 0.030),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.5, color=MUTED)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title(r"two tail handles $p,c$ in total variance")
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.32)
    save(fig, OUT / "fig_svimom_handles.pdf")


def figure_singular(raw: RawSVI) -> None:
    """The psi=0 stratum: same tails and level, the belly curvature is free."""
    rho = raw.rho
    chi = raw.m / np.sqrt(raw.m * raw.m + raw.sigma * raw.sigma)
    angle = np.linspace(-np.pi / 2.0, np.pi / 2.0, 400)

    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))
    ax = axes[0]
    ax.plot(np.sin(angle), np.cos(angle), color=MUTED)
    for u, color, name, dx in (((rho, np.sqrt(1 - rho * rho)), BLUE, r"$u_\rho$", -0.22),
                               ((chi, np.sqrt(1 - chi * chi)), RUST, r"$u_\chi$", 0.06)):
        ax.plot([0, u[0]], [0, u[1]], color=color)
        ax.scatter([u[0]], [u[1]], color=color, zorder=5)
        ax.text(u[0] + dx, u[1] + 0.05, name, color=color)
    ax.annotate(r"gap $D\propto 1-u_\rho\!\cdot u_\chi$", xy=(0.02, 0.98),
                xytext=(-0.58, 0.30),
                arrowprops={"arrowstyle": "->", "color": MUTED}, fontsize=8.8, color=MUTED)
    # box aspect (not aspect='equal') keeps the semicircle round without shrinking
    # the axes out of alignment with panel B; anchor N so the two titles align.
    ax.set_box_aspect(0.52)
    ax.set_anchor("N")
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(0.0, 1.12)
    ax.set_xlabel(r"$\rho$ or $\chi$")
    ax.set_ylabel("positive root")
    ax.set_title("an angle gap")
    label_panel(ax, "A")

    ax = axes[1]
    tau, v, p, c = 0.5, 0.04, 0.5, 0.3
    w0 = v * tau
    b = 0.5 * np.sqrt(w0) * (p + c)
    rho0 = (c - p) / (c + p)
    k = np.linspace(-0.55, 0.50, 600)
    for width, color in zip((0.05, 0.15, 0.40), (RUST, TEAL, VIOLET)):
        m = rho0 * width / np.sqrt(1.0 - rho0 * rho0)
        a = w0 - b * width * np.sqrt(1.0 - rho0 * rho0)
        cand = RawSVI(a=a, b=b, rho=rho0, m=m, sigma=width)
        ax.plot(k, 100.0 * cand.implied_vol(k, tau), color=color, label=rf"belly width $s={width:.2f}$")
    ax.scatter([0.0], [100.0 * np.sqrt(v)], color=INK, zorder=6)
    ax.axvline(0.0, color=MUTED, lw=0.8, ls=":")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title(r"same $(v,0,p,c,v)$: tails fixed, belly free")
    ax.legend(loc="upper center", fontsize=8.3)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_svimom_singular.pdf")


def figure_entangle(raw: RawSVI) -> None:
    """Raw parameters mix tail and belly moves; only a and m act cleanly."""
    k = np.linspace(-0.48, 0.42, 450)
    variants = [
        (r"raise $a$", RawSVI(raw.a + 0.008, raw.b, raw.rho, raw.m, raw.sigma),
         "pure vertical shift"),
        (r"move $m$ right", RawSVI(raw.a, raw.b, raw.rho, raw.m + 0.09, raw.sigma),
         "pure core translation"),
        (r"increase $b$", RawSVI(raw.a, 1.35 * raw.b, raw.rho, raw.m, raw.sigma),
         "both tails + belly"),
        (r"increase $\rho$", RawSVI(raw.a, raw.b, raw.rho + 0.32, raw.m, raw.sigma),
         "tilts tails, moves belly"),
        (r"widen $s$", RawSVI(raw.a, raw.b, raw.rho, raw.m, 1.8 * raw.sigma),
         "belly depth + breadth"),
    ]
    fig, axes = plt.subplots(2, 3, figsize=(7.7, 5.2), sharex=True)
    for i, (title, moved, lesson) in enumerate(variants):
        ax = axes.flat[i]
        ax.plot(k, raw.total_variance(k), color=MUTED, lw=1.5)
        ax.plot(k, moved.total_variance(k), color=TEAL)
        ax.set_title(title, fontsize=11)
        ax.text(0.04, 0.06, lesson, transform=ax.transAxes, fontsize=8.4, color=MUTED)
        if i in (0, 3):
            ax.set_ylabel(r"$w(k)$")
        if i >= 2:
            ax.set_xlabel(r"$k$")
        label_panel(ax, chr(ord("A") + i))
    ax = axes.flat[-1]
    ax.axis("off")
    ax.plot([], [], color=MUTED, lw=1.5, label="baseline")
    ax.plot([], [], color=TEAL, label="one change")
    ax.legend(loc="upper left", fontsize=9)
    ax.text(0.02, 0.52,
            "Only $a$ and $m$ move one\nfeature.  $b,\\rho,s$ each move\n"
            "a tail and the belly together\n--- the reason a desk prefers\n"
            "the JW split.",
            transform=ax.transAxes, va="top", fontsize=9.4, color=INK, linespacing=1.35)
    fig.subplots_adjust(wspace=0.28, hspace=0.32)
    save(fig, OUT / "fig_svimom_entangle.pdf")


def figure_recovery(case: dict) -> None:
    target = case["target"]
    fit = case["fit"]
    k = case["k"]
    w_quotes = case["w_quotes"]
    grid = case["grid"]
    g = case["g"]

    fig = plt.figure(figsize=(7.7, 5.3))
    gs = GridSpec(2, 2, figure=fig, height_ratios=[1.45, 1.0], hspace=0.44, wspace=0.32)
    ax = fig.add_subplot(gs[0, :])
    ax.plot(grid, 100.0 * target.implied_vol(grid, TAU), color=MUTED, lw=2.5,
            label="production JW $\\to$ raw target")
    ax.plot(grid, 100.0 * fit.raw.implied_vol(grid, TAU), color=TEAL, ls="--",
            label="raw-SVI refit")
    ax.scatter(k, 100.0 * np.sqrt(w_quotes / TAU), color=RUST, s=18, zorder=5,
               label="noise-free quotes")
    ax.set_ylabel("implied volatility (%)")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.legend(ncol=3, loc="upper center", fontsize=9)
    ax.set_title("the two coordinate systems round-trip through the production fit")
    label_panel(ax, "A")

    ax = fig.add_subplot(gs[1, 0])
    err = 1e17 * (fit.raw.implied_vol(k, TAU) - np.sqrt(w_quotes / TAU))
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.stem(k, err, linefmt=RUST, markerfmt="o", basefmt=" ")
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"fit error ($10^{-13}$ vol bp)")
    ax.set_title("quote errors")
    label_panel(ax, "B")

    ax = fig.add_subplot(gs[1, 1])
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(grid, 0.0, g, where=g >= 0.0, color=GREEN, alpha=0.14)
    ax.plot(grid, g, color=GREEN)
    ax.set_xlabel(r"$k$")
    ax.set_ylabel(r"$g(k)$")
    ax.set_title("butterfly diagnostic")
    label_panel(ax, "C")
    save(fig, OUT / "fig_svimom_recovery.pdf")


def figure_rigidity(case: dict) -> None:
    k = case["k"]
    w = case["w"]
    fit = case["fit"]
    err = case["error_bp"]
    grid = np.linspace(k.min(), k.max(), 700)

    fig, axes = plt.subplots(2, 1, figsize=(7.1, 5.0), sharex=True,
                             gridspec_kw={"height_ratios": [1.55, 1.0]})
    ax = axes[0]
    ax.plot(k, w, color=RUST, lw=2.4, label="two-minimum target")
    ax.plot(grid, fit.raw.total_variance(grid), color=TEAL, label="best raw-SVI fit")
    ax.scatter(k, w, color=RUST, s=10, alpha=0.45)
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("a single convex hyperbola has exactly one belly")
    ax.legend(loc="upper center", ncol=2, fontsize=9)
    label_panel(ax, "A")

    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.fill_between(k, 0.0, err, color=RUST, alpha=0.12)
    ax.plot(k, err, color=RUST)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("IV error (vol bp)")
    ax.set_title(rf"geometric miss: RMS {case['rms_bp']:.1f} bp, max {case['max_bp']:.1f} bp",
                 fontsize=10.5)
    label_panel(ax, "B")
    fig.subplots_adjust(hspace=0.18)
    save(fig, OUT / "fig_svimom_rigidity.pdf")


def figure_timing(timing: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.4))
    ax = axes[0]
    vals = [timing["fd_ms"], timing["analytic_ms"]]
    bars = ax.bar([0, 1], vals, color=[MUTED, TEAL], width=0.58)
    ax.set_xticks([0, 1], ["finite difference", "analytic"])
    ax.set_ylabel("ms per synthetic fit")
    ax.set_ylim(top=max(vals) * 1.18)
    ax.set_title("fresh 25-quote microbenchmark")
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2f}",
                ha="center", va="bottom", fontsize=9)
    label_panel(ax, "A")

    ax = axes[1]
    vals = [HISTORICAL["fit_fd_ms"], HISTORICAL["fit_analytic_ms"]]
    bars = ax.bar([0, 1], vals, color=[MUTED, TEAL], width=0.58)
    ax.set_xticks([0, 1], ["before", "analytic core"])
    ax.set_ylabel("ms per real node")
    ax.set_ylim(top=max(vals) * 1.18)
    ax.set_title("historical spike-regime measurement")
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.1f}",
                ha="center", va="bottom", fontsize=9)
    label_panel(ax, "B")
    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_svimom_timing.pdf")


# ---------------------------------------------------------------------------
# Macros / payload
# ---------------------------------------------------------------------------
def sci(value: float, digits: int = 1) -> str:
    """Format a tiny value as a LaTeX m x 10^e literal (guide house style)."""
    mant, exp = f"{value:.{digits}e}".split("e")
    return rf"\ensuremath{{{mant}\times10^{{{int(exp)}}}}}"


def tex_table(rows, first_heading: str) -> str:
    lines = [r"\begin{tabular}{lr}", r"\toprule", first_heading + r"\\", r"\midrule"]
    for name, value in rows:
        lines.append(rf"${name}$ & {value:+.6f}\\")
    lines.extend([r"\bottomrule", r"\end{tabular}"])
    return " ".join(lines)


def write_numbers(case, timing, rigidity, facts) -> None:
    fit = case["fit"]
    jw = case["jw"]
    beta_l, beta_r = fit.raw.wing_slopes()
    target_vec = np.array([TARGET_JW.v, TARGET_JW.psi, TARGET_JW.p, TARGET_JW.c, TARGET_JW.v_tilde])
    recovered_vec = np.array([jw["v"], jw["psi"], jw["p"], jw["c"], jw["v_tilde"]])
    jw_roundtrip = float(np.max(np.abs(target_vec - recovered_vec)))

    raw_rows = [("a", fit.raw.a), ("b", fit.raw.b), (r"\rho", fit.raw.rho),
                ("m", fit.raw.m), ("s", fit.raw.sigma)]
    jw_rows = [("v", jw["v"]), (r"\psi", jw["psi"]), ("p", jw["p"]),
               ("c", jw["c"]), (r"\widetilde v", jw["v_tilde"])]

    macros = ["% Auto-generated by gen_svi_moments.py -- do not edit."]
    add = macros.append
    add(rf"\newcommand{{\svimommaxerr}}{{{sci(1e4 * fit.max_iv_error)}}}")
    add(rf"\newcommand{{\svimomnfev}}{{{fit.n_evaluations:d}}}")
    add(rf"\newcommand{{\svimomjwerr}}{{{sci(jw_roundtrip)}}}")
    add(rf"\newcommand{{\svimomgmin}}{{{float(np.min(case['g'])):.3f}}}")
    add(rf"\newcommand{{\svimomwingL}}{{{beta_l:.4f}}}")
    add(rf"\newcommand{{\svimomwingR}}{{{beta_r:.4f}}}")
    add(rf"\newcommand{{\svimomcountermin}}{{{facts['min_var']:.4f}}}")
    add(rf"\newcommand{{\svimomcounterlee}}{{{facts['lee']:.3f}}}")
    add(rf"\newcommand{{\svimomcounterg}}{{{facts['gmin']:.3f}}}")
    add(rf"\newcommand{{\svimomcounterk}}{{{facts['kmin']:.2f}}}")
    add(rf"\newcommand{{\svimomcountergL}}{{{facts['g_tail_l']:.3f}}}")
    add(rf"\newcommand{{\svimomcountergR}}{{{facts['g_tail_r']:.3f}}}")
    add(rf"\newcommand{{\svimomrigidrms}}{{{rigidity['rms_bp']:.1f}}}")
    add(rf"\newcommand{{\svimomrigidmax}}{{{rigidity['max_bp']:.1f}}}")
    add(rf"\newcommand{{\svimomanalyticms}}{{{timing['analytic_ms']:.2f}}}")
    add(rf"\newcommand{{\svimomfdms}}{{{timing['fd_ms']:.2f}}}")
    add(rf"\newcommand{{\svimomspeedup}}{{{timing['speedup']:.2f}}}")
    add(rf"\newcommand{{\svimomcostdiff}}{{{sci(timing['cost_diff'])}}}")
    add(rf"\newcommand{{\svimomhistbefore}}{{{HISTORICAL['fit_fd_ms']:.1f}}}")
    add(rf"\newcommand{{\svimomhistafter}}{{{HISTORICAL['fit_analytic_ms']:.1f}}}")
    add(rf"\newcommand{{\svimomhistspeedup}}{{{HISTORICAL['fit_fd_ms'] / HISTORICAL['fit_analytic_ms']:.2f}}}")
    add(rf"\newcommand{{\svimomhistin}}{{{HISTORICAL['svi_in_bp']:.1f}}}")
    add(rf"\newcommand{{\svimomhistoos}}{{{HISTORICAL['svi_oos_bp']:.1f}}}")
    add(rf"\newcommand{{\svimomnodes}}{{{HISTORICAL['nodes_per_regime']:,}}}")
    add(rf"\newcommand{{\svimomarbold}}{{{HISTORICAL['arb_fd_pct']:.1f}}}")
    add(rf"\newcommand{{\svimomarbnew}}{{{HISTORICAL['arb_analytic_pct']:.1f}}}")
    add(rf"\newcommand{{\svimomlqdarbold}}{{{HISTORICAL['lqd_arb_fd_pct']:.1f}}}")
    add(rf"\newcommand{{\svimomlqdarbnew}}{{{HISTORICAL['lqd_arb_analytic_pct']:.1f}}}")
    add(rf"\newcommand{{\svimompenalty}}{{{_PENALTY:g}}}")
    add(rf"\newcommand{{\svimomleecap}}{{{_LEE_SLOPE_MAX:.1f}}}")
    add(r"\newcommand{\svimomrawtable}{" + tex_table(raw_rows, r"Parameter & Value") + "}")
    add(r"\newcommand{\svimomjwtable}{" + tex_table(jw_rows, r"Handle & Value") + "}")
    (OUT / "svi_moments_tables.tex").write_text("\n".join(macros) + "\n", encoding="utf-8")

    payload = {
        "target_raw": case["target"].__dict__,
        "fit_raw": fit.raw.__dict__,
        "recovered_jw": jw,
        "max_iv_error_bp": 1e4 * fit.max_iv_error,
        "jw_roundtrip_max_abs": jw_roundtrip,
        "recovery_g_min": float(np.min(case["g"])),
        "timing": timing,
        "rigidity": {"rms_bp": rigidity["rms_bp"], "max_bp": rigidity["max_bp"]},
        "counterexample": facts,
        "historical": HISTORICAL,
    }
    (OUT / "svi_moments_numbers.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    case = recovery_case()
    raw = case["fit"].raw
    jw = case["jw"]

    # Execute Appendix D's checked reference inverse against production on
    # several regular-domain points before any figure is published.
    for point in (TARGET_JW,
                  SVIJW(t=0.25, v=0.09, psi=0.10, p=0.40, c=0.60, v_tilde=0.07),
                  SVIJW(t=2.0, v=0.03, psi=-0.05, p=0.30, c=0.28, v_tilde=0.028)):
        prod, ref = jw_to_raw(point), jw_to_raw_checked(point)
        np.testing.assert_allclose(
            [ref.a, ref.b, ref.rho, ref.m, ref.sigma],
            [prod.a, prod.b, prod.rho, prod.m, prod.sigma],
            rtol=2e-12, atol=2e-13,
        )

    facts = counter_facts()
    timing = timing_case(case["k"], case["w_quotes"])
    rigidity = rigidity_case()

    figure_wings(raw)
    figure_moments()
    figure_belly(facts)
    figure_handles(raw, jw)
    figure_singular(raw)
    figure_entangle(raw)
    figure_recovery(case)
    figure_rigidity(rigidity)
    figure_timing(timing)
    write_numbers(case, timing, rigidity, facts)
    print(
        f"SVI moments figures written; recovery max error "
        f"{1e4 * case['fit'].max_iv_error:.3e} vol bp, fresh Jacobian speed-up "
        f"{timing['speedup']:.2f}x, counterexample g_min {facts['gmin']:.3f}"
    )


if __name__ == "__main__":
    main()
