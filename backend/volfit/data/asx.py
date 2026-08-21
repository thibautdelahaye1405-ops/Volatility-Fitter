"""ASX delayed option chains (third ExchangeAdapter, volfit.data.exchange) —
the first non-US venue.

ASX's public market-data API (Markit Digital) serves the exchange's delayed
(~20-min) option chains for every ASX-listed option class — the S&P/ASX 200
index (XJO, European) and the single-stock classes (BHP, CBA, …, American):

    https://asx.api.markitdigital.com/asx-research/1.0/derivatives/equity/{CODE}/options
        -> datesAvailable {monthly, weekly, quarterly}, underlyingAsset {symbol,
           displayName, issueType ("IN" = index), priceLast}, + the NEAREST expiry's groups
    https://asx.api.markitdigital.com/asx-research/1.0/derivatives/equity/{CODE}/options/expiry-groups
        ?expiryDates=YYYY-MM-DD&expiryDates=…   (repeated; the site's own selector)
        -> data.items[] {date, exerciseGroups[] {priceExercise, call{…}, put{…}}}

Each series dict carries ``priceBid`` / ``priceAsk`` / ``priceLast`` /
``openInterest`` / ``volume`` / ``style`` ("European"|"American") /
``dateExpiry`` / ``symbol`` / ``optionRoot`` / ``contractSize`` (10 for XJO,
100 for stocks); prices are per unit (index points for XJO, AUD for stocks),
0 = no quote. Confirmed live 2026-08-21 (the selector was mined from the ASX
site's F2 app bundle — plain ``expiryDate=`` is ignored): XJO 13 expiries /
993 strikes in ONE 0.7 MB call (~1.8 s). No publication stamp is served:
chains are stamped ``now − 20 min`` (ASX's stated delay). Two requests per
chain (dates + groups), cached by the provider; the base payload also serves
the spot. Accepted symbols: ``XJO``, ``^XJO``/``XJO.AX`` (Yahoo style), ``BHP``.
Note: the app's settlement clock (`expiry_time.default_settlement`) is
US-centric; Sydney expiry instants are off by hours — a fine-tuning item.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import OptionQuote

BASE_URL = "https://asx.api.markitdigital.com/asx-research/1.0/derivatives/equity/{code}/options"
GROUPS_URL = BASE_URL + "/expiry-groups?{query}"
DELAY_MINUTES = 20


def asx_code(ticker: str) -> str:
    """App ticker -> ASX code: ``^XJO`` / ``XJO.AX`` / ``xjo`` -> ``XJO``."""
    t = ticker.strip().upper().lstrip("^")
    if t.endswith(".AX"):
        t = t[:-3]
    return t


def groups_url(code: str, dates: Sequence[date | str]) -> str:
    """The expiry-groups URL for a set of expiries (repeated ``expiryDates=``)."""
    parts = [f"expiryDates={d.isoformat() if isinstance(d, date) else d}" for d in dates]
    return GROUPS_URL.format(code=code, query="&".join(parts))


def available_dates(base_payload: dict) -> list[date]:
    """Every listed expiry from ``datesAvailable`` (weekly + monthly + quarterly)."""
    data = (base_payload or {}).get("data") or {}
    avail = data.get("datesAvailable") or {}
    out: set[date] = set()
    for bucket in ("weekly", "monthly", "quarterly"):
        for text in avail.get(bucket) or []:
            try:
                out.add(date.fromisoformat(str(text)[:10]))
            except ValueError:
                continue
    return sorted(out)


def underlying(base_payload: dict) -> tuple[float | None, str, str]:
    """``(spot, issue type, symbol)`` from the base payload's ``underlyingAsset``."""
    data = (base_payload or {}).get("data") or {}
    ua = data.get("underlyingAsset") or {}
    return price_or_none(ua.get("priceLast")), str(ua.get("issueType") or ""), str(ua.get("symbol") or "")


def _quote(ticker: str, expiry: date, strike: float, side: str, rec: dict, stamp: datetime) -> OptionQuote | None:
    if not isinstance(rec, dict):
        return None
    bid, ask, last = price_or_none(rec.get("priceBid")), price_or_none(rec.get("priceAsk")), price_or_none(rec.get("priceLast"))
    if bid is None and ask is None and last is None:
        return None  # side not listed / dead
    return OptionQuote(
        ticker=ticker, expiry=expiry, strike=strike, call_put=side,
        bid=bid, ask=ask, last=last,
        volume=int_or_none(rec.get("volume")), open_interest=int_or_none(rec.get("openInterest")),
        timestamp=stamp,
    )


def parse_groups(ticker: str, groups_payload: dict, stamp: datetime) -> tuple[list[OptionQuote], str | None]:
    """``expiry-groups`` payload -> (quotes, exercise style seen: "european"|"american"|None)."""
    data = (groups_payload or {}).get("data")
    items = data.get("items") if isinstance(data, dict) else data
    key = ticker.strip().upper()
    quotes: list[OptionQuote] = []
    styles: dict[str, int] = {}  # style -> series count (a class can mix; majority wins)
    for group in items or []:
        try:
            expiry = date.fromisoformat(str(group.get("date"))[:10])
        except (TypeError, ValueError):
            continue
        for x in group.get("exerciseGroups") or []:
            strike = price_or_none(x.get("priceExercise"))
            if strike is None:
                continue
            for side, field in (("C", "call"), ("P", "put")):
                rec = x.get(field)
                q = _quote(key, expiry, float(strike), side, rec, stamp)
                if q is not None:
                    quotes.append(q)
                    style = str((rec or {}).get("style") or "").lower()
                    if style in ("european", "american"):
                        styles[style] = styles.get(style, 0) + 1
    style = max(styles, key=styles.get) if styles else None  # majority of the series
    return quotes, style


def build_chain(ticker: str, base_payload: dict, groups_payload: dict, now: datetime | None = None) -> RawChain:
    """Base + groups payloads -> RawChain (pure)."""
    spot, issue_type, _sym = underlying(base_payload)
    if spot is None:
        raise ValueError(f"ASX payload for {ticker!r} carries no underlying price")
    stamp = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(minutes=DELAY_MINUTES))
    stamp = stamp.replace(tzinfo=None, microsecond=0)
    quotes, style = parse_groups(ticker, groups_payload, stamp)
    if style is None:
        style = "european" if issue_type.upper() == "IN" else "american"
    return RawChain(
        ticker=ticker.strip().upper(), spot=float(spot), timestamp=stamp, quotes=quotes,
        exercise_style=style, security_type="index" if issue_type.upper() == "IN" else "stock",
    )


class AsxAdapter:
    """ASX delayed option chains (see module doc)."""

    id = "asx"
    label = "ASX"
    delay_minutes = DELAY_MINUTES
    tick_size = None  # index points / AUD cents: unknown per class -> no tick floor
    headers = {"Origin": "https://www.asx.com.au", "Referer": "https://www.asx.com.au/"}

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        code = asx_code(ticker)
        try:
            base = fetch_json(BASE_URL.format(code=code))
        except ValueError as exc:
            raise ValueError(f"ASX lists no options for {ticker!r} ({exc})") from None
        dates = available_dates(base)
        if not dates:
            raise ValueError(f"ASX lists no options for {ticker!r}")
        groups = fetch_json(groups_url(code, dates))
        return build_chain(ticker, base, groups)

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        spot, _t, _s = underlying(fetch_json(BASE_URL.format(code=asx_code(ticker))))
        if spot is None:
            raise ValueError(f"ASX quote for {ticker!r} carries no price")
        return float(spot)

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
