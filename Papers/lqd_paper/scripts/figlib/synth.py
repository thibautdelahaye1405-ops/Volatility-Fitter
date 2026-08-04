"""Synthetic constructions behind the non-market figures.

Everything is deterministic and closed-form defined; fits go through the
production ``calibrate_slice``:

* the constant-speed (logistic) toy solved to exactly 20% ATM at 6 months
  (figures F1/F2, the exact-solution audit F3 uses the same family);
* the double-hump event mixture from the note lineage (m1/m2 chosen so the
  50/50 lognormal mixture has unit mean) fitted at N = 16 and N = 6
  (figures F10/F11);
* a 40-quote SSVI-shaped strip used as the timing workload (macro block).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.optimize import brentq
from scipy.special import expit
from scipy.stats import norm

from volfit.core.black import implied_total_variance
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import CalibrationResult, calibrate_slice
from volfit.models.lqd.quadrature import LQDSlice, build_slice

TOY_EXPIRY = 0.5
TOY_ATM_VOL = 0.20

# Double-hump mixture: 50/50 lognormal mixture with sigma = 5% per regime;
# the means satisfy 0.5 e^{m1+s^2/2} + 0.5 e^{m2+s^2/2} = 1 (unit mean).
DH_EXPIRY = 30.0 / 365.0
DH_MEANS = (-0.10075573, 0.08924427)
DH_SIGMA = 0.05
DH_ORDER_HIGH = 16
DH_ORDER_LOW = 6
# Production default ridge (regLambda 1e-6, regPower 1.0, n >= 4): with it the
# N = 16 fit recovers exactly two modes (-0.099 / +0.088 vs true
# -0.101 / +0.089); weaker ridges ring (4 shallow modes at lam <= 1e-7).
DH_REG = 1e-6
DH_REG_POWER = 1.0


@dataclass(frozen=True)
class Toy:
    """The constant-speed slice solved to an exact ATM vol."""

    scale: float
    slice: LQDSlice
    expiry: float
    atm_vol: float


@lru_cache(maxsize=1)
def constant_speed_toy() -> Toy:
    """Solve the one-dial logistic family to exactly 20% ATM at 6 months."""

    def atm_error(log_scale: float) -> float:
        slice_ = build_slice(LQDParams(log_scale, log_scale, np.zeros(5)))
        return float(slice_.implied_vol(0.0, TOY_EXPIRY)) - TOY_ATM_VOL

    log_scale = brentq(atm_error, np.log(0.01), np.log(0.60), xtol=1e-14)
    return Toy(
        scale=float(np.exp(log_scale)),
        slice=build_slice(LQDParams(log_scale, log_scale, np.zeros(5))),
        expiry=TOY_EXPIRY,
        atm_vol=TOY_ATM_VOL,
    )


def mode_slices(amplitude: float = 0.10) -> list[tuple[int, LQDSlice]]:
    """Switch on a_2 / a_3 / a_4 = ``amplitude`` one at a time on the toy."""
    toy = constant_speed_toy()
    log_scale = float(np.log(toy.scale))
    out = []
    for degree in (2, 3, 4):
        coeffs = np.zeros(5)
        coeffs[degree - 2] = amplitude
        out.append((degree, build_slice(LQDParams(log_scale, log_scale, coeffs))))
    return out


# ------------------------------------------------------------- double-hump
def mixture_call(k: np.ndarray) -> np.ndarray:
    """Closed-form normalized calls of the 50/50 double-hump mixture."""
    k = np.asarray(k, dtype=float)
    call = np.zeros_like(k)
    for mean in DH_MEANS:
        call += 0.5 * (
            np.exp(mean + 0.5 * DH_SIGMA**2)
            * norm.cdf((mean + DH_SIGMA**2 - k) / DH_SIGMA)
            - np.exp(k) * norm.cdf((mean - k) / DH_SIGMA)
        )
    return call


def mixture_density(x: np.ndarray) -> np.ndarray:
    """True log-return density of the double-hump mixture."""
    return 0.5 * (
        norm.pdf(x, DH_MEANS[0], DH_SIGMA) + norm.pdf(x, DH_MEANS[1], DH_SIGMA)
    )


@dataclass(frozen=True)
class DoubleHump:
    """The mixture target and its production fits at two orders."""

    quote_k: np.ndarray
    quote_w: np.ndarray
    high: CalibrationResult   # N = 16: resolves both modes
    low: CalibrationResult    # N = 6 comparator: smooths them away


@lru_cache(maxsize=1)
def double_hump() -> DoubleHump:
    """Fit the double-hump strip at N = 16 and the N = 6 comparator."""
    quote_k = np.linspace(-0.25, 0.25, 41)
    quote_w = implied_total_variance(quote_k, mixture_call(quote_k))
    high = calibrate_slice(
        quote_k, quote_w, DH_EXPIRY, n_order=DH_ORDER_HIGH,
        reg_lambda=DH_REG, reg_power=DH_REG_POWER,
    )
    low = calibrate_slice(
        quote_k, quote_w, DH_EXPIRY, n_order=DH_ORDER_LOW,
        reg_lambda=DH_REG, reg_power=DH_REG_POWER,
    )
    return DoubleHump(quote_k=quote_k, quote_w=quote_w, high=high, low=low)


def density_modes(x: np.ndarray, f: np.ndarray,
                  window: float = 0.35) -> list[float]:
    """Locations of interior local maxima of a density inside |x| < window."""
    sel = np.abs(x) < window
    xs, fs = x[sel], f[sel]
    floor = 0.05 * float(fs.max())
    idx = np.nonzero(
        (fs[1:-1] > fs[:-2]) & (fs[1:-1] > fs[2:]) & (fs[1:-1] > floor)
    )[0]
    return [float(xs[i + 1]) for i in idx]


def valley_to_peak(x: np.ndarray, f: np.ndarray) -> float:
    """min/max density ratio between the outermost modes (1.0 = unimodal)."""
    modes = density_modes(x, f)
    if len(modes) < 2:
        return 1.0
    between = (x >= modes[0]) & (x <= modes[-1])
    return float(np.min(f[between]) / np.max(f[between]))


def density_l1(slice_: LQDSlice, window: float = 0.6) -> float:
    """L1 distance between a fitted density and the true mixture density."""
    x, f = slice_.density()
    sel = np.abs(x) < window
    return float(np.trapezoid(np.abs(f[sel] - mixture_density(x[sel])), x[sel]))


# ------------------------------------------------------ timing workload
def ssvi_total_variance(k: np.ndarray) -> np.ndarray:
    """A deterministic SPX-shaped SSVI slice used only as a quote oracle."""
    theta, rho, phi = 0.0356, -0.68, 2.40
    k = np.asarray(k, dtype=float)
    return 0.5 * theta * (
        1.0 + rho * phi * k + np.sqrt((phi * k + rho) ** 2 + 1.0 - rho * rho)
    )


def timing_strip() -> tuple[np.ndarray, np.ndarray, float]:
    """(k, w, t): the 40-quote strip every timing solve calibrates."""
    k = np.linspace(-0.35, 0.30, 40)
    return k, ssvi_total_variance(k), 0.5


def logistic_u(z: np.ndarray) -> np.ndarray:
    """Percentile rank u = expit(z) (kept here so figures avoid scipy)."""
    return expit(z)
