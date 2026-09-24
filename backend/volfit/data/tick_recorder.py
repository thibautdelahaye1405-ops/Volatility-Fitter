"""The tick recorder — a separate process that owns the Massive socket(s),
records the live book into a daily tick store and materialises chain FRAMES
into the app's VolStore (TICK RECORDER, 2026-09-24).

WHY a separate process: the key allows ONE quotes socket. Held by the API
process it dies with every restart (the book re-warms, the day's ticks are
gone) and cannot be shared. Here the socket lives in a process of its own;
the API reads the book from the store (volfit.data.massive_recorded, env
``VOLFIT_MASSIVE_BOOK``) and never opens a socket; the day's ticks are on
disk (volfit.data.tick_store) and any instant is replayable.

The recorder does NOT re-implement the plan, the cap, the chunking or the
acknowledgements: it builds the same ``MassiveProvider`` serve.py builds
(``provider_from_env``), plans through ``option_tickers`` and streams through
``start_streaming`` — the provider's own streaming mixin. Its loop
(``Recorder.tick``) then, every ``interval`` seconds, folds the book into the
store (changed ticks only), writes the heartbeat and the stats; and every
``frame_minutes`` builds each ticker's chain through the provider's book read
(``live_chain`` = the book + the per-minute REST memory for the wings) and
saves it into the VolStore as an as-of reconstruction (``source="massive"``,
``series_id=ASOF_CACHE_TAG``, the request ladder recorded) stamped at the
book's newest tick time floored to the frame minute — so the app's
store-first as-of (volfit.api.asof_cache) and the Series lens's import find
the day's frames without a REST harvest. Unquoted rows are not saved (the
recorded request covers them; a 10k-contract ladder of NULLs per minute
would only bloat the store).

The CLI (``python -m volfit.data.tick_recorder record | replay | status |
stop``) lives in volfit.data.tick_recorder_cli — this module is the loop.
Logs on ``volfit.tick_recorder`` (INFO) + the stream's ``volfit.massive_ws``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from volfit.data.massive_listing import exchange_day
from volfit.data.tick_store import TickStore, daily_path
from volfit.data.types import ChainSnapshot

log = logging.getLogger("volfit.tick_recorder")

#: The data-source id the frames are tagged with (the app's Massive source).
SOURCE_ID = "massive"
#: The meta key the launcher sets to ask for a clean stop.
STOP_KEY = "stop"
#: Default tick directory: <backend>/data/ticks (gitignored *.sqlite).
DEFAULT_OUT = Path(__file__).resolve().parents[2] / "data" / "ticks"


# ------------------------------------------------------------------ setup

def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, "").strip() or default))
    except ValueError:
        return default


def provider_from_env(tickers: list[str], cap: int | None = None, connections: int | None = None):
    """The Massive provider exactly as serve.py's Massive block builds it (key,
    cluster override, budget, NBBO history, the on-disk listing cache) — minus
    the flat-file store, which only serves past days. Raises SystemExit
    without a key (dot-source restart.local.ps1)."""
    from volfit.data.massive import MassiveProvider

    key = os.environ.get("VOLFIT_MASSIVE_KEY", "").strip()
    if not key:
        raise SystemExit("VOLFIT_MASSIVE_KEY is not set (dot-source restart.local.ps1 first)")
    return MassiveProvider(
        tickers,
        api_key=key,
        ws_url=(os.environ.get("VOLFIT_MASSIVE_WS_URL", "").strip() or None),
        stream_cap=cap or _env_int("VOLFIT_MASSIVE_WS_CAP", 950),
        stream_connections=connections or _env_int("VOLFIT_MASSIVE_WS_CONNECTIONS", 1),
        hist_nbbo=os.environ.get("VOLFIT_MASSIVE_HIST_NBBO", "1").strip().lower() not in ("0", "false", "no", "off"),
    )


def select_expiries(available: list[date], rule: str) -> list[date]:
    """The expiry rule: ``all``; ``monthly`` (third Fridays); ``weekly`` (every
    Friday, the monthlies included); else a CSV of ISO dates (∩ available)."""
    text = (rule or "all").strip().lower()
    if text == "all":
        return list(available)
    if text == "monthly":
        return [e for e in available if e.weekday() == 4 and 15 <= e.day <= 21]
    if text == "weekly":
        return [e for e in available if e.weekday() == 4]
    wanted = {date.fromisoformat(s.strip()) for s in text.split(",") if s.strip()}
    return [e for e in available if e in wanted]


def resolve_expiries(prov, tickers: list[str], rule: str) -> dict[str, list[date]]:
    out: dict[str, list[date]] = {}
    for ticker in tickers:
        chosen = select_expiries(prov.available_expiries(ticker), rule)
        if not chosen:
            log.warning("%s: the rule %r selects no listed expiry", ticker, rule)
        out[ticker] = chosen
    return out


# ------------------------------------------------------------------ frames

def frame_instant(ts: datetime, frame_minutes: int) -> datetime:
    """The frame's key: ``ts`` floored to the frame minute."""
    step = max(1, int(frame_minutes))
    return ts.replace(minute=ts.minute - ts.minute % step, second=0, microsecond=0)


def frame_chain(prov, ticker: str, expiries: list[date], frame_minutes: int) -> ChainSnapshot | None:
    """The ticker's chain through the provider's book read, restricted to the
    quoted rows and stamped at the frame instant (None: nothing booked)."""
    chain = prov.live_chain(ticker, expiries)
    if chain is None:
        return None
    quoted = [q for q in chain.quotes if q.bid is not None or q.ask is not None]
    if not quoted:
        return None
    return replace(chain, timestamp=frame_instant(chain.timestamp, frame_minutes), quotes=quoted)


def save_frame(store_path, chain: ChainSnapshot, expiries: list[date]) -> int:
    """Persist a frame the way the as-of layer persists a reconstruction."""
    from volfit.data.store import ASOF_CACHE_TAG, VolStore

    with VolStore(store_path) as store:
        return store.save_snapshot(chain, source=SOURCE_ID, series_id=ASOF_CACHE_TAG, request=list(expiries))


# ---------------------------------------------------------------- the loop

class Recorder:
    """The recording loop over a provider (``tick`` is one iteration so tests
    drive it with a fake book and clock; ``run`` loops it until a stop)."""

    def __init__(
        self, prov, expiries: dict[str, list[date]], out_dir, store_path=None,
        frame_minutes: int = 1, interval: float = 1.0, rest_memory: bool = True, clock=time.time,
    ) -> None:
        self.prov = prov
        self.expiries = {t.upper(): list(e) for t, e in expiries.items()}
        self.out_dir = Path(out_dir)
        self.store_path = None if store_path is None else str(store_path)
        self.frame_minutes = max(1, int(frame_minutes))
        self.interval = max(0.0, float(interval))
        self.rest_memory = rest_memory
        self.clock = clock
        self.stop = threading.Event()
        self.store: TickStore | None = None
        self.day: date | None = None
        self.ticks_written = 0
        self.frames_saved = 0
        self._last_frame_at: float | None = None
        self._last_frame_ts: dict[str, datetime] = {}

    # --------------------------------------------------------- lifecycle
    def plan(self) -> list[str]:
        contracts: list[str] = []
        for ticker, exps in self.expiries.items():
            if exps:
                contracts += self.prov.option_tickers(ticker, exps)
        return contracts

    def _open_store(self, day: date | None = None) -> None:
        day = day or exchange_day()
        if self.store is not None and self.day == day:
            return
        if self.store is not None:
            self.store.close()
        self.store, self.day = TickStore(daily_path(self.out_dir, day)), day
        self.store.set_meta("pid", str(os.getpid()))
        self.store.set_meta("startedAt", datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat())
        self.store.delete_meta(STOP_KEY)
        self.store.delete_meta("stoppedAt")
        log.info("tick store: %s", self.store.path)

    def start(self) -> None:
        self._open_store()
        contracts = self.plan()
        self.prov.start_streaming(contracts)
        self._write_plan(contracts)
        log.info("recording %s — %d contracts requested", ", ".join(self.expiries), len(contracts))

    def _write_plan(self, contracts: list[str]) -> None:
        stats = self.prov.stream_stats() or {}
        self.store.set_meta("plan", {
            "tickers": list(self.expiries),
            "expiries": {t: [e.isoformat() for e in exps] for t, exps in self.expiries.items()},
            "requested": len(contracts),
            "subscribed": stats.get("subscribed"),
            "overCap": stats.get("overCap"),
            "refused": stats.get("refused"),
            "cap": stats.get("cap"),
            "connections": stats.get("connections"),
            "frameMinutes": self.frame_minutes,
            "store": self.store_path,
        })

    def _roll_day(self) -> None:
        """The exchange day moved: a new daily file, the listing re-pulled,
        the live set re-planned (expired rungs out, the new one in)."""
        log.info("exchange day rolled to %s", exchange_day())
        self._open_store()
        try:
            self.prov.refresh_contracts()
            for ticker in list(self.expiries):
                self.expiries[ticker] = [e for e in self.expiries[ticker] if e > exchange_day()]
            contracts = self.plan()
            self.prov.update_streaming(contracts)
            self._write_plan(contracts)
        except Exception:  # noqa: BLE001 — keep recording on the old plan
            log.exception("re-plan on the day roll failed")

    # -------------------------------------------------------------- ticks
    def _acked_by_ticker(self) -> dict[str, int]:
        """Per-ticker acknowledged counts off the provider's connections (the
        API's honesty in recorded mode reads these)."""
        acked: set[str] = set()
        for socket in getattr(self.prov, "_sockets", []):
            acked |= set(getattr(socket, "acked", ()) or ())
        plans = getattr(self.prov, "_ticker_plans", {})
        return {t: sum(1 for c in plans.get(t, []) if c in acked) for t in self.expiries}

    def _fold(self, now: float) -> int:
        book = getattr(self.prov, "_live_book", None)
        if book is None or self.store is None:
            return 0
        n = self.store.fold(((c, t.bid, t.ask, t.ts) for c, t in book.items()), seen_at=now)
        self.ticks_written += n
        return n

    def _health(self, now: float) -> None:
        stats = dict(self.prov.stream_stats() or {})
        stats["ackedByTicker"] = self._acked_by_ticker()
        stats["ticksWritten"] = self.ticks_written
        stats["framesSaved"] = self.frames_saved
        self.store.set_meta("stats", stats)
        self.store.heartbeat(now)

    def _frames(self) -> int:
        if self.store_path is None:
            return 0
        saved = 0
        for ticker, exps in self.expiries.items():
            if not exps:
                continue
            if self.rest_memory:
                try:
                    self.prov.refresh_stream_rest(ticker, exps, block=True)  # throttled to 1/min
                except Exception as exc:  # noqa: BLE001 — the wings keep the last memory
                    log.warning("%s: REST memory refresh failed: %s", ticker, exc)
            chain = frame_chain(self.prov, ticker, exps, self.frame_minutes)
            if chain is None:
                log.info("%s: no frame (nothing booked yet)", ticker)
                continue
            if self._last_frame_ts.get(ticker) == chain.timestamp:
                continue  # no new tick since the last frame: the same instant
            try:
                sid = save_frame(self.store_path, chain, exps)
            except Exception:  # noqa: BLE001 — a store failure never stops the recording
                log.exception("%s: frame save failed", ticker)
                continue
            self._last_frame_ts[ticker] = chain.timestamp
            self.frames_saved += 1
            saved += 1
            log.info("%s: frame %s saved (#%d, %d quotes, spot %.2f)", ticker, chain.timestamp.isoformat(), sid, len(chain.quotes), chain.spot)
        return saved

    def tick(self, now: float | None = None) -> dict:
        """One iteration: the day roll, the fold, the health, the frames when due."""
        now = self.clock() if now is None else now
        if self.day is not None and exchange_day() != self.day:
            self._roll_day()
        ticks = self._fold(now)
        self._health(now)
        frames = 0
        if self._last_frame_at is None or now - self._last_frame_at >= self.frame_minutes * 60.0:
            self._last_frame_at = now
            frames = self._frames()
        return {"ticks": ticks, "frames": frames}

    def stop_requested(self) -> bool:
        return self.stop.is_set() or (self.store is not None and self.store.get_meta(STOP_KEY) is not None)

    def run(self) -> None:
        self.start()
        try:
            while not self.stop_requested():
                t0 = self.clock()
                try:
                    self.tick(t0)
                except Exception:  # noqa: BLE001 — one bad iteration never ends the day
                    log.exception("recorder iteration failed")
                wait = self.interval - (self.clock() - t0)
                if wait > 0:
                    self.stop.wait(wait)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """A clean stop: the last fold, then the stream down, then the meta."""
        if self.store is not None:
            try:
                self._fold(self.clock())
            except Exception:  # noqa: BLE001
                log.exception("final fold failed")
        self.prov.stop_streaming()
        if self.store is not None:
            self.store.set_meta("stoppedAt", datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat())
            self.store.close()
            self.store = None
        log.info("recorder stopped — %d ticks written, %d frames saved", self.ticks_written, self.frames_saved)


__all__ = [
    "DEFAULT_OUT", "SOURCE_ID", "STOP_KEY", "Recorder", "frame_chain", "frame_instant",
    "provider_from_env", "resolve_expiries", "save_frame", "select_expiries",
]


if __name__ == "__main__":
    import sys

    from volfit.data.tick_recorder_cli import main

    sys.exit(main())
