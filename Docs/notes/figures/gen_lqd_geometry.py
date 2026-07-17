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
* ``lqd_geometry_tables.tex``   -- macros for every number quoted in the note.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
from scipy.special import expit, logit

from volfit.calib.calendar import calendar_floor_targets
from volfit.models.lqd.basis import g_eval
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice
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

    ax_ledger.plot(
        u_grid, share_near, color=PALETTE["ink"], lw=1.5,
        label=rf"near, $\tau={NEAR_EXPIRY}$",
    )
    ax_ledger.plot(
        u_grid, share_far, color=PALETTE["blue"], lw=1.5,
        label=rf"far, $\tau={EXPIRY}$",
    )
    ax_ledger.set_xlabel(r"rank $u$")
    ax_ledger.set_ylabel(r"upper share $G$")
    ax_ledger.legend(frameon=False, fontsize=8.5)
    label_panel(ax_ledger, "A")

    ax_gap.plot(
        u_grid, share_far - share_near, color=PALETTE["green"], lw=1.5,
        label="legitimate pair",
    )
    ax_gap.plot(
        u_grid, share_cross - share_near, color=PALETTE["rust"], lw=1.5,
        label="crossed pair",
    )
    ax_gap.plot(
        u_grid, share_healed - share_near, color=PALETTE["blue"], lw=1.3,
        ls="--", label="crossed + soft floor",
    )
    ax_gap.axhline(0.0, color=PALETTE["muted"], lw=0.7, alpha=0.7)
    ax_gap.set_xlabel(r"rank $u$")
    ax_gap.set_ylabel(r"calendar gap $G_{\mathrm{far}}-G_{\mathrm{near}}$")
    ax_gap.legend(frameon=False, fontsize=8.5)
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
    ]
    (OUT / "lqd_geometry_tables.tex").write_text("\n".join(lines) + "\n")


def main() -> None:
    spx = fit_spx_case()
    stats: dict[str, float] = {}
    stats.update(figure_charts(spx))
    stats.update(figure_ortho(spx))
    stats.update(figure_calendar(spx))
    write_tables(stats)
    for key, value in sorted(stats.items()):
        print(f"{key:26s} {value:.6g}")


if __name__ == "__main__":
    main()
