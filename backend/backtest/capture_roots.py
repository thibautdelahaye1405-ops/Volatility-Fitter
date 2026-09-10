"""One option root per expiry date for the DAILY capture (backtest.capture).

The intraday twins resolve same-date root collisions with ``backtest.roots``
(first-listed root wins the date); the daily capture never did, and its two
fetch paths let a second series into a slice in two different ways:

* the REST enumeration asks Massive for ``underlying_ticker = <root>`` and gets
  every contract ON that underlying — including corporate-action series whose
  OCC root differs (``XOM1`` under XOM), which the parser tells apart but the
  capture never checked;
* the flat-file reader keeps exactly the asset's roots, but for a multi-root
  index (``SPX`` + ``SPXW``) it keeps BOTH on a shared date.

This module gives the daily capture both halves of the twins' policy: a root
filter on the parsed OCC symbol and the same-date collision rule, and records
what it did in the fixture's ``meta`` (``roots`` / ``expiryRoots`` /
``rootCollisions`` / ``droppedRoots``) — written only when something happened,
so single-root fixtures keep their exact key set. A fixture already on disk is
NEVER rewritten here; fixture_hygiene cleans those at replay.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable

from backtest.roots import resolve_expiry_roots
from volfit.data.occ import underlying_of
from volfit.data.types import ChainSnapshot


def contract_root(occ_ticker: str) -> str | None:
    """The OCC root of an ``O:`` symbol (None when it does not parse)."""
    return underlying_of(occ_ticker)


def _meta(roots: tuple[str, ...], expiry_root: dict[date, str], collisions: list[dict],
          dropped: Counter) -> dict:
    meta: dict = {}
    if collisions:
        meta["roots"] = list(roots)
        meta["expiryRoots"] = {e.isoformat(): r for e, r in sorted(expiry_root.items())}
        meta["rootCollisions"] = collisions
    if dropped:
        meta["droppedRoots"] = {r: int(n) for r, n in sorted(dropped.items())}
    return meta


def apply_root_policy(by_expiry: dict[date, list], roots: Iterable[str]) -> tuple[dict[date, list], dict]:
    """REST path: keep the contracts whose OCC root is one of ``roots`` and,
    per expiry date, only the first-listed root that lists it.

    ``by_expiry`` maps an expiry to contract records carrying ``occ_ticker``
    (rest_quotes._Contract). Returns the filtered map and the ``meta`` block."""
    roots = tuple(r.upper() for r in roots)
    dropped: Counter = Counter()
    boards: dict[str, set[date]] = {r: set() for r in roots}
    tagged: dict[date, list[tuple[str, object]]] = {}
    for exp, contracts in by_expiry.items():
        for c in contracts:
            root = (contract_root(c.occ_ticker) or "").upper()
            if root not in boards:
                dropped[root or "?"] += 1
                continue
            boards[root].add(exp)
            tagged.setdefault(exp, []).append((root, c))
    expiry_root, collisions = resolve_expiry_roots(boards, roots)
    kept = {
        exp: [c for root, c in pairs if expiry_root.get(exp) == root]
        for exp, pairs in tagged.items()
    }
    kept = {exp: cs for exp, cs in kept.items() if cs}
    return kept, _meta(roots, expiry_root, collisions, dropped)


def merge_root_chains(
    ticker: str, chains_by_root: dict[str, ChainSnapshot | None], roots: Iterable[str]
) -> tuple[ChainSnapshot | None, dict]:
    """Flat-file path: one chain per root (``chain_at(option_roots=[root])``)
    merged under the same-date rule — every expiry date keeps the first-listed
    root's quotes only. Spot / stamp / style come from the first root that
    answered."""
    roots = tuple(r.upper() for r in roots)
    boards = {r: (set(ch.expiries()) if ch is not None else set()) for r, ch in chains_by_root.items()}
    boards = {r: boards.get(r, set()) for r in roots}
    expiry_root, collisions = resolve_expiry_roots(boards, roots)
    first = next((ch for r in roots if (ch := chains_by_root.get(r)) is not None), None)
    if first is None:
        return None, {}
    quotes = [
        q for r in roots
        for q in ((chains_by_root.get(r).quotes) if chains_by_root.get(r) is not None else [])
        if expiry_root.get(q.expiry) == r
    ]
    chain = ChainSnapshot(ticker, first.spot, first.timestamp, quotes, first.exercise_style)
    return chain, _meta(roots, expiry_root, collisions, Counter())
