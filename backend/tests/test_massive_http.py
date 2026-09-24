"""The resilient GET + call meter (volfit.data.massive_http, 2026-09-24).

Outcome classes, the retry policy (backoff, Retry-After, the injectable
sleep / retry count), the meter's windows, and the provider-level surface:
``feed_status`` memoised with the " · N calls/h" suffix, ``call_stats``, and a
snapshot page still throttled after the retries raising instead of silently
truncating the chain. The HTTP status-code paths run over ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from volfit.data.massive import MassiveProvider
from volfit.data.massive_http import (
    BACKOFF_BASE_S,
    RETRY_AFTER_CAP_S,
    CallMeter,
    MassiveEntitlement,
    MassiveError,
    MassiveHttp,
    MassiveRateLimited,
    MassiveTransient,
    backoff_delay,
    classify_body,
    is_transport_error,
)

RATE = {"status": "ERROR", "error": "You've exceeded the maximum requests per minute. Upgrade…"}
GATE = {"status": "NOT_AUTHORIZED", "message": "upgrade your plan"}
OK = {"status": "OK", "results": [{"x": 1}]}


class _Seq:
    """An injected http_get answering a scripted sequence (a dict body, or an
    exception instance to raise)."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, url, params):
        self.calls += 1
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return a


def _http(*answers, retries=3, **kw):
    sleeps: list[float] = []
    h = MassiveHttp("k", http_get=_Seq(*answers), retries=retries, sleep=sleeps.append, **kw)
    return h, sleeps


# ------------------------------------------------------------- classification

def test_classify_body_and_transport_errors():
    assert classify_body(OK) == "ok" and classify_body(None) == "ok" and classify_body([]) == "ok"
    assert classify_body(GATE) == "entitlement"
    assert classify_body(RATE) == "rate"
    assert classify_body({"status": "ERROR", "error": "limit must be <= 250"}) == "error"
    assert classify_body({"status": "ERROR", "message": "Too Many Requests"}) == "rate"
    assert is_transport_error(httpx.ConnectError("boom"))
    assert is_transport_error(httpx.ReadTimeout("slow"))
    assert is_transport_error(ConnectionResetError()) and is_transport_error(TimeoutError())
    assert not is_transport_error(RuntimeError("network down")) and not is_transport_error(AssertionError())


def test_backoff_doubles_with_jitter_and_caps():
    import random

    rng = random.Random(1)
    d0, d1, d2 = (backoff_delay(i, rng) for i in range(3))
    assert BACKOFF_BASE_S <= d0 <= 2 * BACKOFF_BASE_S
    assert 2 * BACKOFF_BASE_S <= d1 <= 3 * BACKOFF_BASE_S
    assert 4 * BACKOFF_BASE_S <= d2 <= 5 * BACKOFF_BASE_S
    assert backoff_delay(20, rng) == 8.0  # capped


# --------------------------------------------------------------- the retries

def test_transport_errors_are_retried_then_succeed():
    h, sleeps = _http(httpx.ConnectError("a"), httpx.ReadTimeout("b"), OK)
    events: list[str] = []
    assert h.get("u", None, on_retry=events.append) == OK
    assert h.http_get.calls == 3 and events == ["transport", "transport"]
    assert len(sleeps) == 2 and sleeps[0] < sleeps[1]  # exponential
    s = h.meter.snapshot()
    assert s["total"] == 3 and s["retries"] == 2 and s["transportEvents"] == 2 and s["lastErrorKind"] == "transport"


def test_rate_limit_body_is_retried_then_raised_after_the_budget():
    h, sleeps = _http(RATE, OK)
    assert h.get("u") == OK and h.http_get.calls == 2 and len(sleeps) == 1
    h2, sleeps2 = _http(RATE, RATE, RATE, RATE, retries=3)
    with pytest.raises(MassiveRateLimited, match="maximum requests"):
        h2.get("u")
    assert h2.http_get.calls == 4 and len(sleeps2) == 3  # 1 + 3 retries
    s = h2.meter.snapshot()
    assert s["rateEvents"] == 4 and s["retries"] == 3 and "maximum requests" in s["lastError"]


def test_entitlement_is_never_retried_and_the_body_is_returned():
    h, sleeps = _http(GATE)
    assert h.get("u") == GATE and h.http_get.calls == 1 and sleeps == []
    assert h.meter.snapshot()["entitlementEvents"] == 1
    with pytest.raises(MassiveEntitlement, match="upgrade your plan"):
        MassiveProvider._raise_if_unauthorized(GATE)
    assert issubclass(MassiveEntitlement, RuntimeError)  # the old contract: a RuntimeError


def test_non_transport_exceptions_and_plain_errors_propagate_without_a_retry():
    h, sleeps = _http(AssertionError("unexpected url"))
    with pytest.raises(AssertionError):
        h.get("u")
    assert h.http_get.calls == 1 and sleeps == []
    h2, _ = _http(RuntimeError("network down"))
    with pytest.raises(RuntimeError, match="network down"):
        h2.get("u")
    bad = {"status": "ERROR", "error": "limit must be <= 250"}
    h3, sleeps3 = _http(bad)
    assert h3.get("u") == bad and sleeps3 == []  # not a rate limit: returned for the caller


def test_retries_zero_means_one_attempt_per_call_and_the_override():
    h, sleeps = _http(httpx.ConnectError("a"), OK, retries=0)
    with pytest.raises(MassiveTransient):
        h.get("u")
    assert h.http_get.calls == 1 and sleeps == []
    h2, sleeps2 = _http(RATE, OK, retries=3)
    with pytest.raises(MassiveRateLimited):
        h2.get("u", retries=0)  # the per-call override (the status probe never waits)
    assert h2.http_get.calls == 1


# ------------------------------------------------------ real status codes

def _transport(script):
    """An httpx.MockTransport over a list of (status, headers, body) answers."""
    answers = list(script)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status, headers, body = answers.pop(0)
        content = body if isinstance(body, (bytes, str)) else json.dumps(body)
        return httpx.Response(status, headers=headers, content=content)

    return httpx.MockTransport(handler), seen


def test_429_honours_retry_after_and_5xx_retries_over_the_pooled_client():
    transport, seen = _transport([(429, {"Retry-After": "2"}, ""), (503, {}, "bad gateway"), (200, {}, OK)])
    sleeps: list[float] = []
    h = MassiveHttp("k", transport=transport, sleep=sleeps.append)
    assert h.get("https://api.massive.com/v3/x", {"a": 1}) == OK
    assert len(seen) == 3 and seen[0].headers["authorization"] == "Bearer k"
    assert sleeps[0] == 2.0  # the vendor's Retry-After, verbatim
    assert BACKOFF_BASE_S * 2 <= sleeps[1] <= BACKOFF_BASE_S * 3  # the second attempt's backoff
    s = h.meter.snapshot()
    assert s["rateEvents"] == 1 and s["serverEvents"] == 1 and s["total"] == 3
    transport2, _ = _transport([(429, {"Retry-After": "999"}, ""), (200, {}, OK)])
    sleeps2: list[float] = []
    assert MassiveHttp("k", transport=transport2, sleep=sleeps2.append).get("https://api.massive.com/v3/y") == OK
    assert sleeps2 == [RETRY_AFTER_CAP_S]  # never park a fetch on an absurd hint
    h.close()
    h.close()  # idempotent


def test_non_json_page_is_an_error_not_a_retry():
    transport, seen = _transport([(404, {}, "<html>not found</html>")])
    h = MassiveHttp("k", transport=transport, sleep=lambda _s: None)
    with pytest.raises(MassiveError, match="non-JSON") as info:
        h.get("https://api.massive.com/v3/missing")
    assert info.value.kind == "error" and len(seen) == 1


# ------------------------------------------------------------------ the meter

def test_call_meter_windows_with_an_injected_clock():
    now = {"t": 1_000.0}
    m = CallMeter(clock=lambda: now["t"])
    for _ in range(5):
        m.record()
    now["t"] += 100.0
    m.record("rate", "throttled")
    s = m.snapshot()
    assert s["total"] == 6 and s["perMinute"] == 1 and s["perHour"] == 6
    now["t"] += 3600.0
    m.record()
    s = m.snapshot()
    assert s["perHour"] == 2 and s["total"] == 7 and s["lastErrorKind"] == "rate"
    assert s["lastErrorAt"] is not None and m.per_minute() == 1 and m.per_hour() == 2


# ---------------------------------------------------- the provider's surface

def _status_api():
    exp = date.fromordinal(date.today().toordinal() + 30).isoformat()
    contracts = {"results": [{"contract_type": "call", "expiration_date": exp, "strike_price": 500,
                              "exercise_style": "american", "ticker": "O:SPY"}], "status": "OK"}
    snapshot = {"results": [{"details": {"contract_type": "call", "expiration_date": exp, "strike_price": 500},
                             "last_quote": {"bid": 1.0, "ask": 1.2},
                             "underlying_asset": {"price": 500.0}}], "status": "OK"}
    calls = {"n": 0}

    def http_get(url, params):
        calls["n"] += 1
        return contracts if "reference" in url else snapshot

    return http_get, calls


def test_feed_status_is_memoised_and_carries_the_meter():
    http_get, calls = _status_api()
    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get)  # the default TTL (300 s)
    level, detail = p.feed_status()
    assert level == "amber" and detail.startswith("delayed feed") and detail.endswith(" · 2 calls/h")
    assert calls["n"] == 2
    level, detail = p.feed_status()
    assert calls["n"] == 2 and detail.endswith(" · 2 calls/h")  # memoised: no new probe
    p.fetch_chain("SPY", [date.fromordinal(date.today().toordinal() + 30)])
    assert p.feed_status()[1].endswith(" · 3 calls/h")  # the meter is live even when the probe is not
    fresh = MassiveProvider(["SPY"], api_key="k", http_get=http_get, status_ttl_s=0)
    fresh.feed_status()
    fresh.feed_status()
    assert calls["n"] == 3 + 4  # TTL 0: every call probes
    stats = p.call_stats()
    assert stats["total"] == 3 and stats["retries"] == 0 and stats["lastError"] is None


def test_feed_status_red_is_memoised_only_briefly(monkeypatch):
    from volfit.data import massive as massive_mod

    answers = [RuntimeError("down"), RuntimeError("down")]
    http_get, calls = _status_api()

    def flaky(url, params):
        if answers:
            raise answers.pop(0)
        return http_get(url, params)

    p = MassiveProvider(["SPY"], api_key="k", http_get=flaky)
    assert p.feed_status() == ("red", "unreachable · 1 calls/h")
    clock = {"t": 1000.0}
    monkeypatch.setattr(massive_mod._time, "monotonic", lambda: clock["t"])
    p._status_memo = (clock["t"], *p._status_memo[1:])
    clock["t"] += 10.0
    assert p.feed_status()[0] == "red" and len(answers) == 1  # within 30 s: memoised
    clock["t"] += 25.0
    assert p.feed_status()[0] == "red" and len(answers) == 0  # re-probed after 30 s (still down)
    clock["t"] += 31.0
    assert p.feed_status()[0] == "amber"  # and recovers


def test_a_throttled_snapshot_page_raises_instead_of_truncating_the_chain():
    exp = date.fromordinal(date.today().toordinal() + 30)
    page1 = {"results": [{"details": {"contract_type": "call", "expiration_date": exp.isoformat(),
                                       "strike_price": 500, "exercise_style": "american"},
                          "last_quote": {"bid": 1.0, "ask": 1.2}}],
             "status": "OK", "next_url": "https://api.massive.com/v3/snapshot/options/SPY?cursor=P2"}
    answers = [page1, RATE, RATE, RATE, RATE]

    def http_get(url, params):
        return answers.pop(0)

    p = MassiveProvider(["SPY"], api_key="k", http_get=http_get, retry_sleep=lambda _s: None)
    with pytest.raises(MassiveRateLimited, match="maximum requests"):
        p.fetch_chain("SPY", [exp])
    assert answers == [] and p.call_stats()["rateEvents"] == 4
