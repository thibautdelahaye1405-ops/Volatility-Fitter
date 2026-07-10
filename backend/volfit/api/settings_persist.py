"""Persist the global Fit + Options defaults to the VolStore ([REQ 2026-06-15]).

The Options-tab "Save as default" button writes the current settings here so a
backend restart restores them instead of the built-in code defaults. Storage is
the opt-in app store (AppState.store_path, env VOLFIT_DB) — the very same
SQLite file that already holds named universes and fit history — under two keys
of the `app_settings` table.

Everything is best-effort: without a store path it is a silent no-op, and a
malformed/old persisted blob (e.g. saved before a schema field was added) is
discarded rather than crashing startup — Pydantic fills missing fields with
their defaults and rejects the rest, so a partial restore degrades gracefully.
"""

from __future__ import annotations

import warnings

from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.data.store import VolStore

FIT_KEY = "fit_settings"
OPTIONS_KEY = "options_settings"
GRAPH_EDGES_KEY = "graph_edges"
GRAPH_BLOCK_RULE_KEY = "graph_block_rule"
GRAPH_IDIO_KEY = "graph_idio_history"


def load_defaults(
    store_path,
) -> tuple[FitSettings | None, OptionsSettings | None]:
    """Read the saved Fit/Options defaults (each None when absent/unreadable)."""
    if store_path is None:
        return None, None
    try:
        with VolStore(store_path) as store:
            fit_raw = store.load_setting(FIT_KEY)
            opt_raw = store.load_setting(OPTIONS_KEY)
    except Exception as exc:  # noqa: BLE001 — restore must never break startup
        warnings.warn(f"settings-default load failed: {exc}")
        return None, None
    return _coerce(FitSettings, fit_raw), _coerce(OptionsSettings, opt_raw)


def save_defaults(store_path, fit: FitSettings, options: OptionsSettings) -> bool:
    """Persist the current Fit + Options settings; False when no store is set."""
    if store_path is None:
        return False
    with VolStore(store_path) as store:
        store.save_setting(FIT_KEY, fit.model_dump())
        store.save_setting(OPTIONS_KEY, options.model_dump())
    return True


def clear_defaults(store_path) -> bool:
    """Drop both saved defaults; False when no store is set."""
    if store_path is None:
        return False
    with VolStore(store_path) as store:
        store.delete_setting(FIT_KEY)
        store.delete_setting(OPTIONS_KEY)
    return True


def has_defaults(store_path) -> bool:
    """True when either default has been saved (drives the UI "saved" badge)."""
    if store_path is None:
        return False
    try:
        with VolStore(store_path) as store:
            return (
                store.load_setting(FIT_KEY) is not None
                or store.load_setting(OPTIONS_KEY) is not None
            )
    except Exception:  # noqa: BLE001 — status probe is advisory
        return False


def load_graph_edges(store_path) -> list[dict]:
    """Read the persisted per-edge graph overrides (plan Phase 7); [] when absent
    or unreadable. Stored as ``{"edges": [...]}`` under one app_settings key."""
    if store_path is None:
        return []
    try:
        with VolStore(store_path) as store:
            raw = store.load_setting(GRAPH_EDGES_KEY)
    except Exception as exc:  # noqa: BLE001 — restore must never break startup
        warnings.warn(f"graph-edges load failed: {exc}")
        return []
    return list(raw.get("edges", [])) if raw else []


def save_graph_edges(store_path, edges: list[dict]) -> bool:
    """Persist the per-edge graph overrides; False when no store is set."""
    if store_path is None:
        return False
    with VolStore(store_path) as store:
        store.save_setting(GRAPH_EDGES_KEY, {"edges": edges})
    return True


def load_graph_block_rule(store_path) -> dict | None:
    """Read the persisted ticker-block rule (the sparse block-matrix editor);
    None when absent or unreadable. Stored VERBATIM — the rule must round-trip
    exactly as the user wrote it, its expansion lives under GRAPH_EDGES_KEY."""
    if store_path is None:
        return None
    try:
        with VolStore(store_path) as store:
            return store.load_setting(GRAPH_BLOCK_RULE_KEY)
    except Exception as exc:  # noqa: BLE001 — restore must never break startup
        warnings.warn(f"graph-block-rule load failed: {exc}")
        return None


def save_graph_block_rule(store_path, rule: dict | None) -> bool:
    """Persist the ticker-block rule verbatim (None DELETES it — the edge list
    is hand-edited or cleared); False when no store is set."""
    if store_path is None:
        return False
    with VolStore(store_path) as store:
        if rule is None:
            store.delete_setting(GRAPH_BLOCK_RULE_KEY)
        else:
            store.save_setting(GRAPH_BLOCK_RULE_KEY, rule)
    return True


def load_graph_idio(store_path) -> dict | None:
    """Read the persisted graph innovation history (the idio band-floor input,
    volfit.graph.idio); None when absent or unreadable."""
    if store_path is None:
        return None
    try:
        with VolStore(store_path) as store:
            return store.load_setting(GRAPH_IDIO_KEY)
    except Exception as exc:  # noqa: BLE001 — restore must never break startup
        warnings.warn(f"graph-idio-history load failed: {exc}")
        return None


def save_graph_idio(store_path, blob: dict) -> bool:
    """Persist the graph innovation history; False when no store is set."""
    if store_path is None:
        return False
    with VolStore(store_path) as store:
        store.save_setting(GRAPH_IDIO_KEY, blob)
    return True


def _migrate_options(raw: dict) -> dict:
    """Forward-migrate a persisted OptionsSettings blob (a copy is returned).

    Pre-mode blobs (saved before ``priorPersistenceMode`` existed) carried only the
    binary ``autoLoadPrior`` switch. Map it to the equivalent mode so a restored
    desk keeps its EXACT prior behaviour (the legacy strike-gap anchor) rather than
    jumping to the new ``hybrid`` code default. New installs have no blob, so they
    are untouched and pick up the recommended ``hybrid`` default.
    """
    raw = dict(raw)
    if "priorPersistenceMode" not in raw:
        raw["priorPersistenceMode"] = "strike_gap" if raw.get("autoLoadPrior") else "off"
    return raw


def _coerce(model, raw):
    """Validate a persisted blob into ``model``; None on absence or bad data."""
    if not raw:
        return None
    if model is OptionsSettings:
        raw = _migrate_options(raw)
    try:
        return model(**raw)
    except Exception as exc:  # noqa: BLE001 — stale/partial blob -> code default
        warnings.warn(f"discarding unreadable saved {model.__name__}: {exc}")
        return None
