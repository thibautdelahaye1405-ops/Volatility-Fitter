"""SGX delayed option chains (fifth ExchangeAdapter, volfit.data.exchange).

SGX publishes its delayed derivatives prices as plain JSON (the "Delayed
Prices - Options" page's own API, captured 2026-08-21):

    https://api.sgx.com/derivatives/v1.0/metalist?category=options&derivatives-kind=equityindex
        -> [{contractCode: "NK", contractName: "SGX Nikkei 225 Index Options"}, FCH, TWN, SGP, NKWE/NKWC …]
    https://api.sgx.com/derivatives/v1.0/cc/{CODE}?category=options&params=delivery-month
        -> rows {"delivery-month": "2026-09"} (one per series; dedupe)
    https://api.sgx.com/derivatives/v1.0/cc/{CODE}?category=options&delivery-month=2026-09&session=0
        -> one row per STRIKE: strike-price, call-/put- best-bid-price, best-ask-price,
           last-trade-price, open-interest, total-volume, call-symbol ("NKU26_C66000"),
           updated-time (epoch ms), price-fractional-indicator, current-trading-session
    https://api.sgx.com/derivatives/v1.0/cc/{CODE}?category=futures&delivery-month=…&session=0
        -> the future: last-traded-price-adj (the SPOT PROXY — the Nikkei index itself
           is not an SGX instrument), last-trading-date, best-bid/ask-price(-abs)

Prices: futures rows carry scaled fields (``best-ask-price`` 6606500 for
66,065.0 with ``price-fractional-indicator`` 2) next to ``-adj``/``-abs``
real ones; option rows carry only the plain names, so the adapter applies a
guard — if a quote exceeds 1.5 × the underlying it is scaled by
10^indicator and divided back. Expiry per delivery month: the futures month's
``last-trading-date`` when listed, else the contract rule (NK: the day before
the 2nd Friday — the OSE SQ; FCH/TWN/SGP: the second-last business day).
Stamp: the newest ``updated-time`` (UTC). ~10-min delayed; the T session is
SGT day — outside it the books are empty (verified 2026-08-21 evening:
metadata and ladders present, no two-sided quotes). European, JPY/index pts.
Weeklies (NKWE/NKWC) are keyed by week on the site; not handled here.
"""

from __future__ import annotations

import calendar
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import OptionQuote

BASE = "https://api.sgx.com/derivatives/v1.0"
DELAY_MINUTES = 10
#: App tickers -> SGX option contract codes.
CODES = {"NK": "NK", "NIKKEI": "NK", "N225": "NK", "^N225": "NK", "NKY": "NK", "FCH": "FCH", "A50": "FCH",
         "TWN": "TWN", "TAIWAN": "TWN", "SGP": "SGP", "STI": "SGP", "MSCISG": "SGP"}
#: Months whose expiry is the day before the 2nd Friday (Nikkei SQ rule).
SQ_RULE = {"NK"}


def contract_code(ticker: str) -> str:
    t = ticker.strip().upper()
    return CODES.get(t, t.lstrip("^"))


def months_url(code: str, category: str = "options") -> str:
    return f"{BASE}/cc/{code}?category={category}&params=delivery-month&orderby=delivery-month&order=asc"


def chain_url(code: str, month: str, session: int = 0) -> str:
    return f"{BASE}/cc/{code}?category=options&delivery-month={month}&session={session}&order=asc&orderby=strike-price"


def futures_url(code: str, month: str, session: int = 0) -> str:
    return f"{BASE}/cc/{code}?category=futures&delivery-month={month}&session={session}"


def delivery_months(payload: dict) -> list[str]:
    rows = (payload or {}).get("data") or []
    return sorted({str(r.get("delivery-month")) for r in rows if r.get("delivery-month")})


def second_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    offset = (4 - first.weekday()) % 7
    return first + timedelta(days=offset + 7)


def rule_expiry(code: str, month: str) -> date | None:
    """Contract rule for a delivery month (``"2026-09"``)."""
    try:
        y, m = int(month[:4]), int(month[5:7])
    except (TypeError, ValueError):
        return None
    if code in SQ_RULE:
        return second_friday(y, m) - timedelta(days=1)
    d = date(y, m, calendar.monthrange(y, m)[1])
    seen = 0
    while True:
        if d.weekday() < 5:
            seen += 1
            if seen == 2:
                return d
        d -= timedelta(days=1)


def to_utc(epoch_ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=timezone.utc).replace(tzinfo=None, microsecond=0)
    except (TypeError, ValueError, OSError):
        return None


def parse_rows(ticker: str, expiry: date, rows: list[dict], stamp: datetime, spot: float | None) -> list[OptionQuote]:
    """Strike rows -> OptionQuotes (both sides), de-scaling prices when they are
    obviously in fractional units (guard: a quote above 1.5 × spot)."""
    key = ticker.strip().upper()
    out: list[OptionQuote] = []
    for row in rows or []:
        strike = price_or_none(row.get("strike-price"))
        if strike is None:
            continue
        try:
            scale = 10.0 ** int(row.get("price-fractional-indicator") or 0)
        except (TypeError, ValueError):
            scale = 1.0
        for side, p in (("C", "call-"), ("P", "put-")):
            vals = [price_or_none(row.get(p + k)) for k in ("best-bid-price", "best-ask-price", "last-trade-price")]
            if all(v is None for v in vals):
                continue
            if spot and scale > 1.0 and any(v is not None and v > 1.5 * spot for v in vals):
                vals = [None if v is None else v / scale for v in vals]
            bid, ask, last = vals
            out.append(OptionQuote(
                ticker=key, expiry=expiry, strike=float(strike), call_put=side, bid=bid, ask=ask, last=last,
                volume=int_or_none(row.get(p + "total-volume")), open_interest=int_or_none(row.get(p + "open-interest")),
                timestamp=stamp,
            ))
    return out


class SgxAdapter:
    """SGX delayed option chains (see module doc)."""

    id = "sgx"
    label = "SGX"
    delay_minutes = DELAY_MINUTES
    tick_size = None
    headers = {"Origin": "https://www.sgx.com", "Referer": "https://www.sgx.com/"}
    workers = 6
    max_months = 18  # nearest delivery months fetched (NK lists ~38, out to 2034)

    def _futures(self, code: str, fetch_json) -> tuple[float | None, dict[str, date]]:
        """(front-future last = spot proxy, {delivery-month: last-trading-date})."""
        try:
            months = delivery_months(fetch_json(months_url(code, "futures")))
        except ValueError:
            return None, {}
        spot, dates = None, {}
        for i, m in enumerate(months[: max(1, min(4, len(months)))]):
            try:
                rows = (fetch_json(futures_url(code, m)) or {}).get("data") or []
            except ValueError:
                continue
            for r in rows:
                ltd = r.get("last-trading-date")
                if ltd:
                    try:
                        dates[m] = date.fromisoformat(str(ltd)[:10])
                    except ValueError:
                        pass
                if spot is None:
                    spot = price_or_none(r.get("last-traded-price-adj")) or price_or_none(r.get("daily-settlement-price-adj"))
            if i == 0 and spot is None and rows:
                spot = price_or_none(rows[0].get("session-close-abs"))
        return spot, dates

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        code = contract_code(ticker)
        try:
            months = delivery_months(fetch_json(months_url(code)))
        except ValueError as exc:
            raise ValueError(f"SGX lists no options for {ticker!r} ({exc})") from None
        if not months:
            raise ValueError(f"SGX lists no options for {ticker!r}")
        months = months[: self.max_months]
        spot, ltd = self._futures(code, fetch_json)

        def one(month: str):
            try:
                return month, (fetch_json(chain_url(code, month)) or {}).get("data") or []
            except ValueError:
                return month, []

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(one, months))
        stamps = [to_utc(r.get("updated-time")) for _, rows in results for r in rows[:1]]
        stamps = [s for s in stamps if s is not None]
        stamp = max(stamps) if stamps else (datetime.now(timezone.utc) - timedelta(minutes=DELAY_MINUTES)).replace(tzinfo=None, microsecond=0)
        quotes: list[OptionQuote] = []
        for month, rows in results:
            expiry = ltd.get(month) or rule_expiry(code, month)
            if expiry is None:
                continue
            quotes.extend(parse_rows(ticker, expiry, rows, stamp, spot))
        if spot is None:
            raise ValueError(f"SGX serves no underlying (front future) price for {ticker!r}")
        return RawChain(ticker=ticker.strip().upper(), spot=float(spot), timestamp=stamp, quotes=quotes,
                        exercise_style="european", security_type="index")

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        spot, _ = self._futures(contract_code(ticker), fetch_json)
        if spot is None:
            raise ValueError(f"SGX quote for {ticker!r} carries no price")
        return float(spot)

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
