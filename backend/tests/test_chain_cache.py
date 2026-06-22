"""Per-(ticker,expiry) chain-cache reconciliation (ROADMAP perf #3B).

A changed expiry selection no longer re-pulls the whole ladder: deselecting (or
re-selecting a subset of) the cached expiries prunes the cached snapshot in place
— no provider fetch, and surviving nodes keep their warm fits. Only a genuinely
new expiry forces a full atomic re-fetch (so the chain stays one consistent-instant
observation).
"""

from __future__ import annotations

from datetime import date

from volfit.api.service import fit_key, fit_or_get
from volfit.api.state import AppState
from volfit.data.provider import SyntheticProvider

REF = date(2026, 6, 20)


class CountingProvider(SyntheticProvider):
    """SyntheticProvider that counts chain fetches."""

    def __init__(self) -> None:
        super().__init__(REF)
        self.fetches = 0

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        self.fetches += 1
        return super().fetch_chain(ticker, expiries, as_of)


def _setup():
    prov = CountingProvider()
    state = AppState(REF, provider=prov)
    tk = state.active_tickers()[0]
    exps = sorted(state.available_expiries(tk))
    assert len(exps) >= 4
    return prov, state, tk, exps


def test_subset_reselect_does_not_refetch_and_keeps_warm_fits():
    prov, state, tk, exps = _setup()
    state.set_expiries(tk, exps[:3])
    snap = state.snapshot(tk)  # fetch #1
    assert set(snap.expiries()) == set(exps[:3])
    base = prov.fetches
    assert base >= 1

    iso0 = exps[0].isoformat()
    rec = fit_or_get(state, tk, iso0, "mid")  # warm a surviving node's fit
    key_before = fit_key(state, tk, iso0, "mid")

    # Deselect one -> subset of the cached chain -> prune, NO re-fetch.
    state.set_expiries(tk, exps[:2])
    snap2 = state.snapshot(tk)
    assert prov.fetches == base  # the win: the ladder was not re-pulled
    assert set(snap2.expiries()) == set(exps[:2])
    # The surviving node's fit key is unchanged -> its warm fit is reused.
    assert fit_key(state, tk, iso0, "mid") == key_before
    assert fit_or_get(state, tk, iso0, "mid") is rec
    # Forwards pruned to the new selection (no deselected expiry leaks through).
    assert set(state.forwards(tk)) <= set(exps[:2])


def test_adding_a_new_expiry_forces_atomic_refetch():
    prov, state, tk, exps = _setup()
    state.set_expiries(tk, exps[:2])
    state.snapshot(tk)  # fetch #1
    base = prov.fetches
    # Add expiries absent from the cached chain -> full atomic re-fetch.
    state.set_expiries(tk, exps[:4])
    snap = state.snapshot(tk)
    assert prov.fetches > base
    assert set(snap.expiries()) == set(exps[:4])
