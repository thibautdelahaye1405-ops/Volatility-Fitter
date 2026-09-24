"""Fewer, fuller snapshot pages — the Massive chain request plan (2026-09-24).

The snapshot endpoint (``/v3/snapshot/options/{underlying}``) pages 250 rows
at a time and a liquid name lists hundreds of strikes per expiry, most of
them far outside anything the quote prep keeps (``volfit.data.strike_window``:
the prep drops |ln K/F| > 4 ATM sd). Measured before this module (SPY, the
9-rung ladder): 1.35 s cold / 1.18 s warm for 3,454 quotes, most of the pages
spent on wings the fit never sees; the whole 29-expiry horizon 5.6 s as one
serial page stream. The plan here:

(a) the NEAREST selected expiry is fetched FIRST and UNWINDOWED — the
    smallest page set — and yields the spot: ``underlying_asset.price`` when
    the snapshot carries it, else the parity forward of its own results,
    else the provider's last known spot for the ticker (``_last_spot``,
    updated on every successful chain / spot read);
(b) the REMAINING expiries carry ``strike_price.gte/lte`` from
    ``strike_bounds(spot, expiry, today, window_vol)`` — a window that
    CONTAINS the prep's band, so the PREPARED quotes are byte-identical with
    the window on or off (tests/test_massive.py locks it) — two in flight as
    before (``_SNAPSHOT_WORKERS``: 3–4 measured slower, 8 timed out);
(c) the WHOLE-HORIZON fetch (no selection) is ``horizon_shards`` shards over
    ``expiration_date.gte/lte`` (the horizon split at its midpoint), each a
    full-page paginated stream, two in flight, windowed at the shard's LAST
    expiry (the widest window in the shard) when a spot is already known;
(d) ``window_vol`` (constructor param; ``None`` = no strike filter, the
    requests byte-identical to the pre-window ones; ``horizon_shards=1`` =
    the single stream) lets the desk A/B the plan.

Bounds are rounded OUTWARD to 4 decimals so a listed strike on the boundary
is never lost to a float representation.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from volfit.data.fieldmap import price_or_none
from volfit.data.strike_window import strike_bounds

#: Snapshot page size cap (Massive limits to 250; 1000 answers ``status: ERROR``).
SNAPSHOT_LIMIT = 250
#: Concurrent snapshot streams (per-expiry queries or horizon shards). Kept
#: DELIBERATELY LOW: on live SPY, 2 workers cut a 6-expiry fetch ~1.7x, 3–4 ran
#: SLOWER than sequential and 8 hit read-timeouts.
SNAPSHOT_WORKERS = 2
#: Whole-horizon shards by default (the horizon split at its midpoint date).
DEFAULT_HORIZON_SHARDS = 2


def strike_params(bounds: tuple[float, float] | None) -> dict:
    """The ``strike_price.gte/lte`` filter for ``bounds`` (empty when None),
    rounded outward to four decimals."""
    if bounds is None:
        return {}
    lo, hi = bounds
    return {
        "strike_price.gte": math.floor(lo * 1e4) / 1e4,
        "strike_price.lte": math.ceil(hi * 1e4) / 1e4,
    }


def horizon_shards(
    today: date, max_days: int, shards: int, weights: dict[date, int] | None = None
) -> list[tuple[date | None, date]]:
    """``(gte, lte)`` date ranges tiling ``(today, today + max_days]``; the first
    shard has no lower bound (today's requests never had one).

    With ``weights`` (listed contracts per expiry — the day's listing) the cuts
    sit at the cumulative-count quantiles so every shard pages about the same
    number of rows: the listing is front-loaded (SPY 2026-09-24: the date
    midpoint gave 38 + 10 pages, the count median 24 + 24). Without them the
    horizon is split at its midpoint date(s)."""
    end = today + timedelta(days=max_days)
    n = max(int(shards), 1)
    if n == 1:
        return [(None, end)]
    cuts: list[date] = []
    listed = sorted((e, w) for e, w in (weights or {}).items() if today < e < end and w > 0)
    total = sum(w for _, w in listed)
    if total > 0:
        cum, target = 0, 1
        for e, w in listed:
            cum += w
            while target < n and cum >= total * target / n:
                if not cuts or e > cuts[-1]:
                    cuts.append(e)
                target += 1
    if not cuts:
        cuts = [today + timedelta(days=max_days * i // n) for i in range(1, n)]
    out: list[tuple[date | None, date]] = []
    start: date | None = None
    for stop in [*cuts, end]:
        if start is not None and stop < start:
            continue  # a degenerate shard (a cut at the horizon's end)
        out.append((start, stop))
        start = stop + timedelta(days=1)
    return out


def spot_of_results(results: list[dict], parity) -> float | None:
    """The spot a page set implies: ``underlying_asset.price``, else ``parity``
    (the provider's ``_spot_from_parity``) on the results."""
    for result in results:
        px = price_or_none((result.get("underlying_asset") or {}).get("price"))
        if px is not None:
            return float(px)
    return parity(results)


class MassiveSnapshotMixin:
    """The snapshot plan for ``MassiveProvider`` (uses the host's ``_paginate``,
    ``_underlying``, ``_spot_from_parity``, ``_client``, ``max_days``,
    ``window_vol``, ``horizon_shards`` and the ``_last_spot`` memory)."""

    max_days: int
    window_vol: float | None
    horizon_shards: int
    _last_spot: dict[str, float]

    def _note_spot(self, ticker: str, spot: float | None) -> None:
        """Remember the last usable spot per ticker (the whole-horizon window,
        the fallback when a nearest-expiry page carries none)."""
        if spot is not None and math.isfinite(spot) and spot > 0.0:
            self._last_spot[ticker.upper()] = float(spot)

    def last_spot(self, ticker: str) -> float | None:
        return self._last_spot.get(ticker.upper())

    def _snapshot_results(self, ticker: str, expiries: list[date] | None) -> list[dict]:
        """Raw snapshot ``results`` for the selected expiries (or the horizon),
        concatenated in sorted-expiry (or shard) order whatever the completion
        order — the module docstring's plan (a)–(d)."""
        path = f"/v3/snapshot/options/{self._underlying(ticker)}"
        today = date.today()

        def stream(params: dict) -> list[dict]:
            return list(self._paginate(path, {**params, "limit": SNAPSHOT_LIMIT}))

        if expiries:
            exps = sorted(expiries)
            first = stream({"expiration_date": exps[0].isoformat()})  # (a): unwindowed
            rest = exps[1:]
            if not rest:
                return first
            spot = spot_of_results(first, self._spot_from_parity) or self.last_spot(ticker)
            self._note_spot(ticker, spot)
            plans = [
                {"expiration_date": e.isoformat(), **strike_params(self._bounds(spot, e, today))}
                for e in rest
            ]
        else:
            spot = self.last_spot(ticker)
            plans = []
            weights = self._listing_weights(ticker)
            for gte, lte in horizon_shards(today, self.max_days, self.horizon_shards, weights):
                params = {"expiration_date.lte": lte.isoformat()}
                if gte is not None:
                    params = {"expiration_date.gte": gte.isoformat(), **params}
                plans.append({**params, **strike_params(self._bounds(spot, lte, today))})
            first = []
        return first + self._fan_out(stream, plans)

    def _listing_weights(self, ticker: str) -> dict[date, int] | None:
        """Listed contracts per expiry from the day's listing when it is at hand
        (memory or the disk file — never a pull: a whole-horizon fetch must not
        pay a listing pagination for a better shard split)."""
        rows = self._listings.peek(self._contracts_underlying(ticker))
        if not rows:
            return None
        weights: dict[date, int] = {}
        for r in rows:
            raw = r.get("expiration_date")
            try:
                expiry = date.fromisoformat(str(raw)[:10])
            except (TypeError, ValueError):
                continue
            weights[expiry] = weights.get(expiry, 0) + 1
        return weights

    def _bounds(self, spot: float | None, expiry: date, today: date) -> tuple[float, float] | None:
        """The strike window for ``expiry`` (None = whole ladder: no spot or
        the window switched off)."""
        if spot is None or self.window_vol is None:
            return None
        return strike_bounds(spot, expiry, today, self.window_vol)

    def _fan_out(self, stream, plans: list[dict]) -> list[dict]:
        """Run the page streams ``SNAPSHOT_WORKERS`` at a time, results in plan order."""
        if not plans:
            return []
        if len(plans) == 1:
            return stream(plans[0])
        if self._http_get is None:
            self._client()  # warm the pooled client once before fanning out (no race)
        out: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(SNAPSHOT_WORKERS, len(plans))) as pool:
            for chunk in pool.map(stream, plans):  # map preserves input order
                out.extend(chunk)
        return out
