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
import tempfile
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
        return self._build_snapshot(ticker, roots_set, wanted, ts, nbbos, exercise_style)

    def chains_at(
        self,
        ticker: str,
        expiries: list[date] | None,
        instants: list[datetime],
        option_roots: Iterable[str] | None = None,
        cache_roots: Iterable[str] | None = None,
        exercise_style: str = "american",
    ) -> dict[datetime, ChainSnapshot | None]:
        """Reconstruct the chain at SEVERAL instants of ONE day, one scan total.

        The intraday-capture entry point (R2 0DTE): the day's quotes file is
        the OPRA firehose and gzip has no random access, so N ``chain_at``
        calls would stream it N times. This collapses to "the NBBO at-or-
        before EACH target instant per contract" in a single scan/COPY (one
        extra Parquet column, ``target_ns``) and assembles one snapshot per
        instant. Instants must all fall on the same trading day.
        """
        if not instants:
            return {}
        days = {t.date() for t in instants}
        if len(days) != 1:
            raise ValueError("all instants must fall on one day (one file scan)")
        day = next(iter(days))
        roots = [r.upper() for r in (option_roots or [ticker])]
        roots_set = set(roots)
        scan_roots = sorted(set(r.upper() for r in (cache_roots or roots)) | roots_set)
        targets = sorted({_to_ns(t) for t in instants})
        by_target = self._reduced_bars_multi(day, scan_roots, targets)
        wanted = set(expiries) if expiries else None
        return {
            ts: self._build_snapshot(
                ticker, roots_set, wanted, ts, by_target.get(_to_ns(ts), []),
                exercise_style,
            )
            for ts in instants
        }

    def _build_snapshot(
        self, ticker: str, roots_set: set[str], wanted: set[date] | None,
        ts: datetime, nbbos: list["_Nbbo"], exercise_style: str,
    ) -> ChainSnapshot | None:
        """Collapsed NBBO rows -> one ChainSnapshot (None when unusable)."""
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
        # Re-scan when the cache is absent OR a 0-byte orphan: a kill mid-COPY (this
        # is a long-running, windowed job) leaves an empty parquet; "exists -> skip"
        # would then read no quotes and silently drop that day. Treat empty as absent.
        if not os.path.exists(cache) or os.path.getsize(cache) == 0:
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

    # ------------------------------------------------- multi-instant reduction
    def _multi_cache_path(self, day: date, roots: list[str], targets: list[int]) -> str | None:
        """Parquet path for the multi-instant reduction (own tag namespace)."""
        if self.cache_dir is None:
            return None
        tag = hashlib.sha1(
            (",".join(sorted(roots)) + "@multi:" + ",".join(map(str, targets))).encode()
        ).hexdigest()[:12]
        return os.path.join(self.cache_dir, f"{PRODUCT}_{day:%Y-%m-%d}_{tag}.parquet")

    def _reduced_bars_multi(
        self, day: date, roots: list[str], targets: list[int]
    ) -> dict[int, list[_Nbbo]]:
        """Per-target collapsed NBBO rows, from ONE scan of the day's file.

        The join against a VALUES list of target instants multiplies candidate
        rows before the QUALIFY, but the root filter prunes the firehose first
        and the reduction still streams — one S3 pass however many instants."""
        values = ", ".join(f"({t})" for t in targets)
        select = (
            "SELECT t.target_ns, q.ticker, q.bid_price, q.ask_price, "
            "q.bid_size, q.ask_size, q.sip_timestamp "
            "FROM read_csv_auto(?, sample_size=2000) q "
            f"JOIN (VALUES {values}) t(target_ns) ON q.sip_timestamp <= t.target_ns "
            f"WHERE {_root_filter('q.ticker', roots)} "
            "QUALIFY row_number() OVER "
            "(PARTITION BY t.target_ns, q.ticker ORDER BY q.sip_timestamp DESC) = 1"
        )
        cache = self._multi_cache_path(day, roots, targets)
        con = self._connect()
        try:
            if cache is None:
                rows = con.execute(select, [self._uri(day)]).fetchall()
            else:
                if not os.path.exists(cache) or os.path.getsize(cache) == 0:
                    os.makedirs(self.cache_dir, exist_ok=True)
                    con.execute(
                        f"COPY ({select}) TO '{cache}' (FORMAT PARQUET)", [self._uri(day)]
                    )
                rows = con.execute(
                    "SELECT target_ns, ticker, bid_price, ask_price, bid_size, "
                    "ask_size, sip_timestamp FROM read_parquet(?)", [cache]
                ).fetchall()
        finally:
            con.close()
        out: dict[int, list[_Nbbo]] = {}
        for r in rows:
            out.setdefault(int(r[0]), []).append(
                _Nbbo(
                    ticker=str(r[1]),
                    bid=_pos_or_none(r[2]),
                    ask=_pos_or_none(r[3]),
                    bid_size=int_or_none(r[4]),
                    ask_size=int_or_none(r[5]),
                    sip_ns=int(r[6]),
                )
            )
        return out

    def _connect(self):
        """A DuckDB connection with httpfs configured for the flat-file bucket."""
        import duckdb

        con = duckdb.connect()
        # OOM guard (2026-07-11 probe died: 'Out of Memory Error: Allocation
        # failure'): DuckDB's default memory_limit is 80% of TOTAL RAM, far
        # beyond what this box has physically free, so the multi-instant
        # join + QUALIFY window hit a raw allocation failure before DuckDB
        # ever considered spilling. Cap the budget at something the box can
        # actually deliver and point operator spill at the (roomy) disk.
        mem = os.environ.get("VOLFIT_DUCKDB_MEM", "4GB")
        con.execute(f"SET memory_limit='{mem}';")
        spill = os.path.join(self.cache_dir or tempfile.gettempdir(), "duckdb_spill")
        os.makedirs(spill, exist_ok=True)
        con.execute("SET temp_directory=?;", [spill])
        con.execute("SET max_temp_directory_size='100GB';")
        con.execute("INSTALL httpfs; LOAD httpfs;")
        if not self._source_uri:
            # The day file is a multi-GB gz STREAM: the 30 s default HTTP
            # timeout aborts on any stall (seen live: 'Timeout was reached'
            # mid-scan on a loaded box). Allow long stalls + a few retries.
            # Retries must also RIDE OUT a transient DNS/network outage —
            # the 2026-07-13 probe streamed for hours, then died with
            # 'Could not resolve hostname' because the default retry
            # cadence (~100 ms apart) burns every attempt inside the same
            # blip. Space them out: 10s, 20s, 40s, ... (~10 min total).
            con.execute("SET http_timeout=1800000;")  # 30 min, milliseconds
            con.execute("SET http_retries=6;")
            con.execute("SET http_retry_wait_ms=10000;")
            con.execute("SET http_retry_backoff=2;")
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
