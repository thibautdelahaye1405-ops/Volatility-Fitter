"""Forward-mode and market-settings service logic ([REQ 2026-06-12]).

Backs GET/PUT /forwards and GET/PUT /settings/market (volfit.api.routers
.forwards); lives outside volfit.api.service, which is already at the
file-size policy limit. Assembles the per-expiry side-by-side diagnostics —
parity regression vs dividend-model theoretical vs manual override — and
wraps the AppState market-settings accessors with ticker validation so the
routers map every unknown node to a 404 uniformly.

The expiry universe is gated by the parity fits (state.forwards keys), so
within `forwards_payload` the parity block is always populated; ForwardEntry
still allows None there to stay robust if that gating ever loosens.
"""

from __future__ import annotations

from datetime import date

from volfit.api.schemas import (
    ForwardEntry,
    ForwardPolicy,
    ForwardsResponse,
    MarketSettings,
)
from volfit.api.state import AppState, UnknownNodeError


def _check_ticker(state: AppState, ticker: str) -> None:
    """UnknownNodeError (-> 404) for tickers outside the provider universe."""
    if ticker not in state.provider.list_tickers():
        raise UnknownNodeError(f"unknown ticker {ticker!r}")


# --------------------------------------------------------- market settings
def get_market_settings(state: AppState, ticker: str) -> MarketSettings:
    """The ticker's stored rate/dividend settings (defaults if never set)."""
    _check_ticker(state, ticker)
    return state.market_settings(ticker)


def set_market_settings(
    state: AppState, ticker: str, settings: MarketSettings
) -> MarketSettings:
    """Store the ticker's settings; a real change busts all fit caches."""
    _check_ticker(state, ticker)
    return state.set_market_settings(ticker, settings)


# ----------------------------------------------------------- forward modes
def _forward_entry(state: AppState, ticker: str, expiry: date) -> ForwardEntry:
    """One expiry's parity / theoretical / active forward, side by side."""
    iso = expiry.isoformat()
    parity = state.forwards(ticker).get(expiry)
    theo_forward, theo_discount = state.theoretical_forward_for(ticker, expiry)
    policy = state.forward_policy(ticker, iso)
    active = state.resolved_forward(ticker, expiry)
    return ForwardEntry(
        expiry=iso,
        t=state.year_fraction(expiry),
        parityForward=None if parity is None else parity.forward,
        parityDiscount=None if parity is None else parity.discount,
        parityResidualRms=None if parity is None else parity.residual_rms,
        parityNStrikes=None if parity is None else parity.n_strikes,
        parityNOutliers=None if parity is None else parity.n_outliers,
        theoForward=theo_forward,
        theoDiscount=theo_discount,
        mode=policy.mode,
        manualForward=policy.manualForward,
        activeForward=active.forward,
        activeDiscount=active.discount,
        activeSource=active.source,
    )


def forwards_payload(state: AppState, ticker: str) -> ForwardsResponse:
    """Per-expiry forward diagnostics for the whole ladder, nearest first."""
    snapshot = state.snapshot(ticker)  # UnknownNodeError on bad tickers
    entries = [
        _forward_entry(state, ticker, expiry)
        for expiry in sorted(state.forwards(ticker))
    ]
    return ForwardsResponse(
        ticker=ticker,
        spot=snapshot.spot,
        exerciseStyle=snapshot.exercise_style,
        entries=entries,
    )


def apply_forward_policy(
    state: AppState, ticker: str, expiry_iso: str, policy: ForwardPolicy
) -> ForwardEntry:
    """Set one node's forward policy and return its refreshed entry."""
    expiry = state.resolve_expiry(ticker, expiry_iso)  # UnknownNodeError
    state.set_forward_policy(ticker, expiry.isoformat(), policy)
    return _forward_entry(state, ticker, expiry)
