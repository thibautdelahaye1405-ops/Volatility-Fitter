"""The chapter's synthetic frozen-field worlds (sections 9.5-9.6).

Deterministic constructions: time-homogeneous local-variance fields v(y)
on the normalized strike axis y = K/F_0 (Chapter 4's coordinates, zero
carry, variance time equal to calendar time -- no events).  Three
generators, all sharing the same at-the-money volatility and the same
at-the-money log-slope:

  * ``logaffine``   -- vol affine in log-strike,
                       sigma(y) = SIGMA_ATM + SLOPE_LOC log y;
  * ``dollaraffine``-- vol affine in dollar strike,
                       sigma(y) = SIGMA_ATM + SLOPE_LOC (y - 1);
  * ``bent``        -- log-affine plus curvature,
                       sigma(y) = SIGMA_ATM + SLOPE_LOC log y
                                  + CURV_LOC (log y)^2.

All are clamped to [VOL_LO, VOL_HI] far outside the working span.
Everything the two sections need comes from marching Chapter 4's forward
(Dupire) equation over a field -- the same self-contained marcher the
Chapter 4 figures used (scripts/ch04/figlib/pde1d.py) -- and inverting
the Black formula on the grid nodes (no interpolation at the money: the
grid contains y = 1 exactly).  A spot scenario holds the field fixed in
absolute strike and moves the forward by H: in the new normalized
coordinates the coefficient becomes v(y' e^H).  No randomness anywhere.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

_SCRIPTS = Path(__file__).resolve().parents[2]
_P4 = str(_SCRIPTS / "ch04" / "figlib")
if _P4 not in sys.path:
    sys.path.append(_P4)

import pde1d  # noqa: E402  (Chapter 4's forward-Dupire marcher)
from blackutil import implied_w  # noqa: E402

# ----------------------------------------------------- generator constants
SIGMA_ATM = 0.20      # generator vol at the money (y = 1)
SLOPE_LOC = -0.35     # generator vol log-slope at the money
CURV_LOC = 0.50       # curvature of the ``bent`` generator, per (log y)^2
VOL_LO, VOL_HI = 0.08, 0.60   # clamps, far outside the working span

# ----------------------------------------------------------- lattice sizes
Y_MAX = 4.0
DY = 0.002            # strike step (y = 1 on the grid)
DT = 5.0e-4           # default march step
T_MAX = 1.5
MATURITIES = (0.05, 0.10, 0.15, 0.25, 0.40, 0.60, 0.85, 1.15, 1.50)

K_SPAN = 0.30         # working log-moneyness span of the smile read-outs

GENERATORS = ("logaffine", "dollaraffine", "bent")


def vol_loc(gen: str, y: np.ndarray) -> np.ndarray:
    """The generator volatility sqrt(v)(y), clamped."""
    y = np.maximum(np.asarray(y, dtype=float), 1e-12)
    x = np.log(y)
    if gen == "logaffine":
        raw = SIGMA_ATM + SLOPE_LOC * x
    elif gen == "dollaraffine":
        raw = SIGMA_ATM + SLOPE_LOC * (y - 1.0)
    elif gen == "bent":
        raw = SIGMA_ATM + SLOPE_LOC * x + CURV_LOC * x**2
    else:
        raise ValueError(f"unknown generator {gen!r}")
    return np.clip(raw, VOL_LO, VOL_HI)


def _v_fn(gen: str, big_h: float):
    """Local-variance coefficient after a forward move H (frozen field)."""
    shift = np.exp(big_h)

    def v(_tau, y):
        return vol_loc(gen, np.asarray(y, dtype=float) * shift) ** 2

    return v


@lru_cache(maxsize=32)
def march(gen: str, big_h: float, dt: float = DT, t_max: float = T_MAX,
          maturities: tuple[float, ...] = MATURITIES):
    """March the field (moved by H) and invert every requested maturity.

    Returns {T: (k, w)} where k are exact grid-node log-moneyness values
    inside +/- K_SPAN and w the total implied variances there.
    """
    y = pde1d.uniform_grid(Y_MAX, DY)
    n_steps = int(round(t_max / dt))
    t_grid = np.linspace(0.0, t_max, n_steps + 1)
    want = [t for t in maturities if t <= t_max + 1e-12]
    calls = pde1d.march(_v_fn(gen, big_h), y, t_grid, scheme="implicit",
                        snapshots=want)
    sel = (y > np.exp(-K_SPAN) - 1e-12) & (y < np.exp(K_SPAN) + 1e-12)
    k = np.log(y[sel])
    out = {}
    for t, c in calls.items():
        out[t] = (k, implied_w(k, c[sel]))
    return out


def smile_at(gen: str, big_h: float, t: float, dt: float = DT):
    """(k, sigma) at one maturity for the field moved by H."""
    res = march(gen, big_h, dt=dt, t_max=t, maturities=(t,))
    k, w = res[t]
    return k, np.sqrt(w / t)


def atm_and_skew(k: np.ndarray, sigma: np.ndarray,
                 fit_span: float = 0.03) -> tuple[float, float]:
    """(sigma_atm, s0) by a local quadratic fit around the money."""
    sel = np.abs(k) <= fit_span
    coef = np.polyfit(k[sel], sigma[sel], 2)
    return float(np.polyval(coef, 0.0)), float(coef[1])


def realized_ratio(gen: str, big_h: float, dt: float = DT) -> dict:
    """The frozen-field reprice measured across maturities.

    For each maturity: sigma_atm before/after the move, the base ATM skew
    s0(T), and the realized ratio (sigma_new - sigma_old)/(s0 H).
    """
    base = march(gen, 0.0, dt=dt)
    moved = march(gen, big_h, dt=dt)
    out = {}
    for t in MATURITIES:
        k0, w0 = base[t]
        k1, w1 = moved[t]
        atm0, s0 = atm_and_skew(k0, np.sqrt(w0 / t))
        atm1, _ = atm_and_skew(k1, np.sqrt(w1 / t))
        out[t] = {
            "atm0": atm0, "atm1": atm1, "s0": s0,
            "ratio": (atm1 - atm0) / (s0 * big_h),
        }
    return out


def response(gen: str, big_h: float, t: float, dt: float):
    """The field's own answer: the repriced smile change at fixed moneyness.

    Returns (k, d_sigma_bp): sigma_new(k) - sigma_old(k) in vol bp, both
    smiles read in their own prevailing moneyness.
    """
    k0, sig0 = smile_at(gen, 0.0, t, dt=dt)
    k1, sig1 = smile_at(gen, big_h, t, dt=dt)
    assert np.allclose(k0, k1)
    return k0, (sig1 - sig0) * 1e4
