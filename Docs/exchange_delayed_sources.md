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

Registered in `serve.py` as source ids `cboe`, `nasdaq`, `asx`, `hkex`,
`sgx` and `eurex` (auto-pick order: Bloomberg → **Cboe** → **Nasdaq** →
**ASX** → **HKEX** → **SGX** → **Eurex** → Yahoo → Massive → Synthetic);
launch `.\restart.ps1 -Cboe` / `-Nasdaq` / `-Asx` / `-Hkex` / `-Sgx` /
`-Eurex` to force one; the in-app Data Source selector lists them as
"<Venue> (delayed)" (Eurex: "Eurex (delayed / EOD)").

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

## Shipped — ASX (Australia) ✅ `volfit/data/asx.py` — the first non-US venue

| | |
|---|---|
| Coverage | every ASX-listed option class: the S&P/ASX 200 index (XJO, European) and the single-stock classes (BHP, CBA, …, American) |
| Endpoints | `https://asx.api.markitdigital.com/asx-research/1.0/derivatives/equity/{CODE}/options` (→ `datesAvailable` monthly/weekly/quarterly, `underlyingAsset{symbol, issueType "IN" = index, priceLast}`, nearest expiry's groups) and `…/options/expiry-groups?expiryDates=D1&expiryDates=D2…` (**repeated** param — the site's own selector, mined from the ASX F2 app bundle; plain `expiryDate=` is ignored) → `data.items[] {date, exerciseGroups[] {priceExercise, call{…}, put{…}}}` |
| Fields | per series `priceBid / priceAsk / priceLast / openInterest / volume / style ("European"/"American") / dateExpiry / symbol / optionRoot / contractSize` (10 for XJO, 100 for stocks); prices per unit (index points / AUD); 0 = no quote; a class's style = the majority of its series |
| Stamp | none served → chains stamped `now − 20 min` (ASX's stated delay) |
| Delay | ~20 min |
| Size / speed | XJO 13 expiries / 993 strikes in ONE 0.7 MB call (~1.8 s); two requests per chain (dates + groups), cached |
| Symbols | `XJO`, `^XJO`, `XJO.AX`, `BHP`, `BHP.AX` |
| Verified | 2026-08-21: status amber 0.9 s; XJO 590 quotes / 445 two-sided European, BHP 88 / 73 American; through the app XJO 3-Sep fit (36 quotes, ATM 10.05 %), BHP 3-Sep fit (28 quotes) — after-hours Sydney quotes, so wide |
| Side effect | the universe's default expiry seed was US-calendar only (3rd-Friday monthlies, Mon/Wed/Fri weeklies) → empty for ASX's Thursday expiries; `expiry_select.default_selection` now falls back to a calendar-agnostic ladder (two near rungs + the first expiry of each further month, ≤ 10, ≤ 18 months) |
| Caveats | the settlement clock (`expiry_time.default_settlement`) is US-centric — Sydney expiry instants are off by hours (fine-tuning item); tick size unknown per class → no tick floor |

## Shipped — HKEX (Hong Kong) ✅ `volfit/data/hkex.py`

| | |
|---|---|
| Coverage | the index classes HSI (+ MHI mini), HSCEI (`HHI`), Hang Seng TECH (`HTI`) — European — and every stock-option class (TCH = Tencent, ALB = Alibaba, MET, HEX, …) — American |
| Endpoints | the exchange's own widget, JSONP only (`callback=` mandatory, plain JSON → 403): `www1.hkex.com.hk/hkexwidget/data/getoptioncontractlist?ats=HSI&type=0` (contract months `082026…`), `getderivativesoption?ats=HSI&con=082026&fr=null&to=null` (near-the-money + the month's `min`/`max`) then `fr=min&to=max` (the full ladder — a month's own window, another month's returns nothing), `getderivativesfutures` (stock-future last = stock spot proxy), `getmarketmarquee?sym=.HSI;.HSCE;.HSTECH` (index spot + HKT time), `getderivativesinfo` (`idx` flag) |
| Token | embedded in the public product page (`LabCI.getToken = function () { … return "<token>"; }` — the LAST return; the first is a commented sample); scraped once, cached, re-scraped on a non-`000` response |
| Fields | per strike `c{bd, as, ls, vo, oi, iv}` / `p{…}`, `""` = no quote, thousands separators; `lastupd` HKT → UTC stamp |
| Expiry | the business day before the last business day of the contract month (HKEX rule; HK holidays not modelled) |
| Delay | ~15 min; 2 small calls per month (13 months ≈ 4–8 s, threaded), cached by the provider |
| Symbols | `HSI`/`^HSI`, `HSCEI`/`HHI`, `HSTECH`/`HTI`, `MHI`; stocks `700` / `0700.HK` / `TCH` (built-in map for the large caps, raw class codes pass through) |
| Verified | 2026-08-21 (after the HK close): HSI 13 months listed (8 within 2 y), 126 quotes across two expiries (16 two-sided — evening), spot 26,009.46 European; TCH 83 quotes / 45 two-sided American, spot proxy 457.10; app fits TCH (29 quotes); HSI fit needs the intraday two-sided book |
| Caveats | after-hours the index chains are mostly one-sided; token page is ~1 MB (scraped rarely); US-centric settlement clock (HK instants off by hours) |

## Shipped — SGX (Singapore) ✅ `volfit/data/sgx.py`

| | |
|---|---|
| Coverage | SGX Nikkei 225 Index Options (`NK`; weeklies NKWE/NKWC not handled — keyed by week), FTSE China A50 (`FCH`), FTSE Taiwan (`TWN`), MSCI Singapore (`SGP`) — European |
| Endpoints | `api.sgx.com/derivatives/v1.0/metalist?category=options&derivatives-kind=equityindex` (contracts), `cc/{CODE}?category=options&params=delivery-month` (38 months for NK), `cc/{CODE}?category=options&delivery-month=YYYY-MM&session=0` (one row per strike: `call-/put- best-bid-price / best-ask-price / last-trade-price / open-interest / total-volume`, `updated-time` ms, `price-fractional-indicator`), `cc/{CODE}?category=futures&…` (front future `last-traded-price-adj` = spot proxy — the Nikkei index itself is not an SGX instrument — and `last-trading-date`) |
| Expiry | the futures month's `last-trading-date` when listed, else the contract rule (NK: the day before the 2nd Friday = OSE SQ; others: second-last business day) |
| Stamp | newest `updated-time` (UTC); ~10-min delayed; 18 nearest months fetched on a thread pool (~2 s) |
| Prices | index points (real units on the option rows; the futures rows also carry ×100 "fractional" variants next to the `-adj` real ones); a guard de-scales any option quote above 1.5 × the underlying |
| Symbols | `NK` / `NIKKEI` / `N225` / `^N225` / `NKY`, `FCH` / `A50`, `TWN`, `SGP` |
| Verified | 2026-08-21 evening SGT: status amber, NK 2 nearest months with (stale) quotes, spot proxy 66,065 from NKU26; the T-session two-sided book and the price units must be re-checked during the SGT day (08:30–18:00 SGT) |

## Shipped — Eurex (Europe) ✅ `volfit/data/eurex.py` — two tiers: delayed quotes + the EOD settlement surface

| | |
|---|---|
| Coverage | the Eurex index option classes, European: EURO STOXX 50 (`OESX` / `SX5E` / `^STOXX50E`, id 69660), DAX (`ODAX` / `DAX` / `^GDAXI`, 70044), STOXX Europe 600 (`OSTX` / `SXXP`, 70284); any other product by its **numeric** id (bare number as ticker; read `"productId": N` in the product page's JSON — the code itself is refused, "No product found for productId: OESX") |
| Endpoint | ONE JSON API behind the product pages' Prices/Quotes + Statistics tabs (headless-Edge capture + the `prices-statistics` bundle's request builder): `https://www.eurex.com/api/v1/overallstatistics/{id}?filtertype=overview[&busdate=YYYYMMDD]` → `header {underlyingClosingPrice, tradingDates[newest first], volume, openInterest, putCallRatio}` + `dataRows[] {date "20260918", contractType M\|W\|E, call/put volume & OI}` (one row per EXPIRY — exact dates, no calendar rule); `…?filtertype=detail&productdate=YYYYMMDD&contracttype=M[&busdate=…]` → `dataRowsCall / dataRowsPut [] {strike, versionNumber, volume, openInterest, open, high, low, last, dSettle[, bid, bidVol, ask, askVol, lastTraded]}` |
| busdate | omitted = the last COMPLETED business day (server default); today's date answers empty rows once the session is over |
| Tiers | **intraday** (09:00–17:30 CET): rows carrying `bid`/`ask` (the bundle's quote columns, "Displayed data is 15 minutes delayed") → two-sided quotes stamped now − 15 min; **EOD** (anything without a book): Eurex's daily settlement `dSettle` — a model-smoothed fair value published for EVERY series — → zero-width quotes bid = ask = settle stamped at the busdate's 17:30 CET close, next to the underlying's own close (`underlyingClosingPrice`): a coherent end-of-day surface; `settlement_quotes=False` keeps them last-only. The selector status names the tier served: "Eurex ~15-min delayed" / "Eurex EOD settlement (2026-08-20)" (adapter hook `status_text()`, honoured by `ExchangeChainProvider.feed_status`) |
| Fields | zeros mean "no value" (last/open/high/low 0.0 on untraded series); `versionNumber` ≠ 0 (corporate-action-adjusted series) skipped; prices EUR per unit (index points) |
| Size / speed | 1 overview + 1 detail call per expiry (~10 kB each, threaded ×8, ≤ 40 nearest): OESX 26 expiries within 2 y in ~17 s cold (server-side pacing), ODAX 13 in 8 s, OSTX 16 in 11 s; cached 60 s by the provider |
| Verified | 2026-08-21 (after the 17:30 CET close): status amber 0.4 s; OESX 396 settlement quotes across the first two expiries (all two-sided, zero-width), spot 6,422.06, stamp 2026-08-20 15:30 UTC; ODAX 534 quotes, spot 25,983.04; OSTX 254, spot 650.35; ATM OESX Sep-26 6425 C settle 51.3 vs last 46.4 — **the intraday bid/ask tier is inferred from the app bundle (same detail rows during the session) and still has to be eyeballed on a trading day** |
| Caveats | intraday the spot stays the previous close (`underlyingClosingPrice`) until a live underlying read is found; stock-option classes need their numeric ids (not mapped yet); US-centric settlement clock |

## Not feasible now — Korea (KRX)

KRX's data portal (`data.krx.co.kr`) answers scripted `getJsonData.cmd` calls with `LOGOUT`/400 without its session/OTP dance and the page itself times out in headless Edge (60 s); `global.krx.co.kr` derivatives pages 404; Naver Finance's option pages moved (404 at the known paths). KOSPI 200 option quotes therefore need either KRX's OTP session flow (EOD statistics) or a maintained Korean-portal scrape — parked.

## Probed in depth 2026-08-21 (headless-Edge XHR capture, `frontend/scripts/capture_xhr.mjs`)

| Venue | What the page really calls | Finding | Verdict |
|---|---|---|---|
| **Euronext** (AEX index options `index-options/AEX/DAMS`, CAC `PXA/DPAR`, weeklies `AX1…`, stocks) | `POST live.euronext.com/en/ajax/getPricesOptionsAjax/{type}/{class}/{exchange}` with `md[]=<DD-MM-YYYY first-of-month>&ps=11\|999`, `X-Requested-With`; `getPricesOptionsForm/{class}/{exchange}` lists the maturities; `getUnderlying/{class}/{exchange}/options` = spot. JSON `simple[i].data[]` rows `c_bid/c_ask/c_last/c_settl`, `strike`, `p_*`; `extended[i].rowc/rowp` add volume/OI/last time. | The origin IGNORES `md[]`/`ps` for anonymous callers — the page's OWN XHR (driven headlessly, CloudFront misses) still returns the nearest maturity with 11 ATM strikes: a teaser. The full chain needs a logged-in Euronext Live session (an adapter could take the session cookies from an account). | **Gated** — adapter ready to write once a session cookie is available; per-instrument pages exist but are one request per series. |
| **ICE Futures Europe** (FTSE 100 options) | `www.ice.com/marketdata/api/productguide/charting/contract-data?productId=&hubId=` + `…/data/current-day?marketId=` (FUTURES only); the legacy `DelayedMarkets.shtml?get…AsJson` answer 403 for scripts; the option product page redirects to the future's data tab. | Options quotes moved behind ICE market-data subscriptions; only futures charts and the public EOD settlement reports (`/marketdata/reports/…`) remain. | **No delayed option quotes**; EOD settlements possible (no bid/ask). |

## Candidates — probed 2026-08-21

| Venue | What is public | Bid/ask? | Verdict |
|---|---|---|---|
| **TMX Montréal (Canada)** `m-x.ca/en/trading/data/quotes?symbol=XIU*` | HTML table (bid/ask/last/volume/OI per series), ~2 MB page | ✅ (HTML) | feasible — an HTML-table scrape (lxml/regex); fragile to page redesigns |
| **Eurex (Europe)** `eurex.com/api/v1/overallstatistics/{productId}` | JSON — the SAME endpoint feeds the Prices/Quotes tab (bid/ask columns intraday) and the Statistics tab (settlement / volume / OI per series) | ✅ intraday (15-min), settlement EOD | **SHIPPED** — see "Shipped — Eurex" above |
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
