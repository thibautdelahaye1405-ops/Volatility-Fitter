"""NBBO quotes flat-file reader for the backtest harness (Phase 0).

The live app's ``volfit.data.flatfiles.FlatFileStore`` reads only the *trade*
aggregates (``minute_aggs_v1`` / ``day_aggs_v1``) and quotes the bar ``close`` as
a zero-spread ``bid=ask=close``. For the backtest we need the *real* bid/ask, so
this reads Polygon/Massive's ``quotes_v1`` product — every NBBO update for every
OPRA contract, all day — and reconstructs each contract's NBBO at a target
instant (15:45 ET, the "before-close" snapshot that has tight two-sided markets,
unlike the noisy official close).

Path layout (probed live 2026-06-21, entitled + reaching back to 2022):

    s3://{bucket}/{prefix}/quotes_v1/{YYYY}/{MM}/{YYYY-MM-DD}.csv.gz

    columns: ticker, ask_exchange, ask_price, ask_size,
             bid_exchange, bid_price, bid_size, sequence_number, sip_timestamp
    (sip_timestamp = nanoseconds since the Unix epoch, UTC)

Cost note: the quotes file is the OPRA firehose (many GB/day gzipped) and gzip has
no random access, so each *day* costs one full streamed scan regardless of how few
contracts we keep. We therefore co-cache the whole watchlist AND collapse to "the
NBBO at-or-before the target instant per contract" in a single ``COPY`` — the
cached Parquet is then tiny and every per-ticker read is offline. One scan per day,
shared across the whole asset universe.

The S3 read is isolated in ``_reduce_to_cache``; tests inject ``source_uri`` to
point at a local fixture CSV, so the duckdb read + as-of reduction run offline.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Iterable

from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.occ import parse_option_symbol
from volfit.data.types import ChainSnapshot, OptionQuote

DEFAULT_ENDPOINT = "files.massive.com"
DEFAULT_BUCKET = "flatfiles"
DEFAULT_PREFIX = "us_options_opra"
PRODUCT = "quotes_v1"


@dataclass(frozen=True)
class _Nbbo:
    """One contract's reconstructed NBBO at the target instant."""

    ticker: str
    bid: float | None
    ask: float | None
    bid_size: int | None
    ask_size: int | None
    sip_ns: int


class QuotesFlatFileStore:
    """Lazy S3 ``quotes_v1`` reader with a per-(day, roots, instant) Parquet cache.

    Parameters
    ----------
    access_key/secret : S3 credentials for the flat-file bucket (the
        VOLFIT_FLATFILES_* pair; must carry the quotes-tier entitlement).
    endpoint/bucket/prefix : S3 host, bucket and options prefix.
    cache_dir : local directory for the collapsed per-day Parquet cache.
    source_uri : test hook ``(day) -> uri`` overriding the S3 path with a local
        fixture CSV; when set, credentials are not used.
    """

    def __init__(
        self,
        access_key: str = "",
        secret: str = "",
        endpoint: str = DEFAULT_ENDPOINT,
        bucket: str = DEFAULT_BUCKET,
        prefix: str = DEFAULT_PREFIX,
        cache_dir: str | None = None,
        source_uri: Callable[[date], str] | None = None,
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
        option_roots: Iterable[str] | None = None,
        cache_roots: Iterable[str] | None = None,
        exercise_style: str = "american",
    ) -> ChainSnapshot | None:
        """Reconstruct ``ticker``'s NBBO chain at instant ``ts`` (UTC-naive).

        ``option_roots`` are the OCC roots that belong to this asset (defaults to
        ``[ticker]``); index options need several — SPX trades as both ``SPX``
        (AM-settled monthlies) and ``SPXW`` (PM-settled weeklies/EOM), likewise
        ``NDX``/``NDXP`` and ``RUT``/``RUTW``. ``cache_roots`` is the full
        watchlist of roots to co-cache from the same daily scan (defaults to this
        asset's roots). ``expiries`` restricts the rungs; ``exercise_style`` is
        ``"european"`` for index options, ``"american"`` for single names / ETFs.
        Returns None when the day's file has no usable two-sided quotes.
        """
        day = ts.date()
        roots = [r.upper() for r in (option_roots or [ticker])]
        roots_set = set(roots)
        scan_roots = sorted(set(r.upper() for r in (cache_roots or roots)) | roots_set)
        target_ns = _to_ns(ts)
        nbbos = self._reduced_bars(day, scan_roots, target_ns)
        wanted = set(expiries) if expiries else None
        upper = ticker.upper()
        quotes: list[OptionQuote] = []
        for n in nbbos:
            try:
                occ = parse_option_symbol(n.ticker)
            except ValueError:
                continue
            if occ.underlying not in roots_set:
                continue
            if wanted is not None and occ.expiry not in wanted:
                continue
            quotes.append(
                OptionQuote(
                    ticker=upper,
                    expiry=occ.expiry,
                    strike=occ.strike,
                    call_put=occ.call_put,
                    bid=n.bid,
                    ask=n.ask,
                    last=None,
                    volume=None,
                    open_interest=n.ask_size,  # carry a size hint (ask depth)
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
            exercise_style=exercise_style,
        )

    # ------------------------------------------------------------- internals
    def _uri(self, day: date) -> str:
        """S3 URI of the day's quotes file (or the injected fixture)."""
        if self._source_uri is not None:
            return self._source_uri(day)
        return (
            f"s3://{self.bucket}/{self.prefix}/{PRODUCT}/"
            f"{day:%Y}/{day:%m}/{day:%Y-%m-%d}.csv.gz"
        )

    def _cache_path(self, day: date, roots: list[str], target_ns: int) -> str | None:
        """Collapsed-Parquet path, keyed by day + root set + target instant."""
        if self.cache_dir is None:
            return None
        tag = hashlib.sha1(
            (",".join(sorted(roots)) + f"@{target_ns}").encode()
        ).hexdigest()[:12]
        return os.path.join(
            self.cache_dir, f"{PRODUCT}_{day:%Y-%m-%d}_{tag}.parquet"
        )

    def _reduce_to_cache(self, day: date, roots: list[str], target_ns: int) -> str:
        """Scan the day's quotes once, keep our roots' NBBO at-or-before the target
        instant (last per contract), and materialize that tiny set to Parquet.
        Returns the Parquet path (or runs the reduction inline when no cache dir)."""
        cache = self._cache_path(day, roots, target_ns)
        select = (
            "SELECT ticker, bid_price, ask_price, bid_size, ask_size, sip_timestamp "
            "FROM read_csv_auto(?, sample_size=2000) "
            f"WHERE sip_timestamp <= {target_ns} AND {_root_filter('ticker', roots)} "
            "QUALIFY row_number() OVER "
            "(PARTITION BY ticker ORDER BY sip_timestamp DESC) = 1"
        )
        if cache is None:
            return select  # inline mode: chain_at runs the SELECT directly
        if not os.path.exists(cache):
            os.makedirs(self.cache_dir, exist_ok=True)
            con = self._connect()
            try:
                con.execute(
                    f"COPY ({select}) TO '{cache}' (FORMAT PARQUET)", [self._uri(day)]
                )
            finally:
                con.close()
        return cache

    def _reduced_bars(self, day: date, roots: list[str], target_ns: int) -> list[_Nbbo]:
        """The collapsed NBBO rows for the watchlist at the target instant."""
        source = self._reduce_to_cache(day, roots, target_ns)
        con = self._connect()
        try:
            if source.endswith(".parquet"):
                rows = con.execute(
                    "SELECT ticker, bid_price, ask_price, bid_size, ask_size, "
                    "sip_timestamp FROM read_parquet(?)", [source]
                ).fetchall()
            else:  # inline mode: source IS the SELECT, parameter is the day URI
                rows = con.execute(source, [self._uri(day)]).fetchall()
        finally:
            con.close()
        return [
            _Nbbo(
                ticker=str(r[0]),
                bid=_pos_or_none(r[1]),
                ask=_pos_or_none(r[2]),
                bid_size=int_or_none(r[3]),
                ask_size=int_or_none(r[4]),
                sip_ns=int(r[5]),
            )
            for r in rows
        ]

    def _connect(self):
        """A DuckDB connection with httpfs configured for the flat-file bucket."""
        import duckdb

        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        if not self._source_uri:
            host, use_ssl = _split_endpoint(self.endpoint)
            con.execute("SET s3_region='us-east-1';")
            con.execute("SET s3_url_style='path';")
            con.execute(f"SET s3_use_ssl={'true' if use_ssl else 'false'};")
            con.execute("SET s3_endpoint=?;", [host])
            con.execute("SET s3_access_key_id=?;", [self.access_key])
            con.execute("SET s3_secret_access_key=?;", [self.secret])
        return con


def _split_endpoint(endpoint: str) -> tuple[str, bool]:
    """Normalize a configured endpoint to DuckDB's (bare host, use_ssl)."""
    ep = endpoint.strip()
    if ep.startswith("http://"):
        return ep[len("http://"):].rstrip("/"), False
    if ep.startswith("https://"):
        return ep[len("https://"):].rstrip("/"), True
    return ep.rstrip("/"), True


def _root_filter(column: str, roots: list[str]) -> str:
    """SQL predicate matching ``O:<root>`` for any watchlist root (exact root —
    ``O:SPY`` then the 6-digit date, so it never matches ``O:SPYG``)."""
    import re

    alt = "|".join(re.escape(r.upper()) for r in roots)
    return f"regexp_matches({column}, '^O:({alt})[0-9]{{6}}[CP]')"


def _to_ns(ts: datetime) -> int:
    """UTC-naive datetime → nanoseconds since the Unix epoch (the SIP clock)."""
    return int(ts.replace(tzinfo=timezone.utc).timestamp() * 1_000_000_000)


def _pos_or_none(value) -> float | None:
    """A strictly-positive price, else None (a 0 bid means 'no bid')."""
    px = price_or_none(value)
    if px is None or px <= 0.0:
        return None
    return px


def _parity_spot(quotes: list[OptionQuote]) -> float | None:
    """Spot proxy = nearest-expiry forward from put-call parity on the mids."""
    import numpy as np

    by_exp: dict[date, dict[float, dict[str, float]]] = {}
    for q in quotes:
        if q.mid is None:
            continue
        by_exp.setdefault(q.expiry, {}).setdefault(q.strike, {})[q.call_put] = q.mid
    for expiry in sorted(by_exp):
        pairs = [(k, v["C"], v["P"]) for k, v in by_exp[expiry].items() if "C" in v and "P" in v]
        if len(pairs) < 3:
            continue
        strikes = np.array([p[0] for p in pairs], dtype=float)
        y = np.array([p[1] - p[2] for p in pairs], dtype=float)
        (a, b), *_ = np.linalg.lstsq(
            np.column_stack([np.ones_like(strikes), strikes]), y, rcond=None
        )
        discount = -float(b)
        if discount > 0.0:
            return float(a) / discount
    return None
