"""Var-swap residual rows of the affine LV calibration: static replication weights
and the two row carriers (absolute total variance / ATM-spread).

Static replication (Docs/piecewise_affine_local_variance_calibration.tex, eq.
(variance_swap_static_replication)): the model var-swap TOTAL variance of an
expiry is a theta-linear functional of the PDE call prices,

    z(theta) = q @ C(T, .) + const,          (``varswap_weights`` / ``varswap_const``)

so its Jacobian ``jz = q @ dC/dtheta`` reuses the forward sensitivities. The
source-PDE method (varswap_pde) yields the same ``(z, jz)`` pair by a backward
march; everything below consumes only that pair.

Two row carriers (the LV analogue of volfit.calib.varswap.VarSwapTarget.mode):

* ABSOLUTE (``VarSwapQuote.atm_spread is None``, the historical row): residual
  ``(z − z_mkt) / ζ`` with ζ in total-variance units. Market quotes are always
  absolute (a quote is the truth, not a shape).
* ATM-SPREAD (``atm_spread`` set — PRIOR companion rows under
  ``priorVarSwapMode="atm_spread"``): the tail-mass-over-body carrier

      ((σ_vs(θ) − σ_atm(θ)) − atm_spread) / ζ_σ,

  with σ_vs = sqrt(z / t), σ_atm the Black vol inverted from the model's ATM call
  price (x = 1 is a lattice node — ``varswap_weights`` requires it — so the ATM
  price is a plain grid read, no interpolation) and ζ_σ in VOL units. The row is
  a nonlinear functional of θ but its Jacobian is closed-form from the same
  sensitivities: dσ_vs/dθ = jz / (2 t σ_vs), dσ_atm/dθ = (dC_atm/dθ) / vega(σ_atm).
  Before 2026-08-27 the LV path had no spread row form and silently fell back
  to the absolute carrier (the "nodal-variance linearization" rider).

``varswap_residual_rows`` assembles the whole var-swap block; absolute rows are
the exact historical expressions (byte-identical), spread rows override in place.
"""

from __future__ import annotations

import numpy as np

from volfit.core.black import atm_total_variance, black_vega_sigma

#: Floors keeping the vol transforms finite on a degenerate iterate.
_Z_FLOOR = 1e-12
_VEGA_FLOOR = 1e-6
_P_EPS = 1e-12


def varswap_weights(x_grid: np.ndarray, k_lo: float = 0.0) -> np.ndarray:
    """Trapezoid weights q with I(T) = q @ C(T, .) + const(parity).

    Splits eq. (variance_swap_static_replication) at the anchor k = 1 (which
    must be a grid point): below it the integrand is P/k^2 = (C + k - 1)/k^2,
    above it C/k^2 -- the affine parity part contributes a theta-independent
    constant, returned separately by ``varswap_const``.  Grid points with
    x <= k_lo (and x = 0, where 1/k^2 blows up) get zero weight.
    """
    x = np.asarray(x_grid, dtype=float)
    i1 = int(np.searchsorted(x, 1.0))
    if x[i1] != 1.0:
        raise ValueError("the var-swap anchor x = 1 must be a grid point")
    mask = x >= max(k_lo, 1e-12)
    q = np.zeros_like(x)
    # trapezoid over the put leg [k_lo, 1] and the call leg [1, x_max]
    put_idx = np.nonzero(mask & (x <= 1.0))[0]
    call_idx = np.nonzero(x >= 1.0)[0]
    for idx in (put_idx, call_idx):
        xs = x[idx]
        w = np.zeros(xs.size)
        dx = np.diff(xs)
        w[:-1] += 0.5 * dx
        w[1:] += 0.5 * dx
        q[idx] += 2.0 * w / (xs * xs)
    return q


def varswap_const(x_grid: np.ndarray, k_lo: float = 0.0) -> float:
    """Theta-independent parity part of the replication: 2 int (k-1)/k^2 over the put leg."""
    x = np.asarray(x_grid, dtype=float)
    idx = np.nonzero((x >= max(k_lo, 1e-12)) & (x <= 1.0))[0]
    xs = x[idx]
    f = (xs - 1.0) / (xs * xs)
    return float(2.0 * np.trapezoid(f, xs))


def atm_index(x_grid: np.ndarray) -> int:
    """Index of the ATM node x = 1 on the PDE strike grid (must be a grid point)."""
    x = np.asarray(x_grid, dtype=float)
    i1 = int(np.searchsorted(x, 1.0))
    if i1 >= x.size or x[i1] != 1.0:
        raise ValueError("the var-swap anchor x = 1 must be a grid point")
    return i1


def spread_row_values(
    z: float,
    jz: np.ndarray,
    p_atm: float,
    sens_atm: np.ndarray,
    t: float,
    atm_spread: float,
    tol: float,
) -> tuple[float, np.ndarray]:
    """One ATM-spread var-swap row: value and Jacobian row.

    ``z`` / ``jz`` are the model var-swap total variance and its parameter
    gradient (static replication or source PDE — either), ``p_atm`` /
    ``sens_atm`` the model ATM call price and its gradient (the x = 1 lattice
    row of the PDE solution), ``t`` the expiry, ``atm_spread`` the prior's
    σ_vs − σ_atm (vol units) and ``tol`` the row tolerance ζ_σ (vol units).

        value = ((σ_vs − σ_atm) − atm_spread) / tol
        row   = (jz / (2 t σ_vs) − sens_atm / vega(σ_atm)) / tol

    σ_atm comes from the closed-form ATM inversion B(0, w) = 2Φ(√w/2) − 1 and
    vega(σ_atm) = φ(√w/2)·√t is dB/dσ at k = 0, so dσ_atm/dθ = (dB/dθ) / vega by
    the chain rule on the inversion. Floors keep a degenerate iterate finite.
    """
    sigma_vs = float(np.sqrt(max(float(z), _Z_FLOOR) / t))
    d_sigma_vs = np.asarray(jz, dtype=float) / (2.0 * t * sigma_vs)
    p = min(max(float(p_atm), _P_EPS), 1.0 - _P_EPS)
    w_atm = max(atm_total_variance(p), _Z_FLOOR)
    sigma_atm = float(np.sqrt(w_atm / t))
    vega = max(float(black_vega_sigma(0.0, sigma_atm, t)), _VEGA_FLOOR)
    d_sigma_atm = np.asarray(sens_atm, dtype=float) / vega
    value = ((sigma_vs - sigma_atm) - float(atm_spread)) / tol
    return value, (d_sigma_vs - d_sigma_atm) / tol


def varswap_residual_rows(
    varswaps,
    z: np.ndarray,
    jz: np.ndarray,
    z_mkt: np.ndarray,
    zeta: np.ndarray,
    solution,
    i_atm: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Residual + Jacobian rows of the var-swap block (one row per quote).

    ``varswaps`` are the ``VarSwapQuote`` objects (duck-typed here: ``t``, ``tol``,
    ``atm_spread``), ``z`` / ``jz`` the model totals and their Jacobian for every
    quote, ``z_mkt`` / ``zeta`` the quoted totals and tolerances, ``solution`` the
    sensitivity-carrying ``AffinePDESolution`` and ``i_atm`` the x = 1 lattice
    index (``atm_index``). Absolute rows are EXACTLY the historical
    ``(z − z_mkt) / ζ`` and ``jz / ζ`` (byte-identical); rows whose quote carries
    ``atm_spread`` are overridden by ``spread_row_values``.
    """
    res = (z - z_mkt) / zeta
    jac = jz / zeta[:, None]
    if not any(getattr(v, "atm_spread", None) is not None for v in varswaps):
        return res, jac
    exp_index = {float(t): i for i, t in enumerate(solution.expiries)}
    for i, v in enumerate(varswaps):
        if v.atm_spread is None:
            continue
        e = exp_index[float(v.t)]
        res[i], jac[i] = spread_row_values(
            float(z[i]), jz[i], float(solution.prices[e][i_atm]),
            solution.sens[e][i_atm], float(v.t), float(v.atm_spread), float(v.tol),
        )
    return res, jac
