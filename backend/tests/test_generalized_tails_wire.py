"""Generalized tails — Phase 3a/3b/3c backend locks (wire, wings, scope).

Docs/generalized_tails_calendar_roadmap.md Phase 3:

1. WIRE — alphaL/alphaR ride every artifact as OPTIONAL SIBLING fields
   (never inside the theta vector, whose length is load-bearing): workspace
   prior records round-trip them and alpha = 0 docs keep their exact key
   set; prior snapshots carry them and the transport rebuilds the same tail
   class; export lqdParams and history params emit them only when nonzero;
   the ATM-chart retarget machinery preserves the reference's exponents.
2. WINGS — the publication-chart rule: on a side with alpha > 0 the remote
   display wing comes from the wing law matched at the last reliably priced
   strike, finite and step-free where price inversion has underflowed.
3. SCOPE — per-underlier overrides resolve over the global pair and are
   range-validated.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from volfit.api import service, workspace
from volfit.api.prior_transport import prior_lqd_slice
from volfit.api.schemas import FitSettings
from volfit.api.schemas_prior import PriorNode
from volfit.api.state import AppState, PriorRecord
from volfit.models.lqd.basis import LQDParams
from volfit.models.lqd.quadrature import build_slice

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"

ALPHA_PARAMS = LQDParams(
    L=np.log(0.12), R=np.log(0.10), a=np.array([0.02, -0.01]),
    alpha_left=0.25, alpha_right=0.5,
)
PLAIN_PARAMS = LQDParams(L=np.log(0.12), R=np.log(0.10), a=np.array([0.02, -0.01]))


# ------------------------------------------------------------------ 1. wire
def test_workspace_prior_record_round_trips_alphas():
    state = AppState(REF_DATE)
    state.save_prior((TICKER, "2026-07-17"), PriorRecord(
        curve=[], params=ALPHA_PARAMS, t=0.1))
    state.save_prior((TICKER, "2026-08-21"), PriorRecord(
        curve=[], params=PLAIN_PARAMS, t=0.2))
    doc = workspace.build_doc(state)

    docs = doc["priors"][TICKER]
    tagged, plain = docs["2026-07-17"]["params"], docs["2026-08-21"]["params"]
    assert tagged["alphaL"] == 0.25 and tagged["alphaR"] == 0.5
    # alpha = 0 docs keep the exact historical key set (old-workspace shape).
    assert set(plain.keys()) == {"L", "R", "a"}

    state2 = AppState(REF_DATE)
    workspace.restore_doc(state2, doc)
    back = state2.get_prior((TICKER, "2026-07-17")).params
    assert back.alpha_left == 0.25 and back.alpha_right == 0.5
    assert back.to_vector() == pytest.approx(ALPHA_PARAMS.to_vector())
    back0 = state2.get_prior((TICKER, "2026-08-21")).params
    assert back0.alpha_left == 0.0 and back0.alpha_right == 0.0


def test_prior_node_carries_alphas_and_transport_rebuilds_them():
    node = PriorNode(
        expiry="2026-07-17", tCal=0.1, tau=0.1, forward=100.0, discount=1.0,
        model="lqd", lqd=[float(v) for v in ALPHA_PARAMS.to_vector()],
        alphaL=0.25, alphaR=0.5, atmVol=0.2, skew=-0.1,
    )
    sl = prior_lqd_slice(node)
    assert sl.params.alpha_left == 0.25 and sl.params.alpha_right == 0.5
    # An OLD snapshot without the fields loads as the exponential subclass
    # and rebuilds byte-identically to the historical path.
    legacy = PriorNode.model_validate(
        node.model_dump(exclude={"alphaL", "alphaR"}))
    assert legacy.alphaL == 0.0 and legacy.alphaR == 0.0
    sl0 = prior_lqd_slice(legacy)
    ref = build_slice(LQDParams.from_vector(np.asarray(node.lqd)))
    assert sl0.a_z.tobytes() == ref.a_z.tobytes()


def test_history_and_export_params_docs_emit_only_when_nonzero():
    from volfit.api.history import _params_dict

    tagged = _params_dict(ALPHA_PARAMS)
    assert tagged["alphaL"] == 0.25 and tagged["alphaR"] == 0.5
    assert set(_params_dict(PLAIN_PARAMS).keys()) == {"L", "R", "a"}


def test_snapshot_capture_and_export_carry_alphas_end_to_end():
    """Fit a node under a tail scenario: the prior snapshot node and the
    export artifact both carry the exponents; the committed record already
    does (Phase 2)."""
    from volfit.api import export, priors

    state = AppState(REF_DATE)
    fs = state.fit_settings()
    state.set_fit_settings(fs.model_copy(update={"tailAlphaRight": 0.25}))
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    service.calibrate_node(state, TICKER, iso, "mid")

    snap = priors.capture_snapshot(state, TICKER, "mid")
    node = next(n for n in snap.nodes if n.expiry == iso)
    assert node.alphaR == 0.25 and node.alphaL == 0.0
    moved = prior_lqd_slice(node)
    assert moved.params.alpha_right == 0.25

    out = export.build_surface_export(state, tickers=[TICKER])
    lp = out.tickers[0].nodes[0].lqdParams
    assert lp["alphaR"] == 0.25 and lp["alphaL"] == 0.0


def test_retarget_preserves_reference_alphas():
    from volfit.models.lqd.atm import atm_handles
    from volfit.models.lqd.ortho import build_atm_coordinates

    chart = build_atm_coordinates(ALPHA_PARAMS, t=0.25)
    h0 = chart.handles0
    moved = chart.retarget(h0 * np.array([1.05, 1.0, 1.0]))
    assert moved.alpha_left == 0.25 and moved.alpha_right == 0.5
    got = atm_handles(build_slice(moved), 0.25)
    assert got.w0 == pytest.approx(float(h0[0]) * 1.05, rel=1e-8)


# ------------------------------------------------------------------ 2. wings
def test_alpha_law_wings_patch_remote_wings():
    """A short-dated Gaussian-rate slice underflows its display wings well
    inside the k in [-1.4, 1] window: the patched curve is finite, continuous
    at the seam, flat-to-the-law beyond it (alpha = 1/2), and untouched where
    the inversion is healthy. (s = 0.02, a 2-day ~24%-vol scale: since the
    OTM-side inversion became tail-accurate, prices must genuinely underflow
    double precision — |d| ~ 38 — before the raw curve dies, not merely fall
    below black_call's old erf saturation at |d| ~ 8.3.)"""
    s = 0.02
    lam = s / np.sqrt(2.0)
    sl = build_slice(LQDParams(L=np.log(lam), R=np.log(lam), a=np.zeros(0),
                               alpha_left=0.5, alpha_right=0.5))
    grid = np.linspace(-1.4, 1.0, 241)
    w_raw = np.maximum(sl.implied_w(grid), 0.0)
    assert not np.all(np.isfinite(w_raw) & (w_raw > 0.0))  # the failure exists
    w = service.alpha_law_wings(sl, grid, w_raw)
    assert np.all(np.isfinite(w) & (w > 0.0))
    # No step: the patched curve's increments stay small everywhere.
    assert float(np.max(np.abs(np.diff(w)))) < 5e-3
    # Gaussian rate: the far wing sits at the (matched) constant law level.
    assert w[-1] == pytest.approx(w[np.argmax(grid > 0.5)], rel=0.2)
    # Healthy region untouched (ATM area inverts fine).
    core = np.abs(grid) < 0.1
    assert np.array_equal(w[core], w_raw[core])


def test_alpha_zero_curve_path_untouched():
    """model_curve's alpha = 0 path never enters the patch (byte-identity of
    the historical display pipeline)."""
    state = AppState(REF_DATE)
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    record = service.calibrate_node(state, TICKER, iso, "mid")
    assert record.result.params.alpha_left == 0.0
    curve = service.model_curve(record)
    assert all(np.isfinite(p.vol) for p in curve)


# ------------------------------------------------------------------ 3. scope
def test_per_underlier_alpha_overrides():
    fs = FitSettings(tailAlphaLeft=0.1, tailAlphaRight=0.2,
                     tailAlphaByTicker={"SPY": (0.0, 0.5)})
    assert fs.tail_alphas("SPY") == (0.0, 0.5)
    assert fs.tail_alphas("QQQ") == (0.1, 0.2)
    with pytest.raises(ValueError, match="outside"):
        FitSettings(tailAlphaByTicker={"SPY": (0.0, 0.6)})

    state = AppState(REF_DATE)
    fs2 = state.fit_settings()
    state.set_fit_settings(fs2.model_copy(update={
        "tailAlphaByTicker": {TICKER: (0.25, 0.25)}}))
    iso = sorted(state.forwards(TICKER))[0].isoformat()
    record = service.calibrate_node(state, TICKER, iso, "mid")
    assert record.result.params.alpha_left == 0.25
    assert record.result.params.alpha_right == 0.25
