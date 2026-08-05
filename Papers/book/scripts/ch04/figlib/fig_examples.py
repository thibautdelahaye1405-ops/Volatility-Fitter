"""F8/F9/F10: the worked examples.

F8: the synthetic round trip and its two separately measured numbers --
quote error and surface error.  F9: four SPY expiries priced by ONE
calibrated sheet against the frozen quotes.  F10: per-expiry rms for SPY and
NVDA, the fitting operator beside the refined-operator reprice.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import lvfits
from figstyle import PALETTE
from macros import STORE, num, sci
from volfit.core.black import implied_vol
from volfit.models.localvol.affine import solve_affine_dupire


def _arb_diagnostics(fit: lvfits.SurfaceFit) -> tuple[float, float]:
    """Measured cleanliness of the marched prices: (min divided second
    difference over every expiry = butterfly proxy, min adjacent-expiry
    price increment = calendar proxy).  Both should be >= -(rounding)."""
    sol = solve_affine_dupire(fit.surface, fit.y_grid, fit.t_grid,
                              [n.t for n in fit.nodes])
    y = sol.x_grid
    hm, hp = np.diff(y)[:-1], np.diff(y)[1:]
    bfly = min(
        float(np.min((p[2:] - p[1:-1]) / hp - (p[1:-1] - p[:-2]) / hm))
        for p in sol.prices)
    cal = float(np.min(np.diff(sol.prices, axis=0)))
    return bfly, cal


def fig_lv_recovery() -> str:
    fit = lvfits.syn_fit(0.0)
    err_bp = np.abs(fit.quote_err_bp())
    surf_rms, surf_max = lvfits.syn_surface_error(fit)

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)
    ax = axes[0]
    for s, iv, alpha in zip(fit.strips, fit.iv_model, (0.35, 0.55, 0.75, 1.0)):
        ax.plot(s["k"], 100 * s["iv"], ls="none", marker="o", markersize=3.4,
                color=PALETTE["data"], alpha=alpha)
        ax.plot(s["k"], 100 * iv, color=PALETTE["model"], alpha=alpha, lw=1.3,
                label=rf"$\tau={s['t']:.2f}$")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.legend(loc="lower left", fontsize=6.8)
    figstyle.panel(ax, "a", "target quotes and the recovered fit")
    figstyle.rms_note(ax, float(np.sqrt(np.mean(err_bp**2))),
                      f"max {err_bp.max():.1f} bp")

    ax = axes[1]
    taus = np.linspace(lvfits.SYN_T[0], lvfits.SYN_T[-1], 61)
    ks = np.linspace(-0.55, 0.55, 121)
    k_lo = np.interp(taus, [s["t"] for s in fit.strips],
                     [s["k"].min() for s in fit.strips])
    k_hi = np.interp(taus, [s["t"] for s in fit.strips],
                     [s["k"].max() for s in fit.strips])
    err = np.full((taus.size, ks.size), np.nan)
    for r, (tau, lo, hi) in enumerate(zip(taus, k_lo, k_hi)):
        inside = (ks >= lo) & (ks <= hi)
        y = np.exp(ks[inside])
        sig_fit = np.sqrt(fit.surface.variance(y, float(tau)))
        err[r, inside] = 100.0 * np.abs(sig_fit - lvfits.sigma_true(tau, y))
    pcm = ax.pcolormesh(ks, taus, np.ma.masked_invalid(err),
                        cmap=figstyle.HEATMAP, shading="auto",
                        rasterized=True)
    for s in fit.strips:
        ax.plot(s["k"], np.full(s["k"].size, s["t"]), ls="none", marker=".",
                markersize=2.5, color=PALETTE["ink"])
    ax.grid(False)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"$\tau$ (years)")
    fig.colorbar(pcm, ax=ax, pad=0.02, fraction=0.06,
                 label="|fit $-$ truth| (vol pts)")
    figstyle.panel(ax, "b", "the second number: surface error")

    STORE.add("recovery", "LvRtMaxErrBp", num(float(err_bp.max()), 1),
              "max quote reprice error (vol bp), clean synthetic round trip")
    STORE.add("recovery", "LvRtRmsErrBp",
              num(float(np.sqrt(np.mean(err_bp**2))), 1),
              "rms quote reprice error (vol bp), clean synthetic round trip")
    STORE.add("recovery", "LvRtSurfRmsPts", num(surf_rms, 2),
              "rms |fit - truth| local vol (vol points), quote-covered region")
    STORE.add("recovery", "LvRtSurfMaxPts", num(surf_max, 2),
              "max |fit - truth| local vol (vol points), quote-covered region")
    STORE.add("recovery", "LvRtNQuotes",
              str(sum(s["k"].size for s in fit.strips)),
              "synthetic quote count (four expiries)")
    STORE.add("recovery", "LvRtEvals", str(fit.n_evals),
              "objective evaluations of the synthetic fit")
    figstyle.save(fig, "fig_lv_recovery")
    return (f"quotes {err_bp.max():.1f} bp max, "
            f"surface {surf_max:.2f} pts max")


def fig_lv_fit() -> str:
    fit = lvfits.fit_ticker("SPY")
    picks = [1, 3, 5, 7]
    sol = solve_affine_dupire(fit.surface, fit.y_grid, fit.t_grid,
                              [n.t for n in fit.nodes])
    fig, axes = plt.subplots(2, 2, figsize=figstyle.GRID22)
    for ax, tag, idx in zip(axes.ravel(), "abcd", picks):
        n = fit.nodes[idx]
        order = np.argsort(n.k)
        kk = np.linspace(float(n.k.min()) - 0.01, float(n.k.max()) + 0.01, 201)
        prices = sol.price_at(idx, np.exp(kk))
        iv = np.asarray(implied_vol(kk, prices, n.t), dtype=float)
        figstyle.whiskers(ax, n.k[order], 100 * n.iv_bid[order],
                          100 * n.iv_ask[order])
        ax.plot(n.k[order], 100 * n.iv_mid[order], ls="none", marker="o",
                markersize=2.6, color=PALETTE["data"])
        ax.plot(kk, 100 * iv, color=PALETTE["model"], lw=1.4)
        ax.set_xlabel(r"log-moneyness $k$")
        ax.set_ylabel("implied vol (%)")
        figstyle.panel(ax, tag, f"{n.expiry}  ({n.days} d)")
        figstyle.rms_note(ax, fit.per_expiry_rms_bp()[idx])
    figstyle.save(fig, "fig_lv_fit")
    return "SPY " + ", ".join(fit.nodes[i].expiry for i in picks)


def fig_lv_rms() -> str:
    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2, sharey=True)
    for ax, tag, ticker in zip(axes, "ab", ("SPY", "NVDA")):
        fit = lvfits.fit_ticker(ticker)
        in_op = fit.per_expiry_rms_bp(refined=False)
        conv = fit.per_expiry_rms_bp(refined=True)
        pos = np.arange(len(fit.nodes))
        ax.bar(pos - 0.19, in_op, width=0.38, color=PALETTE["muted"],
               label="fitting operator")
        ax.bar(pos + 0.19, conv, width=0.38, color=PALETTE["model"],
               label="refined operator")
        ax.set_xticks(pos)
        ax.set_xticklabels([n.expiry[2:] for n in fit.nodes], rotation=45,
                           ha="right", fontsize=6.4)
        ax.set_yscale("log")
        figstyle.panel(ax, tag, f"{ticker}: per-expiry rms (vol bp)")
        if tag == "a":
            ax.set_ylabel("rms (vol bp, log)")
            ax.legend(loc="upper right", fontsize=6.8)

        pre = "Lv" + ("Spy" if ticker == "SPY" else "Nvda")
        surf = fit.surface
        bfly, cal = _arb_diagnostics(fit)
        STORE.add("table", pre + "ButterflyMin",
                  sci(bfly, 1) if bfly < 0 else num(bfly, 6),
                  f"{ticker} min divided second difference of the marched "
                  "prices over every expiry (butterfly proxy)")
        STORE.add("table", pre + "CalendarMin",
                  sci(cal, 1) if cal < 0 else num(cal, 6),
                  f"{ticker} min adjacent-expiry increment of the marched "
                  "prices at fixed y (calendar proxy)")
        STORE.add("table", pre + "RmsBp", num(fit.rms_bp(False), 1),
                  f"{ticker} all-quote rms (vol bp), fitting operator")
        STORE.add("table", pre + "ConvBp", num(fit.rms_bp(True), 1),
                  f"{ticker} all-quote rms (vol bp), refined operator")
        STORE.add("table", pre + "WorstConvBp", num(float(conv.max()), 1),
                  f"{ticker} worst per-expiry refined-operator rms (vol bp)")
        STORE.add("table", pre + "Vtx",
                  str(surf.t_nodes.size * surf.x_nodes.size),
                  f"{ticker} sheet vertex count")
        STORE.add("table", pre + "Quotes", str(len(fit.quotes)),
                  f"{ticker} quote count (all expiries)")
        STORE.add("table", pre + "Evals", str(fit.n_evals),
                  f"{ticker} objective evaluations (cold fit)")
    figstyle.save(fig, "fig_lv_rms")
    return "done"
