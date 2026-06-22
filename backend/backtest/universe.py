"""Backtest universe + regime windows (the sample set).

Declares the asset set (display ticker → OCC option roots, exercise style,
sector) and the regime date windows once, so the capture and compute phases share
one definition. Index options need several roots (SPX trades as ``SPX`` AM-settled
monthlies and ``SPXW`` PM-settled weeklies/EOM); single names / ETFs use one.

The snapshot instant is 15:45 ET ("before close" — tight two-sided markets, not
the noisy official print), resolved to a UTC-naive datetime with DST handled via
the IANA tz database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


@dataclass(frozen=True)
class AssetSpec:
    """One backtest asset: display ticker, its OCC option roots, exercise style."""

    ticker: str
    option_roots: tuple[str, ...]
    exercise_style: str  # "european" (index) | "american" (single name / ETF)
    sector: str

    @staticmethod
    def index(ticker: str, roots: tuple[str, ...]) -> "AssetSpec":
        return AssetSpec(ticker, roots, "european", "index")

    @staticmethod
    def equity(ticker: str, sector: str) -> "AssetSpec":
        return AssetSpec(ticker, (ticker,), "american", sector)

    @staticmethod
    def etf(ticker: str, sector: str) -> "AssetSpec":
        return AssetSpec(ticker, (ticker,), "american", sector)


# --- Pilot universe (8 assets): indices + 2 ETFs + 3 single names ------------
PILOT: tuple[AssetSpec, ...] = (
    AssetSpec.index("SPX", ("SPX", "SPXW")),
    AssetSpec.index("NDX", ("NDX", "NDXP")),
    AssetSpec.index("RUT", ("RUT", "RUTW")),
    AssetSpec.etf("EEM", "intl_em"),
    AssetSpec.etf("EFA", "intl_dev"),
    AssetSpec.equity("AAPL", "tech"),
    AssetSpec.equity("NVDA", "semis"),
    AssetSpec.equity("JPM", "financials"),
)

# --- Full universe (25 assets) — confirmed with the user ---------------------
FULL: tuple[AssetSpec, ...] = (
    AssetSpec.index("SPX", ("SPX", "SPXW")),
    AssetSpec.index("NDX", ("NDX", "NDXP")),
    AssetSpec.index("RUT", ("RUT", "RUTW")),
    AssetSpec.etf("EEM", "intl_em"),
    AssetSpec.etf("EFA", "intl_dev"),
    # 10 mega-caps
    AssetSpec.equity("AAPL", "tech"),
    AssetSpec.equity("MSFT", "tech"),
    AssetSpec.equity("NVDA", "semis"),
    AssetSpec.equity("AMZN", "discretionary"),
    AssetSpec.equity("GOOGL", "communication"),
    AssetSpec.equity("META", "communication"),
    AssetSpec.equity("AVGO", "semis"),
    AssetSpec.equity("TSLA", "discretionary"),
    AssetSpec.equity("BRK.B", "financials"),
    AssetSpec.equity("JPM", "financials"),
    # sector breadth
    AssetSpec.equity("XOM", "energy"),
    AssetSpec.equity("CVX", "energy"),
    AssetSpec.equity("LLY", "healthcare"),
    AssetSpec.equity("UNH", "healthcare"),
    AssetSpec.equity("WMT", "staples"),
    AssetSpec.equity("COST", "staples"),
    AssetSpec.equity("HD", "discretionary"),
    AssetSpec.equity("CAT", "industrials"),
    AssetSpec.equity("GS", "financials"),
    AssetSpec.equity("NFLX", "communication"),
)

# --- Regime windows (inclusive start/end calendar dates) ---------------------
# Confirmed: low/stable relaxed to ~2023 (true sub-12 needs pre-2021, where the
# quotes tier thins out). All three reach back within the probed quotes_v1 depth.
REGIME_WINDOWS: dict[str, tuple[date, date]] = {
    "spike_aug2024": (date(2024, 7, 29), date(2024, 8, 23)),  # yen-carry spike + snapback
    "high_oct2022": (date(2022, 9, 26), date(2022, 10, 21)),  # sustained-high bear lows
    "low_jul2023": (date(2023, 7, 17), date(2023, 8, 11)),    # low/stable (~VIX 13-14)
}

#: US market holidays intersecting the regime windows (no trading; skip).
_HOLIDAYS: frozenset[date] = frozenset({
    # none fall inside the three windows above; placeholder for the full run.
})

#: Snapshot instant, ET (before close).
SNAPSHOT_ET = time(15, 45)


def trading_days(start: date, end: date) -> list[date]:
    """Weekdays in [start, end] minus known holidays (inclusive)."""
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in _HOLIDAYS:
            out.append(d)
        d += timedelta(days=1)
    return out


def snapshot_utc(on: date) -> datetime:
    """15:45 ET on ``on`` as a UTC-naive datetime (DST-correct via zoneinfo)."""
    from zoneinfo import ZoneInfo

    et = datetime.combine(on, SNAPSHOT_ET, tzinfo=ZoneInfo("America/New_York"))
    return et.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def all_option_roots(assets: tuple[AssetSpec, ...]) -> list[str]:
    """The union of OCC roots to co-cache from one daily scan."""
    return sorted({r for a in assets for r in a.option_roots})
