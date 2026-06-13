"""Universe-management service: enumerate, search, edit, save/load.

Backs the universe-selection screen. The active universe lives on AppState
(the curated ticker set); named universes persist to the VolStore `universes`
table (volfit.data.universe) when a store is configured (VOLFIT_DB), and are a
no-op otherwise. Pure functions over AppState returning pydantic models, like
the rest of volfit.api.
"""

from __future__ import annotations

from datetime import date

from volfit.api.schemas import ExpiryInfo, UniverseResponse
from volfit.api.schemas_universe import (
    ExpiryOption,
    ExpiryPickerResponse,
    SavedUniversesResponse,
    SymbolMatch,
    SymbolSearchResponse,
)
from volfit.api.state import AppState, UnknownNodeError
from volfit.data.expiries import classify_expiry
from volfit.data.expiry_select import expiry_bucket
from volfit.data.store import VolStore
from volfit.data.universe import (
    Universe,
    list_universes,
    load_universe,
    save_universe,
)


def universe_payload(state: AppState) -> UniverseResponse:
    """Active tickers and their expiry ladders (with expiry-type tags)."""
    tickers = state.active_tickers()
    expiries = {
        ticker: [
            ExpiryInfo(
                expiry=expiry.isoformat(),
                t=state.year_fraction(expiry),
                expiryType=classify_expiry(expiry, state.reference_date),
            )
            for expiry in sorted(state.forwards(ticker))
        ]
        for ticker in tickers
    }
    return UniverseResponse(
        asOf=state.reference_date.isoformat(), tickers=tickers, expiries=expiries
    )


def search(state: AppState, query: str, limit: int) -> SymbolSearchResponse:
    """Provider symbol search for the add-ticker picker."""
    matches = state.provider.search_symbols(query, limit)
    return SymbolSearchResponse(
        query=query,
        matches=[
            SymbolMatch(symbol=m.symbol, name=m.name, type=m.type, exchange=m.exchange)
            for m in matches
        ],
    )


def add_ticker(state: AppState, symbol: str) -> UniverseResponse:
    """Add a ticker (validated by AppState) and return the new universe."""
    state.add_ticker(symbol)  # raises UnknownNodeError on a bad symbol
    return universe_payload(state)


def remove_ticker(state: AppState, symbol: str) -> UniverseResponse:
    """Remove a ticker and return the new universe."""
    state.remove_ticker(symbol)  # UnknownNodeError / ValueError (last ticker)
    return universe_payload(state)


# ----------------------------------------------------- per-ticker expiries
def expiry_picker(state: AppState, ticker: str) -> ExpiryPickerResponse:
    """Full available expiry list of a ticker with current selection flags."""
    available = state.available_expiries(ticker)  # UnknownNodeError if unknown
    selected = set(state.selected_expiries(ticker))
    ref = state.reference_date
    options = [
        ExpiryOption(
            expiry=e.isoformat(),
            t=state.year_fraction(e),
            days=(e - ref).days,
            bucket=expiry_bucket(e, ref),
            selected=e in selected,
        )
        for e in available
    ]
    return ExpiryPickerResponse(
        ticker=ticker, asOf=ref.isoformat(), mode=state.selection_mode(ticker), expiries=options
    )


def set_expiries(state: AppState, ticker: str, iso_dates: list[str]) -> ExpiryPickerResponse:
    """Replace a ticker's selected expiries (custom mode)."""
    state.set_expiries(ticker, [date.fromisoformat(s) for s in iso_dates])  # ValueError if empty
    return expiry_picker(state, ticker)


def reset_expiries(state: AppState, ticker: str) -> ExpiryPickerResponse:
    """Re-apply the default selection rule to a ticker (auto mode)."""
    state.reset_expiries(ticker)
    return expiry_picker(state, ticker)


# --------------------------------------------------------- named universes
def saved(state: AppState) -> SavedUniversesResponse:
    """Names of the stored universes (empty list when no store)."""
    if state.store_path is None:
        return SavedUniversesResponse(names=[], storeEnabled=False)
    with VolStore(state.store_path) as store:
        return SavedUniversesResponse(names=list_universes(store), storeEnabled=True)


def save_current(state: AppState, name: str) -> SavedUniversesResponse:
    """Persist the active ticker set + per-ticker expiry selection under ``name``.

    Auto tickers store ``None`` (re-resolve the default rule on load); custom
    tickers store their explicit ISO picks (re-applied where still listed).
    """
    if state.store_path is None:
        raise ValueError("fit-history store not configured (set VOLFIT_DB)")
    if not name.strip():
        raise ValueError("universe name must not be empty")
    tickers = state.active_tickers()
    selections: dict[str, list[str] | None] = {}
    for t in tickers:
        if state.selection_mode(t) == "custom":
            selections[t] = [e.isoformat() for e in state.selected_expiries(t)]
        else:
            selections[t] = None
    with VolStore(state.store_path) as store:
        save_universe(
            store, Universe(name=name.strip(), tickers=tuple(tickers), selections=selections)
        )
        return SavedUniversesResponse(names=list_universes(store), storeEnabled=True)


def load_saved(state: AppState, name: str) -> UniverseResponse:
    """Apply a saved universe (tickers + per-ticker selection) to the session."""
    if state.store_path is None:
        raise ValueError("fit-history store not configured (set VOLFIT_DB)")
    with VolStore(state.store_path) as store:
        universe = load_universe(store, name)
    if universe is None:
        raise UnknownNodeError(f"no saved universe named {name!r}")
    state.set_active_tickers(list(universe.tickers))  # all start on the default rule
    for ticker, picks in (universe.selections or {}).items():
        if picks:  # custom: re-apply explicit picks where the dates still exist
            try:
                state.set_expiries(ticker, [date.fromisoformat(s) for s in picks])
            except (ValueError, KeyError):
                pass  # ticker dropped or every saved date has expired -> keep auto
    return universe_payload(state)


def delete_saved(state: AppState, name: str) -> SavedUniversesResponse:
    """Delete a saved universe (no-op if absent)."""
    if state.store_path is None:
        raise ValueError("fit-history store not configured (set VOLFIT_DB)")
    with VolStore(state.store_path) as store:
        store.conn.execute("DELETE FROM universes WHERE name = ?", (name,))
        store.conn.commit()
        return SavedUniversesResponse(names=list_universes(store), storeEnabled=True)
