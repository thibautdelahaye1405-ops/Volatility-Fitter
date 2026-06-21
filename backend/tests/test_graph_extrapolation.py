"""Production graph extrapolation — selected-universe construction (plan Phase 1).

The production graph is built over the user-selected lit+dark nodes only
(plan Amendment C), never the full provider universe. These tests pin that
boundary: selected expiries in, unselected out; lit/dark respected; an empty
selection degrades to an empty graph rather than crashing.

Runs over the synthetic provider (ALPHA/BETA/GAMMA, no network).
"""

from datetime import date

import pytest

from volfit.api.graph_extrapolation import build_selected_universe
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def state() -> AppState:
    return AppState(reference_date=REF_DATE)


def _isos(state: AppState, ticker: str) -> list[str]:
    return [e.isoformat() for e in sorted(state.selected_expiries(ticker))]


def test_universe_spans_active_tickers_x_selected_expiries(state):
    universe = build_selected_universe(state)
    expected = sum(len(state.selected_expiries(tk)) for tk in state.active_tickers())
    assert len(universe.nodes) == expected
    assert universe.graph is not None
    # Every node name is in the graph and addressable.
    for node in universe.nodes:
        assert universe.node_index(node.name) >= 0


def test_selected_set_excludes_unselected_provider_nodes(state):
    """Narrowing a ticker's selection drops the unselected expiries from the graph."""
    tk = state.active_tickers()[0]
    available = state.available_expiries(tk)
    assert len(available) >= 2
    keep = available[:2]
    state.set_expiries(tk, keep)

    universe = build_selected_universe(state)
    iso_keep = {d.isoformat() for d in keep}
    tk_nodes = [n for n in universe.nodes if n.ticker == tk]
    assert {n.expiry for n in tk_nodes} == iso_keep


def test_lit_dark_split_is_respected(state):
    tk = state.active_tickers()[0]
    iso = _isos(state, tk)[0]
    state.set_node_lit(tk, iso, False)  # darken one node

    universe = build_selected_universe(state)
    assert (tk, iso) in universe.dark_names
    assert (tk, iso) not in universe.lit_names
    # Everything else stays lit by default.
    assert len(universe.lit_names) == len(universe.nodes) - 1


def test_dark_only_selection_still_builds_nodes(state):
    """A universe where every selected node is dark must still build a graph
    (dark nodes are extrapolation targets, not 'out of graph')."""
    for tk in state.active_tickers():
        for iso in _isos(state, tk):
            state.set_node_lit(tk, iso, False)

    universe = build_selected_universe(state)
    assert universe.graph is not None
    assert len(universe.dark_names) == len(universe.nodes)
    assert universe.lit_names == ()


def test_empty_selection_yields_empty_graph_no_crash(state):
    state._active_tickers = []  # no active tickers -> no selectable nodes
    universe = build_selected_universe(state)
    assert universe.nodes == ()
    assert universe.graph is None
    with pytest.raises(KeyError):
        universe.node_index(("ALPHA", "2026-07-17"))


def test_two_ticker_three_expiry_selection_yields_six_nodes(state):
    """Acceptance: a 2x3 selection yields exactly 6 nodes regardless of how many
    expiries the provider exposes."""
    keep_tickers = state.active_tickers()[:2]
    for tk in list(state.active_tickers()):
        if tk not in keep_tickers:
            state.remove_ticker(tk)
    for tk in keep_tickers:
        state.set_expiries(tk, state.available_expiries(tk)[:3])

    universe = build_selected_universe(state)
    assert len(universe.nodes) == 6
    assert {n.ticker for n in universe.nodes} == set(keep_tickers)
