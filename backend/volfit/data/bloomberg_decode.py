"""Decode ``//blp/mktdata`` subscription events into plain book records.

Companion of volfit.data.bloomberg_stream (kept separate for the 400-line
policy). Everything here is pure and duck-typed over the small blpapi message
surface (``hasElement`` / ``getElement`` / ``isNull`` / ``getValueAsString`` /
``correlationIds`` / ``messageType``), so offline tests exercise it with fake
messages and never import blpapi.

A *record* is what ``BbgBook.apply`` consumes:

* ``{"kind": "data", "sec": str, "fields": {FIELD: str|None}, "ts": datetime|None}``
  — one ``MarketDataEvents`` message. Only fields PRESENT on the message are
  reported (Bloomberg sends deltas after an initial INITPAINT summary); a
  present-but-NULL element (a withdrawn side) is reported as ``None``.
* ``{"kind": "started"|"failure"|"terminated", "sec": str, "reason": str}``
  — subscription status (``SubscriptionStarted`` / ``SubscriptionFailure`` /
  ``SubscriptionTerminated``).
* ``{"kind": "session_down"}`` — ``SessionTerminated`` / ``SessionConnectionDown``.

Wire facts (confirmed live 2026-08-20): per-side stamps ``BID_UPDATE_STAMP_RT``
/ ``ASK_UPDATE_STAMP_RT`` / ``TRADE_UPDATE_STAMP_RT`` are ISO-8601 with offset;
``IS_DELAYED_STREAM`` is a bool string; a bad security fails with
``reason.category = "BAD_SEC"`` and a ``description``.
"""

from __future__ import annotations

from datetime import datetime, timezone

#: Fields subscribed per security. OPEN_INT is reference-only on options (the
#: subscription starts with an ``exceptions[]`` entry) — never requested.
STREAM_FIELDS = ("BID", "ASK", "LAST_PRICE", "VOLUME")

#: Per-side update stamps Bloomberg attaches to quote/trade events.
STAMP_FIELDS = ("BID_UPDATE_STAMP_RT", "ASK_UPDATE_STAMP_RT", "TRADE_UPDATE_STAMP_RT")


# ---------------------------------------------------------------- coercions
def price_or_none(value) -> float | None:
    """A positive float, or None (0 / blank / NULL side = no quote)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f > 0.0 else None


def int_or_none(value) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def flag(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "y")


def parse_stamp(text) -> datetime | None:
    """``'2026-08-20T19:18:58.027+01:00'`` -> UTC-naive datetime (the wire
    convention of volfit.data.types); None on anything unparsable."""
    if text is None:
        return None
    try:
        dt = datetime.fromisoformat(str(text).strip())
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ------------------------------------------------------------ blpapi decode
def decode_event(event) -> list[dict]:
    """Turn one blpapi ``Event`` into book records.

    A pre-decoded record list (what the offline fake session yields) passes
    through untouched, so the consume loop is the same in tests and live.
    """
    if isinstance(event, list):
        return event
    try:
        import blpapi
    except ImportError:  # pragma: no cover - the live path only
        return []
    kind = event.eventType()
    out: list[dict] = []
    for msg in event:
        if kind == blpapi.Event.SUBSCRIPTION_DATA:
            rec = decode_data_message(msg)
            if rec is not None:
                out.append(rec)
        elif kind == blpapi.Event.SUBSCRIPTION_STATUS:
            out.append(decode_status_message(msg))
        elif kind == blpapi.Event.SESSION_STATUS:
            if str(msg.messageType()) in ("SessionTerminated", "SessionConnectionDown"):
                out.append({"kind": "session_down"})
    return [r for r in out if r]


def correlation_sec(msg) -> str:
    """The security a message is about (its first CorrelationId value)."""
    cids = list(msg.correlationIds())
    return str(cids[0].value()) if cids else ""


def decode_data_message(msg, fields: tuple[str, ...] = STREAM_FIELDS) -> dict | None:
    """One ``MarketDataEvents`` message -> a ``"data"`` record (see module doc).

    The record stamp is the newest per-side ``*_UPDATE_STAMP_RT`` on the message,
    or None when it carries none (the book then keeps its previous stamp).
    """
    sec = correlation_sec(msg)
    if not sec:
        return None
    values: dict = {}
    for name in (*fields, "IS_DELAYED_STREAM"):
        if not msg.hasElement(name):
            continue
        el = msg.getElement(name)
        values[name] = None if el.isNull() else el.getValueAsString()
    stamp: datetime | None = None
    for name in STAMP_FIELDS:
        if msg.hasElement(name):
            el = msg.getElement(name)
            ts = None if el.isNull() else parse_stamp(el.getValueAsString())
            if ts is not None and (stamp is None or ts > stamp):
                stamp = ts
    return {"kind": "data", "sec": sec, "fields": values, "ts": stamp}


def decode_status_message(msg) -> dict:
    """SubscriptionStarted / SubscriptionFailure / SubscriptionTerminated -> a
    status record; ``{}`` for anything else (filtered by the caller)."""
    name = str(msg.messageType())
    sec = correlation_sec(msg)
    if name == "SubscriptionStarted":
        return {"kind": "started", "sec": sec}
    if name in ("SubscriptionFailure", "SubscriptionTerminated"):
        return {
            "kind": "failure" if name == "SubscriptionFailure" else "terminated",
            "sec": sec,
            "reason": status_reason(msg),
        }
    return {}


def status_reason(msg) -> str:
    """Short human reason from a subscription-status message's ``reason`` block
    (``description`` preferred, else ``category``), e.g. "Unknown/Invalid
    security" or "NOT_ENTITLED". Best-effort: falls back to the message name."""
    try:
        if msg.hasElement("reason"):
            reason = msg.getElement("reason")
            for key in ("description", "category"):
                if reason.hasElement(key):
                    text = reason.getElementAsString(key).strip()
                    if text:
                        return text[:80]
    except Exception:  # noqa: BLE001 — status decoding must never raise
        pass
    return str(msg.messageType())
