# Exchange-published delayed option chains — source catalog

Why: Yahoo only yields a usable **mid**; the exchanges themselves publish
delayed (typically 15-min) snapshots of their **own books with the full
bid/ask**, sizes, volume and open interest — free, unmetered, no entitlement.
The app ingests them through one seam (`backend/volfit/data/exchange.py`):

- `ExchangeAdapter` — one venue: `fetch_chain(ticker, fetch_json) -> RawChain`
  (spot + every listed contract in `OptionQuote` terms, **one** HTTP round-trip),
  `fetch_spot` (a light underlying read for the real-time spot poll),
  `probe` (cheap reachability). Adding a venue = one ~120-line module + a
  fixture test; nothing else changes.
- `ExchangeChainProvider` — the app's `OptionChainProvider` over an adapter:
  per-ticker raw-chain cache (the venue files weigh MBs and refresh ~once a
  minute, so `available_expiries` + `fetch_chain` + status share one
  download), expiry filtering, the **venue publication time** as the chain
  stamp (the honest data age), amber "~N-min delayed" status, red when the
  venue does not answer / refused the last symbol. HTTP is injectable
  (`fetch_json`) → fully offline-testable.

Registered in `serve.py` as source ids `cboe` and `nasdaq` (auto-pick order:
Bloomberg → **Cboe** → **Nasdaq** → Yahoo → Massive → Synthetic); launch
`.\restart.ps1 -Cboe` / `-Nasdaq` to force one; the in-app Data Source
selector lists them as "Cboe (delayed)" / "Nasdaq (delayed)".

## Shipped — Nasdaq (US) ✅ `volfit/data/nasdaq.py`

| | |
|---|---|
| Coverage | every US-listed equity/ETF option class + the Nasdaq indices (NDX/NDXP…); **not** the Cboe-proprietary SPX/VIX/RUT (use Cboe) |
| Endpoint | `https://api.nasdaq.com/api/quote/{SYM}/option-chain?assetclass={stocks\|etf\|index}&limit=0&fromdate=all&todate=undefined&excode=oprac&callput=callput&money=all&type=all`; underlying `…/info?assetclass=…` |
| Fields | one row per strike with both sides: `c_Bid/c_Ask/c_Last/c_Volume/c_Openinterest` + `p_*`, `strike`, `expiryDate` ("Aug 21"), group-header rows `expirygroup` ("August 21, 2026"); the exact expiry comes from `drillDownURL` (`…/spy---260821c00360000`); numbers are strings with thousands separators, `"--"` = missing; `/info` `primaryData.lastSalePrice` ("$766.01") is the (live) spot, `data.lastTrade` ("LAST TRADE: $762.6 (AS OF …)" / "LATEST INDEX VALUE: 29,213.16 …") the fallback |
| Asset class | not known a priori → tried `stocks → etf → index` (a wrong class answers `status.rCode 400`, no rows), cached per symbol (SPY = etf, AAPL = stocks, NDX = index) |
| Stamp | none served → chains stamped `now − 15 min` (the documented delay) |
| Delay | ~15 min (OPRA-consolidated — a second book to cross-check Cboe's) |
| Size / speed | SPY 6.9k strike-rows / 2.7 MB / ~1.5 s (`limit=0` = whole chain) |
| Verified | 2026-08-21: SPY 31 expiries, 716 quotes / 624 two-sided, live spot 765.98; NDX European 43 expiries; SPY 26-Aug fit ATM 11.78 % / RMS 4.6 bp (Cboe: 11.73 % / 4.8 bp) |

## Shipped — Cboe (US) ✅ `volfit/data/cboe.py`

| | |
|---|---|
| Coverage | every US-listed equity/ETF option class + the Cboe cash indices (SPX/SPXW, XSP, VIX, RUT, NDX, DJX, OEX/XEO, …) |
| Endpoint | `https://cdn.cboe.com/api/global/delayed_quotes/options/{SYMBOL}.json` (indices `_SPX`), underlying `…/quotes/{SYMBOL}.json` |
| Fields | OCC symbol (`SPY260918C00500000` → root/expiry/type/strike via `volfit.data.occ`), bid, ask, bid_size, ask_size, iv, open_interest, volume, last_trade_price/time; underlying current_price, bid/ask, security_type stock/index (→ American/European) |
| Stamp | top-level `timestamp` = publication time **UTC** (matches the CDN Last-Modified) |
| Delay | ~15 min |
| Size / speed | SPY ~14k contracts / 6 MB / ~1 s; SPX ~31k / 14 MB / ~2 s → cached 60 s per ticker |
| Symbols | `SPY`, `SPX` / `^SPX` / `SPX Index` / `SPXW` → `_SPX` (both roots in one file), unknown symbol = CDN 403 → "Cboe lists no options for …" |
| Verified | 2026-08-21: SPY 26-Aug fit from 64 real bid/ask quotes (ATM 11.7 %, RMS 4.8 bp), SPX European fit, table/market frame, data-age pill at the Cboe stamp |

Caveat: this is **Cboe's own book**, not the NBBO — for liquid names it is
within a tick of the NBBO; for thinly-listed names check against a second
venue (Nasdaq, below).

## Candidates — probed 2026-08-21

| Venue | What is public | Bid/ask? | Verdict |
|---|---|---|---|
| **ASX (Australia)** `asx.api.markitdigital.com/asx-research/1.0/derivatives/equity/{CODE}/options` | JSON `expiryGroups.items[].exerciseGroups[]` with `call/put{priceBid, priceAsk, priceLast, openInterest, volume, style, dateExpiry}`, `underlyingAsset.priceLast`, `datesAvailable` (monthly/weekly/quarterly) | ✅ | **near** — the expiry selector parameter is not the obvious `expiryDate=` (the default answer carries only the nearest expiry); capture the site's XHR to find it, then it is a ~100-line adapter (XJO index options European, equities American; prices in AUD / index points) |
| **TMX Montréal (Canada)** `m-x.ca/en/trading/data/quotes?symbol=XIU*` | HTML table (bid/ask/last/volume/OI per series), ~2 MB page | ✅ (HTML) | feasible — an HTML-table scrape (lxml/regex); fragile to page redesigns |
| **Eurex (Europe)** `eurex.com/api/v1/overallstatistics/{productId}` | JSON EOD statistics (volume/OI/settlement per series, `underlyingClosingPrice`, `tradingDates`) | ❌ (EOD only) | the delayed bid/ask tables live in the site's web app; the XHR behind them was not discoverable by guessing — capture from a browser session, or use the EOD settlement prices as an end-of-day source (a different, also useful, tier) |
| **NSE India** `nseindia.com/api/option-chain-indices?symbol=NIFTY` | JSON chain (near-real-time, bid/ask) — requires the site's cookies (visit the home page first) | ✅ | feasible with a cookie handshake; anti-bot measures change often |
| **CME (US futures options)** `cmegroup.com/CmeWS/mvc/Quotes/Option/…` | JSON, 10-min delayed | ✅ | **blocked** — 403 "suspected web scraping" for scripted access; would also need the futures-forward model (options on futures) |
| **HKEX (Hong Kong)** | delayed option quotes on hkex.com.hk behind a token API | ? | not located yet |
| **Euronext (Amsterdam/Paris), JPX/OSE (Nikkei 225)** | derivatives quote pages (web app / HTML) | ? | not probed |

## How to add a venue

1. `backend/volfit/data/<venue>.py`: a class with `id`, `label`,
   `delay_minutes`, `tick_size`, `fetch_chain`, `fetch_spot`, `probe` (copy
   `cboe.py`); keep parsing pure (`parse_chain(ticker, payload) -> RawChain`).
2. `backend/tests/test_<venue>.py`: a canned payload in the venue's exact shape
   through `ExchangeChainProvider(..., fetch_json=FakeFetch)` (copy
   `test_cboe.py`), plus the `VOLFIT_LIVE`-gated live test.
3. `serve.py`: register `"<venue>": ExchangeChainProvider(tickers, VenueAdapter())`,
   place it in `_AUTO_ORDER`; `api/datasource.py` `SOURCE_LABELS`;
   `restart.ps1` switch.
