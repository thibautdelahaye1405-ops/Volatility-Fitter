"""Historical EOD option-chain pulls for the Bloomberg provider (via ``bdh``).

Kept out of bloomberg.py for the 400-line policy. ``bdh`` returns a narwhals
long-format frame (ticker/date/field/value) with one row per (security, date,
field) — read column-wise (the frames lack ``index``/``itertuples``) and pivoted
for a single date by ``bloomberg_parse.pivot_bdh``.

Two entry points used by BloombergProvider:
- ``available_history`` — the last ~30 trading days the Terminal can serve EOD
  (from one underlying PX_LAST history call);
- ``fetch_eod`` — the closing chain for one trading day (EOD bid/ask/last/volume/
  open-interest per option + the underlying close as spot).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from volfit.data.bloomberg_parse import ParsedOption, as_date, columns, pivot_bdh
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import US_OPTION_TICK, ChainSnapshot, OptionQuote

#: Historical EOD fields (note the PX_-prefixed names ``bdh`` uses).
_HIST_FIELDS = ("PX_BID", "PX_ASK", "PX_LAST", "PX_VOLUME", "OPEN_INT")

#: Calendar window scanned for trading days, and how many to keep.
_LOOKBACK_DAYS = 45
_MAX_DAYS = 30


def available_history(blp, security: str) -> list[date]:
    """The last ~30 trading days (oldest first) the underlying has closes for."""
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    frame = blp.bdh(security, "PX_LAST", start.isoformat(), end.isoformat())
    days = sorted(
        {d for d in (as_date(x) for x in columns(frame).get("date", [])) if d}
    )
    return days[-_MAX_DAYS:]


def fetch_eod(
    blp,
    ticker: str,
    security: str,
    contracts: list[ParsedOption],
    on: date,
    exercise_style: str,
) -> ChainSnapshot:
    """The closing chain for ``on``: one ``bdh`` over the contracts + underlying."""
    securities = [c.security for c in contracts]
    frame = blp.bdh(securities + [security], list(_HIST_FIELDS), on.isoformat(), on.isoformat())
    pivot = pivot_bdh(frame, on)
    spot = price_or_none(pivot.get(security, {}).get("PX_LAST"))
    if spot is None:
        raise ValueError(f"no Bloomberg close for {ticker!r} on {on.isoformat()}")
    timestamp = datetime.combine(on, time(21, 0))  # ~US close, tz-naive UTC clock
    quotes = [
        OptionQuote(
            ticker=ticker,
            expiry=c.expiry,
            strike=c.strike,
            call_put=c.call_put,
            bid=price_or_none(pivot.get(c.security, {}).get("PX_BID")),
            ask=price_or_none(pivot.get(c.security, {}).get("PX_ASK")),
            last=price_or_none(pivot.get(c.security, {}).get("PX_LAST")),
            volume=int_or_none(pivot.get(c.security, {}).get("PX_VOLUME")),
            open_interest=int_or_none(pivot.get(c.security, {}).get("OPEN_INT")),
            timestamp=timestamp,
        )
        for c in contracts
    ]
    return ChainSnapshot(
        ticker=ticker,
        spot=spot,
        timestamp=timestamp,
        quotes=quotes,
        exercise_style=exercise_style,
        tick_size=US_OPTION_TICK,
    )
