"""Resilient GETs + a call meter for the Massive REST client (2026-09-24).

Why this module: until now the provider issued every GET exactly once and
counted nothing. One rate-limit ``ERROR`` body ("You've exceeded the maximum
requests per minute") in the middle of a historical frame gated the
per-contract NBBO history for the SESSION — every later past chain silently
became marks — and a transport blip on a snapshot page returned an
incomplete chain with no error at all. The backtest's own client had retried
3x with backoff for months and sustained 40 requests in flight on the same
key with zero 429s; the app deserved the same plumbing.

Outcome classes (``classify_body`` / ``MassiveHttp.get``):

- ``ok``          — a parsed JSON body; returned.
- ``entitlement`` — a ``NOT_AUTHORIZED`` body. NEVER retried: the body is
                    returned as-is so callers surface it exactly as before
                    (``_raise_if_unauthorized`` -> ``MassiveEntitlement``, a
                    ``RuntimeError`` with the actionable message).
- ``rate``        — HTTP 429, or an ``ERROR`` body whose text reads like a
                    rate limit. Retried after a backoff (``Retry-After``
                    honoured when present); reported through ``on_retry`` so a
                    caller with a concurrency window can shrink it; raised as
                    ``MassiveRateLimited`` once the retries are spent.
- ``server``      — HTTP 5xx / a non-JSON 5xx page. Retried; then
                    ``MassiveTransient``.
- ``transport``   — a connection / read / timeout error (httpx's
                    ``TransportError`` family, ``ConnectionError``,
                    ``TimeoutError``) from the pooled client OR from an injected
                    ``http_get``. Retried; then ``MassiveTransient`` chained to
                    the last exception. Any other exception from an injected
                    ``http_get`` (a test's ``AssertionError``, a ``KeyError``)
                    propagates untouched and un-retried.

Backoff: ``BACKOFF_BASE_S * 2**attempt`` plus a uniform jitter of one base
unit, capped at ``BACKOFF_CAP_S``; at most ``DEFAULT_RETRIES`` retries, so a
call that fails for good costs ~0.5 + 1 + 2 s of waiting. A ``Retry-After``
header (seconds) replaces the computed delay, capped at ``RETRY_AFTER_CAP_S``.
The retry count and the sleep are injectable so tests stay instant and can
assert single calls.

The ``CallMeter`` counts every ATTEMPT (each is a real request against the
key's quota) in rolling one-minute and one-hour windows plus a lifetime
total, the retries, the events per class and the last error text.
``MassiveProvider.call_stats()`` returns its ``snapshot()``; ``feed_status``
appends " · N calls/h".
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

#: Retries after the first attempt (4 attempts in all).
DEFAULT_RETRIES = 3
#: Exponential backoff: base × 2^attempt (+ one base unit of jitter), capped.
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 8.0
#: A vendor ``Retry-After`` beyond this is treated as the cap (never park a fetch).
RETRY_AFTER_CAP_S = 30.0
#: Fragments that mark an ``ERROR`` body as a rate limit (Massive's wording:
#: "You've exceeded the maximum requests per minute…").
RATE_LIMIT_MARKERS = ("maximum requests", "rate limit", "too many requests")
#: Pooled-client timeout (connect + read), seconds.
DEFAULT_TIMEOUT_S = 15.0
#: Keep-alive connections the pool retains: at least the history crawl's
#: worker pool (40) plus the snapshot streams. httpx keeps 20 by default, so
#: 40 workers in flight re-handshook TLS on every other call (live 2026-09-24:
#: a 1,500-contract frame took 13.0 s at 40 in flight, the same as at 12).
POOL_CONNECTIONS = 48


class MassiveError(RuntimeError):
    """A classified Massive REST failure. ``kind`` is one of ``entitlement`` /
    ``rate`` / ``server`` / ``transport`` / ``error`` (an ERROR body that is
    not a rate limit); ``retry_after`` the vendor's hint in seconds, if any."""

    kind: str = "error"

    def __init__(self, message: str, kind: str | None = None, retry_after: float | None = None):
        super().__init__(message)
        if kind is not None:
            self.kind = kind
        self.retry_after = retry_after


class MassiveEntitlement(MassiveError):
    """``NOT_AUTHORIZED``: the plan lacks the data. Never retried; gates a session."""

    kind = "entitlement"


class MassiveRateLimited(MassiveError):
    """HTTP 429 / a rate-limit ERROR body, still failing after the retries."""

    kind = "rate"


class MassiveTransient(MassiveError):
    """A 5xx or a transport error still failing after the retries."""

    kind = "transport"


def classify_body(body) -> str:
    """``ok`` / ``entitlement`` / ``rate`` / ``error`` for a parsed JSON body."""
    if not isinstance(body, dict):
        return "ok"
    status = str(body.get("status") or "").upper()
    if status == "NOT_AUTHORIZED":
        return "entitlement"
    if status == "ERROR":
        text = str(body.get("error") or body.get("message") or "").lower()
        return "rate" if any(m in text for m in RATE_LIMIT_MARKERS) else "error"
    return "ok"


def error_text(body: dict) -> str:
    """The vendor's message in an ERROR / NOT_AUTHORIZED body."""
    return str(body.get("error") or body.get("message") or "request failed")


def is_transport_error(exc: BaseException) -> bool:
    """Whether ``exc`` is a connection / read / timeout failure worth a retry."""
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    try:
        import httpx
    except ImportError:  # pragma: no cover — httpx is a hard dependency of the app
        return False
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


def backoff_delay(attempt: int, rng: random.Random | None = None) -> float:
    """``base × 2^attempt`` plus up to one base unit of jitter, capped."""
    r = rng if rng is not None else random
    raw = BACKOFF_BASE_S * (2**attempt) + r.uniform(0.0, BACKOFF_BASE_S)
    return min(raw, BACKOFF_CAP_S)


def _short(exc: BaseException) -> str:
    text = str(exc).strip()
    return text.splitlines()[-1][:160] if text else exc.__class__.__name__


def _retry_after(headers) -> float | None:
    """Seconds from a ``Retry-After`` header (numeric form only), capped."""
    value = headers.get("retry-after") if headers is not None else None
    if value is None:
        return None
    try:
        seconds = float(str(value).strip())
    except ValueError:
        return None
    return min(max(seconds, 0.0), RETRY_AFTER_CAP_S)


class CallMeter:
    """Thread-safe request counter: rolling per-minute / per-hour windows, a
    lifetime total, retries, events per class and the last error."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._stamps: deque[float] = deque()  # the last hour of attempt times
        self.total = 0
        self.retries = 0
        self.events: dict[str, int] = {"entitlement": 0, "rate": 0, "server": 0, "transport": 0, "error": 0}
        self.last_error: str | None = None
        self.last_error_kind: str | None = None
        self.last_error_at: float | None = None

    def record(self, kind: str = "ok", error: str | None = None) -> None:
        """One attempt of outcome ``kind`` (``ok`` or an error class)."""
        now = self._clock()
        with self._lock:
            self._stamps.append(now)
            self._prune(now)
            self.total += 1
            if kind != "ok":
                self.events[kind] = self.events.get(kind, 0) + 1
                self.last_error, self.last_error_kind, self.last_error_at = error, kind, now

    def record_retry(self) -> None:
        with self._lock:
            self.retries += 1

    def _prune(self, now: float) -> None:
        while self._stamps and now - self._stamps[0] > 3600.0:
            self._stamps.popleft()

    def per_hour(self) -> int:
        with self._lock:
            self._prune(self._clock())
            return len(self._stamps)

    def per_minute(self) -> int:
        with self._lock:
            now = self._clock()
            self._prune(now)
            return sum(1 for t in self._stamps if now - t <= 60.0)

    def snapshot(self) -> dict:
        """The meter as a JSON-friendly dict (camelCase: it travels to the UI)."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            at = (
                datetime.fromtimestamp(self.last_error_at, tz=timezone.utc).replace(tzinfo=None).isoformat()
                if self.last_error_at is not None
                else None
            )
            return {
                "total": self.total,
                "perMinute": sum(1 for t in self._stamps if now - t <= 60.0),
                "perHour": len(self._stamps),
                "retries": self.retries,
                "rateEvents": self.events.get("rate", 0),
                "serverEvents": self.events.get("server", 0),
                "transportEvents": self.events.get("transport", 0),
                "entitlementEvents": self.events.get("entitlement", 0),
                "lastError": self.last_error,
                "lastErrorKind": self.last_error_kind,
                "lastErrorAt": at,
            }


class MassiveHttp:
    """The pooled client + the retry policy + the meter, behind one ``get``.

    ``http_get`` (``(url, params) -> dict``) bypasses httpx entirely (offline
    tests); ``transport`` is an httpx transport for the pooled client (tests
    use ``httpx.MockTransport`` to exercise status codes and headers).
    ``sleep`` is the backoff sleep (tests inject a no-op); ``retries`` the
    default retry count (``get(..., retries=0)`` overrides per call — the
    status probe never waits)."""

    def __init__(
        self,
        api_key: str,
        *,
        http_get: Callable[[str, dict | None], dict] | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        sleep: Callable[[float], None] | None = None,
        meter: CallMeter | None = None,
        transport=None,
        rng: random.Random | None = None,
    ) -> None:
        self.api_key = api_key
        self.http_get = http_get
        self.timeout = timeout
        self.retries = max(int(retries), 0)
        self.sleep = sleep if sleep is not None else time.sleep
        self.meter = meter if meter is not None else CallMeter()
        self._transport = transport
        self._rng = rng
        self._client = None
        self._client_lock = threading.Lock()

    # -- the pooled client ---------------------------------------------------

    def client(self):
        """The pooled ``httpx.Client`` (built once, under a lock: the snapshot
        fan-out warms it before the threads start, but be safe anyway)."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    import httpx

                    kwargs = {
                        "headers": {"Authorization": f"Bearer {self.api_key}"},
                        "timeout": self.timeout,
                        "limits": httpx.Limits(
                            max_connections=POOL_CONNECTIONS, max_keepalive_connections=POOL_CONNECTIONS
                        ),
                    }
                    if self._transport is not None:
                        kwargs["transport"] = self._transport
                    self._client = httpx.Client(**kwargs)
        return self._client

    def close(self) -> None:
        """Release the pooled connections (idempotent; safe if never built)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    # -- one attempt ---------------------------------------------------------

    def _attempt(self, url: str, params: dict | None) -> dict:
        """One request. Returns the parsed body (an entitlement / plain ERROR
        body included); raises ``MassiveError`` for 429 / 5xx / a rate-limit
        body, and lets transport exceptions through for ``get`` to classify."""
        if self.http_get is not None:
            body = self.http_get(url, params)
        else:
            resp = self.client().get(url, params=params)
            if resp.status_code == 429:
                raise MassiveRateLimited(f"HTTP 429: {resp.text[:120]}", retry_after=_retry_after(resp.headers))
            if resp.status_code >= 500:
                raise MassiveTransient(f"HTTP {resp.status_code}", kind="server", retry_after=_retry_after(resp.headers))
            try:
                body = resp.json()
            except ValueError as exc:
                raise MassiveError(f"HTTP {resp.status_code}: non-JSON response", kind="error") from exc
        if classify_body(body) == "rate":
            raise MassiveRateLimited(f"Massive: {error_text(body)}")
        return body

    # -- the resilient GET ---------------------------------------------------

    def get(
        self,
        url: str,
        params: dict | None = None,
        *,
        retries: int | None = None,
        on_retry: Callable[[str], None] | None = None,
    ) -> dict:
        """GET with retries on ``rate`` / ``server`` / ``transport`` outcomes.
        ``on_retry(kind)`` fires before each backoff sleep. Returns the parsed
        body; raises ``MassiveRateLimited`` / ``MassiveTransient`` once the
        retries are spent, ``MassiveError(kind="error")`` for a non-JSON page."""
        budget = self.retries if retries is None else max(int(retries), 0)
        attempt = 0
        while True:
            failure: MassiveError | None = None
            cause: BaseException | None = None
            try:
                body = self._attempt(url, params)
            except MassiveError as exc:
                failure = exc
            except Exception as exc:  # noqa: BLE001 — classified below
                if not is_transport_error(exc):
                    self.meter.record("error", _short(exc))
                    raise
                failure, cause = MassiveTransient(_short(exc), kind="transport"), exc
            else:
                kind = classify_body(body)
                self.meter.record(kind, error_text(body) if kind != "ok" else None)
                return body
            self.meter.record(failure.kind, str(failure))
            retryable = failure.kind in ("rate", "server", "transport")
            if not retryable or attempt >= budget:
                if cause is not None:
                    raise failure from cause
                raise failure
            delay = failure.retry_after if failure.retry_after is not None else backoff_delay(attempt, self._rng)
            self.meter.record_retry()
            if on_retry is not None:
                on_retry(failure.kind)
            self.sleep(delay)
            attempt += 1
