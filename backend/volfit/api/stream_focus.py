"""The stream FOCUS registry — which nodes are on screen right now.

The per-node tick-stream SSE (volfit.api.table_stream.table_events, opened
by the Quote Table / Smile Chart for the VIEWED node) is the app's only
honest signal of what the desk is looking at. The registry counts the open
streams per ``(TICKER, expiry ISO)`` node — reference-counted, so two tabs
on one node are one focus and the focus ends when the LAST of them closes —
and bumps a version on every membership change. ``AppState.sync_streaming``
pushes the node set to each streaming provider every scheduler tick; a
provider re-plans only when the set it holds differs (never a re-plan when
nothing changed), and the allocation policy (volfit.data.stream_allocation)
puts the focus nodes' whole planned rungs on the socket first.

Thread-safe: the SSE generators run on the event loop's worker threads, the
scheduler on its own thread.
"""

from __future__ import annotations

import threading

from volfit.data.stream_allocation import Node


class StreamFocus:
    """Reference-counted set of focus nodes with a change version."""

    def __init__(self) -> None:
        self._counts: dict[Node, int] = {}
        self._lock = threading.Lock()
        self._version = 0

    def open(self, node: Node) -> bool:
        """One more stream on ``node``; True when the node ENTERED the focus."""
        with self._lock:
            count = self._counts.get(node, 0)
            self._counts[node] = count + 1
            if count == 0:
                self._version += 1
                return True
            return False

    def close(self, node: Node) -> bool:
        """One stream fewer on ``node``; True when the node LEFT the focus.
        A close without an open is ignored (never a negative count)."""
        with self._lock:
            count = self._counts.get(node, 0)
            if count <= 1:
                if count == 1:
                    del self._counts[node]
                    self._version += 1
                    return True
                return False
            self._counts[node] = count - 1
            return False

    def nodes(self) -> set[Node]:
        with self._lock:
            return set(self._counts)

    def count(self, node: Node) -> int:
        with self._lock:
            return self._counts.get(node, 0)

    @property
    def version(self) -> int:
        """Bumps on every membership change — the "plan dirty" stamp."""
        with self._lock:
            return self._version


__all__ = ["Node", "StreamFocus"]
