"""Figure: where the number lives — the accrual share and the gallery."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import common
import figstyle
from figstyle import PALETTE
from macros import STORE, num


def fig_vs_share() -> str:
    node = common.running_node()
    ff = common.family_fits()
    t = node.t
    w_fn = common.w_curve(ff["LQD"], t)

    k, share = common.accrual_share(w_fn)
    k_lo, k_hi = float(node.k.min()), float(node.k.max())
    quoted = 100.0 * common.span_share(w_fn, k_lo, k_hi)
    atm = 100.0 * common.span_share(w_fn, -0.10, 0.10)
    beyond = 100.0 - quoted

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) cumulative accrual across strikes on the running slice.
    ax_a.axvspan(k_lo, k_hi, color=PALETTE["band"], alpha=0.55, lw=0, zorder=0)
    ax_a.plot(k, 100 * share, color=PALETTE["model"], lw=1.4)
    for edge in (k_lo, k_hi):
        s_edge = 100 * float(np.interp(edge, k, share))
        ax_a.plot([edge], [s_edge], "o", color=PALETTE["ink"], ms=3.0)
    ax_a.set_xlim(-2.0, 1.5)
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel(r"accrued share $\mathcal{S}(k)$ (%)")
    figstyle.callout(
        ax_a, f"quoted span:\n{quoted:.1f}% of the integral",
        xy=(0.5 * (k_lo + k_hi), 88.0), xytext=(0.45, 55.0))
    figstyle.panel(ax_a, "a", "cumulative accrual on the running slice")

    # (b) share beyond the quotes across the frozen gallery (stored fits).
    for ticker, marker in (("SPY", "o"), ("NVDA", "s")):
        taus, shares = [], []
        for n in common.gallery(ticker):
            sl = common.stored_slice(n.ticker, n.expiry)
            outside = 100.0 * (1.0 - common.span_share(
                sl.implied_w, float(n.k.min()), float(n.k.max())))
            taus.append(n.t)
            shares.append(outside)
        color = PALETTE["model"] if ticker == "SPY" else PALETTE["mcs"]
        ax_b.plot(taus, shares, marker, color=color, ms=4.0, label=ticker,
                  lw=0.8, ls="-", alpha=0.9)
        if ticker == "SPY":
            spy_shares = dict(zip(taus, shares))
    all_shares = []
    for ticker in ("SPY", "NVDA"):
        for n in common.gallery(ticker):
            sl = common.stored_slice(n.ticker, n.expiry)
            all_shares.append(100.0 * (1.0 - common.span_share(
                sl.implied_w, float(n.k.min()), float(n.k.max()))))
    ax_b.set_xscale("log")
    ax_b.set_xlabel(r"maturity $\tau$ (years, log scale)")
    ax_b.set_ylabel("share beyond the quotes (%)")
    ax_b.legend(loc="upper left", fontsize=7.5)
    # mark the running node
    run_tau = node.t
    run_share = spy_shares[run_tau]
    ax_b.annotate("the running node", xy=(run_tau, run_share),
                  xytext=(run_tau * 0.28, run_share + 9.0),
                  arrowprops={"arrowstyle": "->", "color": PALETTE["muted"],
                              "lw": 0.9},
                  fontsize=7.5, color=PALETTE["muted"])
    figstyle.panel(ax_b, "b", "the same share across the frozen gallery")

    figstyle.save(fig, "fig_vs_share")

    STORE.add("share", "VsShareQuotedPct", num(quoted, 1),
              "share of the running slice's var-swap integral accrued on the quoted span (%)")
    STORE.add("share", "VsShareBeyondPct", num(beyond, 1),
              "share accrued beyond the quoted span (%)")
    STORE.add("share", "VsShareAtmPct", num(atm, 1),
              "share accrued in |k| <= 0.10 (%)")
    STORE.add("share", "VsShareGalleryMinPct", num(min(all_shares), 1),
              "smallest beyond-quotes share across the 16 frozen nodes (%)")
    STORE.add("share", "VsShareGalleryMaxPct", num(max(all_shares), 1),
              "largest beyond-quotes share across the 16 frozen nodes (%)")
    return f"beyond quotes {beyond:.1f}% (gallery {min(all_shares):.0f}-{max(all_shares):.0f}%)"
