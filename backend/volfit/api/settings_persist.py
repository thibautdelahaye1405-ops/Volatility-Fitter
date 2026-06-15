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


def _coerce(model, raw):
    """Validate a persisted blob into ``model``; None on absence or bad data."""
    if not raw:
        return None
    try:
        return model(**raw)
    except Exception as exc:  # noqa: BLE001 — stale/partial blob -> code default
        warnings.warn(f"discarding unreadable saved {model.__name__}: {exc}")
        return None
