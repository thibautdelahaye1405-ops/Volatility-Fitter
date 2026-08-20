"""Seeding, bounds and evaluation helpers of the Multi-Core SIV calibrator.

Split out of ``calibrate.py`` (V3.1 file split — the 400-line policy): the
data-driven starts, the box bounds of the raw chart, the greedy hat seeding of
the note's "Calibration methodology" (Docs/Multi_Core_SIV_Technical_Note.tex,
eqs calibration-objective, kernel-bounds, linear-amplitude-fit), the flat
parameter-vector evaluator, and the kernel-governance resolution floor (the
book's "governed dial", ch. 03 sec. superposition). ``calibrate.py`` re-exports
the historical names so the public import surface is unchanged.
"""

from __future__ import annotations

import numpy as np

from volfit.models.sigmoid.kernels import hat, siv_base

#: Per-hat starting half-width / steepness (note's WW example, eq ww-fit-model).
_H_INIT = 0.40
_KAPPA_INIT = 5.0
#: Practical kernel bounds (eq kernel-bounds): half-width and steepness ranges.
_H_BOUNDS = (0.15, 1.5)
_KAPPA_BOUNDS = (1.0, 12.0)
#: Centre padding beyond the quoted z-range for hat placement.
_C_PAD = 0.5
#: Mild ridge on hat amplitudes (eq calibration-objective l2 term) — keeps
#: overlapping cores from exploding without biasing well-determined amplitudes.
_RIDGE = 1e-2
#: Variance floor mirroring MultiCoreSiv (keeps vol = sqrt(v) real).
_V_FLOOR = 1e-8


def _reference_vol(vol_quotes: np.ndarray, k: np.ndarray) -> float:
    """Reference vol fixing the z-scale: the quoted vol nearest the money."""
    atm = float(vol_quotes[np.argmin(np.abs(k))])
    return atm if atm > 1e-3 else float(np.median(vol_quotes))


def _eval_v(theta: np.ndarray, z: np.ndarray, n_cores: int) -> np.ndarray:
    """Model variance v_R(z) for a flat parameter vector (base + n_cores hats)."""
    v0, s0, k0, z0, kp, kc = theta[:6]
    v, _, _ = siv_base(z, v0, s0, k0, z0, kp, kc)
    for r in range(n_cores):
        alpha, c, h, kappa = theta[6 + 4 * r : 10 + 4 * r]
        v = v + alpha * hat(z, c, h, kappa)
    return v


def _base_init(z: np.ndarray, v_quotes: np.ndarray) -> np.ndarray:
    """Data-driven start for the 6 base parameters from the variance quotes."""
    order = np.argsort(z)
    zs, vs = z[order], v_quotes[order]
    d = max(0.3 * (zs[-1] - zs[0]) / 2.0, 0.1)
    v_lo, v_mid, v_hi = np.interp([-d, 0.0, d], zs, vs)
    s0 = (v_hi - v_lo) / (2.0 * d)
    k0 = max((v_hi - 2.0 * v_mid + v_lo) / (d * d), 1e-2)
    return np.array([max(v_mid, 1e-4), s0, k0, 0.0, 3.0, 3.0])


def _base_bounds(z: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lo = np.array([1e-6, -10.0, 0.0, z.min() - 2.0, 0.2, 0.2])
    hi = np.array([25.0, 10.0, 10.0, z.max() + 2.0, 25.0, 25.0])
    return lo, hi


def _seed_cores(z: np.ndarray, residual: np.ndarray, n_cores: int) -> list[np.ndarray]:
    """Greedily place hats at the largest |residual|, enforcing centre spacing."""
    sep = max((z.max() - z.min()) / (2.0 * n_cores), 0.2)
    seeds: list[np.ndarray] = []
    remaining = residual.copy()
    for _ in range(n_cores):
        i = int(np.argmax(np.abs(remaining)))
        c = float(z[i])
        alpha = float(np.clip(residual[i], -1.0, 1.0))
        seeds.append(np.array([alpha, c, _H_INIT, _KAPPA_INIT]))
        remaining[np.abs(z - c) < sep] = 0.0  # mask the neighbourhood, then repeat
    return seeds


def _core_bounds(z: np.ndarray) -> tuple[list[float], list[float]]:
    lo = [-1.0, z.min() - _C_PAD, _H_BOUNDS[0], _KAPPA_BOUNDS[0]]
    hi = [1.0, z.max() + _C_PAD, _H_BOUNDS[1], _KAPPA_BOUNDS[1]]
    return lo, hi


# ----------------------------------------------------------- kernel governance
def alpha_resolution_floor(
    theta: np.ndarray,
    z: np.ndarray,
    vol_quotes: np.ndarray,
    n_cores: int,
    sigma_ref: float,
) -> float:
    """Quote-noise resolution floor on the hat amplitudes (V3.1 leg 5).

    A hat of amplitude alpha displaces the model VOL at its centre by roughly
    alpha / (2 sigma_ref) (dv = 2 sigma dsigma and B(c) = 1, eq B-center). When
    that displacement sits below the fit's own residual scale — the rms vol
    error against the quotes at the solution — the amplitude is not resolved by
    the data (the note's kernel non-uniqueness: overlapping hats trade amplitude
    without moving the curve, the book's "governed dial" motivation), so the
    floor is  alpha_min = 2 sigma_ref * rms_vol.  An exact fit (rms -> 0) prunes
    nothing, so clean synthetic round-trips stay byte-identical.
    """
    model_vol = np.sqrt(np.maximum(_eval_v(theta, z, n_cores), _V_FLOOR))
    rms = float(np.sqrt(np.mean((model_vol - vol_quotes) ** 2)))
    return 2.0 * float(sigma_ref) * rms
