# Bloomberg data source — setup & troubleshooting

Short operator note for getting the Bloomberg (`xbbg`) source live and reading
the Data Source light. For the full help-desk write-up of the current
entitlement gate, see
[`bloomberg_workflow_review_account.md`](bloomberg_workflow_review_account.md).

## Prerequisites

- A **running, logged-in Bloomberg Terminal** on the same machine (Desktop API
  / DAPI, `localhost:8194`).
- Python packages in the venv: `xbbg` (the pyo3 1.3.0 engine) and `blpapi`
  (3.26.x). Both are already installed; `pip install xbbg blpapi` if not.

## Running with Bloomberg

```powershell
.\restart.ps1 -Bloomberg     # force Bloomberg active on launch
.\restart.ps1                # auto-pick best reachable (Bloomberg > Yahoo > Massive > Synthetic)
```

All sources are always registered; the in-app **Data Source** selector (TopBar)
switches between them at runtime and shows a status light each. `restart.ps1`
captures the backend to `backend/data/serve.{out,err}.log` and waits for `:8000`
to bind, so a startup failure is visible rather than a vanishing window.

## Real-time streaming (quota-free push feed)

Every `bdp` / `bds` is a METERED reference-data request (the Terminal's daily
quota); polling a chain of hundreds–thousands of contracts every few seconds
is slow and self-limiting. The Desktop API also has a genuine PUSH channel —
the `//blp/mktdata` **subscription** service — and the Bloomberg source uses it
as its live book (`volfit/data/bloomberg_stream.py` book + blpapi transport,
`bloomberg_decode.py` message decode, `bloomberg_live.py` provider mixin):

- When Bloomberg is the **active** source and *Options ▸ Stream live book* is on
  (default) — or spot mode is *Real-time* — `AppState.sync_streaming` subscribes
  the universe's contracts **and their underlyings** (`BID,ASK,LAST_PRICE,VOLUME`,
  conflated with `interval=1.0`); Bloomberg then pushes updates. While it streams,
  **`fetch_chain(live)` and `spot()` issue no `bdp` at all** — every Fetch /
  Calibrate / real-time spot poll / 5 s stream refit reads the in-memory book.
  Metered calls left: the chain listing — one `OPT_CHAIN` (monthlies + LEAPS,
  both sides) plus one `CHAIN_TICKERS` per series (`CHAIN_PERIODICITY_OVRD`
  "W" weeklies + dailies, "Q" quarterlies, each with `CHAIN_EXP_DT_OVRD=ALL`
  and the `CHAIN_POINTS_OVRD` count cap; calls only, puts mirrored, the
  yellow key appended — live-verified 2026-09-02; `volfit/data/
  bloomberg_listing.py`) — **once per ET exchange day** per ticker, persisted
  under `backend/data/cache/bloomberg/<TICKER>_<YYYY-MM-DD>.json`
  (`VOLFIT_CACHE_DIR` overrides the root; a restart inside the day re-lists
  nothing; `refresh_contracts()` / `refresh_chain_cache()` drop memory + file)
  — and one `PX_LAST` to centre the strike window per ticker.
- **Book first** (2026-09-24): while streaming, a live fetch waits up to
  `VOLFIT_BBG_BOOK_WAIT` s (default 5; constructor `book_first_wait`) for the
  underlying's paint AND the selection's coverage (an edited selection is
  resubscribed on the next scheduler tick) before it even considers the
  metered fallback — a refused underlying short-circuits the wait.
  `VOLFIT_BBG_BOOK_ONLY=1` (`book_only`) forbids the fallback altogether: an
  uncovered fetch raises ("retry once it is subscribed") and never costs a
  hit. Any paint read off the book — like any answered `bdp` / `bds` — clears
  a stale refusal from the light (it used to show "workflow review needed"
  all morning while the book streamed).
- **One option root per expiry date** (`volfit.data.bloomberg_roots`,
  2026-09-09). The chain union can list one date under several roots that are
  different instruments: Eurex's weekly `WSX5EB` and daily `SX5EODJ` both
  expire Friday 2026-09-11 (the weekly and the daily settle at different
  instants and price ~15 % apart), the monthly `SX5E` and the daily `SX5EODO`
  on the 18th; SPX and SPXW on every third Friday. Keeping both stacked two
  smiles on the SX5E 2-day slice (125 bp rms, an "ATM discontinuity", a
  16 %/yr parity discount). The provider now keeps ONE root per date — the
  parent root when it lists the date, else the root whose median-strike call
  carries the larger open interest (one small `OPEN_INT` bdp over the
  contested dates' representatives, cached with the chain; a refused probe
  falls back to the root with more strikes, then the first listed) — logs the
  dropped root, and reads each expiry's settlement convention from the kept
  root (SPX AM on the monthlies, SPXW PM on the weeklies). The (date, root)
  expiry key stays the recorded redesign.
- Subscription budget: the Desktop API caps concurrent real-time subscriptions
  per Terminal. Contracts are windowed **per expiry** by the shared rule of
  `volfit/data/strike_window.py` (`strike_window="auto"`, the default since
  2026-09-24): keep |ln K/S| ≤ 4 · σ_ref · √T, floored at 5 % and capped at
  S/7.4 … 7.4 S, with σ_ref = 1.0 (`VOLFIT_BBG_WINDOW_SIGMA`). The window
  CONTAINS every quote the prep keeps (its Z_MAX = 4 ATM-sd cut) for any name
  with ATM vol under σ_ref, so the fit is byte-identical with the window on
  or off — while a 2-day rung costs ~±30 % of spot (a few percent of the
  ladder) instead of the old uniform 0.5–1.5 × spot, and a 1-year rung keeps
  the wide band the old band was cutting. A `(lo, hi)` tuple restores the
  legacy uniform band, `None` the whole ladder. The same rule sizes the
  metered pull. Around a centre held with 5 % hysteresis (no restart when
  spot wobbles across a strike), capped at `VOLFIT_BBG_MAX_SUBS` (default
  3000), nearest-the-money first. Over-cap contracts are carried unquoted and
  the status light says "N over cap". Smoke 2026-08-20: SPY + SPX, 2 expiries
  each, 3166 wanted → 2998 subscribed, **0 metered calls** while streaming.
- Universe edits (ticker / expiry selection, a strike-window re-centre, cap
  re-ranking) are applied **incrementally on the live session** on the next
  scheduler tick (≤ 1 s): `update_streaming` subscribes only the new
  securities and unsubscribes only the gone ones (blpapi matches them by
  CorrelationId value) — no session restart, no repaint of the rest, no warming
  gap; the book forgets the dropped contracts. Verified live 2026-08-20:
  +expiry → 20 contracts painted within 2.5 s on the same session; −expiry →
  92 unsubscribed, none re-appeared. An explicit Fetch inside that ≤ 1 s window
  waits for the coverage (book first, above) so it never silently misses
  contracts and never pays for them.
- `OPEN_INT` is not subscribable (reference-only), and since 2026-09-24 no
  fetch requests it either: a chain — streamed or metered — carries the OI /
  volume / last remembered from the last explicit **`enrich_reference(ticker,
  expiries)`** (None before one; see the quota section).
- Quotes and the chain are stamped with the **provider** tick stamps
  (`*_UPDATE_STAMP_RT`), not the wall clock; un-stamped INITPAINT quotes take the
  chain's newest stamp. On a 15-min delayed exchange that reads 15 min behind —
  the honest data age.
- Env knobs (`serve.py`): `VOLFIT_BBG_STREAM_INTERVAL` (conflation s, 0 = every
  tick), `VOLFIT_BBG_MAX_SUBS`, `VOLFIT_BBG_HOST` / `VOLFIT_BBG_PORT` (DAPI
  endpoint, default `localhost:8194`), `VOLFIT_BBG_BOOK_WAIT` (book-first
  seconds, 5), `VOLFIT_BBG_BOOK_ONLY` (1 = never a metered quote pull while
  streaming), `VOLFIT_BBG_WINDOW_SIGMA` (the window's reference vol, 1.0),
  `VOLFIT_CACHE_DIR` (the listing cache root).
- **Live Quote Table**: while streaming, the Smile Viewer's Table tab opens a
  per-node SSE stream (`GET /smiles/{t}/{e}/table/stream`,
  `volfit/api/table_stream.py`) that reads the book (never a `bdp`) at 1 Hz,
  runs the live chain through the table's own `prepare_quotes` pipeline and
  pushes only the rows whose band moved — bid/mid/ask IV and prices tick with
  a flash, the Model IV column stays the fit's, amended rows are pinned, and a
  `● LIVE n · HH:MM:SS UTC · S spot` badge shows the newest provider stamp
  (≈15 min behind on a delayed exchange). Measured: ~26 ms per frame on SPY
  (de-Am included), 0 metered calls. The same connection (one per viewed
  node, hosted by the Smile Viewer) feeds the **Smile Chart**: live bid/ask
  beams in teal over the red calibration quotes, placed by strike. Live IVs
  are inverted at the **live forward** (the node's forward moved by the
  streamed spot under the app's forward-transport rule), so they are the
  market's IVs at today's spot; the table/chart flash only material moves
  (> 0.5 bp) since a spot tick re-expresses every strike.

## Reference-data quota — what a fetch costs (2026-09-24)

Every `bdp` / `bds` / `bdh` is billed as **hits = securities × fields** against
a daily quota, and every security touched counts once toward a MONTHLY
unique-securities budget (~4–5k on this account, which has gated it twice —
"workflow review needed"). Subscriptions are free. The provider therefore
(`volfit/data/bloomberg_fields.py`):

- requests **BID and ASK only** on the live pull — the only fields the fit
  reads; `OPT_EXER_TYP` is read ONCE per ticker per exchange day from one
  representative contract (the median-strike call; the " Index" rule is the
  fallback when the Terminal does not answer it); `LAST_PRICE` / `VOLUME` /
  `OPEN_INT` are the explicit **`enrich_reference(ticker, expiries)`** — one
  bdp, three hits per contract, filling the caches every later chain reads.
  `fetch_chain` never calls it, so on the reference path the Quote Table
  shows OI / volume only after an enrich (a UI action is still to be wired);
- windows the securities **per expiry** (the strike-window rule above) and
  lists the chain once per exchange day (on disk);
- counts everything: **`call_stats()`** = `{day, hitsToday, callsToday,
  uniqueSecuritiesToday, lastFetchSecurities, lastFetchHits, lastFetchWall}`
  (the meter wraps the xbbg module, so the listing, spot, quotes, enrich and
  EOD history all count; a refused request delivers nothing and counts
  nothing). The light's detail carries it: "real-time (Terminal) · 1,805 hits
  today", "streaming 902 · delayed feed · 1,805 hits today".

Measured live (SPY, the two nearest monthlies 2026-10-16 + 2026-11-20, spot
767.81, US market closed): the listing 13,028 contracts / 31 expiries in
11.7 s (3 hits); `fetch_chain` **900 securities, 1,800 hits, 5.81 s** (plus
one PX_LAST and one style hit) versus the morning's **692 securities × 6
fields = 4,152 hits, 5.7 s** — the wall is the round trip, the saving is the
fields. On these monthlies the listed ladder (300 … 1000, 0.39 … 1.30 × spot)
sits INSIDE the auto window, so the window cut nothing there (the legacy
0.5–1.5 band would have kept 832 — and would cut fittable quotes on a long
rung); the window's saving is on the short rungs (a 2-day rung keeps
~±30 % of spot). Streaming plan for the same selection: 900 securities
(auto) vs 832 (legacy band); the second provider listed from the disk file
with zero `bds`.

### `//blp/mktlist` chain membership — tried, not usable (2026-09-24)

A quota-free listing would remove the last metered call of a streaming day.
The Core Developer Guide's chain-membership topics were subscribed on the
live Terminal (subscriptions only, ≤ 20 s each, `//blp/mktlist` opened OK):

| Topic | Result |
|---|---|
| `//blp/mktlist/chain/bsym/US/SPY` | **no message at all in 20 s** (only SessionConnectionUp / SessionStarted / ServiceOpened) |
| `//blp/mktlist/secids/bsym/US/SPY` | `SubscriptionFailure` at 0.0 s: `source="SubscriptionManager" category="CANCELLED" errorCode=0 description="Subscription cancelled"` |
| `//blp/mktlist/chain/ticker/SPY US Equity` | same `CANCELLED` failure at 0.0 s |
| `//blp/mktlist/secids/ticker/SPY US Equity` | same `CANCELLED` failure at 0.0 s |
| `//blp/mktlist/chain/bsym/US/SPY US Equity` | same `CANCELLED` failure at 0.0 s |

No format yielded a single option security, so there is no
`listing_via_mktlist`; the three-`bds` listing (once per exchange day, on
disk) stays the chain source. Probe script: the lead's session scratchpad
(`mktlist_probe.py`), 100.8 s of Terminal time in total.

## Reading the Data Source light

`feed_status()` reports these states (`volfit/data/bloomberg.py`,
`bloomberg_live.py`) — all quota-free (no billable probe on the 30 s poll);
once any hit was spent today, " · N hits today" is appended to every
non-red detail:

| Light | Meaning |
|---|---|
| **green** "real-time (Terminal)" | session up, last on-demand request succeeded (reference path) |
| **green** "streaming N · real-time" | the subscription book is live with real-time ticks |
| **amber** "stream connecting" / "stream warming · N subscribed" | subscriptions being acknowledged / nothing painted yet |
| **amber** "streaming N · no tick stamp yet" | painted (last-known INITPAINT values) but no stamped tick — a session opened outside trading hours: serving, not moving |
| **amber** "streaming N · delayed feed (SPY)" | the stream is live but the named underlyings' exchanges are delayed (non-entitled — US equities on this Terminal; SPX is real-time) |
| **amber** "stream idle since HH:MM UTC" | newest tick > 20 min old (pre-market / closed) — the book keeps last ticks |
| **red** "stream: &lt;reason&gt;" | an underlying's subscription was refused (`NOT_ENTITLED`, `BAD_SEC`…) or the session failed |
| **red** "no Terminal" | no blpapi session (Terminal closed / not logged in / xbbg missing) |
| **red** "&lt;reason&gt;" | session connected but Bloomberg **refused** the request — the real `responseError` reason, e.g. `workflow review needed`, `not entitled`, `daily request limit reached` |

The last case is the important one: **the Terminal is fine; the account is
gated.** No code change clears it — it's resolved on the Bloomberg side.

## One-line probe (does the Terminal answer?)

```powershell
.venv\Scripts\python -c "from xbbg import blp; print(blp.bdp('SPY US Equity','PX_LAST'))"
```

- Prints a price → entitlements are good; the app will show Bloomberg green.
- Raises `responseError ... subcategory=WORKFLOW_REVIEW_NEEDED` (or similar)
  → connected but gated; take the
  [help-desk account](bloomberg_workflow_review_account.md) to Bloomberg.
- Raises a connection/session error → Terminal not running or not logged in.

## Notes

- The pyo3 `xbbg` logs each *failed* request at WARN to stderr; the provider
  calls `xbbg.set_log_level('error')` (`quiet_xbbg_logs`) on first use to keep
  the console clean — a failed probe is reported via the status light, not spam.
- Dividends: on a Bloomberg-active launch, `serve.py` best-effort imports each
  watchlist ticker's `DVD_HIST_ALL` schedule into its market settings (discrete
  cash dividends for the forward / de-Americanization model).
- Symbol search uses the `//blp/instruments` service (free-text → securities),
  falling back to a substring/echo search if that service is unavailable.
