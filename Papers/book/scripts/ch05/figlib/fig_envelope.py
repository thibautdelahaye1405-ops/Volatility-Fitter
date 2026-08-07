"""Figure: the envelope of admissible completions beyond the last quote.

The cone is built from the last two call-side quote mids of the running node:
monotonicity caps the continuation at the last call value, convexity floors it
at the secant ray.  Mapping both edges through the Black chart gives the fan
of admissible total-variance completions; the three families' fitted wings
must (and do) thread it.  The upper edge admits the closed form
sqrt(w+) = PhiInv(cbar) + sqrt(PhiInv(cbar)^2 + 2k) up to an exponentially
small term, validated here against the production inversion.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from scipy.special import ndtri

import common
import figstyle
from figstyle import FAMILY_COLORS, PALETTE
from macros import STORE, num, sci

from volfit.core.black import black_call, implied_total_variance

FAMILIES = ("LQD", "SVI", "MCS")


def _last_two_strikes(node) -> tuple[float, float]:
    order = np.argsort(node.k)
    k_sorted = node.k[order]
    return float(k_sorted[-2]), float(k_sorted[-1])


def _cone_from(k1: float, k2: float, c1: float, c2: float):
    """(cbar, s_bar): the cone frozen at the last quote from two call values."""
    s_bar = (c2 - c1) / (np.exp(k2) - np.exp(k1))
    return c2, s_bar


def _cone(node):
    """(k1, k2, c1, c2, s_bar) from the last two call-side quote mids."""
    k1, k2 = _last_two_strikes(node)
    order = np.argsort(node.k)
    w_sorted = node.w_mid[order]
    c1 = float(black_call(k1, float(w_sorted[-2])))
    c2 = float(black_call(k2, float(w_sorted[-1])))
    cbar, s_bar = _cone_from(k1, k2, c1, c2)
    return k1, k2, c1, cbar, s_bar


def fig_vs_envelope() -> str:
    node = common.running_node()
    ff = common.family_fits()
    t = node.t
    k1, kbar, c1, cbar, s_bar = _cone(node)
    ybar = float(np.exp(kbar))
    y_zero = ybar - cbar / s_bar          # where the lower edge hits zero
    k_zero = float(np.log(y_zero))

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # ---- (a) price space: the cone between monotone cap and convex floor.
    # Calls out here are ~1e-4 of forward, so the axis is in units of 1e-4.
    SCALE = 1e4
    order = np.argsort(node.k)
    k_call = node.k[order][node.k[order] > 0.02]
    w_call = node.w_mid[order][node.k[order] > 0.02]
    y_q = np.exp(k_call[-6:])
    c_q = SCALE * np.asarray(black_call(k_call[-6:], w_call[-6:]))
    slice_ = ff["LQD"].model
    y_belly = np.linspace(float(y_q[0]) * 0.998, ybar, 120)
    c_belly = SCALE * np.asarray(slice_.call_price(np.log(y_belly)))
    y_ext = np.linspace(ybar, y_zero * 1.10, 240)
    lower = SCALE * np.maximum(cbar + s_bar * (y_ext - ybar), 0.0)
    upper = np.full_like(y_ext, SCALE * cbar)
    ax_a.fill_between(y_ext, lower, upper, color=PALETTE["band"], alpha=0.8,
                      lw=0, zorder=0)
    ax_a.plot(y_belly, c_belly, color=PALETTE["ink"], lw=1.2,
              label="the belly (fitted)")
    ax_a.plot(y_q, c_q, ".", color=PALETTE["data"], ms=5.0, zorder=4,
              label="quote mids")
    ax_a.plot(y_ext, upper, color=PALETTE["muted"], lw=1.1, ls="--")
    ax_a.plot(y_ext, lower, color=PALETTE["muted"], lw=1.1)
    ax_a.plot([y_zero], [0.0], "o", color=PALETTE["ink"], ms=3.5, zorder=5)
    figstyle.callout(ax_a, "slope may rise to 0:\nthe monotone cap",
                     xy=(float(y_ext[190]), SCALE * cbar),
                     xytext=(float(y_ext[130]), SCALE * cbar * 0.62))
    figstyle.callout(ax_a, "slope may stay at $\\bar{s}$:\nthe convex floor",
                     xy=(0.55 * ybar + 0.45 * y_zero, float(
                         np.interp(0.55 * ybar + 0.45 * y_zero, y_ext, lower))),
                     xytext=(0.996 * ybar, SCALE * cbar * 0.18))
    ax_a.set_xlabel("strike ratio $y$")
    ax_a.set_ylabel(r"normalized call ($10^{-4}$ of forward)")
    ax_a.set_xlim(float(y_belly[0]) - 0.003, y_zero * 1.10)
    ax_a.set_ylim(-0.08, float(c_q[0]) * 1.06)
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "price space: the admissible cone")

    # ---- (b) the same cone in the Black chart: the total-variance fan.
    # (Ends at k = 1.8: beyond, the flattest wing's call price falls under the
    # double-precision floor and its Black inversion turns to noise.)
    k_fan = np.linspace(kbar, 1.8, 400)
    y_fan = np.exp(k_fan)
    low_price = np.maximum(cbar + s_bar * (y_fan - ybar), 0.0)
    w_lo = np.where(
        low_price > 0.0,
        np.nan_to_num(implied_total_variance(k_fan, low_price), nan=0.0),
        0.0)
    w_hi = np.asarray(implied_total_variance(
        k_fan, np.full_like(k_fan, cbar)))
    ax_b.fill_between(k_fan, w_lo, w_hi, color=PALETTE["band"], alpha=0.8,
                      lw=0, zorder=0)
    ax_b.plot(k_fan, w_hi, color=PALETTE["muted"], lw=1.1, ls="--",
              label=r"edges $w^{\pm}$")
    ax_b.plot(k_fan, w_lo, color=PALETTE["muted"], lw=1.1)
    # Clearances are measured against EACH family's own cone (built from its
    # own fitted call values at the same two strikes) — nonnegativity is then
    # the convexity/monotonicity theorem, confirmed numerically.  The drawn
    # fan stays the one built from the quote mids.
    clearances = {}
    sel = k_fan >= kbar + 0.05
    for name in FAMILIES:
        w_fam = np.asarray(ff[name].iv(k_fan)) ** 2 * t
        ax_b.plot(k_fan, w_fam, color=FAMILY_COLORS[name], lw=1.3, label=name)
        w_two = np.asarray(ff[name].iv(np.array([k1, kbar]))) ** 2 * t
        c_two = np.asarray(black_call(np.array([k1, kbar]), w_two))
        c_own, s_own = _cone_from(k1, kbar, float(c_two[0]), float(c_two[1]))
        lo_own_price = np.maximum(c_own + s_own * (y_fan - ybar), 0.0)
        w_lo_own = np.where(
            lo_own_price > 0.0,
            np.nan_to_num(implied_total_variance(k_fan, lo_own_price),
                          nan=0.0),
            0.0)
        w_hi_own = np.asarray(implied_total_variance(
            k_fan, np.full_like(k_fan, c_own)))
        clearances[name] = (float(np.min((w_fam - w_lo_own)[sel])),
                            float(np.min((w_hi_own - w_fam)[sel])))
    k_belly_ax = np.linspace(-0.1, kbar, 60)
    ax_b.plot(k_belly_ax, np.asarray(ff["LQD"].iv(k_belly_ax)) ** 2 * t,
              color=PALETTE["ink"], lw=1.2)
    ax_b.plot(node.k, node.w_mid, ".", color=PALETTE["data"], ms=3.0, zorder=4)
    ax_b.set_xlim(-0.1, 1.8)
    ax_b.set_xlabel("log-moneyness $k$")
    ax_b.set_ylabel("total implied variance $w$")
    ax_b.legend(loc="upper left", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the same cone as a total-variance fan")

    figstyle.save(fig, "fig_vs_envelope")

    # Closed-form upper edge vs the production inversion, deep in the wing.
    q_inv = float(ndtri(cbar))
    k_deep = 30.0
    w_closed = (q_inv + np.sqrt(q_inv * q_inv + 2.0 * k_deep)) ** 2
    w_exact = float(implied_total_variance(k_deep, cbar))
    slope_deep = 2.0 + 2.0 * q_inv / np.sqrt(q_inv * q_inv + 2.0 * k_deep)

    STORE.add("envelope", "WingEnvKbar", num(kbar, 3),
              "last quoted call-side log-moneyness on the running node")
    STORE.add("envelope", "WingEnvCbar", sci(cbar, 2),
              "normalized call at the last quote (of forward)")
    STORE.add("envelope", "WingEnvKzero", num(k_zero, 3),
              "log-moneyness where the lower envelope edge reaches zero")
    STORE.add("envelope", "WingEnvTopAgree", sci(abs(w_exact - w_closed), 1),
              "closed-form upper edge vs production inversion at k = 30 (total variance)")
    STORE.add("envelope", "WingEnvTopSlopeDeep", num(slope_deep, 2),
              "upper-edge slope dw+/dk at k = 30 (heads to 2)")
    for name in FAMILIES:
        lo, hi = clearances[name]
        STORE.add("envelope", f"WingEnvClear{name.title()}Lo", num(lo, 4),
                  f"min clearance of the {name} wing above its own cone's lower edge")
        STORE.add("envelope", f"WingEnvClear{name.title()}Hi", num(hi, 4),
                  f"min clearance of the {name} wing below its own cone's upper edge")
    # Family wing slopes for the chapter's contract table.
    for name in FAMILIES:
        STORE.add("table", f"WingBeta{name.title()}L", num(ff[name].beta_l, 3),
                  f"{name} left (put) asymptotic total-variance wing slope")
        STORE.add("table", f"WingBeta{name.title()}R", num(ff[name].beta_r, 3),
                  f"{name} right (call) asymptotic total-variance wing slope")
    worst_lo = min(clearances[n][0] for n in FAMILIES)
    worst_hi = min(clearances[n][1] for n in FAMILIES)
    return (f"kbar {kbar:.3f}, cone zero at {k_zero:.3f}, clearances "
            f"lo {worst_lo:.4f} / hi {worst_hi:.4f}, top agree "
            f"{abs(w_exact - w_closed):.2e}")
