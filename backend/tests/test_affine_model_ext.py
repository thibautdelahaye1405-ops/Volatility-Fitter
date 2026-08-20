"""V3.3 items 3 + 10 (LV side): AffineSmile.modelExt — the untruncated smile
on the shared display grid — and the calendar worst-crossing LOCATION.

modelExt locks (item 3):
  * spans the display grid: left edge <= K_DISPLAY_LO, right edge reaches
    min(K_DISPLAY_HI, ln(x_max) - eps) and NEVER exceeds the PDE lattice
    (price_at np.interp-clamps beyond it — inverting clamped prices is the
    exact failure this feature guards against);
  * every point finite with 0.01 < vol < 2.0 (the test_api_affine discipline);
  * modelExt ≡ model on the quoted-range grid points (one inversion, two
    truncations — the shared core linspace is bit-identical);
  * `model` itself stays truncated to the quoted range ±pad (five consumers
    couple to its x-domain; byte-identity of the legacy payload).

Calendar location locks (item 10): _diagnostics reports (pair, k) of the
deepest adjacent-maturity price decrease on a rigged crossing, None when
clean, and never points at the x = 0 boundary column.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.affine_fit import _K_PAD, _diagnostics
from volfit.api.service import K_DISPLAY_HI, K_DISPLAY_LO

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def fitted(client):
    ticker = client.get("/universe").json()["tickers"][0]
    resp = client.post(f"/fit/affine/{ticker}", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _x_max_upper_bound(data) -> float:
    """Upper bound on the PDE lattice's x_max, reconstructed from the wire
    (mirrors _pde_grids: max(exp(k_hi_global) * 1.4, 2.5); the wire quotes are
    a superset of the fit rows, so this never underestimates)."""
    k_hi_global = max(q["k"] for s in data["smiles"] for q in s["quotes"])
    return max(float(np.exp(k_hi_global)) * 1.4, 2.5)


def test_model_ext_spans_shared_display_grid(fitted):
    ln_x_max = float(np.log(_x_max_upper_bound(fitted)))
    for smile in fitted["smiles"]:
        ext = smile["modelExt"]
        assert len(ext) > 20, "modelExt missing/degenerate"
        ks = [p["k"] for p in ext]
        assert ks == sorted(ks)
        # Left edge: at (or beyond) the display lower bound — no more stubs.
        assert ks[0] <= K_DISPLAY_LO + 1e-9
        # Right edge: reaches the display bound OR the lattice cap, whichever
        # binds (x_max >= 2.5 always, so at least ln(2.5) - eps)...
        assert ks[-1] >= min(K_DISPLAY_HI, float(np.log(2.5))) - 1e-3
        # ...and NEVER beyond the PDE lattice (clamped prices are never inverted).
        assert ks[-1] <= ln_x_max + 1e-9


def test_model_ext_points_finite_and_sane(fitted):
    """The test_api_affine.py:52-53 discipline, applied to the extension."""
    for smile in fitted["smiles"]:
        for p in smile["modelExt"]:
            assert np.isfinite(p["k"]) and np.isfinite(p["vol"])
            assert 0.01 < p["vol"] < 2.0


def test_model_ext_equals_model_on_quoted_grid(fitted):
    """Same grid points => same values: the extension is the SAME inversion
    with a wider truncation, never a re-fit or a resample of `model`."""
    for smile in fitted["smiles"]:
        ext_k = np.array([p["k"] for p in smile["modelExt"]])
        ext_v = np.array([p["vol"] for p in smile["modelExt"]])
        assert len(smile["model"]) > 10
        for p in smile["model"]:
            j = int(np.argmin(np.abs(ext_k - p["k"])))
            assert abs(ext_k[j] - p["k"]) < 1e-12, "core grid point missing"
            assert ext_v[j] == pytest.approx(p["vol"], rel=1e-9)


def test_model_stays_truncated_to_quoted_range(fitted):
    """`model` is untouched: still confined to the quoted range ± _K_PAD
    (its five consumers couple to that x-domain — the item-3 non-goal)."""
    for smile in fitted["smiles"]:
        included = [q["k"] for q in smile["quotes"] if not q["excluded"]]
        ks = [p["k"] for p in smile["model"]]
        assert min(ks) >= min(included) - _K_PAD - 1e-9
        assert max(ks) <= max(included) + _K_PAD + 1e-9


def test_clean_fit_has_no_calendar_location(fitted):
    assert fitted["calendarViolations"] == 0
    assert fitted["calendarWorstPair"] is None
    assert fitted["calendarWorstK"] is None


# ---------------------------------------------------------- item 10 (LV argmin)
class _Sol:
    """Duck-typed march result: _diagnostics reads only .prices."""

    def __init__(self, prices) -> None:
        self.prices = np.asarray(prices, dtype=float)


def test_diagnostics_locates_rigged_crossing():
    """A forced far-below-near price decrease is located at the exact
    (pair, ln x) of the deepest gap; the count keeps its -1e-9 tolerance."""
    x_grid = np.array([0.0, 0.5, 1.0, 1.5, 2.0])
    near = [1.0, 0.60, 0.30, 0.10, 0.05]
    mid = [1.0, 0.62, 0.33, 0.12, 0.06]  # clean vs near
    far = [1.0, 0.61, 0.32, 0.07, 0.06]  # crosses mid: worst -0.05 at x = 1.5
    min_d, cal, arb, pair, k = _diagnostics(_Sol([near, mid, far]), x_grid)
    assert cal == 3  # three lattice nodes dip below -1e-9 on the mid->far pair
    assert not arb
    assert pair == 1  # expiries[1] -> expiries[2]
    assert k == pytest.approx(float(np.log(1.5)))
    assert len(min_d) == 3


def test_diagnostics_clean_pair_reports_none():
    x_grid = np.array([0.0, 0.5, 1.0, 1.5])
    near = [1.0, 0.60, 0.30, 0.10]
    far = [1.0, 0.62, 0.33, 0.12]
    _, cal, _, pair, k = _diagnostics(_Sol([near, far]), x_grid)
    assert cal == 0 and pair is None and k is None


def test_diagnostics_never_points_at_x_zero_boundary():
    """A rigged violation in the x = 0 column (C(., 0) = 1 boundary) keeps the
    count but yields no location — ln(0) is not a strike."""
    x_grid = np.array([0.0, 0.5, 1.0])
    near = [1.0, 0.60, 0.30]
    far = [0.9, 0.60, 0.30]  # boundary-only decrease
    _, cal, _, pair, k = _diagnostics(_Sol([near, far]), x_grid)
    assert cal == 1
    assert pair is None and k is None
