"""Quote-derived fit uncertainty — the smile chart's error bars.

Every committed calibration now retains its solver's solution Jacobian
(the ``solver_diag`` side-channel is requested unconditionally), so the
observation filter's measurement extraction (Note 15 §4) can price the fit's
OWN uncertainty even with the filter off: R_x = G (JᵀWJ+Λ)⁺ Gᵀ with the
bid-ask half-spread as the stated per-quote noise — "error bars from the
quotes". The per-handle standard deviations are cached per fit-cache key at
commit; a record without a stored measurement (an entry committed before
this feature) degrades to the factors route lazily on read.

Advisory throughout: never raises, never affects a calibration — exactly the
commit-hook contract the filter follows.
"""

from __future__ import annotations

import threading

import numpy as np

from volfit.api.state import AppState

_ATTR = "_fit_uncertainty"  # AppState side-dict: fit-cache key -> FilterMeasurement
_lock = threading.Lock()


def _cache(state: AppState) -> dict:
    cache = getattr(state, _ATTR, None)
    if cache is None:
        with _lock:  # concurrent job threads: don't lose a freshly attached dict
            cache = getattr(state, _ATTR, None)
            if cache is None:
                cache = {}
                setattr(state, _ATTR, cache)
    return cache


def store(
    state: AppState, ticker: str, iso: str, fit_mode: str, key: tuple,
    record, solver_diag: dict | None,
) -> None:
    """Compute + cache the committed fit's handle measurement (never raises)."""
    try:
        from volfit.api.observation_filter import _measurement

        _cache(state)[key] = _measurement(state, ticker, iso, record, solver_diag)
    except Exception:  # noqa: BLE001 — error bars must never break a calibration
        pass


def handle_stds(
    state: AppState, ticker: str, iso: str, fit_mode: str
) -> tuple[float, float, float] | None:
    """(σ_atm, σ_skew, σ_curv) of the node's DISPLAYED calibration, or None.

    Keyed by the calibrated pointer (the frozen fit the viewer shows, exactly
    like the smile payload), so a stale node reports the uncertainty of the
    fit on screen, not of a hypothetical refit."""
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    if ptr is None:
        return None
    meas = _cache(state).get(ptr[0])
    if meas is None:  # committed before this feature: factors route, lazily
        record = state.get_fit(ptr[0])
        if record is None:
            return None
        try:
            from volfit.api.observation_filter import _measurement

            meas = _measurement(state, ticker, iso, record, None)
        except Exception:  # noqa: BLE001 — advisory read
            return None
        _cache(state)[ptr[0]] = meas
    cov = np.asarray(meas.cov, dtype=float)
    if cov.shape != (3, 3) or not np.all(np.isfinite(np.diag(cov))):
        return None
    return tuple(float(np.sqrt(max(cov[i, i], 0.0))) for i in range(3))
