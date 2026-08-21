"""HKEX delayed option chains (fourth ExchangeAdapter, volfit.data.exchange).

HKEX's own market-data widget serves the exchange's delayed (~15-min) option
chains for the index classes (HSI, HSCEI "HHI", Hang Seng TECH "HTI", MHI…)
and every stock-option class (TCH = Tencent, ALB = Alibaba, …) as JSONP:

    https://www1.hkex.com.hk/hkexwidget/data/getoptioncontractlist?ats={CODE}&type=0&…
        -> conlist [{id: "082026", mon: "Aug-26"}, …]                (contract months)
    …/getderivativesoption?ats={CODE}&con=082026&fr={min}&to={max}&type=0&…
        -> optionlist [{strike, c {bd, as, ls, vo, oi, iv}, p {…}}], lastupd, min, max
    …/getderivativesfutures?ats={CODE}&type=0&…   -> futureslist [{con, ls, bd, as, …}]
    …/getmarketmarquee?sym=.HSI;.HSCE;.HSTECH&…   -> indices [{ric, ls, date, tm}]
    …/getderivativesinfo?ats={CODE}&…            -> info {idx: bool, opt: bool, …}

Every call needs ``lang=eng&token=<T>&qid=<ms>&callback=<fn>`` — the
``callback`` is MANDATORY (plain JSON is refused with 403), so the adapter
reads TEXT and unwraps the JSONP. The token is embedded in the public product
page (``LabCI.getToken = function () { … return "<token>"; }`` — the LAST
return; the first is a commented sample) and is scraped once and cached; a
non-"000" response code or a refusal re-scrapes it. A month's chain must be
asked with ITS OWN strike window: a ``fr=null&to=null`` call returns the
near-the-money strikes plus ``min``/``max``, the second call with
``fr=min&to=max`` the whole ladder (another month's window returns nothing),
so it is two small calls per month (13 months ≈ 4–8 s, run on a thread pool).
Index classes (``info.idx``) are European (spot = the index marquee, HKT
stamp), stock classes American (spot proxy = the front stock future's last).
Expiry = the business day before the last business day of the contract month
(HKEX rule; HK holidays not modelled — a day off at most). Prices in HKD /
index points; ``""`` = no quote; numbers carry thousands separators.
Confirmed live 2026-08-21 (HSI: 13 months, 111 strikes in the front month).
"""

from __future__ import annotations

import calendar
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Sequence

from volfit.data.exchange import RawChain
from volfit.data.fieldmap import int_or_none, price_or_none
from volfit.data.types import OptionQuote

TOKEN_PAGE = (
    "https://www.hkex.com.hk/Market-Data/Futures-and-Options-Prices/Equity-Index/"
    "Hang-Seng-Index-Futures-and-Options?sc_lang=en"
)
WIDGET = "https://www1.hkex.com.hk/hkexwidget/data/"
DELAY_MINUTES = 15
#: App tickers -> HKEX option class codes, and the index marquee RIC per class.
CLASS_CODES = {"HSI": "HSI", "^HSI": "HSI", "HSCEI": "HHI", "HHI": "HHI", "HSTECH": "HTI", "HTI": "HTI", "MHI": "MHI"}
INDEX_RIC = {"HSI": ".HSI", "MHI": ".HSI", "HHI": ".HSCE", "HTI": ".HSTECH"}
#: Well-known stock-option class codes (HKEX assigns letters per stock).
STOCK_CODES = {"700": "TCH", "0700": "TCH", "9988": "ALB", "3690": "MET", "388": "HEX", "0388": "HEX", "939": "XCC",
               "0939": "XCC", "2318": "PAI", "1": "CKH", "0001": "CKH", "2628": "CLI", "3988": "BOC", "1299": "AIA"}
HKT = timezone(timedelta(hours=8))
_TOKEN_RE = re.compile(r"LabCI\.getToken\s*=\s*function\s*\(\)\s*\{(.*?)\};", re.S)
_RETURN_RE = re.compile(r"^[^/\n]*return\s*\"([^\"]+)\"", re.M)


def class_code(ticker: str) -> str:
    """App ticker -> HKEX class code (``^HSI``/``HSI``/``HSCEI``/``700``/``0700.HK``/``TCH``)."""
    t = ticker.strip().upper()
    if t.endswith(".HK"):
        t = t[:-3]
    if t in CLASS_CODES:
        return CLASS_CODES[t]
    digits = t.lstrip("^")
    if digits.isdigit():
        return STOCK_CODES.get(digits.lstrip("0") or "0", STOCK_CODES.get(digits, digits))
    return t.lstrip("^")


def parse_token(html: str) -> str | None:
    """The widget token from the product page (the LAST ``return "…"`` of
    ``LabCI.getToken``; the first one is a commented sample)."""
    m = _TOKEN_RE.search(html or "")
    if not m:
        return None
    rets = _RETURN_RE.findall(m.group(1))
    return rets[-1] if rets else None


def unwrap_jsonp(text: str) -> dict:
    """``cb({...})`` -> the JSON object; ValueError when it is not JSONP/JSON."""
    m = re.search(r"^\s*[A-Za-z0-9_$.]+\((.*)\)\s*;?\s*$", text or "", re.S)
    raw = m.group(1) if m else (text or "")
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ValueError(f"HKEX widget returned no JSON ({str(exc)[:40]})") from None


def num(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "N/A"):
        return None
    return price_or_none(text)


def count(value) -> int | None:
    text = str(value or "").strip().replace(",", "")
    return int_or_none(text) if text and text != "-" else None


def contract_expiry(con: str) -> date | None:
    """``"082026"`` -> the HKEX expiry day: the business day before the last
    business day of the month (weekends only; holidays not modelled)."""
    try:
        month, year = int(con[:2]), int(con[2:])
    except (TypeError, ValueError):
        return None
    d = date(year, month, calendar.monthrange(year, month)[1])
    business = 0
    while True:
        if d.weekday() < 5:
            business += 1
            if business == 2:
                return d
        d -= timedelta(days=1)


def parse_lastupd(text, fallback_now: datetime | None = None) -> datetime:
    """``"21/08/2026 16:29"`` (HKT) -> UTC-naive; else now − delay."""
    try:
        dt = datetime.strptime(str(text).strip(), "%d/%m/%Y %H:%M").replace(tzinfo=HKT)
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        now = (fallback_now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return (now - timedelta(minutes=DELAY_MINUTES)).replace(tzinfo=None, microsecond=0)


def parse_optionlist(ticker: str, expiry: date, rows: list[dict], stamp: datetime) -> list[OptionQuote]:
    key = ticker.strip().upper()
    out: list[OptionQuote] = []
    for row in rows or []:
        strike = num(row.get("strike"))
        if strike is None:
            continue
        for side, field in (("C", "c"), ("P", "p")):
            rec = row.get(field) or {}
            bid, ask, last = num(rec.get("bd")), num(rec.get("as")), num(rec.get("ls"))
            if bid is None and ask is None and last is None:
                continue
            out.append(OptionQuote(
                ticker=key, expiry=expiry, strike=float(strike), call_put=side,
                bid=bid, ask=ask, last=last, volume=count(rec.get("vo")), open_interest=count(rec.get("oi")),
                timestamp=stamp,
            ))
    return out


class HkexAdapter:
    """HKEX delayed option chains (see module doc)."""

    id = "hkex"
    label = "HKEX"
    delay_minutes = DELAY_MINUTES
    tick_size = None
    headers = {"Referer": "https://www.hkex.com.hk/"}
    workers = 6  # parallel per-month calls

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_at = 0.0

    # ------------------------------------------------------------- plumbing
    def _text(self, fetch_json, url: str) -> str:
        reader = getattr(fetch_json, "text", None)
        if reader is None:
            raise ValueError("HKEX needs a text-capable fetcher (JSONP)")
        return reader(url)

    def _ensure_token(self, fetch_json, force: bool = False) -> str:
        if self._token and not force and time.monotonic() - self._token_at < 1800.0:
            return self._token
        token = parse_token(self._text(fetch_json, TOKEN_PAGE))
        if not token:
            raise ValueError("HKEX token not found on the product page")
        self._token, self._token_at = token, time.monotonic()
        return token

    def _call(self, fetch_json, endpoint: str, **params) -> dict:
        """One widget call; re-scrapes the token once on a refusal."""
        for attempt in (0, 1):
            token = self._ensure_token(fetch_json, force=attempt == 1)
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{WIDGET}{endpoint}?{qs}&lang=eng&token={token}&qid={int(time.time() * 1000)}&callback=cb"
            try:
                data = unwrap_jsonp(self._text(fetch_json, url)).get("data") or {}
            except ValueError:
                if attempt == 0:
                    continue
                raise
            if str(data.get("responsecode", "000")) == "000":
                return data
            if attempt == 1:
                raise ValueError(f"HKEX refused {endpoint}: {data.get('responsemsg') or data.get('responsecode')}")
        return {}

    # --------------------------------------------------------------- reads
    def _spot(self, fetch_json, code: str, is_index: bool) -> tuple[float | None, str | None]:
        if is_index:
            ric = INDEX_RIC.get(code, f".{code}")
            data = self._call(fetch_json, "getmarketmarquee", sym=ric)
            for row in data.get("indices") or []:
                if row.get("ric") == ric:
                    return num(row.get("ls")), None
            return None, None
        data = self._call(fetch_json, "getderivativesfutures", ats=code, type=0)
        for row in data.get("futureslist") or []:  # front stock future's last as the spot proxy
            last = num(row.get("ls"))
            if last is not None:
                return last, data.get("lastupd")
        return None, None

    def fetch_chain(self, ticker: str, fetch_json: Callable[[str], dict]) -> RawChain:
        code = class_code(ticker)
        info = self._call(fetch_json, "getderivativesinfo", ats=code).get("info") or {}
        if not info.get("opt", True):
            raise ValueError(f"HKEX lists no options for {ticker!r}")
        is_index = bool(info.get("idx"))
        months = [c.get("id") for c in self._call(fetch_json, "getoptioncontractlist", ats=code, type=0).get("conlist") or []]
        months = [m for m in months if m and contract_expiry(m)]
        if not months:
            raise ValueError(f"HKEX lists no options for {ticker!r}")

        def one_month(con: str):
            near = self._call(fetch_json, "getderivativesoption", ats=code, con=con, fr="null", to="null", type=0)
            lo, hi = num(near.get("min")), num(near.get("max"))
            full = near
            if lo is not None and hi is not None:
                full = self._call(fetch_json, "getderivativesoption", ats=code, con=con, fr=int(lo), to=int(hi), type=0)
            return con, full

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(one_month, months))
        stamps = [r.get("lastupd") for _, r in results if r.get("lastupd") and r.get("lastupd") != "-"]
        stamp = parse_lastupd(max(stamps) if stamps else None)
        quotes: list[OptionQuote] = []
        for con, data in results:
            expiry = contract_expiry(con)
            if expiry is None:
                continue
            quotes.extend(parse_optionlist(ticker, expiry, data.get("optionlist") or [], stamp))
        spot, _ = self._spot(fetch_json, code, is_index)
        if spot is None:
            raise ValueError(f"HKEX serves no underlying price for {ticker!r}")
        return RawChain(
            ticker=ticker.strip().upper(), spot=float(spot), timestamp=stamp, quotes=quotes,
            exercise_style="european" if is_index else "american",
            security_type="index" if is_index else "stock",
        )

    def fetch_spot(self, ticker: str, fetch_json: Callable[[str], dict]) -> float:
        code = class_code(ticker)
        is_index = code in INDEX_RIC
        if not is_index:
            info = self._call(fetch_json, "getderivativesinfo", ats=code).get("info") or {}
            is_index = bool(info.get("idx"))
        spot, _ = self._spot(fetch_json, code, is_index)
        if spot is None:
            raise ValueError(f"HKEX quote for {ticker!r} carries no price")
        return float(spot)

    def probe(self, tickers: Sequence[str], fetch_json: Callable[[str], dict]) -> bool:
        try:
            self.fetch_spot(tickers[0], fetch_json)
            return True
        except Exception:  # noqa: BLE001
            return False
