"""The "auto" source pin — the fastest green source per ticker (2026-09-24).

WHY: the per-ticker pins (volfit.api.state_sources) name ONE registered
source. A desk running several feeds at once (Cboe delayed at 0.8 s a chain,
Massive at 1.4 s, Yahoo at 2.7 s, a Bloomberg Terminal at 6–14 s) had to
re-pin by hand when a feed went red or slow. The pin value ``AUTO_SOURCE``
resolves, per ticker, to the fastest source that (i) is registered, (ii) has
a cached status of green or amber — a red / timed-out feed is never picked
(``PENDING_STATUS`` is amber: a never-probed feed stays a candidate) — and
(iii) can serve the ticker by a CHEAP check (``can_serve``: listed by the
provider, or an open-universe live feed that takes any symbol); nothing here
touches the network — resolution runs inside ``source_of``.

RANKING: a per-source EWMA (``EWMA_ALPHA``) of the measured live chain-fetch
wall (recorded around the provider call in ``AppState._fetch_and_cache``),
seeded from the static order Cboe → Massive → Nasdaq → Yahoo → Bloomberg
(the walls measured for SPY on 2026-09-23) until a source has been measured;
a source outside the seed ranks after the seeded ones, ties break on
registration order.

STABILITY: a resolution is REMEMBERED and only re-ranked at Fetch time
(``SourcesMixin.refresh_auto_source``, called from the chain pull) — never on
a spot tick, a status poll or a read — so a ticker does not hop between feeds
between two Fetches. A change of resolution drops the ticker's chain caches
like a re-pin (its nodes go stale, the next Fetch pulls from the new source)
and is never silent: ``GET /universe`` reports the resolved source beside the
pin (``resolvedSources``).

Process state, not workspace state: the pins persist (``tickerSources``), the
walls and resolutions are rebuilt on the next process.
"""

from __future__ import annotations

import threading

#: The pin value that means "the fastest green source for this ticker".
AUTO_SOURCE = "auto"

#: Static seed order (fastest first) used until a source has a measured wall.
SEED_ORDER: tuple[str, ...] = ("cboe", "massive", "nasdaq", "yahoo", "bloomberg")

#: Seed walls in seconds (SPY chain fetch, 2026-09-23): the ranking before any
#: measurement, and the prior the EWMA starts from.
SEED_WALL_S: dict[str, float] = {
    "cboe": 0.8, "massive": 1.4, "nasdaq": 2.0, "yahoo": 2.7, "bloomberg": 6.0,
}

#: A source outside the seed ranks after every seeded one until measured.
UNSEEDED_WALL_S = 10.0

#: EWMA weight of the newest measured wall.
EWMA_ALPHA = 0.3

#: Cached status levels an auto pin may resolve to.
ELIGIBLE_LEVELS = frozenset({"green", "amber"})

#: Live feeds that accept ANY (US-listed) symbol on add — the universe picker
#: adds a name on them without a catalogue — versus the sources that serve a
#: fixed universe (synthetic, file) or a regional venue's listing (asx, hkex,
#: sgx, eurex), which serve a ticker only when they list it.
OPEN_UNIVERSE_SOURCES = frozenset({"yahoo", "massive", "bloomberg", "cboe", "nasdaq"})


def can_serve(sid: str, prov, ticker: str) -> bool:
    """CHEAP capability check, no network: the provider lists the ticker, or
    says it takes any symbol (``accepts_any_symbol``, attribute or method), or
    is one of the open-universe live feeds."""
    try:
        if ticker in prov.list_tickers():
            return True
    except Exception:  # noqa: BLE001 — a listing failure is "not listed"
        pass
    accepts = getattr(prov, "accepts_any_symbol", None)
    if accepts is not None:
        return bool(accepts() if callable(accepts) else accepts)
    return sid in OPEN_UNIVERSE_SOURCES


class SourcePolicy:
    """Per-source fetch walls (EWMA) + the remembered auto resolutions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._walls: dict[str, float] = {}
        self._resolved: dict[str, str] = {}

    # ------------------------------------------------------------- walls
    def record_wall(self, sid: str, seconds: float) -> None:
        """Fold one measured live chain-fetch wall into the source's EWMA
        (the seed wall is the prior of the first measurement)."""
        if not (seconds >= 0.0):
            return
        with self._lock:
            prev = self._walls.get(sid)
            if prev is None:
                prev = SEED_WALL_S.get(sid, UNSEEDED_WALL_S)
            self._walls[sid] = (1.0 - EWMA_ALPHA) * prev + EWMA_ALPHA * float(seconds)

    def wall(self, sid: str) -> float:
        """The ranking wall of a source: measured EWMA, else its seed."""
        with self._lock:
            measured = self._walls.get(sid)
        return measured if measured is not None else SEED_WALL_S.get(sid, UNSEEDED_WALL_S)

    def walls(self) -> dict[str, float]:
        """The measured EWMAs only (diagnostics)."""
        with self._lock:
            return dict(self._walls)

    # ------------------------------------------------------- resolutions
    def resolved(self, ticker: str) -> str | None:
        with self._lock:
            return self._resolved.get(ticker)

    def remember(self, ticker: str, sid: str) -> None:
        with self._lock:
            self._resolved[ticker] = sid

    def forget(self, ticker: str) -> None:
        with self._lock:
            self._resolved.pop(ticker, None)

    # ------------------------------------------------------------ ranking
    def rank(self, providers: dict, statuses: dict, ticker: str) -> list[str]:
        """The eligible sources for ``ticker``, fastest first (module rules)."""
        order = list(providers)
        eligible = [
            sid for sid in order
            if statuses.get(sid, ("red", ""))[0] in ELIGIBLE_LEVELS
            and can_serve(sid, providers[sid], ticker)
        ]
        return sorted(eligible, key=lambda sid: (self.wall(sid), order.index(sid)))

    def choose(self, providers: dict, statuses: dict, ticker: str, fallback: str) -> str:
        """The fastest eligible source, else ``fallback`` (the universe's
        default: an auto pin never leaves a ticker without a source)."""
        ranked = self.rank(providers, statuses, ticker)
        return ranked[0] if ranked else fallback
