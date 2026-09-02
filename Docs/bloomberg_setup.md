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
  yellow key appended — live-verified 2026-09-02) — and one `PX_LAST` to
  centre the strike window, per ticker, per 10-minute chain cache.
- Subscription budget: the Desktop API caps concurrent real-time subscriptions
  per Terminal. Contracts are windowed to `strike_window` (default 0.5–1.5 ×
  spot) around a centre held with 5 % hysteresis (no restart when spot wobbles
  across a strike) and capped at `VOLFIT_BBG_MAX_SUBS` (default 3000),
  nearest-the-money first. Over-cap contracts are carried unquoted and the
  status light says "N over cap". Smoke 2026-08-20: SPY + SPX, 2 expiries each,
  3166 wanted → 2998 subscribed, **0 metered calls** while streaming.
- Universe edits (ticker / expiry selection, a strike-window re-centre, cap
  re-ranking) are applied **incrementally on the live session** on the next
  scheduler tick (≤ 1 s): `update_streaming` subscribes only the new
  securities and unsubscribes only the gone ones (blpapi matches them by
  CorrelationId value) — no session restart, no repaint of the rest, no warming
  gap; the book forgets the dropped contracts. Verified live 2026-08-20:
  +expiry → 20 contracts painted within 2.5 s on the same session; −expiry →
  92 unsubscribed, none re-appeared. An explicit Fetch inside that ≤ 1 s window
  falls back to the metered path so it never silently misses contracts.
- `OPEN_INT` is not subscribable (reference-only): a streamed chain carries the
  OI remembered from the last metered fetch (None before one).
- Quotes and the chain are stamped with the **provider** tick stamps
  (`*_UPDATE_STAMP_RT`), not the wall clock; un-stamped INITPAINT quotes take the
  chain's newest stamp. On a 15-min delayed exchange that reads 15 min behind —
  the honest data age.
- Env knobs (`serve.py`): `VOLFIT_BBG_STREAM_INTERVAL` (conflation s, 0 = every
  tick), `VOLFIT_BBG_MAX_SUBS`, `VOLFIT_BBG_HOST` / `VOLFIT_BBG_PORT` (DAPI
  endpoint, default `localhost:8194`).
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

## Reading the Data Source light

`feed_status()` reports these states (`volfit/data/bloomberg.py`,
`bloomberg_live.py`) — all quota-free (no billable probe on the 30 s poll):

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
