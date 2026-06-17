"""The 3D surface mesh is quoted in the same event-variance clock as the Smile.

Regression for the t-vs-tau gap: surface.py used calendar t (sqrt(w/t)) while the
Smile/Term use the event-variance time tau (sqrt(w/tau)). With an event calendar
active (tau != t) the Surface tab disagreed with the Smile; now both use tau and
the Stacked-IV chart recovers the price total variance via the exposed tau.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api import service
from volfit.api.schemas import EventSpec
from volfit.api.state import AppState
from volfit.api.surface import surface_payload

REF = date(2026, 6, 10)
TICKER = "ALPHA"


def test_surface_mesh_uses_variance_clock_like_the_smile():
    state = AppState(REF)
    iso = [e.isoformat() for e in sorted(state.forwards(TICKER))][2]
    t_cal = state.year_fraction(date.fromisoformat(iso))
    state.set_events(TICKER, [EventSpec(time=t_cal * 0.5, weight=30)])  # 30 extra days

    surf = surface_payload(state, TICKER, "mid")
    i = surf.expiries.index(iso)
    assert surf.tau[i] > surf.t[i] + 1e-6  # the event clock dilated this node

    smile = service.smile_payload(state, TICKER, iso, "mid")
    mk = [p.k for p in smile.model]
    mv = [p.vol for p in smile.model]
    # The mesh vol equals the smile's displayed vol at matching strikes (both
    # sqrt(w / tau)); before the fix the mesh used sqrt(w / t) and diverged.
    for k in (-0.1, 0.0, 0.1):
        mesh_v = float(np.interp(k, surf.k, surf.vol[i]))
        smile_v = float(np.interp(k, mk, mv))
        assert abs(mesh_v - smile_v) < 1e-4, (k, mesh_v, smile_v)

    # The ATM marker agrees with the mesh at k=0 (both in the tau clock).
    assert abs(surf.atmVol[i] - float(np.interp(0.0, surf.k, surf.vol[i]))) < 1e-3

    # Stacked-IV recovers the price total variance: w = sigma^2 * tau, monotone
    # in the variance clock (non-crossing across expiries => no calendar arb).
    w0 = [v * v * tau for v, tau in zip([row[len(surf.k) // 2] for row in surf.vol], surf.tau)]
    assert all(b >= a - 1e-9 for a, b in zip(w0, w0[1:]))
