"""Displayed-model overlay fitting — re-export shim.

The pure overlay builder moved to volfit.models.display so the fit-pool worker
processes (volfit.calib.fit_task, spawned by volfit.api.fit_pool) can import it
without executing this package's __init__ (which builds the whole FastAPI
router graph). This module keeps the historical import path for the API layer
and the test suite; new code should import volfit.models.display directly.
"""

from volfit.models.display import (
    OVERLAY_MODELS,
    DisplayFit,
    _max_iv_error,
    build_display_fit,
)

__all__ = ["OVERLAY_MODELS", "DisplayFit", "_max_iv_error", "build_display_fit"]
