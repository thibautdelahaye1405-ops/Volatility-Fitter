"""Degraded-market classification (R2 item 10, degraded mode v1).

A node with no fit can be two very different things: NOT CALIBRATED YET
(gated workflow — "press Calibrate") or UNFITTABLE DATA (a near-settle 0DTE
chain with no parity pairs, or every OTM quote at the tick floor — Calibrate
would not help). v1 names the second class on the payloads the desk reads:
``SmileData.degraded`` (the viewer cue switches to "Degraded market — showing
transported prior") and the Quality row's issue ("degraded: <reason>", still
ready=False so the publish gate stays closed). Unnamed failures keep the
legacy silent None — no false degraded labels on transient feed misses.
"""

from __future__ import annotations

from datetime import date, datetime

from volfit.api import service
from volfit.api.quality import _no_fit_node
from volfit.api.state import AppState
from volfit.data.types import ChainSnapshot, OptionQuote
from volfit.replay_report import _StoredChains

TS = datetime(2026, 7, 10, 19, 45)  # 15:45 ET, minutes from the same-day settle


def _q(expiry, k, cp, bid, ask):
    return OptionQuote("SPY", expiry, k, cp, bid=bid, ask=ask, last=None,
                       volume=None, open_interest=None, timestamp=TS)


def _state(quotes, tick=None):
    snap = ChainSnapshot("SPY", 100.0, TS, quotes, "american", tick_size=tick)
    state = AppState(TS.date(), provider=_StoredChains({"SPY": snap}))
    state.set_expiries("SPY", sorted(snap.expiries()))
    return state


def test_no_parity_chain_is_labeled_degraded():
    expiry = TS.date()  # 0DTE: one-sided quotes only, no parity pair anywhere
    quotes = [_q(expiry, k, cp, None, 1.0) for k in (95.0, 100.0, 105.0)
              for cp in ("C", "P")]
    payload = service.smile_payload(_state(quotes), "SPY", expiry.isoformat(), "mid")
    assert payload.hasFit is False
    assert payload.degraded == "no_parity_forward"


def test_all_quotes_screened_is_labeled_degraded():
    expiry = TS.date()  # parity resolves off the ITM sides; every OTM quote
    quotes = []         # is a sub-3-tick bid -> the whole slice screens away
    for k in (95.0, 100.0, 105.0):
        itm_cp, otm_cp = ("C", "P") if k <= 100.0 else ("P", "C")
        itm = abs(100.0 - k) + 0.50
        quotes.append(_q(expiry, k, itm_cp, itm - 0.02, itm + 0.02))
        quotes.append(_q(expiry, k, otm_cp, 0.01, 0.02))
    payload = service.smile_payload(_state(quotes, tick=0.01), "SPY",
                                    expiry.isoformat(), "mid")
    assert payload.hasFit is False
    assert payload.degraded == "no_fittable_market"


def test_healthy_gated_node_is_not_degraded():
    expiry = date(2026, 8, 21)
    quotes = []
    for k in (90.0, 95.0, 100.0, 105.0, 110.0):
        call = max(100.0 - k, 0.0) + 4.0
        put = call - (100.0 - k)  # parity-consistent at D=1, F=100
        quotes.append(_q(expiry, k, "C", call - 0.05, call + 0.05))
        quotes.append(_q(expiry, k, "P", put - 0.05, put + 0.05))
    state = _state(quotes)
    state._gated = True  # the trigger-gated workflow: reads never calibrate
    state.snapshot("SPY")  # chain fetched, fit not run
    payload = service.smile_payload(state, "SPY", expiry.isoformat(), "mid")
    assert payload.hasFit is False  # gated: never calibrated...
    assert payload.degraded is None  # ...but the market is fine


def test_quality_no_fit_row_names_the_degraded_reason():
    plain = _no_fit_node("SPY", "2026-07-10")
    tagged = _no_fit_node("SPY", "2026-07-10", "no_fittable_market")
    assert plain.issues == ["no fit"] and plain.ready is False
    assert tagged.issues == ["degraded: no_fittable_market"]
    assert tagged.ready is False  # the publish gate stays closed either way
