"""F1: the local-variance field as a ratio of Chapter 2's ledger objects.

From the frozen snapshot's stored per-expiry SPY LQD fits, build the implied
total-variance surface (linear in tau between expiries), and evaluate the
Dupire ratio v = dw/dtau / g_D on a dense (k, tau) mesh.  The numerator is
the calendar increment, the denominator the Durrleman factor: the two static
validity families of Chapters 2-3 are exactly the sign conditions for the
field to exist.  Cells where either sign fails are masked -- they sit in
extrapolated territory, which is the chapter's point.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

import data4
import figstyle
from figstyle import PALETTE
from macros import STORE, num

K_LO, K_HI, N_K = -0.35, 0.20, 221
N_TAU = 160


def _surface_data():
    nodes = data4.nodes("SPY")
    k = np.linspace(K_LO, K_HI, N_K)
    slices = [data4.stored_slice(n) for n in nodes]
    w_exp = np.array([np.asarray(s.implied_w(k), dtype=float) for s in slices])
    t_exp = np.array([n.t for n in nodes])
    spans = [(n.k.min(), n.k.max()) for n in nodes]
    taus = np.geomspace(t_exp[0], t_exp[-1], N_TAU)
    w = np.empty((N_TAU, N_K))
    dtw = np.empty((N_TAU, N_K))
    common = np.zeros((N_TAU, N_K), dtype=bool)  # common quoted support
    for r, tau in enumerate(taus):
        i = min(np.searchsorted(t_exp, tau, side="right") - 1, t_exp.size - 2)
        i = max(i, 0)
        lam = (tau - t_exp[i]) / (t_exp[i + 1] - t_exp[i])
        w[r] = (1 - lam) * w_exp[i] + lam * w_exp[i + 1]
        dtw[r] = (w_exp[i + 1] - w_exp[i]) / (t_exp[i + 1] - t_exp[i])
        lo = max(spans[i][0], spans[i + 1][0])
        hi = min(spans[i][1], spans[i + 1][1])
        common[r] = (k >= lo) & (k <= hi)
    wp = np.gradient(w, k, axis=1)
    wpp = np.gradient(wp, k, axis=1)
    g_d = (1.0 - k * wp / (2.0 * w)) ** 2 \
        - 0.25 * wp**2 * (1.0 / w + 0.25) + 0.5 * wpp
    return nodes, k, taus, w, dtw, g_d, common, spans, t_exp


def _mask_overlay(ax, k, taus, bad):
    """Paint inadmissible cells in the mask grey on top of a heatmap."""
    over = np.ma.masked_where(~bad, np.ones_like(bad, dtype=float))
    ax.pcolormesh(k, taus, over, cmap=ListedColormap([PALETTE["mask"]]),
                  vmin=0.0, vmax=1.0, shading="auto", zorder=3)


def _quote_spans(ax, spans, t_exp, k):
    for (lo, hi), t in zip(spans, t_exp):
        ax.plot([max(lo, k.min()), min(hi, k.max())], [t, t],
                color=PALETTE["ink"], lw=0.8, solid_capstyle="butt", zorder=4)


def fig_lv_ratio() -> str:
    nodes, k, taus, w, dtw, g_d, common, spans, t_exp = _surface_data()
    bad_num = dtw < 0.0
    bad_den = g_d <= 0.0
    bad = bad_num | bad_den
    v = np.where(bad, np.nan, dtw / np.where(bad_den, 1.0, g_d))
    sig = 100.0 * np.sqrt(np.where(v > 0, v, np.nan))

    fig, axes = plt.subplots(1, 3, figsize=figstyle.ROW3, sharey=True)
    panels = [
        ("a", r"calendar increment  $\partial_\tau w$", dtw, bad_num),
        ("b", r"Durrleman factor  $g_{\rm D}$", g_d, bad_den),
        ("c", r"local volatility  $\sqrt{\partial_\tau w/g_{\rm D}}$  (%)",
         sig, bad),
    ]
    for ax, (tag, title, field, mask) in zip(axes, panels):
        data = np.ma.masked_invalid(np.where(mask, np.nan, field))
        # color range from the common quoted support: the extrapolated wings
        # of the shortest expiries reach absurd values and would otherwise
        # own the whole scale; out-of-range cells simply saturate.
        support = field[common & ~mask & np.isfinite(field)]
        pcm = ax.pcolormesh(k, taus, data, cmap=figstyle.HEATMAP,
                            vmin=max(0.0, float(support.min())),
                            vmax=float(support.max()),
                            shading="auto", rasterized=True)
        _mask_overlay(ax, k, taus, mask)
        _quote_spans(ax, spans, t_exp, k)
        ax.set_xlim(float(k.min()), float(k.max()))
        ax.set_yscale("log")
        ax.set_xlabel(r"log-moneyness $k$")
        ax.grid(False)
        figstyle.panel(ax, tag, title)
        fig.colorbar(pcm, ax=ax, pad=0.02, fraction=0.06, extend="max")
    axes[0].set_ylabel(r"$\tau$ (years, log)")

    bad_share = 100.0 * bad.sum() / bad.size
    bad_quoted = 100.0 * (bad & common).sum() / max(common.sum(), 1)
    sig_q = sig[common & ~bad]
    STORE.add("ratio", "LvRatioBadSharePct", num(bad_share, 1),
              "share of displayed (k, tau) cells where the Dupire ratio is "
              "inadmissible (negative calendar increment or g_D <= 0)")
    STORE.add("ratio", "LvRatioBadQuotedSharePct", num(bad_quoted, 2),
              "same share restricted to the common quoted support of each "
              "expiry pair")
    STORE.add("ratio", "LvRatioLocMinPct", num(float(sig_q.min()), 1),
              "smallest extracted local vol (%) on the common quoted support")
    STORE.add("ratio", "LvRatioLocMaxPct", num(float(sig_q.max()), 1),
              "largest extracted local vol (%) on the common quoted support")
    figstyle.save(fig, "fig_lv_ratio")
    return f"bad {bad_share:.1f}% (quoted {bad_quoted:.2f}%)"
