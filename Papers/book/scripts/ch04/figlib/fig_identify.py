"""F6/F7: what the quotes can and cannot see.

F6 (identifiability): two local-volatility surfaces -- the calibrated
synthetic fit, and the same surface with its unquoted deep-put column pushed
down by ten vol points -- reprice the same quote set within a few vol bp.
F7 (influence): the tangent system, seen and checked: the sensitivity of the
priced call curve to one interior vertex is a spreading cone, and every
analytic column agrees with a central finite difference of the full march.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import lvfits
from figstyle import PALETTE
from macros import STORE, num, sci
from volfit.models.localvol.affine import solve_affine_dupire
from volfit.core.black import implied_vol

PUSH_PTS = 10.0   # vol points taken off the deep-put column


def _reprice(surface, fit: lvfits.SynFit) -> list[np.ndarray]:
    sol = solve_affine_dupire(surface, fit.y_grid, fit.t_grid,
                              [s["t"] for s in fit.strips])
    out = []
    for i, s in enumerate(fit.strips):
        p = sol.price_at(i, s["y"])
        out.append(np.asarray(implied_vol(s["k"], p, s["t"]), dtype=float))
    return out


def fig_lv_identify() -> str:
    fit = lvfits.syn_fit(0.0)
    surf = fit.surface
    j_col = int(np.argmin(np.abs(surf.x_nodes - lvfits.SYN_DEEP_COL)))
    sig_col = np.sqrt(surf.theta[:, j_col])
    theta_pushed = surf.theta.copy()
    theta_pushed[:, j_col] = (sig_col - PUSH_PTS / 100.0) ** 2
    pushed = surf.with_theta(theta_pushed.ravel())

    iv_base = fit.iv_model
    iv_push = _reprice(pushed, fit)
    diffs_bp = [1e4 * np.abs(b - p) for b, p in zip(iv_base, iv_push)]
    max_diff = max(float(d.max()) for d in diffs_bp)
    rms_diff = float(np.sqrt(np.mean(np.concatenate(diffs_bp) ** 2)))

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)
    ax = axes[0]
    tau0 = 0.5
    y_plot = np.linspace(0.40, 1.55, 301)
    ax.plot(y_plot, 100 * np.sqrt(surf.variance(y_plot, tau0)),
            color=PALETTE["model"], lw=1.5, label="calibrated surface")
    ax.plot(y_plot, 100 * np.sqrt(pushed.variance(y_plot, tau0)),
            color=PALETTE["model"], lw=1.3, ls="--",
            label=f"deep-put column moved {PUSH_PTS:.0f} vol pts")
    s05 = next(s for s in fit.strips if abs(s["t"] - tau0) < 1e-9)
    ax.axvspan(float(s05["y"].min()), float(s05["y"].max()),
               color=PALETTE["grid"], alpha=0.55, zorder=0)
    ax.text(float(s05["y"].min()) + 0.02, 12.5, "quoted region",
            fontsize=7.0, color=PALETTE["muted"])
    ax.set_xlabel(r"strike $y$")
    ax.set_ylabel("local volatility (%)")
    ax.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax, "a", r"two surfaces at $\tau=0.5$")

    ax = axes[1]
    for s, d, alpha in zip(fit.strips, diffs_bp, (0.35, 0.55, 0.75, 1.0)):
        ax.plot(s["k"], d, ls="none", marker="o", markersize=3.6,
                color=PALETTE["data"], alpha=alpha,
                label=rf"$\tau={s['t']:.2f}$")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("reprice difference (vol bp)")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "b", "what the quote set notices")

    STORE.add("identify", "LvIdentMovePts", num(PUSH_PTS, 0),
              "vol points taken off the unquoted deep-put column")
    STORE.add("identify", "LvIdentColY", num(lvfits.SYN_DEEP_COL, 2),
              "strike of the moved vertex column")
    STORE.add("identify", "LvIdentMaxDiffBp", num(max_diff, 1),
              "largest reprice change (vol bp) across every quote")
    STORE.add("identify", "LvIdentRmsDiffBp", num(rms_diff, 1),
              "rms reprice change (vol bp) across every quote")
    figstyle.save(fig, "fig_lv_identify")
    return f"{PUSH_PTS:.0f} pts -> max {max_diff:.1f} bp"


def fig_lv_influence() -> str:
    fit = lvfits.syn_fit(0.0)
    surf = fit.surface
    n_y = surf.x_nodes.size
    i_row = int(np.argmin(np.abs(surf.t_nodes - 0.25)))
    j_col = int(np.argmin(np.abs(surf.x_nodes - 1.0)))
    ell = i_row * n_y + j_col
    expiries = [s["t"] for s in fit.strips]
    sol = solve_affine_dupire(surf, fit.y_grid, fit.t_grid, expiries,
                              sensitivities=True)

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)
    ax = axes[0]
    y_dense = np.linspace(0.55, 1.6, 301)
    for i, (t, alpha) in enumerate(zip(expiries, (0.35, 0.55, 0.75, 1.0))):
        col = sol.sens_at(i, y_dense)[:, ell]
        ax.plot(y_dense, 1e2 * col, color=PALETTE["model"], alpha=alpha,
                lw=1.3, label=rf"$\tau={t:.2f}$")
    ax.axvline(1.0, color=PALETTE["muted"], lw=0.8, ls=":")
    ax.set_xlabel(r"strike $y$")
    ax.set_ylabel(r"$10^2\,\partial c/\partial\theta_\ell$")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "a", r"influence of the vertex at $(\tau,y)=(0.25,1)$")

    # FD check of every column, at every expiry, over the whole grid; the
    # normalization is the Jacobian's global scale (a per-column scale would
    # divide near-zero columns by their own noise).
    h = 1e-5
    theta0 = surf.theta.ravel()
    scale = float(np.abs(sol.sens).max())
    rels = np.empty(theta0.size)
    for l in range(theta0.size):
        tp, tm = theta0.copy(), theta0.copy()
        tp[l] += h
        tm[l] -= h
        up = solve_affine_dupire(surf.with_theta(tp), fit.y_grid, fit.t_grid,
                                 expiries).prices
        um = solve_affine_dupire(surf.with_theta(tm), fit.y_grid, fit.t_grid,
                                 expiries).prices
        fd = (up - um) / (2 * h)
        ana = sol.sens[:, :, l]
        rels[l] = np.abs(fd - ana).max() / scale
    ax = axes[1]
    ax.semilogy(np.arange(theta0.size), rels, ls="none", marker="o",
                markersize=3.2, color=PALETTE["model"])
    ax.set_xlabel(r"vertex index $\ell$")
    ax.set_ylabel("relative FD disagreement")
    figstyle.panel(ax, "b", "every analytic column vs central differences")

    STORE.add("influence", "LvInflMaxRel", sci(float(rels.max()), 1),
              "worst relative disagreement, analytic tangent vs central FD, "
              "over all vertices and expiries")
    STORE.add("influence", "LvInflVtx", str(theta0.size),
              "vertex count of the synthetic sheet")
    figstyle.save(fig, "fig_lv_influence")
    return f"max rel {rels.max():.1e} over {theta0.size} columns"
