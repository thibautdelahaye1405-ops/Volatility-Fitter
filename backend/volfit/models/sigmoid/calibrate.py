"""Calibration of the Multi-Core SIV slice (Docs/Multi_Core_SIV_Technical_Note.tex).

Implements the robust workflow of section "Calibration methodology":

  1. fit the one-core SIV base (R = 0) to the quotes;
  2. seed R signed hats greedily at the largest variance residuals;
  3. refine the full (6 + 4R)-parameter set jointly with bound constraints and a
     mild ridge penalty on the hat amplitudes (eqs calibration-objective,
     kernel-bounds, linear-amplitude-fit).

Residuals are in implied-vol units (the natural quoting scale). All positive
parameters (K0, the wing steepnesses, the hat half-widths and steepnesses) are
bound-constrained directly through scipy's trust-region reflective solver.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT, BandTarget, band_residuals
from volfit.models.sigmoid.kernels import hat, siv_base
from volfit.models.sigmoid.sigmoid import HatCore, MultiCoreSiv

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


def _fit(
    theta0: np.ndarray,
    lo: np.ndarray,
    hi: np.ndarray,
    z: np.ndarray,
    vol_quotes: np.ndarray,
    sqrt_w: np.ndarray,
    n_cores: int,
    band: BandTarget | None = None,
    ridge: float = _RIDGE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
) -> np.ndarray:
    """Bounded least-squares of the data term plus the amplitude ridge.

    The data term is the plain mid residual (``band is None``) or the bid-ask /
    haircut band objective in vol space (volfit.calib.band). ``ridge`` is the hat
    amplitude penalty strength and ``mid_anchor_weight`` the band's mid anchor.
    """

    def residuals(theta: np.ndarray) -> np.ndarray:
        model_vol = np.sqrt(np.maximum(_eval_v(theta, z, n_cores), _V_FLOOR))
        if band is None:
            res = sqrt_w * (model_vol - vol_quotes)
        else:
            res = band_residuals(
                model_vol, band.iv_lo, band.iv_hi, band.iv_mid, sqrt_w, mid_anchor_weight
            )
        if n_cores:
            alphas = theta[6::4][:n_cores]
            res = np.concatenate([res, np.sqrt(ridge) * alphas])
        return res

    theta0 = np.clip(theta0, lo, hi)
    result = least_squares(residuals, theta0, bounds=(lo, hi), method="trf", xtol=1e-12, ftol=1e-12)
    return result.x


def calibrate_sigmoid(
    k: np.ndarray,
    w_quotes: np.ndarray,
    t: float,
    weights: np.ndarray | None = None,
    n_cores: int = 0,
    band: BandTarget | None = None,
    ridge: float = _RIDGE,
    mid_anchor_weight: float = MID_ANCHOR_WEIGHT,
) -> MultiCoreSiv:
    """Fit the Multi-Core SIV slice to total-variance quotes (eq mcsiv-slice).

    ``n_cores`` is the number R of zero-wing hats added on top of the base SIV
    (the "cores" slider). It is capped so the model never has more free
    parameters than quotes (6 + 4R <= N), guarding sparse short-dated chains
    against fitting spurious narrow kernels (note section identifiability).
    ``band`` switches the final fit to the bid-ask / haircut band objective
    (volfit.calib.band); the base-seeding stage always fits mid so the hats are
    placed on meaningful residuals.
    """
    k = np.asarray(k, dtype=float)
    vol_quotes = np.sqrt(np.asarray(w_quotes, dtype=float) / t)
    v_quotes = np.asarray(w_quotes, dtype=float) / t
    sqrt_w = np.ones_like(k) if weights is None else np.sqrt(np.asarray(weights, float))

    n_cores = max(0, min(int(n_cores), (k.size - 6) // 4))
    sigma_ref = _reference_vol(vol_quotes, k)
    z = k / (sigma_ref * np.sqrt(t))

    # Stage 1: base SIV (R = 0), always on mid — gives a stable centre and the
    # residuals used to place the hats.
    base_lo, base_hi = _base_bounds(z)
    base = _fit(_base_init(z, v_quotes), base_lo, base_hi, z, vol_quotes, sqrt_w, 0)

    # Stage 2: seed hats on the base residual, then refine everything jointly
    # under the requested objective (band or mid).
    if n_cores > 0:
        residual = v_quotes - _eval_v(base, z, 0)
        seeds = _seed_cores(z, residual, n_cores)
        theta0 = np.concatenate([base, *seeds])
        clo, chi = _core_bounds(z)
        lo = np.concatenate([base_lo, *([clo] * n_cores)])
        hi = np.concatenate([base_hi, *([chi] * n_cores)])
        theta = _fit(
            theta0, lo, hi, z, vol_quotes, sqrt_w, n_cores,
            band=band, ridge=ridge, mid_anchor_weight=mid_anchor_weight,
        )
    else:
        theta = _fit(
            base, base_lo, base_hi, z, vol_quotes, sqrt_w, 0,
            band=band, ridge=ridge, mid_anchor_weight=mid_anchor_weight,
        )

    cores = tuple(
        HatCore(
            alpha=float(theta[6 + 4 * r]),
            c=float(theta[7 + 4 * r]),
            h=float(theta[8 + 4 * r]),
            kappa=float(theta[9 + 4 * r]),
        )
        for r in range(n_cores)
    )
    return MultiCoreSiv(
        v0=float(theta[0]),
        s0=float(theta[1]),
        k0=float(theta[2]),
        z0=float(theta[3]),
        kappa_p=float(theta[4]),
        kappa_c=float(theta[5]),
        sigma_ref=sigma_ref,
        t=t,
        cores=cores,
    )
