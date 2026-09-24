"""The Bloomberg stream's PLAN: which securities go on the subscription and
at which conflation interval (split out of volfit.data.bloomberg_live on
2026-09-24 for the tiered-cadence layer; the design is in that module's
docstring).

``BloombergPlanMixin`` gives ``BloombergStreamingMixin``:

* ``_plan_subscriptions(contracts)`` — the underlyings first (the spot comes
  off the stream), then the contracts the shared allocation policy keeps
  within ``max_subscriptions`` (volfit.data.stream_allocation: the focus
  nodes' whole rungs, every ticker's floor, a fair share of the remainder —
  each ticker ranked by |ln K/centre|), ``_stream_dropped`` = the rest.
  BUCKET ROTATION (2026-09-24, volfit.data.bloomberg_rotation) engages ONLY
  when the plan is over the cap: ``_rotation_slots`` (R) are then reserved
  out of the budget, the allocation serves the live set from the remainder
  and ``_rotation_pool`` = the dropped contracts in bucket order (nearest
  the money across tickers); under the cap R = 0 and the whole budget is
  live — the plan is byte-identical with the rotation on or off;
* ``_interval_map(securities)`` — the per-security conflation: the
  underlyings and the FAST set at ``stream_interval`` (1 s), everything else
  at ``slow_interval`` (``VOLFIT_BBG_STREAM_INTERVAL_SLOW``, 5 s). The fast
  set is the contracts of the tickers with a focus node (the desk is looking
  at them), or — without any focus — every ticker's nearest two rungs. The
  Desktop API's per-Terminal update budget is what the slow tier spares;
* ``set_stream_focus(nodes)`` — holds the on-screen nodes, True when they
  changed (``AppState.sync_streaming`` then re-plans in place: only the
  securities whose interval or membership changed move);
* ``stream_tier(ticker, expiry)`` — "live" whenever the ticker streams: both
  tiers are push feeds (there is no REST memory behind a Bloomberg book).

Expects the host's ``_stream_index`` (sec -> (ticker, ParsedOption)),
``_stream_center``, ``_security``, ``_stream_interval``, ``_slow_interval``,
``_max_subscriptions``, ``_floor``, ``_focus``, ``_allocation``,
``_requested``, ``_stream_dropped``, ``_stream_tickers``, ``_rotation_slots``
(R, 0 = off), ``_rotation_pool`` / ``_rotation_active`` (written here).
"""

from __future__ import annotations

import math
import os
from datetime import date

from volfit.data.bloomberg_rotation import rotation_order
from volfit.data.stream_allocation import allocate, normalize_focus

#: The slow conflation tier (s) for the contracts nobody is looking at.
DEFAULT_SLOW_INTERVAL = 5.0
SLOW_INTERVAL_ENV = "VOLFIT_BBG_STREAM_INTERVAL_SLOW"
#: Without a focus, each ticker's nearest this many rungs stay on the fast tier.
FAST_RUNGS = 2


def slow_interval_setting(value: float | None = None) -> float | None:
    """The slow tier: ``value`` when given, else the env knob, else 5 s; 0 =
    every tick (None); a malformed value keeps the default."""
    if value is None:
        raw = os.environ.get(SLOW_INTERVAL_ENV, "").strip()
        try:
            value = float(raw) if raw else DEFAULT_SLOW_INTERVAL
        except ValueError:
            value = DEFAULT_SLOW_INTERVAL
    return float(value) if value and value > 0.0 else None


class BloombergPlanMixin:
    """The subscription plan: allocation, focus, conflation tiers."""

    # ---------------------------------------------------------------- focus
    def set_stream_focus(self, nodes) -> bool:
        """Hold the on-screen nodes ``{(TICKER, expiry ISO)}``; True when they
        CHANGED (the caller re-plans in place), else False."""
        new = normalize_focus(nodes)
        if new == self._focus:
            return False
        self._focus = new
        return True

    def stream_tier(self, ticker: str, expiry: date) -> str:
        """Both conflation tiers are live push feeds; "none" when not streaming."""
        return "live" if self.is_streaming() else "none"

    # ------------------------------------------------------------ the plan
    def _distance(self, sec: str) -> float:
        """|ln K/centre| of a planned security (unknown = last)."""
        entry = self._stream_index.get(sec)
        if entry is None:
            return math.inf
        ticker, c = entry
        center = self._stream_center.get(ticker)
        if not center or c.strike <= 0.0:
            return math.inf
        return abs(math.log(c.strike / center))

    def _plan_subscriptions(self, contracts: list[str]) -> list[str]:
        """Record the requested set and return the securities to stream for it:
        the underlyings first, then the contracts the allocation policy keeps
        (``_stream_dropped`` holds the remainder); the kept contracts keep
        the request's order, so a no-op cap leaves the request untouched."""
        self._requested = list(dict.fromkeys(contracts))
        index = self._stream_index
        self._stream_tickers = {index[s][0] for s in self._requested if s in index}
        underlyings = [self._security(t) for t in sorted(self._stream_tickers)]
        plans: dict[str, list[str]] = {}
        for sec in self._requested:
            plans.setdefault(index[sec][0] if sec in index else "", []).append(sec)
        for ticker, mine in plans.items():
            if ticker:
                mine.sort(key=self._distance)  # stable: the request's order breaks ties
        budget = self._max_subscriptions - len(underlyings)
        # Over the cap — and only then — R slots are reserved for the bucket
        # rotation of the remainder (bloomberg_rotation); under it R = 0 and
        # the allocation sees the whole budget, exactly as before.
        slots = self._rotation_slots if len(self._requested) > budget else 0
        alloc = allocate(
            plans, self._focus, budget - slots, self._floor,
            expiry_of=lambda s: index[s][1].expiry.isoformat() if s in index else None,
        )
        self._allocation = alloc
        keep = set(alloc.live)
        self._stream_dropped = set(alloc.dropped)
        self._rotation_active = slots
        self._rotation_pool = (
            rotation_order(alloc.dropped, lambda s: index[s][0] if s in index else "") if slots else []
        )
        return underlyings + [s for s in self._requested if s in keep]

    def _fast_set(self, securities: list[str]) -> set[str]:
        """The securities on the fast tier: the underlyings; with a focus, every
        contract of the focus tickers; without one, each ticker's nearest
        ``FAST_RUNGS`` expiries."""
        index = self._stream_index
        fast = {self._security(t) for t in self._stream_tickers}
        focused = {t for t, _ in self._focus}
        if focused:
            fast.update(s for s in securities if s in index and index[s][0] in focused)
            return fast
        rungs: dict[str, set[date]] = {}
        for sec in securities:
            if sec in index:
                rungs.setdefault(index[sec][0], set()).add(index[sec][1].expiry)
        nearest = {t: set(sorted(exps)[:FAST_RUNGS]) for t, exps in rungs.items()}
        fast.update(s for s in securities if s in index and index[s][1].expiry in nearest[index[s][0]])
        return fast

    def _interval_map(self, securities: list[str]) -> dict[str, float | None]:
        """sec -> conflation interval: the fast set at ``_stream_interval``,
        the rest at ``_slow_interval`` (an explicit entry per security, so the
        subscription can diff them)."""
        fast = self._fast_set(securities)
        return {s: (self._stream_interval if s in fast else self._slow_interval) for s in securities}


__all__ = ["BloombergPlanMixin", "DEFAULT_SLOW_INTERVAL", "FAST_RUNGS", "slow_interval_setting"]
