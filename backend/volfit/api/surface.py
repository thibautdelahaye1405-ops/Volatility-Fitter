"""3D vol-surface mesh over the fitted expiry ladder (Phase 6 [REQ 2026-06-12]).

Backs GET /surface/{ticker}: every listed expiry's slice fit (cached via
volfit.api.service.fit_or_get, so the mesh is always consistent with what
the Smile Viewer charts) sampled on ONE shared log-moneyness grid, giving
the 3D chart a full rectangular sigma(k, T) mesh.

The shared grid spans the UNION of the per-expiry quoted k ranges, padded
by service.K_PAD: short expiries quote a narrow strike range and long ones
a wide one, but evaluating an LQD slice beyond its quoted range is well
defined (the model extrapolates arbitrage-free Lee wings), so the union
grid is the right trade-off — no expiry's quoted range is cropped and no
mesh cell is missing.

Lives outside service.py purely for the file-size policy; same conventions
(pure functions over AppState returning pydantic response models).
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import SurfaceResponse
from volfit.api.service import K_PAD, displayed_atm_vol, displayed_slice, fit_or_get
from volfit.api.state import AppState

#: Shared k-grid density: 61 points is plenty for a smooth 3D mesh while
#: keeping the payload (n_expiries x 61 floats) chart-light.
N_SURFACE_POINTS = 61


def surface_payload(state: AppState, ticker: str, fit_mode: str) -> SurfaceResponse:
    """Assemble the sigma(k, T) mesh for one ticker, nearest expiry first."""
    forwards = state.forwards(ticker)  # raises UnknownNodeError when unknown
    isos = [expiry.isoformat() for expiry in sorted(forwards)]
    records = [fit_or_get(state, ticker, iso, fit_mode) for iso in isos]

    # Union k range across expiries, padded like the per-smile display grid.
    k_lo = min(float(r.prepared.k.min()) for r in records) - K_PAD
    k_hi = max(float(r.prepared.k.max()) for r in records) + K_PAD
    grid = np.linspace(k_lo, k_hi, N_SURFACE_POINTS)

    vol: list[list[float]] = []
    atm: list[float] = []
    for record in records:
        t = record.prepared.t
        vol.append(np.sqrt(displayed_slice(record).implied_w(grid) / t).tolist())
        atm.append(displayed_atm_vol(record))  # exact ATM (LQD) or numeric (overlay)

    return SurfaceResponse(
        ticker=ticker,
        expiries=isos,
        t=[record.prepared.t for record in records],
        k=grid.tolist(),
        vol=vol,
        atmVol=atm,
        forward=[record.prepared.forward for record in records],
    )
