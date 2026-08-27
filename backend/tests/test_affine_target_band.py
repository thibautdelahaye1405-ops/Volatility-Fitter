"""V3.4 rider — the Local-Vol chart's fit-target overlay (backend half).

The affine payload's QuoteBands (AffineSmile.quotes) now carry the fit-target
edges ``targetLo``/``targetHi`` exactly as the Parametric smile payload does:
both resolve them through ``service.edited_band_full`` — the fit's own band
rule in the FULL prepared index space (excluded quotes keep their would-be
band, an amended quote's haircut band recenters on its amended mid). Locks:

  * "mid": no target (None) on every LV quote;
  * "bidask" / "haircut": LV targetLo/Hi == Parametric targetLo/Hi per quote
    index, bit for bit (same node, same mode);
  * the pre-existing quote fields (k / bid / ask / mid / index / excluded /
    amended) are identical to the Parametric ones — the overlay is a pure
    addition, the rest of the quote payload is untouched;
  * an excluded quote keeps its target on the LV payload too.

The LV read path is frozen (affine_payload), so each mode is calibrated via
POST /calibrate/{ticker}?fit_mode=... before it is read.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)

#: The QuoteBand fields that predate the target overlay (byte-identity set).
QUOTE_FIELDS = ("k", "bid", "ask", "mid", "index", "excluded", "amended")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def ticker(client) -> str:
    return client.get("/universe").json()["tickers"][0]


def _affine_quotes(client, ticker: str, fit_mode: str) -> dict[str, list[dict]]:
    """``{expiry -> LV QuoteBands}`` of the ticker's LV surface fitted in
    ``fit_mode`` (calibrated in that mode first: the read path is frozen)."""
    cal = client.post(f"/calibrate/{ticker}", params={"fit_mode": fit_mode})
    assert cal.status_code == 200, cal.text
    resp = client.post(f"/fit/affine/{ticker}", json={"fitMode": fit_mode})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["hasFit"] is True and data["stale"] is False
    assert len(data["smiles"]) >= 2
    return {s["expiry"]: s["quotes"] for s in data["smiles"]}


def _smile_quotes(client, ticker: str, expiry: str, fit_mode: str) -> list[dict]:
    """The Parametric smile payload's QuoteBands for the same node + mode."""
    resp = client.get(f"/smiles/{ticker}/{expiry}", params={"fit_mode": fit_mode})
    assert resp.status_code == 200, resp.text
    return resp.json()["quotes"]


def _strip(quotes: list[dict]) -> list[dict]:
    return [{f: q[f] for f in QUOTE_FIELDS} for q in quotes]


def test_mid_mode_lv_quotes_carry_no_target(client, ticker):
    by_expiry = _affine_quotes(client, ticker, "mid")
    for expiry, lv in by_expiry.items():
        assert len(lv) >= 2
        assert all(q["targetLo"] is None and q["targetHi"] is None for q in lv)
        # The quote fields themselves are the Parametric ones (same prepared slice).
        assert _strip(lv) == _strip(_smile_quotes(client, ticker, expiry, "mid"))


@pytest.mark.parametrize("fit_mode", ["bidask", "haircut"])
def test_band_mode_lv_targets_equal_parametric_targets(client, ticker, fit_mode):
    by_expiry = _affine_quotes(client, ticker, fit_mode)
    for expiry, lv in by_expiry.items():
        par = _smile_quotes(client, ticker, expiry, fit_mode)
        assert len(lv) == len(par)
        assert _strip(lv) == _strip(par)  # pure addition: nothing else moved
        for q_lv, q_par in zip(lv, par):
            assert q_lv["index"] == q_par["index"]
            assert q_lv["targetLo"] is not None and q_lv["targetHi"] is not None
            # Exact equality: the same edited_band_full call on the same slice.
            assert q_lv["targetLo"] == q_par["targetLo"]
            assert q_lv["targetHi"] == q_par["targetHi"]
            assert q_lv["targetLo"] <= q_lv["mid"] <= q_lv["targetHi"]
            if fit_mode == "bidask":  # the raw band IS the target
                assert q_lv["targetLo"] == q_lv["bid"] and q_lv["targetHi"] == q_lv["ask"]


def test_excluded_quote_keeps_its_target_on_lv_payload(client, ticker):
    """Excluding a wing quote dims it on both charts but its would-be band
    stays on the wire (edited_band_full keeps every prepared row). Last: it
    edits a session."""
    expiry = sorted(_affine_quotes(client, ticker, "haircut"))[-1]
    quotes = _smile_quotes(client, ticker, expiry, "haircut")
    wing = max(quotes, key=lambda q: abs(q["k"]))
    edited = client.post(
        f"/smiles/{ticker}/{expiry}/edits",
        json={"action": "exclude", "index": wing["index"]},
        params={"fit_mode": "haircut"},
    )
    assert edited.status_code == 200, edited.text

    lv = _affine_quotes(client, ticker, "haircut")[expiry]
    par = _smile_quotes(client, ticker, expiry, "haircut")
    ex = lv[wing["index"]]
    assert ex["index"] == wing["index"] and ex["excluded"] is True
    assert ex["targetLo"] is not None and ex["targetHi"] is not None
    assert ex["targetLo"] == par[wing["index"]]["targetLo"]
    assert ex["targetHi"] == par[wing["index"]]["targetHi"]
    assert _strip(lv) == _strip(par)
