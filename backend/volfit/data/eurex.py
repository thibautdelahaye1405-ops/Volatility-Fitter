"""Eurex delayed option chains / EOD settlement surfaces (sixth ExchangeAdapter,
volfit.data.exchange).

Eurex's product pages — e.g. https://www.eurex.com/ex-en/markets/idx/stoxx/
EURO-STOXX-50-Index-Options-46548 (tabs "Prices/Quotes", "Statistics") — are fed
by ONE JSON endpoint (headless-Edge XHR capture 2026-08-21, cross-checked against
the page's ``prices-statistics`` bundle whose request builder emits exactly these
two shapes):

    https://www.eurex.com/api/v1/overallstatistics/{productId}?filtertype=overview[&busdate=YYYYMMDD]
        -> header {underlyingClosingPrice, volume, openInterest, putCallRatio,
                   tradingDates ["20-08-2026 12:00", …]  (newest first = the default busdate)}
           dataRows [{date "20260918", contractType "M"|"W"|"E", callVolume, callOpenInterest,
                      putVolume, putOpenInterest, putCallRatio, total}]  -- one row per EXPIRY
    https://www.eurex.com/api/v1/overallstatistics/{productId}?filtertype=detail
            &productdate=YYYYMMDD&contracttype=M[&busdate=YYYYMMDD]
        -> dataRowsCall / dataRowsPut [{callOrPut, strike, versionNumber, volume, openInterest,
                                        open, high, low, last, dSettle[, bid, bidVol, ask, askVol, lastTraded]}]

``busdate`` omitted = the last COMPLETED business day (the server's default —
today's own date answers empty rows once the session is over). ``productId`` is
Eurex's NUMERIC id (the page's ``"productId": 69660`` JSON / ``data-i18n="69660"``);
the product CODE (OESX) is refused ("No product found"), so the adapter carries a
code -> id map (``PRODUCTS``) and accepts a bare numeric id as the ticker.

Two tiers in one adapter:

* intraday (09:00-17:30 CET for the index classes): rows carrying ``bid``/``ask``
  — the bundle's quote columns (bid, bidVol, ask, askVol, last, lastTraded,
  dSettle), labelled "Displayed data is 15 minutes delayed" — become two-sided
  quotes stamped now - 15 min;
* otherwise (and for any series without a book) the EOD tier: Eurex's daily
  settlement price ``dSettle`` — a model-smoothed fair value Eurex publishes for
  EVERY listed series — becomes a zero-width quote bid = ask = settle, stamped
  at the busdate's 17:30 CET close, next to the underlying's own close
  (``underlyingClosingPrice``): a coherent end-of-day surface to fit.

The selector status says which tier the last fetch delivered. Prices are EUR
per unit (index points); expiries arrive as exact dates (no calendar rule);
``versionNumber`` != 0 (corporate-action-adjusted series) are skipped.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import OptionQuote

BASE = "https://www.eurex.com/api/v1/overallstatistics"
DELAY_MINUTES = 15
#: App tickers -> Eurex NUMERIC product ids (from each product page's JSON config).
#: Add a product: open its eurex.com page, read ``"productId": N`` (or data-i18n="N").
PRODUCTS = {
    "OESX": 69660, "SX5E": 69660, "^STOXX50E": 69660, "STOXX50E": 69660, "ESTX50": 69660, "SX5E INDEX": 69660,
    "ODAX": 70044, "DAX": 70044, "^GDAXI": 70044, "GDAXI": 70044, "DAX INDEX": 70044,
    "OSTX": 70284, "SXXP": 70284, "^STOXX": 70284, "STOXX": 70284, "SXXP INDEX": 70284,
}
#: Display code per product id (the chain's ticker echo).
CODES = {69660: "OESX", 70044: "ODAX", 70284: "OSTX"}


def product_id(ticker: str) -> int:
    """Eurex numeric product id for an app ticker (bare numbers pass through)."""
    t = ticker.strip().upper()
    if t.isdigit():
        return int(t)
    pid = PRODUCTS.get(t) or PRODUCTS.get(t.lstrip("^")) or PRODUCTS.get(t.replace(" INDEX", ""))
    if pid is None:
        raise ValueError(f"Eurex product id unknown for {ticker!r} — use the numeric id from its eurex.com page "
                         f"(known codes: {', '.join(sorted(CODES.values()))})")
    return pid


def overview_url(pid: int, busdate: str | None = None) -> str:
    tail = f"&busdate={busdate}" if busdate else ""
    return f"{BASE}/{pid}?filtertype=overview{tail}"


def detail_url(pid: int, productdate: str, contracttype: str, busdate: str | None = None) -> str:
    tail = f"&busdate={busdate}" if busdate else ""
    return f"{BASE}/{pid}?filtertype=detail&productdate={productdate}&contracttype={contracttype}{tail}"


def parse_busdate(header: dict) -> date | None:
    """``tradingDates[0]`` ("20-08-2026 12:00") -> the statistics' business day."""
    dates = (header or {}).get("tradingDates") or []
    try:
        s = str(dates[0])[:10]
        return date(int(s[6:10]), int(s[3:5]), int(s[0:2]))
    except (IndexError, TypeError, ValueError):
        return None


def parse_date8(s) -> date | None:
    """``"20260918"`` -> date."""
    try:
        s = str(s)
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (TypeError, ValueError):
        return None


def parse_overview(payload: dict) -> tuple[float | None, date | None, list[tuple[date, str]]]:
    """(underlying close, busdate, [(expiry, contractType)] sorted by expiry)."""
    header = (payload or {}).get("header") or {}
    spot = price_or_none(header.get("underlyingClosingPrice"))
    if spot is not None and spot <= 0:
        spot = None
    seen: dict[date, str] = {}
    for row in (payload or {}).get("dataRows") or []:
        d = parse_date8(row.get("date"))
        if d is not None and d not in seen:
            seen[d] = str(row.get("contractType") or "M")
    return spot, parse_busdate(header), sorted(seen.items())


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def cet_close_utc(d: date, hour: int = 17, minute: int = 30) -> datetime:
    """The Frankfurt close of business day ``d`` as a UTC-naive datetime (CET/CEST
    rule: UTC+2 from the last Sunday of March to the last Sunday of October)."""
    summer = _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10)
    return datetime(d.year, d.month, d.day, hour, minute) - timedelta(hours=2 if summer else 1)


def _pos(v) -> float | None:
    p = price_or_none(v)
    return p if p is not None and p > 0 else None


def parse_detail(ticker: str, expiry: date, payload: dict, eod_stamp: datetime, live_stamp: datetime,
                 settlement_quotes: bool = True) -> tuple[list[OptionQuote], int]:
    """Detail rows -> OptionQuotes; returns (quotes, number carrying a live book).
    A row with ``bid``/``ask`` is a delayed two-sided quote (live stamp); any
    other row becomes a zero-width settlement quote (bid = ask = dSettle, EOD
    stamp) when ``settlement_quotes`` — else a last-only quote. Zeros mean "no
    value" on this feed."""
    key = ticker.strip().upper()
    out: list[OptionQuote] = []
    live = 0
    for side, rows in (("C", (payload or {}).get("dataRowsCall") or []), ("P", (payload or {}).get("dataRowsPut") or [])):
        for row in rows:
            strike = _pos(row.get("strike"))
            if strike is None:
                continue
            version = int_or_none(row.get("versionNumber")) or 0
            if version != 0:
                continue
            bid, ask, last, settle = _pos(row.get("bid")), _pos(row.get("ask")), _pos(row.get("last")), _pos(row.get("dSettle"))
            stamp = eod_stamp
            if bid is not None or ask is not None:
                live += 1
                stamp = live_stamp
            elif settlement_quotes and settle is not None:
                bid = ask = settle
            elif last is None and settle is None:
                continue
            out.append(OptionQuote(
                ticker=key, expiry=expiry, strike=float(strike), call_put=side, bid=bid, ask=ask,
                last=last if last is not None else settle, volume=int_or_none(row.get("volume")),
                open_interest=int_or_none(row.get("openInterest")), timestamp=stamp,
            ))
    return out, live


class EurexAdapter:
    """Eurex delayed quotes / EOD settlement chains (see module doc)."""

    id = "eurex"
    label = "Eurex"
    delay_minutes = DELAY_MINUTES
    tick_size = None
    headers = {"Referer": "https://www.eurex.com/ex-en/markets/idx/stoxx/EURO-STOXX-50-Index-Options-46548"}
    workers = 8
    max_expiries = 40  # nearest expiries fetched (OESX lists ~38 incl. weeklies / end-of-month)
    settlement_quotes = True  # EOD tier: settle -> zero-width quotes (False = last-only rows)

    def __init__(self) -> None:
        self._last: tuple[str, date | None] | None = None  # ("live" | "eod", busdate) of the last chain

    def status_text(self) -> str:
        """Amber status text — names the tier the last fetch delivered."""
        if self._last and self._last[0] == "live":
            return f"{self.label} ~{self.delay_minutes}-min delayed"
        if self._last and self._last[1] is not None:
            return f"{self.label} EOD settlement ({self._last[1].isoformat()})"
        return f"{self.label} ~{self.delay_minutes}-min delayed / EOD settlement"

    def _overview(self, ticker: str, fetch_json) -> tuple[int, float | None, date | None, list[tuple[date, str]]]:
        pid = product_id(ticker)
        try:
            payload = fetch_json(overview_url(pid))
        except ValueError as exc:
            raise ValueError(f"Eurex lists no product {ticker!r} (id {pid}: {exc})") from None
        spot, busdate, expiries = parse_overview(payload)
        return pid, spot, busdate, expiries

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        pid, spot, busdate, expiries = self._overview(ticker, fetch_json)
        if spot is None:
            raise ValueError(f"Eurex serves no underlying close for {ticker!r} (id {pid})")
        busdate = busdate or datetime.now(timezone.utc).date()
        expiries = [(d, c) for d, c in expiries if d >= busdate][: self.max_expiries]
        eod_stamp = cet_close_utc(busdate)
        live_stamp = (datetime.now(timezone.utc) - timedelta(minutes=DELAY_MINUTES)).replace(tzinfo=None, microsecond=0)
        key = CODES.get(pid, ticker.strip().upper())

        def one(item: tuple[date, str]):
            d, ctype = item
            try:
                return d, fetch_json(detail_url(pid, d.strftime("%Y%m%d"), ctype)) or {}
            except ValueError:
                return d, {}

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(one, expiries))
        quotes: list[OptionQuote] = []
        live = 0
        for d, payload in results:
            q, n = parse_detail(key, d, payload, eod_stamp, live_stamp, self.settlement_quotes)
            quotes.extend(q)
            live += n
        self._last = ("live" if live else "eod", busdate)
        return RawChain(ticker=key, spot=float(spot), timestamp=live_stamp if live else eod_stamp,
                        quotes=quotes, exercise_style="european", security_type="index")

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        pid, spot, _, _ = self._overview(ticker, fetch_json)
        if spot is None:
            raise ValueError(f"Eurex serves no underlying close for {ticker!r} (id {pid})")
        return float(spot)

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
