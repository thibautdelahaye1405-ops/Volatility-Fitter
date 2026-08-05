"""F3/F4: the P1 sheet itself, and its anatomy.

F3 draws the calibrated SPY local-volatility sheet with the triangulation
the pricing basis actually uses: every triangle a region where local
variance is affine, every vertex one calibration parameter.  F4 takes the
object apart on a small demonstration grid: the star support of one hat
function, and a strike cross-section showing the partition of unity.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import lvfits
from figstyle import PALETTE
from macros import STORE
from volfit.models.localvol.affine import AffineVarianceSurface


def fig_lv_sheet() -> str:
    fit = lvfits.fit_ticker("SPY")
    surf = fit.surface
    tt, yy = np.meshgrid(surf.t_nodes, surf.x_nodes, indexing="ij")
    sig = 100.0 * np.sqrt(surf.theta)
    tri = surf._delaunay()  # the cached pricing triangulation itself

    fig = plt.figure(figsize=(6.3, 3.6))
    ax = fig.add_subplot(projection="3d")
    st = np.sqrt(tt.ravel())  # sqrt-maturity axis so short rows stay readable
    ax.plot_trisurf(yy.ravel(), st, sig.ravel(), triangles=tri.simplices,
                    cmap=figstyle.HEATMAP, edgecolor=PALETTE["ink"],
                    linewidth=0.25, alpha=0.92, antialiased=True)
    ax.scatter(yy.ravel(), st, sig.ravel() + 0.4, color=PALETTE["ink"],
               s=2.5, depthshade=False)
    ax.set_xlabel(r"strike $y = K/F$", labelpad=2)
    ticks = [0.05, 0.25, 0.75, 1.37]
    ax.set_yticks([np.sqrt(t) for t in ticks])
    ax.set_yticklabels([f"{t:g}" for t in ticks])
    ax.set_ylabel(r"$\tau$ (years, $\sqrt{\cdot}$ axis)", labelpad=2)
    ax.set_zlabel("local vol (%)", labelpad=2)
    ax.view_init(elev=24, azim=-125)
    ax.tick_params(labelsize=7)
    ax.grid(False)

    n_t, n_y = surf.t_nodes.size, surf.x_nodes.size
    STORE.add("sheet", "LvSheetRows", str(n_t), "SPY sheet maturity rows")
    STORE.add("sheet", "LvSheetCols", str(n_y), "SPY sheet strike columns")
    STORE.add("sheet", "LvSheetVtx", str(n_t * n_y),
              "SPY sheet vertex count (= calibration parameters)")
    figstyle.save(fig, "fig_lv_sheet")
    return f"{n_t} x {n_y} vertices"


def fig_lv_basis() -> str:
    t_nodes = np.array([0.0, 0.25, 0.5, 1.0])
    y_nodes = np.array([0.60, 0.72, 0.84, 0.93, 1.00, 1.07, 1.18, 1.32, 1.50])
    surf = AffineVarianceSurface(t_nodes, y_nodes,
                                 np.full((t_nodes.size, y_nodes.size), 0.04))
    tri = surf._delaunay()
    pts = tri.points  # (t, y) pairs, t-major order matching theta.ravel()
    star_vertex = 2 * y_nodes.size + 4  # row tau = 0.5, column y = 1.0

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)
    ax = axes[0]
    for simplex in tri.simplices:
        poly = pts[simplex]
        in_star = star_vertex in simplex
        ax.fill(poly[:, 1], poly[:, 0],
                facecolor=PALETTE["model"] if in_star else "none",
                alpha=0.30 if in_star else 1.0,
                edgecolor=PALETTE["muted"], lw=0.7, zorder=2)
    ax.plot(pts[:, 1], pts[:, 0], ls="none", marker="o", markersize=3.0,
            color=PALETTE["ink"], zorder=3)
    ax.plot([pts[star_vertex, 1]], [pts[star_vertex, 0]], marker="o",
            markersize=5.0, color=PALETTE["model"], zorder=4)
    ax.set_xlabel(r"strike $y$")
    ax.set_ylabel(r"$\tau$ (years)")
    figstyle.panel(ax, "a", "the vertex grid and one hat's support")
    figstyle.callout(ax, "the star of triangles this\nparameter influences",
                     (1.0, 0.5), (1.17, 0.12))

    ax = axes[1]
    y_dense = np.linspace(0.55, 1.55, 401)
    basis = surf.basis(y_dense, 0.5)  # cross-section along the tau = 0.5 row
    row = slice(2 * y_nodes.size, 3 * y_nodes.size)
    hats = basis[:, row]
    for j in range(y_nodes.size):
        ax.plot(y_dense, hats[:, j], color=PALETTE["model"], lw=1.0,
                alpha=0.45 + 0.55 * (j == 4))
    ax.plot(y_dense, basis.sum(axis=1), color=PALETTE["ink"], lw=1.4,
            label="sum over all vertices = 1")
    ax.set_xlabel(r"strike $y$")
    ax.set_ylabel("basis weight")
    ax.set_ylim(-0.05, 1.12)
    ax.legend(loc="center right", fontsize=7.0)
    figstyle.panel(ax, "b", r"hat functions along the $\tau=0.5$ row")

    figstyle.save(fig, "fig_lv_basis")
    return "done"
