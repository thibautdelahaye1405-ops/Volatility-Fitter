"""Short-dated objective knobs (2026-08 ruggedness arc, final wave).

Covers the three opt-in objective fixes — every default byte-identical:

1. ``midAnchorTauRef`` — tau-aware mid-anchor attenuation
   (calib.band.effective_mid_anchor), applied inside all three parametric
   calibrators (LQD / SVI / Multi-Core Sigmoid);
2. ``robustLoss`` / ``robustFScale`` — IRLS robust reweighting of the QUOTE
   rows only (calib.band.robust_multipliers): scipy's global ``loss=`` would
   also soften the no-arb / calendar / prior rows, which must stay quadratic.
   The LV affine analogue (the original fix-order #3) shipped 2026-08-27 as
   models/localvol/affine_robust.py (locked in test_lv_affine_robust);
3. ``overlayPriceResiduals`` — SVI / MCS data rows in vega-normalized price
   space (the LQD convention, calib.band.price_targets), with the SVI
   analytic Jacobian extended by the row-wise dC/dw chain factor (FD-locked
   below); MCS gained the same analytic price rows on 2026-08-27
   (models/sigmoid/price_rows.py, FD-locked in test_sigmoid_price_jacobian).
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.calib.band import (
    BandTarget,
    band_residuals,
    effective_mid_anchor,
    price_targets,
    quote_residual_magnitude,
    resolve_band,
    robust_multipliers,
)
from volfit.core.black import black_call
from volfit.models.lqd.calibrate import calibrate_slice
from volfit.models.sigmoid import calibrate_sigmoid
from volfit.models.svi_jw import calibrate_svi
from volfit.models.svi_jw.calibrate import _penalties, _unpack
from volfit.models.svi_jw.jacobian import (
    svi_residual_jacobian,
    svi_residual_jacobian_structural,
)
from volfit.models.svi_jw.structural import pack_structural, unpack_structural
from volfit.models.svi_jw.svi import RawSVI

MODELS = ["lqd", "svi", "sigmoid"]


# ----------------------------------------------------------------- helpers
def _fit(model, k, w, t, band=None, **kw):
    if model == "lqd":
        return calibrate_slice(k, w, t, band=band, **kw)
    if model == "svi":
        return calibrate_svi(k, w, t, band=band, **kw)
    return calibrate_sigmoid(k, w, t, n_cores=0, band=band, **kw)


def _vec(model, fit) -> np.ndarray:
    """The fitted parameter vector (exact-equality carrier)."""
    if model == "lqd":
        return fit.params.to_vector()
    if model == "svi":
        r = fit.raw
        return np.array([r.a, r.b, r.rho, r.m, r.sigma])
    return fit.to_vector()


def _model_vol(model, fit, k, t) -> np.ndarray:
    if model == "lqd":
        w = fit.slice.implied_w(k)
    elif model == "svi":
        w = fit.raw.total_variance(k)
    else:
        w = fit.implied_w(k)
    return np.sqrt(np.maximum(w, 1e-12) / t)


# ------------------------------------------------- effective_mid_anchor unit
def test_effective_mid_anchor_none_is_identity():
    w = 0.05
    # None must not even touch the float: the identical object comes back.
    assert effective_mid_anchor(w, 0.01, None) is w


def test_effective_mid_anchor_attenuation_value():
    # sqrt(0.01 / 0.04) = 0.5 -> half the anchor weight.
    assert effective_mid_anchor(0.05, 0.01, 0.04) == pytest.approx(0.025, rel=1e-12)


def test_effective_mid_anchor_caps_at_one_for_long_tau():
    assert effective_mid_anchor(0.05, 2.0, 0.04) == 0.05  # min(1, sqrt(50)) = 1
    assert effective_mid_anchor(0.05, 0.04, 0.04) == 0.05  # exactly at the ref


# ------------------------------------------------------ robust_multipliers unit
def test_robust_multipliers_values():
    r = np.array([0.0, 0.005, 0.01, 0.05])
    np.testing.assert_array_equal(robust_multipliers(r, "off", 0.005), np.ones(4))
    np.testing.assert_allclose(
        robust_multipliers(r, "huber", 0.005), [1.0, 1.0, 0.5, 0.1]
    )
    np.testing.assert_allclose(
        robust_multipliers(r, "cauchy", 0.005),
        [1.0, 0.5, 1.0 / 5.0, 1.0 / 101.0],
    )


def test_quote_residual_magnitude_band_combines_hinge_and_anchor():
    model = np.array([0.25, 0.20])
    lo, mid, hi = np.array([0.18, 0.18]), np.array([0.20, 0.19]), np.array([0.22, 0.22])
    r = quote_residual_magnitude(model, mid, lo, hi, 0.05)
    # First quote: 3 volpts above the band + 5 volpts off mid; second: in-band.
    np.testing.assert_allclose(
        r, [np.sqrt(0.03**2 + 0.05 * 0.05**2), np.sqrt(0.05 * 0.01**2)]
    )
    # Mid mode: plain |model - mid| (scaled).
    np.testing.assert_allclose(
        quote_residual_magnitude(model, mid, None, None, 0.05, 2.0),
        [0.10, 0.02],
    )


# ------------------------------------------------- midAnchorTauRef per model
def _short_band_fixture(t=0.02):
    """A short-dated band fixture whose hinge rows are ACTIVE at the solution:
    a +-2 volpt tick staircase inside a +-0.4 volpt band that no smooth family
    can hold. Active hinges are essential — with every quote in-band the
    anchor attenuation is a uniform rescale of the whole data block and the
    argmin cannot move (only LQD's barrier row would break the scale)."""
    k = np.linspace(-0.15, 0.15, 17)
    true_vol = 0.25 - 0.4 * k + 1.2 * k**2
    mid = true_vol.copy()
    zig = np.array([6, 7, 8, 9, 10])
    mid[zig] += 0.02 * (-1.0) ** zig
    band = resolve_band(mid - 0.004, mid, mid + 0.004, "bidask")
    return k, mid**2 * t, t, band


@pytest.mark.parametrize("model", MODELS)
def test_mid_anchor_tau_ref_moves_short_tau_band_fit(model):
    k, w, t, band = _short_band_fixture()
    base = _vec(model, _fit(model, k, w, t, band=band))
    atten = _vec(model, _fit(model, k, w, t, band=band, mid_anchor_tau_ref=1.0))
    # sqrt(0.02 / 1.0) ~ 0.14: the anchor fades 7x and the band fit moves.
    assert np.max(np.abs(base - atten)) > 1e-7


@pytest.mark.parametrize("model", MODELS)
def test_mid_anchor_tau_ref_long_tau_byte_identical(model):
    k, w, t, band = _short_band_fixture(t=1.5)
    base = _vec(model, _fit(model, k, w, t, band=band))
    same = _vec(model, _fit(model, k, w, t, band=band, mid_anchor_tau_ref=0.05))
    # tau >> ref: the attenuation caps at exactly 1.0 -> byte-identical fit.
    np.testing.assert_array_equal(base, same)


# --------------------------------------------------------- IRLS robust loss
def _outlier_fixture(t=0.25):
    """A smooth mid smile with ONE gross (+5 volpt) off-market print."""
    k = np.linspace(-0.3, 0.3, 21)
    mid = 0.22 - 0.25 * k + 0.6 * k**2
    j = 6
    mid = mid.copy()
    mid[j] += 0.05
    return k, mid, t, j


@pytest.mark.parametrize("model", MODELS)
def test_huber_pulls_fit_back_to_clean_quotes(model):
    k, mid, t, j = _outlier_fixture()
    w = mid**2 * t
    keep = np.ones(k.size, dtype=bool)
    keep[j] = False
    # Reference: the outlier-free fit; both robust passes terminate (returns).
    clean = _model_vol(model, _fit(model, k[keep], w[keep], t), k[keep], t)
    off = _model_vol(model, _fit(model, k, w, t), k[keep], t)
    hub = _model_vol(
        model, _fit(model, k, w, t, robust_loss="huber"), k[keep], t
    )
    err_off = float(np.sqrt(np.mean((off - clean) ** 2)))
    err_hub = float(np.sqrt(np.mean((hub - clean) ** 2)))
    assert err_hub < err_off  # closer to the outlier-free fit than "off"


@pytest.mark.parametrize("model", MODELS)
def test_robust_off_is_byte_identical(model):
    k, mid, t, _ = _outlier_fixture()
    w = mid**2 * t
    base = _vec(model, _fit(model, k, w, t))
    off = _vec(model, _fit(model, k, w, t, robust_loss="off", robust_f_scale=0.01))
    np.testing.assert_array_equal(base, off)


@pytest.mark.parametrize("model", MODELS)
def test_huber_band_mode_in_band_deviation_untouched(model):
    """An off-mid quote still INSIDE a wide band: the hinge is zero and the
    anchor magnitude stays under the f-scale, so every IRLS multiplier is
    exactly 1 and the warm-started re-solves stay at the base solution."""
    t = 0.25
    k = np.linspace(-0.25, 0.25, 15)
    true_vol = 0.22 - 0.25 * k + 0.5 * k**2
    mid = true_vol.copy()
    mid[7] += 0.015  # 1.5 volpts off-mid, inside the +-3 volpt band
    band = resolve_band(true_vol - 0.03, mid, true_vol + 0.03, "bidask")
    w = mid**2 * t
    base = _model_vol(model, _fit(model, k, w, t, band=band), k, t)
    hub = _model_vol(
        model,
        _fit(model, k, w, t, band=band, robust_loss="huber", robust_f_scale=0.02),
        k, t,
    )
    np.testing.assert_allclose(hub, base, atol=1e-7)


# --------------------------------------------- overlayPriceResiduals (SVI/MCS)
def _wing_fixture():
    """Short-dated smile plus one deep far-wing quote with a gross IV bump —
    a multi-vol-point IV quantum whose price is still ~0 (sub-tick vega)."""
    t = 0.02
    k = np.append(np.linspace(-0.2, 0.2, 15), 0.42)
    vol = 0.25 - 0.3 * k + 1.0 * k**2
    vol[-1] += 0.15
    return k, vol**2 * t, t


@pytest.mark.parametrize("model", ["svi", "sigmoid"])
def test_price_residuals_change_fit_and_drop_wing_influence(model):
    k, w, t = _wing_fixture()
    vol_fit = _model_vol(model, _fit(model, k, w, t), k, t)
    px_fit = _model_vol(model, _fit(model, k, w, t, price_residuals=True), k, t)
    quote_vol = np.sqrt(w / t)
    # The toggle changes the fitted smile...
    assert np.max(np.abs(px_fit - vol_fit)) > 1e-6
    # ...and the far-wing quote's pull collapses: in price space its
    # vega-normalized residual is ~0, so the fit no longer chases the bump.
    assert abs(px_fit[-1] - quote_vol[-1]) > abs(vol_fit[-1] - quote_vol[-1])


@pytest.mark.parametrize("model", ["svi", "sigmoid"])
def test_price_residuals_off_is_byte_identical(model):
    k, w, t = _wing_fixture()
    base = _vec(model, _fit(model, k, w, t))
    off = _vec(model, _fit(model, k, w, t, price_residuals=False))
    np.testing.assert_array_equal(base, off)


# ------------------------------------- SVI price-row analytic Jacobian FD lock
T_J = 0.1
K_J = np.linspace(-0.3, 0.3, 15)
PW, LEE, MAW = 1e3, 1.95, 0.05
QUOTED = RawSVI(a=0.02, b=0.10, rho=-0.30, m=0.0, sigma=0.20)  # the quotes
FIT_AT = RawSVI(a=0.022, b=0.13, rho=-0.24, m=0.015, sigma=0.22)  # eval point


def _resid_price(theta, unpack_fn, band, pt):
    """The calibrator's price-space data rows + the two penalty rows."""
    raw = unpack_fn(theta)
    target_price, inv_vega, price_lo, price_hi = pt
    model_price = black_call(K_J, np.maximum(raw.total_variance(K_J), 1e-12))
    if band is None:
        fit = inv_vega * (model_price - target_price)  # unit scheme weights
    else:
        fit = band_residuals(model_price, price_lo, price_hi, target_price, inv_vega, MAW)
    return np.concatenate((fit, _penalties(raw, PW, LEE)))


def _fd(fn, theta, eps=1e-7):
    base = fn(theta)
    j = np.empty((base.size, theta.size))
    for p in range(theta.size):
        d = np.zeros_like(theta)
        d[p] = eps
        j[:, p] = (fn(theta + d) - fn(theta - d)) / (2.0 * eps)
    return j


def _theta_raw(raw: RawSVI) -> np.ndarray:
    return np.array(
        [raw.a, np.log(np.expm1(raw.b)), np.arctanh(raw.rho), raw.m, np.log(raw.sigma)]
    )


@pytest.mark.parametrize("with_band", [False, True])
@pytest.mark.parametrize("chart", ["raw", "structural"])
def test_svi_price_jacobian_matches_fd(chart, with_band):
    w_q = QUOTED.total_variance(K_J)
    mid = np.sqrt(w_q / T_J)
    band = BandTarget(iv_lo=mid - 0.01, iv_mid=mid, iv_hi=mid + 0.01) if with_band else None
    pt = price_targets(K_J, w_q, T_J, band)
    ones = np.ones_like(K_J)
    if chart == "raw":
        theta = _theta_raw(FIT_AT)
        unpack_fn = _unpack
        an = svi_residual_jacobian(
            theta, K_J, T_J, ones, band, MAW, PW, LEE, None, None, 0.0,
            price_targets=pt,
        )
    else:
        theta = pack_structural(FIT_AT, LEE)
        unpack_fn = lambda th: unpack_structural(th, LEE)  # noqa: E731
        an = svi_residual_jacobian_structural(
            theta, K_J, T_J, ones, band, MAW, PW, LEE, None, None, 0.0,
            price_targets=pt,
        )
    fd = _fd(lambda th: _resid_price(th, unpack_fn, band, pt), theta)
    assert an.shape == fd.shape
    np.testing.assert_allclose(an, fd, rtol=5e-4, atol=1e-7)


# ------------------------------------------------------------- API threading
REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    from volfit.api import create_app

    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _vols(client, expiry, fit_mode="mid"):
    data = client.get(f"/smiles/ALPHA/{expiry}?fit_mode={fit_mode}").json()
    return np.array([p["vol"] for p in data["model"]])


def _differs(a, b, tol=1e-7) -> bool:
    return bool(np.max(np.abs(np.asarray(a) - np.asarray(b))) > tol)


def test_api_shortdated_settings_reach_the_fits(client):
    """PUT each new knob -> the displayed fit changes; defaults are the OFF
    values (the full defaults payload is locked in test_api_settings.py)."""
    settings = client.get("/settings/fit").json()
    assert settings["midAnchorTauRef"] is None
    assert settings["robustLoss"] == "off"
    assert settings["robustFScale"] == 0.005
    assert settings["overlayPriceResiduals"] is False

    expiry = client.get("/universe").json()["expiries"]["ALPHA"][2]["expiry"]

    # midAnchorTauRef: the band-mode (bidask) LQD fit moves when the anchor fades.
    base_band = _vols(client, expiry, "bidask")
    assert client.put("/settings/fit", json={"midAnchorTauRef": 5.0}).status_code == 200
    assert _differs(_vols(client, expiry, "bidask"), base_band)
    client.put("/settings/fit", json={})  # back to defaults

    # Amend one quote into a gross off-market print: the residual structure a
    # near-perfect synthetic chain lacks, needed by both remaining knobs.
    client.put("/settings/fit", json={"model": "svi"})
    data = client.get(f"/smiles/ALPHA/{expiry}").json()
    q = data["quotes"][len(data["quotes"]) // 3]
    resp = client.post(
        f"/smiles/ALPHA/{expiry}/edits",
        json={"action": "amend", "index": q["index"], "mid": q["mid"] + 0.05},
    )
    assert resp.status_code == 200
    off_vols = _vols(client, expiry)

    # robustLoss: the huber IRLS fit visibly differs (it downweights the print).
    client.put("/settings/fit", json={"model": "svi", "robustLoss": "huber"})
    assert _differs(_vols(client, expiry), off_vols)

    # overlayPriceResiduals: the SVI overlay switches to price-space rows,
    # changing how much of the off-market print bleeds into the smile.
    client.put("/settings/fit", json={"model": "svi", "overlayPriceResiduals": True})
    assert _differs(_vols(client, expiry), off_vols)

    # Back to defaults + no edits: cleanup.
    client.post(f"/smiles/ALPHA/{expiry}/edits", json={"action": "reset"})
    client.put("/settings/fit", json={})
