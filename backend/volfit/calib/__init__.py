"""Calibration objectives, no-arbitrage constraints and time conventions."""

from volfit.calib.calendar import CAL_STRIDE, calendar_grid_indices, calendar_violation
from volfit.calib.event_time import Event, EventClock

__all__ = [
    "CAL_STRIDE",
    "Event",
    "EventClock",
    "ExpiryQuotes",
    "SurfaceFit",
    "calendar_grid_indices",
    "calendar_violation",
    "calibrate_surface",
]

#: ``surface`` is imported lazily: it depends on volfit.models.lqd.calibrate,
#: which now imports volfit.calib.band. Eagerly importing surface here would
#: form an import cycle whenever lqd.calibrate is imported before this package
#: finishes loading (e.g. ``import volfit.models.lqd.calibrate`` first, as the
#: perf suite does). PEP 562 module __getattr__ defers it, breaking the cycle.
_LAZY = {"ExpiryQuotes", "SurfaceFit", "calibrate_surface"}


def __getattr__(name: str):
    if name in _LAZY:
        from volfit.calib import surface

        return getattr(surface, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
