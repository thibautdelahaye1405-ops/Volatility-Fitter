"""The live-slot allocation policy shared by the streaming providers — focus
first, then a per-ticker floor, then a fair share of the remainder
(2026-09-24, the tiered-cadence layer).

Why: the Massive quotes socket allows ~1,000 contracts per connection and the
Bloomberg Desktop API caps concurrent subscriptions. The 2026-09-24 rework
shared that budget across tickers by pure nearest-the-money rank, and on the
app's universe SPY's 25 dense rungs took 874 of 950 live slots while NVDA
got 76 (the rest of both came from the per-minute REST snapshot — no quote
lost, only its cadence). The desk wants the node ON SCREEN ticking at full
NBBO rate, every ticker a fair share of the remainder, and the unviewed rest
at a slower but honest cadence. This module is the pure policy; the
providers feed it their ranked plans and diff its answer against the socket
(volfit.data.massive_stream, volfit.data.bloomberg_plan).

``allocate(plans, focus, budget, floor, expiry_of)`` — three phases:

1. FOCUS — every planned contract of the focus nodes (the nodes with an
   open tick-stream SSE: ``AppState.stream_focus``), nearest-the-money
   first, round-robin across focus tickers. The focus may not eat the floors
   of the tickers WITHOUT a focus: their floors are reserved before it is
   served, so an on-screen SPY rung cannot starve NVDA.
2. FLOORS — one contract at a time to the tickers still under ``floor``
   (each by its own rank, the least-served first), so no ticker starves.
3. FAIR SHARE — one contract at a time to the ticker with the fewest
   NON-focus live contracts (water-filling: equal levels make it a plain
   round-robin, a ticker that starts behind catches up first) until the
   budget is spent; a ticker whose plan runs out leaves the round. The focus
   is not charged against the share: "a fair share of the remainder".

Deterministic (tickers in name order, ties by rank position) and STABLE:
the answer is a pure function of its inputs, and each ticker's live set is a
rank PREFIX of its plan (plus its focus contracts) — a re-plan on unchanged
inputs returns the same contracts, and a change of budget or focus moves
only a ticker's far end. The callers diff the sets, so this is what keeps
the socket quiet under a spot wobble inside the window's hysteresis.

The order of ``Allocation.live`` is the PRIORITY order (focus, floors, then
the fair-share rounds): the Massive transport subscribes in that order, so a
refused chunk trims the least valuable half (volfit.data.massive_ws_acks).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

#: Every ticker keeps at least this many live contracts when the budget
#: allows (env ``VOLFIT_MASSIVE_WS_FLOOR``; shared with the Bloomberg cap).
STREAM_TICKER_FLOOR = 60
FLOOR_ENV = "VOLFIT_MASSIVE_WS_FLOOR"

#: A focus node: ``(TICKER, expiry ISO)`` — the key the tick-stream SSE opens.
Node = tuple[str, str]


def ticker_floor(default: int = STREAM_TICKER_FLOOR) -> int:
    """The per-ticker floor: ``VOLFIT_MASSIVE_WS_FLOOR`` when set and sane,
    else ``default`` (a malformed value never breaks a start)."""
    raw = os.environ.get(FLOOR_ENV, "").strip()
    if not raw:
        return default
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return default


@dataclass(frozen=True)
class TickerShare:
    """One ticker's slots: planned (requested), live, and how many of the
    live ones belong to its focus nodes."""

    requested: int
    live: int
    focus: int = 0

    def as_dict(self) -> dict:
        return {"requested": self.requested, "live": self.live, "focus": self.focus}


@dataclass(frozen=True)
class Allocation:
    """The policy's answer: the live set in priority order, the remainder,
    the per-ticker shares and the focus nodes that matched a plan."""

    live: list[str]
    dropped: list[str]
    shares: dict[str, TickerShare]
    focus: list[Node]

    def as_dict(self) -> dict:
        """The plain form ``stream_stats()`` carries (JSON-serialisable)."""
        return {
            "tickers": {t: s.as_dict() for t, s in sorted(self.shares.items())},
            "focus": [f"{t}|{e}" for t, e in self.focus],
            "live": len(self.live),
            "dropped": len(self.dropped),
        }


def normalize_focus(nodes: Iterable[Node] | None) -> set[Node]:
    """``{(TICKER, expiry ISO)}`` — upper-cased tickers, stripped strings."""
    out: set[Node] = set()
    for ticker, expiry in nodes or ():
        out.add((str(ticker).strip().upper(), str(expiry).strip()))
    return out


class _Cursor:
    """Water-filling over per-ticker queues: each slot goes to the ticker
    with the LOWEST level (ties by name), each queue consumed in its own
    (rank) order — with equal levels that is a plain round-robin, and a
    ticker that starts behind catches up first. The cursor is shared by the
    floor and fair-share phases so a ticker's live set stays one prefix of
    its plan."""

    def __init__(self, queues: Mapping[str, Sequence[str]]) -> None:
        self._queues = {t: list(q) for t, q in queues.items()}
        self._pos = {t: 0 for t in self._queues}
        self._order = sorted(self._queues)

    def _next(self, ticker: str) -> str | None:
        queue, pos = self._queues[ticker], self._pos[ticker]
        if pos >= len(queue):
            return None
        self._pos[ticker] = pos + 1
        return queue[pos]

    def exhausted(self, ticker: str) -> bool:
        return self._pos[ticker] >= len(self._queues[ticker])

    def run(
        self,
        room: int,
        take: Callable[[str, str], bool],
        want: Callable[[str], bool],
        level: Callable[[str], int],
    ) -> int:
        """Fill while ``room`` lasts and some wanted ticker has contracts left:
        the next slot goes to the lowest-``level`` wanted ticker; ``take``
        returns whether the contract was new (a duplicate costs no slot).
        Returns the number of slots used."""
        used = 0
        while used < room:
            candidates = [t for t in self._order if want(t) and not self.exhausted(t)]
            if not candidates:
                break
            ticker = min(candidates, key=level)  # ties: name order (the list is sorted)
            while True:  # skip duplicates without spending a slot
                contract = self._next(ticker)
                if contract is None:
                    break
                if take(ticker, contract):
                    used += 1
                    break
        return used


def allocate(
    plans: Mapping[str, Sequence[str]],
    focus: Iterable[Node] | None,
    budget: int,
    floor: int = STREAM_TICKER_FLOOR,
    expiry_of: Callable[[str], str | None] | None = None,
) -> Allocation:
    """Split ``budget`` live slots across the tickers' ranked ``plans``.

    ``plans``: ticker -> its planned contracts, nearest-the-money FIRST (the
    provider's rank; a caller with contracts of unknown ticker may pass them
    under one pseudo key in input order). ``focus``: the on-screen nodes.
    ``expiry_of(contract)``: the contract's expiry ISO (None = not a focus
    candidate); without it the focus is ignored. See the module docstring
    for the three phases and the stability contract."""
    budget = max(0, int(budget))
    floor = max(0, int(floor))
    tickers = sorted(str(t).upper() for t, plan in plans.items() if plan)
    by_ticker = {str(t).upper(): list(plan) for t, plan in plans.items() if plan}
    focus_nodes = normalize_focus(focus)
    focus_of = {t: {e for tt, e in focus_nodes if tt == t} for t in tickers}

    focus_part: dict[str, list[str]] = {}
    rest_part: dict[str, list[str]] = {}
    for ticker in tickers:
        mine = focus_of[ticker] if expiry_of is not None else set()
        picked: list[str] = []
        rest: list[str] = []
        for contract in by_ticker[ticker]:
            if mine and expiry_of(contract) in mine:  # type: ignore[misc]
                picked.append(contract)
            else:
                rest.append(contract)
        focus_part[ticker], rest_part[ticker] = picked, rest

    live: list[str] = []
    seen: set[str] = set()
    taken: dict[str, list[str]] = {t: [] for t in tickers}

    def take(ticker: str, contract: str) -> bool:
        if contract in seen:
            return False
        seen.add(contract)
        taken[ticker].append(contract)
        live.append(contract)
        return True

    # 1. the focus, with the floors of the focus-less tickers reserved
    focused = {t for t in tickers if focus_part[t]}
    reserved = sum(min(floor, len(by_ticker[t])) for t in tickers if t not in focused)
    focus_used = _Cursor({t: focus_part[t] for t in focused}).run(
        max(0, budget - reserved), take, lambda t: True, lambda t: len(taken[t])
    )
    focus_counts = {t: len(taken[t]) for t in tickers}
    room = budget - focus_used
    # 2. the floors (levelled on the ticker's whole live set — its focus counts
    # towards its floor), 3. the fair share of the REMAINDER (levelled on the
    # non-focus count, so the focus is not charged against it) — one cursor,
    # so each ticker's non-focus set stays a prefix of its plan.
    cursor = _Cursor(rest_part)
    room -= cursor.run(room, take, lambda t: len(taken[t]) < floor, lambda t: len(taken[t]))
    cursor.run(room, take, lambda t: True, lambda t: len(taken[t]) - focus_counts[t])

    dropped = [c for t in tickers for c in by_ticker[t] if c not in seen]
    shares = {
        t: TickerShare(requested=len(by_ticker[t]), live=len(taken[t]), focus=focus_counts[t])
        for t in tickers
    }
    matched = sorted((t, e) for t in tickers for e in focus_of[t] if focus_part[t] and expiry_of is not None
                     and any(expiry_of(c) == e for c in focus_part[t]))
    return Allocation(live=live, dropped=dropped, shares=shares, focus=matched)


__all__ = [
    "Allocation", "FLOOR_ENV", "Node", "STREAM_TICKER_FLOOR", "TickerShare",
    "allocate", "normalize_focus", "ticker_floor",
]
