"""Figure 5.1: three families, one quote set, three fair strikes."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import common
import figstyle
from figstyle import FAMILY_COLORS, PALETTE
from macros import STORE, num

FAMILIES = ("LQD", "SVI", "MCS")


def fig_vs_pins() -> str:
    node = common.running_node()
    ff = common.family_fits()
    t = node.t

    # Fair strikes by the reference strike-side replication, per family.
    fair = {name: common.fair_w_replication(common.w_curve(ff[name], t))
            for name in FAMILIES}
    vols = {name: common.vs_vol_pct(w, t) for name, w in fair.items()}
    gaps = [abs(vols[a] - vols[b]) * 100.0  # vol bp
            for i, a in enumerate(FAMILIES) for b in FAMILIES[i + 1:]]

    # Belly agreement: worst pairwise IV distance on the quoted span.
    k_belly = np.linspace(float(node.k.min()), float(node.k.max()), 601)
    iv = {name: np.asarray(ff[name].iv(k_belly)) for name in FAMILIES}
    belly_bp = max(
        float(np.max(np.abs(iv[a] - iv[b]))) * 1e4
        for i, a in enumerate(FAMILIES) for b in FAMILIES[i + 1:])

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the quoted region: all three curves thread the same quotes.
    pad = 0.05 * (node.k.max() - node.k.min())
    ka = np.linspace(float(node.k.min()) - pad, float(node.k.max()) + pad, 401)
    figstyle.whiskers(ax_a, node.k, 100 * node.iv_bid, 100 * node.iv_ask,
                      label="bid–ask")
    ax_a.plot(node.k, 100 * node.iv_mid, ".", color=PALETTE["data"], ms=3.0,
              zorder=4)
    for name in FAMILIES:
        ax_a.plot(ka, 100 * np.asarray(ff[name].iv(ka)),
                  color=FAMILY_COLORS[name], lw=1.2, label=name)
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel("implied volatility (%)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the quoted span: three fits, one smile")

    # (b) wide view in total variance: the wings separate.
    kb = np.linspace(-1.25, 1.25, 601)
    ax_b.axvspan(float(node.k.min()), float(node.k.max()),
                 color=PALETTE["band"], alpha=0.55, lw=0, zorder=0)
    for name in FAMILIES:
        w = np.asarray(ff[name].iv(kb)) ** 2 * t
        ax_b.plot(kb, w, color=FAMILY_COLORS[name], lw=1.3,
                  label=rf"{name}: $\sigma_{{\rm vs}}$ {vols[name]:.2f}%")
    ax_b.plot(node.k, node.w_mid, ".", color=PALETTE["data"], ms=3.0, zorder=4)
    ax_b.set_xlabel("log-moneyness $k$")
    ax_b.set_ylabel("total implied variance $w$")
    ax_b.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the wings: three laws, three fair strikes")

    figstyle.save(fig, "fig_vs_pins")

    STORE.add("pins", "VsPinsNQuotes", str(node.n_quotes),
              "prepared quotes on the running SPY December 2026 node")
    STORE.add("pins", "VsPinsLqdPct", num(vols["LQD"]),
              "LQD fair var-swap vol on the running node (%)")
    STORE.add("pins", "VsPinsSviPct", num(vols["SVI"]),
              "SVI fair var-swap vol on the running node (%)")
    STORE.add("pins", "VsPinsMcsPct", num(vols["MCS"]),
              "MCS fair var-swap vol on the running node (%)")
    STORE.add("pins", "VsPinsMaxGapBp", num(max(gaps), 1),
              "largest pairwise fair-strike gap across families (vol bp)")
    STORE.add("pins", "VsPinsBellyAgreeBp", num(belly_bp, 1),
              "worst pairwise IV distance on the quoted span (vol bp)")
    worst_rms = max(ff[name].rms_bp for name in FAMILIES)
    STORE.add("pins", "VsPinsWorstRmsBp", num(worst_rms, 1),
              "worst per-family rms fit error on the node (vol bp)")
    return (f"gap {max(gaps):.1f} bp, belly {belly_bp:.1f} bp, "
            f"vs {vols['LQD']:.2f}/{vols['SVI']:.2f}/{vols['MCS']:.2f}%")
