"""Stacked-IV display crop tables (volfit.api.crop, 2026-09-03).

Opt-in Options ``stackCrop`` / ``stackCropTailProb``: each expiry's curve is
drawn only inside its realistic log-moneyness range — the slice's own
[Q(ε), Q(1 − ε)] widened to the quoted range — because a pricer sampling the
fitted distribution never reads the smile beyond with probability 1 − O(ε).
The payloads carry the range at fixed tail levels (1e-2 … 1e-12); the view
interpolates ε. Quotes are always drawn.

Locks:
  * the table from a CDF: monotone (wider for smaller u), never narrower than
    the quoted range, exact on a Gaussian CDF (Q(1e-7) ≈ −5.2 sd), clamped to
    the samples' ends when the tail is unresolved;
  * the surface payload carries one table per expiry, each containing that
    expiry's quoted range, widening with maturity on the clean synthetic;
  * the LV payload carries a table per smile containing its quoted range;
  * the two Options fields exist with their defaults, are display-only (no
    options-version bump) and round-trip.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.crop import TAIL_U_LEVELS, crop_ranges_from_cdf
from volfit.core.black import norm_cdf

REF_DATE = date(2026, 6, 10)


def test_levels_span_the_option_bounds():
    assert TAIL_U_LEVELS[0] == pytest.approx(1e-2)
    assert TAIL_U_LEVELS[-1] == pytest.approx(1e-12)
    assert all(a > b for a, b in zip(TAIL_U_LEVELS, TAIL_U_LEVELS[1:]))


def test_table_from_gaussian_cdf_is_exact_monotone_and_contains_quotes():
    sd = 0.1
    k = np.linspace(-1.5, 1.5, 30001)
    cdf = norm_cdf(k / sd)
    table = crop_ranges_from_cdf(k, cdf, k_quote_lo=-0.05, k_quote_hi=0.02)
    assert table.u == TAIL_U_LEVELS
    j = TAIL_U_LEVELS.index(1e-7)
    # Q(1e-7) of a Gaussian is -5.199 sd (first node whose CDF reaches u).
    assert table.lo[j] == pytest.approx(-5.199 * sd, abs=2e-4)
    assert table.hi[j] == pytest.approx(5.199 * sd, abs=2e-4)
    # Wider for smaller u, and never narrower than the quoted range.
    assert all(a >= b for a, b in zip(table.lo, table.lo[1:]))
    assert all(a <= b for a, b in zip(table.hi, table.hi[1:]))
    assert all(lo <= -0.05 for lo in table.lo) and all(hi >= 0.02 for hi in table.hi)
    # The 1e-2 level is narrower than the quotes on the right: the quoted
    # range wins (a traded strike is realistic by definition).
    assert table.hi[0] == pytest.approx(max(2.326 * sd, 0.02), abs=2e-4)


def test_unresolved_tail_clamps_at_the_sample_range():
    k = np.linspace(-0.3, 0.3, 601)
    cdf = norm_cdf(k / 0.1)  # 1e-7 needs 5.2 sd = 0.52: beyond the samples
    table = crop_ranges_from_cdf(k, cdf, 0.0, 0.0)
    j = TAIL_U_LEVELS.index(1e-7)
    assert table.lo[j] == pytest.approx(-0.3)
    assert table.hi[j] == pytest.approx(0.3)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_surface_payload_carries_widening_tables(client):
    ticker = client.get("/universe").json()["tickers"][0]
    assert client.post(f"/calibrate/{ticker}").status_code == 200
    s = client.get(f"/surface/{ticker}").json()
    assert len(s["cropRanges"]) == len(s["expiries"]) >= 2
    j = TAIL_U_LEVELS.index(1e-7)
    widths = []
    for table in s["cropRanges"]:
        assert table["u"] == pytest.approx(TAIL_U_LEVELS)
        assert table["lo"][j] < 0.0 < table["hi"][j]
        assert all(a >= b for a, b in zip(table["lo"], table["lo"][1:]))
        assert all(a <= b for a, b in zip(table["hi"], table["hi"][1:]))
        widths.append(table["hi"][j] - table["lo"][j])
    # Maturity-dependent: the clean synthetic ladder widens with T.
    assert widths == sorted(widths)


def test_affine_payload_carries_tables_containing_the_quoted_range(client):
    ticker = client.get("/universe").json()["tickers"][0]
    resp = client.post(f"/fit/affine/{ticker}", json={})
    assert resp.status_code == 200, resp.text
    j = TAIL_U_LEVELS.index(1e-7)
    for smile in resp.json()["smiles"]:
        table = smile["cropRanges"]
        assert table is not None
        included = [q["k"] for q in smile["quotes"] if not q["excluded"]]
        assert table["lo"][j] <= min(included) and table["hi"][j] >= max(included)
        assert all(a >= b for a, b in zip(table["lo"], table["lo"][1:]))


def test_options_fields_are_display_only(client):
    opts = client.get("/settings/options").json()
    assert opts["stackCrop"] is False and opts["stackCropTailProb"] == pytest.approx(1e-7)
    state = client.app.state.volfit
    v0 = state.options_version
    body = {**opts, "stackCrop": True, "stackCropTailProb": 1e-9}
    try:
        assert client.put("/settings/options", json=body).status_code == 200
        got = client.get("/settings/options").json()
        assert got["stackCrop"] is True and got["stackCropTailProb"] == pytest.approx(1e-9)
        assert state.options_version == v0  # no fit-cache invalidation
        assert client.put("/settings/options", json={**opts, "stackCropTailProb": 0.5}).status_code == 422
    finally:
        assert client.put("/settings/options", json=opts).status_code == 200
