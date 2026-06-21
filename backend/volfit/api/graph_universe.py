"""Selected lit+dark universe construction for the production graph (plan Phase 1).

The production graph is built over the user-selected lit+dark nodes only (plan
Amendment C): the product boundary is the universe the user picked, not every node
the provider happens to expose. Edges reuse the sandbox lattice (calendar chains
within a ticker + cross-ticker same-expiry) restricted to the selected node set, so
both the sandbox and production paths build topology identically.

Split out of ``graph_extrapolation`` (orchestration) to keep both under the file-size
policy; the solve/precision/beta logic lives there, the reconstruction in
``graph_reconstruct``.
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


def lattice_weights_for(
    state: AppState,
    calendar_weight: float | None = None,
    cross_weight: float | None = None,
) -> dict[tuple[NodeId, NodeId], float]:
    """The auto-lattice directed weights over the selected universe (calendar
    chains + cross-ticker same-expiry). Exposed so the edge editor can seed from
    the lattice the solve would otherwise build."""
    ladders = _selected_ladders(state)
    calendar_w = SAME_TICKER_WEIGHT if calendar_weight is None else calendar_weight
    cross_w = CROSS_TICKER_WEIGHT if cross_weight is None else cross_weight
    return _lattice_weights(list(ladders), ladders, calendar_w, cross_w)


def build_selected_universe(
    state: AppState,
    calendar_weight: float | None = None,
    cross_weight: float | None = None,
    edges: list[tuple[NodeId, NodeId, float]] | None = None,
) -> SelectedUniverse:
    """Build the production graph over the selected lit+dark universe.

    Nodes = every active ticker x its selected expiries (lit/dark read from
    ``state.node_lit``). Edges default to the auto-lattice (calendar chains +
    cross-ticker same-expiry) with optional ``calendar_weight`` / ``cross_weight``
    overrides; an explicit ``edges`` list of ``(src_name, dst_name, weight)``
    REPLACES the lattice (restricted to the selected node set — edges naming an
    unselected node are dropped) (plan Phase 7). Unselected provider expiries are
    never included (Amendment C). An empty selection yields ``graph=None``.
    """
    ladders = _selected_ladders(state)
    nodes: list[SelectedNode] = []
    for ticker, isos in ladders.items():
        for iso in isos:
            nodes.append(SelectedNode(ticker, iso, lit=state.node_lit(ticker, iso)))

    if not nodes:
        return SelectedUniverse(nodes=(), graph=None)

    names = {node.name for node in nodes}
    if edges is not None:
        weights = {
            (src, dst): float(w) for src, dst, w in edges if src in names and dst in names
        }
    else:
        calendar_w = SAME_TICKER_WEIGHT if calendar_weight is None else calendar_weight
        cross_w = CROSS_TICKER_WEIGHT if cross_weight is None else cross_weight
        weights = _lattice_weights(list(ladders), ladders, calendar_w, cross_w)
    graph = build_graph([node.name for node in nodes], weights)
    return SelectedUniverse(nodes=tuple(nodes), graph=graph)
