"""GET /smiles/{t}/{e}/compare?tail_match=… — the tail-matching toggles.

Locks: with a flag the SVI-JW / MCS rows are refit onto LQD's numbers (the
var-swap level, the Lee slopes, the quoted-edge values) and say so
(``tailMatched``), while LQD and the eSSVI yardstick stay untouched; the
constrained rows live under their own cache keys beside the plain rows and
are never a committed-record reuse; Lee is reported unavailable (and dropped)
when the name's LQD tails are generalized; an unknown flag is a 422.

In-process over fastapi.testclient on the synthetic universe (the
test_api_compare.py style).
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
ALL = "lqd,svi,sigmoid,essvi"
CONSTRAINED = ("svi", "sigmoid")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def node(client):
    universe = client.get("/universe").json()
    ticker = universe["tickers"][0]
    client.app.state.volfit.snapshot(ticker)  # warm the chain (ungated read fetch) — no fit
    return ticker, universe["expiries"][ticker][0]["expiry"]


def _compare(client, node, **params):
    ticker, expiry = node
    r = client.get(f"/smiles/{ticker}/{expiry}/compare", params={"models": ALL, **params})
    assert r.status_code == 200, r.text
    return r.json()


def _row(payload, family):
    return next(r for r in payload["models"] if r["model"] == family)


def _curve_at(row, k):
    ks = [p["k"] for p in row["curve"]]
    vols = [p["vol"] for p in row["curve"]]
    i = max(j for j, kk in enumerate(ks) if kk <= k)
    frac = (k - ks[i]) / (ks[i + 1] - ks[i])
    return vols[i] + frac * (vols[i + 1] - vols[i])


def test_var_swap_flag_pins_the_straight_wing_families_to_lqd(client, node):
    plain = _compare(client, node)
    assert plain.get("tailMatch") is None
    payload = _compare(client, node, tail_match="varswap")
    info = payload["tailMatch"]
    assert info["requested"] == ["varswap"] and info["applied"] == ["varswap"]
    assert info["target"] == "lqd" and info["leeAvailable"] is True
    lqd = _row(payload, "lqd")
    assert lqd["tailMatched"] == [] and _row(payload, "essvi")["tailMatched"] == []
    assert abs(info["referenceVarSwapVol"] - lqd["varSwapVol"]) < 1e-9
    for family in CONSTRAINED:
        row = _row(payload, family)
        assert row["ok"], row.get("error")
        assert row["tailMatched"] == ["varswap"] and row["reused"] is False
        assert abs(row["varSwapVol"] - lqd["varSwapVol"]) < 3e-4, family
    # The plain fits did NOT share LQD's var-swap this tightly on every row.
    plain_gap = max(abs(_row(plain, f)["varSwapVol"] - _row(plain, "lqd")["varSwapVol"]) for f in CONSTRAINED)
    pinned_gap = max(abs(_row(payload, f)["varSwapVol"] - lqd["varSwapVol"]) for f in CONSTRAINED)
    assert pinned_gap <= plain_gap + 1e-12


def test_lee_flag_matches_the_asymptotic_slopes(client, node):
    payload = _compare(client, node, tail_match="lee")
    info = payload["tailMatch"]
    assert info["applied"] == ["lee"]
    lqd = _row(payload, "lqd")
    assert info["referenceLeeLeft"] == pytest.approx(lqd["leeLeft"])
    assert info["referenceLeeRight"] == pytest.approx(lqd["leeRight"])
    target_l = min(lqd["leeLeft"], 1.95 - 0.02) if info["leeClamped"] else lqd["leeLeft"]
    target_r = min(lqd["leeRight"], 1.95 - 0.02) if info["leeClamped"] else lqd["leeRight"]
    for family in CONSTRAINED:
        row = _row(payload, family)
        assert row["ok"], row.get("error")
        assert row["tailMatched"] == ["lee"]
        assert abs(row["leeLeft"] - target_l) < 5e-3, family
        assert abs(row["leeRight"] - target_r) < 5e-3, family


def test_edge_flag_matches_value_at_the_quoted_edges(client, node):
    payload = _compare(client, node, tail_match="edge")
    info = payload["tailMatch"]
    assert info["applied"] == ["edge"]
    lqd = _row(payload, "lqd")
    for family in CONSTRAINED:
        row = _row(payload, family)
        assert row["ok"], row.get("error")
        assert row["tailMatched"] == ["edge"]
        for k_edge in (info["edgeKLeft"], info["edgeKRight"]):
            assert abs(_curve_at(row, k_edge) - _curve_at(lqd, k_edge)) < 5e-4, (family, k_edge)


def test_all_three_flags_report_in_wire_order_and_cache_separately(client, node):
    ticker, expiry = node
    payload = _compare(client, node, tail_match="edge,lee,varswap")
    info = payload["tailMatch"]
    assert info["requested"] == ["varswap", "lee", "edge"]
    assert info["applied"] == ["varswap", "lee", "edge"]
    for family in CONSTRAINED:
        assert _row(payload, family)["tailMatched"] == ["varswap", "lee", "edge"]
    cache = client.app.state.volfit._compare_cache
    keys = list(cache.entries)
    plain = [k for k in keys if len(k) == 2 and k[1] == "svi"]
    flagged = [k for k in keys if len(k) == 3 and k[1] == "svi"]
    assert plain and flagged  # both rows coexist under distinct keys
    assert ("varswap", "lee", "edge") in {k[2] for k in flagged}
    hits = cache.hits
    again = _compare(client, node, tail_match="varswap,lee,edge")
    assert cache.hits == hits + 5  # the LQD reference read + every row, all from the side cache
    assert again["models"] == payload["models"]


def test_lee_is_unavailable_when_lqd_tails_are_generalized(client, node):
    ticker, _ = node
    fit = client.get("/settings/fit").json()
    try:
        assert client.put("/settings/fit", json={"tailAlphaByTicker": {ticker: [0.25, 0.25]}}).status_code == 200
        payload = _compare(client, node, tail_match="lee,edge")
        info = payload["tailMatch"]
        assert info["leeAvailable"] is False
        assert info["applied"] == ["edge"]  # Lee dropped, Edge still applies
        assert "alpha > 0" in (info["note"] or "")
        for family in CONSTRAINED:
            assert _row(payload, family)["tailMatched"] == ["edge"]
        only_lee = _compare(client, node, tail_match="lee")
        assert only_lee["tailMatch"]["applied"] == []
        for family in CONSTRAINED:
            assert _row(only_lee, family)["tailMatched"] == []  # the plain fit
    finally:
        assert client.put("/settings/fit", json={"tailAlphaByTicker": fit["tailAlphaByTicker"]}).status_code == 200


def test_unknown_tail_flag_is_422(client, node):
    ticker, expiry = node
    r = client.get(f"/smiles/{ticker}/{expiry}/compare", params={"models": ALL, "tail_match": "varswap,wings"})
    assert r.status_code == 422
    assert "unknown" in r.json()["detail"]
