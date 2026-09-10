"""API locks for POST /fit/affine/{ticker}/compare (LV Dupire-twin arc, D2).

In-process over fastapi.testclient against the synthetic provider (pinned
reference date, ungated: reads bootstrap the parametric and LV fits, as the
historical test app does). Invariants:

1. Shapes: the twin sits on the affine vertex lattice (tNodes × xNodes) of the
   SAME rows, inside the variance box, every x > 0 vertex inside the display
   range differentiated, the counters one entry per t row, the affine sheet and
   the difference present on the matching lattice.
2. The clean synthetic surface needs no butterfly repair; every expiry carries
   the twin / parametric / affine curves, the quotes and three finite scores.
3. The round trip — the twin repriced back against its parametric source at
   the quoted strikes — is a MEASURED number locked with slack (the coarse
   affine lattice samples a smooth surface: the residual is sampling +
   discretization, the arc's honest figure, not a model error).
4. The buckets chip returns a different sheet on the same lattice.
5. Gates: unknown ticker 404, unknown chip values 422 (the Literal body
   validation), and the payload is served from the cache on a repeat call.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    return client.get("/universe").json()


@pytest.fixture(scope="module")
def compare(client, universe):
    # Parametric fits first (the app calibrates parametric before LV): touching
    # every expiry's smile bootstraps its fit in the ungated test app.
    for e in universe["expiries"]["ALPHA"]:
        assert client.get(f"/smiles/ALPHA/{e['expiry']}").status_code == 200
    response = client.post("/fit/affine/ALPHA/compare", json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_shapes_on_the_affine_lattice(compare, client):
    affine = client.post("/fit/affine/ALPHA", json={}).json()
    assert compare["ticker"] == "ALPHA"
    assert compare["tInterp"] == "smooth" and compare["tails"] == "model"
    n_t, n_x = len(compare["tNodes"]), len(compare["xNodes"])
    assert compare["tNodes"] == affine["tNodes"] and compare["xNodes"] == affine["xNodes"]
    twin = np.array(compare["localVolTwin"])
    assert twin.shape == (n_t, n_x)
    # The twin clips only at the 400 % ceiling; varHi is the FIT's cap, which
    # the capped counter reads against (the synthetic ladder stays inside it).
    lo = np.sqrt(compare["varLo"])
    assert np.all(twin >= lo - 1e-12) and np.all(twin <= 4.0 + 1e-12)
    assert np.all(twin <= np.sqrt(compare["varHi"]) + 1e-12)
    x = np.array(compare["xNodes"])
    inside = (x > 0.0) & (np.log(np.where(x > 0, x, 1.0)) >= -1.4) & (np.log(np.where(x > 0, x, 1.0)) <= 1.0)
    assert compare["differentiated"] == inside.tolist()
    raw = compare["rawLocalVariance"]
    assert len(raw) == n_t and all(len(r) == n_x for r in raw)
    # The unrepaired values exist exactly on the differentiated vertices (the
    # delta-spaced lattice carries no x = 0 vertex; a linear one would, guarded).
    for row in raw:
        assert [v is not None for v in row] == inside.tolist()
    for name in ("butterfly", "calendar", "floored", "capped"):
        assert len(compare["counters"][name]) == n_t
    # The twin's own triangulation is the affine sheet's on the same vertices.
    assert compare["cellDiagMain"] == affine["cellDiagMain"]
    assert np.array(compare["cellDiagMain"]).shape == (n_t - 1, n_x - 1)
    assert compare["hasAffine"] is True and compare["affineLatticeMatches"] is True
    assert np.array(compare["localVolAffine"]).shape == (n_t, n_x)
    diff = np.array(compare["diffLocalVol"])
    assert diff.shape == (n_t, n_x)
    np.testing.assert_allclose(diff, twin - np.array(affine["localVol"]), atol=1e-12)


def test_clean_surface_and_per_expiry_content(compare, universe):
    ladder = [e["expiry"] for e in universe["expiries"]["ALPHA"]]
    assert compare["counters"]["butterfly"] == [0] * len(compare["tNodes"])
    assert compare["skippedExpiries"] == []
    assert [s["expiry"] for s in compare["smiles"]] == ladder
    for s in compare["smiles"]:
        assert len(s["twin"]) > 10 and len(s["parametric"]) > 10 and len(s["quotes"]) >= 2
        assert len(s["twinExt"]) >= len(s["twin"])
        assert s["tau"] > 0 and s["forward"] > 0
        for score in (s["twinScore"], s["parametricScore"], s["affineScore"]):
            assert score is not None
            assert np.isfinite(score["rmsError"]) and np.isfinite(score["maxBp"])
        assert s["twinScore"]["convergedBp"] is None  # the twin has one operator: its display operator
        assert s["parametricScore"]["convergedBp"] is None
        assert s["affineScore"]["convergedBp"] is not None
        # The parametric source fits the synthetic quotes tightly; the twin's
        # scores are finite and its round trip is what the lattice can carry.
        assert s["parametricScore"]["rmsBp"] < 50.0
        assert np.isfinite(s["roundTripBp"]) and np.isfinite(s["sheetRoundTripBp"]) and np.isfinite(s["operatorBp"])
    assert compare["affineScore"] is not None
    assert "twin on" in compare["message"]


def test_round_trip_is_a_measured_figure(compare):
    # Measured 2026-09-08 on the synthetic ALPHA ladder (11 × 14 vertices) on
    # the twin's display operator (Rannacher dt/8 dx/4): the SMOOTH twin
    # repriced back against its parametric source reads 0.93 bp rms pooled —
    # 1.98 on the one-month front against a 1.80 bp operator floor, 0.16 at
    # one year — and scores the quotes like the parametric does (5.2 vs 5.0
    # bp); the NODAL sheet on the same operator reads 14.3 bp (what the
    # coarse lattice loses). The first cut marched the nodal sheet on the
    # calibration operator and read 24 bp: the first-order operator (a flat
    # control read 154 bp on the front), not the twin. The lock keeps 2x
    # slack so a lattice or scheme change that doubles it is caught.
    rt = compare["roundTripBp"]
    assert 0.0 < rt < ROUND_TRIP_BP_CEILING
    assert compare["roundTripMaxBp"] >= rt
    # The twin reads the operator: its round trip sits within a couple of
    # floors of the flat control's error, never far above it.
    assert rt <= 2.0 * compare["operatorBp"] + 0.5
    for s in compare["smiles"]:
        assert s["roundTripBp"] <= 2.0 * s["operatorBp"] + 0.5
        assert s["sheetRoundTripBp"] > s["roundTripBp"]  # the lattice loses, the twin does not
    # The twin fits the quotes as its source does (the same surface, marched).
    assert abs(compare["twinScore"]["rmsBp"] - compare["parametricScore"]["rmsBp"]) < 1.0
    assert compare["sheetRoundTripBp"] > 5.0 * rt


#: Round-trip ceiling (bp) — 2x the figure measured at the twin-fidelity fix
#: (ROADMAP 2026-09-08); tighten only from a new measurement.
ROUND_TRIP_BP_CEILING = 2.0


def test_buckets_chip_is_another_sheet_on_the_same_lattice(compare, client):
    response = client.post("/fit/affine/ALPHA/compare", json={"tInterp": "buckets"})
    assert response.status_code == 200, response.text
    buckets = response.json()
    assert buckets["tInterp"] == "buckets"
    assert buckets["tNodes"] == compare["tNodes"] and buckets["xNodes"] == compare["xNodes"]
    a, b = np.array(compare["localVolTwin"]), np.array(buckets["localVolTwin"])
    assert a.shape == b.shape and not np.allclose(a, b)
    assert len(buckets["smiles"]) == len(compare["smiles"])


def test_hull_and_affine_tail_targets(compare, client):
    """The two tail targets of 2026-09-10 (dupire_surface.WING_TARGETS):
    ``hull`` differentiates inside each expiry's quoted range only and holds
    the local variance flat beyond it — so the ATM column (inside every quoted
    range) equals the model twin's while the far wings differ; ``affine`` reads
    the calibrated sheet outside the quoted range (its cells equal the sheet's
    nodal variance there) and is a 422 without a sheet on the same lattice."""
    model = np.asarray(compare["localVolTwin"], dtype=float)
    x = np.asarray(compare["xNodes"], dtype=float)
    i_atm = int(np.argmin(np.abs(x - 1.0)))

    hull = client.post("/fit/affine/ALPHA/compare", json={"tails": "hull"})
    assert hull.status_code == 200, hull.text
    hull = hull.json()
    assert hull["tails"] == "hull" and hull["tInterp"] == "smooth"
    twin_h = np.asarray(hull["localVolTwin"], dtype=float)
    assert twin_h.shape == model.shape
    np.testing.assert_allclose(twin_h[:, i_atm], model[:, i_atm], rtol=1e-12)
    assert not np.allclose(twin_h, model)  # the wings are held flat, the model's are not
    # Beyond the quoted range a hull row is constant. The vertex lattice spans
    # the LONGEST expiry's quoted band, so the shortest expiry's row (the first,
    # its band the narrowest) is flat at both ends; longer rows may still be
    # quoted at the outermost node.
    assert np.allclose(twin_h[0, -1], twin_h[0, -2]) and np.allclose(twin_h[0, 1], twin_h[0, 2])
    assert not np.allclose(model[0, -1], model[0, -2])  # the model's wing is not flat there

    affine = client.post("/fit/affine/ALPHA/compare", json={"tails": "affine"})
    if compare["hasAffine"] and compare["affineLatticeMatches"]:
        assert affine.status_code == 200, affine.text
        body = affine.json()
        assert body["tails"] == "affine"
        twin_a = np.asarray(body["localVolTwin"], dtype=float)
        sheet = np.asarray(body["localVolAffine"], dtype=float)
        np.testing.assert_allclose(twin_a[:, i_atm], model[:, i_atm], rtol=1e-12)
        # The shortest expiry's outermost cells lie outside its quoted range:
        # they read the sheet — local vol for local vol (the sheet lives inside
        # the fit's box, which the twin's ceiling contains: no clip).
        np.testing.assert_allclose(twin_a[0, -1], sheet[0, -1], rtol=1e-9)
        np.testing.assert_allclose(twin_a[0, 1], sheet[0, 1], rtol=1e-9)
    else:
        assert affine.status_code == 422
        assert "Affine wings" in affine.json()["detail"]
    assert client.post("/fit/affine/ALPHA/compare", json={"tails": "matchLqd"}).status_code == 422


def test_gates_and_cache(client, compare):
    assert client.post("/fit/affine/NOPE/compare", json={}).status_code == 404
    assert client.post("/fit/affine/ALPHA/compare", json={"tails": "kernel"}).status_code == 422
    assert client.post("/fit/affine/ALPHA/compare", json={"tInterp": "cubic"}).status_code == 422
    state = client.app.state.volfit
    cache = getattr(state, "_lv_compare_cache")
    n_before = len(cache)
    again = client.post("/fit/affine/ALPHA/compare", json={}).json()
    assert again == compare
    assert len(cache) == n_before  # served from the cache, no new entry


def test_anchored_under_a_spot_move(client, compare):
    """A spot move never rebuilds the twin: the comparison is anchored at the
    calibration spot (the same sheets, the same lattice match, the same
    figures), the response reports the shift, and the cache serves it."""
    state = client.app.state.volfit
    cache = getattr(state, "_lv_compare_cache")
    n_before = len(cache)
    assert client.put("/spot/ALPHA", json={"spotReturn": 0.012}).status_code == 200
    try:
        moved = client.post("/fit/affine/ALPHA/compare", json={}).json()
        assert moved["spotShift"] == pytest.approx(0.012)
        assert moved["affineLatticeMatches"] is True
        assert moved["localVolTwin"] == compare["localVolTwin"]
        assert moved["localVolAffine"] == compare["localVolAffine"]
        assert moved["roundTripBp"] == compare["roundTripBp"]
        assert "compared at the calibration spot" in moved["message"]
        assert all(len(s["affine"]) > 10 for s in moved["smiles"])
        # Anchored ⇒ the same cache entry served it (no spot version in the key).
        assert len(cache) == n_before
    finally:
        assert client.put("/spot/ALPHA", json={"spotReturn": 0.0}).status_code == 200


def test_smooth_sheet_sample_passes_through_the_vertices(compare):
    """The drawn twin is the smooth surface sampled on the subdivided lattice:
    the vertex values sit inside it bit-for-bit, the samples between are inside
    the box, and the subdivision respects the renderer's column cap."""
    t_fine, x_fine = np.array(compare["tNodesFine"]), np.array(compare["xNodesFine"])
    fine = np.array(compare["localVolTwinFine"])
    n_t, n_x = len(compare["tNodes"]), len(compare["xNodes"])
    assert t_fine.size == 4 * (n_t - 1) + 1
    sub_x = (x_fine.size - 1) // (n_x - 1)
    assert 1 <= sub_x <= 4 and x_fine.size <= 48
    assert fine.shape == (t_fine.size, x_fine.size)
    np.testing.assert_array_equal(t_fine[::4], np.array(compare["tNodes"]))
    np.testing.assert_array_equal(x_fine[::sub_x], np.array(compare["xNodes"]))
    np.testing.assert_array_equal(fine[::4, ::sub_x], np.array(compare["localVolTwin"]))  # bit-for-bit
    # Between the vertices the samples are the smooth twin's own values: a
    # sample next to a vertex sits close to it (no interpolant kink).
    assert np.max(np.abs(fine[::4, 1::sub_x] - fine[::4, :-1:sub_x])) < 0.5 * np.ptp(fine)
    lo = np.sqrt(compare["varLo"])
    assert np.all(fine >= lo - 1e-12) and np.all(fine <= 4.0 + 1e-12)
    assert np.all(np.diff(t_fine) > 0) and np.all(np.diff(x_fine) > 0)
    assert "samples of the smooth twin" in compare["message"]
