"""The chapter's common fitting protocol and per-family diagnostics.

Protocol (stated in the chapter appendix): each family is calibrated by the
reference implementation to the SAME mid quotes with equal weights ---
  * LQD: order 16 under the quote-count guard, logistic chart,
    ridge 1e-6 with power 1 (the snapshot's recipe, mid objective);
  * SVI: structural chart, default fences (cap 1.95, multiplier 1e3);
  * MCS: two cores under the identifiability cap, amplitude ridge 1e-2,
    put-wing regularizer at its reference strength.

Every Durrleman factor is evaluated from the model's own analytic structure,
never by differencing prices: SVI and MCS from closed-form (w, w', w''),
LQD exactly through the density identity g_D = f_X(k) sqrt(w) / phi(d_-)
(book eq. durrleman), with f_X the slice's explicit density.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import numpy as np

from volfit.models.lqd.basis import LQDParams, lee_slopes
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.quadrature import LQDSlice, build_slice
from volfit.models.sigmoid.calibrate import calibrate_sigmoid
from volfit.models.sigmoid.kernels import gatheral_g_from_z
from volfit.models.sigmoid.sigmoid import MultiCoreSiv
from volfit.models.svi_jw.calibrate import calibrate_svi
from volfit.models.svi_jw.svi import RawSVI, durrleman_g_raw

import data3

FAMILIES = ("LQD", "SVI", "MCS")

# Protocol constants (the reference implementation's shipped defaults).
LQD_ORDER = 16
LQD_RIDGE, LQD_RIDGE_POWER = 1e-6, 1.0
MCS_CORES = 2
MCS_WING_PENALTY = 1e3  # reference strength of the put-wing regularizer
G_GRID = 801            # dense traded-range grid for the min-g_D margin


def lqd_effective_order(n_quotes: int, n_order: int = LQD_ORDER) -> int:
    """The quote-count guard of book eq. (orderguard)."""
    return max(min(n_order, n_quotes // 2 - 1), min(n_order, 6))


# --------------------------------------------------------------- Durrleman g
def g_svi(raw: RawSVI, k: np.ndarray) -> np.ndarray:
    """Closed-form Durrleman factor of a raw SVI slice."""
    return durrleman_g_raw(raw, np.asarray(k, dtype=float))


def g_mcs(model: MultiCoreSiv, k: np.ndarray) -> np.ndarray:
    """Durrleman factor of an MCS slice from its analytic z-space jets."""
    z = model.z(np.asarray(k, dtype=float))
    v, vz, vzz = model.variance_z(z)
    return gatheral_g_from_z(z, v, vz, vzz, model.t, model.sigma_ref)


def g_lqd(slice_: LQDSlice, k: np.ndarray, t: float) -> np.ndarray:
    """Durrleman factor of an LQD slice, exactly, via the density identity.

    Chapter 2's eq. (durrleman) reads f_X(k) = g_D(k) phi(d_-)/sqrt(w), so
    g_D(k) = f_X(k) sqrt(w(k)) / phi(d_-(k, w)).  f_X comes from the slice's
    explicit density (log-interpolated between grid points); no finite
    difference of w is involved.
    """
    k = np.asarray(k, dtype=float)
    x_grid, f_x = slice_.density()
    log_f = np.interp(k, x_grid, np.log(np.maximum(f_x, 1e-300)))
    w = np.asarray(slice_.implied_w(k), dtype=float)
    sqrt_w = np.sqrt(w)
    d_minus = -k / sqrt_w - 0.5 * sqrt_w
    phi = np.exp(-0.5 * d_minus**2) / np.sqrt(2.0 * np.pi)
    return np.exp(log_f) * sqrt_w / phi


def mcs_wing_slopes(model: MultiCoreSiv) -> tuple[float, float]:
    """Asymptotic total-variance k-space slopes (beta_P, beta_C) of the base."""
    scale = np.sqrt(model.t) / model.sigma_ref
    beta_p = scale * (2.0 * model.k0 / model.kappa_p - model.s0)
    beta_c = scale * (model.s0 + 2.0 * model.k0 / model.kappa_c)
    return float(beta_p), float(beta_c)


# ------------------------------------------------------------------ fitting
@dataclass
class FamilyFit:
    """One family fitted to one quote strip, plus the chapter's metrics."""

    family: str
    n_params: int
    model: object                       # LQDSlice | RawSVI | MultiCoreSiv
    iv: Callable[[np.ndarray], np.ndarray]
    g: Callable[[np.ndarray], np.ndarray]
    rms_bp: float
    max_bp: float
    min_g: float                        # min g_D on the dense traded-range grid
    beta_l: float
    beta_r: float


def _metrics(iv_fn, g_fn, k, iv_mid) -> tuple[float, float, float]:
    err = 1e4 * (iv_fn(k) - iv_mid)
    grid = np.linspace(float(k.min()), float(k.max()), G_GRID)
    return (
        float(np.sqrt(np.mean(err**2))),
        float(np.max(np.abs(err))),
        float(np.min(g_fn(grid))),
    )


def fit_lqd(k, w_mid, t, iv_mid, n_order: int = LQD_ORDER) -> FamilyFit:
    n_eff = lqd_effective_order(k.size, n_order)
    res = calibrate_slice(
        np.asarray(k, float), np.asarray(w_mid, float), t, n_order=n_eff,
        reg_lambda=LQD_RIDGE, reg_power=LQD_RIDGE_POWER, coords="logistic",
    )
    slice_ = res.slice

    def iv_fn(kk, s=slice_, tt=t):
        return np.asarray(s.implied_vol(np.asarray(kk, float), tt))

    def g_fn(kk, s=slice_, tt=t):
        return g_lqd(s, kk, tt)

    rms, mx, ming = _metrics(iv_fn, g_fn, k, iv_mid)
    b_l, b_r = lee_slopes(res.params)
    return FamilyFit("LQD", n_eff + 1, slice_, iv_fn, g_fn,
                     rms, mx, ming, float(b_l), float(b_r))


def fit_svi(k, w_mid, t, iv_mid) -> FamilyFit:
    res = calibrate_svi(
        np.asarray(k, float), np.asarray(w_mid, float), t, chart="structural",
    )
    raw = res.raw

    def iv_fn(kk, r=raw, tt=t):
        return np.asarray(r.implied_vol(np.asarray(kk, float), tt))

    def g_fn(kk, r=raw):
        return g_svi(r, kk)

    rms, mx, ming = _metrics(iv_fn, g_fn, k, iv_mid)
    b_l, b_r = raw.wing_slopes()
    return FamilyFit("SVI", 5, raw, iv_fn, g_fn,
                     rms, mx, ming, float(b_l), float(b_r))


def fit_mcs(k, w_mid, t, iv_mid, n_cores: int = MCS_CORES,
            wing_penalty: float = MCS_WING_PENALTY) -> FamilyFit:
    model = calibrate_sigmoid(
        np.asarray(k, float), np.asarray(w_mid, float), t,
        n_cores=n_cores, wing_penalty=wing_penalty,
    )

    def iv_fn(kk, m=model):
        return np.asarray(m.vol(np.asarray(kk, float)))

    def g_fn(kk, m=model):
        return g_mcs(m, kk)

    rms, mx, ming = _metrics(iv_fn, g_fn, k, iv_mid)
    b_l, b_r = mcs_wing_slopes(model)
    return FamilyFit("MCS", 6 + 4 * len(model.cores), model, iv_fn, g_fn,
                     rms, mx, ming, b_l, b_r)


@lru_cache(maxsize=None)
def node_fits(ticker: str, expiry: str) -> dict[str, FamilyFit]:
    """All three families fitted to one frozen node under the protocol."""
    n = data3.node(ticker, expiry)
    return {
        "LQD": fit_lqd(n.k, n.w_mid, n.t, n.iv_mid),
        "SVI": fit_svi(n.k, n.w_mid, n.t, n.iv_mid),
        "MCS": fit_mcs(n.k, n.w_mid, n.t, n.iv_mid),
    }


def rebuild_stored_lqd(node: data3.Node) -> LQDSlice:
    """The snapshot's stored haircut fit (provenance only, never refitted)."""
    return build_slice(node.lqd_params)
