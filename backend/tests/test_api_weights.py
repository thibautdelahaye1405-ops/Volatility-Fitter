"""GET /smiles/{ticker}/{expiry}/weights — per-quote weights (V3.4 item 5).

Locks the endpoint's five contracts:
1. POLL-SAFE: reading never creates a fit-cache entry or calibrated pointer
   (the quality.py doctrine — prepared quotes + session edits only);
2. "equal" reports unit weights with the Voronoi spacing still populated;
3. "tv_density" matches volfit.calib.weights.resolve_weights EXACTLY
   (max-mult cap + mean-1 normalization included);
4. session exclusions: weights recompute on the post-edit arrays and remap
   back to the full prepared/QuoteBand index space (excluded rows weight 0);
5. weight_components decomposes resolve_weights byte-identically (the unit
   lock behind the endpoint — the scheme is never re-implemented).

Runs in-process over fastapi.testclient on its own app instance
(module-scoped client). GAMMA keeps the sessions clear of other suites.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.quotes import apply_edits
from volfit.api.service import prepare_slice
from volfit.calib.weights import (
    DEFAULT_MAX_MULT,
    otm_time_value,
    resolve_weights,
    tv_density_weights,
    weight_components,
)

REF_DATE = date(2026, 6, 10)
TICKER = "GAMMA"


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def expiries(client):
    # Fetch the chain WITHOUT fitting (the test_quality idiom): the weights
    # read needs prepared quotes, and must itself never trigger a calibration.
    client.app.state.volfit.ensure_chain(TICKER)
    response = client.get("/universe")
    assert response.status_code == 200
    return [e["expiry"] for e in response.json()["expiries"][TICKER]]


# -- weight_components unit locks (volfit.calib.weights) ------------------------


def test_weight_components_decomposes_resolve_weights():
    """The endpoint's decomposition never re-derives the scheme: the final
    weights ARE resolve_weights, and raw x capped-spacing-multiplier
    mean-normalized reproduces them."""
    k = np.array([-0.6, -0.30, -0.05, -0.02, 0.0, 0.03, 0.07, 0.35, 0.9])
    vol = 0.20 - 0.25 * k + 0.5 * k**2
    w = vol**2 * 0.3

    comps = weight_components("tv_density", k, w)
    assert comps.scheme == "tv_density" and comps.max_mult == DEFAULT_MAX_MULT
    resolved = resolve_weights("tv_density", k, w)
    np.testing.assert_array_equal(comps.weights, resolved)  # byte-identical

    # Components' product, normalized, reproduces the fit's weights.
    mult = np.minimum(comps.spacing / comps.spacing.mean(), comps.max_mult)
    product = comps.raw * mult
    np.testing.assert_allclose(product / product.mean(), comps.weights, rtol=1e-12)

    # raw is the eps-floored OTM time value the doc weights are built on, and
    # the uncapped product equals the tv_density_weights helper itself.
    np.testing.assert_allclose(comps.raw, np.maximum(otm_time_value(k, w), 1e-12))
    np.testing.assert_allclose(
        comps.raw * comps.spacing / comps.spacing.mean(),
        tv_density_weights(k, otm_time_value(k, w), max_mult=None),
        rtol=1e-12,
    )


def test_weight_components_equal_scheme_reports_spacing():
    k = np.linspace(-0.3, 0.3, 7)
    comps = weight_components("equal", k, np.full(7, 0.01))
    assert comps.scheme == "equal"
    np.testing.assert_array_equal(comps.weights, np.ones(7))
    np.testing.assert_array_equal(comps.raw, np.ones(7))
    np.testing.assert_allclose(comps.spacing, 0.1)  # uniform grid, ends one-sided
    with pytest.raises(ValueError):
        weight_components("nope", k, k)


def test_weight_components_degenerate_sizes():
    empty = weight_components("tv_density", np.array([]), np.array([]))
    assert empty.weights.size == 0 and empty.spacing.size == 0
    one = weight_components("tv_density", np.array([0.1]), np.array([0.02]))
    np.testing.assert_array_equal(one.weights, [1.0])  # mean-1 of one quote
    assert one.spacing[0] == 0.0  # no Voronoi cell with a single quote


# -- endpoint ------------------------------------------------------------------


def test_weights_read_never_fits(client, expiries):
    """Poll-safety: the read creates no fit-cache entry / calibrated pointer.
    Runs FIRST against a never-fitted node (module order matters)."""
    state = client.app.state.volfit
    before = set(state._fits)
    response = client.get(f"/smiles/{TICKER}/{expiries[1]}/weights")
    assert response.status_code == 200
    assert len(response.json()["entries"]) >= 5
    assert set(state._fits) == before  # no fit-cache entry created
    assert state.get_calibrated_ptr(TICKER, expiries[1], "mid") is None


def test_weights_equal_scheme_is_ones_with_spacing(client, expiries):
    data = client.get(f"/smiles/{TICKER}/{expiries[0]}/weights").json()
    assert data["ticker"] == TICKER and data["expiry"] == expiries[0]
    assert data["scheme"] == "equal"
    assert data["maxMult"] == DEFAULT_MAX_MULT
    assert data["meanNormalized"] is True

    entries = data["entries"]
    assert len(entries) >= 5
    assert [e["index"] for e in entries] == list(range(len(entries)))
    ks = [e["k"] for e in entries]
    assert ks == sorted(ks)
    for e in entries:
        assert e["weight"] == 1.0 and e["weightRaw"] == 1.0
        assert e["spacing"] > 0.0  # the crowding readout survives "equal"
        assert e["excluded"] is False


def test_weights_tv_density_matches_resolve_weights(client, expiries):
    iso = expiries[2]
    defaults = client.get("/settings/fit").json()
    try:
        put = client.put("/settings/fit", json=dict(defaults, weightScheme="tv_density"))
        assert put.status_code == 200
        data = client.get(f"/smiles/{TICKER}/{iso}/weights").json()
        assert data["scheme"] == "tv_density"

        # The exact lock: the served weights equal the fit's own resolve_weights
        # on the same prepared inputs (cap + mean-1 normalization included).
        state = client.app.state.volfit
        prepared = prepare_slice(state, TICKER, iso)
        k, w, _ = apply_edits(prepared, {}, None)
        expected = resolve_weights("tv_density", k, w)
        got = np.array([e["weight"] for e in data["entries"]])
        np.testing.assert_array_equal(got, expected)
        assert got.mean() == pytest.approx(1.0, abs=1e-12)
        # Raw entries are the eps-floored time values (pre-normalization).
        raw = np.array([e["weightRaw"] for e in data["entries"]])
        np.testing.assert_array_equal(raw, np.maximum(otm_time_value(k, w), 1e-12))
    finally:
        assert client.put("/settings/fit", json=defaults).status_code == 200


def test_weights_exclusion_remaps_to_full_index_space(client, expiries):
    iso = expiries[3]
    base = client.get(f"/smiles/{TICKER}/{iso}/weights").json()["entries"]
    n = len(base)
    mid_i = base[n // 2]["index"]

    edited = client.post(
        f"/smiles/{TICKER}/{iso}/edits", json={"action": "exclude", "index": mid_i}
    )
    assert edited.status_code == 200

    defaults = client.get("/settings/fit").json()
    try:
        client.put("/settings/fit", json=dict(defaults, weightScheme="tv_density"))
        entries = client.get(f"/smiles/{TICKER}/{iso}/weights").json()["entries"]
        assert len(entries) == n  # every prepared quote is still listed
        assert [e["index"] for e in entries] == [e["index"] for e in base]
        row = entries[mid_i]
        assert row["excluded"] is True
        assert row["weight"] == 0.0 and row["weightRaw"] == 0.0 and row["spacing"] == 0.0

        # Included rows equal resolve_weights on the POST-EDIT (shorter) arrays,
        # remapped back to the full index space.
        state = client.app.state.volfit
        prepared = prepare_slice(state, TICKER, iso)
        session = state.session_if_exists((TICKER, iso))
        k, w, _ = apply_edits(prepared, session.edits, None)
        assert k.size == n - 1
        expected = resolve_weights("tv_density", k, w)
        included = [e for e in entries if not e["excluded"]]
        np.testing.assert_array_equal(np.array([e["weight"] for e in included]), expected)
        # The neighbours absorb the excluded quote's Voronoi cell.
        assert entries[mid_i - 1]["spacing"] > base[mid_i - 1]["spacing"]
        assert entries[mid_i + 1]["spacing"] > base[mid_i + 1]["spacing"]
    finally:
        assert client.put("/settings/fit", json=defaults).status_code == 200


def test_weights_unknown_node_404(client, expiries):
    assert client.get(f"/smiles/NOPE/{expiries[0]}/weights").status_code == 404
    assert client.get(f"/smiles/{TICKER}/2031-01-01/weights").status_code == 404
