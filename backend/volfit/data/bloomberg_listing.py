"""The Bloomberg chain LISTING — three ``bds`` per ticker, cached per exchange day.

Why a module of its own: the listing is the one metered request the streaming
book cannot replace (``//blp/mktdata`` has no chain membership — see the
``//blp/mktlist`` finding in Docs/bloomberg_setup.md), and its cost is fixed
per ticker: ``OPT_CHAIN`` + one ``CHAIN_TICKERS`` per series (SPY 3.8 s, SPX
7.7 s, measured 2026-09-23). A ladder changes once a day (new dailies list
overnight, never mid-session), so re-listing every 10 minutes — the old
``CHAIN_CACHE_TTL`` — bought nothing and, on a Terminal with a monthly
unique-securities budget, re-touched thousands of securities per refresh.
The listing is therefore keyed by the ET EXCHANGE DAY and persisted on disk
(``volfit.data.cache_dir``, ``<TICKER>_<YYYY-MM-DD>.json``), so a restart
inside the day costs nothing and a new day re-lists exactly once.

Listing facts (live-verified 2026-09-02, Docs/bloomberg_setup.md):

* ``OPT_CHAIN`` — the monthlies + LEAPS, BOTH sides, full securities ("SPY US
  09/18/26 C500 Equity"); deaf to every CHAIN_*_OVRD override.
* ``CHAIN_TICKERS`` per series ("W" weeklies + dailies, "Q" quarterlies) with
  ``CHAIN_EXP_DT_OVRD="ALL"`` (every expiry of the series — without it the
  field answers ONE expiry, the nearest), the periodicity and the
  ``CHAIN_POINTS_OVRD`` count cap. Rows are CALLS only, without the yellow key
  ("SPY US 09/04/26 C740"): the put is mirrored and the asset class appended.

A series the Terminal cannot answer contributes nothing (OPT_CHAIN is the
backbone and its failure propagates); the union is de-duplicated by security.
The provider then keeps one root per date (volfit.data.bloomberg_roots) and
stores the kept contracts + roots — what the file holds.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from volfit.data.bloomberg_parse import ParsedOption, columns, parse_descriptor
from volfit.data.expiry_time import ET

logger = logging.getLogger(__name__)

#: Bloomberg "yellow key" asset-class words (upper-cased index) — a contract
#: whose last token is one of these already carries its key.
_ASSET_CLASSES_UPPER = {c.upper() for c in ("Equity", "Index", "Curncy", "Comdty", "Corp", "Govt", "Mtge", "Pfd")}

#: The CHAIN_TICKERS series fetched ON TOP of OPT_CHAIN's monthlies / LEAPS:
#: "W" = weeklies + dailies (Bloomberg files a Tue/Thu daily under W), "Q" =
#: the end-of-quarter / end-of-month quarterlies. "M" would duplicate OPT_CHAIN
#: and "D" answers nothing (live-verified 2026-09-02).
CHAIN_SERIES = ("W", "Q")
#: CHAIN_EXP_DT_OVRD value listing every expiry of a series.
CHAIN_ALL_EXPIRIES = "ALL"
#: CHAIN_POINTS_OVRD — the COUNT cap of a CHAIN_TICKERS request (a single
#: strike comes back without it); large enough for an index root's full ladder.
CHAIN_POINTS = 50000

#: The " C<strike>" token of a descriptor (never the "C US" of a root like Citi).
_CALL_TOKEN_RE = re.compile(r"\sC(?=[0-9])")
#: Characters allowed in a listing file's ticker stem ("SX5E INDEX" -> "SX5E_INDEX").
_STEM_RE = re.compile(r"[^A-Za-z0-9.\-]+")
#: On-disk format version — bump when the JSON shape changes (old files are ignored).
_FORMAT = 1


def exchange_day() -> date:
    """Today's ET exchange day — the listing's cache key. Rolls at midnight ET,
    before any US or European session lists its new dailies."""
    return datetime.now(ET).date()


@dataclass(frozen=True)
class Listing:
    """One ticker's chain for one exchange day: the contracts after the
    one-root-per-date selection and the root kept per expiry date."""

    day: date
    contracts: list[ParsedOption]
    roots: dict[date, str]


# ------------------------------------------------------------ frame parsing
def parse_chain_frame(frame, asset_class: str = "") -> list[ParsedOption]:
    """Parsed contracts out of a chain ``bds`` frame — CHAIN_TICKERS (one
    security per row) or OPT_CHAIN ("Security Description" descriptors): every
    non-metadata column is tried and the first one that yields contracts wins,
    so the column's name (which differs between the two fields and xbbg
    versions) never matters. ``asset_class`` ("Index" / "Equity") completes a
    row that lacks its yellow key — sent bare, the reference request refuses it
    ("All securities failed: SX5E 09/18/26 C4650, …")."""
    for name, values in columns(frame).items():
        if name in ("ticker", "field"):
            continue
        parsed = [p for p in (parse_descriptor(str(v)) for v in values) if p]
        if parsed:
            return [with_asset_class(p, asset_class) for p in parsed]
    return []


def with_asset_class(contract: ParsedOption, asset_class: str) -> ParsedOption:
    """The contract with ``asset_class`` appended when its security carries no
    yellow key (a CHAIN_TICKERS row); untouched when it already ends in one."""
    if not asset_class:
        return contract
    if contract.security.rsplit(" ", 1)[-1].upper() in _ASSET_CLASSES_UPPER:
        return contract
    return replace(contract, security=f"{contract.security} {asset_class}")


def with_mirrored_puts(contracts: list[ParsedOption]) -> list[ParsedOption]:
    """CHAIN_TICKERS answers CALLS only; every listed strike carries a put too,
    so each call is paired with its put security (" C740" -> " P740") — a
    call-only chain has no parity and implies no forward."""
    out: list[ParsedOption] = []
    for c in contracts:
        out.append(c)
        if c.call_put == "C":
            out.append(replace(c, security=_CALL_TOKEN_RE.sub(" P", c.security, count=1), call_put="P"))
    return out


def dedupe_contracts(contracts: list[ParsedOption]) -> list[ParsedOption]:
    """First occurrence per security (OPT_CHAIN's keyed rows win over a series'
    mirrored ones); order otherwise preserved."""
    seen: set[str] = set()
    out: list[ParsedOption] = []
    for c in contracts:
        if c.security not in seen:
            seen.add(c.security)
            out.append(c)
    return out


# ------------------------------------------------------------- the 3 bds
def list_chain(blp, security: str, chain_series: Sequence[str] = CHAIN_SERIES) -> list[ParsedOption]:
    """Every listed contract of ``security`` from the Terminal: OPT_CHAIN (its
    failure propagates — an account-side refusal must reach the status light)
    plus one CHAIN_TICKERS per series (a series the Terminal cannot answer is
    skipped). De-duplicated by security; roots NOT yet selected."""
    asset_class = security.rsplit(" ", 1)[-1]  # "Index" / "Equity"
    parsed = parse_chain_frame(blp.bds(security, "OPT_CHAIN"), asset_class)
    for series in chain_series:
        overrides = {
            "CHAIN_POINTS_OVRD": str(CHAIN_POINTS),
            "CHAIN_PERIODICITY_OVRD": series,
            "CHAIN_EXP_DT_OVRD": CHAIN_ALL_EXPIRIES,
        }
        try:
            rows = parse_chain_frame(blp.bds(security, "CHAIN_TICKERS", overrides=overrides), asset_class)
        except Exception:  # noqa: BLE001 — a Terminal / rig without the field or the series
            rows = []
        parsed.extend(with_mirrored_puts(rows))
    return dedupe_contracts(parsed)


# ------------------------------------------------------------- disk cache
def listing_path(directory: Path, ticker: str, day: date) -> Path:
    """``<dir>/<TICKER>_<YYYY-MM-DD>.json`` (spaces and the like folded to "_")."""
    stem = _STEM_RE.sub("_", ticker.strip().upper()).strip("_") or "TICKER"
    return Path(directory) / f"{stem}_{day.isoformat()}.json"


def load_listing(directory: Path | None, ticker: str, day: date) -> Listing | None:
    """The persisted listing of ``ticker`` for ``day``, or None (missing, a
    corrupt / foreign-format file, an unreadable directory — never raises)."""
    if directory is None:
        return None
    path = listing_path(directory, ticker, day)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("format") != _FORMAT or raw.get("day") != day.isoformat():
            return None
        contracts = [
            ParsedOption(
                security=str(c["security"]), expiry=date.fromisoformat(c["expiry"]),
                strike=float(c["strike"]), call_put=str(c["cp"]),
            )
            for c in raw["contracts"]
        ]
        roots = {date.fromisoformat(k): str(v) for k, v in (raw.get("roots") or {}).items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return Listing(day=day, contracts=contracts, roots=roots)


def save_listing(directory: Path | None, ticker: str, listing: Listing) -> Path | None:
    """Persist ``listing`` atomically (temp file + ``os.replace``); a failure only
    disables the cache for this call (a fetch never fails on a cache)."""
    if directory is None:
        return None
    path = listing_path(directory, ticker, listing.day)
    payload = {
        "format": _FORMAT,
        "ticker": ticker.strip().upper(),
        "day": listing.day.isoformat(),
        "contracts": [
            {"security": c.security, "expiry": c.expiry.isoformat(), "strike": c.strike, "cp": c.call_put}
            for c in listing.contracts
        ],
        "roots": {d.isoformat(): r for d, r in listing.roots.items()},
    }
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logger.info("bloomberg listing cache not written (%s): %s", path, exc)
        try:
            tmp.unlink()
        except OSError:
            pass
        return None
    return path


def drop_listings(directory: Path | None, ticker: str | None = None) -> int:
    """Delete the persisted listing files of ``ticker`` (every day), or of every
    ticker when None. Returns the number removed; never raises."""
    if directory is None:
        return 0
    stem = None if ticker is None else listing_path(directory, ticker, date(2000, 1, 1)).name[: -len("_2000-01-01.json")]
    pattern = re.compile(r"^(.+)_\d{4}-\d{2}-\d{2}\.json$")
    removed = 0
    try:
        for path in Path(directory).glob("*.json"):
            m = pattern.match(path.name)
            if m is None or (stem is not None and m.group(1) != stem):
                continue
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed
