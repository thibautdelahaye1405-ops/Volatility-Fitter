"""Nasdaq delayed option chains (the second ExchangeAdapter, volfit.data.exchange).

nasdaq.com exposes the delayed (~15-min, OPRA-consolidated) option chain of
every US-listed option class as JSON:

    https://api.nasdaq.com/api/quote/{SYM}/option-chain?assetclass={stocks|etf|index}
        &limit=0&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all
    https://api.nasdaq.com/api/quote/{SYM}/info?assetclass={…}          (underlying)

Shape (confirmed live 2026-08-21): ``data.table.rows[]`` is one row per STRIKE
carrying both sides — ``c_Bid/c_Ask/c_Last/c_Volume/c_Openinterest`` and the
``p_*`` twins, ``strike``, ``expiryDate`` ("Aug 21", no year), plus GROUP HEADER
rows (``expirygroup: "August 21, 2026"``, everything else null) that open each
expiry. The exact expiry (with year) is taken from the row's ``drillDownURL``
tail (``…/spy---260821c00360000`` = root padded with dashes + YYMMDD + c/p +
strike×1000), the group header being the fallback. Numbers are strings with
thousands separators, ``"--"`` = missing, ``"$"``-prefixed in ``/info``.
``limit=0`` returns the whole chain (SPY ~6.9k rows / 2.7 MB / ~1.5 s).
The asset class is not known a priori: the adapter tries ``stocks → etf →
index`` (a wrong class answers ``status.rCode 400`` with no rows) and caches
the hit per symbol. ``data.lastTrade`` ("LAST TRADE: $762.6 (AS OF …)" /
"LATEST INDEX VALUE: 29,213.16 (…)") is the fallback spot; ``/info``
``primaryData.lastSalePrice`` the preferred (live) one. No publication stamp is
served: chains are stamped ``now − 15 min`` (the documented delay) so the data
age stays honest. Coverage: every US-listed class incl. the Nasdaq indices
(NDX/NDXP…); the Cboe-proprietary SPX/VIX/RUT are not carried (use Cboe).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import US_OPTION_TICK, OptionQuote

CHAIN_URL = (
    "https://api.nasdaq.com/api/quote/{sym}/option-chain?assetclass={ac}&limit=0"
    "&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all"
)
INFO_URL = "https://api.nasdaq.com/api/quote/{sym}/info?assetclass={ac}"
#: Asset classes tried in order of how common they are on a watchlist.
ASSET_CLASSES = ("stocks", "etf", "index")
DELAY_MINUTES = 15

_URL_TAIL = re.compile(r"([a-z0-9-]+?)-*(\d{6})([cp])(\d{8})\s*$", re.IGNORECASE)
_LAST_TRADE = re.compile(r"\$?\s*([0-9][0-9,]*\.?[0-9]*)")
_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"), start=1)}


def num(value) -> float | None:
    """``"10,860.40"`` / ``"$766.01"`` / ``"--"`` → float | None (0 → None via price_or_none)."""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("$", "")
    if text in ("", "--", "N/A"):
        return None
    return price_or_none(text)


def count(value) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "--", "N/A"):
        return None
    return int_or_none(text)


def parse_group_date(text: str) -> date | None:
    """``"August 21, 2026"`` → date (the group header's expiry)."""
    try:
        month, rest = text.strip().split(" ", 1)
        day, year = rest.replace(",", "").split()
        return date(int(year), _MONTHS[month.lower()], int(day))
    except (ValueError, KeyError, AttributeError):
        return None


def parse_drilldown(url: str | None) -> tuple[date, str, float] | None:
    """``…/spy---260821c00360000`` → (expiry, "C"/"P", strike) or None."""
    if not url:
        return None
    m = _URL_TAIL.search(url.rsplit("/", 1)[-1])
    if m is None:
        return None
    yymmdd, cp, strike = m.group(2), m.group(3).upper(), m.group(4)
    try:
        expiry = date(2000 + int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))
    except ValueError:
        return None
    return expiry, cp, int(strike) / 1000.0


def parse_last_trade(text) -> float | None:
    """``"LAST TRADE: $762.6 (AS OF …)"`` / ``"LATEST INDEX VALUE: 29,213.16 …"`` → price."""
    if not text:
        return None
    m = _LAST_TRADE.search(str(text).split(":", 1)[-1])
    return num(m.group(1)) if m else None


def chain_ok(payload) -> bool:
    """Whether a chain payload is a real answer (right asset class, rows)."""
    if not isinstance(payload, dict):
        return False
    data = payload.get("data")
    if not isinstance(data, dict):
        return False
    code = (payload.get("status") or {}).get("rCode")
    rows = ((data.get("table") or {}).get("rows")) or []
    return (code in (None, 200)) and bool(rows)


def parse_rows(ticker: str, rows: list[dict], stamp: datetime) -> list[OptionQuote]:
    """Strike rows (+ group headers) → OptionQuotes, both sides per row."""
    key = ticker.strip().upper()
    quotes: list[OptionQuote] = []
    group_expiry: date | None = None
    for row in rows:
        header = row.get("expirygroup")
        if header and not row.get("strike"):
            group_expiry = parse_group_date(header)
            continue
        strike = num(row.get("strike"))
        parsed = parse_drilldown(row.get("drillDownURL"))
        expiry = parsed[0] if parsed else group_expiry
        if strike is None and parsed:
            strike = parsed[2]
        if expiry is None or strike is None:
            continue
        for side, prefix in (("C", "c_"), ("P", "p_")):
            bid, ask = num(row.get(prefix + "Bid")), num(row.get(prefix + "Ask"))
            last = num(row.get(prefix + "Last"))
            if bid is None and ask is None and last is None:
                continue  # the side is not listed (or dead) — nothing to carry
            quotes.append(
                OptionQuote(
                    ticker=key, expiry=expiry, strike=strike, call_put=side,
                    bid=bid, ask=ask, last=last,
                    volume=count(row.get(prefix + "Volume")),
                    open_interest=count(row.get(prefix + "Openinterest")),
                    timestamp=stamp,
                )
            )
    return quotes


def parse_chain(ticker: str, payload: dict, asset_class: str, spot: float | None, now: datetime | None = None) -> RawChain:
    """One chain payload → RawChain (pure). ``spot`` from /info when available,
    else the payload's ``lastTrade``; stamped ``now − DELAY_MINUTES``."""
    if not chain_ok(payload):
        raise ValueError(f"Nasdaq returned no chain for {ticker!r}")
    data = payload["data"]
    spot = spot if spot is not None else parse_last_trade(data.get("lastTrade"))
    if spot is None:
        raise ValueError(f"Nasdaq payload for {ticker!r} carries no underlying price")
    stamp = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(minutes=DELAY_MINUTES))
    stamp = stamp.replace(tzinfo=None, microsecond=0)
    quotes = parse_rows(ticker, (data.get("table") or {}).get("rows") or [], stamp)
    return RawChain(
        ticker=ticker.strip().upper(),
        spot=float(spot),
        timestamp=stamp,
        quotes=quotes,
        exercise_style="european" if asset_class == "index" else "american",
        security_type=asset_class,
    )


class NasdaqAdapter:
    """Nasdaq delayed option chains (see module doc)."""

    id = "nasdaq"
    label = "Nasdaq"
    delay_minutes = DELAY_MINUTES
    tick_size = US_OPTION_TICK
    headers = {"Accept-Language": "en-US,en;q=0.9"}

    def __init__(self) -> None:
        self._class: dict[str, str] = {}  # symbol -> resolved asset class

    def _resolve_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> tuple[dict, str]:
        """Try the cached class first, then stocks → etf → index."""
        sym = ticker.strip().upper().lstrip("^")
        order = [self._class[sym]] if sym in self._class else []
        order += [ac for ac in ASSET_CLASSES if ac not in order]
        for ac in order:
            try:
                payload = fetch_json(CHAIN_URL.format(sym=sym, ac=ac))
            except ValueError:
                continue
            if chain_ok(payload):
                self._class[sym] = ac
                return payload, ac
        raise ValueError(f"Nasdaq lists no options for {ticker!r}")

    def _info_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float | None:
        sym = ticker.strip().upper().lstrip("^")
        order = [self._class[sym]] if sym in self._class else list(ASSET_CLASSES)
        for ac in order:
            try:
                payload = fetch_json(INFO_URL.format(sym=sym, ac=ac))
            except ValueError:
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            spot = num(((data or {}).get("primaryData") or {}).get("lastSalePrice"))
            if spot is not None:
                self._class.setdefault(sym, ac)
                return spot
        return None

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        payload, ac = self._resolve_chain(ticker, fetch_json)
        spot = self._info_spot(ticker, fetch_json)
        return parse_chain(ticker, payload, ac, spot)

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        spot = self._info_spot(ticker, fetch_json)
        if spot is None:
            raise ValueError(f"Nasdaq quote for {ticker!r} carries no price")
        return spot

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
