"""Quote-band relaxation infeasibility diagnostic (calib.band_relaxation;
V3.0 rider, book ch. 2 §calendar: "the smallest quote-band relaxation needed
for feasibility"). Locks:

1. A RIGGED uncertifiable pair in a band mode — the far expiry quoted at
   0.9x the near total variance (a calendar crossing everywhere), both
   slices held by HEAVY band rows in a +-1 vol-bp tube with the mid anchor
   off, so the exchange's rank/interface rows cannot trade the crossing
   against the bands — fails at delta = 0 and the bisection returns a
   delta > 0 with the exact bracket invariant: the pair certifies when
   re-run at ``delta_vol`` and does not at ``delta_infeasible``.
2. A certified pair returns delta 0.0 with NO solve; a gated pair whose tail
   clause is decided by unequal exponents is infeasible with NO solve.
3. ``widen_spec`` never mutates the caller's specs.
4. API, flag off (and flag on, clean ladder): ``state._band_relaxation``
   stays empty, the quality payload fields are None, the committed thetas
   are byte-identical between the two states, the options version is the
   same (the flag never bumps it).
5. API, flag on in haircut mode with a refuted pair: the diagnostic is
   recorded under (ticker, far_iso, fit_mode) with the gate flag threaded,
   rides the quality row (``bandRelaxationVol``) and the export node, and
   its hint decorates the certificate issue.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import numpy as np
import pytest

from tests import benchmarks as bm
from volfit.api import export, quality, service, surface_symmetric
from volfit.api.state import AppState
from volfit.calib.band import BandTarget
from volfit.calib.band_relaxation import (
    DELTA_MAX,
    BandRelaxation,
    pair_feasible_at,
    relax_pair,
    widen_spec,
)
from volfit.calib.calendar import CAL_STRIDE
from volfit.calib.calendar_certificate import ledger_certificate
from volfit.calib.symmetric import SliceSpec, _spec_params
from volfit.calib.symmetric_exchange import _CAL_TOL
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.lqd.quadrature import build_slice

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"

K = np.linspace(*bm.SVI_FIT_RANGE, 41)
W_NEAR = bm.SVI_RAW.total_variance(K)
W_FAR = 0.9 * W_NEAR  # far total variance BELOW near everywhere: crossed
T_NEAR, T_FAR = 0.5, 1.0
#: Half-width of the rigged tube (1 vol bp) and the band-row weight that
#: makes the tube effectively hard against the exchange's 1e6-scale rows.
TUBE = 1e-4
HEAVY = 1e6
BISECT_ROUNDS = 5


def _band(w, t, half: float) -> BandTarget:
    iv = np.sqrt(np.asarray(w, dtype=float) / t)
    return BandTarget(iv_lo=iv - half, iv_mid=iv, iv_hi=iv + half)


def _spec(
    t, k, w, half: float = TUBE, heavy: bool = True, n_order: int = 6, **kw
) -> SliceSpec:
    fit_kwargs = dict(n_order=n_order, band=_band(w, t, half), **kw)
    if heavy:
        # Mid anchor OFF: inside the tube the curves are free, so a wide
        # enough tube contains an ordered configuration (the diagnostic's
        # question); the heavy weights make the tube the binding rows.
        fit_kwargs.update(weights=np.full(np.size(k), HEAVY), mid_anchor_weight=0.0)
    return SliceSpec(
        t=t, k=np.asarray(k, dtype=float), w=np.asarray(w, dtype=float),
        fit_kwargs=fit_kwargs,
    )


@pytest.fixture(scope="module")
def crossed():
    """Independent (mid) fits of the crossed pair + the heavy-tube specs +
    the diagnostic run once (the expensive part, shared by the locks)."""
    near = calibrate_slice(K, W_NEAR, t=T_NEAR, n_order=6)
    far = calibrate_slice(K, W_FAR, t=T_FAR, n_order=6)
    specs = [_spec(T_NEAR, K, W_NEAR), _spec(T_FAR, K, W_FAR)]
    thetas = [near.params.to_vector(), far.params.to_vector()]
    rel = relax_pair(
        specs[0], specs[1], thetas[0], thetas[1],
        tail_gate=False, rounds=BISECT_ROUNDS,
    )
    return specs, thetas, rel


def _isos(state: AppState) -> list[str]:
    return [e.isoformat() for e in sorted(state.forwards(TICKER))]


def _state(flag: bool) -> AppState:
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={
        "autoCalibrate": False, "fitMode": "haircut", "bandRelaxationDiagnostic": flag,
    }))
    return state


# ------------------------------------------- 1. rigged pair + bisection invariant
def test_crossed_pair_is_uncertifiable_inside_the_tube(crossed):
    specs, thetas, _rel = crossed
    slices = [build_slice(_spec_params(t, s.fit_kwargs)) for t, s in zip(thetas, specs)]
    cert = ledger_certificate(slices[0], slices[1])
    assert not cert.certified(_CAL_TOL) and cert.min_gap < -1e-3  # crossed everywhere
    ok0, gap0 = pair_feasible_at(specs[0], specs[1], thetas, 0.0, tail_gate=False)
    assert not ok0 and gap0 < -_CAL_TOL  # the heavy tube holds the crossing


def test_bisection_returns_the_smallest_feasible_widening(crossed):
    specs, thetas, rel = crossed
    assert isinstance(rel, BandRelaxation)
    assert rel.feasible and rel.delta_vol is not None
    assert 0.0 < rel.delta_vol <= DELTA_MAX
    assert rel.delta_vol > 10.0 * TUBE  # a real widening, not the tube's own width
    assert rel.delta_infeasible is not None and rel.delta_infeasible < rel.delta_vol
    # Bracket resolution: delta_max / 2**rounds; solves = delta 0 + delta_max + rounds.
    assert rel.delta_vol - rel.delta_infeasible <= DELTA_MAX / 2**BISECT_ROUNDS + 1e-12
    assert rel.rounds == 2 + BISECT_ROUNDS
    assert rel.certificate_gap_at_delta >= -_CAL_TOL
    assert rel.delta_max == DELTA_MAX and rel.tail_gated is False
    # The bracket invariant, re-run from the same thetas (deterministic solves).
    ok_hi, gap_hi = pair_feasible_at(specs[0], specs[1], thetas, rel.delta_vol, False)
    assert ok_hi and gap_hi >= -_CAL_TOL
    ok_lo, _gap_lo = pair_feasible_at(specs[0], specs[1], thetas, rel.delta_infeasible, False)
    assert not ok_lo


# ------------------------------------------------ 2. decided without a solve
def test_certified_pair_needs_no_relaxation_and_no_solve():
    near = calibrate_slice(K, W_NEAR, t=T_NEAR, n_order=6)
    far = calibrate_slice(K, 2.0 * W_NEAR, t=T_FAR, n_order=6, init=near.params)
    specs = [
        _spec(T_NEAR, K, W_NEAR, half=0.005, heavy=False),
        _spec(T_FAR, K, 2.0 * W_NEAR, half=0.005, heavy=False),
    ]
    rel = relax_pair(
        specs[0], specs[1], near.params.to_vector(), far.params.to_vector()
    )
    assert rel.feasible and rel.delta_vol == 0.0 and rel.rounds == 0
    assert rel.delta_infeasible is None
    assert rel.certificate_gap_at_delta >= -_CAL_TOL


def test_gated_unequal_exponents_are_infeasible_without_a_solve():
    near_p = LQDParams(
        L=np.log(0.12), R=np.log(0.10), a=np.array([0.020, -0.010]),
        alpha_left=0.25, alpha_right=0.25,
    )
    far_p = LQDParams(  # lighter right tail exponent: no band width moves it
        L=np.log(0.20), R=np.log(0.17), a=np.array([0.015, -0.008]),
        alpha_left=0.25, alpha_right=0.40,
    )
    kq = np.linspace(-0.4, 0.4, 33)
    s_n, s_f = build_slice(near_p), build_slice(far_p)
    specs = [
        _spec(T_NEAR, kq, s_n.implied_w(kq), half=0.005, heavy=False,
              n_order=near_p.order, alpha_left=0.25, alpha_right=0.25),
        _spec(T_FAR, kq, s_f.implied_w(kq), half=0.005, heavy=False,
              n_order=far_p.order, alpha_left=0.25, alpha_right=0.40),
    ]
    rel = relax_pair(
        specs[0], specs[1], near_p.to_vector(), far_p.to_vector(), tail_gate=True
    )
    assert not rel.feasible and rel.delta_vol is None and rel.rounds == 0
    assert rel.delta_infeasible == DELTA_MAX and rel.tail_gated


# ---------------------------------------------------------- 3. no mutation
def test_widen_spec_never_mutates_the_caller():
    spec = _spec(T_NEAR, K, W_NEAR, half=0.002, heavy=False)
    band = spec.fit_kwargs["band"]
    lo, hi = band.iv_lo.copy(), band.iv_hi.copy()
    wide = widen_spec(spec, 0.01)
    assert wide is not spec and wide.fit_kwargs["band"] is not band
    assert np.allclose(wide.fit_kwargs["band"].iv_lo, np.maximum(lo - 0.01, 0.0))
    assert np.allclose(wide.fit_kwargs["band"].iv_hi, hi + 0.01)
    assert np.array_equal(wide.fit_kwargs["band"].iv_mid, band.iv_mid)
    assert np.array_equal(band.iv_lo, lo) and np.array_equal(band.iv_hi, hi)
    assert widen_spec(spec, 0.0) is spec  # zero widening: the very object
    bare = SliceSpec(t=T_NEAR, k=K, w=W_NEAR, fit_kwargs=dict(n_order=6))
    assert widen_spec(bare, 0.01) is bare  # nothing to widen


# ----------------------------------------------- 4. API: flag off / clean ladder
def test_flag_off_and_clean_ladder_leave_surface_and_payload_untouched():
    off, on = _state(False), _state(True)
    service.fit_surface(off, TICKER, "haircut", True)
    service.fit_surface(on, TICKER, "haircut", True)
    # The synthetic ladder certifies: nothing to diagnose either way.
    assert off._band_relaxation == {} and on._band_relaxation == {}
    for iso in _isos(off):
        a = service.fit_or_get(off, TICKER, iso, "haircut").result.params.to_vector()
        b = service.fit_or_get(on, TICKER, iso, "haircut").result.params.to_vector()
        assert a.tobytes() == b.tobytes()  # the flag never touches a fit
    assert off.options_version == on.options_version  # advisory: no version bump
    report = quality.build_quality_report(off, "haircut")
    assert report.summary.fitted > 0
    assert all(
        n.bandRelaxationVol is None and n.bandRelaxationFeasible is None
        for n in report.nodes
    )


# ---------------------------------------- 5. API: flag on, refuted pair on the wire
def test_flag_on_records_pair_diagnostic_on_the_wire(monkeypatch):
    state = _state(True)
    isos = _isos(state)
    assert len(isos) >= 2

    real_ladder = surface_symmetric.exchange_ladder

    def refuting_ladder(specs, thetas, tail_gate=False):
        out, touched, certs = real_ladder(specs, thetas, tail_gate=tail_gate)
        certs[0] = dataclasses.replace(certs[0], min_gap=-1e-3)  # refute pair 0
        return out, touched, certs

    calls: list[tuple] = []

    def stub_relax(spec_near, spec_far, theta_near, theta_far, *, tail_gate=False, **kw):
        calls.append((spec_near, spec_far, tail_gate))
        return BandRelaxation(
            delta_vol=0.0123, feasible=True, rounds=3,
            certificate_gap_at_delta=0.0, delta_infeasible=0.011,
        )

    monkeypatch.setattr(surface_symmetric, "exchange_ladder", refuting_ladder)
    monkeypatch.setattr(surface_symmetric, "relax_pair", stub_relax)
    service.fit_surface(state, TICKER, "haircut", True)

    key = (TICKER, isos[1], "haircut")
    assert list(state._band_relaxation) == [key]
    assert len(calls) == 1
    assert calls[0][2] is False  # the (default-off) tail gate is threaded through
    assert calls[0][0].fit_kwargs.get("band") is not None  # a band mode reached it

    report = quality.build_quality_report(state, "haircut")
    row = next(n for n in report.nodes if n.ticker == TICKER and n.expiry == isos[1])
    assert row.bandRelaxationVol == 0.0123 and row.bandRelaxationFeasible is True
    others = [n for n in report.nodes if n.ticker == TICKER and n.expiry != isos[1]]
    assert all(n.bandRelaxationVol is None for n in others)

    out = export.build_surface_export(
        state, fit_mode="haircut", tickers=[TICKER], require_clean=False
    )
    node = next(n for n in out.tickers[0].nodes if n.expiry == isos[1])
    assert node.bandRelaxationVol == 0.0123

    # The hint rides the certificate issue: refute the pair in the quality
    # row (the between-node dip rig of test_quality) and read the text.
    near_rec = service.fit_or_get(state, TICKER, isos[0], "haircut")
    far_rec = service.fit_or_get(state, TICKER, isos[1], "haircut")
    sl = near_rec.result.slice
    j = int(np.searchsorted(sl.q_z, float(near_rec.prepared.k.max()) + 0.5))
    while j % CAL_STRIDE in (0, CAL_STRIDE - 1):
        j += 1
    da = sl.da_dz.copy()
    da[j] -= 0.05
    da[j + 1] -= 0.05
    rigged = dataclasses.replace(sl, da_dz=da)
    node_row, _ = quality._node_row(
        state, TICKER, isos[1], "haircut", far_rec, rigged, None,
        near_rec.prepared.k, None, 50.0, False,
    )
    assert not node_row.ledgerCertified and not node_row.ready
    assert any(
        s.startswith("calendar certificate")
        and "certifies with +-1.23 vol-pt band widening" in s
        for s in node_row.issues
    )
    # The recorded diagnostic clears with the chain caches.
    state._clear_chain_caches()
    assert state._band_relaxation == {}
