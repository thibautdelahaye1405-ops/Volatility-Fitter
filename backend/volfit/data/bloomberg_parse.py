"""Parsing helpers for the Bloomberg provider (volfit.data.bloomberg).

Kept separate so bloomberg.py stays within the 400-line policy. Two concerns:

1. **DataFrame access that is backend-agnostic.** The xbbg build on the target
   machine returns *narwhals* frames in long/tidy format — column access
   (``df[col]``) and ``list(...)`` work, but ``df.index`` / ``df.itertuples``
   do not. Reading every column as a plain list (``_columns``) therefore works
   for narwhals *and* pandas, which is all the provider relies on.

2. **Option-descriptor parsing.** ``blp.bds(sec, "OPT_CHAIN")`` returns one row
   per listed contract with a descriptor like ``'SPY US 06/18/26 C245 Equity'``
   (ROOT COUNTRY MM/DD/YY <C|P>STRIKE YELLOW-KEY). Parsing expiry / strike /
   call-put straight from that string lets ``available_expiries`` enumerate the
   ladder with a single bulk call and no per-contract ``bdp`` — the cheap path
   the universe picker needs (liquid names list thousands of contracts).

Dividend projection (``project_dividends``) rolls a trailing cash schedule
forward when Bloomberg exposes no future-declared dividend, matching desk
practice for the discrete-dividend forward/de-Am model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from volfit.data.dividends import Dividend

#: Bloomberg responseError ``subcategory`` -> short human reason for the Data
#: Source light. These are account/entitlement states the *Terminal* must clear
#: (no code change makes data flow), so we surface them verbatim-ish instead of
#: the old catch-all "no Terminal / xbbg" which hid the real cause.
_BLP_REASONS = {
    "WORKFLOW_REVIEW_NEEDED": "workflow review needed",
    "NOT_ENTITLED": "not entitled",
    "NOT_AUTHORIZED": "not authorized",
    "DAILY_LIMIT_REACHED": "daily request limit reached",
    "MONTHLY_LIMIT_REACHED": "monthly request limit reached",
    "RESPONSE_LIMIT_REACHED": "response limit reached",
}

#: subcategory=... token inside a Bloomberg responseError message.
_SUBCATEGORY_RE = re.compile(r"subcategory=([A-Z_]+)")


def quiet_xbbg_logs() -> None:
    """Lower the pyo3 xbbg engine's tracing level so a *failed* Bloomberg
    request (which it logs at WARN to stderr) does not spam the console and
    read like a broken install. Best-effort: silently ignored on any xbbg build
    without ``set_log_level`` (e.g. the classic pandas xbbg).
    """
    try:
        import xbbg

        xbbg.set_log_level("error")
    except Exception:
        pass


def session_connected(blp) -> bool:
    """Whether the xbbg/blpapi session is actually connected to a Terminal.

    The pyo3 xbbg exposes ``is_connected()``; older builds and the test stub do
    not, so missing/raising means "unknown" -> ``False``. Used to tell a real
    *down* session apart from a *connected-but-refused* request (entitlement /
    workflow review), which the Data Source light should report differently.

    xbbg 1.x creates its engine (and the local Terminal session) **lazily on the
    first data request**, so ``is_connected()`` reads ``False`` on a fresh
    process *even with the Terminal open* — it only flips ``True`` after the
    first ``bdp``/``bds``. Because ``feed_status`` deliberately issues no billable
    request, that left the Data Source light stuck on red "no Terminal" until the
    user's first fetch. We therefore bring the engine up first via the quota-free
    ``_get_engine()`` (a local bbcomm/Terminal connect, **not** a reference-data
    request, so it never touches the daily quota) and then probe. Best-effort:
    skipped on builds/stubs without ``_get_engine`` (e.g. classic pandas xbbg),
    and a failed connect reads as not-connected.
    """
    probe = getattr(blp, "is_connected", None)
    if probe is None:
        return False
    ensure_engine = getattr(blp, "_get_engine", None)
    if ensure_engine is not None:
        try:
            ensure_engine()  # idempotent singleton: only the first call connects
        except Exception:
            return False
    try:
        return bool(probe())
    except Exception:
        return False


def short_blp_reason(exc: Exception) -> str:
    """Concise, user-facing reason from a Bloomberg request error.

    Maps a known responseError ``subcategory`` (e.g. WORKFLOW_REVIEW_NEEDED) to
    plain English; otherwise returns a trimmed tail of the message. Keeps the
    Data Source tooltip actionable ("workflow review needed") instead of generic.
    """
    text = str(exc)
    match = _SUBCATEGORY_RE.search(text)
    if match:
        token = match.group(1)
        return _BLP_REASONS.get(token, token.replace("_", " ").lower())
    return text.strip().splitlines()[-1][:80] if text.strip() else "request failed"

#: date + call/put + strike inside a descriptor, e.g. "06/18/26 C245" or "P500.5".
_DESCRIPTOR_RE = re.compile(r"(\d{2})/(\d{2})/(\d{2})\s+([CP])([0-9]+(?:\.[0-9]+)?)")

#: Yellow-key suffix in an instrument-search result, e.g. "NVDA US<equity>".
_YK_SUFFIX_RE = re.compile(r"<([A-Za-z]+)>")

#: Dividend-frequency string -> step in months (for forward projection).
_FREQ_MONTHS = {
    "monthly": 1,
    "quarter": 3,
    "quarterly": 3,
    "semi-anl": 6,
    "semi-annual": 6,
    "semi annual": 6,
    "annual": 12,
    "yearly": 12,
}


@dataclass(frozen=True)
class ParsedOption:
    """One listed contract identified purely from its OPT_CHAIN descriptor."""

    security: str  # the full Bloomberg security string, e.g. "SPY US 06/18/26 C245 Equity"
    expiry: date
    strike: float
    call_put: str  # 'C' or 'P'


def columns(df) -> dict[str, list]:
    """Read a narwhals/pandas frame as ``{column_name: [values...]}``.

    Relies only on ``df.columns`` and ``df[col]`` + ``list(...)`` — the subset
    both backends agree on (the xbbg narwhals frames lack ``index``/
    ``itertuples``).
    """
    return {str(c): list(df[c]) for c in df.columns}


def records(df) -> list[dict]:
    """Row-wise list of ``{column: value}`` dicts (column-list transpose)."""
    cols = columns(df)
    names = list(cols)
    if not names:
        return []
    n = len(cols[names[0]])
    return [{name: cols[name][i] for name in names} for i in range(n)]


def parse_descriptor(text: str) -> ParsedOption | None:
    """Parse one OPT_CHAIN descriptor; ``None`` if it doesn't match the format."""
    match = _DESCRIPTOR_RE.search(text)
    if match is None:
        return None
    mm, dd, yy, cp, strike = match.groups()
    try:
        expiry = date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None
    return ParsedOption(
        security=text.strip(), expiry=expiry, strike=float(strike), call_put=cp
    )


def normalize_security(security: str) -> str:
    """Turn an instrument-search result into a usable Bloomberg security string.

    The ``//blp/instruments`` service returns the yellow key in angle brackets
    (``"NVDA US<equity>"``); convert it to the space-separated form the rest of
    the stack expects (``"NVDA US Equity"``).
    """
    return _YK_SUFFIX_RE.sub(lambda m: " " + m.group(1).capitalize(), security).strip()


def cp_flag(value) -> str | None:
    """Map OPT_PUT_CALL ('Call'/'Put', case-insensitive) to 'C'/'P'."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s.startswith("c"):
        return "C"
    if s.startswith("p"):
        return "P"
    return None


def pivot_bdp(df) -> dict[str, dict[str, object]]:
    """Pivot a long-format ``bdp`` frame to ``{security: {field: value}}``.

    The frame has columns ``ticker`` / ``field`` / ``value`` (one row per
    security-field pair). Missing columns yield an empty mapping rather than
    raising, so a degenerate response degrades gracefully.
    """
    cols = columns(df)
    tickers = cols.get("ticker")
    fields = cols.get("field")
    values = cols.get("value")
    if tickers is None or fields is None or values is None:
        return {}
    out: dict[str, dict[str, object]] = {}
    for sec, fld, val in zip(tickers, fields, values):
        out.setdefault(str(sec), {})[str(fld)] = val
    return out


def pivot_bdh(df, on: date) -> dict[str, dict[str, object]]:
    """Pivot a long-format ``bdh`` frame (ticker/date/field/value) to
    ``{security: {field: value}}`` for a single date ``on``.

    Used for historical EOD chains: ``bdh`` returns one row per
    (security, date, field), so we keep only the requested day.
    """
    cols = columns(df)
    tickers = cols.get("ticker")
    dates = cols.get("date")
    fields = cols.get("field")
    values = cols.get("value")
    if tickers is None or dates is None or fields is None or values is None:
        return {}
    out: dict[str, dict[str, object]] = {}
    for sec, day, fld, val in zip(tickers, dates, fields, values):
        if as_date(day) != on:
            continue
        out.setdefault(str(sec), {})[str(fld)] = val
    return out


def as_date(value) -> date | None:
    """Coerce a Bloomberg date cell (datetime.date or ISO string) to date."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _add_months(d: date, months: int) -> date:
    """``d`` shifted by ``months``, clamped to the target month's last day."""
    total = (d.year * 12 + (d.month - 1)) + months
    year, month = divmod(total, 12)
    month += 1
    # Clamp day (e.g. Jan 31 + 1 month -> Feb 28/29).
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return date(year, month, 28)


def project_dividends(
    history: list[tuple[date, float, str]], reference: date, horizon_days: int
) -> tuple[Dividend, ...]:
    """Roll a trailing cash schedule forward to cover the option horizon.

    ``history`` is ``(ex_date, amount, frequency)`` rows (any order). The most
    recent row sets the cadence (its frequency string) and amount; successive
    ex-dates are stepped forward until they pass ``reference`` and out to
    ``reference + horizon_days``. Empty history -> no dividends (the forward
    model then falls back to continuous yield, unchanged).
    """
    if not history:
        return ()
    latest_date, latest_amt, latest_freq = max(history, key=lambda r: r[0])
    step = _FREQ_MONTHS.get(str(latest_freq).strip().lower(), 3)
    end = date.fromordinal(reference.toordinal() + horizon_days)
    out: list[Dividend] = []
    nxt = _add_months(latest_date, step)
    guard = 0
    while nxt <= end and guard < 64:
        if nxt > reference:
            out.append(Dividend(ex_date=nxt, amount=latest_amt))
        nxt = _add_months(nxt, step)
        guard += 1
    return tuple(out)
