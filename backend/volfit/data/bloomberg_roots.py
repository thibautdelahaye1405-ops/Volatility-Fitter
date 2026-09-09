"""One listing root per expiry date for Bloomberg chains (the SX5E finding of
2026-09-09).

A Terminal's chain union (``OPT_CHAIN`` + ``CHAIN_TICKERS`` per series) can
list ONE expiry date under SEVERAL option roots — different instruments on
the same date and strikes:

* Eurex EURO STOXX 50: the weekly ``WSX5EB`` and the daily ``SX5EODJ`` both
  expire Friday 2026-09-11 (238 and 226 contracts); the monthly ``SX5E`` and
  the daily ``SX5EODO`` on the 18th. The two series price apart (the weekly
  and the daily settle at different instants), so a slice that keeps both
  carries two smiles about 2.4 vol points apart at every strike — the
  "125 bp rms, ATM discontinuity" of the first live SX5E run, and the
  16 %-per-year discount its parity regression returned.
* Cboe SPX through Bloomberg: the AM-settled parent ``SPX`` and its PM weekly
  sibling ``SPXW`` on every third Friday.

The app keys expiries by DATE (the (date, root) key is the recorded
redesign), so a chain must carry one root per date. The rule is the one the
exchange adapter already applies (``volfit.data.exchange`` ``RawChain.roots``):

1. the PARENT root — the underlying's own (``SX5E``, ``SPX``) — wins when it
   lists the date (OPT_CHAIN's monthlies / LEAPS);
2. otherwise the root whose median-strike call carries the larger OPEN
   INTEREST wins: one reference probe over the contested dates' representative
   contracts, injected by the provider so it is cached with the chain and
   costs one small ``bdp`` per chain refresh — nothing when no date is
   contested;
3. ties, or a probe the Terminal refuses, go to the root listing more strikes
   on that date, then to the first listed.

The kept root per date is what the settlement convention reads (SPX AM on
the monthlies, SPXW PM on the weeklies).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Callable

from volfit.data.bloomberg_parse import ParsedOption

#: ``probe(securities) -> {security: open interest}`` — the provider's one-bdp
#: liquidity vote; None disables the probe (listing rule only).
OpenInterestProbe = Callable[[list[str]], dict[str, int]]


def root_of(security: str) -> str:
    """The option root of a contract security — its first token: "WSX5EB
    09/11/26 C5725 Index" -> "WSX5EB", "SPY US 09/18/26 C500 Equity" -> "SPY"."""
    return security.split(" ", 1)[0].upper()


def parent_root(underlying_security: str) -> str:
    """The underlying's own root: "SX5E Index" -> "SX5E", "SAP GY Equity" -> "SAP"."""
    return underlying_security.split(" ", 1)[0].upper()


def representative(contracts: list[ParsedOption]) -> ParsedOption:
    """The median-strike CALL of one root on one date (its put mirrors it) —
    the contract whose open interest stands for the series' liquidity."""
    calls = sorted((c for c in contracts if c.call_put == "C"), key=lambda c: c.strike)
    pool = calls or sorted(contracts, key=lambda c: c.strike)
    return pool[len(pool) // 2]


@dataclass(frozen=True)
class RootSelection:
    """The chain with one root per date, the root kept for every date, and a
    note per dropped root (for the log)."""

    contracts: list[ParsedOption]
    roots: dict[date, str]
    dropped: list[str]


def one_root_per_date(
    contracts: list[ParsedOption],
    parent: str,
    probe_open_interest: OpenInterestProbe | None,
) -> RootSelection:
    """Keep one option root per expiry date (rule in the module docstring).

    ``contracts`` is the deduplicated chain union in listing order (OPT_CHAIN
    first, then each series). ``parent`` is the underlying's root. The probe is
    called once, over the representative contracts of every contested date
    the parent does not settle; a failing probe degrades to the listing rule.
    """
    by_date: dict[date, dict[str, list[ParsedOption]]] = {}
    for c in contracts:
        by_date.setdefault(c.expiry, {}).setdefault(root_of(c.security), []).append(c)

    contested = {
        d: roots for d, roots in by_date.items() if len(roots) > 1 and parent not in roots
    }
    open_interest: dict[str, int] = {}
    if contested and probe_open_interest is not None:
        reps = [representative(cs).security for roots in contested.values() for cs in roots.values()]
        try:
            open_interest = dict(probe_open_interest(reps))
        except Exception:  # noqa: BLE001 — a refused probe falls back to the listing rule
            open_interest = {}

    kept_roots: dict[date, str] = {}
    dropped: list[str] = []
    for d, roots in by_date.items():
        if len(roots) == 1:
            kept_roots[d] = next(iter(roots))
            continue
        if parent in roots:
            winner = parent
        else:
            order = list(roots)  # listing order (dict insertion) — the last tie-break

            def score(root: str) -> tuple[int, int, int]:
                oi = open_interest.get(representative(roots[root]).security, -1)
                return (oi, len(roots[root]), -order.index(root))

            winner = max(order, key=score)
        kept_roots[d] = winner
        for root, cs in roots.items():
            if root != winner:
                dropped.append(
                    f"{d.isoformat()}: kept {winner} ({len(roots[winner])} contracts), "
                    f"dropped {root} ({len(cs)})"
                )

    kept = [c for c in contracts if root_of(c.security) == kept_roots[c.expiry]]
    return RootSelection(kept, kept_roots, dropped)
