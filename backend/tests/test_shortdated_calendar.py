"""Short-dated calendar + band arc (2026-08 ruggedness follow-up).

Three opt-in knobs, every default byte-identical:

1. ``OptionsSettings.calendarFloorPadZ`` — winged overlay calendar floors:
   when set, BOTH overlay families (SVI and MCS) build their calendar floor
   AND ceiling grids with ``variance_floor_grid_winged`` at that pad, so the
   wing crossings a support-confined grid cannot see are enforced; None keeps
   the historical per-family scopes exactly.
2. ``OptionsSettings.calendarOnRefit`` — single-node refits keep calendar
   context: with ``enforceCalendar``, a lone ``_compute_fit`` threads the
   FRESH committed neighbour slices (selected ladder) as its confined floor
   (previous expiry) and ceiling (next), read-only, and folds a NEIGHBOUR
   FINGERPRINT into the fit key so a neighbour's changed fit invalidates the
   cached fit; toggle off, the key is the historical tuple unchanged.
3. ``FitSettings.bandTickFloorTicks`` — IV band half-width floor: each band
   quote is widened about its mid to at least that many price ticks of IV at
   its own (vega-floored) Black vega, AFTER the haircut, only ever widening;
   0 or a tickless chain is byte-identical.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backtest.replay import StaticProvider
from volfit.api import create_app, service
from volfit.api.quotes import apply_band_edits, prepare_quotes
from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.state import AppState
from volfit.calib.band import BandTarget, TICK_VEGA_FLOOR, apply_tick_floor, resolve_band
from volfit.calib.calendar import (
    FLOOR_WING_PAD_Z,
    calendar_violation_windowed,
    common_support,
    variance_floor_grid_common,
    variance_floor_grid_winged,
    variance_floor_targets,
)
from volfit.core.black import black_call, black_vega_sigma
from volfit.data.forwards import ImpliedForward
from volfit.data.types import ChainSnapshot, OptionQuote
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.svi_jw import RawSVI, calibrate_svi

REF_DATE = date(2026, 6, 10)


# ======================================================================
# 1. Winged overlay floors (calendarFloorPadZ)
# ======================================================================
# Near slice quoted WIDE and steep; far slice quoted NARROW and flat. Ordered
# on the common support, but the near slice crosses the far fit at k ~ -0.45 —
# outside the common support, inside a one-sigma wing pad: exactly the
# crossing a support-confined floor grid cannot see.
K_NEAR = np.linspace(-0.60, 0.60, 25)
K_FAR = np.linspace(-0.25, 0.20, 21)
NEAR_STEEP = RawSVI(a=0.01, b=0.20, rho=-0.7, m=0.0, sigma=0.05)
FAR_FLAT = RawSVI(a=0.08, b=0.08, rho=-0.3, m=0.0, sigma=0.10)
W_FAR = FAR_FLAT.total_variance(K_FAR)
T_FAR = 1.0


def test_winged_grid_default_pad_is_byte_identical():
    """No pad argument == the historical FLOOR_WING_PAD_Z grid, exactly."""
    base = variance_floor_grid_winged(K_NEAR, K_FAR, W_FAR, T_FAR)
    same = variance_floor_grid_winged(K_NEAR, K_FAR, W_FAR, T_FAR, pad_z=FLOOR_WING_PAD_Z)
    np.testing.assert_array_equal(base, same)


def test_winged_grid_extends_beyond_common_support():
    lo, hi = common_support(K_NEAR, K_FAR)
    common = variance_floor_grid_common(K_NEAR, K_FAR)
    assert common.min() == lo and common.max() == hi
    g1 = variance_floor_grid_winged(K_NEAR, K_FAR, W_FAR, T_FAR, pad_z=1.0)
    g3 = variance_floor_grid_winged(K_NEAR, K_FAR, W_FAR, T_FAR, pad_z=3.0)
    assert g1.min() < lo and g1.max() > hi  # winged past the support...
    assert g3.min() < g1.min() and g3.max() > g1.max()  # ...monotone in the pad
    assert g1.size == g3.size == common.size  # same node budget (V3.1 4a)


def test_winged_floor_repairs_a_wing_crossing_the_common_grid_misses():
    """The SVI fit changes under the winged floor and the wing crossing dies;
    the support-confined floor never sees it."""
    # Calendar-consistent where both are quoted, crossed in the near wing.
    assert np.all(FAR_FLAT.total_variance(K_FAR) > NEAR_STEEP.total_variance(K_FAR))
    assert NEAR_STEEP.total_variance(-0.45) > FAR_FLAT.total_variance(-0.45)

    gc = variance_floor_grid_common(K_NEAR, K_FAR)
    gw = variance_floor_grid_winged(K_NEAR, K_FAR, W_FAR, T_FAR, pad_z=1.0)

    def fit(grid):
        if grid is None:
            return calibrate_svi(K_FAR, W_FAR, t=T_FAR)
        return calibrate_svi(
            K_FAR, W_FAR, t=T_FAR,
            calendar_k=grid, calendar_floor=variance_floor_targets(NEAR_STEEP, grid)[1],
        )

    def wing_viol(res):  # worst drop below the near slice on the WINGED grid
        fk, fw = variance_floor_targets(NEAR_STEEP, gw)
        return float(np.max(fw - res.raw.total_variance(fk)))

    free, on_common, on_winged = fit(None), fit(gc), fit(gw)
    assert wing_viol(free) > 1e-2  # the crossing is real
    assert wing_viol(on_common) > 0.5 * wing_viol(free)  # confined grid: blind
    assert wing_viol(on_winged) < 1e-4  # winged grid: repaired
    p = lambda r: np.array([r.raw.a, r.raw.b, r.raw.rho, r.raw.m, r.raw.sigma])
    assert not np.array_equal(p(on_winged), p(on_common))  # the fit changed


@pytest.mark.parametrize("model", ["svi", "sigmoid"])
def test_pad_option_wings_both_overlay_families(model):
    """Service wiring: pad None == the historical per-family grid arrays
    byte-identically; a pad set wings floor AND ceiling for BOTH families."""
    state = AppState(REF_DATE)
    state.set_fit_settings(FitSettings(model=model))
    exps = sorted(state.selected_expiries("ALPHA"))
    e1, e2 = exps[1].isoformat(), exps[2].isoformat()
    rec1 = service.fit_or_get(state, "ALPHA", e1, "mid")
    prepared2 = service.prepare_slice(state, "ALPHA", e2)

    def grids():
        task = service._slice_task(
            state, "ALPHA", e2, prepared2, "mid",
            prev_display=rec1.display, prev_k=rec1.prepared.k,
            next_display=rec1.display, next_k=rec1.prepared.k,
            enforce_calendar=True, with_fit=False,
        )
        return task.overlay["calendar_floor"][0], task.overlay["calendar_ceiling"][0]

    f0, c0 = grids()
    k2, w2, _ = service.edited_fit_inputs(state, "ALPHA", e2, prepared2, None)
    hist = (
        variance_floor_grid_common(rec1.prepared.k, k2)
        if model == "svi"
        else variance_floor_grid_winged(rec1.prepared.k, k2, w2, prepared2.tau)
    )
    np.testing.assert_array_equal(f0, hist)  # pad None: historical branch
    np.testing.assert_array_equal(c0, hist)

    state.set_options(OptionsSettings(calendarFloorPadZ=5.0))
    f1, c1 = grids()
    assert f1.min() < f0.min() and f1.max() > f0.max()
    assert c1.min() < c0.min() and c1.max() > c0.max()
    assert f1.size == f0.size  # node budget unchanged


# ======================================================================
# 2. Calendar context on single-node refits (calendarOnRefit)
# ======================================================================
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _record(state, iso):
    return state.get_fit(state.get_calibrated_ptr("ALPHA", iso, "mid")[0])


def test_neighbour_isos_walk_the_selected_ladder():
    state = AppState(REF_DATE)
    isos = [d.isoformat() for d in sorted(state.selected_expiries("ALPHA"))]
    assert service._neighbour_isos(state, "ALPHA", isos[0]) == (None, isos[1])
    assert service._neighbour_isos(state, "ALPHA", isos[2]) == (isos[1], isos[3])
    assert service._neighbour_isos(state, "ALPHA", isos[-1]) == (isos[-2], None)


def test_refit_context_respects_the_committed_floor(client):
    """Amended wing quotes pull the short slice above the long one; without
    the toggle a single-node refit of the long slice keeps the crossing (and
    its fit key never moves), with it the refit respects the floor and the
    key fingerprints the neighbours (cache correctness)."""
    exps = [e["expiry"] for e in client.get("/universe").json()["expiries"]["ALPHA"]]
    e1, e2 = exps[1], exps[2]  # adjacent mid-ladder nodes
    state = client.app.state.volfit
    d1 = client.get(f"/smiles/ALPHA/{e1}").json()
    client.get(f"/smiles/ALPHA/{e2}")
    win = common_support(_record(state, e1).prepared.k, _record(state, e2).prepared.k)
    key2_start = service.fit_key(state, "ALPHA", e2, "mid")
    assert key2_start == service._base_fit_key(state, "ALPHA", e2, "mid")  # OFF: no fingerprint

    # Drag the short expiry's put wing up hard -> an identified calendar
    # crossing against the (unchanged) long slice on the common support.
    for i in range(4):
        client.post(
            f"/smiles/ALPHA/{e1}/edits",
            json={"action": "amend", "index": i, "mid": d1["quotes"][i]["mid"] + 0.30},
        )
    client.get(f"/smiles/ALPHA/{e1}")  # refit the short node under its session
    viol = calendar_violation_windowed(
        _record(state, e1).result.slice, _record(state, e2).result.slice, win
    )
    assert viol > 5e-3  # the crossing is real

    # TOGGLE OFF (current behaviour): the long node's key ignores the
    # neighbour entirely, so an explicit single-node recalibrate cache-hits
    # and the crossing survives.
    assert service.fit_key(state, "ALPHA", e2, "mid") == key2_start
    ptr_before = state.get_calibrated_ptr("ALPHA", e2, "mid")[0]
    client.post(f"/calibrate/ALPHA/{e2}")
    assert state.get_calibrated_ptr("ALPHA", e2, "mid")[0] == ptr_before
    still = calendar_violation_windowed(
        _record(state, e1).result.slice, _record(state, e2).result.slice, win
    )
    assert still == pytest.approx(viol)

    # TOGGLE ON: re-commit the short node fresh under the new options, then a
    # single-node recalibrate of the long node threads it as a floor.
    client.put("/settings/options", json={"calendarOnRefit": True})
    client.post(f"/calibrate/ALPHA/{e1}")
    key_on = service.fit_key(state, "ALPHA", e2, "mid")
    fingerprint = key_on[len(key2_start):]
    assert len(fingerprint) == 1 and fingerprint[0][0] is not None  # prev side used
    assert fingerprint[0][0][0] == e1
    client.post(f"/calibrate/ALPHA/{e2}")
    repaired = calendar_violation_windowed(
        _record(state, e1).result.slice, _record(state, e2).result.slice, win
    )
    assert repaired < max(1e-4, 0.02 * viol)

    # CACHE CORRECTNESS: a neighbour's changed fit moves this node's key and
    # marks it stale, so the cached fit cannot be served against a moved floor.
    d1b = client.get(f"/smiles/ALPHA/{e1}").json()
    client.post(
        f"/smiles/ALPHA/{e1}/edits",
        json={"action": "amend", "index": 4, "mid": d1b["quotes"][4]["mid"] + 0.30},
    )
    client.post(f"/calibrate/ALPHA/{e1}")
    assert service.fit_key(state, "ALPHA", e2, "mid") != key_on
    assert service.node_dirty(state, "ALPHA", e2, "mid")


def test_toggle_off_key_is_the_historical_tuple(client):
    """calendarOnRefit False (default): fit_key == _base_fit_key even when a
    fresh committed neighbour exists — byte-identical to the historical key."""
    exps = [e["expiry"] for e in client.get("/universe").json()["expiries"]["ALPHA"]]
    client.get(f"/smiles/ALPHA/{exps[1]}")  # a fresh committed neighbour
    state = client.app.state.volfit
    for iso in exps[:3]:
        assert service.fit_key(state, "ALPHA", iso, "mid") == service._base_fit_key(
            state, "ALPHA", iso, "mid"
        )


# ======================================================================
# 3. IV band tick floor (bandTickFloorTicks)
# ======================================================================
EXPIRY = date(2026, 9, 10)
TS = datetime(2026, 6, 10, 20, 0)
F = 100.0
T = 92.0 / 365.0
TICK = 0.01
TICK_NORM = TICK / F  # discount 1, forward 100


def _sigma(k: float) -> float:
    return 0.25 - 0.15 * k


def _price(strike: float, cp: str, sigma: float) -> float:
    k = np.log(strike / F)
    c = float(black_call(np.array([k]), np.array([sigma * sigma * T]))[0])
    return (c if cp == "C" else c - 1.0 + strike / F) * F


def _ticked_chain(spike: float = 0.0, both_sides: bool = False) -> ChainSnapshot:
    """OTM chain with 1.2-tick wing spreads (sub-tick IV certainty), a wide
    ATM band, and an optional +vol spike on the far call; tick_size = 0.01."""
    quotes = []
    for strike in range(80, 121, 4):
        sig = _sigma(float(np.log(strike / F))) + (spike if strike == 120 else 0.0)
        half = 0.30 if 96 <= strike <= 104 else 0.006  # wide ATM / 1.2-tick wings
        sides = ("C", "P") if both_sides else ("C" if strike >= F else "P",)
        for cp in sides:
            mid = _price(float(strike), cp, sig)
            quotes.append(OptionQuote(ticker="XYZ", expiry=EXPIRY, strike=float(strike),
                                      call_put=cp, bid=max(mid - half, 0.001), ask=mid + half))
    return ChainSnapshot(ticker="XYZ", spot=F, timestamp=TS, quotes=quotes,
                         exercise_style="european", tick_size=TICK)


def _prepared(spike: float = 0.0):
    fwd = ImpliedForward(expiry=EXPIRY, forward=F, discount=1.0, n_strikes=11,
                         residual_rms=0.0)
    return prepare_quotes(_ticked_chain(spike), EXPIRY, fwd, T)


def test_apply_tick_floor_disengaged_is_the_same_object():
    band = resolve_band(np.array([0.19]), np.array([0.20]), np.array([0.21]), "bidask")
    k = np.array([0.0])
    assert apply_tick_floor(band, k, T, TICK_NORM, 0.0) is band  # ticks 0
    assert apply_tick_floor(band, k, T, None, 3.0) is band  # tickless chain
    assert apply_tick_floor(None, k, T, TICK_NORM, 3.0) is None  # mid mode


def test_apply_tick_floor_formula_and_asymmetry():
    """h = ticks * tick_norm / max(vega, floor) about MID; each side only ever
    widens, so a side already wider than the floor keeps the market's edge."""
    k = np.array([0.0, 0.25])
    mid = np.array([0.20, 0.24])
    lo = np.array([0.14, 0.2395])  # ATM wide; wing lo sub-tick-tight
    hi = np.array([0.2005, 0.32])  # ATM hi tight; wing hi already wide
    band = BandTarget(iv_lo=lo, iv_mid=mid, iv_hi=hi)
    out = apply_tick_floor(band, k, T, TICK_NORM, 4.0)
    vega = np.maximum(black_vega_sigma(k, mid, T), TICK_VEGA_FLOOR)
    h = 4.0 * TICK_NORM / vega
    np.testing.assert_allclose(out.iv_lo, np.minimum(lo, mid - 0.5 * h))
    np.testing.assert_allclose(out.iv_hi, np.maximum(hi, mid + 0.5 * h))
    assert out.iv_lo[0] == lo[0] and out.iv_hi[1] == hi[1]  # wide sides untouched
    assert out.iv_hi[0] > hi[0] and out.iv_lo[1] < lo[1]  # tight sides floored
    np.testing.assert_array_equal(out.iv_mid, mid)  # the anchor never moves


def test_band_edits_zero_ticks_byte_identical_and_floor_widens_wings():
    prepared = _prepared()
    assert prepared.tick_size == TICK and prepared.screened == ()
    base = apply_band_edits(prepared, {}, "bidask")
    same = apply_band_edits(prepared, {}, "bidask", tick_floor_ticks=0.0)
    np.testing.assert_array_equal(base.iv_lo, same.iv_lo)  # 0 = byte-identical
    np.testing.assert_array_equal(base.iv_hi, same.iv_hi)
    floored = apply_band_edits(prepared, {}, "bidask", tick_floor_ticks=10.0)
    w0, w1 = base.iv_hi - base.iv_lo, floored.iv_hi - floored.iv_lo
    atm = np.abs(prepared.k) < 0.05  # wide-band belly rows: untouched
    assert np.all(w1[atm] == w0[atm])
    assert np.all(w1[~atm] > w0[~atm])  # every sub-floor wing row widened
    assert np.all(w1 >= w0)  # the floor only ever widens


def test_tick_floor_changes_the_fit_on_a_sub_tick_wing_spike():
    """A spiked far-wing quote with a 1.2-tick spread drags the band fit; the
    tick floor widens its band so the fit stops chasing sub-tick certainty."""
    prepared = _prepared(spike=0.04)
    raw = apply_band_edits(prepared, {}, "bidask")
    floored = apply_band_edits(prepared, {}, "bidask", tick_floor_ticks=10.0)
    fit_raw = calibrate_slice(prepared.k, prepared.w_mid, t=prepared.tau, band=raw)
    fit_flr = calibrate_slice(prepared.k, prepared.w_mid, t=prepared.tau, band=floored)
    assert not np.array_equal(fit_raw.params.to_vector(), fit_flr.params.to_vector())
    j = int(np.argmax(prepared.k))  # the spiked strike
    iv = lambda fit: float(np.sqrt(fit.slice.implied_w(prepared.k[j : j + 1]) / prepared.tau)[0])
    # The floored fit sits further from the spiked mid (the widened band lets
    # the smooth smile win); identical inputs elsewhere.
    assert abs(iv(fit_flr) - prepared.iv_mid[j]) > abs(iv(fit_raw) - prepared.iv_mid[j])


class _TickedProvider(StaticProvider):
    """StaticProvider whose expiry filter keeps the chain METADATA (its
    filtered branch rebuilds the snapshot without ``tick_size``, which this
    test needs intact — the fixture chain is single-expiry anyway)."""

    def fetch_chain(self, ticker, expiries=None, as_of=None):
        return self._chains[ticker]


def test_service_threads_the_settings_tick_floor():
    """FitSettings.bandTickFloorTicks reaches the fit-path band via
    service.edited_band, applied AFTER the haircut so the floor wins."""
    state = AppState(REF_DATE, provider=_TickedProvider({"XYZ": _ticked_chain(both_sides=True)}))
    state.set_expiries("XYZ", [EXPIRY])
    state.ensure_chain("XYZ")
    iso = EXPIRY.isoformat()
    prepared = service.prepare_slice(state, "XYZ", iso)
    assert prepared is not None and prepared.tick_size == TICK
    b0 = service.edited_band(state, "XYZ", iso, prepared, "haircut")
    state.set_fit_settings(FitSettings(bandTickFloorTicks=8.0))
    b1 = service.edited_band(state, "XYZ", iso, prepared, "haircut")
    w0, w1 = b0.iv_hi - b0.iv_lo, b1.iv_hi - b1.iv_lo
    wing = np.abs(prepared.k) > 0.1
    # The default 0.5-pt haircut collapses the 1.2-tick wing bands to (mid,
    # mid); the floor re-opens them to the 8-tick IV width — after the
    # haircut, so the floor wins.
    assert np.all(w0[wing] == 0.0) and np.all(w1[wing] > 0.0)
    assert np.all(w1 >= w0)
    # The full-index band (fit-target overlay) follows the same rule.
    full = service.edited_band_full(state, "XYZ", iso, prepared, "haircut")
    np.testing.assert_array_equal(full.iv_lo, b1.iv_lo)
    np.testing.assert_array_equal(full.iv_hi, b1.iv_hi)
