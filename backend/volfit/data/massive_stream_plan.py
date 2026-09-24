"""The PLAN half of the Massive live book — the strike window, its
hysteresis-held centre and the nearest-the-money rank (split out of
volfit.data.massive_stream on 2026-09-24 to keep each module under the
400-line policy; the design is in that module's docstring).

``MassiveStreamPlanMixin`` gives the provider ``option_tickers`` (the plan
the scheduler asks for every tick — cheap once the listing and the centre
are cached), the centring (``_window_center``: the book's parity spot when
serving, else the last REST spot, else ONE nearest-expiry snapshot page
retried at most every minute; re-centred only after a > ``RECENTER_PCT``
move so a spot wobbling across a strike does not re-plan every tick) and
the rank (|ln K/centre| / sqrt(T), stable so a call precedes its put).
Expects the host's ``_intraday_contracts``, ``available_expiries``,
``last_spot`` / ``_note_spot``, ``_get``, ``base_url``, ``_underlying``,
``_spot_from_parity``, ``window_vol`` and the stream state ``_stream_index``,
``_ticker_plans``, ``_stream_center``, ``_center_failed_at``, ``_plan_cache``,
``_live_book`` and ``_book_parity_spot``.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import date

from volfit.data.massive_snapshot import SNAPSHOT_LIMIT, spot_of_results
from volfit.data.strike_window import inside, strike_bounds

log = logging.getLogger("volfit.massive_ws")

#: Re-centre the strike window only after the spot moves this far (fraction).
RECENTER_PCT = 0.05
#: Retry a failed centring snapshot page at most this often.
_SPOT_RETRY_SECONDS = 60.0


class MassiveStreamPlanMixin:
    """The windowed, ranked plan of a ticker's selection."""

    def _window_center(self, ticker: str) -> float | None:
        """The spot the strike window is centred on: the live reading (the book's
        parity spot when serving, else the last REST spot) once a > RECENTER_PCT
        move is seen, else the held centre, else ONE nearest-expiry snapshot
        page (retried at most every minute). None = cannot plan yet."""
        key = ticker.upper()
        held = self._stream_center.get(key)
        live = self._book_parity_spot(ticker) if self._live_book is not None else None
        if live is None:
            live = self.last_spot(ticker)
        if live is not None and (held is None or abs(live / held - 1.0) > RECENTER_PCT):
            self._stream_center[key] = held = live
        if held is not None:
            return held
        last_fail = self._center_failed_at.get(key)
        if last_fail is not None and time.monotonic() - last_fail < _SPOT_RETRY_SECONDS:
            return None
        try:
            probe = self._probe_center(ticker)
        except Exception as exc:  # noqa: BLE001 — unreachable / gated: back off a minute
            log.warning("massive stream: %s centring page failed: %s", key, exc)
            probe = None
        if probe is None:
            self._center_failed_at[key] = time.monotonic()
            return None
        self._stream_center[key] = probe
        self._note_spot(key, probe)
        return probe

    def _probe_center(self, ticker: str) -> float | None:
        """One snapshot PAGE of the nearest listed expiry → its spot."""
        expiries = self.available_expiries(ticker)
        if not expiries:
            return None
        body = self._get(
            f"{self.base_url}/v3/snapshot/options/{self._underlying(ticker)}",
            {"expiration_date": expiries[0].isoformat(), "limit": SNAPSHOT_LIMIT},
        )
        if body.get("status") == "NOT_AUTHORIZED":
            return None
        return spot_of_results(list(body.get("results") or []), self._spot_from_parity)

    def option_tickers(self, ticker: str, expiries: list[date] | None) -> list[str]:
        """The PLAN for ``ticker``'s selection: listed contracts inside the
        per-expiry window around the held centre, nearest-the-money first.
        Cheap once the listing and the centre are cached (called every tick);
        empty until a centre exists."""
        key = ticker.upper()
        today = date.today()
        center = self._window_center(ticker)
        if center is None:
            self._ticker_plans[key] = []
            return []
        cache_key = (key, frozenset(expiries) if expiries else None, today, center)
        plan = self._plan_cache.get(cache_key)
        if plan is None:
            plan = self._rank_contracts(self._intraday_contracts(ticker, expiries), center, today)
            if len(self._plan_cache) > 64:
                self._plan_cache.clear()
            self._plan_cache[cache_key] = plan
        for contract, row, rank in plan:
            self._stream_index[contract] = (key, row, rank)
        self._ticker_plans[key] = [c for c, _, _ in plan]
        return list(self._ticker_plans[key])

    def _rank_contracts(self, rows: list[dict], center: float, today: date) -> list[tuple[str, dict, float]]:
        """Window + rank: keep the rows inside ``strike_bounds`` of their expiry,
        ordered by |ln K/centre| / sqrt(T) (stable, so a call precedes its put)."""
        bounds: dict[date, tuple[float, float] | None] = {}
        ranked: list[tuple[float, str, dict]] = []
        for row in rows:
            expiry, strike = row["expiry"], row["strike"]
            if strike <= 0.0:
                continue
            if expiry not in bounds:
                bounds[expiry] = strike_bounds(center, expiry, today, self.window_vol)
            if not inside(strike, bounds[expiry]):
                continue
            years = max((expiry - today).days, 1) / 365.0
            ranked.append((abs(math.log(strike / center)) / math.sqrt(years), row["ticker"], row))
        ranked.sort(key=lambda item: item[0])
        return [(contract, row, rank) for rank, contract, row in ranked]

    def _drop_stream_plans(self) -> None:
        """Forget the memoised plans (the day rolled: the listing is re-pulled
        and ``option_tickers`` re-derives — expired rungs out, the new one in)."""
        self._plan_cache.clear()


__all__ = ["MassiveStreamPlanMixin", "RECENTER_PCT"]
