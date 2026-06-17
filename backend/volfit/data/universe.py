"""Universe selection: which tickers and expiries the user is working on.

Design intent (ROADMAP Phase 3): the user picks a subset of the tickers and
expiries the providers can serve; that choice is persisted so a session can
be re-opened (and a 20-ticker snapshot command can iterate over it).  A
universe is deliberately *declarative* — a ticker list plus an expiry window
in days — and is resolved against live chains at fetch time, so it stays
valid as expiries roll.

Persistence reuses the `universes(name PK, config_json)` table of the
VolStore schema (volfit.data.store): the dataclass serializes to JSON, which
keeps this module free of any SQL beyond three one-liners.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from volfit.data.store import VolStore


@dataclass(frozen=True)
class Universe:
    """A named selection of tickers, an expiry window, and per-ticker picks.

    `min_days`/`max_days` bound the time-to-expiry (in calendar days from the
    as-of date) of the smiles included in the universe; the defaults keep
    everything from tomorrow out to ten years. `selections` records each
    ticker's expiry selection so it survives save/load: ``None`` means "auto"
    (re-apply the default rule on load), a list of ISO dates means the user's
    custom picks (re-applied where those dates still exist).
    """

    name: str
    tickers: tuple[str, ...]
    min_days: int = 1
    max_days: int = 3650
    selections: dict[str, list[str] | None] = field(default_factory=dict)

    def filter_expiries(self, expiries: list[date], asof: date) -> list[date]:
        """Expiries within the universe's [min_days, max_days] window, sorted."""
        return sorted(
            e for e in expiries if self.min_days <= (e - asof).days <= self.max_days
        )

    def to_config(self) -> dict:
        """JSON-ready representation (inverse of `from_config`)."""
        return {
            "tickers": list(self.tickers),
            "min_days": self.min_days,
            "max_days": self.max_days,
            "selections": self.selections,
        }

    @staticmethod
    def from_config(name: str, config: dict) -> "Universe":
        return Universe(
            name=name,
            tickers=tuple(config["tickers"]),
            min_days=int(config["min_days"]),
            max_days=int(config["max_days"]),
            selections=config.get("selections", {}),
        )


def save_universe(store: VolStore, universe: Universe) -> None:
    """Persist (insert or replace) a universe under its name."""
    store.conn.execute(
        "INSERT INTO universes (name, config_json) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET config_json = excluded.config_json",
        (universe.name, json.dumps(universe.to_config())),
    )
    store.conn.commit()


def load_universe(store: VolStore, name: str) -> Universe | None:
    """Load one universe by name, or None if absent."""
    row = store.conn.execute(
        "SELECT config_json FROM universes WHERE name = ?", (name,)
    ).fetchone()
    return Universe.from_config(name, json.loads(row[0])) if row else None


def list_universes(store: VolStore) -> list[str]:
    """Names of all stored universes, sorted."""
    return [r[0] for r in store.conn.execute("SELECT name FROM universes ORDER BY name")]


#: app_settings key tracking the active named universe (the last one saved or
#: loaded), so a restart restores it as the default selection.
_LAST_UNIVERSE_KEY = "last_universe"


def set_last_universe(store: VolStore, name: str) -> None:
    """Record ``name`` as the active named universe (restored on next startup)."""
    store.save_setting(_LAST_UNIVERSE_KEY, {"name": name})


def get_last_universe(store: VolStore) -> str | None:
    """The active named universe to restore on startup, or None if unset."""
    doc = store.load_setting(_LAST_UNIVERSE_KEY)
    name = doc.get("name") if isinstance(doc, dict) else None
    return name if isinstance(name, str) and name else None


def clear_last_universe(store: VolStore) -> None:
    """Forget the active named universe (e.g. when it is deleted)."""
    store.delete_setting(_LAST_UNIVERSE_KEY)
