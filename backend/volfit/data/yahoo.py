"""Yahoo Finance option-chain provider (ROADMAP Phase 3, real market data).

Design intent: `YahooProvider` implements the `OptionChainProvider` contract
of volfit.data.provider on top of the `yfinance` package, so the rest of the
stack (storage, forwards, calibration, API) runs unchanged on live data.
The provider serves exactly the user's watchlist passed at construction —
Yahoo can quote nearly any listed ticker, so universe selection is the
caller's job, not discovery here.

yfinance API surface relied on (stable across recent versions):
- ``Ticker(symbol)`` construction;
- ``Ticker.fast_info["last_price"]`` for the spot, with a fallback to the
  last daily close of ``Ticker.history(period="5d")``;
- ``Ticker.options`` — tuple of ISO 'YYYY-MM-DD' expiry strings;
- ``Ticker.option_chain(expiry)`` — object with ``.calls`` / ``.puts``
  pandas DataFrames carrying ``strike``, ``bid``, ``ask``, ``lastPrice``,
  ``volume``, ``openInterest`` columns.

Conventions and robustness:
- yfinance is imported *lazily* (only when a real Ticker is needed), so this
  module imports fine in environments without it; tests inject a fake
  ``ticker_factory`` and stay offline.
- Yahoo reports 0.0 for absent bid/ask/last — per volfit.data.types missing
  means ``None`` (never 0.0), so values <= 0 are mapped to ``None`` here.
- NaN volume / open interest map to ``None``; DataFrames are walked via
  ``itertuples``/``getattr`` so pandas is never imported in this module.
- A failing expiry is skipped with a warning rather than failing the whole
  chain; only if *every* expiry fails does fetch_chain raise.
"""

from __future__ import annotations

import math
import warnings
from datetime import date, datetime, timezone
from typing import Callable, Sequence

from volfit.data.provider import OptionChainProvider, SymbolMatch
from volfit.data.types import ChainSnapshot, OptionQuote

#: Yahoo autocomplete endpoint and the option-bearing quote types we surface.
_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_SEARCH_TYPES = {"EQUITY", "ETF", "INDEX"}


def _default_ticker_factory(symbol: str):
    """Resolve yfinance.Ticker on first use; clear error if not installed."""
    try:
        import yfinance
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "YahooProvider requires the 'yfinance' package: pip install yfinance"
        ) from exc
    return yfinance.Ticker(symbol)


def _price_or_none(value) -> float | None:
    """Map a Yahoo price field to float; <= 0 or NaN means 'no quote' -> None."""
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or x <= 0.0:
        return None
    return x


def _int_or_none(value) -> int | None:
    """Map a Yahoo count field (volume, OI) to int; NaN/None -> None."""
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(x) or math.isinf(x):
        return None
    return int(x)


class YahooProvider(OptionChainProvider):
    """Live option chains for a user watchlist via Yahoo Finance.

    Parameters
    ----------
    tickers      : the watchlist; `list_tickers` returns exactly this list.
    max_expiries : keep at most this many near expiries per chain.
    max_days     : drop expiries further out than this (and already-expired).
    ticker_factory : ``symbol -> Ticker``-like object; defaults to
        ``yfinance.Ticker`` (imported lazily), injectable for offline tests.
    exercise_style : force "european" or "american" on every snapshot; None
        (the default) applies the per-ticker heuristic of `_exercise_style`.
    """

    def __init__(
        self,
        tickers: Sequence[str],
        max_expiries: int = 8,
        max_days: int = 730,
        ticker_factory: Callable[[str], object] | None = None,
        exercise_style: str | None = None,
    ) -> None:
        self._tickers = list(tickers)
        self.max_expiries = max_expiries
        self.max_days = max_days
        self._ticker_factory = ticker_factory or _default_ticker_factory
        self.exercise_style = exercise_style

    def _exercise_style(self, ticker: str) -> str:
        """Constructor override, else heuristic: Yahoo's '^'-prefixed symbols
        are cash indices with European options (^SPX, ^VIX, ...); everything
        else on the watchlist is a US-listed stock/ETF, hence American."""
        if self.exercise_style is not None:
            return self.exercise_style
        return "european" if ticker.startswith("^") else "american"

    def list_tickers(self) -> list[str]:
        return list(self._tickers)

    def search_symbols(self, query: str, limit: int = 10) -> list[SymbolMatch]:
        """Yahoo autocomplete: free-text (symbol or company name) -> symbols.

        Hits Yahoo's public search endpoint (httpx, lazy import) and keeps only
        option-bearing quote types (equity/ETF/index). Any failure — no httpx,
        network down, schema surprise — falls back to the base substring/echo
        search so the picker keeps working offline.
        """
        q = query.strip()
        if not q:
            return []
        try:
            import httpx

            response = httpx.get(
                _SEARCH_URL,
                params={"q": q, "quotesCount": limit, "newsCount": 0},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=5.0,
            )
            quotes = response.json().get("quotes", [])
        except Exception:
            return super().search_symbols(query, limit)
        out: list[SymbolMatch] = []
        for item in quotes:
            symbol = item.get("symbol")
            if not symbol or item.get("quoteType") not in _SEARCH_TYPES:
                continue
            out.append(
                SymbolMatch(
                    symbol=symbol,
                    name=item.get("shortname") or item.get("longname") or "",
                    type=item.get("quoteType", ""),
                    exchange=item.get("exchange", ""),
                )
            )
        return out[:limit]

    # -- spot ----------------------------------------------------------------

    def _spot(self, t, ticker: str) -> float:
        """Last price from fast_info, else last daily close, else ValueError."""
        try:
            price = _price_or_none(t.fast_info["last_price"])
        except Exception:
            price = None
        if price is not None:
            return price
        try:
            closes = t.history(period="5d")["Close"]
            if len(closes) > 0:
                price = _price_or_none(closes.iloc[-1])
        except Exception:
            price = None
        if price is not None:
            return price
        raise ValueError(f"could not determine spot price for {ticker!r}")

    # -- expiries ------------------------------------------------------------

    def available_expiries(self, ticker: str) -> list[date]:
        """All listed expiries inside (0, max_days], unthinned — the full list
        the universe picker offers. One cheap ``Ticker.options`` call, no chains."""
        t = self._ticker_factory(ticker)
        today = date.today()
        out: list[date] = []
        for iso in tuple(getattr(t, "options", ()) or ()):
            try:
                expiry = date.fromisoformat(str(iso))
            except ValueError:
                continue
            if 0 < (expiry - today).days <= self.max_days:
                out.append(expiry)
        return sorted(out)

    def _select_expiries(self, t, ticker: str) -> list[tuple[str, date]]:
        """Listed expiries inside (0, max_days], thinned to max_expiries.

        Liquid names list dozens of dailies/weeklies up front; taking the
        *first* N would give a ladder entirely inside one month. Instead the
        survivors are spread across the window evenly in sqrt(days) — the
        natural maturity spacing for a vol surface (denser short end, single
        rungs out to the far end), always keeping the nearest and farthest.
        """
        listed = tuple(t.options or ())
        if not listed:
            raise ValueError(f"no listed options for {ticker!r}")
        today = date.today()
        selected: list[tuple[str, date]] = []
        for iso in listed:
            try:
                expiry = date.fromisoformat(str(iso))
            except ValueError:
                continue  # malformed expiry string; ignore
            if 0 < (expiry - today).days <= self.max_days:
                selected.append((str(iso), expiry))
        selected.sort(key=lambda pair: pair[1])
        if not selected:
            raise ValueError(
                f"no listed options for {ticker!r} within {self.max_days} days"
            )
        if len(selected) <= self.max_expiries:
            return selected
        if self.max_expiries == 1:
            return [selected[0]]
        sqrt_days = [math.sqrt((e - today).days) for _, e in selected]
        targets = [
            sqrt_days[0] + (sqrt_days[-1] - sqrt_days[0]) * i / (self.max_expiries - 1)
            for i in range(self.max_expiries)
        ]
        chosen: list[int] = []
        for target in targets:  # nearest unused expiry per sqrt-time target
            i = min(range(len(selected)), key=lambda j: abs(sqrt_days[j] - target))
            if i not in chosen:
                chosen.append(i)
        return [selected[i] for i in sorted(chosen)]

    # -- chain ---------------------------------------------------------------

    @staticmethod
    def _quotes_from_frame(
        frame, ticker: str, expiry: date, call_put: str, timestamp: datetime
    ) -> list[OptionQuote]:
        """Map one calls/puts DataFrame to OptionQuote rows (NaN-safe)."""
        quotes: list[OptionQuote] = []
        for row in frame.itertuples(index=False):
            strike = _price_or_none(getattr(row, "strike", None))
            if strike is None:
                continue  # unusable row without a positive strike
            quotes.append(
                OptionQuote(
                    ticker=ticker,
                    expiry=expiry,
                    strike=strike,
                    call_put=call_put,
                    bid=_price_or_none(getattr(row, "bid", None)),
                    ask=_price_or_none(getattr(row, "ask", None)),
                    last=_price_or_none(getattr(row, "lastPrice", None)),
                    volume=_int_or_none(getattr(row, "volume", None)),
                    open_interest=_int_or_none(getattr(row, "openInterest", None)),
                    timestamp=timestamp,
                )
            )
        return quotes

    def fetch_chain(self, ticker: str, expiries: list[date] | None = None) -> ChainSnapshot:
        """Fetch spot + the requested expiries (the universe selection), or the
        thinned ladder when none is given; skip (warn) failing expiries."""
        t = self._ticker_factory(ticker)
        spot = self._spot(t, ticker)
        if expiries is None:
            chosen = self._select_expiries(t, ticker)  # legacy sqrt-thinned ladder
        else:
            chosen = [(e.isoformat(), e) for e in sorted(expiries)]
        # Naive UTC snapshot time (types.py convention: tz-naive, UTC clock).
        timestamp = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)

        quotes: list[OptionQuote] = []
        failures = 0
        for iso, expiry in chosen:
            try:
                chain = t.option_chain(iso)
                quotes.extend(
                    self._quotes_from_frame(chain.calls, ticker, expiry, "C", timestamp)
                )
                quotes.extend(
                    self._quotes_from_frame(chain.puts, ticker, expiry, "P", timestamp)
                )
            except Exception as exc:  # network hiccup, schema surprise, ...
                failures += 1
                warnings.warn(
                    f"{ticker}: skipping expiry {iso}: {exc}", stacklevel=2
                )
        if chosen and failures == len(chosen):
            raise ValueError(
                f"all {failures} expiries failed for {ticker!r}; see warnings"
            )
        return ChainSnapshot(
            ticker=ticker,
            spot=spot,
            timestamp=timestamp,
            quotes=quotes,
            exercise_style=self._exercise_style(ticker),
        )
