"""Bucket rotation of the Bloomberg live book — the over-cap contracts READ
without a metered reference hit (2026-09-24).

Why
---
The Desktop API caps concurrent ``//blp/mktdata`` subscriptions per Terminal
(``max_subscriptions``, 3,000 by default) and a universe of a few dense SPY
rungs beside a second name plans more than that. Until today the over-cap
contracts were carried UNQUOTED: the fit saw the live set only, and the only
way to price the rest was a metered ``bdp`` pull. The churn check of
2026-09-24 (Docs/bloomberg_setup.md, "Subscription churn — verified live")
established that the service tolerates a subscribe → INITPAINT → unsubscribe
cycle: thirty buckets of 40 SPY securities cycled three times in a row, every
bucket painted 40/40 in 0.8–3.0 s, 0 ``SubscriptionFailure``, 0 hits. So a
slice of the budget (``rotation_slots``, R) is reserved and the over-cap
contracts are CYCLED through it: each bucket's INITPAINT — Bloomberg's
last-known bid / ask / last for the security — is copied into a PAINT MEMORY
with the stamp it was taken at and the underlying's spot at that instant, and
the provider's chain serves those paints beside the live ticks. A paint is an
older quote at an older spot: the quote synchronisation (volfit.api.quote_sync)
transports it to the chain's spot and widens its band by its age, so the fit
reads a universe larger than the cap as ONE synchronous set.

The pieces
----------
* ``rotation_slots_setting`` — R from the constructor or the env knob
  ``VOLFIT_BBG_ROTATION_SLOTS`` (default 300), clamped to a quarter of the cap
  so the live set keeps at least three quarters of the budget; 0 = off.
* ``rotation_order`` — the pool in the order the buckets take it: nearest the
  money FIRST across tickers (rank position within each ticker's plan, then
  the ticker's name), so the first bucket of a cycle carries every ticker's
  nearest over-cap contracts.
* ``PaintMemory`` — the thread-safe ``{security: Paint}`` store the chain
  reads; pruned to the pool whenever the plan changes.
* ``RotationWorker`` — the daemon thread: buckets of ≤ R — ``subscribe`` →
  poll the book every ``poll`` s until every security of the bucket painted
  or failed, or ``bucket_wait`` s elapsed → copy the paints → ``unsubscribe``
  → next; after the last bucket the pool starts over. A failed security is
  skipped and retried on the next cycle. The worker OWNS its bucket's
  subscriptions: the provider's re-plan diffs the live set under ``hold()``
  (the worker's lock) so a bucket is never unsubscribed by a re-plan, and a
  security the re-plan promotes into the live set while it sits in a bucket
  is handed over (``release``) instead of being dropped when the bucket ends.
  A new pool (a plan change) takes effect at the next bucket boundary; an
  unchanged pool leaves the running cycle alone.

Paint stamps: a paint carries the tick's own provider stamp when the INITPAINT
had one (the honest age of an illiquid quote, exactly as a live tick is dated)
and the arrival wall time (UTC-naive) as the fallback the chain caps at its
newest provider stamp — the same rule an un-stamped live INITPAINT follows.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from volfit.data.bloomberg_book import BbgBook

__all__ = [
    "BUCKET_WAIT_S", "DEFAULT_ROTATION_SLOTS", "PAINT_RATE_FLOOR", "POLL_S", "ROTATION_SLOTS_ENV",
    "Paint", "PaintMemory", "RotationWorker", "paint_stamp", "rotation_order", "rotation_slots_setting",
]

#: Slots reserved for the rotation when the plan is over the cap (env below).
DEFAULT_ROTATION_SLOTS = 300
ROTATION_SLOTS_ENV = "VOLFIT_BBG_ROTATION_SLOTS"
#: A bucket is released once every security painted / failed, or after
#: ``max(BUCKET_WAIT_S, len(bucket) / PAINT_RATE_FLOOR)`` seconds: the Terminal
#: INITPAINTs at ~15 securities per second (the churn check: 40/40 in 0.8–3.0 s;
#: the live check of 2026-09-24 on SPY: 100-security buckets at 15–18/s, which a
#: flat 6 s cap truncated), so the cap grows with the bucket at a conservative
#: 10/s — a dead security costs a bucket at most the slack above that rate.
BUCKET_WAIT_S = 6.0
PAINT_RATE_FLOOR = 10.0
#: How often the worker polls the book for a bucket's paints.
POLL_S = 0.25


def rotation_slots_setting(value: int | None, cap: int) -> int:
    """R: ``value`` when given, else ``VOLFIT_BBG_ROTATION_SLOTS``, else 300 —
    clamped to ``[0, cap // 4]`` (a malformed env value keeps the default)."""
    if value is None:
        raw = os.environ.get(ROTATION_SLOTS_ENV, "").strip()
        try:
            value = int(float(raw)) if raw else DEFAULT_ROTATION_SLOTS
        except ValueError:
            value = DEFAULT_ROTATION_SLOTS
    return max(0, min(int(value), max(0, int(cap)) // 4))


def rotation_order(dropped: Sequence[str], ticker_of: Callable[[str], str]) -> list[str]:
    """The pool in bucket order: ``dropped`` arrives grouped per ticker in
    that ticker's rank order (the allocation's remainder); interleave the
    groups by rank position (ties by ticker name) so every ticker's nearest
    over-cap contracts are painted first."""
    groups: dict[str, list[str]] = {}
    for sec in dropped:
        groups.setdefault(ticker_of(sec), []).append(sec)
    out: list[str] = []
    rank = 0
    while True:
        row = [g[rank] for _, g in sorted(groups.items()) if rank < len(g)]
        if not row:
            return out
        out.extend(row)
        rank += 1


@dataclass(frozen=True)
class Paint:
    """One rotated security's last-known quote: the INITPAINT's sides, the
    provider stamp it carried (``ts``, None on a bare paint), the wall time it
    was taken at (``stamp``) and the underlying's spot at that instant."""

    bid: float | None
    ask: float | None
    last: float | None
    volume: int | None
    ts: datetime | None
    stamp: datetime
    spot: float | None


def paint_stamp(paint: Paint, newest: datetime | None, wall: datetime) -> datetime:
    """The ``timestamp`` a chain gives a rotated paint: its own provider stamp
    when the INITPAINT carried one (dated like a live tick); else its AGE —
    the chain's newest provider stamp minus the wall time since the paint was
    taken (honest on a 15-min delayed feed too, where capping the wall-clock
    arrival at the provider stamp would read every paint as fresh); the
    arrival time itself when the chain has no provider stamp at all."""
    if paint.ts is not None:
        return paint.ts
    if newest is None:
        return paint.stamp
    return newest - max(wall - paint.stamp, timedelta(0))


class PaintMemory:
    """Thread-safe ``{security: Paint}`` — what the chain serves for the
    over-cap contracts between two visits of the rotation."""

    def __init__(self) -> None:
        self._paints: dict[str, Paint] = {}
        self._lock = threading.Lock()

    def put(self, sec: str, paint: Paint) -> None:
        with self._lock:
            self._paints[sec] = paint

    def get(self, sec: str) -> Paint | None:
        with self._lock:
            return self._paints.get(sec)

    def retain(self, keep: Iterable[str]) -> None:
        """Forget every security outside ``keep`` (the pool changed)."""
        wanted = set(keep)
        with self._lock:
            for sec in [s for s in self._paints if s not in wanted]:
                del self._paints[sec]

    def size(self) -> int:
        with self._lock:
            return len(self._paints)


class RotationWorker:
    """The daemon thread cycling ``pool`` through buckets of ``slots`` on the
    provider's live subscription (module docstring)."""

    def __init__(
        self,
        sub,
        book: BbgBook,
        spot_of: Callable[[str], float | None],
        slots: int,
        bucket_wait: float = BUCKET_WAIT_S,
        poll: float = POLL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sub, self._book = sub, book
        self._spot_of = spot_of
        self._slots = max(1, int(slots))
        self._bucket_wait, self._poll, self._clock = float(bucket_wait), float(poll), clock
        self.memory = PaintMemory()
        self._lock = threading.RLock()  # ownership + pool, shared with the re-plan
        self._pool: list[str] = []
        self._version = 0
        self._owned: set[str] = set()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # stats (read under the lock): the last completed cycle's, plus the
        # running count of the cycle in flight (a 3,000-contract pool takes
        # minutes per cycle — the light must not stay blank that long)
        self._cycles = 0
        self._cycle_seconds: float | None = None
        self._bucket_seconds: float | None = None
        self._painted = 0
        self._failed = 0
        self._painted_now = 0
        self._buckets_now = 0

    # ---------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="bbg-rotation", daemon=True)
        self._thread.start()

    def stop(self, join: float = 1.0) -> None:
        """Stop after the current poll; the bucket in flight is released."""
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(join)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --------------------------------------------------- pool + ownership
    def set_pool(self, pool: Sequence[str]) -> bool:
        """Adopt a new pool (the plan changed): the running cycle is abandoned
        at its next bucket boundary and restarts on it; the memory forgets
        what left the pool. False (nothing touched) when the pool is unchanged."""
        new = list(dict.fromkeys(pool))
        with self._lock:
            if new == self._pool:
                return False
            self._pool = new
            self._version += 1
        self.memory.retain(new)
        return True

    def pool(self) -> list[str]:
        with self._lock:
            return list(self._pool)

    def hold(self):
        """The lock a re-plan diffs under: no bucket is subscribed or released
        while it is held, so ``owned()`` is exact for the whole diff."""
        return self._lock

    def owned(self) -> set[str]:
        """The securities of the bucket in flight (the worker's own subscriptions)."""
        with self._lock:
            return set(self._owned)

    def release(self, securities: Iterable[str]) -> list[str]:
        """Hand bucket securities over to the live set: the worker will not
        unsubscribe them when the bucket ends. Returns the ones it owned."""
        with self._lock:
            handed = [s for s in securities if s in self._owned]
            self._owned.difference_update(handed)
        return handed

    def stats(self) -> dict:
        """The ``rotation`` block of ``stream_stats()``."""
        with self._lock:
            return {
                "pool": len(self._pool),
                "slots": self._slots,
                "bucketWait": self._bucket_wait,
                "bucketSeconds": self._bucket_seconds,
                "cycleSeconds": self._cycle_seconds,
                "painted": self._painted,
                "failed": self._failed,
                "cycles": self._cycles,
                "paintedNow": self._painted_now,
                "bucketsNow": self._buckets_now,
                "owned": len(self._owned),
                "memory": self.memory.size(),
            }

    # --------------------------------------------------------------- loop
    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                with self._lock:
                    pool, version = list(self._pool), self._version
                if not pool:
                    self._stop.wait(self._poll)
                    continue
                t0 = self._clock()
                painted = failed = 0
                restarted = False
                with self._lock:
                    self._painted_now = self._buckets_now = 0
                for start in range(0, len(pool), self._slots):
                    if self._stop.is_set():
                        return
                    with self._lock:
                        restarted = self._version != version
                    if restarted:
                        break  # a new pool: start over on it
                    p, f = self._bucket(pool[start : start + self._slots])
                    painted += p
                    failed += f
                    with self._lock:
                        self._painted_now, self._buckets_now = painted, self._buckets_now + 1
                if restarted or self._stop.is_set():
                    continue
                with self._lock:
                    self._cycles += 1
                    self._cycle_seconds = self._clock() - t0
                    self._painted, self._failed = painted, failed
        finally:
            self._release_bucket([])

    def _bucket(self, bucket: list[str]) -> tuple[int, int]:
        """One bucket: subscribe, wait for the paints, copy, unsubscribe.
        Returns ``(painted, failed)``."""
        t0 = self._clock()
        with self._lock:
            # Own only what the subscription reports as NEW: a security the
            # live set already carries (a stale cycle after a re-plan) is not
            # the worker's to release.
            mine = list(self._sub.subscribe(bucket))
            self._owned = set(mine)
        deadline = t0 + max(self._bucket_wait, len(mine) / PAINT_RATE_FLOOR)
        done: set[str] = set()
        failed: set[str] = set()
        while not self._stop.is_set():
            for sec in mine:
                if sec in done:
                    continue
                tick = self._book.quote(sec)
                if tick is None or (tick.bid is None and tick.ask is None and tick.last is None):
                    continue
                self.memory.put(sec, Paint(
                    bid=tick.bid, ask=tick.ask, last=tick.last, volume=tick.volume, ts=tick.ts,
                    stamp=datetime.now(timezone.utc).replace(tzinfo=None),
                    spot=self._spot_of(sec),
                ))
                done.add(sec)
            failures = self._book.failures()
            failed = {s for s in mine if s in failures and s not in done}
            if len(done) + len(failed) >= len(mine) or self._clock() >= deadline:
                break
            self._stop.wait(self._poll)
        self._release_bucket(mine)
        with self._lock:
            self._bucket_seconds = self._clock() - t0
        return len(done), len(failed)

    def _release_bucket(self, bucket: list[str]) -> None:
        """Unsubscribe what the worker still owns of ``bucket`` (a handed-over
        security stays live; the empty list releases whatever is in flight)."""
        with self._lock:
            drop = [s for s in (bucket or list(self._owned)) if s in self._owned]
            self._owned = set()
        if drop:
            self._sub.unsubscribe(drop)
