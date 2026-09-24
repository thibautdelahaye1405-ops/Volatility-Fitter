"""Bloomberg option-chain provider via xbbg (ROADMAP Phase 3, real market data).

Design intent: `BloombergProvider` implements the `OptionChainProvider`
contract (volfit.data.provider) on top of the `xbbg` convenience wrapper around
the Bloomberg Python API, so the rest of the stack — storage, forwards,
de-Americanization, calibration, API — runs unchanged on Bloomberg data. It is
the most complete live source: real bid/ask/last/volume/OI, spot, the genuine
American/European exercise flag, and a dividend schedule for the discrete-
dividend forward model.

xbbg surface relied on (confirmed live against an open Terminal):
- the chain LISTING — ``bds(security, "OPT_CHAIN")`` (monthlies / LEAPS, both
  sides, keyed) + one ``bds(security, "CHAIN_TICKERS", overrides=...)`` per
  series (weeklies + dailies, quarterlies; calls only, puts mirrored) — lives
  in volfit.data.bloomberg_listing, cached per ET EXCHANGE DAY and on disk;
- ``blp.bdp(securities, fields)`` -> long/tidy frame (ticker/field/value), all
  values as strings — coerced via volfit.data.fieldmap;
- ``blp.bds(security, "DVD_HIST_ALL")`` -> declared dividend rows (Ex-Date,
  Dividend Amount, Dividend Frequency, Dividend Type) for dividend import.

Robustness / conventions:
- xbbg is imported *lazily* (only when a real call is made), so this module
  imports fine without it; tests inject a fake ``blp_module`` and stay offline.
- Frames are read column-wise (volfit.data.bloomberg_parse.columns) because the
  xbbg narwhals frames lack ``index``/``itertuples``.
- ``available_expiries`` parses the descriptor strings (cheap, the listing, no
  per-contract ``bdp``); ``fetch_chain`` only ``bdp``s the *selected* expiries'
  contracts, windowed per expiry to the fittable strike band (volfit.data.
  strike_window — a 2-day rung costs ~30 % of the ladder, a 1-year rung the
  wide band), and requests BID/ASK only (volfit.data.bloomberg_fields: the
  exercise style is one hit per ticker per day, OI / volume / last are the
  explicit ``enrich_reference``). ``call_stats()`` reports the hits.
- Missing/zero price fields map to ``None`` (volfit.data.types convention).

Real-time streaming (quota-free): ``BloombergStreamingMixin`` (volfit.data.
bloomberg_live) adds the ``start_streaming``/``option_tickers``/... contract
AppState drives; while a ``//blp/mktdata`` subscription book is live (volfit.
data.bloomberg_stream), ``spot`` and ``fetch_chain(live)`` are served from it
and issue NO ``bdp`` — BOOK FIRST: a fetch waits up to ``book_first_wait`` for
the paint and the selection's coverage before the metered fallback, and never
falls back with ``book_only=True``.
"""

from __future__ import annotations

import threading
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from volfit.data.bloomberg_parse import (
    ParsedOption,
    as_date,
    pivot_bdp,
    project_dividends,
    quiet_xbbg_logs,
    records,
    session_connected,
    short_blp_reason,
)
from volfit.data.bloomberg_fields import BloombergReferenceMixin, MeteredBlp
from volfit.data.bloomberg_history import available_history as _available_history
from volfit.data.bloomberg_history import fetch_eod as _fetch_eod
from volfit.data.bloomberg_listing import (  # noqa: F401 — CHAIN_* re-exported for callers
    CHAIN_ALL_EXPIRIES,
    CHAIN_POINTS,
    CHAIN_SERIES,
    Listing,
    drop_listings,
    list_chain,
    load_listing,
    parse_chain_frame,
    save_listing,
)
from volfit.data.bloomberg_listing import exchange_day as _exchange_day_et
from volfit.data.bloomberg_live import BloombergStreamingMixin
from volfit.data.bloomberg_search import instrument_search
from volfit.data.cache_dir import cache_dir
from volfit.data.dividends import Dividend
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.bloomberg_roots import one_root_per_date, parent_root
from volfit.data.expiry_time import ExpirySettlement, default_settlement, session_close_utc
from volfit.data.roots import is_index_root, is_intl_index_root, normalize_root
from volfit.data.provider import AsOf, OptionChainProvider, SymbolMatch
from volfit.data.strike_window import DEFAULT_SIGMA_REF, inside, strike_bounds
from volfit.data.types import ChainSnapshot

import logging

logger = logging.getLogger(__name__)

#: Seconds a live fetch waits, while streaming, for the book to paint the
#: underlying AND cover the selection before the metered fallback (a fresh
#: start paints within ~1 s; a selection edit is resubscribed on the next
#: scheduler tick, <= 1 s). Constructor ``book_first_wait``.
BOOK_FIRST_WAIT = 5.0

#: Back-compat alias — tests and older callers import the parser from here.
_parse_chain_frame = parse_chain_frame

#: Bloomberg "yellow key" asset-class words that complete a security string
#: ("SPX Index", "SAP GY Equity"). Stored canonically (title-case) and indexed
#: by their upper-cased form: the rest of the app uppercases every symbol, so a
#: full security arrives as "SPX INDEX" / "SAP GY EQUITY" and the suffix must be
#: re-cased before it is sent to Bloomberg (the API is case-sensitive on the
#: yellow key). Covers the asset classes that list options + the common ones.
_ASSET_CLASSES = ("Equity", "Index", "Curncy", "Comdty", "Corp", "Govt", "Mtge", "Pfd")
_ASSET_CLASS_BY_UPPER = {c.upper(): c for c in _ASSET_CLASSES}

def _default_blp():
    """Resolve ``xbbg.blp`` on first use; clear error if xbbg is not installed."""
    try:
        from xbbg import blp
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "BloombergProvider requires the 'xbbg' package (and a running "
            "Bloomberg Terminal): pip install xbbg blpapi"
        ) from exc
    quiet_xbbg_logs()  # silence the pyo3 engine's per-failure WARN spam
    return blp


class BloombergProvider(BloombergStreamingMixin, BloombergReferenceMixin, OptionChainProvider):
    """Live option chains for a watchlist via Bloomberg (xbbg + blpapi streaming).

    Parameters
    ----------
    tickers      : the watchlist; `list_tickers` returns exactly this list.
    yellow_key   : suffix appended to bare tickers to form a Bloomberg security
                   ("SPY" -> "SPY US Equity"). Tickers already carrying a yellow
                   key (e.g. "SPX Index") are passed through untouched.
    max_days     : drop expiries further out than this (and already-expired).
    blp_module   : an object exposing ``bds(security, field)`` and
                   ``bdp(securities, fields)`` like ``xbbg.blp``; defaults to the
                   lazily-imported real module, injectable for offline tests.
    strike_window: which strikes a live fetch / the stream carries — ``"auto"``
                   (default) = the shared per-expiry rule (volfit.data.
                   strike_window: |ln K/S| <= 4·sigma_ref·sqrt(T), floored and
                   capped — contains everything the quote prep keeps, so the
                   fit is byte-identical); a ``(lo, hi)`` tuple = the legacy
                   uniform band in units of spot; None = the whole ladder.
    window_sigma_ref : the reference vol the auto window is sized for (1.0).
    stream_interval / max_subscriptions / stream_session_factory / stream_host /
    stream_port  : the ``//blp/mktdata`` streaming knobs (volfit.data.
                   bloomberg_live): conflation seconds, concurrent-subscription
                   budget, injectable session (tests), DAPI endpoint override.
    rotation_slots : slots reserved for the BUCKET ROTATION of the over-cap
                   contracts (volfit.data.bloomberg_rotation; None = env
                   ``VOLFIT_BBG_ROTATION_SLOTS``, default 300, clamped to a
                   quarter of the cap; 0 = off — over-cap contracts unquoted).
    book_first_wait : seconds a live fetch waits for the streaming book (paint +
                   coverage) before the metered fallback (BOOK_FIRST_WAIT).
    book_only    : while streaming, NEVER fall back to a metered quote pull —
                   an uncovered fetch raises instead (zero quote hits, ever).
    chain_series : the CHAIN_TICKERS series requested on top of OPT_CHAIN's
                   monthlies (bloomberg_listing; default CHAIN_SERIES = weeklies
                   + quarterlies). () = OPT_CHAIN only, the legacy monthly ladder.
    listing_dir  : where the per-exchange-day listings persist — ``"auto"`` =
                   ``cache_dir("bloomberg")`` when the REAL xbbg is used (a test
                   fake never touches the shared cache); a path; None = memory.
    exchange_day : the ET exchange-day clock (tests inject a fake day).
    """

    def __init__(
        self,
        tickers: Sequence[str],
        yellow_key: str = "US Equity",
        max_days: int = 730,
        blp_module: object | None = None,
        strike_window: tuple[float, float] | str | None = "auto",
        window_sigma_ref: float = DEFAULT_SIGMA_REF,
        stream_interval: float | None = 1.0,
        max_subscriptions: int = 3000,
        stream_session_factory=None,
        stream_host: str | None = None,
        stream_port: int | None = None,
        book_first_wait: float = BOOK_FIRST_WAIT,
        book_only: bool = False,
        chain_series: Sequence[str] = CHAIN_SERIES,
        listing_dir: str | Path | None = "auto",
        exchange_day: Callable[[], date] | None = None,
        rotation_slots: int | None = None,
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self.yellow_key = yellow_key
        self.max_days = max_days
        self._blp = blp_module
        self._exchange_day = exchange_day if exchange_day is not None else _exchange_day_et
        self._init_reference()
        self._init_streaming(
            stream_interval, max_subscriptions, stream_session_factory, stream_host, stream_port,
            rotation_slots=rotation_slots,
        )
        #: The strike window of a live fetch and of the stream plan (see the
        #: class docstring): every listed strike is a separately-METERED
        #: Bloomberg security / a subscription slot, and the far tails never
        #: reach a fit, so the window cuts both by a large factor on the short
        #: rungs while containing every quote the prep keeps.
        self.strike_window = strike_window
        self.window_sigma_ref = window_sigma_ref
        self.book_first_wait = max(0.0, float(book_first_wait))
        self.book_only = bool(book_only)
        self.chain_series = tuple(chain_series)
        if listing_dir == "auto":
            listing_dir = cache_dir("bloomberg") if blp_module is None else None
        self._listing_dir: Path | None = Path(listing_dir) if listing_dir is not None else None
        #: ticker -> the day's Listing (contracts + roots); re-listed on a new
        #: ET exchange day (see ``_chain``).
        self._chain_cache: dict[str, Listing] = {}
        #: ticker -> {expiry: the option root kept for that date} (bloomberg_roots:
        #: one root per date; the settlement convention reads it).
        self._roots_cache: dict[str, dict[date, str]] = {}
        self._history_cache: dict[str, list[date]] = {}
        #: Lazily-opened blpapi session for the instrument-search service, reused
        #: across searches and guarded so concurrent searches serialize.
        self._search_session = None
        self._search_lock = threading.Lock()
        #: Reason of the last *connected-but-refused* real request (entitlement /
        #: workflow review / daily limit), or None after any success. Lets the
        #: status light report a real account-side gate WITHOUT feed_status itself
        #: issuing a billable probe on every poll (the 30 s Data Source refresh
        #: must never burn the Bloomberg daily reference-data quota). Set by
        #: ``_record`` from the on-demand fetch paths only.
        self._last_error: str | None = None

    # -- plumbing ------------------------------------------------------------

    def _blp_module(self):
        """The (lazily-imported) xbbg module wrapped in the hit meter, so every
        reference request of every path counts toward ``call_stats``."""
        if self._blp is None:
            self._blp = _default_blp()
        if not isinstance(self._blp, MeteredBlp):
            self._blp = MeteredBlp(self._blp, self._meter)
        return self._blp

    def _security(self, ticker: str) -> str:
        """Full Bloomberg security string for an underlying ticker.

        Handles the three shapes the universe layer can hand us (it uppercases
        every symbol, so a yellow key arrives upper-cased and must be re-cased):

        * **already a full security** — the last token is a yellow-key asset
          class ("SPX INDEX", "SAP GY EQUITY"): re-case the suffix and pass it
          through ("SPX Index", "SAP GY Equity") so non-US names and indices
          work end-to-end;
        * **exchange-coded equity shorthand** — a root plus a 2-letter market
          code but no asset class ("SAP GY", "VOD LN", "7203 JT"): append
          " Equity" (the asset class is implied by the exchange code);
        * **bare index root** — a known cash-index root ("SPX", "NDX", "VIX",
          the universe's portable spelling, volfit.data.symbols) or a known
          non-US index root in its Bloomberg spelling ("SX5E", "DAX", "UKX",
          volfit.data.roots.INTL_INDEX_ROOTS): " Index";
        * **bare ticker** — a single token ("SPY", "NVDA"): append the default
          yellow key (``yellow_key``, "US Equity"), i.e. the US listing.
        """
        t = ticker.strip()
        if not t:
            return t
        parts = t.split()
        asset_class = _ASSET_CLASS_BY_UPPER.get(parts[-1].upper())
        if asset_class is not None:  # full security: re-case the yellow key
            return " ".join(parts[:-1] + [asset_class])
        if len(parts) >= 2:  # exchange-coded equity (root + market code)
            return f"{t} Equity"
        if is_index_root(t) or is_intl_index_root(t):  # bare index root -> "SPX Index" / "SX5E Index"
            return f"{normalize_root(t)} Index"
        return f"{t} {self.yellow_key}"

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def _record(self, exc: Exception | None) -> None:
        """Remember the outcome of a real (on-demand) Bloomberg request so the
        status light can report a connected-but-refused account — entitlement,
        *workflow review needed*, or *daily capacity reached* — without
        feed_status issuing its own billable probe. Cleared on any success; a
        *disconnected* failure is left to feed_status to report as "no Terminal".
        """
        if exc is None:
            self._last_error = None
        elif isinstance(exc, ValueError):
            return  # our own "no contracts / no spot for this selection" — not a feed refusal
        elif session_connected(self._blp_module()):
            self._last_error = short_blp_reason(exc)

    def feed_status(self) -> tuple[str, str]:
        """Liveness for the Data Source selector — a CHEAP, quota-free probe.

        Routine status polling (the UI re-checks every 30 s) must never consume
        the Bloomberg daily reference-data quota, so this issues NO ``bdp``/``bds``
        request: it reads the blpapi session state (``is_connected()``) and the
        cached outcome of the last real fetch. States:

        - **red "no Terminal"** — no blpapi session (xbbg not installed, Terminal
          closed / not logged in);
        - **red "<reason>"** — the session is connected but the last on-demand
          request was refused (entitlement / *workflow review needed* / daily
          limit); the actual cause is surfaced so the user knows it is an
          account-side gate, not a broken install;
        - **green** — session connected and no outstanding refusal (real-time).

        The real data-flow / entitlement state is established by the on-demand
        fetches themselves (which call ``_record``), not by a status poll.
        """
        tickers = self.list_tickers()
        if not tickers:
            return ("red", "no tickers configured")
        try:
            blp = self._blp_module()
        except ImportError:
            return ("red", "xbbg not installed")
        if not session_connected(blp):
            return ("red", "no Terminal")
        streaming = self._stream_status()  # the live //blp/mktdata book, if any
        if streaming is not None:
            level, detail = streaming
            return (level, detail if level == "red" else detail + self._hits_suffix())
        if self._last_error is not None:
            return ("red", self._last_error)
        return ("green", "real-time (Terminal)" + self._hits_suffix())

    # -- symbol search -------------------------------------------------------

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Free-text symbol/company search via Bloomberg's instruments service.

        Resolves "Nvidia" or "NVDA" to Bloomberg securities like
        "NVDA US Equity". Any failure (no blpapi, no Terminal, service down)
        degrades to the base substring/echo search so the picker still works.
        """
        q = query.strip()
        if not q:
            return []
        try:
            import blpapi
        except ImportError:
            return super().search_symbols(query, limit)
        with self._search_lock:
            try:
                return self._instrument_search(blpapi, q, limit)
            except Exception:
                if self._search_session is not None:  # drop a possibly-dead session
                    try:
                        self._search_session.stop()
                    except Exception:
                        pass
                    self._search_session = None
                return super().search_symbols(query, limit)

    def _instrument_search(self, blpapi, query: str, limit: int) -> list[SymbolMatch]:
        """One instrumentListRequest against //blp/instruments (call under lock);
        the body lives in bloomberg_search to keep this module under 400 lines."""
        return instrument_search(self, blpapi, query, limit)

    # -- chain enumeration (cheap, descriptor-only) --------------------------

    def _chain(self, ticker: str) -> list[ParsedOption]:
        """Every listed contract of a ticker for TODAY's ET exchange day —
        memory first, then the on-disk listing (``listing_dir``), then the
        three ``bds`` of volfit.data.bloomberg_listing. A ladder changes once a
        day (new dailies list overnight), so a listing is re-requested exactly
        once per day, or on ``refresh_contracts`` / ``refresh_chain_cache``.

        The Terminal's answer then keeps one option root per expiry date
        (bloomberg_roots: a Eurex weekly and daily, or SPX and SPXW, listing
        the same Friday are different instruments — keeping both stacks two
        smiles on one slice); the kept contracts + roots are what persists."""
        key = ticker.upper()
        day = self._exchange_day()
        hit = self._chain_cache.get(key)
        if hit is None or hit.day != day:
            hit = load_listing(self._listing_dir, key, day)
            if hit is None:
                hit = self._list_from_terminal(key, day)
            self._chain_cache[key] = hit
        self._roots_cache[key] = hit.roots
        return hit.contracts

    def _list_from_terminal(self, key: str, day: date) -> Listing:
        """The three-bds listing + the root selection, persisted for ``day``."""
        security = self._security(key)
        try:
            parsed = list_chain(self._blp_module(), security, self.chain_series)
        except Exception as exc:
            # The chain listing is an on-demand request too: an account-side
            # refusal here (LIMIT / workflow review, 2026-09-10 — every ticker
            # of a restored universe wore a yellow pill while the light stayed
            # green) must reach the Data Source light like a quote refusal.
            self._record(exc)
            raise
        selection = one_root_per_date(parsed, parent_root(security), self._probe_open_interest)
        for note in selection.dropped:
            logger.info("%s chain — one root per date: %s", key, note)
        listing = Listing(day=day, contracts=selection.contracts, roots=selection.roots)
        save_listing(self._listing_dir, key, listing)
        self._record(None)  # a listing that answered clears a remembered refusal
        return listing

    def _probe_open_interest(self, securities: list[str]) -> dict[str, int]:
        """OPEN_INT of a few representative contracts (one bdp) — the liquidity
        vote of ``one_root_per_date`` for a date two sibling roots list."""
        pivot = pivot_bdp(self._blp_module().bdp(securities, ["OPEN_INT"]))
        out: dict[str, int] = {}
        for s in securities:
            oi = int_or_none(pivot.get(s, {}).get("OPEN_INT"))
            if oi is not None:
                out[s] = oi
        return out

    def _settlement(self, ticker: str, expiries) -> dict[date, ExpirySettlement]:
        """Per-expiry settlement records, each under the root that LISTS the
        date (``_roots_cache``: SPX AM on the monthlies, SPXW PM on the
        weeklies); the ticker's own root where the chain was never listed."""
        roots = self._roots_cache.get(ticker.upper(), {})
        return {e: default_settlement(e, roots.get(e, ticker)) for e in sorted(set(expiries))}

    def refresh_chain_cache(self, ticker: str | None = None) -> None:
        """Drop the cached listing(s) — memory AND the on-disk file(s) — so the
        next call re-lists from the Terminal (explicit invalidation inside the
        exchange day, e.g. a ladder the Terminal amended)."""
        if ticker is None:
            self._chain_cache.clear()
            drop_listings(self._listing_dir)
        else:
            self._chain_cache.pop(ticker.upper(), None)
            drop_listings(self._listing_dir, ticker.upper())

    def refresh_contracts(self) -> None:
        """Every provider's day-roll hook (same name as Massive's): forget every
        listing (memory + disk), the history ladders and the day's exercise-
        style probes, so the next request re-lists for the new exchange day."""
        self.refresh_chain_cache()
        self._history_cache.clear()
        self._style_day.clear()

    def _keep_expiry(self, expiry: date, today: date) -> bool:
        """Inside ``max_days``; TODAY's expiry only while its session is open
        (a 0DTE is a live node until the close)."""
        days = (expiry - today).days
        if days > self.max_days:
            return False
        if days > 0:
            return True
        return days == 0 and datetime.now(timezone.utc).replace(tzinfo=None) < session_close_utc(today)

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed expiries inside (0, max_days] (+ today's while its session
        is open), parsed from the chain contracts."""
        today = date.today()
        return sorted({p.expiry for p in self._chain(ticker) if self._keep_expiry(p.expiry, today)})

    # -- as-of history -------------------------------------------------------

    def historical_modes(self) -> set[str]:
        """Bloomberg serves live, prior-close and any past trading day (EOD)."""
        return {"live", "prev_close", "eod"}

    def available_history(self, ticker: str) -> list[date]:
        """Last ~30 trading days the Terminal can serve an EOD chain for (cached)."""
        key = ticker.upper()
        if key not in self._history_cache:
            self._history_cache[key] = _available_history(
                self._blp_module(), self._security(ticker)
            )
        return list(self._history_cache[key])

    # -- spot ----------------------------------------------------------------

    def _spot(self, ticker: str) -> float:
        """Last price (PX_LAST) for the underlying; ValueError if unavailable."""
        blp = self._blp_module()
        security = self._security(ticker)
        try:
            pivot = pivot_bdp(blp.bdp(security, "PX_LAST"))
        except Exception as exc:
            self._record(exc)  # a refused PX_LAST is a real refusal for the light
            raise
        self._record(None)  # ...and an answered one clears a stale refusal
        value = price_or_none(pivot.get(security, {}).get("PX_LAST"))
        if value is None:
            raise ValueError(f"could not determine spot price for {ticker!r}")
        return value

    def spot(self, ticker: str, expiries: list[date] | None = None) -> float:
        """Cheap underlying spot — ONE PX_LAST reference hit on the underlying.

        Overrides the base contract, whose default re-fetches the WHOLE option
        chain just to read its spot. The Auto-update spot probe (autoUpdate="spot")
        probes this every few seconds, so the default would have re-``bdp``ed
        hundreds–thousands of option contracts per poll and torched the Bloomberg
        daily reference-data quota. One underlying price per poll instead — and
        ZERO while the subscription book streams (the underlying is subscribed)."""
        live = self._book_spot(ticker) if self.is_streaming() else None
        return live if live is not None else self._spot(ticker)

    def book_spot(self, ticker: str, expiries: list[date] | None = None) -> float | None:
        """Book-only spot (no bdp, no warm-up wait): the underlying's last tick
        off the ``//blp/mktdata`` book, or None unless streaming and painted."""
        if not self.is_streaming():
            return None
        return self._book_spot(ticker, wait=0.0)

    # -- chain ---------------------------------------------------------------

    def _select_contracts(
        self, ticker: str, expiries: list[date] | None
    ) -> list[ParsedOption]:
        """Parsed contracts for the requested expiries (or all within max_days)."""
        today = date.today()
        parsed = self._chain(ticker)
        if expiries is None:
            wanted = {p.expiry for p in parsed if self._keep_expiry(p.expiry, today)}
        else:
            wanted = set(expiries)
        contracts = [p for p in parsed if p.expiry in wanted]
        if not contracts:
            raise ValueError(
                f"no listed options for {ticker!r} within the requested expiries"
            )
        return contracts

    def fetch_chain(
        self,
        ticker: str,
        expiries: list[date] | None = None,
        as_of: AsOf | None = None,
    ) -> ChainSnapshot:
        """Live (None/`live`) NBBO chain, or a historical EOD chain for a past
        trading day (`eod`) / the prior close (`prev_close`).

        This is the on-demand fetch path, so its outcome drives the status light
        (``_record``): a success clears any cached refusal, a connected-but-refused
        failure (entitlement / daily limit) is remembered so the light can show it
        without a separate billable probe."""
        try:
            contracts = self._select_contracts(ticker, expiries)
            if as_of is not None and as_of.mode != "live":
                on = as_of.on if as_of.mode == "eod" else self._latest_history(ticker)
                if on is None:
                    raise ValueError(f"no historical close available for {ticker!r}")
                style = "european" if self._security(ticker).endswith(" Index") else "american"
                snap = _fetch_eod(
                    self._blp_module(), ticker, self._security(ticker), contracts, on, style,
                    roots=self._roots_cache.get(ticker.upper()),
                )
            else:
                # Streaming: BOOK FIRST — wait (book_first_wait) for the paint and
                # the selection's coverage, then the metered reference pull is the
                # fallback (never with book_only: an uncovered fetch raises).
                snap = self._chain_from_book_first(ticker, expiries) if self.is_streaming() else None
                if snap is None:
                    if self.book_only and self.is_streaming():
                        raise ValueError(
                            f"{ticker}: the streaming book does not cover this selection yet "
                            "and book_only forbids a metered pull — retry once it is subscribed"
                        )
                    snap = self._fetch_live(ticker, contracts)
        except Exception as exc:
            self._record(exc)
            raise
        self._record(None)
        return snap

    def _latest_history(self, ticker: str) -> date | None:
        """Most recent trading day available for EOD (for prev_close)."""
        history = self.available_history(ticker)
        return history[-1] if history else None

    def _window_contracts(
        self, contracts: list[ParsedOption], spot: float | None
    ) -> list[ParsedOption]:
        """The contracts a live fetch / the stream plan carries (the quota
        filter, see ``strike_window``): ``"auto"`` = the shared PER-EXPIRY rule
        (volfit.data.strike_window.strike_bounds around ``spot``, seen from the
        ET exchange day — a 2-day rung keeps ~±30 %, a 1-year rung the wide
        band), a tuple = the legacy uniform ``[lo, hi] * spot`` band, None =
        everything. No-op on an unusable spot; never windows down to nothing
        (a degenerate band falls back to the full set)."""
        if self.strike_window is None or spot is None or not spot > 0.0:
            return contracts
        if isinstance(self.strike_window, str):  # "auto": the per-expiry rule
            today = self._exchange_day()
            bounds: dict[date, tuple[float, float] | None] = {}
            for c in contracts:
                if c.expiry not in bounds:
                    bounds[c.expiry] = strike_bounds(spot, c.expiry, today, self.window_sigma_ref)
            kept = [c for c in contracts if inside(c.strike, bounds[c.expiry])]
        else:
            lo, hi = self.strike_window
            kept = [c for c in contracts if lo * spot <= c.strike <= hi * spot]
        return kept or contracts

    # ``_fetch_live`` (BID/ASK only), ``_exercise_style`` (one hit per ticker per
    # day), ``enrich_reference`` and ``call_stats`` live in bloomberg_fields.

    # -- dividends (provider-specific capability, not part of the contract) --

    def dividend_schedule(
        self, ticker: str, reference_date: date | None = None
    ) -> tuple[Dividend, ...]:
        """Forward cash-dividend schedule for the de-Am / forward model.

        Prefers future-declared rows from DVD_HIST_ALL; if none are listed (the
        common case — issuers declare one quarter out), projects the trailing
        cadence forward across the option horizon. Best-effort: any failure
        (no entitlement, no Terminal, schema surprise) warns and returns ``()``,
        so the caller falls back to the continuous-yield forward unchanged.
        """
        reference = reference_date or date.today()
        blp = self._blp_module()
        try:
            frame = blp.bds(self._security(ticker), "DVD_HIST_ALL")
            rows = records(frame)
        except Exception as exc:  # no entitlement / Terminal / schema change
            warnings.warn(f"{ticker}: dividend fetch failed: {exc}", stacklevel=2)
            return ()

        history: list[tuple[date, float, str]] = []
        for row in rows:
            div_type = str(row.get("Dividend Type", "")).strip().lower()
            if div_type and div_type != "income":
                continue  # skip specials / capital-gains distributions
            ex_date = as_date(row.get("Ex-Date"))
            amount = price_or_none(row.get("Dividend Amount"))
            if ex_date is None or amount is None:
                continue
            history.append((ex_date, amount, str(row.get("Dividend Frequency", ""))))

        future = sorted(
            (d, a)
            for (d, a, _) in history
            if 0 < (d - reference).days <= self.max_days
        )
        if future:
            return tuple(Dividend(ex_date=d, amount=a) for d, a in future)
        return project_dividends(history, reference, self.max_days)
