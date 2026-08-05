"""Chapter 3 comparison figures: the arbitrage-free mixture benchmark, the
SPY December node, the SPY gallery margins, and the chapter table macros
(F8-F10).  One protocol for all three families (see fits.py)."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from volfit.core.black import implied_total_variance

import data3
import fits
from figstyle import FAMILY_COLORS, PALETTE, ROW2, panel, save, whiskers
from macros import STORE, num

# Martingale two-lognormal mixture: weights, component vols, component
# forwards (w1 f1 + w2 f2 = 1), quarter-year expiry.
MIX_W = (0.65, 0.35)
MIX_VOL = (0.14, 0.42)
MIX_F2 = 0.85
MIX_F = ((1.0 - MIX_W[1] * MIX_F2) / MIX_W[0], MIX_F2)
MIX_TAU = 0.25


def _mixture_call(k: np.ndarray) -> np.ndarray:
    """Normalized call of the mixture: sum of component Black calls."""
    y = np.exp(np.asarray(k, dtype=float))
    c = np.zeros_like(y)
    for wgt, vol, f in zip(MIX_W, MIX_VOL, MIX_F):
        wi = vol * vol * MIX_TAU
        d1 = (np.log(f / y) + 0.5 * wi) / np.sqrt(wi)
        d2 = d1 - np.sqrt(wi)
        from scipy.stats import norm
        c += wgt * (f * norm.cdf(d1) - y * norm.cdf(d2))
    return c


def _mixture_g(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Exact g_D of the mixture target through the density identity."""
    k = np.asarray(k, dtype=float)
    x = k
    f_x = np.zeros_like(x)
    for wgt, vol, f in zip(MIX_W, MIX_VOL, MIX_F):
        wi = vol * vol * MIX_TAU
        mu = np.log(f) - 0.5 * wi
        f_x += wgt * np.exp(-0.5 * (x - mu) ** 2 / wi) / np.sqrt(2 * np.pi * wi)
    sqrt_w = np.sqrt(w)
    d_minus = -k / sqrt_w - 0.5 * sqrt_w
    phi = np.exp(-0.5 * d_minus**2) / np.sqrt(2.0 * np.pi)
    return f_x * sqrt_w / phi


# ------------------------------------------------------------- F8: mixture
def fig_cmp_mixture() -> str:
    kq = np.linspace(-0.5, 0.4, 25)
    wq = np.asarray(implied_total_variance(kq, _mixture_call(kq)), dtype=float)
    iv_t = np.sqrt(wq / MIX_TAU)
    g_target = _mixture_g(np.linspace(kq.min(), kq.max(), 801),
                          np.asarray(implied_total_variance(
                              np.linspace(kq.min(), kq.max(), 801),
                              _mixture_call(np.linspace(kq.min(), kq.max(), 801))),
                              dtype=float))
    if g_target.min() <= 0.0:
        raise RuntimeError(f"mixture target not admissible: {g_target.min():.4f}")
    STORE.add("mixture", "CmpMixTargetGmin", num(float(g_target.min()), 3),
              "min g_D of the mixture target on the quoted range (exact density)")

    fam_fits = {
        "LQD": fits.fit_lqd(kq, wq, MIX_TAU, iv_t),
        "SVI": fits.fit_svi(kq, wq, MIX_TAU, iv_t),
        "MCS": fits.fit_mcs(kq, wq, MIX_TAU, iv_t),
    }
    for fam, ff in fam_fits.items():
        STORE.add("mixture", f"CmpMix{fam.capitalize()}Rms", num(ff.rms_bp, 1),
                  f"{fam} rms on the mixture target, vol bp")
        STORE.add("mixture", f"CmpMix{fam.capitalize()}Gmin", num(ff.min_g, 3),
                  f"{fam} min g_D on the quoted range, mixture fit")

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    kk = np.linspace(kq.min() - 0.03, kq.max() + 0.03, 601)
    ax = axes[0]
    ax.plot(kq, 100 * iv_t, "o", ms=3.0, color=PALETTE["data"], zorder=5,
            label="mixture target")
    for fam, ff in fam_fits.items():
        ax.plot(kk, 100 * ff.iv(kk), color=FAMILY_COLORS[fam], lw=1.2,
                label=fam)
    ax.set_xlabel(r"$k$"); ax.set_ylabel("implied vol (%)")
    ax.legend(loc="upper right", fontsize=7)
    panel(ax, "a", "a bimodal but arbitrage-free law")

    ax = axes[1]
    for fam, ff in fam_fits.items():
        ax.plot(kq, 1e4 * (ff.iv(kq) - iv_t), "o-", ms=2.6, lw=0.9,
                color=FAMILY_COLORS[fam], label=fam)
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xlabel(r"$k$"); ax.set_ylabel("fit error (vol bp)")
    ax.legend(loc="lower right", fontsize=7)
    panel(ax, "b", "signed errors: one belly against two modes")

    save(fig, "fig_cmp_mixture")
    return " / ".join(f"{f} {fam_fits[f].rms_bp:.1f}bp" for f in fits.FAMILIES)


# ---------------------------------------------------------------- F9: node
def fig_cmp_node() -> str:
    n = data3.node(*data3.SPY_DEC)
    fam_fits = fits.node_fits(*data3.SPY_DEC)
    for fam, ff in fam_fits.items():
        cap = fam.capitalize()
        STORE.add("node", f"CmpSpy{cap}Rms", num(ff.rms_bp, 1),
                  f"{fam} rms on SPY Dec-2026 mid quotes, vol bp")
        STORE.add("node", f"CmpSpy{cap}Gmin", num(ff.min_g, 3),
                  f"{fam} min g_D on the SPY Dec traded range")
        STORE.add("node", f"CmpSpy{cap}BetaL", num(ff.beta_l, 3),
                  f"{fam} left wing slope, SPY Dec fit")
        STORE.add("node", f"CmpSpy{cap}BetaR", num(ff.beta_r, 3),
                  f"{fam} right wing slope, SPY Dec fit")
        STORE.add("node", f"CmpSpy{cap}Par", str(ff.n_params),
                  f"{fam} free parameters on SPY Dec")

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    kk = np.linspace(float(n.k.min()), float(n.k.max()), 601)
    ax = axes[0]
    whiskers(ax, n.k, 100 * n.iv_bid, 100 * n.iv_ask, label="bid-ask")
    for fam, ff in fam_fits.items():
        ax.plot(kk, 100 * ff.iv(kk), color=FAMILY_COLORS[fam], lw=1.1,
                label=fam)
    ax.set_xlabel(r"$k$"); ax.set_ylabel("implied vol (%)")
    ax.legend(loc="upper right", fontsize=7)
    panel(ax, "a", "SPY December 2026, three families, one protocol")

    ax = axes[1]
    for fam, ff in fam_fits.items():
        ax.plot(n.k, 1e4 * (ff.iv(n.k) - n.iv_mid), "o-", ms=2.4, lw=0.8,
                color=FAMILY_COLORS[fam], label=fam)
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xlabel(r"$k$"); ax.set_ylabel("model $-$ mid (vol bp)")
    ax.legend(loc="upper left", fontsize=7)
    panel(ax, "b", "residual structure against the mid quotes")

    save(fig, "fig_cmp_node")
    return " / ".join(f"{f} {fam_fits[f].rms_bp:.1f}bp" for f in fits.FAMILIES)


# ------------------------------------------------------------- F10: gallery
def fig_cmp_gallery() -> str:
    spy = data3.nodes("SPY")
    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    xs = np.arange(len(spy))
    width = 0.26

    for j, fam in enumerate(fits.FAMILIES):
        rms = [fits.node_fits(n.ticker, n.expiry)[fam].rms_bp for n in spy]
        axes[0].bar(xs + (j - 1) * width, rms, width,
                    color=FAMILY_COLORS[fam], label=fam)
        gmin = [fits.node_fits(n.ticker, n.expiry)[fam].min_g for n in spy]
        axes[1].plot(xs, gmin, "o", ms=4, color=FAMILY_COLORS[fam], label=fam)

    labels = [f"{n.days}d" for n in spy]
    for ax in axes:
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_xlabel("SPY expiry (calendar days)")
    axes[0].set_ylabel("rms vs mid (vol bp)")
    axes[0].legend(loc="upper left", fontsize=7)
    panel(axes[0], "a", "fit quality across the SPY expiries")
    axes[1].axhline(0.0, color=PALETTE["ink"], lw=0.7)
    axes[1].set_ylabel(r"validity margin $\min g_{\rm D}$")
    panel(axes[1], "b", "the traded-range butterfly margin")

    save(fig, "fig_cmp_gallery")

    # ------------------------------------------------- book-wide table macros
    all_nodes = data3.nodes()
    STORE.add("table", "CmpNodes", str(len(all_nodes)),
              "nodes in the three-family comparison")
    for fam in fits.FAMILIES:
        cap = fam.capitalize()
        rms = np.array([fits.node_fits(n.ticker, n.expiry)[fam].rms_bp
                        for n in all_nodes])
        gmin = np.array([fits.node_fits(n.ticker, n.expiry)[fam].min_g
                         for n in all_nodes])
        STORE.add("table", f"CmpTab{cap}MedRms", num(float(np.median(rms)), 1),
                  f"{fam} median rms across the 16 nodes, vol bp")
        STORE.add("table", f"CmpTab{cap}WorstRms", num(float(rms.max()), 1),
                  f"{fam} worst rms across the 16 nodes, vol bp")
        STORE.add("table", f"CmpTab{cap}MedGmin", num(float(np.median(gmin)), 3),
                  f"{fam} median traded-range min g_D across the 16 nodes")
        STORE.add("table", f"CmpTab{cap}WorstGmin", num(float(gmin.min()), 3),
                  f"{fam} worst traded-range min g_D across the 16 nodes")
        STORE.add("table", f"CmpTab{cap}NegNodes", str(int((gmin < 0).sum())),
                  f"{fam} nodes with a negative traded-range margin")

    # The capacity dial isolated: the same MCS protocol with R = 0 (its
    # convex base alone) across the same 16 nodes.
    zero = [fits.fit_mcs(n.k, n.w_mid, n.t, n.iv_mid, n_cores=0)
            for n in all_nodes]
    rms0 = np.array([f.rms_bp for f in zero])
    gmin0 = np.array([f.min_g for f in zero])
    STORE.add("table", "CmpTabMcszeroMedRms", num(float(np.median(rms0)), 1),
              "MCS base (R=0) median rms across the 16 nodes, vol bp")
    STORE.add("table", "CmpTabMcszeroMedGmin", num(float(np.median(gmin0)), 3),
              "MCS base (R=0) median traded-range min g_D")
    STORE.add("table", "CmpTabMcszeroNegNodes", str(int((gmin0 < 0).sum())),
              "MCS base (R=0) nodes with a negative traded-range margin")
    return "table macros over 16 nodes"
