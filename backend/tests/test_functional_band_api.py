"""Functional-band API wiring (R3 item 12): graph drill-in + filter overlay.

Contracts locked here:
  - band-only: the posterior CURVE and handles are identical whether the
    functional band is on or off (the idio-floor discipline);
  - the default drill-in band is the functional pushforward (kind, var-swap /
    tail-mass sds present, straddles the posterior);
  - ``functionalBand=false`` routes to the legacy ATM-level band exactly
    (its ATM half-width is 1.96 sd by construction);
  - the wings of a functional band carry the skew/curv uncertainty the level
    band cannot see (wing half-width >= a level band's parallel floor is NOT
    asserted — the honest statement is that widths differ only in the wings).
"""

from datetime import date

import numpy as np
import pytest

from volfit.api import priors
from volfit.api.graph_reconstruct import node_smile
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
Z_95 = 1.96


@pytest.fixture()
def primed() -> AppState:
    state = AppState(REF_DATE)
    for tk in state.active_tickers():
        snap = priors.capture_snapshot(state, tk, "mid")
        if snap is not None:
            state.set_active_prior(tk, snap, "saved")
    return state


def _isos(state, tk):
    return [e.isoformat() for e in sorted(state.forwards(tk))]


def _dark_smile(state, functional: bool):
    tk = state.active_tickers()[0]
    iso = _isos(state, tk)[1]
    state.set_node_lit(tk, iso, False)
    return node_smile(
        state, tk, iso, GraphExtrapolateRequest(functionalBand=functional)
    )


def _vols(points):
    return np.array([p.vol for p in points])


def test_default_band_is_functional_with_functionals(primed):
    smile = _dark_smile(primed, functional=True)
    assert smile.bandKind == "functional"
    assert len(smile.postBandLo) == len(smile.post) == len(smile.postBandHi) > 0
    ks = np.array([p.k for p in smile.post])
    atm = int(np.argmin(np.abs(ks)))
    assert smile.postBandLo[atm].vol <= smile.post[atm].vol <= smile.postBandHi[atm].vol
    # The pushforward's derived functionals ride the payload.
    assert smile.varSwapVol is not None and smile.varSwapVol > 0.0
    assert smile.varSwapVolSd is not None and smile.varSwapVolSd >= 0.0
    assert smile.tailMassLeft is not None and 0.0 <= smile.tailMassLeft <= 1.0
    assert smile.tailMassRight is not None and 0.0 <= smile.tailMassRight <= 1.0
    assert smile.tailMassLeftSd is not None and smile.tailMassRightSd is not None
    # Full marginal sds surfaced alongside the ATM one.
    assert smile.sdSkew is not None and smile.sdSkew >= 0.0
    assert smile.sdCurv is not None and smile.sdCurv >= 0.0


def test_escape_hatch_is_the_level_band(primed):
    smile = _dark_smile(primed, functional=False)
    assert smile.bandKind == "level"
    assert smile.varSwapVol is None and smile.varSwapVolSd is None
    ks = np.array([p.k for p in smile.post])
    atm = int(np.argmin(np.abs(ks)))
    width = smile.postBandHi[atm].vol - smile.postBandLo[atm].vol
    # Level band: sigma0 +/- 1.96 sd retargeted exactly -> ATM width 2 x 1.96 sd.
    assert width == pytest.approx(2.0 * Z_95 * smile.sd, rel=5e-2)


def test_band_toggle_is_band_only(primed):
    """The idio-floor discipline: toggling the band NEVER moves the posterior."""
    on = _dark_smile(primed, functional=True)
    off = _dark_smile(primed, functional=False)
    np.testing.assert_array_equal(_vols(on.post), _vols(off.post))
    assert on.postAtmVol == off.postAtmVol
    assert on.postSkew == off.postSkew
    assert on.postCurv == off.postCurv
    assert on.sd == off.sd


def test_functional_atm_width_matches_level_at_the_money(primed):
    """dIV(0)/dsigma0 = 1, so both constructions agree at the money to first
    order — the functional band differs from the level band only in the wings."""
    on = _dark_smile(primed, functional=True)
    off = _dark_smile(primed, functional=False)
    ks = np.array([p.k for p in on.post])
    atm = int(np.argmin(np.abs(ks)))
    w_on = on.postBandHi[atm].vol - on.postBandLo[atm].vol
    w_off = off.postBandHi[atm].vol - off.postBandLo[atm].vol
    assert w_on == pytest.approx(w_off, rel=8e-2)


def test_filter_overlay_band_uses_the_full_covariance(primed):
    """The filter drill-in band survives the upgrade: present, straddling,
    finite (semantic lock — its construction is now the functional pushforward
    of the stored 3x3 covariance)."""
    from volfit.api.observation_filter import _overlay_curves
    from volfit.api.service import fit_or_get

    tk = primed.active_tickers()[0]
    iso = _isos(primed, tk)[0]
    record = fit_or_get(primed, tk, iso, "mid")
    assert record is not None

    from dataclasses import dataclass

    @dataclass
    class _State:
        mean: np.ndarray
        cov: np.ndarray
        provenance: str = "test"
        reset_reason: str | None = None

    @dataclass
    class _Holder:
        state: _State
        prediction: object = None

    from volfit.models.lqd.atm import atm_handles
    from volfit.models.lqd.quadrature import build_slice

    h = atm_handles(build_slice(record.result.params), float(record.prepared.tau))
    mean = np.array([h.sigma0, h.skew, h.curvature])
    cov = np.diag([0.01**2, 0.02**2, 0.15**2])
    cov[0, 1] = cov[1, 0] = 0.5 * 0.01 * 0.02  # a real cross-term
    holder = _Holder(state=_State(mean=mean, cov=cov))

    post, lo, hi, _pred = _overlay_curves(primed, tk, iso, "mid", holder)
    assert len(post) == len(lo) == len(hi) > 0
    vols = _vols(post)
    assert np.all(_vols(lo) <= vols + 1e-12)
    assert np.all(vols <= _vols(hi) + 1e-12)
    # Wing widths exceed the ATM width: skew/curv uncertainty reaches the wings.
    ks = np.array([p.k for p in post])
    atm = int(np.argmin(np.abs(ks)))
    width = _vols(hi) - _vols(lo)
    assert width[0] > width[atm]
    assert width[-1] > width[atm]
