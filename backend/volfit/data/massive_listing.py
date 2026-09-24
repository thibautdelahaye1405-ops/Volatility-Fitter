"""One contracts listing per (underlying, ET exchange day), on disk (2026-09-24).

Why: the contracts reference (``/v3/reference/options/contracts``, 1,000 rows
a page — SPY is 13 pages, ~1.4 s) was paginated once per process for the
expiry ladder, then AGAIN under a second cache key by the per-expiry contract
lookup (the WS subscription plan, the historical crawl), and again after every
restart. The listing changes once a day — new weeklies appear overnight, an
expiry drops off at its close — so ONE pull per (underlying, exchange day)
serves every derived view: the expiry ladder, the per-expiry contract keys,
the subscription plan, across restarts.

The day is the EXCHANGE day (``volfit.data.expiry_time.ET``): a listing pulled
at 23:30 New York on the 23rd is still the 23rd's, whatever the box's clock
says; a file from any other day is simply not matched (the name carries the
day) and old files are swept when a new one is written.

File: ``cache_dir("massive")/<UNDERLYING>_<YYYY-MM-DD>.json`` with the raw
reference fields the provider reads (``ROW_FIELDS``), written atomically
(tmp + ``os.replace``). A missing, corrupt or unwritable file only means a
miss: the cache never fails a fetch. ``ListingCache.get`` memoises in memory
too, under a per-underlying lock so two threads asking for the same name
share one pull; ``drop`` forgets memory AND the day's file (the provider's
``refresh_contracts``); ``get(..., refresh=True)`` re-pulls explicitly.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from volfit.data.cache_dir import cache_dir
from volfit.data.expiry_time import ET

#: The reference fields kept per row (what ``available_expiries`` /
#: ``_intraday_contracts`` read); everything else the API sends is dropped.
ROW_FIELDS = ("ticker", "expiration_date", "strike_price", "contract_type", "exercise_style")
#: Provider sub-directory under the cache root.
SUBDIR = "massive"
_NAME = re.compile(r"^(?P<underlying>[A-Z0-9._:^-]+)_(?P<day>\d{4}-\d{2}-\d{2})\.json$")


def exchange_day(now: datetime | None = None) -> date:
    """Today's date in New York (an aware ``now`` for tests)."""
    moment = now if now is not None else datetime.now(ET)
    return moment.astimezone(ET).date()


def slim(row: dict) -> dict:
    """One reference row reduced to ``ROW_FIELDS``."""
    return {k: row.get(k) for k in ROW_FIELDS}


def listing_path(underlying: str, day: date) -> Path | None:
    root = cache_dir(SUBDIR)
    return None if root is None else root / f"{underlying.upper()}_{day.isoformat()}.json"


def load_listing(underlying: str, day: date) -> list[dict] | None:
    """The stored rows for (underlying, day), or None on a miss / a bad file."""
    path = listing_path(underlying, day)
    if path is None or not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if payload.get("underlying") != underlying.upper() or payload.get("day") != day.isoformat():
            return None
        rows = payload.get("rows")
        return [slim(r) for r in rows] if isinstance(rows, list) and rows else None
    except (OSError, ValueError, AttributeError):
        return None


def store_listing(underlying: str, day: date, rows: list[dict]) -> bool:
    """Write the rows atomically; sweep the underlying's files from other
    days. False (and nothing written) when the cache directory is unusable."""
    path = listing_path(underlying, day)
    if path is None:
        return False
    payload = {
        "underlying": underlying.upper(),
        "day": day.isoformat(),
        "pulledAt": datetime.now(ET).isoformat(timespec="seconds"),
        "rows": [slim(r) for r in rows],
    }
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    _sweep(path.parent, underlying.upper(), keep=path.name)
    return True


def drop_listing(underlying: str, day: date) -> None:
    path = listing_path(underlying, day)
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _sweep(folder: Path, underlying: str, keep: str) -> None:
    """Remove the underlying's listings from other days (they can never match)."""
    try:
        for entry in folder.iterdir():
            m = _NAME.match(entry.name)
            if m and m.group("underlying") == underlying and entry.name != keep:
                entry.unlink(missing_ok=True)
    except OSError:
        pass


class ListingCache:
    """Memory + (optional) disk memo of contract listings keyed by underlying,
    valid for the current exchange day. ``disk=False`` keeps it in memory
    only (an injected fake HTTP layer must never persist its rows)."""

    def __init__(self, disk: bool = True) -> None:
        self.disk = disk
        self._memo: dict[str, tuple[date, list[dict]]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._master = threading.Lock()
        self.pulls = 0  # diagnostics: how many times the reference was paginated

    def _lock_for(self, underlying: str) -> threading.Lock:
        with self._master:
            lock = self._locks.get(underlying)
            if lock is None:
                lock = self._locks[underlying] = threading.Lock()
            return lock

    def get(
        self, underlying: str, pull: Callable[[], list[dict]], refresh: bool = False
    ) -> list[dict]:
        """The day's rows for ``underlying``: memory, else the day's file, else
        ``pull()`` (stored when non-empty — a transient empty answer is never
        frozen). ``refresh`` skips both memos and re-pulls."""
        key = underlying.upper()
        day = exchange_day()
        with self._lock_for(key):
            if not refresh:
                memo = self._memo.get(key)
                if memo is not None and memo[0] == day:
                    return memo[1]
                if self.disk:
                    rows = load_listing(key, day)
                    if rows:
                        self._memo[key] = (day, rows)
                        return rows
            rows = [slim(r) for r in pull()]
            self.pulls += 1
            if rows:
                self._memo[key] = (day, rows)
                if self.disk:
                    store_listing(key, day, rows)
            return rows

    def drop(self, underlying: str | None = None) -> None:
        """Forget memory and today's file for one underlying (None = all memoised)."""
        keys = [underlying.upper()] if underlying else list(self._memo)
        day = exchange_day()
        for key in keys:
            with self._lock_for(key):
                self._memo.pop(key, None)
                if self.disk:
                    drop_listing(key, day)

    def cached(self, underlying: str) -> bool:
        memo = self._memo.get(underlying.upper())
        return memo is not None and memo[0] == exchange_day()

    def peek(self, underlying: str) -> list[dict] | None:
        """The day's rows if they are at hand (memory, else the day's file) —
        never a pull. None on a miss."""
        key = underlying.upper()
        day = exchange_day()
        with self._lock_for(key):
            memo = self._memo.get(key)
            if memo is not None and memo[0] == day:
                return memo[1]
            if not self.disk:
                return None
            rows = load_listing(key, day)
            if rows:
                self._memo[key] = (day, rows)
            return rows
