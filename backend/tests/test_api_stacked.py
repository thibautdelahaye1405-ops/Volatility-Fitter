"""API test: GET /smiles/{ticker}/densities (stacked-densities view, Phase 10).

One density per fitted expiry, model-aware, each non-negative and integrating
to ~1 over the central mass (the visual no-butterfly-arbitrage check).

V3.3 item 11 (sub-zero density evidence): the SIGNED un-clipped channel
``densityRaw`` + ``minDensity``/``minDensityX`` — attached only when a
negative region exists; computed on the FULL grid before chart striding so a
dip narrower than the display stride is still reported; absent for LQD
(structurally positive) so the legacy payload is byte-identical.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.analytics import _distribution_model, stacked_density_arrays
from volfit.models.diagnostics import belly_certificate, numeric_density

REF_DATE = date(2026, 6, 10)


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_stacked_densities_shape(client):
    ticker = client.get("/universe").json()["tickers"][0]
    resp = client.get(f"/smiles/{ticker}/densities")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["ticker"] == ticker
    expiries = data["expiries"]
    assert len(expiries) >= 2
    # Nearest-first, strictly increasing maturities.
    ts = [e["t"] for e in expiries]
    assert ts == sorted(ts)
    for e in expiries:
        x = np.array(e["x"])
        pdf = np.array(e["density"])
        assert x.size > 10 and len(pdf) == len(x)
        assert np.all(pdf >= 0.0)  # no butterfly arbitrage on any slice
        assert 0.8 < float(np.trapezoid(pdf, x)) <= 1.0 + 1e-6


def test_stacked_densities_reach_k_min(client):
    """Every stacked density extends its left tail to the display lower bound
    k_min = -1.4 (matching the smile / surface range), staying finite + >= 0."""
    ticker = client.get("/universe").json()["tickers"][0]
    expiries = client.get(f"/smiles/{ticker}/densities").json()["expiries"]
    for e in expiries:
        x = np.array(e["x"])
        assert x.min() <= -1.4 + 1e-2  # left tail drawn out to ~ -1.4
        assert np.all(np.isfinite(np.array(e["density"])))


def test_stacked_densities_unknown_ticker(client):
    assert client.get("/smiles/NOPE/densities").status_code == 404


# ------------------------------------------------ V3.3 item 11: sub-zero evidence
class _DentSlice:
    """Flat ~20%-vol smile with a NARROW variance bump at k0: the local w'' is
    strongly negative, so Durrleman g (hence the signed pdf) dips below zero
    over a window (~0.008 in k) narrower than the stacked chart's display
    stride — the exact stride hazard the pre-stride min/argmin fields close.
    A rigged butterfly-arb slice in the belly (the Vogt dip lives too far in
    the right tail to survive the display window's cdf trim)."""

    K0 = 0.05
    AMP = 8e-5
    WIDTH = 0.004  # g < 0 over roughly k0 +- width

    def implied_w(self, k):
        k = np.asarray(k, dtype=float)
        u = (k - self.K0) / self.WIDTH
        return 0.04 + self.AMP * np.exp(-0.5 * u * u)


def test_rigged_dip_reports_raw_min_and_location():
    """A g < 0 slice: densityRaw dips, the clipped density does not, and the
    reported argmin sits at the belly certificate's own argmin location."""
    slice_ = _DentSlice()
    x, density, raw, min_d, min_x = stacked_density_arrays(slice_, with_raw=True)
    assert min_d < 0.0
    assert min_x == pytest.approx(_DentSlice.K0, abs=0.02)
    assert np.all(density >= 0.0)  # the clipped curve cannot dip
    # The emitted raw channel is exactly the signed twin of the clipped curve.
    np.testing.assert_array_equal(density, np.maximum(raw, 0.0))
    # Same defect the belly certificate reports, same location.
    cert = belly_certificate(slice_, -0.5, 0.5)
    assert cert is not None and not cert.certified and cert.min_g < 0.0
    assert min_x == pytest.approx(cert.argmin_k, abs=0.02)


def test_stride_hazard_min_is_pre_stride():
    """The reported minimum equals an independent FULL-grid computation over
    the displayed window — never the strided chart array's minimum, which can
    sample straight past a dip narrower than the stride."""
    slice_ = _DentSlice()
    x, density, raw, min_d, min_x = stacked_density_arrays(slice_, with_raw=True)
    k, pdf, cdf, full_raw = numeric_density(slice_, half_floor=1.4, return_raw=True)
    # The evidence window: displayed range, central probability mass (the
    # U_TRIM discipline on BOTH sides — the drawn deep tail is display only).
    window = (k >= -1.4) & (cdf >= 1e-3) & (cdf <= 1.0 - 1e-3)
    assert min_d == pytest.approx(float(full_raw[window].min()), rel=1e-12)
    # The dip (~2 * WIDTH wide) is narrower than the emitted grid spacing —
    # the hazard is real on this fixture, not hypothetical.
    assert float(np.median(np.diff(x))) > 2.0 * _DentSlice.WIDTH
    # And the reported min is at least as deep as anything the chart shows.
    assert min_d <= float(np.min(raw)) + 1e-15


def test_clean_slice_raw_channel_matches_and_reports_no_dip():
    """A clean flat slice: raw == clipped everywhere, min >= 0 (no evidence to
    attach — the payload layer keys the fields off min < 0)."""
    from volfit.models.svi_jw import RawSVI

    flat = RawSVI(a=0.04, b=0.0, rho=0.0, m=0.0, sigma=1.0)
    x, density, raw, min_d, _ = stacked_density_arrays(flat, with_raw=True)
    assert min_d >= 0.0
    np.testing.assert_array_equal(density, raw)
    # Default 2-tuple path: byte-identical arrays to the with_raw call.
    x2, density2 = stacked_density_arrays(flat)
    np.testing.assert_array_equal(x, x2)
    np.testing.assert_array_equal(density, density2)


def test_distribution_model_attaches_raw_only_on_dip():
    """_distribution_model (the single-node Density view): densityRaw attached
    (same emitted grid) for the rigged slice, absent for a clean one."""
    from volfit.models.svi_jw import RawSVI

    dipped = _distribution_model(_DentSlice())
    assert len(dipped.densityRaw) == len(dipped.density) > 0
    a = np.array(dipped.densityRaw)
    b = np.array(dipped.density)
    np.testing.assert_array_equal(b, np.maximum(a, 0.0))  # clipped twin

    clean = _distribution_model(RawSVI(a=0.04, b=0.0, rho=0.0, m=0.0, sigma=1.0))
    assert clean.densityRaw == []


def test_lqd_stacked_payload_has_no_raw_fields(client):
    """LQD is structurally positive: the evidence fields never attach, so the
    legacy stacked payload is byte-identical (the item-11 guard)."""
    ticker = client.get("/universe").json()["tickers"][0]
    expiries = client.get(f"/smiles/{ticker}/densities").json()["expiries"]
    assert len(expiries) >= 2
    for e in expiries:
        assert e["densityRaw"] == []
        assert e["minDensity"] is None
        assert e["minDensityX"] is None
