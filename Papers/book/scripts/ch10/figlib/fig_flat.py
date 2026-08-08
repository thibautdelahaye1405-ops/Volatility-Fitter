"""Figure 10.1 -- what a sparse morning does not determine.

The frozen SPY December 2026 node is thinned to its at-the-money band; a
flexible spline family is fitted to the band with the wing volatility at
k = -0.30 PINNED to a sweep of imposed values.  Panel (a): the pinned
completions -- identical through the band, fanning in the wing.  Panel (b):
the profile of band misfit against the imposed wing value -- a flat valley
on the thinned morning, a sharp V on the full chain.  Panel (c): the quote
support profile, the cheap proxy for the same geometry.

Stated per-quote noise is the chain's own bid-ask half-spread (floored at
one vol bp), the units discipline of the chapter.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import data10
import estimation
import figstyle
from figstyle import PALETTE
from macros import STORE, num

K_WING = -0.30
PIN_RANGE = (0.24, 0.36)         # imposed wing vols swept over this range
FAN = (0.26, 0.28, 0.30, 0.32, 0.34)
KNOTS = np.array([-0.36, -0.30, -0.22, -0.15, -0.09, -0.04, 0.0,
                  0.04, 0.09, 0.15, 0.26])
PIN_WEIGHT = 1e12                # the pin is effectively exact
RIDGE = 0.5                      # mild smoothness; does not fight the pin


def _noise(iv_bid, iv_ask):
    return np.maximum(0.5 * (iv_ask - iv_bid), 1e-4)


def _pinned_fit(family, k_q, iv_q, sd_q, pin_value):
    pin_row = family.design(np.array([K_WING]))
    return estimation.fit_spline(
        family, k_q, iv_q, sd_q, pin_row, np.array([pin_value]),
        np.array([PIN_WEIGHT]), ridge=RIDGE)


def _profile(family, k_q, iv_q, sd_q, pins):
    """Root-mean-square quote error (bp) as a function of the imposed wing."""
    rms = []
    for pin in pins:
        fit = _pinned_fit(family, k_q, iv_q, sd_q, pin)
        rms.append(1e4 * float(np.sqrt(np.mean(
            (fit.vol(k_q) - iv_q) ** 2))))
    return np.asarray(rms)


def fig_flt_flat() -> str:
    node = data10.running_node()
    k_thin, iv_thin, _, _ = data10.thinned()
    keep = np.abs(node.k) <= data10.BAND
    sd_thin = _noise(node.iv_bid[keep], node.iv_ask[keep])
    sd_full = _noise(node.iv_bid, node.iv_ask)

    family = estimation.SplineFamily(KNOTS)
    pins = np.linspace(*PIN_RANGE, 25)
    prof_thin = _profile(family, k_thin, iv_thin, sd_thin, pins)
    prof_full = _profile(family, node.k, node.iv_mid, sd_full, pins)

    grid = np.linspace(-0.36, 0.26, 401)
    supp_thin = estimation.support(grid, k_thin)
    supp_full = estimation.support(grid, node.k)

    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=figstyle.ROW3)

    # (a) the fan of pinned completions.
    ax_a.axvspan(-data10.BAND, data10.BAND, color=PALETTE["band"],
                 alpha=0.55, zorder=0)
    fan_colors = ["#8a5cd6", "#5b7fb8", "#2a78d6", "#1baf7a", "#eb9a34"]
    for pin, color in zip(FAN, fan_colors):
        fit = _pinned_fit(family, k_thin, iv_thin, sd_thin, pin)
        ax_a.plot(grid, 1e2 * fit.vol(grid), lw=1.1, color=color, alpha=0.9)
    ax_a.plot(k_thin, 1e2 * iv_thin, "o", ms=2.8, color=PALETTE["data"],
              zorder=5, label="morning quotes")
    ax_a.axvline(K_WING, color=PALETTE["muted"], lw=0.8, ls=":")
    figstyle.callout(ax_a, "every curve fits the\nband equally well",
                     (K_WING, 1e2 * FAN[-1]), (-0.20, 1e2 * FAN[-1] + 1.5))
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel("implied volatility (%)")
    ax_a.legend(loc="lower left", fontsize=7.0)
    figstyle.panel(ax_a, "a", "five imposed wings, one band")

    # (b) the profile of misfit against the imposed wing.
    ax_b.plot(1e2 * pins, prof_thin, color=PALETTE["data"], lw=1.5,
              label="thinned morning")
    ax_b.plot(1e2 * pins, prof_full, color=PALETTE["ink"], lw=1.5,
              label="full chain")
    figstyle.callout(
        ax_b, "flat: the band cannot tell",
        (1e2 * pins[4], prof_thin[4] + 2.0), (1e2 * pins[2], 55.0))
    ax_b.set_xlabel(f"imposed wing vol at $k={K_WING}$ (%)")
    ax_b.set_ylabel("rms quote error (vol bp)")
    ax_b.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the likelihood's valley, profiled")

    # (c) the support profile.
    ax_c.axvspan(-data10.BAND, data10.BAND, color=PALETTE["band"],
                 alpha=0.55, zorder=0)
    ax_c.semilogy(grid, np.maximum(supp_full, 1e-4), color=PALETTE["ink"],
                  lw=1.3, label="full chain")
    ax_c.semilogy(grid, np.maximum(supp_thin, 1e-4), color=PALETTE["data"],
                  lw=1.3, label="thinned morning")
    ax_c.axhline(1.0, color=PALETTE["muted"], lw=0.9, ls=":")
    ax_c.annotate("one effective quote", (-0.35, 1.35), fontsize=7.0,
                  color=PALETTE["muted"])
    ax_c.set_ylim(1e-4, 3e1)
    ax_c.set_xlabel("log-moneyness $k$")
    ax_c.set_ylabel(r"quote support $\mathcal{Q}(k)$")
    ax_c.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax_c, "c", "support: the cheap proxy")

    figstyle.save(fig, "fig_flt_flat")

    # Ensemble garnish: eight reference-implementation fits of the band.
    members = data10.ensemble()
    wing_vals = np.array([m.iv(np.array([K_WING]))[0] for m in members])
    ens_spread_pts = 1e2 * float(wing_vals.max() - wing_vals.min())

    valley_bp = float(prof_thin.max() - prof_thin.min())
    rms_best = float(prof_thin.min())
    i_best = int(np.argmin(prof_full))
    rise = prof_full - prof_full[i_best]
    # half-width of the full-chain V at +5 bp of rms.
    above = np.where(rise >= 5.0)[0]
    left = above[above < i_best]
    right = above[above > i_best]
    v_half_pts = 1e2 * float(min(
        pins[i_best] - pins[left[-1]] if left.size else np.inf,
        pins[right[0]] - pins[i_best] if right.size else np.inf,
    ))

    n_thin = k_thin.size
    STORE.add("flat", "PriorFlatNThin", str(n_thin),
              "quotes kept in the staged morning (|k| <= 0.10)")
    STORE.add("flat", "PriorFlatNFull", str(node.n_quotes),
              "quotes on the full frozen chain")
    STORE.add("flat", "PriorFlatHeroDays", str(node.days),
              "days to expiry of the running node")
    STORE.add("flat", "PriorFlatPinLoPct", num(1e2 * PIN_RANGE[0], 0),
              "lowest imposed wing vol (%)")
    STORE.add("flat", "PriorFlatPinHiPct", num(1e2 * PIN_RANGE[1], 0),
              "highest imposed wing vol (%)")
    STORE.add("flat", "PriorFlatPinSpanPts", num(
        1e2 * (PIN_RANGE[1] - PIN_RANGE[0]), 0),
        "span of the imposed wing sweep (vol points)")
    STORE.add("flat", "PriorFlatValleyBp", num(valley_bp, 2),
              "total variation of the thinned-morning rms across the sweep")
    STORE.add("flat", "PriorFlatBandRmsBp", num(rms_best, 1),
              "thinned-morning band rms at the valley floor (bp)")
    STORE.add("flat", "PriorFlatVHalfPts", num(v_half_pts, 1),
              "full-chain V half-width at +5 bp of rms (vol points)")
    STORE.add("flat", "PriorFlatEnsembleSpreadPts", num(ens_spread_pts, 1),
              "wing spread of eight reference-implementation band fits")
    STORE.add("flat", "PriorFlatSuppAtm", num(float(
        estimation.support(np.array([0.0]), k_thin)[0]), 1),
        "quote support at the money on the staged morning")
    STORE.add("flat", "PriorFlatSuppWing", num(float(
        estimation.support(np.array([K_WING]), k_thin)[0]), 2),
        "quote support at k = -0.30 on the staged morning")
    return (f"valley {valley_bp:.2f} bp over {1e2*(PIN_RANGE[1]-PIN_RANGE[0]):.0f} "
            f"pts; full-chain V half-width {v_half_pts:.1f} pts; "
            f"ensemble {ens_spread_pts:.1f} pts")
