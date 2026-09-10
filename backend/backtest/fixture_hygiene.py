"""Fixture hygiene — ONE option series per (expiry, strike, side) in a replayed chain.

The 2026-09-10 benchmark readout (ROADMAP wrap 2026-09-10b) found 39 of the
483 spike_aug2024 fixtures carrying two contracts per (expiry, strike, side):

* XOM on every captured day — an ADJUSTED series (a corporate-action root such
  as ``XOM1``, whose deliverable is not 100 plain shares) beside the standard
  one: a 115 call at 150.65 / 155.0 next to the real 4.5 / 4.6, puts one-sided
  (bid None) or cheaper. Fitted as one slice, XOM read 15–50 vol points of rms
  in every sweep and poisoned the graph solve on six days.
* SPX on its monthlies — the AM-settled ``SPX`` and the PM-settled ``SPXW``
  series, both internally consistent, the PM one worth slightly more at every
  strike (it settles ~6.5 h later).

The daily capture wrote those fixtures without the intraday twins'
one-root-per-date policy, and a fixture quote carries no root. This module
recovers one series from the prices alone, so the pack, the graph LOO and
run_compute replay clean chains (``replay.load_fixture`` applies it;
``VOLFIT_FIXTURE_DEDUPE=0`` disables it for byte-identity checks). Rules, in
order, per expiry:

(a) only (strike, side) groups with two or more quotes are touched — every
    other quote is returned as the same object, in the original order;
(b) inside a group a one-sided quote (bid or ask missing / zero) loses to a
    two-sided one;
(c) per strike, put-call parity with the fixture's own forward and discount
    for that expiry, C − P = D·(F − K), decides: each candidate's best
    residual against the other side's options (ties: the cheaper quote); a
    verdict whose margin beats the candidates' bid-ask width is DECISIVE
    (an adjusted series misses parity by its mispricing; two consistent
    series barely differ). Where the other side is absent, the candidate
    whose implied total variance is closest to the median of the expiry's
    uncontested two-sided quotes wins (no reference: the cheaper one) — an
    ambiguous verdict;
(d) a UNIFORMITY vote, per side, over the ambiguous groups only: two
    candidates are ranked by mid (low / high) and the side's majority rank
    among its decisive picks is applied to the ambiguous ones, so one slice
    never mixes two series where parity could not tell them apart (a mid
    rank identifies a series only within a side — an adjusted series is
    dearer on calls and cheaper on puts, a PM twin dearer on both). An
    expiry whose duplicates price within TWIN_RATIO of each other at the
    median strike is a settlement twin: one vote for the whole expiry,
    the cheaper series on a tie (the parent, as the live rule keeps it).
    The expiry's keptRank is the common rank of its sides, "mixed"
    otherwise;
(e) in an expiry that had duplicates, a single (non-duplicated) two-sided
    quote dearer than a decided quote it must not exceed — a call above a
    decided call at a lower strike, a put above a decided put at a higher
    strike — by more than its own width is the second series' strike the
    first never listed (XOM's adjusted 160 C at 105 / 109) and goes too.

The report is per expiry (ISO date) — {nDuplicateKeys, nDropped, keptRank
(low / high / mixed / None), nOneSided, nMonotone} — and empty when nothing
was duplicated. ``python -m backtest.fixture_scan`` lists what it would drop.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import numpy as np

from volfit.core.black import implied_total_variance
from volfit.data.types import OptionQuote

Key = tuple[float, str]  # (strike, call_put)

#: Median high/low mid ratio below which an expiry's duplicates are read as a
#: settlement twin (one expiry-wide vote) rather than a foreign series.
TWIN_RATIO = 1.25


def _two_sided(q: OptionQuote) -> bool:
    return q.bid is not None and q.ask is not None and float(q.bid) > 0.0 and float(q.ask) > 0.0


def _mid(q: OptionQuote) -> float:
    """The mid; a one-sided quote reads its one side (a group can be entirely
    one-sided, and the fallbacks still need an ordering); nan when empty."""
    sides = [float(s) for s in (q.bid, q.ask) if s is not None and float(s) > 0.0]
    return sum(sides) / len(sides) if sides else float("nan")


def _forward(forwards: dict | None, iso: str, spot: float) -> tuple[float, float]:
    """The fixture's parity forward and discount for the expiry (spot, 1 when absent)."""
    rec = (forwards or {}).get(iso) or {}
    f, d = rec.get("forward"), rec.get("discount")
    return (float(f) if f else float(spot)), (float(d) if d else 1.0)


def _parity_residual(c_mid: float, p_mid: float, strike: float, f: float, d: float) -> float:
    return abs((c_mid - p_mid) - d * (f - strike))


def _total_variance(q: OptionQuote, f: float, d: float) -> float:
    """Implied total variance of a two-sided quote's mid (nan when it does not invert)."""
    m = _mid(q)
    if q.call_put == "P":
        m = m + d * (f - float(q.strike))  # parity to the call
    k = math.log(float(q.strike) / f)
    with np.errstate(all="ignore"):
        w = float(implied_total_variance(k, m / (d * f)))
    return w if math.isfinite(w) and w > 0.0 else float("nan")


def _rank(cands: list[int], quotes: list[OptionQuote]) -> dict[int, str]:
    """"low" / "high" by mid for a two-candidate group."""
    lo, hi = sorted(cands, key=lambda i: _mid(quotes[i]))
    return {lo: "low", hi: "high"}


def _dedupe_expiry(
    quotes: list[OptionQuote], idxs: list[int], f: float, d: float
) -> tuple[set[int], dict]:
    """The indices to DROP within one expiry, and the expiry's report entry."""
    groups: dict[Key, list[int]] = defaultdict(list)
    for i in idxs:
        groups[(float(quotes[i].strike), quotes[i].call_put)].append(i)
    dups = {key: g for key, g in groups.items() if len(g) > 1}
    if not dups:
        return set(), {}

    # Reference variance of the expiry: its uncontested two-sided quotes.
    ref = [
        _total_variance(quotes[g[0]], f, d)
        for key, g in groups.items() if len(g) == 1 and _two_sided(quotes[g[0]])
    ]
    ref = [w for w in ref if math.isfinite(w)]
    ref_w = float(np.median(ref)) if ref else None

    def residual(i: int, other: list[int]) -> float:
        """The candidate's best parity residual against the other side's quotes."""
        q = quotes[i]
        return min(
            _parity_residual(
                _mid(q) if q.call_put == "C" else _mid(quotes[j]),
                _mid(quotes[j]) if q.call_put == "C" else _mid(q),
                float(q.strike), f, d,
            )
            for j in other
        )

    def noise(cands: list[int]) -> float:
        """The quote noise a parity verdict must beat: the candidates' mean bid-ask width."""
        widths = [float(quotes[i].ask) - float(quotes[i].bid) for i in cands if _two_sided(quotes[i])]
        return max(sum(widths) / len(widths) if widths else 0.0, 0.01)

    # (b) + (c) per group: parity decides where it can (a one-sided quote reads
    # its one side); ``decisive`` marks a verdict whose margin beats the quote
    # noise. Where parity cannot tell — or there is no other side — a two-sided
    # candidate beats a one-sided one, then the implied-variance distance to
    # the expiry's reference, then the cheaper quote.
    picks: dict[Key, int] = {}
    decisive: dict[Key, bool] = {}
    n_one_sided = 0
    for key, cands in dups.items():
        strike, side = key
        other = groups.get((strike, "P" if side == "C" else "C"), [])
        two = [i for i in cands if _two_sided(quotes[i])]
        if other:
            res = {i: residual(i, other) for i in cands}
            ordered = sorted(cands, key=lambda i: (round(res[i], 9), i not in two, _mid(quotes[i])))
            best = ordered[0]
            margin = res[ordered[1]] - res[best]
            # Decisive = the margin beats the quote noise AND a tenth of the
            # option's price: a settlement twin differs by a few percent (never
            # decisive), a foreign series by a multiple (always).
            floor = 0.1 * min((m for m in (_mid(quotes[i]) for i in cands) if math.isfinite(m)), default=0.0)
            decisive[key] = margin > max(noise(cands), floor)
            if not decisive[key] and two:
                best = min(two, key=lambda i: (round(res[i], 9), _mid(quotes[i])))
        else:
            pool = two or list(cands)
            if ref_w is not None:
                def dist(i: int) -> float:
                    w = _total_variance(quotes[i], f, d)
                    return abs(w - ref_w) if math.isfinite(w) else float("inf")
                best = min(pool, key=lambda i: (dist(i), _mid(quotes[i])))
            else:
                best = min(pool, key=lambda i: _mid(quotes[i]))
            decisive[key] = False
        picks[key] = best
        if best in two:
            n_one_sided += sum(1 for i in cands if i not in two)

    # (d) the uniformity vote, PER SIDE and over the AMBIGUOUS groups only: a
    # mid rank is a series identity within a side (an adjusted series is
    # dearer on calls and cheaper on puts; a PM twin dearer on both), and a
    # decisive parity verdict is never overridden. The side's majority rank
    # among its decisive picks (all picks when none is decisive) is applied
    # to its ambiguous two-candidate groups; the expiry's keptRank is the
    # common rank of its sides ("mixed" when they differ or a side mixes).
    kept_rank: str | None = None
    # A settlement twin prices within a few percent at every strike (SPX /
    # SPXW: median high/low mid ratio 1.02 on the spike monthlies); a foreign
    # series by a multiple. A twin expiry ignores stray per-group verdicts
    # (a deep-out-of-the-money group's residual is the far side's noise).
    ratios = []
    for g in dups.values():
        mids = [m for m in (_mid(quotes[i]) for i in g) if math.isfinite(m) and m > 0.0]
        if len(mids) > 1:
            ratios.append(max(mids) / min(mids))
    twin_expiry = bool(ratios) and float(np.median(ratios)) < TWIN_RATIO
    any_decisive = any(decisive.values()) and not twin_expiry
    if not any_decisive:
        # Nothing told the series apart (a settlement twin): one vote for the
        # whole expiry, both sides, the cheaper series on a tie — the parent
        # (SPX before SPXW), as the live one-root-per-date rule keeps it.
        ranks_all = {key: _rank(dups[key], quotes) for key in dups if len(dups[key]) == 2}
        votes = [ranks_all[key][picks[key]] for key in ranks_all]
        majority = "low" if votes.count("low") >= votes.count("high") else "high"
        for key, rk in ranks_all.items():
            picks[key] = next(i for i, r in rk.items() if r == majority)
    side_rank: dict[str, str] = {}
    for side in ("C", "P"):
        keys = [key for key in dups if key[1] == side]
        if not keys:
            continue
        ranks = {key: _rank(dups[key], quotes) for key in keys if len(dups[key]) == 2}
        voters = [key for key in ranks if decisive[key]] or list(ranks)
        votes = [ranks[key][picks[key]] for key in voters]
        if votes and any_decisive:
            majority = "low" if votes.count("low") >= votes.count("high") else "high"
            for key, rk in ranks.items():
                if not decisive[key]:
                    picks[key] = next(i for i, r in rk.items() if r == majority)
        final = {ranks[key][picks[key]] for key in ranks}
        side_rank[side] = final.pop() if len(final) == 1 else "mixed"
    ranks_seen = set(side_rank.values())
    kept_rank = ranks_seen.pop() if len(ranks_seen) == 1 else ("mixed" if ranks_seen else None)

    keep = set(picks.values())
    drop = {i for g in dups.values() for i in g if i not in keep}

    # (e) the second series' strikes the first never listed are no duplicates,
    # yet they belong to it (XOM's foreign 160 C at 105 / 109 beside a real
    # 115 C at 4.5, a 400 P at 134 on a 114 stock): in an expiry that had
    # duplicates, a single two-sided quote out of monotone order with the
    # DECIDED quotes (a call must not exceed a decided call at a lower strike
    # nor fall under one at a higher strike; puts the mirror) or below its
    # intrinsic value, by more than its own width, goes too.
    calls = sorted((float(quotes[i].strike), _mid(quotes[i])) for i in keep
                   if quotes[i].call_put == "C" and _two_sided(quotes[i]))
    puts = sorted((float(quotes[i].strike), _mid(quotes[i])) for i in keep
                  if quotes[i].call_put == "P" and _two_sided(quotes[i]))
    n_monotone = 0
    for key, g in groups.items():
        if key in dups or not _two_sided(quotes[g[0]]):
            continue
        q = quotes[g[0]]
        strike, m = float(q.strike), _mid(q)
        width = max(float(q.ask) - float(q.bid), 0.01)
        if q.call_put == "C":
            caps = [mid for k_, mid in calls if k_ < strike]
            floors = [mid for k_, mid in calls if k_ > strike]
            intrinsic = d * (f - strike)
        else:
            caps = [mid for k_, mid in puts if k_ > strike]
            floors = [mid for k_, mid in puts if k_ < strike]
            intrinsic = d * (strike - f)
        bad = (
            (caps and m > min(caps) + width)
            or (floors and m < max(floors) - width)
            or m < intrinsic - width
        )
        if bad:
            drop.add(g[0])
            n_monotone += 1
    report = {
        "nDuplicateKeys": len(dups),
        "nDropped": len(drop),
        "keptRank": kept_rank,
        "nOneSided": n_one_sided,
        "nMonotone": n_monotone,
    }
    return drop, report


def dedupe_quotes(
    quotes: list[OptionQuote], forwards: dict | None, spot: float
) -> tuple[list[OptionQuote], dict[str, dict]]:
    """One series per (expiry, strike, side); see the module docstring.

    Returns the kept quotes (original objects, original order) and the report
    keyed by ISO expiry — empty when no (expiry, strike, side) was duplicated."""
    by_exp: dict[date, list[int]] = defaultdict(list)
    for i, q in enumerate(quotes):
        by_exp[q.expiry].append(i)
    drop: set[int] = set()
    report: dict[str, dict] = {}
    for exp in sorted(by_exp):
        iso = exp.isoformat()
        f, d = _forward(forwards, iso, spot)
        gone, entry = _dedupe_expiry(quotes, by_exp[exp], f, d)
        if entry:
            report[iso] = entry
            drop |= gone
    if not drop:
        return quotes, report
    return [q for i, q in enumerate(quotes) if i not in drop], report
