"""Figure suite for the forward edition of Note 04 (local volatility).

Run from the repository root with the project virtual environment::

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lv_forward.py

Every surface, price, sensitivity and grid in these figures is produced by the
production local-volatility implementation (``volfit.models.localvol`` and the
production grid builder); local formulae appear only to define synthetic
truths and deterministic quote noise.  The synthetic round trip reproduces the
construction of ``gen_lv.py`` exactly; the Bloomberg per-expiry panel is drawn
from ``lv_numbers.json`` (the artifact of ``gen_lv.py``'s product-path run) so
this suite never re-times the benchmark.

Outputs, written next to this script:

* ``fig_lvf_wrongway.pdf``  -- Dupire extraction from noisy data vs forward fit;
* ``fig_lvf_tri.pdf``       -- the triangulated local-vol sheet (3-D, app-style);
* ``fig_lvf_basis.pdf``     -- P1 anatomy: triangulation, hats, partition of unity;
* ``fig_lvf_monotone.pdf``  -- implicit Euler vs Crank--Nicolson on a coarse grid;
* ``fig_lvf_influence.pdf`` -- one vertex's influence + tangent-vs-FD audit;
* ``fig_lvf_recovery.pdf``  -- synthetic round trip: IV fit and surface error;
* ``fig_lvf_identify.pdf``  -- two surfaces, one set of quotes (identifiability);
* ``fig_lvf_rescue.pdf``    -- the short-dated coverage rescue (grid builder);
* ``fig_lvf_rms.pdf``       -- Bloomberg per-expiry RMS (from lv_numbers.json);
* ``lv_forward_tables.tex`` -- macros for every number quoted in the note.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.tri as mtri  # noqa: E402

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, label_panel, save, setup  # noqa: E402

from volfit.core.black import implied_total_variance  # noqa: E402
from volfit.models.localvol.affine import (  # noqa: E402
    AffineVarianceSurface,
    solve_affine_dupire,
)
from volfit.models.localvol.affine_calib import OptionQuote, calibrate_affine  # noqa: E402
from volfit.models.localvol.dupire import dupire_local_variance  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()

EXPIRY_COLORS = [PALETTE["teal"], PALETTE["blue"], PALETTE["amber"], PALETTE["rust"]]
EXPIRIES = np.array([0.15, 0.30, 0.60, 1.00])
QUOTE_STRIKES = np.linspace(0.80, 1.30, 11)


# ---------------------------------------------------------------------------
# Shared synthetic truth and round trip (the construction of gen_lv.py).
# ---------------------------------------------------------------------------


def truth_surface() -> AffineVarianceSurface:
    t_nodes = np.array([0.0, 0.5, 1.0])
    x_nodes = np.array([0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.7, 2.0])

    def loc_var(t: float, x: float) -> float:
        base = 0.035 + 0.05 * np.exp(-2.2 * (x - 0.7))
        return float(np.clip(base, 0.0064, 0.16) * (1.0 + 0.08 * t))

    theta = np.array([[loc_var(t, x) for x in x_nodes] for t in t_nodes])
    return AffineVarianceSurface(t_nodes, x_nodes, theta)


DENSE_X = np.linspace(0.2, 3.0, 401)
DENSE_T = np.linspace(0.0, 1.0, 201)


def round_trip() -> dict:
    """Price the truth, quote it, and recover from a flat seed (production)."""

    truth = truth_surface()
    sol = solve_affine_dupire(truth, DENSE_X, DENSE_T, EXPIRIES)

    options, target = [], {}
    for ie, expiry in enumerate(EXPIRIES):
        px = sol.price_at(ie, QUOTE_STRIKES)
        for x, p in zip(QUOTE_STRIKES, px):
            options.append(OptionQuote(t=float(expiry), x=float(x), price=float(p)))
        w = implied_total_variance(np.log(QUOTE_STRIKES), px)
        target[float(expiry)] = np.sqrt(w / expiry)

    x_nodes = np.array([0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.6])
    t_nodes = np.array([0.1, 0.25, 0.5, 1.0])
    seed = AffineVarianceSurface(t_nodes, x_nodes, np.full((4, 7), 0.04))
    cal = calibrate_affine(seed, options, DENSE_X, DENSE_T)

    sol2 = solve_affine_dupire(cal.surface, DENSE_X, DENSE_T, EXPIRIES)
    recovered = {}
    residual_bp = {}
    for ie, expiry in enumerate(EXPIRIES):
        px = sol2.price_at(ie, QUOTE_STRIKES)
        w = implied_total_variance(np.log(QUOTE_STRIKES), px)
        iv = np.sqrt(w / expiry)
        recovered[float(expiry)] = iv
        residual_bp[float(expiry)] = 1e4 * (iv - target[float(expiry)])

    tt = np.linspace(float(EXPIRIES[0]), float(EXPIRIES[-1]), 41)
    xx = np.linspace(float(QUOTE_STRIKES[0]), float(QUOTE_STRIKES[-1]), 51)
    dvol = np.array([
        100.0 * (np.sqrt(np.maximum(cal.surface.variance(xx, float(t)), 0.0))
                 - np.sqrt(np.maximum(truth.variance(xx, float(t)), 0.0)))
        for t in tt
    ])
    return dict(
        truth=truth, cal=cal, options=options, target=target,
        recovered=recovered, residual_bp=residual_bp,
        surf_err_grid=(tt, xx, dvol),
        surf_rms=float(np.sqrt(np.mean(dvol**2))),
        surf_max=float(np.max(np.abs(dvol))),
        max_err_bp=float(max(np.max(np.abs(v)) for v in residual_bp.values())),
        n_evals=int(cal.n_evals),
        n_vertices=int(cal.surface.theta.size),
    )


# ---------------------------------------------------------------------------
# Figure 1: the wrong direction and the right one.
# ---------------------------------------------------------------------------


def figure_wrongway(rt: dict) -> dict[str, float]:
    """Extract local vol from noisy implied data vs calibrate it forward."""

    truth = rt["truth"]
    t_star = 0.30
    t_bump = 0.02
    k_quotes = np.log(np.linspace(0.80, 1.30, 13))  # a realistic sparse strip
    k_grid = np.linspace(k_quotes[0], k_quotes[-1], 61)
    x_eval = np.exp(k_grid)

    def noisy_quote_w(expiry: float) -> np.ndarray:
        """Total variance at the quoted strikes, with a 30 bp deterministic
        ripple whose phase moves with expiry (real ticks do not cancel in T)."""
        sol = solve_affine_dupire(truth, DENSE_X, DENSE_T, np.array([expiry]))
        px = sol.price_at(0, np.exp(k_quotes))
        iv = np.sqrt(implied_total_variance(k_quotes, px) / expiry)
        iv_noisy = iv + 5e-3 * np.sin(77.0 * k_quotes + 40.0 * expiry)
        return iv_noisy * iv_noisy * expiry

    # What a naive extraction actually does: interpolate the sparse noisy
    # quotes to a dense grid, then finite-difference the interpolant.
    w_mid = np.interp(k_grid, k_quotes, noisy_quote_w(t_star))
    w_lo = np.interp(k_grid, k_quotes, noisy_quote_w(t_star - t_bump))
    w_hi = np.interp(k_grid, k_quotes, noisy_quote_w(t_star + t_bump))

    dk = k_grid[1] - k_grid[0]
    wk = np.gradient(w_mid, dk)
    wkk = np.gradient(wk, dk)
    wt = (w_hi - w_lo) / (2.0 * t_bump)
    extracted = dupire_local_variance(k_grid, w_mid, wk, wkk, wt)
    extracted_vol = 100.0 * np.sqrt(np.where(extracted > 0, extracted, np.nan))
    n_bad = int(np.sum(~np.isfinite(extracted_vol)))

    # The same noisy quotes, calibrated FORWARD through the production PDE.
    from volfit.core.black import black_call

    options = []
    for expiry in EXPIRIES:
        w_noisy = noisy_quote_w(float(expiry))
        px = black_call(k_quotes, w_noisy)
        for x, p in zip(np.exp(k_quotes), px):
            options.append(OptionQuote(t=float(expiry), x=float(x), price=float(p)))
    seed = AffineVarianceSurface(
        np.array([0.1, 0.25, 0.5, 1.0]),
        np.array([0.5, 0.7, 0.85, 1.0, 1.15, 1.3, 1.6]),
        np.full((4, 7), 0.04),
    )
    cal = calibrate_affine(seed, options, DENSE_X, DENSE_T)
    forward_vol = 100.0 * np.sqrt(cal.surface.variance(x_eval, t_star))
    truth_vol = 100.0 * np.sqrt(truth.variance(x_eval, t_star))

    fig, (ax_bad, ax_good) = plt.subplots(1, 2, figsize=WIDE, sharey=True)

    ax_bad.plot(x_eval, truth_vol, color=PALETTE["ink"], lw=2.0, label="true local vol")
    ax_bad.plot(
        x_eval, extracted_vol, color=PALETTE["rust"], lw=1.3,
        label="extracted from noisy quotes",
    )
    bad_mask = ~np.isfinite(extracted_vol)
    if bad_mask.any():
        for xb in x_eval[bad_mask]:
            ax_bad.axvline(xb, color=PALETTE["rust"], lw=2.2, alpha=0.12)
    ax_bad.set_xlabel(r"normalized strike $x=K/F$")
    ax_bad.set_ylabel("local volatility (%)")
    ax_bad.set_ylim(0.0, 78.0)
    ax_bad.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_bad, "A")

    ax_good.plot(x_eval, truth_vol, color=PALETTE["ink"], lw=2.0, label="true local vol")
    ax_good.plot(
        x_eval, forward_vol, color=PALETTE["teal"], lw=1.6,
        label="calibrated forward, same quotes",
    )
    ax_good.set_xlabel(r"normalized strike $x=K/F$")
    ax_good.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_good, "B")

    for ax in (ax_bad, ax_good):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.subplots_adjust(wspace=0.14)
    save(fig, OUT / "fig_lvf_wrongway.pdf")
    return {
        "wrongnoise": 50.0,
        "wrongnbad": float(n_bad),
        "wrongmaxspike": float(np.nanmax(extracted_vol)),
        "wrongfwdmax": float(np.max(np.abs(forward_vol - truth_vol))),
    }


# ---------------------------------------------------------------------------
# Figure 2: the triangulated sheet (the app's object).
# ---------------------------------------------------------------------------


def figure_tri(rt: dict) -> dict[str, float]:
    """The triangulated sheet the app renders: the product-path SPY fit.

    Falls back to the synthetic recovered surface if the Bloomberg fixture is
    unavailable, so the suite always regenerates.
    """

    source = "SPY (Bloomberg fixture, product path)"
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
        from lv_benchmark import build_state
        from volfit.api.affine_fit import calibrate_affine_surface
        from volfit.api.schemas_affine import AffineFitRequest

        resp = calibrate_affine_surface(build_state(), "SPY", AffineFitRequest())
        t_nodes = np.array(resp.tNodes)
        x_nodes = np.array(resp.xNodes)
        vol = 100.0 * np.array(resp.localVol)
    except Exception as exc:  # pragma: no cover
        print("!! product-path fit unavailable, falling back to synthetic:", exc)
        source = "synthetic recovered surface"
        surf = rt["cal"].surface
        t_nodes, x_nodes = surf.t_nodes, surf.x_nodes
        vol = 100.0 * np.sqrt(np.maximum(surf.theta, 1e-10))

    from scipy.spatial import Delaunay

    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    simplices = Delaunay(np.column_stack([tt.ravel(), xx.ravel()])).simplices
    tri = mtri.Triangulation(xx.ravel(), tt.ravel(), triangles=simplices)

    fig = plt.figure(figsize=(7.3, 4.8))
    ax = fig.add_subplot(111, projection="3d")
    collection = ax.plot_trisurf(
        tri, vol.ravel(), cmap="viridis", edgecolor="white",
        linewidth=0.4, antialiased=True, alpha=0.97,
    )
    ax.scatter(
        xx.ravel(), tt.ravel(), vol.ravel(), color=PALETTE["ink"],
        s=3, depthshade=False, alpha=0.75,
    )
    ax.set_xlabel(r"normalized strike $x=K/F$", labelpad=8)
    ax.set_ylabel(r"variance time $\tau$", labelpad=8)
    ax.set_zlabel("local vol (%)", labelpad=4)
    ax.view_init(elev=24, azim=-124)
    ax.set_box_aspect((1.45, 1.0, 0.52))
    ax.xaxis.pane.set_alpha(0.0)
    ax.yaxis.pane.set_alpha(0.0)
    ax.zaxis.pane.set_alpha(0.0)
    ax.tick_params(labelsize=8, pad=1)
    colorbar = fig.colorbar(
        collection, ax=ax, fraction=0.033, pad=0.01, shrink=0.72
    )
    colorbar.set_label("local vol (%)", fontsize=9)
    fig.subplots_adjust(left=0.0, right=1.0, top=1.05, bottom=0.0)
    save(fig, OUT / "fig_lvf_tri.pdf")
    print("  hero surface source:", source)
    return {"trivtx": float(vol.size)}


# ---------------------------------------------------------------------------
# Figure 3: P1 anatomy — triangulation, hats, partition of unity.
# ---------------------------------------------------------------------------


def figure_basis(rt: dict) -> None:
    surf = rt["cal"].surface
    tri = surf._delaunay()
    tt, xx = np.meshgrid(surf.t_nodes, surf.x_nodes, indexing="ij")
    pts_t, pts_x = tt.ravel(), xx.ravel()

    n_x = surf.x_nodes.size
    star_vertex = 1 * n_x + 3  # row t=0.25, strike x=1.0: an interior vertex

    fig, (ax_grid, ax_hats) = plt.subplots(1, 2, figsize=WIDE)

    ax_grid.triplot(
        pts_x, pts_t, tri.simplices, color=PALETTE["muted"], lw=0.7, alpha=0.85
    )
    star = [s for s in tri.simplices if star_vertex in s]
    for simplex in star:
        ax_grid.fill(
            pts_x[simplex], pts_t[simplex], color=PALETTE["teal"], alpha=0.22
        )
    ax_grid.plot(pts_x, pts_t, "o", ms=3.4, color=PALETTE["ink"])
    ax_grid.plot(
        [pts_x[star_vertex]], [pts_t[star_vertex]], "o", ms=6.5,
        color=PALETTE["rust"], zorder=5,
    )
    ax_grid.set_ylim(0.02, 1.40)
    ax_grid.annotate(
        "one vertex $=$ one parameter $\\theta_\\ell$\nshaded: its support",
        xy=(pts_x[star_vertex] + 0.03, pts_t[star_vertex] + 0.03),
        xytext=(0.50, 1.10), fontsize=8.5, color=PALETTE["ink"],
        arrowprops=dict(arrowstyle="-", lw=0.7, color=PALETTE["muted"],
                        connectionstyle="arc3,rad=0.15"),
    )
    ax_grid.set_xlabel(r"normalized strike $x$")
    ax_grid.set_ylabel(r"variance time $\tau$")
    label_panel(ax_grid, "A")

    x_dense = np.linspace(surf.x_nodes[0], surf.x_nodes[-1], 500)
    t_fix = 0.25
    basis = surf.basis(x_dense, t_fix)
    shown = 0
    for column in range(basis.shape[1]):
        if np.max(basis[:, column]) > 1e-9:
            color = EXPIRY_COLORS[shown % len(EXPIRY_COLORS)]
            ax_hats.plot(x_dense, basis[:, column], color=color, lw=1.2)
            shown += 1
    ax_hats.plot(
        x_dense, basis.sum(axis=1), color=PALETTE["ink"], lw=1.8,
        label="sum of all hats $=1$",
    )
    ax_hats.set_ylim(-0.06, 1.24)
    ax_hats.set_xlabel(r"normalized strike $x$ (at $\tau=0.25$)")
    ax_hats.set_ylabel(r"basis value $\phi_\ell$")
    ax_hats.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_hats, "B")

    for ax in (ax_grid, ax_hats):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.6)

    fig.subplots_adjust(wspace=0.26)
    save(fig, OUT / "fig_lvf_basis.pdf")


# ---------------------------------------------------------------------------
# Figure 4: monotone implicit Euler vs oscillating Crank--Nicolson.
# ---------------------------------------------------------------------------


def figure_monotone() -> dict[str, float]:
    """The same march, implicit vs Crank--Nicolson reaching the kink undamped.

    Both runs use the production solver.  The CN run is given a deliberately
    vanishing implicit start-up step (t = 1e-4), so the payoff kink reaches
    the CN steps essentially undamped --- the regime Rannacher start-up
    exists to prevent, and the cleanest demonstration of why monotonicity is
    a property of the scheme, not of luck.
    """

    flat = AffineVarianceSurface(
        np.array([0.0, 1.0]), np.array([0.2, 2.4]), np.full((2, 2), 0.16)
    )
    x_grid = np.arange(0.0, 2.5 + 1e-9, 0.025)
    t_grid = np.array([0.0, 1e-4, 0.033, 0.066, 0.1])
    expiries = np.array([0.1])

    sol_impl = solve_affine_dupire(flat, x_grid, t_grid, expiries)
    sol_cn = solve_affine_dupire(
        flat, x_grid, t_grid, expiries,
        time_scheme="rannacher", rannacher_steps=1,
    )

    def second_diff(sol) -> tuple[np.ndarray, np.ndarray]:
        u = sol.prices[0]
        x = sol.x_grid
        d2 = (u[2:] - 2.0 * u[1:-1] + u[:-2]) / (x[1] - x[0]) ** 2
        return x[1:-1], d2

    x_i, d2_impl = second_diff(sol_impl)
    x_c, d2_cn = second_diff(sol_cn)
    keep = (x_i > 0.5) & (x_i < 1.5)
    cn_min = float(np.min(d2_cn[keep]))
    x_at_min = float(x_c[keep][np.argmin(d2_cn[keep])])

    fig, ax = plt.subplots(figsize=(6.9, 3.5))
    ax.plot(
        x_i[keep], d2_impl[keep], color=PALETTE["teal"], lw=1.8,
        label="implicit Euler",
    )
    ax.plot(
        x_c[keep], d2_cn[keep], color=PALETTE["rust"], lw=1.3,
        label="Crank--Nicolson, kink undamped",
    )
    ax.fill_between(
        x_c[keep], 0.0, np.minimum(d2_cn[keep], 0.0),
        color=PALETTE["rust"], alpha=0.16,
    )
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.8)
    ax.annotate(
        "negative density: butterflies\nthe scheme invented",
        xy=(x_at_min, cn_min),
        xytext=(0.56, 0.62 * cn_min), fontsize=8.5, color=PALETTE["rust"],
        arrowprops=dict(arrowstyle="-", lw=0.7, color=PALETTE["rust"]),
    )
    ax.set_xlabel(r"normalized strike $x$")
    ax.set_ylabel("call second difference")
    ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)
    save(fig, OUT / "fig_lvf_monotone.pdf")
    return {
        "cnmind2": cn_min,
        "implmind2": float(np.min(d2_impl[keep])),
    }


# ---------------------------------------------------------------------------
# Figure 5: one vertex's influence, and the tangent audit.
# ---------------------------------------------------------------------------


def figure_influence(rt: dict) -> dict[str, float]:
    surf = rt["cal"].surface
    n_x = surf.x_nodes.size
    vertex = 1 * n_x + 3  # row tau=0.25, strike 1.0
    sol = solve_affine_dupire(surf, DENSE_X, DENSE_T, EXPIRIES, sensitivities=True)

    x_show = np.linspace(0.55, 1.6, 300)

    fig, (ax_cone, ax_audit) = plt.subplots(1, 2, figsize=WIDE)

    for ie, (expiry, color) in enumerate(zip(EXPIRIES, EXPIRY_COLORS)):
        sens = sol.sens_at(ie, x_show)[:, vertex]
        ax_cone.plot(
            x_show, 1e4 * sens, color=color, lw=1.5,
            label=rf"$\tau={expiry:.2f}$",
        )
    ax_cone.axvline(
        float(surf.x_nodes[3]), color=PALETTE["muted"], lw=0.8, ls=":"
    )
    ax_cone.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax_cone.set_xlabel(r"normalized strike $x$")
    ax_cone.set_ylabel(r"$10^4\,\partial c/\partial\theta_\ell$")
    ax_cone.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_cone, "A")

    theta0 = surf.theta.ravel().copy()
    step = 1e-6
    quotes_x = QUOTE_STRIKES
    analytic = np.stack(
        [sol.sens_at(ie, quotes_x) for ie in range(EXPIRIES.size)]
    )  # (n_exp, n_quote, m)
    rel_err = np.empty(theta0.size)
    for ell in range(theta0.size):
        up, dn = theta0.copy(), theta0.copy()
        up[ell] += step
        dn[ell] -= step
        sol_up = solve_affine_dupire(
            surf.with_theta(up), DENSE_X, DENSE_T, EXPIRIES
        )
        sol_dn = solve_affine_dupire(
            surf.with_theta(dn), DENSE_X, DENSE_T, EXPIRIES
        )
        fd = np.stack([
            (sol_up.price_at(ie, quotes_x) - sol_dn.price_at(ie, quotes_x))
            / (2.0 * step)
            for ie in range(EXPIRIES.size)
        ])
        an = analytic[:, :, ell]
        denom = max(float(np.linalg.norm(fd)), 1e-12)
        rel_err[ell] = float(np.linalg.norm(an - fd)) / denom

    ax_audit.bar(
        np.arange(theta0.size), np.maximum(rel_err, 1e-13),
        color=PALETTE["teal"], width=0.7,
    )
    ax_audit.set_yscale("log")
    ax_audit.set_xlabel(r"vertex index $\ell$ (time-major)")
    ax_audit.set_ylabel("tangent vs central-FD relative error")
    label_panel(ax_audit, "B")

    for ax in (ax_cone, ax_audit):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_lvf_influence.pdf")
    return {"tangentmaxrel": float(np.max(rel_err))}


# ---------------------------------------------------------------------------
# Figure 6: the round trip, and its two separate error numbers.
# ---------------------------------------------------------------------------


def figure_recovery(rt: dict) -> None:
    fig, (ax_fit, ax_err) = plt.subplots(
        1, 2, figsize=WIDE, gridspec_kw={"width_ratios": [1.0, 1.12]}
    )

    for (expiry, color) in zip(EXPIRIES, EXPIRY_COLORS):
        ax_fit.plot(
            np.log(QUOTE_STRIKES), 100 * rt["target"][float(expiry)],
            color=color, lw=1.9, label=rf"$\tau={expiry:.2f}$",
        )
        ax_fit.plot(
            np.log(QUOTE_STRIKES), 100 * rt["recovered"][float(expiry)],
            color=color, ls="--", lw=1.2,
        )
    ax_fit.set_xlabel(r"log-moneyness $k$")
    ax_fit.set_ylabel("implied volatility (%)")
    ax_fit.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_fit, "A")

    tt, xx, dvol = rt["surf_err_grid"]
    mesh = ax_err.pcolormesh(
        xx, tt, np.abs(dvol), cmap="magma_r", shading="auto",
        vmin=0.0,
    )
    for expiry in EXPIRIES:
        ax_err.plot(
            QUOTE_STRIKES, np.full(QUOTE_STRIKES.size, expiry), ls="none",
            marker="o", ms=2.4, color=PALETTE["teal"],
        )
    ax_err.set_xlabel(r"normalized strike $x$")
    ax_err.set_ylabel(r"variance time $\tau$")
    colorbar = fig.colorbar(mesh, ax=ax_err, fraction=0.046, pad=0.03)
    colorbar.set_label("|local-vol error| (vol pts)", fontsize=8.5)
    label_panel(ax_err, "B")

    ax_fit.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)
    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_lvf_recovery.pdf")


# ---------------------------------------------------------------------------
# Figure 7: identifiability — two surfaces, one set of quotes.
# ---------------------------------------------------------------------------


def figure_identify(rt: dict) -> dict[str, float]:
    surf = rt["cal"].surface
    theta_alt = surf.theta.copy()
    # Halve the local VOL of the unquoted deep-put column (x = 0.5, well below
    # the lowest 0.80 strike); the fitted column sits near the box cap, so the
    # equally admissible move is down.
    theta_alt[:, 0] = np.maximum(theta_alt[:, 0] / 4.0, 0.006)
    alt = surf.with_theta(theta_alt.ravel())

    def quote_rms_bp(surface: AffineVarianceSurface) -> float:
        sol = solve_affine_dupire(surface, DENSE_X, DENSE_T, EXPIRIES)
        errs = []
        for ie, expiry in enumerate(EXPIRIES):
            px = sol.price_at(ie, QUOTE_STRIKES)
            iv = np.sqrt(implied_total_variance(np.log(QUOTE_STRIKES), px) / expiry)
            errs.append(1e4 * (iv - rt["target"][float(expiry)]))
        return float(np.sqrt(np.mean(np.concatenate(errs) ** 2)))

    rms_base = quote_rms_bp(surf)
    rms_alt = quote_rms_bp(alt)

    x_slice = np.linspace(0.45, 1.7, 400)
    t_slice = 0.6
    vol_base = 100.0 * np.sqrt(surf.variance(x_slice, t_slice))
    vol_alt = 100.0 * np.sqrt(alt.variance(x_slice, t_slice))
    max_vol_move = float(np.max(np.abs(vol_alt - vol_base)))

    fig, (ax_surf, ax_res) = plt.subplots(1, 2, figsize=WIDE)

    ax_surf.axvspan(
        QUOTE_STRIKES[0], QUOTE_STRIKES[-1], color=PALETTE["teal"], alpha=0.08
    )
    ax_surf.plot(x_slice, vol_base, color=PALETTE["teal"], lw=1.7,
                 label="calibrated surface")
    ax_surf.plot(x_slice, vol_alt, color=PALETTE["rust"], lw=1.5, ls="--",
                 label="wings pushed hard")
    ax_surf.annotate(
        "quoted region", xy=(1.05, float(np.min(vol_base)) + 0.6),
        fontsize=8.5, color=PALETTE["muted"], ha="center",
    )
    ax_surf.set_xlabel(r"normalized strike $x$ (slice at $\tau=0.6$)")
    ax_surf.set_ylabel("local volatility (%)")
    ax_surf.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_surf, "A")

    sol_alt = solve_affine_dupire(alt, DENSE_X, DENSE_T, EXPIRIES)
    for ie, (expiry, color) in enumerate(zip(EXPIRIES, EXPIRY_COLORS)):
        px = sol_alt.price_at(ie, QUOTE_STRIKES)
        iv = np.sqrt(implied_total_variance(np.log(QUOTE_STRIKES), px) / expiry)
        ax_res.plot(
            np.log(QUOTE_STRIKES),
            1e4 * (iv - rt["target"][float(expiry)]),
            color=color, lw=1.2, marker="o", ms=3.0,
            label=rf"$\tau={expiry:.2f}$",
        )
    ax_res.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax_res.set_xlabel(r"log-moneyness $k$")
    ax_res.set_ylabel("reprice error of the pushed surface (vol bp)")
    ax_res.legend(frameon=False, fontsize=8, loc="lower right", ncol=2)
    label_panel(ax_res, "B")

    for ax in (ax_surf, ax_res):
        ax.grid(True, color=PALETTE["grid"], lw=0.5, alpha=0.7)

    fig.subplots_adjust(wspace=0.30)
    save(fig, OUT / "fig_lvf_identify.pdf")
    return {
        "identrmsbase": rms_base,
        "identrmsalt": rms_alt,
        "identvolmove": max_vol_move,
    }


# ---------------------------------------------------------------------------
# Figure 8: the short-dated coverage rescue (production grid builder).
# ---------------------------------------------------------------------------


def figure_rescue() -> dict[str, float]:
    from volfit.api.affine_fit import (
        _augment_per_expiry_coverage,
        _axis_scale,
        _delta_strike_nodes,
    )

    sigma = 0.20
    tau_wk, tau_6m = 6.0 / 365.0, 0.5
    k_wk = np.linspace(-2.5, 2.5, 21) * sigma * np.sqrt(tau_wk)
    k_6m = np.linspace(-0.35, 0.25, 25)
    rows = [
        ("wk", tau_wk, k_wk, np.full(k_wk.size, sigma**2 * tau_wk), None, None),
        ("6m", tau_6m, k_6m, np.full(k_6m.size, sigma**2 * tau_6m), None, None),
    ]
    sigma_star, t_star = _axis_scale(rows)
    base = _delta_strike_nodes(sigma_star, t_star, float(k_6m[0]), float(k_6m[-1]), 12)
    aug = _augment_per_expiry_coverage(base, rows, 8)
    added = np.setdiff1d(np.round(aug, 12), np.round(base, 12))

    def in_range(nodes: np.ndarray, k: np.ndarray) -> int:
        lk = np.log(nodes)
        return int(np.count_nonzero((lk >= k.min()) & (lk <= k.max())))

    before, after = in_range(base, k_wk), in_range(aug, k_wk)

    lanes = [("6-day weekly", k_wk, 1.0), ("6-month expiry", k_6m, 0.0)]
    fig, axes = plt.subplots(
        1, 2, figsize=WIDE, gridspec_kw={"width_ratios": [1.3, 1.0]}
    )
    xlims = [
        (float(k_6m[0]) - 0.02, float(k_6m[-1]) + 0.02),
        (float(k_wk.min()) * 1.8, float(k_wk.max()) * 1.8),
    ]
    for ax, xlim in zip(axes, xlims):
        for name, k, y in lanes:
            ax.fill_betweenx(
                [y - 0.16, y + 0.16], k.min(), k.max(),
                color=PALETTE["teal"], alpha=0.13,
            )
            ax.plot(
                np.log(base), np.full(base.size, y), "o", ms=5.5,
                color=PALETTE["muted"],
                label="delta axis" if y > 0 and ax is axes[0] else None,
            )
            if added.size:
                ax.plot(
                    np.log(added), np.full(added.size, y), "D", ms=5.5,
                    color=PALETTE["rust"],
                    label="added by the floor" if y > 0 and ax is axes[0] else None,
                )
            ax.text(
                xlim[0] + 0.01 * (xlim[1] - xlim[0]), y + 0.27, name,
                fontsize=9.5, color=PALETTE["ink"],
            )
        ax.axvline(0.0, color=PALETTE["ink"], lw=0.7, ls=":")
        ax.set_yticks([])
        ax.set_ylim(-0.55, 1.8)
        ax.set_xlim(*xlim)
        ax.set_xlabel(r"log-moneyness $k$")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper right")
    axes[1].text(
        xlims[1][1] * 0.92, 1.42,
        f"in the weekly's range: {before} $\\to$ {after}",
        ha="right", fontsize=9, color=PALETTE["ink"],
    )
    axes[1].text(
        xlims[1][1] * 0.92, 0.30,
        "already $\\geq 8$: untouched",
        ha="right", fontsize=8.5, color=PALETTE["muted"],
    )
    label_panel(axes[0], "A")
    label_panel(axes[1], "B")
    fig.subplots_adjust(wspace=0.16)
    save(fig, OUT / "fig_lvf_rescue.pdf")
    return {"rescuebefore": float(before), "rescueafter": float(after)}


# ---------------------------------------------------------------------------
# Figure 9: Bloomberg per-expiry RMS, from gen_lv.py's stored artifact.
# ---------------------------------------------------------------------------


def figure_rms() -> bool:
    numbers = json.loads((OUT / "lv_numbers.json").read_text(encoding="utf-8"))
    bench = numbers.get("benchmark")
    if not bench:
        print("lv_numbers.json has no benchmark block; skipping fig_lvf_rms")
        return False

    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.3), sharey=True)
    width = 0.38
    for ax, ticker, color, letter in zip(
        axes, ("SPY", "NVDA"), (PALETTE["teal"], PALETTE["rust"]), "AB"
    ):
        smiles = bench[ticker]["smiles"]
        labels = [e[5:] for e, _, _ in smiles]
        year = smiles[0][0][:4]
        in_op = [r for _, r, _ in smiles]
        conv = [r for _, _, r in smiles]
        xpos = np.arange(len(in_op))
        ax.bar(xpos - width / 2, in_op, width=width, color=color,
               label="in-operator")
        ax.bar(xpos + width / 2, conv, width=width, color=PALETTE["muted"],
               label="converged reprice")
        ax.set_xticks(xpos, labels, fontsize=7.5, rotation=45)
        ax.set_xlabel(f"{ticker} expiry ({year})")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(True, axis="y", color=PALETTE["grid"], lw=0.5, alpha=0.7)
        label_panel(ax, letter)
    axes[0].set_ylabel("per-expiry RMS (vol bp)")
    fig.subplots_adjust(wspace=0.08)
    save(fig, OUT / "fig_lvf_rms.pdf")
    return True


# ---------------------------------------------------------------------------
# Macro emission.
# ---------------------------------------------------------------------------


def tex_sci(value: float) -> str:
    if value == 0.0:
        return r"\ensuremath{0}"
    exponent = int(np.floor(np.log10(abs(value))))
    mantissa = value / 10.0**exponent
    return rf"\ensuremath{{{mantissa:.2f}\times10^{{{exponent}}}}}"


def write_tables(stats: dict[str, float], rt: dict) -> None:
    lines = [
        "% Auto-generated by Docs/notes/figures/gen_lv_forward.py -- do not edit.",
        f"\\newcommand{{\\lvfrtmaxerr}}{{{rt['max_err_bp']:.1f}}}",
        f"\\newcommand{{\\lvfrtsurfrms}}{{{rt['surf_rms']:.2f}}}",
        f"\\newcommand{{\\lvfrtsurfmax}}{{{rt['surf_max']:.2f}}}",
        f"\\newcommand{{\\lvfrtnevals}}{{{rt['n_evals']}}}",
        f"\\newcommand{{\\lvfrtvtx}}{{{rt['n_vertices']}}}",
        f"\\newcommand{{\\lvfwrongnbad}}{{{int(stats['wrongnbad'])}}}",
        f"\\newcommand{{\\lvfwrongmaxspike}}{{{stats['wrongmaxspike']:.0f}}}",
        f"\\newcommand{{\\lvfwrongfwdmax}}{{{stats['wrongfwdmax']:.1f}}}",
        f"\\newcommand{{\\lvfcnmind}}{{{stats['cnmind2']:.2f}}}",
        f"\\newcommand{{\\lvfimplmind}}{{{tex_sci(stats['implmind2'])}}}",
        f"\\newcommand{{\\lvftangentmaxrel}}{{{tex_sci(stats['tangentmaxrel'])}}}",
        f"\\newcommand{{\\lvfidentrmsbase}}{{{stats['identrmsbase']:.1f}}}",
        f"\\newcommand{{\\lvfidentrmsalt}}{{{stats['identrmsalt']:.1f}}}",
        f"\\newcommand{{\\lvfidentvolmove}}{{{stats['identvolmove']:.0f}}}",
        f"\\newcommand{{\\lvfrescuebefore}}{{{int(stats['rescuebefore'])}}}",
        f"\\newcommand{{\\lvfrescueafter}}{{{int(stats['rescueafter'])}}}",
        f"\\newcommand{{\\lvftrivtx}}{{{int(stats['trivtx'])}}}",
    ]
    (OUT / "lv_forward_tables.tex").write_text("\n".join(lines) + "\n")


def main() -> None:
    print("round trip (production calibrator) ...")
    rt = round_trip()
    stats: dict[str, float] = {}
    print("wrong-way figure ...")
    stats.update(figure_wrongway(rt))
    print("triangulated sheet ...")
    stats.update(figure_tri(rt))
    figure_basis(rt)
    print("monotone demo ...")
    stats.update(figure_monotone())
    print("influence + tangent audit ...")
    stats.update(figure_influence(rt))
    figure_recovery(rt)
    print("identifiability demo ...")
    stats.update(figure_identify(rt))
    stats.update(figure_rescue())
    figure_rms()
    write_tables(stats, rt)
    for key, value in sorted(stats.items()):
        print(f"{key:22s} {value:.6g}")
    print(f"rt: max_err {rt['max_err_bp']:.1f} bp, surf rms/max "
          f"{rt['surf_rms']:.2f}/{rt['surf_max']:.2f} vol pts, "
          f"{rt['n_evals']} evals")


if __name__ == "__main__":
    main()
