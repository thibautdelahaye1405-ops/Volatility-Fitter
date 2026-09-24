"""The real ``blpapi`` session behind ``BloombergSubscription`` (split out of
volfit.data.bloomberg_stream on 2026-09-24 to keep that module under the
400-line policy). ``blpapi_session(host, port)`` starts a Desktop API session
and wraps it in the small interface the subscription loop drives — the same
interface the fake session of the tests mimics — including ``resubscribe``,
the SDK's own primitive for changing a live subscription's options (the
conflation ``interval``) without an unsubscribe / subscribe gap.
"""

from __future__ import annotations


def blpapi_session(host: str, port: int):
    """A started real blpapi session wrapped with the loop's interface."""
    import blpapi

    opts = blpapi.SessionOptions()
    opts.setServerHost(host)
    opts.setServerPort(port)
    opts.setAutoRestartOnDisconnection(True)
    session = blpapi.Session(opts)
    if not session.start():
        raise RuntimeError(f"blpapi session failed to start ({host}:{port})")
    return BlpapiSession(session, blpapi)


class BlpapiSession:
    """Thin adapter over ``blpapi.Session`` exposing the loop's interface."""

    def __init__(self, session, blpapi) -> None:
        self._s = session
        self._blpapi = blpapi

    def openService(self, name: str) -> bool:  # noqa: N802 — blpapi naming
        return bool(self._s.openService(name))

    def subscription_list(self, items: list[tuple[str, str, str]]):
        subs = self._blpapi.SubscriptionList()
        for sec, fields, options in items:
            subs.add(sec, fields, options, self._blpapi.CorrelationId(sec))
        return subs

    def subscribe(self, subs) -> None:
        self._s.subscribe(subs)

    def unsubscribe(self, subs) -> None:
        # blpapi matches on CorrelationId VALUE, so a fresh CorrelationId(sec)
        # identifies the original subscription of that security.
        self._s.unsubscribe(subs)

    def resubscribe(self, subs) -> None:
        """Change the options (fields / interval) of LIVE subscriptions in
        place — matched by CorrelationId value like ``unsubscribe``."""
        self._s.resubscribe(subs)

    def nextEvent(self, timeout_ms: int):  # noqa: N802 — blpapi naming
        event = self._s.nextEvent(timeout_ms)
        return None if event.eventType() == self._blpapi.Event.TIMEOUT else event

    def stop(self) -> None:
        self._s.stop()


__all__ = ["BlpapiSession", "blpapi_session"]
