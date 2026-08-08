"""Figure F13: calendar order and the confinement illustration.

Panel (a): SPY total variance at fixed log-moneyness across the eight
expiries -- convex order holds where quotes live.  Panel (b): the 1-day /
3-day pair whose *vol-space* order audit flags a huge gap at k ~ +0.98,
far outside the common quote span where both call prices are ~1e-20 of
forward -- the live case for support-confined calendar enforcement.

Every forensic number is RECOMPUTED here from the frozen file (the audit
formula is identified by matching the manifest's stored worst-gap value),
never copied from the data README.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import data
from figstyle import PALETTE, ROW2, panel, save
from macros import STORE, num, sci

FIXED_K = (-0.10, 0.0, 0.10)
K_COLORS = {-0.10: PALETTE["model"], 0.0: PALETTE["ink"], 0.10: PALETTE["data"]}


def calendar_forensics() -> dict:
    """Recompute the family-level advisory from the frozen display curves.

    Replicates the production post-projection calendar audit: for every
    adjacent pair, interpolate the NEAR node's frozen curve onto the FAR
    node's display grid over the grids' overlap and take the worst
    1e4 * (sqrt(w_near / t_far) - sqrt(w_far / t_far)) -- both legs
    annualized at the far maturity.  The recomputed worst must match the
    manifest's stored ``projectionCalendarWorstBp``.
    """
    spy = data.nodes("SPY")
    worst_gap, worst_k, worst_pair = -np.inf, 0.0, (spy[0], spy[1])
    for near, far in zip(spy[:-1], spy[1:]):
        lo = max(float(near.curve_k.min()), float(far.curve_k.min()))
        hi = min(float(near.curve_k.max()), float(far.curve_k.max()))
        sel = (far.curve_k >= lo) & (far.curve_k <= hi)
        w_near = np.interp(far.curve_k[sel], near.curve_k, near.curve_w)
        gap = 1e4 * (np.sqrt(np.maximum(w_near, 0.0) / far.t)
                     - np.sqrt(np.maximum(far.curve_w[sel], 0.0) / far.t))
        idx = int(np.nanargmax(gap))
        if float(gap[idx]) > worst_gap:
            worst_gap = float(gap[idx])
            worst_k = float(far.curve_k[sel][idx])
            worst_pair = (near, far)

    short, long_ = worst_pair
    stored = float(data.manifest()["projectionCalendarWorstBp"])
    if abs(worst_gap - stored) > 1.0:
        raise RuntimeError(
            f"calendar audit mismatch: recomputed {worst_gap:.1f} bp vs "
            f"manifest {stored:.1f} bp")
    best_gap, best_k = worst_gap, worst_k

    span_lo = max(float(short.k.min()), float(long_.k.min()))
    span_hi = min(float(short.k.max()), float(long_.k.max()))
    call_s = float(short.slice.call_price(best_k))
    call_l = float(long_.slice.call_price(best_k))
    k = short.curve_k  # grid reused by the price-space check below

    # Price-space check across ALL adjacent SPY pairs on the display grid.
    worst_price = -np.inf
    spy = data.nodes("SPY")
    for near, far in zip(spy[:-1], spy[1:]):
        viol = np.max(np.asarray(near.slice.call_price(k))
                      - np.asarray(far.slice.call_price(k)))
        worst_price = max(worst_price, float(viol))

    return dict(short=short, long=long_, gap_bp=best_gap,
                gap_k=best_k, stored_bp=stored, span=(span_lo, span_hi),
                call_short=call_s, call_long=call_l, price_worst=worst_price)


def fig_calendar() -> str:
    """F13: term-structure order + the confined-enforcement case study."""
    forensic = calendar_forensics()
    short, long_ = forensic["short"], forensic["long"]
    span_lo, span_hi = forensic["span"]

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    spy = data.nodes("SPY")
    maturities = [n.t for n in spy]
    for k_fix in FIXED_K:
        w_term = [float(n.slice.implied_w(k_fix)) for n in spy]
        axes[0].semilogy(maturities, w_term, color=K_COLORS[k_fix],
                         marker="o", ms=3.0, lw=1.1,
                         label=rf"$k = {k_fix:+.2f}$" if k_fix else r"$k = 0$")
    axes[0].set_xlabel(r"maturity $t$ (years)")
    axes[0].set_ylabel(r"total variance $w(k, t)$")
    axes[0].legend(loc="lower right", fontsize=7.0)
    panel(axes[0], "a", "convex order along the SPY strip")

    # Panel (b) draws the audit quantity itself, from the FROZEN display
    # curves: both legs annualized at the FAR maturity, so the vertical
    # distance between the curves IS the audited gap.  Each solid curve is
    # TRUNCATED where the node's rebuilt call drops below 1e-13 of forward
    # (same rule as fig_lee): beyond that point the stored w(k) is Black-
    # inversion noise, not a smile.  A light dotted flat segment continues
    # each censored curve so the eye knows it ended, not vanished.
    window = (-0.25, 1.05)
    price_floor = 1e-13
    trunc_k: dict[str, float] = {}
    end_vol: dict[str, float] = {}
    for node, color, label in (
        (short, PALETTE["model"], f"{short.expiry}  ({short.days}d)"),
        (long_, PALETTE["data"], f"{long_.expiry}  ({long_.days}d)"),
    ):
        sel = (node.curve_k >= window[0]) & (node.curve_k <= window[1])
        kk = node.curve_k[sel]
        vol = 100.0 * np.sqrt(node.curve_w[sel] / long_.t)
        dead = np.nonzero(
            np.asarray(node.slice.call_price(kk)) < price_floor)[0]
        cut = int(dead[0]) if dead.size else kk.size
        trunc_k[node.expiry] = float(kk[cut - 1])
        end_vol[node.expiry] = float(vol[cut - 1])
        axes[1].plot(kk[:cut], vol[:cut], color=color, lw=1.1, label=label)
        if cut < kk.size:  # censored continuation, not data
            axes[1].plot([kk[cut - 1], window[1]], [vol[cut - 1]] * 2,
                         color=color, lw=0.8, ls=":", alpha=0.55)
    axes[1].axvspan(span_lo, span_hi, color=PALETTE["alt"], alpha=0.22, lw=0.0)
    from matplotlib.transforms import blended_transform_factory

    span_text_tf = blended_transform_factory(axes[1].transData,
                                             axes[1].transAxes)
    axes[1].text(0.5 * (span_lo + span_hi), 0.86, "common\nquote span",
                 transform=span_text_tf, ha="center", fontsize=6.8,
                 color=PALETTE["ink"])
    axes[1].axvline(forensic["gap_k"], color=PALETTE["muted"], lw=0.8, ls=":")
    axes[1].annotate(
        f"order gap {forensic['gap_bp']:.0f} bp; both calls\n$\\leq$ "
        f"{max(forensic['call_short'], forensic['call_long']):.0e}$\\,F$ "
        "— beyond double-\nprecision resolution",
        (forensic["gap_k"], end_vol[long_.expiry]), xytext=(-14, -66),
        textcoords="offset points", ha="right", fontsize=7.0,
        color=PALETTE["muted"],
        arrowprops={"arrowstyle": "->", "color": PALETTE["muted"], "lw": 0.8},
    )
    axes[1].set_xlabel(r"log-moneyness $k$")
    axes[1].set_ylabel(f"vol at the {long_.days}d maturity (%)")
    axes[1].legend(loc="lower right", fontsize=7.0)
    panel(axes[1], "b", "the crossing lives in the empty wing")

    save(fig, "fig_calendar")

    STORE.add("calendar", "CalendarGapBp", num(forensic["gap_bp"], 1),
              "recomputed worst vol-space calendar gap of the 1d/3d pair, bp")
    STORE.add("calendar", "CalendarManifestGapBp", num(forensic["stored_bp"], 1),
              "the same gap as stored by the production exit gate, bp")
    STORE.add("calendar", "CalendarGapK", num(forensic["gap_k"], 3),
              "log-moneyness of the worst vol-space gap")
    STORE.add("calendar", "CalendarSpanLo", num(span_lo, 3),
              "lower edge of the pair's common quote span")
    STORE.add("calendar", "CalendarSpanHi", num(span_hi, 3),
              "upper edge of the pair's common quote span")
    STORE.add("calendar", "CalendarCallShort", sci(forensic["call_short"]),
              "short-dated normalized call at the gap strike")
    STORE.add("calendar", "CalendarCallLong", sci(forensic["call_long"]),
              "longer-dated normalized call at the gap strike")
    STORE.add("calendar", "CalendarPriceWorst", sci(forensic["price_worst"]),
              "worst price-space calendar violation across adjacent SPY"
              " pairs on the display grid (negative = none)")
    STORE.add("calendar", "CalendarShortExpiry", short.expiry,
              "short leg of the forensic pair")
    STORE.add("calendar", "CalendarLongExpiry", long_.expiry,
              "long leg of the forensic pair")
    return (f"calendar: gap {forensic['gap_bp']:.1f} bp at k="
            f"{forensic['gap_k']:.3f} on pair {short.expiry}/{long_.expiry} "
            f"(manifest {forensic['stored_bp']:.1f}); span "
            f"[{span_lo:+.3f}, {span_hi:+.3f}]; price-space worst "
            f"{forensic['price_worst']:.1e}; wing truncation (call<1e-13F) "
            f"2d k={trunc_k[short.expiry]:+.3f}, "
            f"4d k={trunc_k[long_.expiry]:+.3f}")
