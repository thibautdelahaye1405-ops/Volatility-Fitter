"""Figures F4-F7: the real-market examples from the frozen snapshot.

F4 fig_spy_gallery -- eight SPY small multiples: haircut whiskers + fit.
F5 fig_spy_node    -- the SPY 2026-12-18 deep dive: band fit, residual
                      ledger, density vs an ATM-matched normal.
F6 fig_nvda_nodes  -- the NVDA 1-day node (order guard live) + the
                      longest NVDA node: fits and residual ledgers.
F7 fig_lqd_chart   -- a real node in the model's own chart: log quantile
                      density vs the universal skeleton, g(u) shaded.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import logit
from scipy.stats import norm

import data
from figstyle import GALLERY, GRID22, PALETTE, ROW2, ROW3, panel, rms_note, save, whiskers
from macros import STORE, num


def _fit_grid(node: data.Node, pad: float = 0.08) -> np.ndarray:
    """Dense k grid spanning the quoted strikes with a small margin."""
    lo, hi = float(node.k.min()), float(node.k.max())
    margin = pad * (hi - lo)
    return np.linspace(lo - margin, hi + margin, 301)


def _density_window(node: data.Node) -> tuple[np.ndarray, np.ndarray]:
    """Density restricted to the central 99.6% of the distribution."""
    x, f = node.slice.density()
    lo = float(np.interp(logit(0.002), node.slice.z, node.slice.q_z))
    hi = float(np.interp(logit(0.998), node.slice.z, node.slice.q_z))
    sel = (x >= lo) & (x <= hi)
    return x[sel], f[sel]


def _draw_quotes(ax, node: data.Node, band: bool) -> None:
    """Quote mids as dots; whiskers = haircut band (live) or raw bid-ask.

    On SPY every haircut band degenerates to the mid (spreads sit far
    inside 2h), so the honest picture there is the raw bid-ask whisker;
    on NVDA the haircut band is alive and is what the calibrator saw.
    """
    lo = node.band_lo if band else node.iv_bid
    hi = node.band_hi if band else node.iv_ask
    label = "haircut band" if band else "bid-ask spread"
    whiskers(ax, node.k, 100.0 * lo, 100.0 * hi, label=label)
    ax.scatter(node.k, 100.0 * node.iv_mid, s=3.5, color=PALETTE["data"],
               zorder=4, label="quote mid", linewidths=0.0)


def _residual_ledger(ax, node: data.Node, band: bool) -> None:
    """Model-minus-mid residuals in vol bp against the quote envelope."""
    res = node.residual_bp
    lo = node.band_lo if band else node.iv_bid
    hi = node.band_hi if band else node.iv_ask
    ax.fill_between(node.k, 1e4 * (lo - node.iv_mid), 1e4 * (hi - node.iv_mid),
                    color=PALETTE["data"], alpha=0.25, lw=0.0,
                    label="haircut band" if band else "bid-ask spread")
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.vlines(node.k, 0.0, res, color=PALETTE["model"], lw=0.8)
    ax.scatter(node.k, res, s=6, color=PALETTE["model"], zorder=4,
               label="fit $-$ mid")
    # The residual detail is the point: keep deep-wing envelopes from
    # dictating the scale (the fill is clipped, not hidden).
    cap = 1.35 * float(np.max(np.abs(res)))
    ax.set_ylim(-cap, cap)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("residual (vol bp)")


def _node_macros(section: str, prefix: str, node: data.Node) -> None:
    """Per-node stats every caption quotes for a featured node."""
    a_l, a_r, b_l, b_r = node.tails()
    live = (node.band_hi - node.band_lo) > 1e-9
    STORE.add(section, f"{prefix}MedianSpreadBp",
              num(1e4 * float(np.median(node.iv_ask - node.iv_bid)), 0),
              "median quoted bid-ask spread, vol bp")
    STORE.add(section, f"{prefix}BandLivePct",
              num(100.0 * float(live.mean()), 0),
              "share of quotes whose haircut band does NOT degenerate to"
              " mid, %")
    STORE.add(section, f"{prefix}Expiry", node.expiry, "expiry date")
    STORE.add(section, f"{prefix}Days", str(node.days), "calendar days to expiry")
    STORE.add(section, f"{prefix}TYears", num(node.t, 4), "year fraction t")
    STORE.add(section, f"{prefix}Forward", num(node.forward, 2), "forward F")
    STORE.add(section, f"{prefix}NQuotes", str(node.n_quotes),
              "calibration quotes retained")
    STORE.add(section, f"{prefix}Order", str(node.order),
              "effective Legendre order N after the quote-count guard")
    STORE.add(section, f"{prefix}RmsBp", num(node.rms_bp, 1),
              "rms fit error vs mid, vol bp (frozen quality stat)")
    STORE.add(section, f"{prefix}AtmVolPct",
              num(100.0 * float(node.model_iv(0.0)), 2), "ATM implied vol, %")
    STORE.add(section, f"{prefix}Al", num(a_l, 3),
              "left endpoint scale lambda_-")
    STORE.add(section, f"{prefix}Ar", num(a_r, 3),
              "right endpoint scale lambda_+")
    STORE.add(section, f"{prefix}BetaLeft", num(b_l, 3),
              "left Lee wing slope beta_-")
    STORE.add(section, f"{prefix}BetaRight", num(b_r, 3),
              "right Lee wing slope beta_+")
    STORE.add(section, f"{prefix}VarSwapPct", num(100.0 * node.var_swap_vol, 2),
              "var-swap vol from the ledger first moment, %")


def fig_spy_gallery() -> str:
    """F4: eight SPY expiries, haircut whiskers plus the fitted slice."""
    spy = data.nodes("SPY")
    fig, axes = plt.subplots(2, 4, figsize=GALLERY)
    for ax, node in zip(axes.flat, spy):
        grid = _fit_grid(node)
        _draw_quotes(ax, node, band=False)  # SPY haircut bands all degenerate
        ax.plot(grid, 100.0 * node.model_iv(grid), color=PALETTE["model"],
                lw=1.1, zorder=5)
        rms_note(ax, node.rms_bp)
        ax.set_title(f"{node.expiry}  ({node.days}d)", fontsize=8.0, pad=3.0)
        ax.tick_params(labelsize=7.0)
        ax.margins(x=0.02)
    for ax in axes[1]:
        ax.set_xlabel(r"log-moneyness $k$", fontsize=8.0)
    for ax in axes[:, 0]:
        ax.set_ylabel("implied vol (%)", fontsize=8.0)
    save(fig, "fig_spy_gallery")
    rms = [n.rms_bp for n in spy]
    STORE.add("spy", "SpyGalleryMedianRmsBp", num(np.median(rms), 1),
              "median rms across the eight SPY expiries, vol bp")
    STORE.add("spy", "SpyGalleryWorstRmsBp", num(max(rms), 1),
              "worst rms across the eight SPY expiries, vol bp")
    return f"SPY gallery: rms median {np.median(rms):.1f} / worst {max(rms):.1f} bp"


def fig_spy_node() -> str:
    """F5: the SPY 2026-12-18 deep dive."""
    node = data.node(*data.SPY_DEC)
    grid = _fit_grid(node)

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    _draw_quotes(axes[0], node, band=False)
    axes[0].plot(grid, 100.0 * node.model_iv(grid), color=PALETTE["model"],
                 lw=1.2, label="LQD fit", zorder=5)
    axes[0].set_xlabel(r"log-moneyness $k$")
    axes[0].set_ylabel("implied volatility (%)")
    axes[0].legend(loc="upper right", fontsize=7.0)
    panel(axes[0], "a", f"SPY {node.expiry}, {node.n_quotes} quotes")

    _residual_ledger(axes[1], node, band=False)
    axes[1].legend(loc="upper right", fontsize=7.0)
    panel(axes[1], "b", f"residual ledger, rms {node.rms_bp:.1f} bp")

    x, f = _density_window(node)
    atm_w = float(node.model_iv(0.0)) ** 2 * node.t
    axes[2].plot(x, f, color=PALETTE["model"], label="LQD density")
    axes[2].plot(x, norm.pdf(x, -0.5 * atm_w, np.sqrt(atm_w)),
                 color=PALETTE["muted"], ls="--", label="ATM-matched normal")
    axes[2].fill_between(x, 0.0, f, color=PALETTE["model"], alpha=0.08, lw=0.0)
    axes[2].set_xlabel(r"log return $x$")
    axes[2].set_ylabel(r"density $f_X$")
    axes[2].legend(loc="upper left", fontsize=7.0)
    panel(axes[2], "c", "the distribution behind the fit")

    save(fig, "fig_spy_node")
    _node_macros("spy", "SpyDec", node)
    recomputed = float(np.sqrt(np.mean(node.residual_bp**2)))
    STORE.add("spy", "SpyDecRecomputedRmsBp", num(recomputed, 1),
              "rms vs mid recomputed from the rebuilt slice, vol bp")
    return f"SPY Dec node: rms {node.rms_bp:.1f} bp (recomputed {recomputed:.1f})"


def fig_nvda_nodes() -> str:
    """F6: the 1-day NVDA node (order guard) and the longest NVDA node."""
    short = data.node(*data.NVDA_SHORT)
    long_ = data.node(*data.NVDA_LONG)

    fig, axes = plt.subplots(2, 2, figsize=GRID22)
    for col, node, tag_fit, tag_res in ((0, short, "a", "c"),
                                        (1, long_, "b", "d")):
        ax = axes[0, col]
        grid = _fit_grid(node)
        _draw_quotes(ax, node, band=True)  # NVDA haircut bands are live
        ax.plot(grid, 100.0 * node.model_iv(grid), color=PALETTE["model"],
                lw=1.2, label="LQD fit", zorder=5)
        ax.set_xlabel(r"log-moneyness $k$")
        ax.set_ylabel("implied volatility (%)")
        ax.legend(loc="upper right", fontsize=7.0)
        panel(ax, tag_fit,
              f"NVDA {node.expiry} ({node.days}d), $N={node.order}$")
        _residual_ledger(axes[1, col], node, band=True)
        panel(axes[1, col], tag_res, f"rms {node.rms_bp:.1f} bp")
    axes[1, 0].legend(loc="upper right", fontsize=7.0)

    save(fig, "fig_nvda_nodes")
    _node_macros("nvda", "NvdaOneDay", short)
    _node_macros("nvda", "NvdaLong", long_)
    STORE.add("nvda", "NvdaOneDayParams", str(short.order + 1),
              "parameter count P = N + 1 on the guarded 1-day node")
    return (f"NVDA nodes: 1d N={short.order} ({short.n_quotes} quotes, "
            f"rms {short.rms_bp:.1f} bp), long N={long_.order} "
            f"(rms {long_.rms_bp:.1f} bp)")


def fig_lqd_chart() -> str:
    """F7: SPY 2026-12-18 in the model's own chart."""
    from volfit.models.lqd.basis import g_eval

    node = data.node(*data.SPY_DEC)
    u = np.linspace(0.004, 0.996, 801)
    skeleton = -np.log(u) - np.log(1.0 - u)
    ell = skeleton + g_eval(node.params, u)

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    axes[0].plot(u, skeleton, color=PALETTE["ink"], ls="--", lw=1.0,
                 label=r"skeleton $-\log u - \log(1-u)$")
    axes[0].plot(u, ell, color=PALETTE["model"], lw=1.3,
                 label=r"$\log q(u)$ (fitted)")
    axes[0].fill_between(u, ell, skeleton, color=PALETTE["model"], alpha=0.12,
                         lw=0.0)
    mid = 0.62
    y_mid = 0.5 * (float(np.interp(mid, u, skeleton))
                   + float(np.interp(mid, u, ell)))
    axes[0].annotate(r"the gap is $g(u)$", (mid, y_mid), ha="center",
                     fontsize=8.0, color=PALETTE["model"])
    axes[0].set_xlabel(r"percentile rank $u$")
    axes[0].set_ylabel("log quantile density")
    axes[0].legend(loc="upper center", fontsize=7.0)
    panel(axes[0], "a", f"SPY {node.expiry} in the model's chart")

    x, f = _density_window(node)
    axes[1].plot(x, f, color=PALETTE["model"])
    axes[1].fill_between(x, 0.0, f, color=PALETTE["model"], alpha=0.08, lw=0.0)
    axes[1].set_xlabel(r"log return $x$")
    axes[1].set_ylabel(r"density $f_X$")
    panel(axes[1], "b", "the same object as a density")

    save(fig, "fig_lqd_chart")
    return "chart figure drawn on SPY 2026-12-18"
