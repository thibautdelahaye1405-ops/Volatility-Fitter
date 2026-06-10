"""Common smile-model interface.

Every smile parametrization (LQD slice, SVI, sigmoid, local-vol column)
exposes the same minimal surface so viewers, calibration diagnostics and the
graph layer stay model-agnostic: total implied variance and implied vol on
log-forward-moneyness k = log(K / F).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class SmileModel(Protocol):
    """Anything that can quote total implied variance at log-moneyness k."""

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Total implied variance w(k) = sigma_BS(k)^2 * T."""
        ...

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        """Implied Black volatility at expiry t."""
        ...
