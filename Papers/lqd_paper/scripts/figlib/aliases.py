"""Author-contract macro names (review/REQUESTED_MACROS.md reconciliation).

The paper's sections were written against a macro vocabulary that differs
from the generator's canonical names.  This module ADDS the missing names
without touching the canonical set:

* pure aliases re-emit the SAME stored value string as their canonical
  twin, so the two names can never disagree;
* light derivations (max of two audit numbers, signed reformatting, the
  timing-table body) are computed FROM the stored values;
* small per-node quantities the contract asks for by name (exact ATM
  handles, forward rank, endpoint lambdas, Lee ratios) are computed from
  the same cached SPY-Dec / NVDA-long slice objects the figures use.

Runs LAST in the pipeline so every canonical value is already in the store.
"""

from __future__ import annotations

import re

import numpy as np
from scipy.special import expit

from volfit.models.lqd.atm import atm_handles

import data
import fig_tails
from macros import STORE, num, sci

# (new name, canonical name, meaning) — value copied verbatim.
_PURE = [
    ("SnapNodeCount", "NodeCount", "total fitted nodes (alias)"),
    ("SnapMedianRmsBp", "MedianRmsBp", "median per-node rms, vol bp (alias)"),
    ("SnapWorstRmsBp", "WorstRmsBp", "worst per-node rms, vol bp (alias)"),
    ("AuditSliceCount", "CertSlices", "randomized-audit slice count (alias)"),
    ("AuditBoundsWorst", "CertWorstBounds", "worst call-bound violation (alias)"),
    ("AuditFlyWorst", "CertWorstButterfly", "worst butterfly violation (alias)"),
    ("AuditDigitalWorst", "CertWorstDigital", "worst digital violation (alias)"),
    ("AuditGridAgreeWorst", "CertGridAgree",
     "worst 8001-vs-32001-grid price disagreement (alias)"),
    ("CalGapVolBp", "CalendarGapBp", "vol-space order-audit worst gap (alias)"),
    ("CalPriceGridWorst", "CalendarPriceWorst",
     "worst price-space violation, adjacent pairs on the display grid (alias)"),
    ("GuardQuoteCountZeroDte", "NvdaOneDayNQuotes",
     "quote count of the order-guard study node = NVDA 1d (alias)"),
    ("GuardEffOrderZeroDte", "NvdaOneDayOrder",
     "guarded effective order on that node (alias)"),
    ("NvdaOneDayEffOrder", "NvdaOneDayOrder",
     "NVDA 1d guarded effective order (alias)"),
    ("TicketPrice", "TicketCall", "ticket normalized call price (alias)"),
    ("HumpIvAgreeBp", "DhIvGapBp",
     "double-hump max N16-vs-N6 IV gap, vol bp (alias)"),
    ("HumpLOneNSixteen", "DhLOneHigh", "L1 density error at N = 16 (alias)"),
    ("HumpLOneNSix", "DhLOneLow", "L1 density error at N = 6 (alias)"),
    ("JacFdMaxRel", "JacobianMaxRelErr",
     "worst analytic-vs-central-FD relative disagreement (alias)"),
]

_SCI_RE = re.compile(r"([-\d.]+)\\times10\^\{(-?\d+)\}")


def _parse(value: str) -> float:
    """Float back out of a stored macro body (plain decimal or ensuremath)."""
    match = _SCI_RE.search(value)
    if match:
        return float(match.group(1)) * 10.0 ** int(match.group(2))
    return float(value.replace(r"\ensuremath{0}", "0"))


def _timing_rows() -> str:
    """tab:timing body: Configuration & Order & Median & IQR & vs. FD."""
    rows = []
    for order, tag in ((6, "NSix"), (12, "NTwelve"), (16, "NSixteen")):
        a_med = STORE.value(f"TimingAnalyticMed{tag}")
        a_iqr = STORE.value(f"TimingAnalyticIqr{tag}")
        f_med = STORE.value(f"TimingFdMed{tag}")
        f_iqr = STORE.value(f"TimingFdIqr{tag}")
        speed = STORE.value(f"TimingSpeedup{tag}")
        rows.append(rf"Analytic Jacobian & {order} & {a_med}\,ms & "
                    rf"{a_iqr}\,ms & {speed}$\times$")
        rows.append(rf"Finite difference & {order} & {f_med}\,ms & "
                    rf"{f_iqr}\,ms & ---")
    return r"\\ ".join(rows)  # the table source adds the final row break


def _lee_ratios(node: data.Node) -> dict[str, float]:
    """Exact (effective slope) / (Lee limit) at the 10-delta / 1-delta strikes."""
    _, _, beta_l, beta_r = node.tails()
    out = {}
    for side, wing, beta in (("left", "Put", beta_l), ("right", "Call", beta_r)):
        for target, tag in ((0.10, "TenDelta"), (0.01, "OneDelta")):
            k_d = fig_tails._delta_strike(node, target, side)
            eff = float(node.slice.implied_w(k_d)) / abs(k_d)
            out[f"LeeRatio{tag}{wing}"] = eff / beta
    return out


def aliases() -> str:
    """Emit every contract name; see REQUESTED_MACROS.md for the meanings."""
    for new, old, meaning in _PURE:
        STORE.add("aliases", new, STORE.value(old), meaning)

    # Reformatted / derived from stored canonical values.
    STORE.add("aliases", "ExactMaxErr",
              sci(max(_parse(STORE.value("ExactMuWorst")),
                      _parse(STORE.value("ExactMapWorst")))),
              "worst |m, x(z)| error vs closed forms over the scale sweep")
    speedups = [_parse(STORE.value(f"TimingSpeedup{t}"))
                for t in ("NSix", "NTwelve", "NSixteen")]
    STORE.add("aliases", "JacSpeedupMin", num(min(speedups), 2),
              "min median analytic-vs-FD speedup across orders")
    STORE.add("aliases", "JacSpeedupMax", num(max(speedups), 2),
              "max median analytic-vs-FD speedup across orders")
    STORE.add("aliases", "CalGapArgmaxK",
              f"{_parse(STORE.value('CalendarGapK')):+.3f}",
              "argmax log-moneyness of the calendar order-audit gap (signed)")
    STORE.add("aliases", "CalSpanLo",
              f"{_parse(STORE.value('CalendarSpanLo')):+.3f}",
              "common quote span, lower edge (signed)")
    STORE.add("aliases", "CalSpanHi",
              f"{_parse(STORE.value('CalendarSpanHi')):+.3f}",
              "common quote span, upper edge (signed)")
    call_worst = max(_parse(STORE.value("CalendarCallShort")),
                     _parse(STORE.value("CalendarCallLong")))
    exponent = int(np.floor(np.log10(call_worst)))
    STORE.add("aliases", "CalWingPriceOrder",
              rf"\ensuremath{{10^{{{exponent}}}}}",
              "order of magnitude bounding BOTH calls at the gap strike"
              " (the larger of the two; they are 1.6e-26 and 5.4e-107)")
    STORE.add("aliases", "HumpFitRmsBp",
              num(_parse(STORE.value("DhRmsBpHigh")), 1),
              "double-hump N = 16 rms fit error, vol bp (1dp alias)")
    STORE.add("aliases", "TicketRankPct",
              STORE.value("TicketPercentilePct") + r"\%",
              "ticket exercise percentile, rendered with %")
    STORE.add("aliases", "TicketDollarPrice",
              r"\$" + STORE.value("TicketCallDollars"),
              "ticket dollar price per share (call x forward)")
    STORE.add("aliases", "TimingRows", _timing_rows(),
              "tab:timing body rows (Configuration & Order & Median & IQR"
              " & vs. FD)")

    # Per-node quantities from the SAME cached slice objects the figures use.
    spy = data.node(*data.SPY_DEC)
    nvda = data.node(*data.NVDA_LONG)  # 'chosen NVDA' = the F6/F8 long node
    for prefix, node in (("Spy", spy), ("Nvda", nvda)):
        a_l, a_r, b_l, b_r = node.tails()
        STORE.add("aliases", f"{prefix}LamL", num(a_l, 3),
                  f"left endpoint scale lambda- of {node.ticker} {node.expiry}")
        STORE.add("aliases", f"{prefix}LamR", num(a_r, 3),
                  f"right endpoint scale lambda+ of {node.ticker} {node.expiry}")
        STORE.add("aliases", f"{prefix}BetaL", num(b_l, 3),
                  f"left Lee slope of {node.ticker} {node.expiry}")
        STORE.add("aliases", f"{prefix}BetaR", num(b_r, 3),
                  f"right Lee slope of {node.ticker} {node.expiry}")
    handles = atm_handles(spy.slice, spy.t)
    STORE.add("aliases", "SpyDecSkew", num(handles.skew, 3),
              "SPY Dec exact ATM skew sigma'(0), vol per log-moneyness")
    STORE.add("aliases", "SpyDecCurv", num(handles.curvature, 2),
              "SPY Dec exact ATM curvature sigma''(0)")
    u_fwd = float(expit(spy.slice.strike_to_z(0.0)))
    STORE.add("aliases", "SpyDecForwardRankPct",
              num(100.0 * u_fwd, 2) + r"\%",
              "SPY Dec forward rank u* at k = 0, with %")
    ratios = _lee_ratios(spy)
    for name, ratio in ratios.items():
        STORE.add("aliases", name, num(ratio, 2),
                  "SPY Dec effective-slope / Lee-limit ratio at the "
                  + name.replace("LeeRatio", "").lower())
    below = [n for n, r in ratios.items() if r < 1.0]
    flag = f"; RATIOS BELOW 1: {below}" if below else ""
    return (f"aliases: {len(_PURE)} pure + derivations; Lee ratios "
            + ", ".join(f"{n}={r:.2f}" for n, r in ratios.items()) + flag)
