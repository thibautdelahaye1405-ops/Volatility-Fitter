"""Four-parameter sigmoid implied-volatility curve.

    sigma(k) = vol_right + (vol_left - vol_right) * expit(-(k - shift) / width)

A monotone skew curve running from a left-wing level ``vol_left`` down (or
up) to a right-wing level ``vol_right``, centered at ``shift`` with
transition ``width``. It is a quoting/marking convenience — cheap, robust,
and readable — not an arbitrage-free density model: use the model-free
butterfly diagnostics before trading off it, or hand the shape to LQD.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares
from scipy.special import expit


@dataclass(frozen=True)
class SigmoidSmile:
    """Sigmoid smile at one expiry ``t`` (kept so the model is self-pricing)."""

    vol_left: float
    vol_right: float
    shift: float
    width: float
    t: float

    def vol(self, k: np.ndarray | float) -> np.ndarray:
        k_arr = np.asarray(k, dtype=float)
        ramp = expit(-(k_arr - self.shift) / self.width)
        return self.vol_right + (self.vol_left - self.vol_right) * ramp

    def implied_vol(self, k: np.ndarray | float, t: float | None = None) -> np.ndarray:
        """SmileModel interface; ``t`` is accepted for signature parity."""
        return self.vol(k)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Total implied variance w(k) = sigma(k)^2 T."""
        vol = self.vol(k)
        return vol * vol * self.t

    def to_vector(self) -> np.ndarray:
        return np.array([self.vol_left, self.vol_right, self.shift, self.width])


def calibrate_sigmoid(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
) -> SigmoidSmile:
    """Least-squares fit of the sigmoid curve to total-variance quotes.

    Residuals are in implied-vol units (the natural quoting scale). The width
    is optimized in log space to stay positive.
    """
    k = np.asarray(k, dtype=float)
    vol_quotes = np.sqrt(np.asarray(w_quotes, dtype=float) / t)
    sqrt_weights = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))

    def unpack(theta: np.ndarray) -> SigmoidSmile:
        return SigmoidSmile(
            vol_left=theta[0],
            vol_right=theta[1],
            shift=theta[2],
            width=float(np.exp(theta[3])),
            t=t,
        )

    def residuals(theta: np.ndarray) -> np.ndarray:
        return sqrt_weights * (unpack(theta).vol(k) - vol_quotes)

    # Data-driven start: wing levels from the end quotes, center at the
    # vol-midpoint strike, width from the quoted strike span.
    order = np.argsort(k)
    v_lo, v_hi = vol_quotes[order[0]], vol_quotes[order[-1]]
    span = max(k.max() - k.min(), 1e-3)
    theta0 = np.array([v_lo, v_hi, float(np.median(k)), np.log(0.25 * span)])

    result = least_squares(residuals, theta0, method="lm", xtol=1e-15, ftol=1e-15)
    return unpack(result.x)
