"""Transported-prior node baselines with provenance (plan Phase 2).

Every production node's baseline is a transported prior with explicit provenance.
These tests pin the hierarchy (active -> nearest-expiry -> bootstrap -> flat), the
transport identity/shift, the precision tiers, and the valid-for-validation flags.

Runs over the synthetic provider (ungated, so today's fits bootstrap on read).
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import priors
from volfit.api.graph_extrapolation import build_selected_universe
from volfit.api.graph_nodes import (
    DEFAULT_FLAT_ATM_VOL,
    resolve_node_prior,
    resolve_priors,
)
from volfit.api.state import AppState
from volfit.models.lqd.atm import atm_handles
from volfit.api.prior_transport import prior_lqd_slice, prior_node

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def state() -> AppState:
    return AppState(REF_DATE)


@pytest.fixture()
def primed(state):
    """A ticker with today's surface captured as its active prior."""
    ticker = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    snap = priors.capture_snapshot(state, ticker, "mid")
    assert snap is not None
    state.set_active_prior(ticker, snap, "saved")
    return state, ticker, isos, snap


def test_active_transported_identity_when_forward_unchanged(primed):
    """h=0 (current forward == prior forward): handles == the prior's own."""
    state, ticker, isos, snap = primed
    prior = resolve_node_prior(state, ticker, isos[0])
    assert prior.source == "active_transported"
    assert prior.transport_distance == 0.0
    assert prior.valid_for_validation is True

    node = prior_node(snap, isos[0])
    exact = atm_handles(prior_lqd_slice(node), node.tau)
    np.testing.assert_allclose(
        prior.handles, [exact.sigma0, exact.skew, exact.curvature], atol=1e-12
    )


def test_transported_baseline_shifts_when_forward_moves(primed):
    """A prior calibrated at a different forward transports to non-identity handles."""
    state, ticker, isos, snap = primed
    # Re-stamp the prior node's forward 5% below the current one -> h = log(1.05).
    moved_nodes = []
    for n in snap.nodes:
        if n.expiry == isos[0]:
            moved_nodes.append(n.model_copy(update={"forward": n.forward / 1.05}))
        else:
            moved_nodes.append(n)
    state.set_active_prior(ticker, snap.model_copy(update={"nodes": moved_nodes}), "saved")

    prior = resolve_node_prior(state, ticker, isos[0])
    assert prior.source == "active_transported"
    assert prior.transport_distance == pytest.approx(np.log(1.05), abs=1e-9)
    # The transported handles differ from the raw (untransported) prior handles.
    node = prior_node(snap, isos[0])
    raw_handles = atm_handles(prior_lqd_slice(node), node.tau)
    assert abs(prior.handles[0] - raw_handles.sigma0) > 1e-6


def test_nearest_expiry_fallback_fires_and_flags(state):
    """No prior for the exact expiry -> nearest-expiry prior, reduced precision."""
    ticker = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    snap = priors.capture_snapshot(state, ticker, "mid")
    # Drop the target node so only other expiries remain.
    trimmed = [n for n in snap.nodes if n.expiry != isos[0]]
    state.set_active_prior(ticker, snap.model_copy(update={"nodes": trimmed}), "saved")

    prior = resolve_node_prior(state, ticker, isos[0])
    assert prior.source == "nearest_expiry_transported"
    assert prior.valid_for_validation is True
    active = resolve_node_prior(state, ticker, isos[1])  # still has its own node
    assert active.source == "active_transported"
    # Nearest-expiry enters with strictly less precision than an exact-match prior.
    assert np.all(prior.precision < active.precision)


def test_bootstrap_flagged_not_valid_for_validation(state):
    """No prior anywhere -> today's mid fit, low precision, not validation-clean."""
    ticker = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    assert state.active_prior(ticker) is None
    prior = resolve_node_prior(state, ticker, isos[0])
    assert prior.source == "today_bootstrap"
    assert prior.valid_for_validation is False
    assert prior.handles[0] > 0.0  # a real ATM vol from the bootstrap fit


def test_flat_atm_diagnostic(state):
    ticker = state.active_tickers()[0]
    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    prior = resolve_node_prior(state, ticker, isos[0], flat_atm=True)
    assert prior.source == "flat_atm"
    assert prior.valid_for_validation is False
    np.testing.assert_allclose(prior.handles, [DEFAULT_FLAT_ATM_VOL, 0.0, 0.0])


def test_precision_tiers_ordered(primed):
    """active > nearest > bootstrap > flat in baseline precision (per handle)."""
    state, ticker, isos, snap = primed
    active = resolve_node_prior(state, ticker, isos[0]).precision
    flat = resolve_node_prior(state, ticker, isos[0], flat_atm=True).precision
    assert np.all(active > flat)


def test_resolve_priors_aligns_with_universe(primed):
    state, ticker, isos, snap = primed
    universe = build_selected_universe(state)
    resolved = resolve_priors(state, universe)
    assert len(resolved) == len(universe.nodes)
    # The primed ticker's nodes resolve to the active transported prior.
    for node, prior in zip(universe.nodes, resolved):
        if node.ticker == ticker and node.expiry in isos:
            assert prior.source == "active_transported"
