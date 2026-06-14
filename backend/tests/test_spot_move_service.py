"""Integration tests: a spot move transports the calibrated views without refit.

Exercises volfit.api.service.fit_or_get / smile_payload / analytics / localvol
end-to-end on the synthetic provider: setting a per-ticker spot shift moves the
forward, the smile, the term ATM and the local-vol grid per the note's regimes,
while the cached anchor calibration is reused (transported, never re-fitted).
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from volfit.api import analytics, localvol, service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"
SHIFT = 0.02  # +2% spot move


def _state() -> AppState:
    return AppState(REF_DATE)


def _iso(state: AppState) -> str:
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][1]  # ~3M


def _vol_at(curve, k: float) -> float:
    ks = np.array([p.k for p in curve])
    vs = np.array([p.vol for p in curve])
    return float(np.interp(k, ks, vs))


def test_forward_moves_multiplicatively_under_continuous_yield():
    state = _state()
    iso = _iso(state)
    f0 = service.smile_payload(state, TICKER, iso, "mid").forward
    state.set_spot_shift(TICKER, SHIFT)
    f1 = service.smile_payload(state, TICKER, iso, "mid").forward
    assert f1 == pytest.approx(f0 * (1.0 + SHIFT), rel=1e-9)


def test_sticky_strike_fixes_vol_at_fixed_strike():
    """Default regime is sticky-strike: the vol at a fixed strike is unchanged.

    A fixed strike's new moneyness is k0 - h (h = log(F1/F0)); the moved smile
    there must equal the anchor smile at k0.
    """
    state = _state()
    iso = _iso(state)
    base = service.smile_payload(state, TICKER, iso, "mid")
    h = np.log(1.0 + SHIFT)
    state.set_spot_shift(TICKER, SHIFT)
    moved = service.smile_payload(state, TICKER, iso, "mid")
    for k0 in (-0.1, -0.03, 0.0, 0.05):
        assert _vol_at(moved.model, k0 - h) == pytest.approx(_vol_at(base.model, k0), abs=2e-4)


def test_sticky_moneyness_leaves_smile_in_moneyness_unchanged():
    state = _state()
    state.set_options(state.options().model_copy(update={"dynamicsRegime": "sticky_moneyness"}))
    iso = _iso(state)
    base = service.smile_payload(state, TICKER, iso, "mid")
    state.set_spot_shift(TICKER, SHIFT)
    moved = service.smile_payload(state, TICKER, iso, "mid")
    for k in (-0.1, 0.0, 0.08):
        assert _vol_at(moved.model, k) == pytest.approx(_vol_at(base.model, k), abs=2e-4)


def test_sticky_strike_atm_drops_for_spot_up_equity_skew():
    """Spot up with negative skew lowers the new ATM vol (sticky strike)."""
    state = _state()
    iso = _iso(state)
    base_atm = service.smile_payload(state, TICKER, iso, "mid").diagnostics.atmVol
    state.set_spot_shift(TICKER, SHIFT)
    moved_atm = service.smile_payload(state, TICKER, iso, "mid").diagnostics.atmVol
    assert moved_atm < base_atm  # negative skew + spot up => ATM down


def test_term_structure_follows_the_move():
    state = _state()
    from volfit.api.schemas import TermStructureRequest

    base = analytics.term_structure(state, TICKER, TermStructureRequest(fitMode="mid"))
    state.set_spot_shift(TICKER, SHIFT)
    moved = analytics.term_structure(state, TICKER, TermStructureRequest(fitMode="mid"))
    # Every expiry's ATM vol changes (sticky strike, equity skew => all drop).
    assert all(m.atmVol < b.atmVol for m, b in zip(moved.points, base.points))


def test_localvol_grid_reextracts_after_move():
    state = _state()
    base = localvol.localvol_payload(state, TICKER, "mid")
    state.set_spot_shift(TICKER, SHIFT)
    moved = localvol.localvol_payload(state, TICKER, "mid")
    # The extraction grid recenters on the new forward (quotes re-indexed by -h).
    assert moved.k[0] < base.k[0] - 1e-6


def test_reset_restores_the_anchor():
    state = _state()
    iso = _iso(state)
    f0 = service.smile_payload(state, TICKER, iso, "mid").forward
    state.set_spot_shift(TICKER, SHIFT)
    state.set_spot_shift(TICKER, 0.0)
    assert service.smile_payload(state, TICKER, iso, "mid").forward == pytest.approx(f0, rel=1e-12)


def test_anchor_model_overlaid_only_when_spot_moved():
    """The pre-transport calibration is exposed (for the dimmed overlay) only
    while a spot move is active, and sticky-strike makes it a lateral shift."""
    state = _state()
    iso = _iso(state)
    assert service.smile_payload(state, TICKER, iso, "mid").anchorModel is None

    state.set_spot_shift(TICKER, SHIFT)
    moved = service.smile_payload(state, TICKER, iso, "mid")
    assert moved.anchorModel is not None
    # Sticky strike: transported(k0 - h) == anchor(k0) (a lateral translation).
    h = np.log(1.0 + SHIFT)
    for k0 in (-0.05, 0.0, 0.05):
        assert _vol_at(moved.model, k0 - h) == pytest.approx(
            _vol_at(moved.anchorModel, k0), abs=2e-4
        )


def test_affine_lv_surface_transports_without_refit():
    """The Local-Vol (affine) surface moves on a spot shift via the grid rule."""
    from volfit.api.affine_fit import affine_payload
    from volfit.api.schemas_affine import AffineFitRequest

    state = _state()
    req = AffineFitRequest()
    base = affine_payload(state, TICKER, req)
    state.set_spot_shift(TICKER, SHIFT)
    moved = affine_payload(state, TICKER, req)

    # Sticky-strike (R=1), spot up: nodal grid relabels to lower x = K/F
    # (x' = x e^{-(R/2) h}); quotes re-index to lower moneyness (k - h).
    assert moved.xNodes[0] < base.xNodes[0] - 1e-9
    assert moved.smiles[0].quotes[0].k < base.smiles[0].quotes[0].k - 1e-9

    # Fixed-strike invariance of the reconstructed smile (sticky strike): the
    # moved vol at k0 - h equals the anchor vol at k0.
    h = np.log(1.0 + SHIFT)
    b, m = base.smiles[1], moved.smiles[1]
    bk = np.array([p.k for p in b.model])
    bv = np.array([p.vol for p in b.model])
    mk = np.array([p.k for p in m.model])
    mv = np.array([p.vol for p in m.model])
    for k0 in (-0.05, 0.0, 0.05):
        assert float(np.interp(k0 - h, mk, mv)) == pytest.approx(
            float(np.interp(k0, bk, bv)), abs=5e-4
        )


def test_anchor_fit_is_reused_not_refitted():
    """The cached anchor calibration is shared across spot moves (no refit)."""
    state = _state()
    iso = _iso(state)
    anchor = service._compute_fit(state, TICKER, iso, "mid")
    state.set_spot_shift(TICKER, SHIFT)
    again = service._compute_fit(state, TICKER, iso, "mid")
    assert again is anchor  # same cached object: transport never re-fits
