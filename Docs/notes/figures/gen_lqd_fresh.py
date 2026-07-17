"""Generate the independent figure suite for the fresh edition of Note 01.

Run from the repository root with the project virtual environment::

    .venv\Scripts\python.exe Docs\notes\figures\gen_lqd_fresh.py

The examples are deterministic and offline.  All distributions are built or
fitted through the production LQD implementation; local formulae are used only
to define the two synthetic quote sets against which production is exercised.

Outputs, written next to this script:

* ``fig_lqd_fresh_butterfly.pdf`` -- call convexity and discrete butterflies;
* ``fig_lqd_fresh_ruler.pdf`` -- exact-20%-ATM logistic percentile toy;
* ``fig_lqd_fresh_modes.pdf`` -- three one-mode perturbation experiments;
* ``fig_lqd_fresh_tails.pdf`` -- endpoint scale to moment to Lee-slope chain;
* ``fig_lqd_fresh_spx.pdf`` -- SPX-like fit, residuals, and recovered density;
* ``fig_lqd_fresh_event.pdf`` -- asymmetric double-hat fit and density;
* ``fig_lqd_fresh_jacobian.pdf`` -- deterministic analytic-Jacobian check;
* ``lqd_fresh_tables.tex`` -- numerical-example and diagnostic macros.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
from scipy.optimize import brentq
from scipy.special import expit, logit
from scipy.stats import norm

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.core.black import (
    black_call,
    black_vega_sigma,
    implied_total_variance,
)
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import (
    LQDParams,
    endpoint_scales,
    g_eval,
    lee_psi,
    lee_slopes,
)
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
from volfit.models.lqd.quadrature import LQDSlice, build_slice

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from style import PALETTE, WIDE, callout, label_panel, save, setup  # noqa: E402


OUT = Path(__file__).resolve().parent
setup()


@dataclass(frozen=True)
class ToyCase:
    """The scale-solved symmetric logistic example."""

    expiry: float
    target_atm_vol: float
    scale: float
    slice: LQDSlice
    u_atm: float
    u_ten: float
    share_ten: float
    cash_ten: float
    call_ten: float
    iv_ten: float


@dataclass(frozen=True)
class SmileCase:
    """A quote set, a dense target curve, and its production fit."""

    expiry: float
    quote_k: np.ndarray
    quote_iv: np.ndarray
    dense_k: np.ndarray
    target_dense_iv: np.ndarray
    result: CalibrationResult


@dataclass(frozen=True)
class EventCase:
    """The asymmetric two-regime event distribution and its production fit."""

    smile: SmileCase
    weight_left: float
    means: np.ndarray
    sigmas: np.ndarray


def solve_logistic_toy() -> ToyCase:
    """Solve the production logistic family to exactly 20% ATM at six months."""

    expiry = 0.5
    target_atm_vol = 0.20

    def atm_error(log_scale: float) -> float:
        params = LQDParams(log_scale, log_scale, np.zeros(5))
        return float(build_slice(params).implied_vol(0.0, expiry)) - target_atm_vol

    log_scale = brentq(atm_error, np.log(0.01), np.log(0.30), xtol=1e-14)
    scale = float(np.exp(log_scale))
    slice_ = build_slice(LQDParams(log_scale, log_scale, np.zeros(5)))
    z_atm = float(slice_.strike_to_z(0.0))
    z_ten = float(slice_.strike_to_z(0.10))
    u_ten = float(expit(z_ten))
    return ToyCase(
        expiry=expiry,
        target_atm_vol=target_atm_vol,
        scale=scale,
        slice=slice_,
        u_atm=float(expit(z_atm)),
        u_ten=u_ten,
        share_ten=float(slice_.asset_share_at(z_ten)),
        cash_ten=float(np.exp(0.10) * (1.0 - u_ten)),
        call_ten=float(slice_.call_price(0.10)),
        iv_ten=float(slice_.implied_vol(0.10, expiry)),
    )


def ssvi_total_variance(k: np.ndarray) -> np.ndarray:
    """A deterministic, SPX-shaped SSVI slice used only as a quote oracle."""

    theta, rho, phi = 0.0356, -0.68, 2.40
    k = np.asarray(k, dtype=float)
    return 0.5 * theta * (
        1.0
        + rho * phi * k
        + np.sqrt((phi * k + rho) ** 2 + 1.0 - rho * rho)
    )


def fit_spx_case() -> SmileCase:
    """Fit a mildly noisy, irregularly spaced, SPX-like quote strip."""

    expiry = 0.75
    quote_k = np.array(
        [
            -0.42,
            -0.36,
            -0.31,
            -0.27,
            -0.23,
            -0.19,
            -0.16,
            -0.13,
            -0.10,
            -0.075,
            -0.05,
            -0.025,
            0.0,
            0.025,
            0.05,
            0.075,
            0.10,
            0.13,
            0.16,
            0.19,
            0.23,
            0.27,
            0.31,
            0.36,
        ]
    )
    smooth_iv = np.sqrt(ssvi_total_variance(quote_k) / expiry)
    # A reproducible sub-two-bp microstructure ripple keeps this a genuine fit,
    # rather than the sterile recovery of a curve sampled without quote noise.
    quote_iv = smooth_iv + 1e-4 * (
        1.20 * np.sin(9.0 * quote_k + 0.4) + 0.55 * np.cos(21.0 * quote_k)
    )
    result = calibrate_slice(
        quote_k,
        quote_iv * quote_iv * expiry,
        expiry,
        n_order=9,
        reg_lambda=3e-8,
        reg_power=1.2,
    )
    dense_k = np.linspace(-0.48, 0.42, 480)
    return SmileCase(
        expiry=expiry,
        quote_k=quote_k,
        quote_iv=quote_iv,
        dense_k=dense_k,
        target_dense_iv=np.sqrt(ssvi_total_variance(dense_k) / expiry),
        result=result,
    )


def mixture_call(
    k: np.ndarray,
    weights: np.ndarray,
    means: np.ndarray,
    sigmas: np.ndarray,
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


def fit_event_case() -> EventCase:
    """Fit an asymmetric, martingale-normalized two-regime event smile."""

    expiry = 24.0 / 365.0
    weight_left = 0.56
    weights = np.array([weight_left, 1.0 - weight_left])
    raw_means = np.array([-0.075, 0.085])
    sigmas = np.array([0.052, 0.047])
    shift = -np.log(np.sum(weights * np.exp(raw_means + 0.5 * sigmas * sigmas)))
    means = raw_means + shift

    quote_k = np.linspace(-0.22, 0.22, 37)
    target_call = mixture_call(quote_k, weights, means, sigmas)
    target_w = implied_total_variance(quote_k, target_call)
    quote_iv = np.sqrt(target_w / expiry)
    result = calibrate_slice(
        quote_k,
        target_w,
        expiry,
        n_order=16,
        reg_lambda=1e-11,
    )
    dense_k = np.linspace(-0.25, 0.25, 500)
    dense_call = mixture_call(dense_k, weights, means, sigmas)
    dense_iv = np.sqrt(implied_total_variance(dense_k, dense_call) / expiry)
    smile = SmileCase(
        expiry=expiry,
        quote_k=quote_k,
        quote_iv=quote_iv,
        dense_k=dense_k,
        target_dense_iv=dense_iv,
        result=result,
    )
    return EventCase(
        smile=smile,
        weight_left=weight_left,
        means=means,
        sigmas=sigmas,
    )


def figure_butterfly(spx: SmileCase) -> dict[str, float]:
    """Show convex calls and recover the density with tradable butterflies."""

    slice_ = spx.result.slice
    y = np.linspace(0.68, 1.38, 360)
    calls = slice_.call_price(np.log(y))

    fig, axes = plt.subplots(1, 2, figsize=WIDE)

    axes[0].plot(y, calls, color=PALETTE["teal"], label="model call")
    axes[0].plot(
        y,
        np.maximum(1.0 - y, 0.0),
        color=PALETTE["muted"],
        ls="--",
        label="intrinsic value",
    )
    y1, y2 = 0.84, 1.16
    c1, c2 = [float(slice_.call_price(np.log(v))) for v in (y1, y2)]
    chord_y = np.linspace(y1, y2, 100)
    chord = c1 + (c2 - c1) * (chord_y - y1) / (y2 - y1)
    curve = slice_.call_price(np.log(chord_y))
    axes[0].plot(chord_y, chord, color=PALETTE["amber"], ls=":", label="chord")
    axes[0].fill_between(chord_y, curve, chord, color=PALETTE["amber"], alpha=0.10)
    axes[0].set_xlabel(r"strike / forward $K/F$")
    axes[0].set_ylabel("normalized call value")
    axes[0].legend(loc="upper right")
    callout(
        axes[0],
        "convex: the chord stays above",
        xy=(1.02, float(np.interp(1.02, chord_y, chord))),
        xytext=(0.92, 0.20),
    )
    label_panel(axes[0], "A")

    h = 0.004
    butterflies = (
        slice_.call_price(np.log(y - h))
        - 2.0 * calls
        + slice_.call_price(np.log(y + h))
    ) / (h * h)
    x_grid, density_x = slice_.density()
    density_y = np.interp(np.log(y), x_grid, density_x) / y
    axes[1].plot(y, density_y, color=PALETTE["ink"], lw=2.2, label="model density")
    axes[1].scatter(
        y[::12],
        butterflies[::12],
        color=PALETTE["rust"],
        s=18,
        zorder=4,
        label=rf"$h={h:.3f}$ butterflies",
    )
    axes[1].fill_between(y, 0.0, butterflies, color=PALETTE["teal"], alpha=0.10)
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.8)
    axes[1].set_xlabel(r"central strike / forward $K/F$")
    axes[1].set_ylabel("density recovered from call prices")
    axes[1].legend(loc="upper right")
    label_panel(axes[1], "B")

    fig.subplots_adjust(wspace=0.31)
    save(fig, OUT / "fig_lqd_fresh_butterfly.pdf")
    relative = np.abs(butterflies - density_y) / np.maximum(density_y, 1e-12)
    return {
        "min_butterfly": float(np.min(butterflies)),
        "max_relative_density_error": float(np.max(relative)),
    }


def figure_ruler(toy: ToyCase) -> None:
    """Walk from a percentile ruler to quantiles and then to the quoted smile."""

    fig, axes = plt.subplots(1, 3, figsize=(8.4, 3.10))

    z = np.linspace(-4.8, 4.8, 700)
    u = expit(z)
    axes[0].plot(z, 100.0 * u, color=PALETTE["teal"])
    marked_u = np.array([0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
    marked_z = logit(marked_u)
    axes[0].scatter(marked_z, 100.0 * marked_u, color=PALETTE["rust"], s=18, zorder=4)
    for probability, z_value in zip(marked_u[[0, 3, 6]], marked_z[[0, 3, 6]], strict=True):
        axes[0].annotate(
            f"{100 * probability:.0f}%",
            (z_value, 100.0 * probability),
            xytext=(0, 7),
            textcoords="offset points",
            ha="center",
            fontsize=9.0,
            color=PALETTE["muted"],
        )
    axes[0].set_xlabel("log-odds coordinate")
    axes[0].set_ylabel("percentile (%)")
    axes[0].set_title("one ruler, infinite tails")
    label_panel(axes[0], "A")

    percentile = np.linspace(0.005, 0.995, 700)
    quantile = np.interp(logit(percentile), toy.slice.z, toy.slice.q_z)
    axes[1].plot(100.0 * percentile, quantile, color=PALETTE["teal"])
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.8)
    axes[1].scatter(
        [100.0 * toy.u_atm, 100.0 * toy.u_ten],
        [0.0, 0.10],
        color=[PALETTE["rust"], PALETTE["amber"]],
        zorder=4,
    )
    axes[1].annotate(
        "forward",
        (100.0 * toy.u_atm, 0.0),
        xytext=(-30, 11),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[1].annotate(
        r"$k=0.10$",
        (100.0 * toy.u_ten, 0.10),
        xytext=(-11, 11),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[1].set_xlabel("percentile (%)")
    axes[1].set_ylabel("log-return quantile")
    axes[1].set_title("the percentile ruler bends")
    label_panel(axes[1], "B")

    k = np.linspace(-0.26, 0.26, 260)
    iv = toy.slice.implied_vol(k, toy.expiry)
    axes[2].plot(k, 100.0 * iv, color=PALETTE["teal"])
    axes[2].scatter(
        [0.0, 0.10],
        [100.0 * toy.target_atm_vol, 100.0 * toy.iv_ten],
        color=[PALETTE["rust"], PALETTE["amber"]],
        zorder=4,
    )
    axes[2].annotate(
        "20.00%",
        (0.0, 100.0 * toy.target_atm_vol),
        xytext=(-34, -18),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[2].annotate(
        f"{100.0 * toy.iv_ten:.2f}%",
        (0.10, 100.0 * toy.iv_ten),
        xytext=(4, 8),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[2].set_xlabel("log-moneyness")
    axes[2].set_ylabel("implied volatility (%)")
    axes[2].set_title("the option market's view")
    label_panel(axes[2], "C")

    fig.subplots_adjust(wspace=0.46)
    save(fig, OUT / "fig_lqd_fresh_ruler.pdf")


def figure_modes(toy: ToyCase) -> None:
    """Perturb one production basis coefficient at a time."""

    amplitude = 0.10
    modes: list[tuple[int, str, str, LQDSlice]] = []
    for degree, name, color in (
        (2, "mode 2", PALETTE["blue"]),
        (3, "mode 3", PALETTE["amber"]),
        (4, "mode 4", PALETTE["violet"]),
    ):
        coeffs = np.zeros(5)
        coeffs[degree - 2] = amplitude
        params = LQDParams(np.log(toy.scale), np.log(toy.scale), coeffs)
        modes.append((degree, name, color, build_slice(params)))

    fig, axes = plt.subplots(1, 3, figsize=(8.5, 3.15))

    u = np.linspace(0.002, 0.998, 700)
    base_g = g_eval(toy.slice.params, u)
    for _degree, name, color, slice_ in modes:
        axes[0].plot(u, g_eval(slice_.params, u) - base_g, color=color, label=name)
    axes[0].axhline(0.0, color=PALETTE["muted"], lw=0.8)
    axes[0].set_xlabel("percentile")
    axes[0].set_ylabel("change in log-spacing")
    axes[0].set_title("the three deformations")
    axes[0].legend(loc="lower left")
    label_panel(axes[0], "A")

    k = np.linspace(-0.30, 0.30, 300)
    axes[1].plot(
        k,
        100.0 * toy.slice.implied_vol(k, toy.expiry),
        color=PALETTE["muted"],
        ls="--",
        label="baseline",
    )
    for _degree, name, color, slice_ in modes:
        axes[1].plot(k, 100.0 * slice_.implied_vol(k, toy.expiry), color=color, label=name)
    axes[1].set_xlabel("log-moneyness")
    axes[1].set_ylabel("implied volatility (%)")
    axes[1].set_title("what the trader sees")
    label_panel(axes[1], "B")

    x0, density0 = toy.slice.density()
    selected0 = (x0 > -0.42) & (x0 < 0.38)
    axes[2].plot(
        x0[selected0],
        density0[selected0],
        color=PALETTE["muted"],
        ls="--",
        label="baseline",
    )
    for _degree, name, color, slice_ in modes:
        x, density = slice_.density()
        selected = (x > -0.42) & (x < 0.38)
        axes[2].plot(x[selected], density[selected], color=color, label=name)
    axes[2].set_xlabel("log-forward return")
    axes[2].set_ylabel("probability density")
    axes[2].set_title("what the distribution does")
    label_panel(axes[2], "C")

    fig.subplots_adjust(wspace=0.44)
    save(fig, OUT / "fig_lqd_fresh_modes.pdf")


def figure_tails(spx: SmileCase) -> None:
    """Draw the three-link endpoint-scale-to-Lee-slope map."""

    a_left_fit, a_right_fit = endpoint_scales(spx.result.params)
    beta_left_fit, beta_right_fit = lee_slopes(spx.result.params)
    p_left_fit = 1.0 / a_left_fit
    p_right_fit = 1.0 / a_right_fit - 1.0

    fig, axes = plt.subplots(1, 3, figsize=(8.5, 3.15))

    endpoint_log = np.linspace(-4.7, -0.02, 500)
    endpoint_scale = np.exp(endpoint_log)
    axes[0].plot(endpoint_log, endpoint_scale, color=PALETTE["teal"])
    axes[0].scatter(
        [np.log(a_left_fit), np.log(a_right_fit)],
        [a_left_fit, a_right_fit],
        color=[PALETTE["blue"], PALETTE["amber"]],
        zorder=4,
    )
    axes[0].set_xlabel("endpoint log-spacing")
    axes[0].set_ylabel("tail scale $A$")
    axes[0].set_title(r"first link: $A=e^h$")
    label_panel(axes[0], "A")

    scale = np.linspace(0.015, 0.985, 700)
    p_left = 1.0 / scale
    p_right = 1.0 / scale - 1.0
    axes[1].semilogy(scale, p_left, color=PALETTE["blue"], label="left tail")
    axes[1].semilogy(scale, p_right, color=PALETTE["amber"], label="right tail")
    axes[1].scatter(
        [a_left_fit, a_right_fit],
        [p_left_fit, p_right_fit],
        color=[PALETTE["blue"], PALETTE["amber"]],
        edgecolor=PALETTE["ink"],
        linewidth=0.5,
        zorder=4,
    )
    axes[1].set_xlabel("tail scale $A$")
    axes[1].set_ylabel("critical moment exponent $p$")
    axes[1].set_title("second link: moment budget")
    axes[1].legend(loc="upper right")
    label_panel(axes[1], "B")

    p = np.logspace(-3, 2.2, 800)
    axes[2].semilogx(p, lee_psi(p), color=PALETTE["teal"])
    axes[2].scatter(
        [p_left_fit, p_right_fit],
        [beta_left_fit, beta_right_fit],
        color=[PALETTE["blue"], PALETTE["amber"]],
        edgecolor=PALETTE["ink"],
        linewidth=0.5,
        zorder=4,
    )
    axes[2].annotate(
        "left fit",
        (p_left_fit, beta_left_fit),
        xytext=(-29, 12),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[2].annotate(
        "right fit",
        (p_right_fit, beta_right_fit),
        xytext=(5, 10),
        textcoords="offset points",
        fontsize=9.0,
        color=PALETTE["muted"],
    )
    axes[2].axhline(2.0, color=PALETTE["muted"], lw=0.8, ls=":")
    axes[2].set_xlabel("critical moment exponent $p$")
    axes[2].set_ylabel(r"Lee wing slope $\psi(p)$")
    axes[2].set_ylim(-0.02, 2.05)
    axes[2].set_title("third link: asymptotic wing")
    label_panel(axes[2], "C")

    fig.subplots_adjust(wspace=0.47)
    save(fig, OUT / "fig_lqd_fresh_tails.pdf")


def figure_spx(spx: SmileCase) -> dict[str, float]:
    """Plot the production fit, quote residuals, and distributional content."""

    model_dense_iv = spx.result.slice.implied_vol(spx.dense_k, spx.expiry)
    model_quote_iv = spx.result.slice.implied_vol(spx.quote_k, spx.expiry)
    residual_bp = 1e4 * (model_quote_iv - spx.quote_iv)

    fig, axes = plt.subplots(1, 3, figsize=(8.55, 3.18))

    axes[0].plot(
        spx.dense_k,
        100.0 * spx.target_dense_iv,
        color=PALETTE["muted"],
        lw=2.2,
        label="smooth quote oracle",
    )
    axes[0].plot(
        spx.dense_k,
        100.0 * model_dense_iv,
        color=PALETTE["teal"],
        ls="--",
        label="production LQD",
    )
    axes[0].scatter(
        spx.quote_k,
        100.0 * spx.quote_iv,
        color=PALETTE["rust"],
        s=18,
        zorder=4,
        label="quotes",
    )
    axes[0].set_xlabel("log-moneyness")
    axes[0].set_ylabel("implied volatility (%)")
    axes[0].set_title("a skewed index strip")
    axes[0].legend(loc="upper right")
    label_panel(axes[0], "A")

    axes[1].axhspan(-2.0, 2.0, color=PALETTE["teal"], alpha=0.08)
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.8)
    axes[1].vlines(spx.quote_k, 0.0, residual_bp, color=PALETTE["rust"], lw=1.2)
    axes[1].scatter(spx.quote_k, residual_bp, color=PALETTE["rust"], s=16, zorder=4)
    axes[1].set_xlabel("quoted log-moneyness")
    axes[1].set_ylabel("fit minus quote (vol bp)")
    axes[1].set_title("the error ledger")
    label_panel(axes[1], "B")

    x, density = spx.result.slice.density()
    atm_vol = float(spx.result.slice.implied_vol(0.0, spx.expiry))
    atm_variance = atm_vol * atm_vol * spx.expiry
    normal_density = norm.pdf(x, loc=-0.5 * atm_variance, scale=np.sqrt(atm_variance))
    selected = (x > -0.62) & (x < 0.42)
    left_tail = selected & (x < -0.20)
    axes[2].plot(x[selected], density[selected], color=PALETTE["teal"], label="LQD density")
    axes[2].plot(
        x[selected],
        normal_density[selected],
        color=PALETTE["muted"],
        ls="--",
        label="ATM-matched normal",
    )
    axes[2].fill_between(
        x[left_tail],
        0.0,
        density[left_tail],
        color=PALETTE["rust"],
        alpha=0.12,
    )
    axes[2].set_xlabel("log-forward return")
    axes[2].set_ylabel("probability density")
    axes[2].set_title("the downside mass behind the skew")
    axes[2].legend(loc="upper left")
    label_panel(axes[2], "C")

    fig.subplots_adjust(wspace=0.47)
    save(fig, OUT / "fig_lqd_fresh_spx.pdf")
    return {
        "max_error_bp": float(np.max(np.abs(residual_bp))),
        "rms_error_bp": float(np.sqrt(np.mean(residual_bp * residual_bp))),
    }


def figure_event(event: EventCase) -> dict[str, float]:
    """Show the high-order fit resolving an asymmetric double-hat density."""

    smile = event.smile
    model_dense_iv = smile.result.slice.implied_vol(smile.dense_k, smile.expiry)
    model_quote_iv = smile.result.slice.implied_vol(smile.quote_k, smile.expiry)
    residual_bp = 1e4 * (model_quote_iv - smile.quote_iv)

    fig, axes = plt.subplots(1, 2, figsize=WIDE)

    axes[0].plot(
        smile.dense_k,
        100.0 * smile.target_dense_iv,
        color=PALETTE["ink"],
        lw=2.2,
        label="two-regime target",
    )
    axes[0].plot(
        smile.dense_k,
        100.0 * model_dense_iv,
        color=PALETTE["teal"],
        ls="--",
        label="production LQD",
    )
    axes[0].scatter(
        smile.quote_k,
        100.0 * smile.quote_iv,
        color=PALETTE["rust"],
        s=14,
        zorder=4,
        label="quotes",
    )
    axes[0].set_xlabel("log-moneyness")
    axes[0].set_ylabel("implied volatility (%)")
    axes[0].set_title("one smile, two event regimes")
    axes[0].legend(loc="upper right")
    label_panel(axes[0], "A")

    x, model_density = smile.result.slice.density()
    target_density = (
        event.weight_left * norm.pdf(x, event.means[0], event.sigmas[0])
        + (1.0 - event.weight_left) * norm.pdf(x, event.means[1], event.sigmas[1])
    )
    selected = (x > -0.25) & (x < 0.25)
    axes[1].plot(
        x[selected],
        target_density[selected],
        color=PALETTE["ink"],
        lw=2.2,
        label="two-regime density",
    )
    axes[1].plot(
        x[selected],
        model_density[selected],
        color=PALETTE["teal"],
        ls="--",
        label="LQD density",
    )
    axes[1].fill_between(
        x[selected],
        0.0,
        model_density[selected],
        color=PALETTE["teal"],
        alpha=0.08,
    )
    axes[1].set_xlabel("log-forward return")
    axes[1].set_ylabel("probability density")
    axes[1].set_title("both hats survive the inversion")
    axes[1].legend(loc="upper right")
    label_panel(axes[1], "B")

    fig.subplots_adjust(wspace=0.31)
    save(fig, OUT / "fig_lqd_fresh_event.pdf")
    return {
        "max_error_bp": float(np.max(np.abs(residual_bp))),
        "rms_error_bp": float(np.sqrt(np.mean(residual_bp * residual_bp))),
    }


def jacobian_check(spx: SmileCase) -> dict[str, float]:
    """Compare the production analytic Jacobian with deterministic central FD."""

    theta = spx.result.params.to_vector()
    target_w = spx.quote_iv * spx.quote_iv * spx.expiry
    target_price = black_call(spx.quote_k, target_w)
    inv_vega = 1.0 / (
        black_vega_sigma(spx.quote_k, spx.quote_iv, spx.expiry) + _VEGA_FLOOR
    )
    sqrt_weights = np.ones_like(spx.quote_k)
    degrees = np.arange(2, spx.result.params.order + 1, dtype=float)
    reg = np.sqrt(3e-8) * np.where(degrees >= 4, degrees**1.2, 0.0)
    args = (
        spx.quote_k,
        target_price,
        inv_vega,
        sqrt_weights,
        reg,
        None,
        None,
        1e6,
        None,
        None,
        _BARRIER_CENTER,
        _BARRIER_SCALE,
        MID_ANCHOR_WEIGHT,
        None,
        None,
        None,
        None,
        OPT_N_POINTS,
    )
    analytic = residual_jacobian(theta, *args)
    central = np.empty_like(analytic)
    for column in range(theta.size):
        step = 2e-6 * max(1.0, abs(theta[column]))
        plus = theta.copy()
        minus = theta.copy()
        plus[column] += step
        minus[column] -= step
        central[:, column] = (
            _residuals(plus, *args) - _residuals(minus, *args)
        ) / (2.0 * step)

    denominator = np.maximum(np.linalg.norm(central, axis=0), 1e-14)
    relative_error = np.linalg.norm(analytic - central, axis=0) / denominator
    labels = ["L", "R"] + [rf"$a_{{{degree}}}$" for degree in range(2, 10)]

    fig, axes = plt.subplots(1, 2, figsize=WIDE)

    fit_block = analytic[: spx.quote_k.size]
    normalized = fit_block / np.maximum(np.max(np.abs(fit_block), axis=0), 1e-14)
    image = axes[0].imshow(
        normalized,
        origin="lower",
        aspect="auto",
        cmap="coolwarm",
        vmin=-1.0,
        vmax=1.0,
    )
    axes[0].set_xticks(np.arange(theta.size), labels, rotation=45, ha="right")
    row_ticks = np.array([0, 4, 8, 12, 16, 20, 23])
    axes[0].set_yticks(row_ticks, [f"{spx.quote_k[i]:+.2f}" for i in row_ticks])
    axes[0].set_xlabel("parameter column")
    axes[0].set_ylabel("quoted log-moneyness")
    axes[0].set_title("where each parameter moves prices")
    colorbar = fig.colorbar(image, ax=axes[0], fraction=0.046, pad=0.03)
    colorbar.set_label("column-normalized sensitivity")
    label_panel(axes[0], "A")

    axes[1].bar(np.arange(theta.size), relative_error, color=PALETTE["teal"])
    axes[1].axhline(1e-6, color=PALETTE["rust"], ls="--", lw=1.0, label="one ppm")
    axes[1].set_yscale("log")
    axes[1].set_xticks(np.arange(theta.size), labels, rotation=45, ha="right")
    axes[1].set_xlabel("parameter column")
    axes[1].set_ylabel("analytic vs central-FD relative error")
    axes[1].set_title("an independent derivative audit")
    axes[1].legend(loc="upper right")
    label_panel(axes[1], "B")

    fig.subplots_adjust(wspace=0.36)
    save(fig, OUT / "fig_lqd_fresh_jacobian.pdf")
    return {
        "max_relative_error": float(np.max(relative_error)),
        "n_parameters": float(theta.size),
    }


def _tex_scientific(value: float) -> str:
    """Format a scalar as a robust math-mode LaTeX macro body."""

    if value == 0.0:
        return r"\ensuremath{0}"
    exponent = int(np.floor(np.log10(abs(value))))
    mantissa = value / 10.0**exponent
    return rf"\ensuremath{{{mantissa:.2f}\times10^{{{exponent}}}}}"


def write_macros(
    toy: ToyCase,
    spx: SmileCase,
    event: EventCase,
    butterfly: dict[str, float],
    spx_errors: dict[str, float],
    event_errors: dict[str, float],
    jacobian: dict[str, float],
) -> None:
    """Write all numbers used by worked examples and diagnostic callouts."""

    spx_handles = atm_handles(spx.result.slice, spx.expiry)
    spx_a_left, spx_a_right = endpoint_scales(spx.result.params)
    spx_beta_left, spx_beta_right = lee_slopes(spx.result.params)
    spx_varswap_vol = np.sqrt(spx.result.slice.var_swap_strike() / spx.expiry)
    event_a_left, event_a_right = endpoint_scales(event.smile.result.params)
    event_model_iv = event.smile.result.slice.implied_vol(
        event.smile.quote_k, event.smile.expiry
    )
    event_martingale_error = event.smile.result.slice.martingale_check() - 1.0
    spx_martingale_error = spx.result.slice.martingale_check() - 1.0

    lines = [
        "% Auto-generated by Docs/notes/figures/gen_lqd_fresh.py -- do not edit.",
        "% Exact-20%-ATM half-year logistic toy.",
        rf"\newcommand{{\lqdfreshtoyexpiry}}{{{toy.expiry:.2f}}}",
        rf"\newcommand{{\lqdfreshtoyatm}}{{{100.0 * toy.target_atm_vol:.4f}}}",
        rf"\newcommand{{\lqdfreshtoyscale}}{{{toy.scale:.8f}}}",
        rf"\newcommand{{\lqdfreshtoymu}}{{{toy.slice.mu:.8f}}}",
        rf"\newcommand{{\lqdfreshtoyuatm}}{{{toy.u_atm:.6f}}}",
        rf"\newcommand{{\lqdfreshtoyuatmpct}}{{{100.0 * toy.u_atm:.4f}}}",
        rf"\newcommand{{\lqdfreshtoyuten}}{{{toy.u_ten:.6f}}}",
        rf"\newcommand{{\lqdfreshtoystriketen}}{{{np.exp(0.10):.6f}}}",
        rf"\newcommand{{\lqdfreshtoyshareten}}{{{toy.share_ten:.8f}}}",
        rf"\newcommand{{\lqdfreshtoycashten}}{{{toy.cash_ten:.8f}}}",
        rf"\newcommand{{\lqdfreshtoycallten}}{{{toy.call_ten:.8f}}}",
        rf"\newcommand{{\lqdfreshtoycalltenpct}}{{{100.0 * toy.call_ten:.4f}}}",
        rf"\newcommand{{\lqdfreshtoyivten}}{{{100.0 * toy.iv_ten:.4f}}}",
        "% SPX-like production fit.",
        rf"\newcommand{{\lqdfreshspxorder}}{{{spx.result.params.order}}}",
        rf"\newcommand{{\lqdfreshspxnquotes}}{{{spx.quote_k.size}}}",
        rf"\newcommand{{\lqdfreshspxatm}}{{{100.0 * spx_handles.sigma0:.4f}}}",
        rf"\newcommand{{\lqdfreshspxskew}}{{{spx_handles.skew:.6f}}}",
        rf"\newcommand{{\lqdfreshspxcurvature}}{{{spx_handles.curvature:.6f}}}",
        rf"\newcommand{{\lqdfreshspxmaxerr}}{{{spx_errors['max_error_bp']:.3f}}}",
        rf"\newcommand{{\lqdfreshspxrmserr}}{{{spx_errors['rms_error_bp']:.3f}}}",
        rf"\newcommand{{\lqdfreshspxnfev}}{{{spx.result.n_evaluations}}}",
        rf"\newcommand{{\lqdfreshspxAL}}{{{spx_a_left:.6f}}}",
        rf"\newcommand{{\lqdfreshspxAR}}{{{spx_a_right:.6f}}}",
        rf"\newcommand{{\lqdfreshspxbetaL}}{{{spx_beta_left:.6f}}}",
        rf"\newcommand{{\lqdfreshspxbetaR}}{{{spx_beta_right:.6f}}}",
        rf"\newcommand{{\lqdfreshspxvarswap}}{{{100.0 * spx_varswap_vol:.4f}}}",
        rf"\newcommand{{\lqdfreshspxmart}}{{{_tex_scientific(spx_martingale_error)}}}",
        "% Asymmetric double-hat event fit.",
        rf"\newcommand{{\lqdfresheventorder}}{{{event.smile.result.params.order}}}",
        rf"\newcommand{{\lqdfresheventnquotes}}{{{event.smile.quote_k.size}}}",
        rf"\newcommand{{\lqdfresheventweightleft}}{{{100.0 * event.weight_left:.1f}}}",
        rf"\newcommand{{\lqdfresheventmeanleft}}{{{event.means[0]:.6f}}}",
        rf"\newcommand{{\lqdfresheventmeanright}}{{{event.means[1]:.6f}}}",
        rf"\newcommand{{\lqdfresheventmaxerr}}{{{event_errors['max_error_bp']:.3f}}}",
        rf"\newcommand{{\lqdfresheventrmserr}}{{{event_errors['rms_error_bp']:.3f}}}",
        rf"\newcommand{{\lqdfresheventAL}}{{{event_a_left:.6f}}}",
        rf"\newcommand{{\lqdfresheventAR}}{{{event_a_right:.6f}}}",
        rf"\newcommand{{\lqdfresheventmart}}{{{_tex_scientific(event_martingale_error)}}}",
        rf"\newcommand{{\lqdfresheventmaxquotediv}}{{{1e4 * np.max(np.abs(event_model_iv - event.smile.quote_iv)):.3f}}}",
        "% Convexity and derivative checks.",
        rf"\newcommand{{\lqdfreshminbutterfly}}{{{butterfly['min_butterfly']:.6f}}}",
        rf"\newcommand{{\lqdfreshbutterflyrelerr}}{{{100.0 * butterfly['max_relative_density_error']:.4f}}}",
        rf"\newcommand{{\lqdfreshjacnparams}}{{{int(jacobian['n_parameters'])}}}",
        rf"\newcommand{{\lqdfreshjacmaxrel}}{{{_tex_scientific(jacobian['max_relative_error'])}}}",
        "% Ready-to-drop worked-example tables.",
        r"\newcommand{\lqdfreshtoytable}{%",
        r"\begin{tabular}{lr}",
        r"\toprule",
        r"Quantity & Production value\\",
        r"\midrule",
        rf"Solved scale & {toy.scale:.8f}\\",
        rf"Martingale shift & {toy.slice.mu:.8f}\\",
        rf"ATM percentile & {100.0 * toy.u_atm:.4f}\%\\",
        rf"$C(0.10)$ & {toy.call_ten:.8f}\\",
        rf"$\sigma_{{\mathrm{{BS}}}}(0.10)$ & {100.0 * toy.iv_ten:.4f}\%\\",
        r"\bottomrule",
        r"\end{tabular}}",
        r"\newcommand{\lqdfreshfitdiagtable}{%",
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Diagnostic & SPX-like & Event\\",
        r"\midrule",
        rf"Model order & {spx.result.params.order} & {event.smile.result.params.order}\\",
        rf"Quotes & {spx.quote_k.size} & {event.smile.quote_k.size}\\",
        rf"Max error (vol bp) & {spx_errors['max_error_bp']:.3f} & {event_errors['max_error_bp']:.3f}\\",
        rf"RMS error (vol bp) & {spx_errors['rms_error_bp']:.3f} & {event_errors['rms_error_bp']:.3f}\\",
        rf"$A_L$ & {spx_a_left:.6f} & {event_a_left:.6f}\\",
        rf"$A_R$ & {spx_a_right:.6f} & {event_a_right:.6f}\\",
        r"\bottomrule",
        r"\end{tabular}}",
    ]
    (OUT / "lqd_fresh_tables.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Generate every figure and the matching LaTeX macros."""

    print("Solving the exact-ATM logistic toy ...")
    toy = solve_logistic_toy()
    print("Fitting the SPX-like SSVI quote strip ...")
    spx = fit_spx_case()
    print("Fitting the asymmetric double-hat event strip ...")
    event = fit_event_case()

    print("Drawing the independent seven-figure suite ...")
    butterfly = figure_butterfly(spx)
    figure_ruler(toy)
    figure_modes(toy)
    figure_tails(spx)
    spx_errors = figure_spx(spx)
    event_errors = figure_event(event)
    jacobian = jacobian_check(spx)
    write_macros(toy, spx, event, butterfly, spx_errors, event_errors, jacobian)

    print(
        "Wrote 7 figures + lqd_fresh_tables.tex; "
        f"SPX max/RMS={spx_errors['max_error_bp']:.3f}/{spx_errors['rms_error_bp']:.3f} bp, "
        f"event max/RMS={event_errors['max_error_bp']:.3f}/{event_errors['rms_error_bp']:.3f} bp"
    )


if __name__ == "__main__":
    main()
