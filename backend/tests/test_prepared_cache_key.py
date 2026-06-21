"""Stage 2 — prepared-quote cache invalidation is content-precise + ticker-scoped.

The de-Americanized, inverted quotes (the seconds-long binomial inversion on an
American chain) are memoized on a content-digest key (``service._prepared_key``).
The contract the digest must honour, per
Docs/deamericanization_calibration_speed_note.md §7:

  - Tuning a fit-only hyperparameter (grid size, roughness, var-swap, calendar,
    optimizer tolerances, display settings) must NOT invalidate prepared quotes.
  - A change to a real de-Am input (raw chain, resolved forward, dividend
    schedule, the event/variance clock, the as-of date) MUST invalidate them.
  - One ticker's forward edit must NOT invalidate another ticker's prepared
    quotes (the old global ``forwards_version`` did exactly that).

These assert the KEY rather than re-running de-Am, so they are fast and read as
an explicit invalidation table.
"""

from __future__ import annotations

from datetime import date

from volfit.api import service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"
OTHER = "BETA"


def _state() -> AppState:
    return AppState(REF_DATE)


def _key(state: AppState, ticker: str, expiry: date) -> tuple:
    """Resolve the prepared inputs the way ``prepared_quotes`` does, then key."""
    forward = state.resolved_forward(ticker, expiry)
    cash = state.cash_dividend_schedule(ticker, expiry, forward.forward)
    t_cal = state.year_fraction(expiry)
    tau = service.variance_time(state, ticker, expiry, t_cal)
    return service._prepared_key(state, ticker, expiry.isoformat(), forward, cash, t_cal, tau)


def _expiry(state: AppState, ticker: str = TICKER) -> date:
    return sorted(state.forwards(ticker))[1]


# -- fit-only changes must NOT re-key (the headline Stage 2 win) --------------


def test_fit_settings_change_does_not_invalidate():
    state = _state()
    exp = _expiry(state)
    k0 = _key(state, TICKER, exp)
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"regLambda": fs.regLambda * 3 + 1e-9}))
    assert _key(state, TICKER, exp) == k0


def test_fit_only_options_change_does_not_invalidate():
    """Grid density / roughness / var-swap / calendar are LV-fit knobs that do
    not touch quote prep — they must not re-run de-Am."""
    state = _state()
    exp = _expiry(state)
    k0 = _key(state, TICKER, exp)
    opts = state.options()
    state.set_options(
        opts.model_copy(
            update={
                "gridXNodes": opts.gridXNodes + 5,
                "gridRegLambda": opts.gridRegLambda * 2 + 1e-9,
                "varSwapWeightPct": opts.varSwapWeightPct + 1.0,
                "calendarWeight": opts.calendarWeight + 1.0,
            }
        )
    )
    assert _key(state, TICKER, exp) == k0


# -- real de-Am-input changes MUST re-key ------------------------------------


def test_fresh_chain_invalidates():
    state = _state()
    exp = _expiry(state)
    k0 = _key(state, TICKER, exp)
    state.bump_data_version(TICKER)  # a fresh options fetch
    assert _key(state, TICKER, exp) != k0


def test_event_clock_change_invalidates():
    """Toggling the event variance clock changes tau, hence the reported IV
    band in PreparedQuotes — it must re-key."""
    state = _state()
    exp = _expiry(state)
    opts = state.options()
    state.set_options(opts.model_copy(update={"eventsEnabled": True}))
    state.set_events(TICKER, [service_event(exp)])
    k_on = _key(state, TICKER, exp)
    state.set_options(state.options().model_copy(update={"eventsEnabled": False}))
    assert _key(state, TICKER, exp) != k_on


def service_event(expiry: date):
    """A single event a few days before the expiry (variance-clock weight)."""
    from volfit.api.schemas import EventSpec

    t = (expiry - REF_DATE).days / 365.0
    return EventSpec(label="E", time=max(t * 0.5, 1e-3), weight=2.0)


def test_as_of_change_invalidates():
    state = _state()
    exp = _expiry(state)
    k0 = _key(state, TICKER, exp)
    state.reference_date = date(2026, 6, 9)  # an as-of switch
    assert _key(state, TICKER, exp) != k0


# -- ticker scoping (the global-forwards-version bug) ------------------------


def test_other_ticker_forward_change_does_not_invalidate():
    """A forward-policy edit on BETA must leave ALPHA's prepared key untouched.
    The old global ``forwards_version`` re-keyed every ticker on any edit."""
    state = _state()
    exp_a = _expiry(state, TICKER)
    k_a = _key(state, TICKER, exp_a)

    exp_b = _expiry(state, OTHER)
    pol = state.forward_policy(OTHER, exp_b.isoformat())
    state.set_forward_policy(
        OTHER, exp_b.isoformat(), pol.model_copy(update={"mode": "manual", "manualForward": 123.0})
    )
    assert _key(state, TICKER, exp_a) == k_a
