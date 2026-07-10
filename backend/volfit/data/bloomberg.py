"""Bloomberg option-chain provider via xbbg (ROADMAP Phase 3, real market data).

Design intent: `BloombergProvider` implements the `OptionChainProvider`
contract (volfit.data.provider) on top of the `xbbg` convenience wrapper around
the Bloomberg Python API, so the rest of the stack — storage, forwards,
de-Americanization, calibration, API — runs unchanged on Bloomberg data. It is
the most complete live source: real bid/ask/last/volume/OI, spot, the genuine
American/European exercise flag, and a dividend schedule for the discrete-
dividend forward model.

xbbg surface relied on (confirmed live against an open Terminal):
- ``blp.bds(security, "OPT_CHAIN")`` -> one row per listed contract, descriptor
  in a "Security Description" column ("SPY US 06/18/26 C245 Equity");
- ``blp.bdp(securities, fields)`` -> long/tidy frame (ticker/field/value), all
  values as strings — coerced via volfit.data.fieldmap;
- ``blp.bds(security, "DVD_HIST_ALL")`` -> declared dividend rows (Ex-Date,
  Dividend Amount, Dividend Frequency, Dividend Type) for dividend import.

Robustness / conventions:
- xbbg is imported *lazily* (only when a real call is made), so this module
  imports fine without it; tests inject a fake ``blp_module`` and stay offline.
- Frames are read column-wise (volfit.data.bloomberg_parse.columns) because the
  xbbg narwhals frames lack ``index``/``itertuples``.
- ``available_expiries`` parses the descriptor strings (cheap, one ``bds``,
  no per-contract ``bdp``); ``fetch_chain`` only ``bdp``s the *selected*
  expiries' contracts (the universe layer passes them), keeping liquid names
  (thousands of contracts) fast.
- Missing/zero price fields map to ``None`` (volfit.data.types convention).
"""

from __future__ import annotations

import threading
import warnings
from datetime import date, datetime, timezone
from typing import Sequence

from volfit.data.bloomberg_parse import (
    ParsedOption,
    as_date,
    columns,
    parse_descriptor,
    pivot_bdp,
    project_dividends,
    quiet_xbbg_logs,
    records,
    session_connected,
    short_blp_reason,
)
from volfit.data.bloomberg_history import available_history as _available_history
from volfit.data.bloomberg_history import fetch_eod as _fetch_eod
from volfit.data.bloomberg_search import instrument_search
from volfit.data.dividends import Dividend
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.provider import AsOf, OptionChainProvider, SymbolMatch
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: Bloomberg "yellow key" asset-class words that complete a security string
#: ("SPX Index", "SAP GY Equity"). Stored canonically (title-case) and indexed
#: by their upper-cased form: the rest of the app uppercases every symbol, so a
#: full security arrives as "SPX INDEX" / "SAP GY EQUITY" and the suffix must be
#: re-cased before it is sent to Bloomberg (the API is case-sensitive on the
#: yellow key). Covers the asset classes that list options + the common ones.
_ASSET_CLASSES = ("Equity", "Index", "Curncy", "Comdty", "Corp", "Govt", "Mtge", "Pfd")
_ASSET_CLASS_BY_UPPER = {c.upper(): c for c in _ASSET_CLASSES}

#: Per-contract fields pulled in the bulk bdp (strike/expiry/CP come from the
#: descriptor, so only quote fields + the exercise flag are requested here).
_QUOTE_FIELDS = ("BID", "ASK", "LAST_PRICE", "VOLUME", "OPEN_INT", "OPT_EXER_TYP")


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


class BloombergProvider(OptionChainProvider):
    """Live option chains for a watchlist via Bloomberg (xbbg).

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
    """

    def __init__(
        self,
        tickers: Sequence[str],
        yellow_key: str = "US Equity",
        max_days: int = 730,
        blp_module: object | None = None,
        strike_window: tuple[float, float] | None = (0.5, 1.5),
    ) -> None:
        self._tickers = [t.strip().upper() for t in tickers]
        self.yellow_key = yellow_key
        self.max_days = max_days
        self._blp = blp_module
        #: Keep only strikes within ``[lo, hi] * spot`` when fetching a live chain
        #: (None = the whole listed ladder). A liquid index/ETF lists hundreds of
        #: strikes spanning a huge range — each is a separately-METERED Bloomberg
        #: security, and the far tails carry no liquidity (and break the fit), so
        #: windowing to the fittable band cuts the per-fetch security count (and
        #: the daily-quota burn) by a large factor. Widen/disable per deployment.
        self.strike_window = strike_window
        self._chain_cache: dict[str, list[ParsedOption]] = {}
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
        if self._blp is None:
            self._blp = _default_blp()
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
        if self._last_error is not None:
            return ("red", self._last_error)
        return ("green", "real-time (Terminal)")

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
        """Parsed OPT_CHAIN contracts for a ticker (cached; one ``bds`` call)."""
        key = ticker.upper()
        if key in self._chain_cache:
            return self._chain_cache[key]
        blp = self._blp_module()
        frame = blp.bds(self._security(ticker), "OPT_CHAIN")
        cols = columns(frame)
        # The descriptor column is "Security Description"; fall back to the last
        # non-metadata column if a future xbbg names it differently.
        desc_col = "Security Description"
        if desc_col not in cols:
            extras = [c for c in cols if c not in ("ticker", "field")]
            desc_col = extras[-1] if extras else ""
        descriptors = cols.get(desc_col, [])
        parsed = [p for p in (parse_descriptor(str(d)) for d in descriptors) if p]
        self._chain_cache[key] = parsed
        return parsed

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed expiries inside (0, max_days], parsed from the descriptors."""
        today = date.today()
        return sorted(
            {
                p.expiry
                for p in self._chain(ticker)
                if 0 < (p.expiry - today).days <= self.max_days
            }
        )

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
        pivot = pivot_bdp(blp.bdp(security, "PX_LAST"))
        value = price_or_none(pivot.get(security, {}).get("PX_LAST"))
        if value is None:
            raise ValueError(f"could not determine spot price for {ticker!r}")
        return value

    def spot(self, ticker: str, expiries: list[date] | None = None) -> float:
        """Cheap underlying spot — ONE PX_LAST reference hit on the underlying.

        Overrides the base contract, whose default re-fetches the WHOLE option
        chain just to read its spot. Real-time spot polling (spotMode="realtime")
        probes this every few seconds, so the default would have re-``bdp``ed
        hundreds–thousands of option contracts per poll and torched the Bloomberg
        daily reference-data quota. One underlying price per poll instead."""
        return self._spot(ticker)

    # -- chain ---------------------------------------------------------------

    def _select_contracts(
        self, ticker: str, expiries: list[date] | None
    ) -> list[ParsedOption]:
        """Parsed contracts for the requested expiries (or all within max_days)."""
        today = date.today()
        parsed = self._chain(ticker)
        if expiries is None:
            wanted = {
                p.expiry for p in parsed if 0 < (p.expiry - today).days <= self.max_days
            }
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
                    self._blp_module(), ticker, self._security(ticker), contracts, on, style
                )
            else:
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
        self, contracts: list[ParsedOption], spot: float
    ) -> list[ParsedOption]:
        """Drop strikes outside ``strike_window * spot`` (the quota-saving filter;
        see ``strike_window``). No-op when disabled or non-positive spot; never
        windows down to nothing (a degenerate band falls back to the full set)."""
        if self.strike_window is None or spot <= 0.0:
            return contracts
        lo, hi = self.strike_window
        kept = [c for c in contracts if lo * spot <= c.strike <= hi * spot]
        return kept or contracts

    def _fetch_live(self, ticker: str, contracts: list[ParsedOption]) -> ChainSnapshot:
        """The current NBBO chain for the given contracts (one bulk bdp)."""
        spot = self._spot(ticker)
        contracts = self._window_contracts(contracts, spot)  # quota: fittable band only
        blp = self._blp_module()
        pivot = pivot_bdp(blp.bdp([p.security for p in contracts], list(_QUOTE_FIELDS)))
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

        quotes: list[OptionQuote] = []
        styles: list[str] = []
        for contract in contracts:
            fields = pivot.get(contract.security, {})
            style = str(fields.get("OPT_EXER_TYP", "")).strip().lower()
            if style in ("american", "european"):
                styles.append(style)
            quotes.append(
                OptionQuote(
                    ticker=ticker,
                    expiry=contract.expiry,
                    strike=contract.strike,
                    call_put=contract.call_put,  # parsed from the descriptor
                    bid=price_or_none(fields.get("BID")),
                    ask=price_or_none(fields.get("ASK")),
                    last=price_or_none(fields.get("LAST_PRICE")),
                    volume=int_or_none(fields.get("VOLUME")),
                    open_interest=int_or_none(fields.get("OPEN_INT")),
                    timestamp=timestamp,
                )
            )
        from volfit.data.expiry_time import settlement_map

        return ChainSnapshot(
            ticker=ticker,
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=_resolve_style(styles),
            tick_size=US_OPTION_TICK,
            settlement=settlement_map({q.expiry for q in quotes}, root=ticker),
        )

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


def _resolve_style(styles: list[str]) -> str:
    """Majority exercise style across a chain (default american for equities)."""
    if not styles:
        return "american"
    return "european" if styles.count("european") > styles.count("american") else "american"
