"""Publish-time wing projection (Notes 09/10 Phase 3, models.projection).

Contracts locked:
  * a clean curve is an exact no-op — the caller's ORIGINAL array back;
  * the traded core is pinned byte-identically whenever wings move;
  * a butterfly-violating wing is lifted to discrete price convexity,
    including the seam with the core (first wing slope >= core edge slope);
  * a calendar crossing in the wing is lifted to the previous PUBLISHED
    curve's floor; a floor above the pinned core edge cannot be repaired and
    reports fully_clean=False (a core conflict — the fit's business);
  * the export path projects per ticker in ascending maturity, flags the
    nodes it moved, counts them in the manifest, and ``project_wings=false``
    restores the raw model wings exactly.
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.core.black import black_call
from volfit.models.projection import project_published_wings

REF_DATE = date(2026, 6, 10)
K = np.linspace(-0.4, 0.6, 51)
LO, HI = -0.2, 0.2  # traded range: wings on both sides


def _core(k: np.ndarray = K) -> np.ndarray:
    return (k >= LO - 1e-12) & (k <= HI + 1e-12)


def _call_slopes(k: np.ndarray, w: np.ndarray) -> np.ndarray:
    x = np.exp(k)
    c = black_call(k, w)
    return np.diff(c) / np.diff(x)


def test_clean_curve_is_exact_noop():
    w = np.full(K.size, 0.04)  # flat total variance: g = 1 everywhere
    out = project_published_wings(K, w, LO, HI)
    assert out.w is w  # the ORIGINAL object — byte-identical by construction
    assert not out.changed and out.fully_clean


def test_butterfly_wing_lifted_to_discrete_convexity_core_pinned():
    w = np.full(K.size, 0.04)
    dirty = w.copy()
    dirty[K > 0.35] = 0.012  # sharp wing drop: call-price convexity breaks
    out = project_published_wings(K, dirty, LO, HI)
    assert out.changed and out.fully_clean
    assert np.array_equal(out.w[_core()], dirty[_core()])  # core pinned
    # Discrete butterfly cleanliness on the right wing INCLUDING the seam:
    # call-price slopes in strike non-decreasing (and non-positive).
    right = K >= HI - 1e-12  # from the traded edge outward
    s = _call_slopes(K[right], out.w[right])
    assert np.all(np.diff(s) >= -1e-10)
    assert np.all(s <= 1e-12)


def test_calendar_wing_crossing_lifted_to_published_floor():
    w = np.full(K.size, 0.04)
    prev = w.copy()
    prev[K > 0.35] = 0.06  # prev expiry's published wing above this one
    out = project_published_wings(K, w, LO, HI, prev_k=K, prev_w=prev)
    assert out.changed and out.fully_clean
    assert np.array_equal(out.w[_core()], w[_core()])  # core pinned
    far = K > 0.36
    assert np.all(out.w[far] >= 0.06 - 1e-6)  # lifted to the floor
    # The lift itself must not introduce a butterfly: slopes still monotone.
    right = K >= HI - 1e-12
    s = _call_slopes(K[right], out.w[right])
    assert np.all(np.diff(s) >= -1e-10)


def test_left_wing_repair_in_put_space():
    w = np.full(K.size, 0.04)
    dirty = w.copy()
    dirty[K < -0.32] = 0.012  # left-wing drop: put-price convexity breaks
    out = project_published_wings(K, dirty, LO, HI)
    assert out.changed and out.fully_clean
    assert np.array_equal(out.w[_core()], dirty[_core()])
    left = K <= LO + 1e-12
    x = np.exp(K[left])
    put = black_call(K[left], out.w[left]) - (1.0 - x)
    s = np.diff(put) / np.diff(x)
    assert np.all(np.diff(s) >= -1e-10)  # convex in strike
    assert np.all((s >= -1e-12) & (s <= 1.0 + 1e-12))  # put slope cone


def test_floor_above_pinned_core_reports_not_fully_clean():
    w = np.full(K.size, 0.04)
    prev = np.full(K.size, 0.09)  # prev curve above EVERYWHERE incl. the core
    out = project_published_wings(K, w, LO, HI, prev_k=K, prev_w=prev)
    assert out.changed and not out.fully_clean  # core conflict: unrepairable
    assert np.array_equal(out.w[_core()], w[_core()])  # core still pinned
    # Wings capped at the pinned edge value: never above the core anchor.
    x = np.exp(K)
    c = black_call(K, out.w)
    edge = int(np.flatnonzero(K <= HI + 1e-12)[-1])
    assert np.all(c[K > HI] <= c[edge] + 1e-12)


# --------------------------------------------------------------- export path
def test_export_projection_flags_and_off_switch():
    from volfit.api import export, workflow
    from volfit.api.state import AppState

    state = AppState(REF_DATE)
    workflow.calibrate_ticker(state, "ALPHA")

    raw = export.build_surface_export(state, tickers=["ALPHA"], project_wings=False)
    pub = export.build_surface_export(state, tickers=["ALPHA"])  # default ON
    assert raw.manifest.wingProjection is False
    assert raw.manifest.projectedNodes == 0
    assert all(not n.curveProjected for t in raw.tickers for n in t.nodes)
    assert pub.manifest.wingProjection is True
    flagged = sum(n.curveProjected for t in pub.tickers for n in t.nodes)
    assert pub.manifest.projectedNodes == flagged

    # Nodes export in ascending maturity and the core samples are IDENTICAL
    # between the raw and published artifacts (only wings may differ).
    for t_raw, t_pub in zip(raw.tickers, pub.tickers):
        taus = [n.tau for n in t_pub.nodes]
        assert taus == sorted(taus)
        for n_raw, n_pub in zip(t_raw.nodes, t_pub.nodes):
            ptr = state.get_calibrated_ptr("ALPHA", n_pub.expiry, "mid")
            record = state.get_fit(ptr[0])
            k_lo, k_hi = float(record.prepared.k.min()), float(record.prepared.k.max())
            for p_raw, p_pub in zip(n_raw.curve, n_pub.curve):
                if k_lo - 1e-12 <= p_raw.k <= k_hi + 1e-12:
                    assert p_pub.iv == p_raw.iv and p_pub.w == p_raw.w
