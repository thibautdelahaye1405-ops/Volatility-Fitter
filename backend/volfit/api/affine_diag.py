"""Phase 0 diagnostics for the local-vol affine fit — per-expiry metrics that
distinguish the short-dated failure modes WITHOUT changing any calibrated value.

Pure observation: computed from the fit inputs (the gathered ``rows``, the vertex
grid, the PDE grids, and the live-vs-prior quote split) and attached to a
side-channel on ``AppState`` (like ``last_affine_diagnostics``), never fed back
into the solve — so the surface stays byte-identical. It exists to answer, with
numbers, *why* a short-dated Local-Vol smile fits badly, before any model change:

- **Cause A — strike under-resolution.** ``nVerticesInRange`` is how many STRIKE
  vertices fall inside THIS expiry's traded ``[kLo, kHi]``. The tensor axis is
  scaled to the LONGEST expiry and clipped to the GLOBAL strike range
  (``_delta_strike_nodes``), so a narrow short smile can land only a handful of
  vertices on its sharpest curvature.
- **Cause B — the maturity-blind vega floor.** ``nVegaFloored`` / ``vegaFloorFrac``
  count quotes whose Black vega (``black_vega_sigma`` = φ(d₊)·√τ) is below the
  ABSOLUTE ``_VEGA_FLOOR``. Since ATM vega ~ √τ, the same floor underweights the
  short end far harder than the long end — reported next to ``vegaAtm`` so the
  √τ scaling is visible.
- **Cause C — coarse front PDE clock.** ``nTimeSteps`` is how many PDE time steps
  resolve ``(t_prev, τ]`` — the first expiry gets very few backward-Euler steps
  over the payoff kink.
- **Cause E — prior/early-stop leak.** ``nPriorRows`` / ``priorActive`` count the
  synthetic prior option rows targeting the expiry; the early-stop accounting only
  mixes them with live quotes when these are > 0.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.core.black import black_vega_sigma, norm_pdf


@dataclass(frozen=True)
class AffineExpiryDiagnostics:
    """Per-expiry Phase-0 diagnostics (side metadata; never fed back into the fit)."""

    expiry: str  # ISO date
    t: float  # calendar year fraction (axis)
    tau: float  # event-weighted variance years (the diffusion clock)
    n_quotes: int  # live option quotes constraining this expiry
    n_vega_floored: int  # live quotes with vega < the absolute floor (Cause B)
    vega_floor_frac: float  # n_vega_floored / n_quotes
    vega_atm: float  # ATM Black vega φ(d₊)·√τ — the √τ-scaled reference
    vega_floor: float  # the absolute floor in force (_VEGA_FLOOR)
    k_lo: float  # this expiry's traded log-moneyness range
    k_hi: float
    n_vertices_in_range: int  # STRIKE vertices inside [kLo, kHi] (Cause A)
    n_vertices_total: int  # total strike vertices on the shared axis
    n_time_steps: int  # PDE time steps resolving (t_prev, τ] (Cause C)
    n_prior_rows: int  # synthetic prior option rows targeting this expiry (Cause E)
    prior_active: bool  # any prior rows present anywhere in the fit


def expiry_diagnostics(
    rows,
    x_nodes: np.ndarray,
    t_grid: np.ndarray,
    vega_floor: float,
    prior_t_counts: dict[float, int] | None = None,
) -> list[AffineExpiryDiagnostics]:
    """Per-expiry diagnostics from the affine fit inputs (pure, deterministic).

    ``rows`` are the ``_gather`` 6-tuples ``(iso, tau, k, w, prepared, band)``
    (ascending tau, as ``_pde_grids`` requires); only ``iso, tau, k, w`` are read.
    ``x_nodes`` is the shared strike-vertex axis, ``t_grid`` the fine PDE time
    grid, ``vega_floor`` the absolute floor the fit applied, and
    ``prior_t_counts`` maps a prior option row's tau to its count (empty / None
    when no prior is active). Returns one record per row, in row order.
    """
    x = np.asarray(x_nodes, dtype=float)
    tg = np.asarray(t_grid, dtype=float)
    n_x = int(x.size)
    prior_t_counts = prior_t_counts or {}
    prior_active = bool(prior_t_counts)

    diags: list[AffineExpiryDiagnostics] = []
    prev = 0.0  # previous expiry's tau, for the per-segment time-step count
    for iso, tau, k, w, prepared, _band in rows:
        k = np.asarray(k, dtype=float)
        w = np.asarray(w, dtype=float)
        tau = float(tau)
        # Cause B: how many quotes the absolute vega floor underweights.
        vol = np.sqrt(np.maximum(w, 1e-12) / max(tau, 1e-12))
        vega = black_vega_sigma(k, vol, tau)
        n_floored = int(np.count_nonzero(np.asarray(vega) < vega_floor))
        n_q = int(k.size)
        # ATM vega = φ(d₊)·√τ at k = 0 (interp the traded w to ATM); falls back to
        # the kink value φ(0)·√τ when ATM is outside the quoted range.
        order = np.argsort(k)
        w_atm = float(np.interp(0.0, k[order], w[order]))
        d_atm = 0.5 * np.sqrt(max(w_atm, 1e-12))
        vega_atm = float(norm_pdf(d_atm) * np.sqrt(max(tau, 0.0)))
        # Cause A: strike vertices inside THIS expiry's traded range.
        k_lo, k_hi = float(k.min()), float(k.max())
        in_range = int(np.count_nonzero((x >= np.exp(k_lo)) & (x <= np.exp(k_hi))))
        # Cause C: PDE time steps resolving (prev, tau].
        n_steps = int(np.count_nonzero((tg > prev + 1e-12) & (tg <= tau + 1e-12)))
        prev = tau
        # Cause E: synthetic prior option rows targeting this expiry.
        n_prior = int(prior_t_counts.get(round(tau, 12), prior_t_counts.get(tau, 0)))
        t_cal = float(getattr(prepared, "t", tau)) if prepared is not None else tau
        diags.append(
            AffineExpiryDiagnostics(
                expiry=str(iso),
                t=t_cal,
                tau=tau,
                n_quotes=n_q,
                n_vega_floored=n_floored,
                vega_floor_frac=float(n_floored / n_q) if n_q else 0.0,
                vega_atm=vega_atm,
                vega_floor=float(vega_floor),
                k_lo=k_lo,
                k_hi=k_hi,
                n_vertices_in_range=in_range,
                n_vertices_total=n_x,
                n_time_steps=n_steps,
                n_prior_rows=n_prior,
                prior_active=prior_active,
            )
        )
    return diags
