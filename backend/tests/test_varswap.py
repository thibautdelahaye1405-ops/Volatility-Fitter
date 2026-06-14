"""Variance-swap quote penalty + session tests.

Covers the four layers of the var-swap feature:

1. VarSwapSession state machine (set/exclude/include/remove/reset, undo/redo).
2. The calibration penalty (volfit.calib.varswap): an active var-swap quote
   pulls EVERY model's fair var-swap toward the quoted level, and a None target
   leaves the fit byte-identical (the existing golden tests guard the latter
   globally; here we assert it directly on one slice).
3. The HTTP endpoints (apply/undo/redo) and the SmileData / TermPoint payloads.
4. The weight semantics: a larger weight-% pulls the model var-swap harder.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.varswap_session import VarSwapSession
from volfit.calib.varswap import VarSwapTarget, varswap_total_variance
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.svi_jw import calibrate_svi
from volfit.models.sigmoid import calibrate_sigmoid

REF_DATE = date(2026, 6, 10)


# ----------------------------------------------------------------- session
def test_session_set_exclude_include_remove():
    s = VarSwapSession()
    assert s.state.level is None and not s.state.is_active
    s.apply("set", 0.20)
    assert s.state.level == 0.20 and s.state.is_active
    s.apply("exclude", None)
    assert s.state.level == 0.20 and not s.state.is_active
    s.apply("include", None)
    assert s.state.is_active
    s.apply("remove", None)
    assert s.state.level is None


def test_session_undo_redo_and_validation():
    s = VarSwapSession()
    s.apply("set", 0.18)
    s.apply("set", 0.22)
    assert s.state.level == 0.22 and s.can_undo
    s.undo()
    assert s.state.level == 0.18
    s.redo()
    assert s.state.level == 0.22
    with pytest.raises(ValueError):
        s.apply("set", -1.0)  # non-positive level
    with pytest.raises(ValueError):
        VarSwapSession().apply("exclude", None)  # no quote to exclude


# -------------------------------------------------------------- penalty core
def _flat_quotes(t=0.5, sigma=0.20, n=11):
    k = np.linspace(-0.3, 0.3, n)
    w = np.full(n, sigma * sigma * t)
    return k, w, t


def test_penalty_pulls_model_varswap_toward_quote_all_models():
    """For LQD/SVI/sigmoid, adding a high var-swap quote raises the model's own
    fair var-swap toward it (a heavy weight, so the effect is unambiguous)."""
    k, w, t = _flat_quotes()
    quote_vol = 0.30  # well above the 0.20 flat smile
    target = VarSwapTarget(total_var=quote_vol**2 * t, weight=50.0 * k.size, t=t)

    # LQD
    base = calibrate_slice(k, w, t=t)
    pen = calibrate_slice(k, w, t=t, var_swap=target)
    vs_base = np.sqrt(varswap_total_variance(base.slice.implied_w) / t)
    vs_pen = np.sqrt(varswap_total_variance(pen.slice.implied_w) / t)
    assert vs_pen > vs_base + 0.01

    # SVI
    b = calibrate_svi(k, w, t)
    p = calibrate_svi(k, w, t, var_swap=target)
    assert (
        np.sqrt(varswap_total_variance(p.raw.total_variance) / t)
        > np.sqrt(varswap_total_variance(b.raw.total_variance) / t) + 0.005
    )

    # sigmoid
    bs = calibrate_sigmoid(k, w, t, n_cores=0)
    ps = calibrate_sigmoid(k, w, t, n_cores=0, var_swap=target)
    assert (
        np.sqrt(varswap_total_variance(ps.implied_w) / t)
        > np.sqrt(varswap_total_variance(bs.implied_w) / t) + 0.005
    )


def test_none_target_is_byte_identical():
    """var_swap=None must reproduce the historical fit exactly (no objective change)."""
    k, w, t = _flat_quotes()
    a = calibrate_slice(k, w, t=t)
    b = calibrate_slice(k, w, t=t, var_swap=None)
    np.testing.assert_array_equal(a.params.to_vector(), b.params.to_vector())


def test_weight_strength_monotone():
    """A larger penalty weight moves the model var-swap closer to the quote."""
    k, w, t = _flat_quotes()
    quote_vol = 0.30
    base_vs = np.sqrt(varswap_total_variance(calibrate_slice(k, w, t=t).slice.implied_w) / t)

    def gap(weight):
        tgt = VarSwapTarget(total_var=quote_vol**2 * t, weight=weight, t=t)
        vs = np.sqrt(varswap_total_variance(calibrate_slice(k, w, t=t, var_swap=tgt).slice.implied_w) / t)
        return abs(quote_vol - vs)

    light, heavy = gap(2.0 * k.size), gap(100.0 * k.size)
    assert heavy < light < abs(quote_vol - base_vs) + 1e-9


# ------------------------------------------------------------------- HTTP API
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _first_node(client):
    uni = client.get("/universe").json()
    ticker = uni["tickers"][0]
    expiry = uni["expiries"][ticker][0]["expiry"]
    return ticker, expiry


def test_smile_payload_carries_varswap(client):
    ticker, expiry = _first_node(client)
    data = client.get(f"/smiles/{ticker}/{expiry}").json()
    vs = data["varSwap"]
    assert vs["level"] is None and vs["enabled"] is True and vs["modelVol"] > 0.0
    assert not vs["canUndo"] and not vs["canRedo"]


def test_varswap_endpoints_refit_and_undo(client):
    ticker, expiry = _first_node(client)
    model_vol = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]["modelVol"]
    quote = model_vol + 0.05

    r = client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": quote})
    assert r.status_code == 200
    vs = r.json()["varSwap"]
    assert vs["level"] == pytest.approx(quote) and not vs["excluded"] and vs["canUndo"]
    # The penalty moved the fitted var-swap up toward the quote.
    assert vs["modelVol"] > model_vol

    excl = client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "exclude"}).json()
    assert excl["varSwap"]["excluded"] is True
    assert excl["varSwap"]["modelVol"] == pytest.approx(model_vol, abs=2e-4)

    undone = client.post(f"/smiles/{ticker}/{expiry}/varswap/undo").json()
    assert undone["varSwap"]["excluded"] is False  # back to the active quote

    bad = client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": -1})
    assert bad.status_code == 422


def test_disabling_varswap_drops_the_penalty(client):
    ticker, expiry = _first_node(client)
    model_vol = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]["modelVol"]
    client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": model_vol + 0.05})
    options = client.get("/settings/options").json()
    options["varSwapEnabled"] = False
    client.put("/settings/options", json=options)
    vs = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]
    assert vs["enabled"] is False
    assert vs["modelVol"] == pytest.approx(model_vol, abs=2e-4)  # quote ignored


def test_term_reports_varswap_quote(client):
    ticker, expiry = _first_node(client)
    client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": 0.25})
    term = client.post(f"/term/{ticker}", json={}).json()
    point = next(p for p in term["points"] if p["expiry"] == expiry)
    assert point["varSwapQuote"] == pytest.approx(0.25)
    assert point["varSwapExcluded"] is False


def test_affine_fit_carries_and_honours_varswap(client):
    """The Local-Vol (affine) surface fit reports the shared var-swap quote per
    expiry and its penalty moves the reconstructed var-swap toward a high quote."""
    ticker = client.get("/universe").json()["tickers"][0]
    base = client.post(f"/fit/affine/{ticker}", json={}).json()
    sm0 = base["smiles"][1]
    assert sm0["varSwap"]["level"] is None and sm0["varSwap"]["modelVol"] > 0.0

    expiry = sm0["expiry"]
    quote = sm0["varSwap"]["modelVol"] + 0.06
    client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": quote})

    client.post(f"/calibrate/{ticker}")  # LV is trigger-gated: rebuild after the edit
    pen = client.post(f"/fit/affine/{ticker}", json={}).json()
    sm1 = next(s for s in pen["smiles"] if s["expiry"] == expiry)
    assert sm1["varSwap"]["level"] == pytest.approx(quote)
    assert sm1["varSwap"]["modelVol"] > sm0["varSwap"]["modelVol"]
