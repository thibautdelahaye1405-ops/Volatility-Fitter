"""Cboe delayed option chains (the reference ExchangeAdapter, volfit.data.exchange).

Cboe publishes, for every US-listed equity/ETF option class and its own cash
indices, a delayed (~15-min) snapshot of its book as public JSON on its CDN:

    https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json
    https://cdn.cboe.com/api/global/delayed_quotes/quotes/{SYMBOL}.json   (underlying only)

Shape (confirmed live 2026-08-21): ``{"timestamp": "2026-08-21 11:45:27",
"symbol": "SPY", "data": {"symbol", "security_type": "stock"|"index",
"current_price", "bid", "ask", "last_trade_time", ..., "options": [{"option":
"SPY260918C00500000", "bid", "ask", "bid_size", "ask_size", "iv",
"open_interest", "volume", "last_trade_price", "last_trade_time", ...}]}}``.
The top-level ``timestamp`` is the publication time in UTC (it matches the
CDN's Last-Modified), ``option`` is the OCC symbol (volfit.data.occ parses it
— variable roots, so SPX and SPXW series in the one ``_SPX`` file both parse),
and prices are plain decimals (0 = no quote). Cash indices are addressed with a
leading underscore (``_SPX``, ``_VIX``, ``_XSP``, ``_RUT``…) and come back with
``security_type == "index"`` → European exercise; everything else American.
An unlisted symbol is refused by the CDN (403/XML), mapped to ValueError.
Sizes: SPY ~14k contracts / 6 MB / ~1 s; SPX ~31k / 14 MB / ~2 s — hence the
provider's per-ticker cache. Every US-listed option class is reachable, no
key, no quota.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain, utc_naive
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.occ import parse_option_symbol
from volfit.data.types import US_OPTION_TICK, OptionQuote

OPTIONS_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{sym}.json"
QUOTE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/quotes/{sym}.json"

#: Cboe cash-index roots (addressed ``_ROOT`` on the CDN; European exercise).
#: Weekly/flex roots map to their parent file (SPXW lives in ``_SPX``).
INDEX_ROOTS = {
    "SPX", "SPXW", "XSP", "XSPW", "VIX", "VIXW", "RUT", "RUTW", "MRUT", "NDX", "NDXP",
    "DJX", "OEX", "XEO", "BXM", "BXD", "BXR", "PUT", "RXM", "VXX", "NANOS",
}
_PARENT_FILE = {"SPXW": "SPX", "XSPW": "XSP", "VIXW": "VIX", "RUTW": "RUT", "NDXP": "NDX"}


def cdn_symbol(ticker: str) -> str:
    """The CDN file symbol for an app ticker: ``^SPX`` / ``SPX`` / ``SPX Index`` →
    ``_SPX``; ``SPXW`` → ``_SPX`` (same file); ``SPY`` → ``SPY``."""
    t = ticker.strip().upper()
    if t.endswith(" INDEX"):  # Bloomberg-style security string
        t = t[: -len(" INDEX")].strip()
    is_index = t.startswith("^")
    t = t.lstrip("^").lstrip("_")
    t = _PARENT_FILE.get(t, t)
    if is_index or t in INDEX_ROOTS:
        return f"_{t}"
    return t


def parse_timestamp(text) -> datetime:
    """Cboe's ``"YYYY-MM-DD HH:MM:SS"`` publication stamp (UTC) → UTC-naive;
    falls back to now (UTC) on anything unparsable."""
    if text:
        try:
            dt = datetime.fromisoformat(str(text).strip().replace("T", " "))
            return utc_naive(dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc))
        except ValueError:
            pass
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def parse_chain(ticker: str, payload: dict) -> RawChain:
    """One CDN options payload → RawChain (pure; offline-testable)."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError(f"Cboe returned no chain for {ticker!r}")
    stamp = parse_timestamp(payload.get("timestamp"))
    spot = price_or_none(data.get("current_price"))
    if spot is None:
        raise ValueError(f"Cboe payload for {ticker!r} carries no underlying price")
    key = ticker.strip().upper()
    quotes: list[OptionQuote] = []
    for rec in data.get("options") or []:
        sym = rec.get("option")
        if not sym:
            continue
        try:
            occ = parse_option_symbol(f"O:{sym}")
        except ValueError:
            continue  # not an OCC symbol: skip the row, never the chain
        quotes.append(
            OptionQuote(
                ticker=key,
                expiry=occ.expiry,
                strike=occ.strike,
                call_put=occ.call_put,
                bid=price_or_none(rec.get("bid")),
                ask=price_or_none(rec.get("ask")),
                last=price_or_none(rec.get("last_trade_price")),
                volume=int_or_none(rec.get("volume")),
                open_interest=int_or_none(rec.get("open_interest")),
                timestamp=stamp,
            )
        )
    sec_type = str(data.get("security_type") or "").lower()
    return RawChain(
        ticker=key,
        spot=float(spot),
        timestamp=stamp,
        quotes=quotes,
        exercise_style="european" if sec_type == "index" else "american",
        spot_bid=price_or_none(data.get("bid")),
        spot_ask=price_or_none(data.get("ask")),
        security_type=sec_type,
    )


class CboeAdapter:
    """Cboe delayed-quotes adapter (see module doc)."""

    id = "cboe"
    label = "Cboe"
    delay_minutes = 15
    tick_size = US_OPTION_TICK

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        try:
            payload = fetch_json(OPTIONS_URL.format(sym=cdn_symbol(ticker)))
        except ValueError as exc:
            raise ValueError(f"Cboe lists no options for {ticker!r} ({exc})") from None
        return parse_chain(ticker, payload)

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        payload = fetch_json(QUOTE_URL.format(sym=cdn_symbol(ticker)))
        data = payload.get("data") if isinstance(payload, dict) else None
        spot = price_or_none((data or {}).get("current_price"))
        if spot is None:
            raise ValueError(f"Cboe quote for {ticker!r} carries no price")
        return float(spot)

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        """One small underlying-quote request for the first ticker."""
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
