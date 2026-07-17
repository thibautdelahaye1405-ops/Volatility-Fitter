"""Generate the figure suite for the coordinates edition of Note 01.

Run from the repository root with the project virtual environment::

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lqd_geometry.py

The examples are deterministic and offline.  Every slice shown is built or
fitted by the production LQD implementation; local formulae appear only as
quote oracles (an SSVI-shaped curve and a Gaussian mixture) that production is
then exercised against.  The SPX-like case reproduces the quote set of
``gen_lqd_fresh.py`` exactly, so figures from the two suites can share one
narrative and one set of fitted numbers.

Outputs, written next to this script:

* ``fig_lqd_geom_charts.pdf``   -- one fitted slice in four coordinate charts;
* ``fig_lqd_geom_ortho.pdf``    -- primary (handle) move vs shape move;
* ``fig_lqd_geom_calendar.pdf`` -- upper-share ledgers and the convex order;
* ``fig_lqd_geom_jacobian.pdf`` -- deterministic analytic-Jacobian audit;
* ``fig_lqd_geom_spx.pdf``      -- SPX-like case: fit, residuals, density;
* ``fig_lqd_geom_spxtails.pdf`` -- fitted endpoint-scale-to-Lee-slope chain;
* ``fig_lqd_geom_event.pdf``    -- asymmetric double-hat event case;
* ``lqd_geometry_tables.tex``   -- macros for every number quoted in the note.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from scipy.special import expit, logit
from scipy.stats import norm

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.calib.calendar import calendar_floor_targets
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.models.lqd.basis import endpoint_scales, g_eval, lee_psi, lee_slopes
from volfit.models.lqd.calibrate import (
    OPT_N_POINTS,
    _BARRIER_CENTER,
    _BARRIER_SCALE,
    _VEGA_FLOOR,
    CalibrationResult,
    _residuals,
    calibrate_slice,
)
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.ortho import build_atm_coordinates, handles_vector

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from style import PALETTE, WIDE, label_panel, save, setup  # noqa: E402


OUT = Path(__file__).resolve().parent
setup()

EXPIRY = 0.75
NEAR_EXPIRY = 0.25


def ssvi_total_variance(k: np.ndarray) -> np.ndarray:
    """The SPX-shaped SSVI quote oracle of gen_lqd_fresh.py (same constants)."""

    theta, rho, phi = 0.0356, -0.68, 2.40
    k = np.asarray(k, dtype=float)
    return 0.5 * theta * (
        1.0
        + rho * phi * k
        + np.sqrt((phi * k + rho) ** 2 + 1.0 - rho * rho)
    )


QUOTE_K = np.array(
    [
        -0.42, -0.36, -0.31, -0.27, -0.23, -0.19, -0.16, -0.13,
        -0.10, -0.075, -0.05, -0.025, 0.0, 0.025, 0.05, 0.075,
        0.10, 0.13, 0.16, 0.19, 0.23, 0.27, 0.31, 0.36,
    ]
)


def quote_iv(expiry: float, scale: float = 1.0) -> np.ndarray:
    """The fresh-suite quote strip: SSVI level plus the same 2 bp ripple."""

    smooth_iv = np.sqrt(scale * ssvi_total_variance(QUOTE_K) / expiry)
    return smooth_iv + 1e-4 * (
        1.20 * np.sin(9.0 * QUOTE_K + 0.4) + 0.55 * np.cos(21.0 * QUOTE_K)
    )


def fit_spx_case() -> CalibrationResult:
    """The production SPX-like fit (identical to the fresh-suite case)."""

    iv = quote_iv(EXPIRY)
    return calibrate_slice(
        QUOTE_K,
        iv * iv * EXPIRY,
        EXPIRY,
        n_order=9,
        reg_lambda=3e-8,
        reg_power=1.2,
    )


# ---------------------------------------------------------------------------
# Figure 1: the same slice in four coordinate charts.
# ---------------------------------------------------------------------------


def figure_charts(spx: CalibrationResult) -> dict[str, float]:
    """One fitted slice drawn in the four charts the note tours."""

    slice_ = spx.slice
    fig, axes = plt.subplots(2, 2, figsize=(7.6, 6.4))
    (ax_price, ax_iv), (ax_dens, ax_free) = axes

    k_grid = np.linspace(-0.45, 0.40, 400)
    y_grid = np.exp(k_grid)

    # (A) price chart: decreasing and convex in strike.
    call = slice_.call_price(k_grid)
    ax_price.plot(y_grid, call, color=PALETTE["blue"], lw=1.6)
    ax_price.set_xlabel(r"normalized strike $e^k$")
    ax_price.set_ylabel(r"normalized call $C$")
    ax_price.set_title("price chart: a convex cone", fontsize=10)
    label_panel(ax_price, "A")

    # (B) implied-volatility chart: the quoted object, implicit constraint.
    iv = slice_.implied_vol(k_grid, EXPIRY)
    ax_iv.plot(k_grid, 100 * iv, color=PALETTE["teal"], lw=1.6)
    ax_iv.plot(
        QUOTE_K, 100 * quote_iv(EXPIRY), ls="none", marker="o", ms=3.2,
        color=PALETTE["ink"], alpha=0.55,
    )
    ax_iv.set_xlabel(r"log-moneyness $k$")
    ax_iv.set_ylabel(r"implied vol $\sigma$ (%)")
    ax_iv.set_title("volatility chart: implicit boundary", fontsize=10)
    label_panel(ax_iv, "B")

    # (C) density chart: positive, two integral constraints.
    x_dens, f_dens = slice_.density()
    keep = (x_dens > -0.75) & (x_dens < 0.55)
    ax_dens.plot(x_dens[keep], f_dens[keep], color=PALETTE["violet"], lw=1.6)
    ax_dens.fill_between(
        x_dens[keep], 0.0, f_dens[keep], color=PALETTE["violet"], alpha=0.10
    )
    ax_dens.set_xlabel(r"log return $x$")
    ax_dens.set_ylabel(r"density $f$")
    ax_dens.set_title("density chart: positivity + two integrals", fontsize=10)
    label_panel(ax_dens, "C")

    # (D) the LQD chart: log q dives along the universal skeleton at both
    # ends (the classical U); the model's freedom is the gap g above it.
    u_grid = np.linspace(2e-3, 1.0 - 2e-3, 600)
    skeleton = -np.log(u_grid) - np.log(1.0 - u_grid)
    log_q = skeleton + g_eval(spx.params, u_grid)
    ax_free.plot(
        u_grid, log_q, color=PALETTE["rust"], lw=1.6, label=r"$\log q(u)$"
    )
    ax_free.plot(
        u_grid, skeleton, color=PALETTE["muted"], lw=1.2, ls="--",
        label=r"skeleton $-\log u(1-u)$",
    )
    ax_free.fill_between(
        u_grid, skeleton, log_q, color=PALETTE["rust"], alpha=0.10
    )
    ax_free.set_xlabel(r"rank $u$")
    ax_free.set_ylabel(r"$\log q(u)$")
    ax_free.set_title("LQD chart: only the gap $g$ is free", fontsize=10)
    ax_free.legend(frameon=False, fontsize=8.0, loc="upper center")
    label_panel(ax_free, "D")

    for ax in axes.flat:
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.tight_layout()
    save(fig, OUT / "fig_lqd_geom_charts.pdf")

    return {"chartsmart": abs(slice_.martingale_check() - 1.0)}


# ---------------------------------------------------------------------------
# Figure 2: the ATM-orthogonal chart in action.
# ---------------------------------------------------------------------------


def figure_ortho(spx: CalibrationResult) -> dict[str, float]:
    """A primary skew move versus a handle-preserving shape move."""

    t = EXPIRY
    coords = build_atm_coordinates(spx.params, t)
    h0 = coords.handles0  # (w0, skew, curvature)

    skew_bump = 0.04
    target = h0 + np.array([0.0, skew_bump, 0.0])
    params_primary = coords.retarget(target)
    resid = handles_vector(params_primary, t) - target

    n_shape = coords.shape.shape[1]
    xi = np.zeros(n_shape)
    xi[0] = 0.15
    params_shape = coords.theta(np.zeros(3), xi)
    drift = handles_vector(params_shape, t) - h0

    from volfit.models.lqd.quadrature import build_slice

    slice_ref = spx.slice
    slice_primary = build_slice(params_primary)
    slice_shape = build_slice(params_shape)

    k_grid = np.linspace(-0.40, 0.35, 400)
    iv_ref = slice_ref.implied_vol(k_grid, t)
    iv_primary = slice_primary.implied_vol(k_grid, t)
    iv_shape = slice_shape.implied_vol(k_grid, t)

    fig, (ax_smile, ax_diff) = plt.subplots(1, 2, figsize=WIDE)

    ax_smile.plot(
        k_grid, 100 * iv_ref, color=PALETTE["ink"], lw=1.5, label="reference"
    )
    ax_smile.plot(
        k_grid, 100 * iv_primary, color=PALETTE["blue"], lw=1.5,
        label=rf"primary: skew ${skew_bump:+.2f}$",
    )
    ax_smile.plot(
        k_grid, 100 * iv_shape, color=PALETTE["teal"], lw=1.5, ls="--",
        label=r"shape: $\xi_1=0.15$",
    )
    ax_smile.axvline(0.0, color=PALETTE["muted"], lw=0.7, alpha=0.6)
    ax_smile.set_xlabel(r"log-moneyness $k$")
    ax_smile.set_ylabel(r"implied vol (%)")
    ax_smile.legend(frameon=False, fontsize=8.5)
    label_panel(ax_smile, "A")

    ax_diff.plot(
        k_grid, 1e4 * (iv_primary - iv_ref), color=PALETTE["blue"], lw=1.5,
        label="primary move",
    )
    ax_diff.plot(
        k_grid, 1e4 * (iv_shape - iv_ref), color=PALETTE["teal"], lw=1.5,
        ls="--", label="shape move",
    )
    ax_diff.axhline(0.0, color=PALETTE["muted"], lw=0.7, alpha=0.6)
    ax_diff.axvline(0.0, color=PALETTE["muted"], lw=0.7, alpha=0.6)
    ax_diff.set_xlabel(r"log-moneyness $k$")
    ax_diff.set_ylabel(r"$\Delta\sigma$ (vol bp)")
    ax_diff.legend(frameon=False, fontsize=8.5)
    label_panel(ax_diff, "B")

    for ax in (ax_smile, ax_diff):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.tight_layout()
    save(fig, OUT / "fig_lqd_geom_ortho.pdf")

    sigma0_ref = np.sqrt(h0[0] / t)
    sigma0_shape = np.sqrt((h0[0] + drift[0]) / t)
    wing_move = np.max(np.abs(1e4 * (iv_shape - iv_ref)))
    atm_move = float(1e4 * abs(iv_shape[np.argmin(np.abs(k_grid))] - iv_ref[np.argmin(np.abs(k_grid))]))
    return {
        "orthonshape": float(n_shape),
        "orthoshapedriftsigma": abs(sigma0_shape - sigma0_ref) * 1e4,
        "orthoshapedriftskew": abs(drift[1]),
        "orthoshapedriftcurv": abs(drift[2]),
        "orthoshapewingmove": wing_move,
        "orthoshapeatmmove": atm_move,
        "orthoretargetresid": float(np.max(np.abs(resid))),
        "orthoskewbump": skew_bump,
    }


# ---------------------------------------------------------------------------
# Figure 3: convex order read off the upper-share ledger.
# ---------------------------------------------------------------------------


def figure_calendar(spx: CalibrationResult) -> dict[str, float]:
    """Legitimate calendar ordering, a hidden crossing, and the soft repair."""

    # Near expiry: the same SSVI shape with proportionally smaller variance.
    iv_near = quote_iv(NEAR_EXPIRY, scale=NEAR_EXPIRY / EXPIRY)
    near = calibrate_slice(
        QUOTE_K,
        iv_near * iv_near * NEAR_EXPIRY,
        NEAR_EXPIRY,
        n_order=9,
        reg_lambda=3e-8,
        reg_power=1.2,
    )

    # A crafted far expiry whose body variance sits BELOW the near slice while
    # its wings sit above: the crossing hides away from the ATM strikes.
    w_near_quotes = iv_near * iv_near * NEAR_EXPIRY
    w_cross = 0.90 * w_near_quotes + 0.055 * QUOTE_K**2
    cross = calibrate_slice(
        QUOTE_K, w_cross, EXPIRY, n_order=9, reg_lambda=3e-8, reg_power=1.2
    )

    # The same crossed quotes refitted with the production soft calendar floor.
    cal_z, cal_floor = calendar_floor_targets(near.slice)
    healed = calibrate_slice(
        QUOTE_K,
        w_cross,
        EXPIRY,
        n_order=9,
        reg_lambda=3e-8,
        reg_power=1.2,
        calendar_z=cal_z,
        calendar_floor=cal_floor,
    )

    u_grid = np.linspace(0.004, 0.996, 600)
    z_grid = logit(u_grid)
    share_near = near.slice.asset_share_at(z_grid)
    share_far = spx.slice.asset_share_at(z_grid)
    share_cross = cross.slice.asset_share_at(z_grid)
    share_healed = healed.slice.asset_share_at(z_grid)

    fig, (ax_ledger, ax_gap) = plt.subplots(1, 2, figsize=WIDE)

    ax_ledger.fill_between(
        u_grid, share_near, share_far, color=PALETTE["blue"], alpha=0.10
    )
    ax_ledger.plot(
        u_grid, share_near, color=PALETTE["ink"], lw=1.6,
        label=rf"near, $\tau={NEAR_EXPIRY}$",
    )
    ax_ledger.plot(
        u_grid, share_far, color=PALETTE["blue"], lw=1.6,
        label=rf"far, $\tau={EXPIRY}$",
    )
    ax_ledger.annotate(
        "far $\\geq$ near\nat every rank",
        xy=(0.42, float(np.interp(0.42, u_grid, share_far))),
        xytext=(0.60, 0.72), fontsize=8.5, color=PALETTE["muted"],
        arrowprops=dict(arrowstyle="-", lw=0.7, color=PALETTE["muted"]),
    )
    ax_ledger.set_xlabel(r"rank $u$")
    ax_ledger.set_ylabel(r"upper share $G$")
    ax_ledger.legend(frameon=False, fontsize=8.5, loc="lower left")
    label_panel(ax_ledger, "A")

    gap_cross_curve = share_cross - share_near
    ax_gap.plot(
        u_grid, share_far - share_near, color=PALETTE["green"], lw=1.6,
        label="legitimate pair",
    )
    ax_gap.plot(
        u_grid, gap_cross_curve, color=PALETTE["rust"], lw=1.6,
        label="crossed pair",
    )
    ax_gap.plot(
        u_grid, share_healed - share_near, color=PALETTE["blue"], lw=1.4,
        ls="--", label="crossed + soft floor",
    )
    ax_gap.fill_between(
        u_grid, 0.0, np.minimum(gap_cross_curve, 0.0),
        color=PALETTE["rust"], alpha=0.15,
    )
    i_min = int(np.argmin(gap_cross_curve))
    ax_gap.annotate(
        "free calendar spread",
        xy=(float(u_grid[i_min]), float(gap_cross_curve[i_min])),
        xytext=(0.55, 0.0065), fontsize=8.5, color=PALETTE["rust"],
        arrowprops=dict(arrowstyle="-", lw=0.7, color=PALETTE["rust"]),
    )
    ax_gap.axhline(0.0, color=PALETTE["muted"], lw=0.7, alpha=0.7)
    ax_gap.set_ylim(-0.006, 0.0425)
    ax_gap.set_xlabel(r"rank $u$")
    ax_gap.set_ylabel(r"calendar gap $G_{\mathrm{far}}-G_{\mathrm{near}}$")
    ax_gap.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_gap, "B")

    for ax in (ax_ledger, ax_gap):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.tight_layout()
    save(fig, OUT / "fig_lqd_geom_calendar.pdf")

    gap_legit = share_far - share_near
    gap_cross = share_cross - share_near
    gap_healed = share_healed - share_near
    return {
        "calmingaplegit": float(np.min(gap_legit)),
        "calmingapcross": float(np.min(gap_cross)),
        "calugapcross": float(u_grid[int(np.argmin(gap_cross))]),
        "calmingaphealed": float(np.min(gap_healed)),
    }


# ---------------------------------------------------------------------------
# Figure 4: analytic-Jacobian audit (uncluttered edition).
# ---------------------------------------------------------------------------


def figure_jacobian(spx: CalibrationResult) -> dict[str, float]:
    """Audit the production analytic Jacobian against central differences."""

    theta = spx.params.to_vector()
    iv = quote_iv(EXPIRY)
    target_w = iv * iv * EXPIRY
    target_price = black_call(QUOTE_K, target_w)
    inv_vega = 1.0 / (black_vega_sigma(QUOTE_K, iv, EXPIRY) + _VEGA_FLOOR)
    degrees = np.arange(2, spx.params.order + 1, dtype=float)
    reg = np.sqrt(3e-8) * np.where(degrees >= 4, degrees**1.2, 0.0)
    args = (
        QUOTE_K, target_price, inv_vega, np.ones_like(QUOTE_K), reg,
        None, None, 1e6, None, None,
        _BARRIER_CENTER, _BARRIER_SCALE, MID_ANCHOR_WEIGHT,
        None, None, None, None, OPT_N_POINTS,
    )
    analytic = residual_jacobian(theta, *args)
    central = np.empty_like(analytic)
    for column in range(theta.size):
        step = 2e-6 * max(1.0, abs(theta[column]))
        plus, minus = theta.copy(), theta.copy()
        plus[column] += step
        minus[column] -= step
        central[:, column] = (
            _residuals(plus, *args) - _residuals(minus, *args)
        ) / (2.0 * step)

    denominator = np.maximum(np.linalg.norm(central, axis=0), 1e-14)
    relative_error = np.linalg.norm(analytic - central, axis=0) / denominator
    labels = ["$L$", "$R$"] + [
        rf"$a_{{{degree}}}$" for degree in range(2, spx.params.order + 1)
    ]

    fig, (ax_map, ax_err) = plt.subplots(1, 2, figsize=(7.6, 3.4))

    fit_block = analytic[: QUOTE_K.size]
    normalized = fit_block / np.maximum(np.max(np.abs(fit_block), axis=0), 1e-14)
    image = ax_map.imshow(
        normalized, origin="lower", aspect="auto", cmap="coolwarm",
        vmin=-1.0, vmax=1.0,
    )
    ax_map.set_xticks(np.arange(theta.size), labels, fontsize=8)
    row_ticks = np.array([0, 6, 12, 18, 23])
    ax_map.set_yticks(row_ticks, [f"{QUOTE_K[i]:+.2f}" for i in row_ticks])
    ax_map.set_xlabel("parameter")
    ax_map.set_ylabel(r"quoted log-moneyness $k$")
    fig.colorbar(image, ax=ax_map, fraction=0.046, pad=0.04)
    label_panel(ax_map, "A")

    ax_err.bar(
        np.arange(theta.size), relative_error, color=PALETTE["teal"], width=0.62
    )
    ax_err.axhline(1e-6, color=PALETTE["rust"], ls="--", lw=1.0)
    ax_err.annotate(
        "one part per million",
        xy=(4.6, 1.05e-6), xytext=(0.1, 3.2e-5),
        fontsize=8.5, color=PALETTE["rust"],
        arrowprops=dict(arrowstyle="-", lw=0.7, color=PALETTE["rust"]),
    )
    ax_err.set_yscale("log")
    ax_err.set_ylim(5e-7, float(np.max(relative_error)) * 10.0)
    ax_err.set_xticks(np.arange(theta.size), labels, fontsize=8)
    ax_err.set_xlabel("parameter")
    ax_err.set_ylabel("relative error vs central FD")
    label_panel(ax_err, "B")

    fig.subplots_adjust(wspace=0.52)
    save(fig, OUT / "fig_lqd_geom_jacobian.pdf")
    return {
        "jacmaxrel": float(np.max(relative_error)),
        "jacnparams": float(theta.size),
    }


# ---------------------------------------------------------------------------
# Figures 5-7: the two case files, uncluttered editions.
# ---------------------------------------------------------------------------


def figure_spx_case(spx: CalibrationResult) -> None:
    """The SPX-like case: fit, residual ledger, and the density behind it."""

    iv_quotes = quote_iv(EXPIRY)
    dense_k = np.linspace(-0.48, 0.42, 480)
    oracle_iv = np.sqrt(ssvi_total_variance(dense_k) / EXPIRY)
    model_iv = spx.slice.implied_vol(dense_k, EXPIRY)
    residual_bp = 1e4 * (spx.slice.implied_vol(QUOTE_K, EXPIRY) - iv_quotes)

    fig, (ax_fit, ax_res, ax_dens) = plt.subplots(1, 3, figsize=(8.55, 3.0))

    ax_fit.plot(
        dense_k, 100 * oracle_iv, color=PALETTE["muted"], lw=2.2,
        label="quote oracle",
    )
    ax_fit.plot(
        dense_k, 100 * model_iv, color=PALETTE["teal"], ls="--",
        label="production LQD",
    )
    ax_fit.scatter(
        QUOTE_K, 100 * iv_quotes, color=PALETTE["rust"], s=16, zorder=4,
        label="quotes",
    )
    ax_fit.set_xlabel(r"log-moneyness $k$")
    ax_fit.set_ylabel("implied volatility (%)")
    ax_fit.legend(frameon=False, fontsize=8, loc="upper right")
    label_panel(ax_fit, "A")

    ax_res.axhspan(-2.0, 2.0, color=PALETTE["teal"], alpha=0.08)
    ax_res.axhline(0.0, color=PALETTE["muted"], lw=0.8)
    ax_res.vlines(QUOTE_K, 0.0, residual_bp, color=PALETTE["rust"], lw=1.1)
    ax_res.scatter(QUOTE_K, residual_bp, color=PALETTE["rust"], s=14, zorder=4)
    ax_res.set_ylim(-2.4, 2.4)
    ax_res.set_xlabel(r"quoted log-moneyness $k$")
    ax_res.set_ylabel("fit minus quote (vol bp)")
    label_panel(ax_res, "B")

    x, density = spx.slice.density()
    atm_vol = float(spx.slice.implied_vol(0.0, EXPIRY))
    atm_variance = atm_vol * atm_vol * EXPIRY
    normal_density = norm.pdf(
        x, loc=-0.5 * atm_variance, scale=np.sqrt(atm_variance)
    )
    selected = (x > -0.62) & (x < 0.42)
    left_tail = selected & (x < -0.20)
    ax_dens.plot(
        x[selected], density[selected], color=PALETTE["teal"],
        label="LQD density",
    )
    ax_dens.plot(
        x[selected], normal_density[selected], color=PALETTE["muted"],
        ls="--", label="ATM-matched normal",
    )
    ax_dens.fill_between(
        x[left_tail], 0.0, density[left_tail], color=PALETTE["rust"],
        alpha=0.15,
    )
    ax_dens.set_ylim(-0.08, float(np.max(density[selected])) * 1.35)
    ax_dens.set_xlabel(r"log-forward return $x$")
    ax_dens.set_ylabel("probability density")
    ax_dens.legend(frameon=False, fontsize=8, loc="upper left")
    label_panel(ax_dens, "C")

    fig.subplots_adjust(wspace=0.42)
    save(fig, OUT / "fig_lqd_geom_spx.pdf")


def figure_spx_tails(spx: CalibrationResult) -> None:
    """The fitted three-link chain: endpoint scale, moment budget, Lee slope."""

    a_left, a_right = endpoint_scales(spx.params)
    beta_left, beta_right = lee_slopes(spx.params)
    p_left, p_right = 1.0 / a_left, 1.0 / a_right - 1.0
    dot_colors = [PALETTE["blue"], PALETTE["amber"]]

    fig, (ax_scale, ax_moment, ax_lee) = plt.subplots(1, 3, figsize=(8.55, 3.0))

    endpoint_log = np.linspace(-4.7, -0.02, 500)
    ax_scale.plot(endpoint_log, np.exp(endpoint_log), color=PALETTE["teal"])
    ax_scale.scatter(
        [np.log(a_left), np.log(a_right)], [a_left, a_right],
        color=dot_colors, zorder=4,
    )
    ax_scale.annotate(
        "left tail", (np.log(a_left), a_left), xytext=(-6, 10),
        textcoords="offset points", ha="right", fontsize=8.5,
        color=PALETTE["blue"],
    )
    ax_scale.annotate(
        "right tail", (np.log(a_right), a_right), xytext=(4, -16),
        textcoords="offset points", fontsize=8.5, color=PALETTE["amber"],
    )
    ax_scale.set_xlabel(r"endpoint value $g(0)$ or $g(1)$")
    ax_scale.set_ylabel(r"tail scale $A=e^{g}$")
    label_panel(ax_scale, "A")

    scale = np.linspace(0.015, 0.985, 700)
    ax_moment.semilogy(scale, 1.0 / scale, color=PALETTE["blue"], label="left")
    ax_moment.semilogy(
        scale, 1.0 / scale - 1.0, color=PALETTE["amber"], label="right"
    )
    ax_moment.scatter(
        [a_left, a_right], [p_left, p_right], color=dot_colors,
        edgecolor=PALETTE["ink"], linewidth=0.5, zorder=4,
    )
    ax_moment.set_xlabel(r"tail scale $A$")
    ax_moment.set_ylabel(r"last finite moment $p^{*}$")
    ax_moment.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_moment, "B")

    p_grid = np.logspace(-3, 2.2, 800)
    ax_lee.semilogx(p_grid, lee_psi(p_grid), color=PALETTE["teal"])
    ax_lee.scatter(
        [p_left, p_right], [beta_left, beta_right], color=dot_colors,
        edgecolor=PALETTE["ink"], linewidth=0.5, zorder=4,
    )
    ax_lee.annotate(
        "left wing", (p_left, beta_left), xytext=(-16, 22),
        textcoords="offset points", ha="right", fontsize=8.5,
        color=PALETTE["blue"],
        arrowprops=dict(arrowstyle="-", lw=0.6, color=PALETTE["blue"]),
    )
    ax_lee.annotate(
        "right wing", (p_right, beta_right), xytext=(10, 14),
        textcoords="offset points", fontsize=8.5, color=PALETTE["amber"],
        arrowprops=dict(arrowstyle="-", lw=0.6, color=PALETTE["amber"]),
    )
    ax_lee.axhline(2.0, color=PALETTE["muted"], lw=0.8, ls=":")
    ax_lee.set_ylim(-0.05, 2.12)
    ax_lee.set_xlabel(r"last finite moment $p^{*}$")
    ax_lee.set_ylabel(r"Lee wing slope $\psi(p^{*})$")
    label_panel(ax_lee, "C")

    fig.subplots_adjust(wspace=0.46)
    save(fig, OUT / "fig_lqd_geom_spxtails.pdf")


def mixture_call(
    k: np.ndarray, weights: np.ndarray, means: np.ndarray, sigmas: np.ndarray
) -> np.ndarray:
    """Normalized call prices for a finite mixture of Gaussian log returns."""

    k = np.asarray(k, dtype=float)
    call = np.zeros_like(k)
    for weight, mean, sigma in zip(weights, means, sigmas, strict=True):
        call += weight * (
            np.exp(mean + 0.5 * sigma * sigma)
            * norm.cdf((mean + sigma * sigma - k) / sigma)
            - np.exp(k) * norm.cdf((mean - k) / sigma)
        )
    return call


def figure_event_case() -> None:
    """The asymmetric double-hat event case, fitted by production at N=16."""

    expiry = 24.0 / 365.0
    weight_left = 0.56
    weights = np.array([weight_left, 1.0 - weight_left])
    raw_means = np.array([-0.075, 0.085])
    sigmas = np.array([0.052, 0.047])
    shift = -np.log(np.sum(weights * np.exp(raw_means + 0.5 * sigmas * sigmas)))
    means = raw_means + shift

    quote_k = np.linspace(-0.22, 0.22, 37)
    target_w = implied_total_variance(
        quote_k, mixture_call(quote_k, weights, means, sigmas)
    )
    result = calibrate_slice(quote_k, target_w, expiry, n_order=16, reg_lambda=1e-11)

    dense_k = np.linspace(-0.25, 0.25, 500)
    dense_iv = np.sqrt(
        implied_total_variance(dense_k, mixture_call(dense_k, weights, means, sigmas))
        / expiry
    )
    model_iv = result.slice.implied_vol(dense_k, expiry)

    fig, (ax_smile, ax_dens) = plt.subplots(1, 2, figsize=WIDE)

    ax_smile.plot(
        dense_k, 100 * dense_iv, color=PALETTE["ink"], lw=2.2,
        label="two-regime target",
    )
    ax_smile.plot(
        dense_k, 100 * model_iv, color=PALETTE["teal"], ls="--",
        label="production LQD",
    )
    ax_smile.scatter(
        quote_k, 100 * np.sqrt(target_w / expiry), color=PALETTE["rust"],
        s=13, zorder=4, label="quotes",
    )
    ax_smile.set_ylim(25.0, 44.5)
    ax_smile.set_xlabel(r"log-moneyness $k$")
    ax_smile.set_ylabel("implied volatility (%)")
    ax_smile.legend(frameon=False, fontsize=8.5, loc="upper left")
    label_panel(ax_smile, "A")

    x, model_density = result.slice.density()
    target_density = (
        weights[0] * norm.pdf(x, means[0], sigmas[0])
        + weights[1] * norm.pdf(x, means[1], sigmas[1])
    )
    selected = (x > -0.25) & (x < 0.25)
    ax_dens.plot(
        x[selected], target_density[selected], color=PALETTE["ink"], lw=2.2,
        label="two-regime density",
    )
    ax_dens.plot(
        x[selected], model_density[selected], color=PALETTE["teal"], ls="--",
        label="LQD density",
    )
    ax_dens.fill_between(
        x[selected], 0.0, model_density[selected], color=PALETTE["teal"],
        alpha=0.08,
    )
    ax_dens.set_ylim(-0.15, float(np.max(target_density)) * 1.32)
    ax_dens.set_xlabel(r"log-forward return $x$")
    ax_dens.set_ylabel("probability density")
    ax_dens.legend(frameon=False, fontsize=8.5, loc="upper left")
    label_panel(ax_dens, "B")

    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_lqd_geom_event.pdf")


# ---------------------------------------------------------------------------
# Macro emission.
# ---------------------------------------------------------------------------


def fmt(value: float, spec: str) -> str:
    return format(value, spec)


def tex_sci(value: float) -> str:
    """Format a scalar as a robust math-mode LaTeX macro body."""

    if value == 0.0:
        return r"\ensuremath{0}"
    exponent = int(np.floor(np.log10(abs(value))))
    mantissa = value / 10.0**exponent
    return rf"\ensuremath{{{mantissa:.2f}\times10^{{{exponent}}}}}"


def write_tables(stats: dict[str, float]) -> None:
    lines = [
        "% Auto-generated by Docs/notes/figures/gen_lqd_geometry.py -- do not edit.",
        f"\\newcommand{{\\lqdgeomnshape}}{{{int(stats['orthonshape'])}}}",
        f"\\newcommand{{\\lqdgeomshapedriftsigma}}{{{fmt(stats['orthoshapedriftsigma'], '.2f')}}}",
        f"\\newcommand{{\\lqdgeomshapedriftskew}}{{{tex_sci(stats['orthoshapedriftskew'])}}}",
        f"\\newcommand{{\\lqdgeomshapedriftcurv}}{{{tex_sci(stats['orthoshapedriftcurv'])}}}",
        f"\\newcommand{{\\lqdgeomshapewingmove}}{{{fmt(stats['orthoshapewingmove'], '.0f')}}}",
        f"\\newcommand{{\\lqdgeomshapeatmmove}}{{{fmt(stats['orthoshapeatmmove'], '.2f')}}}",
        f"\\newcommand{{\\lqdgeomretargetresid}}{{{tex_sci(stats['orthoretargetresid'])}}}",
        f"\\newcommand{{\\lqdgeomskewbump}}{{{fmt(stats['orthoskewbump'], '.2f')}}}",
        f"\\newcommand{{\\lqdgeommingaplegit}}{{{fmt(stats['calmingaplegit'], '.5f')}}}",
        f"\\newcommand{{\\lqdgeommingapcross}}{{{fmt(stats['calmingapcross'], '.5f')}}}",
        f"\\newcommand{{\\lqdgeomugapcross}}{{{fmt(stats['calugapcross'], '.2f')}}}",
        f"\\newcommand{{\\lqdgeommingaphealed}}{{{tex_sci(stats['calmingaphealed'])}}}",
        f"\\newcommand{{\\lqdgeomchartsmart}}{{{tex_sci(stats['chartsmart'])}}}",
        f"\\newcommand{{\\lqdgeomjacnparams}}{{{int(stats['jacnparams'])}}}",
        f"\\newcommand{{\\lqdgeomjacmaxrel}}{{{tex_sci(stats['jacmaxrel'])}}}",
    ]
    (OUT / "lqd_geometry_tables.tex").write_text("\n".join(lines) + "\n")


def main() -> None:
    spx = fit_spx_case()
    stats: dict[str, float] = {}
    stats.update(figure_charts(spx))
    stats.update(figure_ortho(spx))
    stats.update(figure_calendar(spx))
    stats.update(figure_jacobian(spx))
    figure_spx_case(spx)
    figure_spx_tails(spx)
    figure_event_case()
    write_tables(stats)
    for key, value in sorted(stats.items()):
        print(f"{key:26s} {value:.6g}")


if __name__ == "__main__":
    main()
