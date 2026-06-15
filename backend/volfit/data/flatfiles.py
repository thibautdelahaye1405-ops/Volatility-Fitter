"""Massive/Polygon flat-file history → local columnar cache (ROADMAP Tier 2).

The flat files are the long-deferred columnar history: daily gzipped CSV
aggregates on an S3-compatible bucket (``files.polygon.io`` / ``flatfiles``),
one row per (contract, bar). Two products matter here:

  * ``minute_aggs_v1`` — one OHLCV bar per contract per minute, so any past
    intraday chain can be reconstructed at a target minute (the as-of
    "latest" / "before close" moments on a *past* day);
  * ``day_aggs_v1``    — one bar per contract per day, the official close (the
    as-of "close" moment on a past day).

Path layout: ``s3://{bucket}/{prefix}/{product}/{YYYY}/{MM}/{YYYY-MM-DD}.csv.gz``
with columns ``ticker,volume,open,close,high,low,window_start,transactions``
(``window_start`` = nanoseconds since the Unix epoch, UTC). Contracts carry only
the ``O:`` ticker, which fully encodes strike/expiry/type — see ``volfit.data.occ``.

Design:
  * DuckDB (+ the bundled ``httpfs`` extension) reads the gzipped CSV straight
    from S3, filters to the watchlist underlyings, and the day's filtered rows
    are cached locally as Parquet (lazy, once per (date, product)). Per-ticker
    reconstruction then queries that small local Parquet — cheap and offline.
  * ``chain_at`` reconstructs a ``ChainSnapshot`` at a target instant: each
    contract's bar at-or-before the target (minute) / the day's bar (day), with
    the ``close`` quoted as a zero-spread bid=ask=close (like a prev-close mark),
    and spot implied from put-call parity on the reconstructed closes.

The S3 read is isolated in ``_query_bars``; tests inject ``source_uri`` to point
at a local fixture CSV, so the duckdb read + as-of window query run offline.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterable

from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.occ import parse_option_symbol
from volfit.data.types import ChainSnapshot, OptionQuote

#: Default S3-compatible host + bucket (Polygon flat files; Massive inherits it).
DEFAULT_ENDPOINT = "files.polygon.io"
DEFAULT_BUCKET = "flatfiles"
#: Options aggregates live under this prefix; products are the two aggregate sets.
DEFAULT_PREFIX = "us_options_opra"
_PRODUCT = {"minute": "minute_aggs_v1", "day": "day_aggs_v1"}


@dataclass(frozen=True)
class _Bar:
    """One reconstructed aggregate bar (the close is the price we quote)."""

    ticker: str
    close: float | None
    volume: int | None
    window_start_ns: int


class FlatFileStore:
    """Lazy S3 flat-file reader with a local Parquet day-cache.

    Parameters
    ----------
    access_key/secret : S3 credentials for the flat-file bucket.
    endpoint/bucket/prefix : S3 host, bucket and options prefix (configurable so a
                Massive-branded host is a pure config change).
    cache_dir : local directory for the per-day Parquet cache (created lazily).
    source_uri : test hook ``(day, frequency) -> uri`` overriding the S3 path with
                a local fixture; when set, credentials are not used.
    """

    def __init__(
        self,
        access_key: str = "",
        secret: str = "",
        endpoint: str = DEFAULT_ENDPOINT,
        bucket: str = DEFAULT_BUCKET,
        prefix: str = DEFAULT_PREFIX,
        cache_dir: str | None = None,
        source_uri: Callable[[date, str], str] | None = None,
    ) -> None:
        self.access_key = access_key
        self.secret = secret
        self.endpoint = endpoint
        self.bucket = bucket
        self.prefix = prefix
        self.cache_dir = cache_dir
        self._source_uri = source_uri

    # ------------------------------------------------------------ public API
    def available(self) -> bool:
        """Whether the store is usable (has credentials, or a test source)."""
        return bool(self._source_uri or (self.access_key and self.secret))

    def chain_at(
        self,
        ticker: str,
        expiries: list[date] | None,
        ts: datetime,
        underlyings: Iterable[str] | None = None,
        frequency: str = "minute",
    ) -> ChainSnapshot | None:
        """Reconstruct ``ticker``'s chain at instant ``ts`` from the flat files.

        ``underlyings`` is the full watchlist to co-cache from the same daily file
        (defaults to just ``ticker``); ``expiries`` restricts the rungs. Returns
        None when the day's file has no usable bars for the ticker.
        """
        day = ts.date()
        roots = sorted({u.upper() for u in (underlyings or [ticker])} | {ticker.upper()})
        target_ns = _to_ns(ts)
        bars = self._latest_bars(day, roots, target_ns, frequency)
        wanted = set(expiries) if expiries else None
        quotes: list[OptionQuote] = []
        upper = ticker.upper()
        for bar in bars:
            try:
                occ = parse_option_symbol(bar.ticker)
            except ValueError:
                continue
            if occ.underlying != upper or bar.close is None:
                continue
            if wanted is not None and occ.expiry not in wanted:
                continue
            quotes.append(
                OptionQuote(
                    ticker=upper,
                    expiry=occ.expiry,
                    strike=occ.strike,
                    call_put=occ.call_put,
                    bid=bar.close,  # zero-spread close (prev-close-style mark)
                    ask=bar.close,
                    last=bar.close,
                    volume=bar.volume,
                    open_interest=None,
                    timestamp=ts,
                )
            )
        if not quotes:
            return None
        spot = _parity_spot(quotes)
        if spot is None:
            return None
        return ChainSnapshot(
            ticker=upper, spot=spot, timestamp=ts, quotes=quotes,
            exercise_style="american",  # US single-stock / ETF options
        )

    # ------------------------------------------------------------- internals
    def _uri(self, day: date, frequency: str) -> str:
        """S3 URI of the day's aggregate file (or the injected fixture)."""
        if self._source_uri is not None:
            return self._source_uri(day, frequency)
        product = _PRODUCT[frequency]
        return (
            f"s3://{self.bucket}/{self.prefix}/{product}/"
            f"{day:%Y}/{day:%m}/{day:%Y-%m-%d}.csv.gz"
        )

    def _cache_path(self, day: date, frequency: str) -> str | None:
        if self.cache_dir is None:
            return None
        return os.path.join(self.cache_dir, f"{self.prefix}_{frequency}_{day:%Y-%m-%d}.parquet")

    def _ensure_cached(self, day: date, roots: list[str], frequency: str) -> str:
        """Materialize the day's watchlist-filtered bars to a local Parquet once;
        return the Parquet path (or the source URI when no cache dir is set)."""
        cache = self._cache_path(day, frequency)
        if cache is None:
            return self._uri(day, frequency)
        if not os.path.exists(cache):
            os.makedirs(self.cache_dir, exist_ok=True)
            con = self._connect()
            try:
                con.execute(
                    f"COPY (SELECT ticker, close, volume, window_start "
                    f"FROM read_csv_auto(?) WHERE {_root_filter('ticker', roots)}) "
                    f"TO '{cache}' (FORMAT PARQUET)",
                    [self._uri(day, frequency)],
                )
            finally:
                con.close()
        return cache

    def _latest_bars(
        self, day: date, roots: list[str], target_ns: int, frequency: str
    ) -> list[_Bar]:
        """Each contract's most recent bar at-or-before ``target_ns`` that day."""
        source = self._ensure_cached(day, roots, frequency)
        con = self._connect()
        try:
            rows = con.execute(
                "SELECT ticker, close, volume, window_start FROM read_parquet(?) "
                "WHERE window_start <= ? "
                "QUALIFY row_number() OVER "
                "(PARTITION BY ticker ORDER BY window_start DESC) = 1"
                if source.endswith(".parquet")
                else (
                    f"SELECT ticker, close, volume, window_start FROM read_csv_auto(?) "
                    f"WHERE window_start <= ? AND {_root_filter('ticker', roots)} "
                    f"QUALIFY row_number() OVER "
                    f"(PARTITION BY ticker ORDER BY window_start DESC) = 1"
                ),
                [source, target_ns],
            ).fetchall()
        finally:
            con.close()
        return [
            _Bar(
                ticker=str(r[0]),
                close=price_or_none(r[1]),
                volume=int_or_none(r[2]),
                window_start_ns=int(r[3]),
            )
            for r in rows
        ]

    def _connect(self):
        """A DuckDB connection with httpfs configured for the flat-file bucket."""
        import duckdb

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        if not self._source_uri:  # real S3: set endpoint + credentials
            con.execute(
                "SET s3_endpoint=?; SET s3_region='us-east-1'; "
                "SET s3_url_style='path'; SET s3_use_ssl=true;",
                [self.endpoint],
            )
            con.execute(
                "SET s3_access_key_id=?; SET s3_secret_access_key=?;",
                [self.access_key, self.secret],
            )
        return con


def _root_filter(column: str, roots: list[str]) -> str:
    """SQL predicate matching ``O:<root>`` for any watchlist root (exact root —
    ``O:SPY`` followed by the 6-digit date, so it never matches ``O:SPYG``)."""
    alt = "|".join(re.escape(r.upper()) for r in roots)
    return f"regexp_matches({column}, '^O:({alt})[0-9]{{6}}[CP]')"


def _to_ns(ts: datetime) -> int:
    """UTC-naive datetime → nanoseconds since the Unix epoch (the bar clock)."""
    return int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _parity_spot(quotes: list[OptionQuote]) -> float | None:
    """Spot proxy = nearest-expiry forward from put-call parity on the closes."""
    import numpy as np

    by_exp: dict[date, dict[float, dict[str, float]]] = {}
    for q in quotes:
        if q.bid is None:
            continue
        by_exp.setdefault(q.expiry, {}).setdefault(q.strike, {})[q.call_put] = q.bid
    for expiry in sorted(by_exp):
        pairs = [(k, v["C"], v["P"]) for k, v in by_exp[expiry].items() if "C" in v and "P" in v]
        if len(pairs) < 3:
            continue
        strikes = np.array([p[0] for p in pairs], dtype=float)
        y = np.array([p[1] - p[2] for p in pairs], dtype=float)
        (a, b), *_ = np.linalg.lstsq(np.column_stack([np.ones_like(strikes), strikes]), y, rcond=None)
        discount = -float(b)
        if discount > 0.0:
            return float(a) / discount
    return None
