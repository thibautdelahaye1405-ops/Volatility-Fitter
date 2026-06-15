"""As-of (timestamp) service: day-grouped capabilities + moment resolution.

Backs GET /asof and POST /asof (volfit.api.routers.asof). The as-of dropdown
under Data Source chooses *when* chains are observed as a two-level pick: first a
business **day**, then a **moment** within it —

  * ``close``         the official end-of-day close (provider EOD / prev-close);
  * ``latest``        the most recent intraday snapshot of that day;
  * ``before_close``  the snapshot nearest to N minutes before the 16:00 ET close.

Intraday moments (``latest`` / ``before_close``) come from snapshots the app
captured while running (VolStore history) for Yahoo/Bloomberg; a provider that
``intraday_capable`` (Massive/Polygon) instead fetches the chain at the resolved
instant, so those moments work even on days the app never captured. ``close`` is
always available from the provider for any listed trading day.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from volfit.api.state import AppState, AsOfSelection
from volfit.data.store import VolStore

#: US-equity regular-session close, used to anchor the "N minutes before close"
#: moment. Captured snapshot timestamps are stored UTC-naive (every provider),
#: so the target instant is computed in ET and converted to UTC-naive to match.
MARKET_CLOSE = time(16, 0)
#: Preset "minutes before close" offsets the dropdown offers.
CLOSE_OFFSETS = (15, 30, 60)
#: How many recent business days (with data) to surface in the picker.
MAX_DAYS = 20


def _market_tz():
    """America/New_York, or None if the tz database is unavailable (Windows
    without ``tzdata``) — callers fall back to a fixed-offset approximation."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/New_York")
    except Exception:  # noqa: BLE001 — missing tzdata: caller approximates
        return None


def market_close_utc(on: date) -> datetime:
    """The 16:00 ET close of ``on`` as a UTC-naive datetime (matches stored ts).

    Uses the IANA tz (correct across DST) when available; otherwise approximates
    US Eastern with the standard 2nd-Sun-Mar..1st-Sun-Nov DST window (−4h EDT /
    −5h EST), which is exact for every regular US trading day."""
    tz = _market_tz()
    if tz is not None:
        local = datetime.combine(on, MARKET_CLOSE, tzinfo=tz)
        return local.astimezone(timezone.utc).replace(tzinfo=None)
    edt = _us_eastern_is_dst(on)
    offset = 4 if edt else 5
    return datetime.combine(on, MARKET_CLOSE) + timedelta(hours=offset)


def _us_eastern_is_dst(on: date) -> bool:
    """US DST on ``on``: 2nd Sunday of March .. 1st Sunday of November."""
    march = date(on.year, 3, 1)
    dst_start = march + timedelta(days=(6 - march.weekday()) % 7 + 7)  # 2nd Sun
    nov = date(on.year, 11, 1)
    dst_end = nov + timedelta(days=(6 - nov.weekday()) % 7)  # 1st Sun
    return dst_start <= on < dst_end


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _prev_business_day(d: date) -> date:
    d -= timedelta(days=1)
    while not _is_weekday(d):
        d -= timedelta(days=1)
    return d


def _captures_by_date(state: AppState) -> dict[date, list[datetime]]:
    """Captured snapshot instants grouped by date (each list newest-first)."""
    out: dict[date, list[datetime]] = {}
    if state.store_path is None:
        return out
    tickers = state.active_tickers()
    if not tickers:
        return out
    try:
        with VolStore(state.store_path) as store:
            rows = store.list_snapshots(tickers)  # newest first
    except Exception:  # noqa: BLE001 — history is best-effort
        return out
    seen: set[datetime] = set()
    for _ticker, _sid, ts in rows:
        bucket = ts.replace(second=0, microsecond=0)
        if bucket in seen:
            continue
        seen.add(bucket)
        out.setdefault(ts.date(), []).append(ts)
    return out


def _history_dates(state: AppState) -> list[date]:
    """Provider EOD trading days (empty when the source has no EOD list)."""
    modes = state.provider.historical_modes()
    tickers = state.active_tickers()
    if "eod" not in modes or not tickers:
        return []
    try:
        return list(state.provider.available_history(tickers[0]))
    except Exception:  # noqa: BLE001
        return []


def _prev_session(history: list[date], today: date) -> date:
    """The day the provider's ``prev_close`` refers to: its newest EOD day if it
    lists one, else the previous business day."""
    return history[-1] if history else _prev_business_day(today)


def asof_payload(state: AppState) -> dict:
    """Current selection plus the day-grouped capabilities for the dropdown."""
    modes = state.provider.historical_modes()
    intraday = state.provider.intraday_capable()
    history = _history_dates(state)
    history_set = set(history)
    captures = _captures_by_date(state)
    today = state.reference_date
    prev_session = _prev_session(history, today)

    def _has_close(d: date) -> bool:
        if "eod" in modes and d in history_set:
            return True
        return "prev_close" in modes and d == prev_session

    # Candidate days: today + EOD days + captured days (+ the prev-close day),
    # newest first, capped. Only days that can serve a moment are listed (an empty
    # day would dead-end every pick): a day with real data (a close or captures)
    # always shows; an intraday-capable provider can additionally synthesize a
    # moment on any business day even with no stored data.
    candidates = {today, prev_session} | history_set | set(captures)
    days = []
    for d in sorted(candidates, reverse=True):
        has_close = _has_close(d)
        has_caps = bool(captures.get(d))
        if not (has_close or has_caps or (intraday and _is_weekday(d))):
            continue
        days.append(
            {
                "date": d.isoformat(),
                "isToday": d == today,
                "hasClose": has_close,
                "hasCaptures": has_caps,
                "intraday": intraday,
            }
        )
        if len(days) >= MAX_DAYS:
            break

    sel = state.as_of
    return {
        "mode": sel.mode,
        "on": sel.on.isoformat() if sel.on else None,
        "ts": sel.ts.isoformat() if sel.ts else None,
        "day": sel.day.isoformat() if sel.day else None,
        "moment": sel.moment,
        "offset": sel.offset,
        "supportedModes": sorted(modes),
        "intradayCapable": intraday,
        "closeOffsets": list(CLOSE_OFFSETS),
        "days": days,
    }


def set_asof(state: AppState, mode: str, on: str | None, ts: str | None) -> dict:
    """Apply a low-level as-of selection (the legacy/explicit form)."""
    selection = AsOfSelection(
        mode=mode,
        on=date.fromisoformat(on) if on else None,
        ts=datetime.fromisoformat(ts) if ts else None,
    )
    state.set_as_of(selection)
    return asof_payload(state)


def set_moment(state: AppState, on: str, moment: str, offset: int | None) -> dict:
    """Resolve a (day, moment) dropdown pick into a concrete as-of and apply it.

    ``moment`` is "close" | "latest" | "before_close" (the last with an ``offset``
    in minutes). Raises ValueError when the day cannot serve the requested moment.
    """
    day = date.fromisoformat(on)
    selection = _resolve_moment(state, day, moment, offset)
    state.set_as_of(selection)
    return asof_payload(state)


def _resolve_moment(
    state: AppState, day: date, moment: str, offset: int | None
) -> AsOfSelection:
    modes = state.provider.historical_modes()
    intraday = state.provider.intraday_capable()
    history = _history_dates(state)
    captures = _captures_by_date(state).get(day, [])  # newest first

    if moment == "close":
        if "eod" in modes and day in set(history):
            return AsOfSelection(mode="eod", on=day, day=day, moment="close")
        if "prev_close" in modes and day == _prev_session(history, state.reference_date):
            return AsOfSelection(mode="prev_close", day=day, moment="close")
        raise ValueError(f"no close available for {day.isoformat()}")

    if moment == "latest":
        if captures:
            return AsOfSelection(mode="captured", ts=captures[0], day=day, moment="latest")
        if intraday:
            ts = min(market_close_utc(day), _now_utc())
            return AsOfSelection(mode="intraday", ts=ts, day=day, moment="latest")
        raise ValueError(f"no intraday snapshot for {day.isoformat()}")

    if moment == "before_close":
        minutes = int(offset or 0)
        target = market_close_utc(day) - timedelta(minutes=minutes)
        at_or_before = [t for t in captures if t <= target]
        if at_or_before:
            ts = at_or_before[0]  # captures is newest-first -> nearest <= target
        elif intraday:
            return AsOfSelection(
                mode="intraday", ts=target, day=day, moment="before_close", offset=minutes
            )
        elif captures:
            ts = captures[-1]  # only later captures exist: use the earliest we have
        else:
            raise ValueError(f"no intraday snapshot for {day.isoformat()}")
        return AsOfSelection(
            mode="captured", ts=ts, day=day, moment="before_close", offset=minutes
        )

    raise ValueError(f"unknown moment {moment!r}")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
