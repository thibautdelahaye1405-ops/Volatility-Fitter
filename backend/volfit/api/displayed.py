"""Displayed-fit accessors: read the chosen model from a cached FitRecord.

LQD is always fitted (the analytic backbone), and a non-LQD model choice attaches
a ``DisplayFit`` overlay (volfit.api.fit_models). The Smile Viewer's chart,
diagnostics, table, 3D surface, SSR scenario, density and term-structure read the
*displayed* fit: the overlay's numeric handles/var-swap when one is active, else
the LQD slice's exact closed forms. These accessors centralise that overlay-vs-
LQD branch so every view stays consistent with the selected model. (The graph
universe is the one exception — it needs exact LQD ATM-orthogonal coordinates and
Newton retargeting, so it always reads the LQD fit, not these.)
"""

from __future__ import annotations

from volfit.api.state import FitRecord
from volfit.models.lqd.atm import atm_handles


def displayed_slice(record: FitRecord):
    """The SmileModel the Smile Viewer charts (overlay model or LQD)."""
    return record.display.slice if record.display is not None else record.result.slice


def displayed_atm_vol(record: FitRecord) -> float:
    """ATM vol of the displayed fit (numeric for an overlay, exact for LQD)."""
    if record.display is not None:
        return record.display.handles.atm_vol
    return atm_handles(record.result.slice, record.prepared.t).sigma0


def displayed_skew(record: FitRecord) -> float:
    """ATM skew of the displayed fit (numeric for an overlay, exact for LQD)."""
    if record.display is not None:
        return record.display.handles.skew
    return atm_handles(record.result.slice, record.prepared.t).skew


def displayed_var_swap_w(record: FitRecord) -> float:
    """Var-swap fair total variance of the displayed fit (overlay or LQD)."""
    if record.display is not None:
        return record.display.var_swap_w
    return record.result.slice.var_swap_strike()


def displayed_max_iv_error(record: FitRecord) -> float:
    """Worst per-quote IV error of the displayed fit (overlay or LQD)."""
    if record.display is not None:
        return record.display.max_iv_error
    return record.result.max_iv_error
