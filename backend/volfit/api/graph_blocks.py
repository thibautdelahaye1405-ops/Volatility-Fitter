"""Ticker-block rule expansion for the graph edge editor (sparse block matrix).

The UI writes topology at TICKER-pair granularity: cross-ticker block rules,
per-ticker calendar-chain rules and optional explicit per-edge overrides
(``GraphBlockRule``). The design contract is a lossless round-trip: the RULE
itself is what persists (GET/PUT /graph/edges/blocks returns it exactly as
written), while this module expands it into the per-edge list ``/graph/edges``
continues to serve — the solver and the network view are unchanged, they only
ever see expanded ``GraphEdgeInput`` rows.

Expansion mirrors the auto-lattice's pairing (graph_service._lattice_weights):
a pair rule links two tickers on every expiry present in BOTH selected ladders
(both directions when symmetric); a calendar rule links consecutive selected
expiries within the ticker, in both directions. Explicit overrides layer LAST —
an override REPLACES any expanded edge with the same directed (from, to) node
pair. Rules naming tickers not currently active (or with an unresolved ladder)
expand to nothing, silently: the rule may legitimately reference a universe
wider than today's, and it must survive intact until those tickers return.
"""

from __future__ import annotations

from volfit.api.graph_universe import _selected_ladders
from volfit.api.schemas import GraphBlockRule, GraphEdgeInput
from volfit.api.state import AppState

#: Directed node pair key: ((fromTicker, fromExpiry), (toTicker, toExpiry)).
_EdgeKey = tuple[tuple[str, str], tuple[str, str]]


def expand_block_rule(state: AppState, rule: GraphBlockRule) -> list[GraphEdgeInput]:
    """Expand a block rule into directed per-edge rows over the selected universe.

    Deterministic: the result is sorted by (fromTicker, fromExpiry, toTicker,
    toExpiry). Calendar and pair rules cannot collide (same-ticker vs cross-ticker
    edges); only ``rule.overrides`` can shadow an expanded edge, and they always
    win. Unknown tickers / unresolved ladders are skipped silently.
    """
    ladders = _selected_ladders(state)
    # Tolerate case drift in hand-typed rules (active tickers are upper-case).
    lookup = {ticker.upper(): ticker for ticker in ladders}

    edges: dict[_EdgeKey, GraphEdgeInput] = {}

    def put(src: tuple[str, str], dst: tuple[str, str], weight: float, beta: float):
        edges[(src, dst)] = GraphEdgeInput(
            fromTicker=src[0], fromExpiry=src[1], toTicker=dst[0], toExpiry=dst[1],
            weight=weight, betaAtmVol=beta, betaSkew=beta, betaCurv=beta,
        )

    for cal in rule.calendar:
        ticker = lookup.get(cal.ticker.upper())
        if ticker is None:
            continue  # inactive / unknown ticker: the rule outlives the universe
        isos = ladders[ticker]
        for near, far in zip(isos[:-1], isos[1:]):
            # Consecutive expiries, BOTH directions — exactly the lattice's
            # calendar edges (_lattice_weights writes near->far AND far->near).
            put((ticker, near), (ticker, far), cal.weight, cal.beta)
            put((ticker, far), (ticker, near), cal.weight, cal.beta)

    for pair in rule.pairs:
        a = lookup.get(pair.a.upper())
        b = lookup.get(pair.b.upper())
        if a is None or b is None or a == b:
            continue  # unknown ticker (skip silently) or degenerate self-pair
        # Same-expiry links on every expiry BOTH ladders carry — the exact
        # pairing the auto-lattice uses for its cross-ticker edges.
        for iso in sorted(set(ladders[a]) & set(ladders[b])):
            put((a, iso), (b, iso), pair.weight, pair.beta)
            if pair.symmetric:
                put((b, iso), (a, iso), pair.weight, pair.beta)

    # Explicit per-edge overrides layered LAST: the same directed (from, to)
    # REPLACES the expanded edge rather than duplicating it. Overrides naming
    # unselected nodes are kept verbatim — build_selected_universe drops edges
    # outside the node set anyway, and the rule must round-trip untrimmed.
    for override in rule.overrides:
        src = (override.fromTicker, override.fromExpiry)
        dst = (override.toTicker, override.toExpiry)
        edges[(src, dst)] = override

    return [edges[key] for key in sorted(edges)]
