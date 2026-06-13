"""Schemas for universe management (add/remove tickers, named universes).

The universe-selection screen (frontend Universe tab) drives these: search
the provider's catalog for a symbol, add/remove it from the active universe,
and save/load named universes (the SQLite persistence of
volfit.data.universe). camelCase per the frontend contract.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class SymbolMatch(BaseModel):
    """One symbol-search hit (mirror of volfit.data.provider.SymbolMatch)."""

    symbol: str
    name: str = ""
    type: str = ""
    exchange: str = ""


class SymbolSearchResponse(BaseModel):
    """Candidate symbols for a free-text query (symbol or company name)."""

    query: str
    matches: list[SymbolMatch]


class AddTickerRequest(BaseModel):
    """Add one symbol to the active universe."""

    symbol: str = Field(min_length=1, max_length=20)


class SavedUniversesResponse(BaseModel):
    """Named universes stored on disk (empty when no store is configured)."""

    names: list[str]
    storeEnabled: bool  # False when VOLFIT_DB is unset — save/load disabled
