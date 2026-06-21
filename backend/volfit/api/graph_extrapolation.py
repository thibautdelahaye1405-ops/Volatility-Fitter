"""Production graph smile-extrapolation service (plan Phases 1-6).

This is the *production* counterpart to ``volfit.api.graph_service`` (which
stays the manual-shift sandbox, plan Amendment A). The two never share an
endpoint or semantics:

    transported prior -> lit calibration innovation -> graph posterior increment
                      -> dark reconstructed smile    -> quote comparison

Phase 1 (this commit) builds the graph over the **user-selected lit+dark
universe only** (plan Amendment C): the product boundary is the universe the
user picked, not every node the provider happens to expose. Later phases attach
transported-prior baselines (Phase 2), the lit-calibration innovation feed and
the solve (Phase 3), data-derived precision (Phase 4), reconstructed smiles +
quote metrics (Phase 5) and per-edge beta (Phase 6).

The lattice topology (calendar chains within a ticker + cross-ticker same-expiry
edges) reuses the sandbox's ``_lattice_weights`` helper restricted to the
selected node set, so both paths build edges identically.
"""

from __future__ import annotations

from dataclasses import dataclass

from volfit.api.graph_service import (
    CROSS_TICKER_WEIGHT,
    SAME_TICKER_WEIGHT,
    _lattice_weights,
)
from volfit.api.state import AppState
from volfit.graph.build import NodeId, SmileGraph, build_graph


@dataclass(frozen=True)
class SelectedNode:
    """One node of the selected production universe: ``(ticker, expiry-ISO)``
    plus its lit/dark designation (lit = a calibration observation; dark = an
    extrapolation target whose quotes, if any, are used only for validation)."""

    ticker: str
    expiry: str  # ISO date
    lit: bool

    @property
    def name(self) -> NodeId:
        return (self.ticker, self.expiry)


@dataclass(frozen=True)
class SelectedUniverse:
    """The production graph built over the selected lit+dark nodes only.

    Carries the node list (with lit/dark flags) and the prepared ``SmileGraph``
    topology. Deliberately separate from the sandbox ``SmileUniverse`` so the
    two paths never couple; later phases hang per-node prior/precision and
    reconstruction off the same node ordering. ``graph`` is ``None`` for an
    empty selection (a degenerate graph cannot be built, plan Phase 1 test).
    """

    nodes: tuple[SelectedNode, ...]
    graph: SmileGraph | None

    @property
    def names(self) -> tuple[NodeId, ...]:
        """Node names in graph order ``(ticker, expiry-ISO)``."""
        return tuple(node.name for node in self.nodes)

    @property
    def lit_names(self) -> tuple[NodeId, ...]:
        return tuple(node.name for node in self.nodes if node.lit)

    @property
    def dark_names(self) -> tuple[NodeId, ...]:
        return tuple(node.name for node in self.nodes if not node.lit)

    def node_index(self, name: NodeId) -> int:
        if self.graph is None:
            raise KeyError(name)
        return self.graph.index[name]


def _selected_ladders(state: AppState) -> dict[str, list[str]]:
    """``{ticker: [expiry-ISO, ...]}`` over the active tickers' SELECTED
    expiries only (cheap selection metadata — no chain fetch, no fit). Empty
    ladders are dropped so a ticker with no resolved selection adds no nodes."""
    ladders: dict[str, list[str]] = {}
    for ticker in state.active_tickers():
        isos = [expiry.isoformat() for expiry in sorted(state.selected_expiries(ticker))]
        if isos:
            ladders[ticker] = isos
    return ladders


def build_selected_universe(state: AppState) -> SelectedUniverse:
    """Build the production graph over the selected lit+dark universe.

    Nodes = every active ticker x its selected expiries (lit/dark read from
    ``state.node_lit``); edges = the lattice (calendar chains + cross-ticker
    same-expiry) restricted to that node set. Unselected provider expiries are
    never included (plan Amendment C). An empty selection yields an empty
    universe with ``graph=None`` rather than crashing.
    """
    ladders = _selected_ladders(state)
    nodes: list[SelectedNode] = []
    for ticker, isos in ladders.items():
        for iso in isos:
            nodes.append(SelectedNode(ticker, iso, lit=state.node_lit(ticker, iso)))

    if not nodes:
        return SelectedUniverse(nodes=(), graph=None)

    weights = _lattice_weights(
        list(ladders), ladders, SAME_TICKER_WEIGHT, CROSS_TICKER_WEIGHT
    )
    graph = build_graph([node.name for node in nodes], weights)
    return SelectedUniverse(nodes=tuple(nodes), graph=graph)
