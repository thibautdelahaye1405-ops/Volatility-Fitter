"""F2: the same noisy market read both ways.

Panel A: the naive extraction pipeline -- interpolate 15 quotes per expiry
carrying a deterministic +/-50 bp alternating vol ripple, finite-difference,
and divide -- swings wildly and returns negative variance at many strikes.
Panel B: the same noisy quotes handed to the forward calibration: the
regularized fit averages the noise the derivative quotient amplifies.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import lvfits
from figstyle import PALETTE
from macros import STORE, num

RIPPLE_BP = 50.0


def _extract_band(s: dict, s_next: dict):
    """Naive Dupire extraction AT one quoted expiry: strike derivatives by
    central differences of that expiry's own noisy quotes, the calendar
    derivative by forward difference to the next expiry."""
    k = s["k"]
    w = s["iv"] ** 2 * s["t"]
    w_next = np.interp(k, s_next["k"], s_next["iv"] ** 2 * s_next["t"])
    dtw = (w_next - w) / (s_next["t"] - s["t"])
    # central differences on the (uniform) strike grid
    dk = k[1] - k[0]
    ki = k[1:-1]
    wp = (w[2:] - w[:-2]) / (2 * dk)
    wpp = (w[2:] - 2 * w[1:-1] + w[:-2]) / dk**2
    wi = w[1:-1]
    g_d = (1 - ki * wp / (2 * wi)) ** 2 - 0.25 * wp**2 * (1 / wi + 0.25) \
        + 0.5 * wpp
    v = dtw[1:-1] / g_d
    bad = (g_d <= 0) | (v <= 0)
    return s["t"], ki, v, bad


def fig_lv_wrongway() -> str:
    strips = lvfits.syn_quotes(RIPPLE_BP)

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)
    ax = axes[0]
    max_spike, n_bad, coarse_min = 0.0, 0, np.inf
    # extraction at tau = 0.25, at two quote spacings of the SAME market
    for n_strikes, alpha, label in ((13, 0.55, "from 13 quotes per expiry"),
                                    (31, 1.0, "from 31 quotes per expiry")):
        s = lvfits.syn_quotes(RIPPLE_BP, n_strikes)
        tau, ki, v, bad = _extract_band(s[1], s[2])
        sig = 100.0 * np.sqrt(np.where(bad, np.nan, v))
        max_spike = max(max_spike, float(np.nanmax(sig)))
        if n_strikes == 13:
            coarse_min = float(np.nanmin(sig))
        n_bad += int(bad.sum())
        ax.plot(ki, sig, color=PALETTE["data"], alpha=alpha, lw=1.1,
                marker="o", markersize=2.6, label=label)
        if bad.any():
            ax.plot(ki[bad], np.zeros(bad.sum()), ls="none", marker="x",
                    color=PALETTE["data"], alpha=alpha, markersize=4.5,
                    zorder=4)
    ax.plot(ki, 100.0 * lvfits.sigma_true(0.25, np.exp(ki)),
            color=PALETTE["ink"], lw=1.0, ls="--", label="truth")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("local volatility (%)")
    ax.set_ylim(bottom=-3)
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "a",
                   r"differentiate the data, then divide  ($\tau=0.25$)")
    figstyle.callout(ax, "negative variance:\nno admissible diffusion",
                     (float(ki[bad][2]) if bad.any() else 0.0, 0.0),
                     (-0.13, 3.6))

    fit = lvfits.syn_fit(RIPPLE_BP)
    t_exp = [s["t"] for s in strips]
    ax = axes[1]
    fwd_max = 0.0
    for tau, ls in [(0.30, "-"), (0.70, "-.")]:
        i = int(np.searchsorted(t_exp, tau, side="right") - 1)
        k_lo = max(strips[i]["k"].min(), strips[i + 1]["k"].min())
        k_hi = min(strips[i]["k"].max(), strips[i + 1]["k"].max())
        kk = np.linspace(k_lo, k_hi, 121)
        sig_fit = 100.0 * np.sqrt(fit.surface.variance(np.exp(kk), tau))
        sig_tru = 100.0 * lvfits.sigma_true(tau, np.exp(kk))
        fwd_max = max(fwd_max, float(np.abs(sig_fit - sig_tru).max()))
        ax.plot(kk, sig_fit, color=PALETTE["model"], lw=1.4, ls=ls,
                label=rf"forward fit, $\tau={tau:.2f}$")
        ax.plot(kk, sig_tru, color=PALETTE["ink"], lw=0.9, ls="--")
    ax.plot([], [], color=PALETTE["ink"], lw=0.9, ls="--", label="truth")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("local volatility (%)")
    ax.legend(loc="upper right", fontsize=6.8)
    figstyle.panel(ax, "b", "the same quotes, read forward")

    # global summary numbers: the residual keeps the noise, the edges wander
    err_bp = np.abs(fit.quote_err_bp())
    edge_max = 0.0
    for tau in np.linspace(lvfits.SYN_T[0], lvfits.SYN_T[-1], 31):
        i = min(max(int(np.searchsorted(t_exp, tau, side="right") - 1), 0),
                len(t_exp) - 2)
        lo = max(strips[i]["k"].min(), strips[i + 1]["k"].min())
        hi = min(strips[i]["k"].max(), strips[i + 1]["k"].max())
        y = np.exp(np.linspace(lo, hi, 61))
        edge_max = max(edge_max, float(np.max(
            100 * np.abs(np.sqrt(fit.surface.variance(y, float(tau)))
                         - lvfits.sigma_true(tau, y)))))

    STORE.add("wrongway", "LvWrongMaxSpikePct", num(max_spike, 0),
              "largest extracted local vol (%) in the naive pipeline")
    STORE.add("wrongway", "LvWrongCoarseMinPct", num(coarse_min, 0),
              "smallest valid extracted local vol (%) in the 13-quote arm")
    STORE.add("wrongway", "LvWrongTruthAtmPct",
              num(100.0 * float(lvfits.sigma_true(0.25, 1.0)), 0),
              "true ATM local vol (%) at tau = 0.25")
    STORE.add("wrongway", "LvWrongNBad", str(n_bad),
              "strikes at which the naive extraction returns negative "
              "variance or a nonpositive Durrleman factor")
    STORE.add("wrongway", "LvWrongFwdMaxPts", num(fwd_max, 1),
              "max |fitted - true| local vol (vol points) along the two "
              "plotted cross-sections of the forward fit to the noisy quotes")
    STORE.add("wrongway", "LvWrongQuoteRmsBp", num(
        float(np.sqrt(np.mean(err_bp**2))), 0),
              "reprice rms (vol bp) of the forward fit to the rippled "
              "quotes: the noise stays in the residual, not the surface")
    STORE.add("wrongway", "LvWrongEdgePts", num(edge_max, 0),
              "max |fitted - true| local vol (vol points) anywhere on the "
              "common quoted support: the short-expiry span edges, where "
              "single rippled quotes meet weakly identified vertices")
    STORE.add("wrongway", "LvWrongRippleBp", num(RIPPLE_BP, 0),
              "amplitude (vol bp) of the deterministic alternating ripple")
    figstyle.save(fig, "fig_lv_wrongway")
    return (f"spike {max_spike:.0f}%, {n_bad} bad, cross-sec {fwd_max:.1f} "
            f"pts, edge {edge_max:.0f} pts")
