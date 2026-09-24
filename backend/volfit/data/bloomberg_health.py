"""The Bloomberg stream's HEALTH: the Data Source light's reading and the
``stream_stats()`` block the ``/datasources`` payload carries (split out of
volfit.data.bloomberg_live on 2026-09-24 with the bucket rotation, to keep
that module under the 400-line policy).

``BloombergHealthMixin`` gives ``BloombergStreamingMixin``:

* ``_stream_status()`` — ``(level, detail)`` for the light while streaming,
  quota-free, read off the book: red on a session error or a refused
  underlying, amber while connecting / painted-but-unstamped / idle / on a
  delayed feed, green once real-time ticks flow. Mentions the over-cap count
  — "rotating N over cap · cycle 32 s" once the rotation serves them — and
  the refused count.
* ``stream_stats()`` — the same dict shape as the Massive book's
  (volfit.data.massive_stream_reads: ``connected`` / ``subscribed`` /
  ``acknowledged`` = started / ``refused`` = failures / ``overCap`` /
  ``requested`` / ``cap`` / ``rate`` / the per-ticker served flags / the
  allocation / ``level`` + ``detail``) plus the ``rotation`` block
  (volfit.data.bloomberg_rotation ``RotationWorker.stats``: pool, slots,
  bucket and cycle seconds, paints, cycles) — None when not streaming.

Expects the host's ``_book``, ``_sub``, ``_rotation``, ``_stream_tickers``,
``_stream_dropped``, ``_requested``, ``_allocation``, ``_focus``, ``_floor``,
``_max_subscriptions``, ``_stream_host`` / ``_stream_port``, ``_security``,
``_book_spot`` and ``is_streaming``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from volfit.data.bloomberg_stream import DEFAULT_HOST, DEFAULT_PORT
from volfit.data.expiry_time import session_open_now

#: A stream whose newest stamp is older than this is reported idle (pre-market,
#: closed session) — the book retains each contract's last tick across quiet spells.
_IDLE_SECONDS = 20 * 60.0


class BloombergHealthMixin:
    """The light's reading and the health block of the Bloomberg stream."""

    def _over_cap_note(self) -> str | None:
        """"rotating N over cap · cycle 32 s" while the rotation serves the
        over-cap contracts ("· M painted so far" until its first cycle ends),
        "N over cap" when they are carried unquoted."""
        worker = getattr(self, "_rotation", None)
        rot = worker.stats() if worker is not None else None
        if rot is not None and rot["pool"]:
            cycle = rot["cycleSeconds"]
            suffix = f" · cycle {cycle:.0f} s" if cycle is not None else f" · {rot['paintedNow']} painted so far"
            return f"rotating {rot['pool']} over cap{suffix}"
        if self._stream_dropped:
            return f"{len(self._stream_dropped)} over cap"
        return None

    def _stream_status(self) -> tuple[str, str] | None:
        """``(level, detail)`` for the Data Source light while streaming (None
        otherwise) — quota-free, read off the book (module docstring)."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        if self._sub.last_error:
            return ("red", f"stream: {self._sub.last_error}")
        failures = self._book.failures()
        underlyings = [self._security(t) for t in sorted(self._stream_tickers)]
        for sec in underlyings:
            if sec in failures:
                return ("red", f"stream: {failures[sec]}")
        started = self._book.started()
        if started == 0:
            return ("amber", "stream connecting")
        extras = []
        over = self._over_cap_note()
        if over:
            extras.append(over)
        refused = [s for s in failures if s not in underlyings]
        if refused:
            extras.append(f"{len(refused)} refused")
        suffix = "".join(f" · {e}" for e in extras)
        newest = self._book.newest_ts()
        if newest is None:
            if self._book.size() == 0:
                return ("amber", f"stream warming · {started} subscribed{suffix}")
            # Painted (INITPAINT last-known values) but no stamped tick yet — the
            # signature of a session opened outside trading hours: the book is
            # serving, just not moving. Say so rather than "warming" forever.
            return ("amber", f"streaming {started} · no tick stamp yet{suffix}")
        age = (datetime.now(timezone.utc).replace(tzinfo=None) - newest).total_seconds()
        if age > _IDLE_SECONDS:
            return ("amber", f"stream idle since {newest:%H:%M} UTC · {started} subscribed{suffix}")
        slow = [t for t in sorted(self._stream_tickers) if self._book.delayed([self._security(t)])]
        if slow:
            which = "" if len(slow) == len(underlyings) else f" ({', '.join(slow)})"
            return ("amber", f"streaming {started} · delayed feed{which}{suffix}")
        return ("green", f"streaming {started} · real-time{suffix}")

    def stream_stats(self) -> dict | None:
        """The plain health dict the ``/datasources`` payload carries (None
        when not streaming) — the Massive shape where it applies, plus the
        ``rotation`` block (module docstring)."""
        if not self.is_streaming() or self._book is None or self._sub is None:
            return None
        book, sub = self._book, self._sub
        flow = book.flow()
        failures = book.failures()
        underlyings = [self._security(t) for t in sorted(self._stream_tickers)]
        status = self._stream_status() or ("amber", "")
        alloc = self._allocation
        newest = book.newest_ts()
        worker = getattr(self, "_rotation", None)
        return {
            "connected": bool(book.connected),
            "running": sub.is_running(),
            "connections": 1,
            "connectedCount": 1 if book.connected else 0,
            "url": f"{self._stream_host or DEFAULT_HOST}:{self._stream_port or DEFAULT_PORT}",
            "cluster": "delayed" if book.delayed(underlyings) else "realtime",
            "messages": flow["messages"],
            "quotes": flow["messages"],
            "rate": flow["rate"],
            "lastMessageAge": flow["lastMessageAge"],
            "lastQuoteAge": flow["lastMessageAge"],
            "lastMessageUtc": newest.isoformat() if newest is not None else None,
            "reconnects": 0,
            "lastError": sub.last_error,
            "lastErrorAge": None,
            "authFailed": False,
            "subscribed": len(sub.securities),
            "acknowledged": book.started(),
            "refused": len(failures),
            "overCap": len(self._stream_dropped),
            "requested": len(self._requested),
            "cap": self._max_subscriptions,
            "sessionOpen": session_open_now(),
            # served = the underlying painted (the chain can be built off the book)
            "tickers": {t: self._book_spot(t, wait=0.0) is not None for t in sorted(self._stream_tickers)},
            "allocation": alloc.as_dict()["tickers"] if alloc is not None else {},
            "focus": [f"{t}|{e}" for t, e in sorted(self._focus)],
            "floor": self._floor,
            "restSeconds": None,
            "level": status[0],
            "detail": status[1],
            "rotation": worker.stats() if worker is not None else None,
        }


__all__ = ["BloombergHealthMixin"]
