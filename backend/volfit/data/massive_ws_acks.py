"""Acknowledgement bookkeeping of the Massive options socket (split out of
volfit.data.massive_ws on 2026-09-24 to keep the transport under the
400-line policy).

The server confirms each subscribed contract with a ``success`` status
("subscribed to: Q.O:…"); a quote arriving for a pending contract confirms
it too (the implicit acknowledgement). A subscribe frame that crosses the
~1,000-contract limit is refused IN FULL ("Subscription limit reached for
feed…" — the 2026-09-23 finding, once dropped silently): the refusal is
paired with the pending chunk it answers (FIFO, the server answers frames in
order; when no acknowledgement has parsed yet on the connection, the last
chunk sent), the farther half of that chunk is dropped into ``refused``
(chunks are ranked nearest-the-money first) and the nearer half re-sent,
halving until the acknowledged count sits under the limit. ``auth_failed``
ends the session; any other error is recorded and logged.

``AckMixin`` expects the transport's ``_lock``, ``_contracts``, ``_acked``,
``_pending`` / ``_pending_syms``, ``_refused``, ``_acks_parsed``, ``_stats``,
``_batch``, ``_name`` and ``_send_subscribe``.
"""

from __future__ import annotations

import logging

log = logging.getLogger("volfit.massive_ws")

#: The error text of a refused (over-limit) subscribe frame.
LIMIT_TEXT = "subscription limit"


def subscribed_syms(message: str) -> list[str]:
    """Contract keys named by an acknowledgement ("subscribed to: Q.O:A,Q.O:B")."""
    text = message.strip()
    marker = "subscribed to:"
    if not text.lower().startswith(marker):
        return []
    out = []
    for part in text[len(marker) :].split(","):
        sym = part.strip()
        if sym.startswith("Q."):
            sym = sym[2:]
        if sym:
            out.append(sym)
    return out



class AckMixin:
    """Acknowledgements, refusals and status frames of one connection."""

    # ------------------------------------------------- acknowledgements
    def _forget_pending(self, syms) -> None:
        """Call under the lock: drop ``syms`` from the pending chunks."""
        for chunk in self._pending:
            chunk["left"].difference_update(syms)
        self._pending = [c for c in self._pending if c["left"]]
        self._pending_syms.difference_update(syms)

    def _ack(self, syms, by_status: bool) -> int:
        """Record acknowledged contracts (status text, or a quote arriving)."""
        with self._lock:
            live = set(self._contracts)
            hits = [s for s in syms if s in live and s not in self._acked]
            self._acked.update(hits)
            if by_status:
                self._acks_parsed += len(syms)
            if hits:
                self._forget_pending(hits)
        return len(hits)

    def _take_refused_chunk(self) -> list[str] | None:
        """The pending chunk a limit error answers (call under the lock):
        FIFO when acknowledgements parse on this connection, else the last
        chunk sent (the back-to-back initial subscribe)."""
        if not self._pending:
            return None
        chunk = self._pending.pop(0 if self._acks_parsed else -1)
        self._pending_syms.difference_update(chunk["items"])
        return list(chunk["items"])

    async def _on_limit(self, conn, message: str) -> None:
        """A refused subscribe frame: keep the nearer half of the chunk it
        answers (re-sent), drop the farther half into ``refused``."""
        with self._lock:
            chunk = self._take_refused_chunk()
            if chunk is None:
                keep, drop = [], []
            else:
                keep_n = len(chunk) // 2
                keep, drop = chunk[:keep_n], chunk[keep_n:]
                dropped = set(drop)
                self._contracts = [c for c in self._contracts if c not in dropped]
                self._acked.difference_update(dropped)
                self._refused.extend(c for c in drop if c not in self._refused)
        self._stats.note_error(f"{message.strip()} · {len(drop)} dropped")
        log.warning(
            "%s: subscribe refused (%s): dropped %d, re-sending %d (refused so far %d)",
            self._name, message.strip(), len(drop), len(keep), len(self._refused),
        )
        if keep:
            await self._send_subscribe(conn, keep)

    async def _handle_status(self, conn, ev: dict, url: str) -> str | None:
        """Act on one status event; returns "auth_failed" when the session must end."""
        status = ev.get("status")
        message = str(ev.get("message") or "")
        if status == "auth_success":
            self._stats.note_connected(url)
            log.info("%s: authenticated on %s", self._name, url)
        elif status == "auth_failed":
            self._stats.note_auth_failed(f"auth failed: {message}")
            log.error("%s: authentication failed on %s: %s", self._name, url, message)
            return "auth_failed"
        elif status == "success":
            syms = subscribed_syms(message)
            if syms:
                hits = self._ack(syms, by_status=True)
                if hits and (self._acks_parsed <= self._batch or not self._pending):
                    log.info("%s: acknowledged %d (total %d)", self._name, hits, len(self._acked))
        elif status == "error":
            if LIMIT_TEXT in message.lower():
                await self._on_limit(conn, message)
            else:
                self._stats.note_error(message)
                log.warning("%s: error frame: %s", self._name, message)
        elif status == "connected":
            log.info("%s: connected to %s", self._name, url)
        return None

    def _ack_by_quotes(self, events: list[dict]) -> None:
        """A quote for a pending contract is its acknowledgement."""
        with self._lock:
            if not self._pending_syms:
                return
            pending = self._pending_syms
        hits = [ev.get("sym") for ev in events if ev.get("ev") == "Q" and ev.get("sym") in pending]
        if hits:
            self._ack(hits, by_status=False)
