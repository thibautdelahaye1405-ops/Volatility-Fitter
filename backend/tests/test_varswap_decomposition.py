"""Strip-vs-tails decomposition of the var-swap replication (V3.6 rider).

Locks volfit.calib.varswap.varswap_decomposition — the SAME integrand and grid
as varswap_total_variance, partitioned by trapezoid-cell midpoint into left
tail / quoted strip / right tail — and its wire readouts (VarSwapInfo
stripVarShare / tailVarShareLeft / tailVarShareRight / stripKLo / stripKHi) on
both the parametric smile payload and the Local-Vol affine payload. Read-only:
the existing byte-identity locks in test_varswap.py are untouched.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.calib.varswap import (
    VS_HALF_WIDTH,
    VS_POINTS,
    varswap_decomposition,
    varswap_total_variance,
)
from volfit.core.black import black_call
from volfit.models.lqd.calibrate import calibrate_slice

REF_DATE = date(2026, 6, 10)

_FIELDS = ("stripVarShare", "tailVarShareLeft", "tailVarShareRight", "stripKLo", "stripKHi")


def _skewed_slice(t=0.5):
    """A fitted LQD slice on a skewed, curved smile (the shares are then
    asymmetric — a symmetric smile would hide a left/right swap)."""
    k = np.linspace(-0.35, 0.25, 13)
    vol = 0.22 - 0.25 * k + 0.6 * k * k
    return calibrate_slice(k, vol * vol * t, t=t).slice, k, t


def test_partition_is_exact_and_total_matches_replication():
    """(a) strip + left + right == total to 1e-12, and total == the existing
    varswap_total_variance on the same fitted LQD slice (shared helper)."""
    sl, k, _ = _skewed_slice()
    d = varswap_decomposition(sl.implied_w, float(k.min()), float(k.max()))
    assert d.strip_w + d.tail_left_w + d.tail_right_w == pytest.approx(d.total_w, abs=1e-12)
    assert d.total_w == pytest.approx(varswap_total_variance(sl.implied_w), abs=1e-12)
    assert d.total_w > 0.0 and d.strip_w > 0.0
    assert d.tail_left_w > 0.0 and d.tail_right_w > 0.0  # wings carry real mass
    shares = d.shares()
    assert shares is not None and sum(shares) == pytest.approx(1.0, abs=1e-9)
    assert 0.5 < shares[0] < 1.0  # the quoted strip carries the bulk of the mass


def test_widening_the_strip_never_decreases_its_share():
    """(b) Monotonicity: the strip share is non-decreasing in the span."""
    sl, _, _ = _skewed_slice()
    prev = -1.0
    for half in np.linspace(0.02, 2.0, 25):
        d = varswap_decomposition(sl.implied_w, -half, half)
        share = d.shares()[0]
        assert share >= prev - 1e-12  # cells are OTM prices >= 0 up to rounding
        prev = share
    # Asymmetric widening on one side only moves that side's tail.
    a = varswap_decomposition(sl.implied_w, -0.3, 0.2)
    b = varswap_decomposition(sl.implied_w, -0.6, 0.2)
    assert b.tail_left_w <= a.tail_left_w + 1e-12
    assert b.tail_right_w == a.tail_right_w  # identical cells, identical sum


def test_flat_smile_shares_match_a_direct_regional_trapezoid():
    """(c) Flat smile: with the span endpoints ON grid points, the midpoint
    rule reduces to a plain trapezoid of the same integrand restricted to each
    region — an independent one-liner per region."""
    sigma, t = 0.25, 0.75
    w_flat = sigma * sigma * t
    k = np.linspace(-VS_HALF_WIDTH, VS_HALF_WIDTH, VS_POINTS)
    k_lo, k_hi = float(k[360]), float(k[440])  # grid points ⇒ cells align
    f = black_call(k, np.full(k.size, w_flat)) * np.exp(-k)
    f[k < 0.0] += 1.0 - np.exp(-k[k < 0.0])
    strip = 2.0 * np.trapezoid(f[(k >= k_lo) & (k <= k_hi)], k[(k >= k_lo) & (k <= k_hi)])
    left = 2.0 * np.trapezoid(f[k <= k_lo], k[k <= k_lo])
    right = 2.0 * np.trapezoid(f[k >= k_hi], k[k >= k_hi])
    d = varswap_decomposition(lambda kk: np.full(np.asarray(kk).shape, w_flat), k_lo, k_hi)
    assert d.strip_w == pytest.approx(strip, abs=1e-12)
    assert d.tail_left_w == pytest.approx(left, abs=1e-12)
    assert d.tail_right_w == pytest.approx(right, abs=1e-12)
    # A flat smile replicates w exactly; the 801-point trapezoid is ~1e-3
    # relative (the OTM put/call integrand has a derivative kink at k = 0).
    assert d.total_w == pytest.approx(w_flat, rel=2e-3)


def test_degenerate_span_puts_everything_in_the_tails():
    sl, _, _ = _skewed_slice()
    d = varswap_decomposition(sl.implied_w, 0.1, 0.1)
    assert d.strip_w == pytest.approx(0.0, abs=1e-15)
    assert d.tail_left_w + d.tail_right_w == pytest.approx(d.total_w, abs=1e-12)
    inv = varswap_decomposition(sl.implied_w, 0.2, -0.2)  # inverted: no double count
    assert inv.strip_w == 0.0
    assert inv.tail_left_w + inv.tail_right_w == pytest.approx(inv.total_w, abs=1e-12)


# --------------------------------------------------------------- wire locks
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _first_node(client):
    uni = client.get("/universe").json()
    ticker = uni["tickers"][0]
    return ticker, uni["expiries"][ticker][0]["expiry"]


def _assert_split_fields(vs: dict) -> None:
    for name in _FIELDS:
        assert name in vs and vs[name] is not None, name
    shares = (vs["stripVarShare"], vs["tailVarShareLeft"], vs["tailVarShareRight"])
    assert all(0.0 <= s <= 1.0 for s in shares), shares
    assert sum(shares) == pytest.approx(1.0, abs=1e-9)
    assert vs["stripKLo"] < vs["stripKHi"]


def test_smile_payload_carries_the_split(client):
    """(d) GET /smiles/{t}/{e}: the five fields ride on varSwap, shares in
    [0, 1] summing to one, the strip span is the included quotes' k span."""
    ticker, expiry = _first_node(client)
    data = client.get(f"/smiles/{ticker}/{expiry}").json()
    vs = data["varSwap"]
    _assert_split_fields(vs)
    ks = [q["k"] for q in data["quotes"] if not q["excluded"]]
    assert vs["stripKLo"] == pytest.approx(min(ks))
    assert vs["stripKHi"] == pytest.approx(max(ks))
    # Excluding the outermost quote narrows the strip: the span follows the
    # INCLUDED quotes (the quote-edit session), not the fetched chain.
    outer = max(range(len(data["quotes"])), key=lambda i: data["quotes"][i]["k"])
    edited = client.post(
        f"/smiles/{ticker}/{expiry}/edits", json={"action": "exclude", "index": outer}
    )
    assert edited.status_code == 200
    vs2 = edited.json()["varSwap"]
    _assert_split_fields(vs2)
    assert vs2["stripKHi"] < vs["stripKHi"]


def test_affine_payload_carries_the_lv_split(client):
    """LV wiring: each affine smile's varSwap carries the lattice split of the
    surface's OWN static replication (shares sum to one, span = the expiry's
    fit-input k range)."""
    ticker = client.get("/universe").json()["tickers"][0]
    aff = client.post(f"/fit/affine/{ticker}", json={}).json()
    sm = aff["smiles"][1]
    vs = sm["varSwap"]
    _assert_split_fields(vs)
    ks = [q["k"] for q in sm["quotes"] if not q["excluded"]]
    assert vs["stripKLo"] == pytest.approx(min(ks), abs=1e-9)
    assert vs["stripKHi"] == pytest.approx(max(ks), abs=1e-9)
