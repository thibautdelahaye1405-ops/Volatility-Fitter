"""The METERED reference-data half of the Bloomberg provider — fields, hit
meter, the live quote pull, the exercise-style probe and the on-demand enrich.

Why: every ``bdp`` / ``bds`` / ``bdh`` is billed as securities × fields
("hits") against a daily quota AND a monthly unique-securities budget (~4–5k
on this account, gated twice). The fit only ever reads BID and ASK, yet the
live pull used to request six fields per contract (SPY, 2 expiries: 692
securities × 6 = 4,152 hits for one Fetch — measured 2026-09-23). So:

* ``LIVE_FIELDS`` — the live pull requests BID/ASK only (a third of the hits);
* ``STYLE_FIELD`` (OPT_EXER_TYP) is read ONCE per ticker per exchange day from
  one representative contract (one hit), the index / " Index" rule the fallback;
* ``REFERENCE_FIELDS`` (LAST_PRICE / VOLUME / OPEN_INT — the Quote Table's
  colour, never a fit input) move to the explicit ``enrich_reference`` — NOT
  called by ``fetch_chain``: on the reference path the table shows OI / volume
  only after an enrich (the UI action is the lead's to wire);
* ``CallMeter`` counts the hits, the unique securities and the last fetch wall,
  exposed as ``call_stats()`` and appended to the status light's detail.

``MeteredBlp`` wraps the ``xbbg.blp`` module (real or a test fake) so every
reference request of every path — listing, spot, quotes, history — is counted
at one choke point; the wrapper forwards everything else untouched.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Callable

from volfit.data.bloomberg_parse import ParsedOption, pivot_bdp
from volfit.data.bloomberg_roots import representative
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: The fields a live pull requests per contract — the only ones the fit reads.
LIVE_FIELDS = ("BID", "ASK")
#: Reference colour for the Quote Table, pulled on demand by ``enrich_reference``.
REFERENCE_FIELDS = ("LAST_PRICE", "VOLUME", "OPEN_INT")
#: The exercise-style field, probed once per ticker per exchange day.
STYLE_FIELD = "OPT_EXER_TYP"


class CallMeter:
    """Hits (securities × fields) per ET exchange day, the unique securities
    touched today, and the last live fetch's size and wall — the numbers the
    quota is billed on (a bds counts as one security × one field)."""

    def __init__(self, day_fn: Callable[[], date]) -> None:
        self._day_fn = day_fn
        self._day: date | None = None
        self.hits = 0
        self.calls = 0
        self.unique: set[str] = set()
        self.last_fetch_wall: float | None = None
        self.last_fetch_hits = 0
        self.last_fetch_securities = 0

    def _roll(self) -> None:
        day = self._day_fn()
        if day != self._day:
            self._day, self.hits, self.calls, self.unique = day, 0, 0, set()

    def record(self, securities: list[str], fields: list[str]) -> int:
        """Count one answered request; returns its hits."""
        self._roll()
        hits = len(securities) * max(len(fields), 1)
        self.hits += hits
        self.calls += 1
        self.unique.update(securities)
        return hits

    def note_fetch(self, securities: int, hits: int, wall: float) -> None:
        self.last_fetch_securities, self.last_fetch_hits, self.last_fetch_wall = securities, hits, wall

    def stats(self) -> dict:
        self._roll()
        return {
            "day": self._day.isoformat() if self._day else None,
            "hitsToday": self.hits,
            "callsToday": self.calls,
            "uniqueSecuritiesToday": len(self.unique),
            "lastFetchSecurities": self.last_fetch_securities,
            "lastFetchHits": self.last_fetch_hits,
            "lastFetchWall": self.last_fetch_wall,
        }


class MeteredBlp:
    """``xbbg.blp`` with the reference requests counted (answered ones only —
    a refused request delivers no data); every other attribute is forwarded,
    so ``is_connected`` / ``_get_engine`` and a test fake's own bookkeeping
    keep working through the wrapper."""

    def __init__(self, blp, meter: CallMeter) -> None:
        self._blp = blp
        self._meter = meter

    @staticmethod
    def _as_list(value) -> list[str]:
        return [value] if isinstance(value, str) else list(value)

    def bdp(self, securities, fields, **kwargs):
        out = self._blp.bdp(securities, fields, **kwargs)
        self._meter.record(self._as_list(securities), self._as_list(fields))
        return out

    def bds(self, security, field, **kwargs):
        out = self._blp.bds(security, field, **kwargs)
        self._meter.record(self._as_list(security), self._as_list(field))
        return out

    def bdh(self, securities, fields, *args, **kwargs):
        out = self._blp.bdh(securities, fields, *args, **kwargs)
        self._meter.record(self._as_list(securities), self._as_list(fields))
        return out

    def __getattr__(self, name):
        return getattr(self._blp, name)


def resolve_style(value) -> str | None:
    """'American' / 'European' (any case) -> the app's style, else None."""
    style = str(value or "").strip().lower()
    return style if style in ("american", "european") else None


class BloombergReferenceMixin:
    """The metered quote path of ``BloombergProvider`` (expects the host to
    provide ``_blp_module``, ``_security``, ``_select_contracts``,
    ``_window_contracts``, ``spot``, ``_settlement``, ``_record``,
    ``_exchange_day``)."""

    def _init_reference(self) -> None:
        self._meter = CallMeter(self._exchange_day)
        #: Reference-only facts the stream cannot carry: OI / volume / last per
        #: security from the last ``enrich_reference``, the exercise style per
        #: ticker (with the exchange day it was probed on).
        self._oi_cache: dict[str, int] = {}
        self._volume_cache: dict[str, int] = {}
        self._last_cache: dict[str, float] = {}
        self._style_cache: dict[str, str] = {}
        self._style_day: dict[str, date] = {}

    # ------------------------------------------------------------- meter
    def call_stats(self) -> dict:
        """Today's metered usage: hits, calls, unique securities, the last live
        fetch's securities / hits / wall (the status light shows the hits)."""
        return self._meter.stats()

    def _hits_suffix(self) -> str:
        hits = self._meter.stats()["hitsToday"]
        return f" · {hits:,} hits today" if hits else ""

    # ------------------------------------------------------- exercise style
    def _fallback_style(self, ticker: str) -> str:
        return "european" if self._security(ticker).endswith(" Index") else "american"

    def _exercise_style(self, ticker: str, contracts: list[ParsedOption]) -> str:
        """The chain's exercise style: cached for the exchange day, else ONE
        OPT_EXER_TYP hit on the selection's median-strike call. A probe the
        Terminal cannot answer falls back to the index rule for this fetch
        only (an answer is what gets cached)."""
        key, day = ticker.upper(), self._exchange_day()
        cached = self._style_cache.get(key)
        if cached is not None and self._style_day.get(key) == day:
            return cached
        style = None
        if contracts:
            rep = representative(contracts)
            try:
                pivot = pivot_bdp(self._blp_module().bdp([rep.security], [STYLE_FIELD]))
                style = resolve_style(pivot.get(rep.security, {}).get(STYLE_FIELD))
            except Exception:  # noqa: BLE001 — the quote pull right after reports a refusal
                style = None
        if style is None:
            return self._style_cache.get(key) or self._fallback_style(ticker)
        self._style_cache[key], self._style_day[key] = style, day
        return style

    # ------------------------------------------------------------ live pull
    def _fetch_live(self, ticker: str, contracts: list[ParsedOption]) -> ChainSnapshot:
        """The current chain for ``contracts`` — the spot (book or one PX_LAST),
        the once-a-day style probe, then ONE bdp of BID/ASK over the windowed
        contracts. LAST / VOLUME / OI come from the enrich caches (None before
        an ``enrich_reference``)."""
        t0 = time.perf_counter()
        spot = self.spot(ticker)  # off the stream book when streaming, else PX_LAST
        contracts = self._window_contracts(contracts, spot)  # quota: the fittable band only
        style = self._exercise_style(ticker, contracts)
        pivot = pivot_bdp(self._blp_module().bdp([c.security for c in contracts], list(LIVE_FIELDS)))
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
        quotes = [
            OptionQuote(
                ticker=ticker,
                expiry=c.expiry,
                strike=c.strike,
                call_put=c.call_put,  # parsed from the descriptor
                bid=price_or_none(pivot.get(c.security, {}).get("BID")),
                ask=price_or_none(pivot.get(c.security, {}).get("ASK")),
                last=self._last_cache.get(c.security),
                volume=self._volume_cache.get(c.security),
                open_interest=self._oi_cache.get(c.security),
                timestamp=timestamp,
            )
            for c in contracts
        ]
        self._meter.note_fetch(len(contracts), len(contracts) * len(LIVE_FIELDS), time.perf_counter() - t0)
        return ChainSnapshot(
            ticker=ticker,
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=style,
            tick_size=US_OPTION_TICK,
            settlement=self._settlement(ticker, {q.expiry for q in quotes}),
        )

    # --------------------------------------------------------------- enrich
    def enrich_reference(self, ticker: str, expiries: list[date] | None = None) -> dict:
        """On-demand LAST_PRICE / VOLUME / OPEN_INT over the selection's windowed
        contracts (one bdp, three hits per contract), filling the caches every
        later chain — metered or streamed — reads. Never called by ``fetch_chain``.
        Returns ``{ticker, securities, hits, wall, openInterest, volume}``."""
        t0 = time.perf_counter()
        try:
            contracts = self._window_contracts(self._select_contracts(ticker, expiries), self.spot(ticker))
            pivot = pivot_bdp(self._blp_module().bdp([c.security for c in contracts], list(REFERENCE_FIELDS)))
        except Exception as exc:
            self._record(exc)
            raise
        self._record(None)
        n_oi = n_vol = 0
        for c in contracts:
            fields = pivot.get(c.security, {})
            oi, vol, last = (int_or_none(fields.get("OPEN_INT")), int_or_none(fields.get("VOLUME")),
                             price_or_none(fields.get("LAST_PRICE")))
            if oi is not None:
                self._oi_cache[c.security] = oi
                n_oi += 1
            if vol is not None:
                self._volume_cache[c.security] = vol
                n_vol += 1
            if last is not None:
                self._last_cache[c.security] = last
        return {
            "ticker": ticker.upper(), "securities": len(contracts),
            "hits": len(contracts) * len(REFERENCE_FIELDS), "wall": time.perf_counter() - t0,
            "openInterest": n_oi, "volume": n_vol,
        }
