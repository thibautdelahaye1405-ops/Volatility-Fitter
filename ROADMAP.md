# Vol-Fitter — Development Roadmap

Implied-volatility fitter (à la VolaDynamics) with a differentiating feature:
**extrapolation of sparse smile observations to the full universe of smiles**
(across expiries and assets) by propagating signal through a graph whose nodes
are smiles `(underlying, T)`, using the OT-regularized Bayesian solver of
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`.

---

## STATUS — updated 2026-06-15 (resume here)

**Done & verified (471 pytest tests green incl. 4 perf + 1 live-optional skipped, `git log --oneline` tells the story):**

- **[2026-06-15] Massive feed Tier 2 — flat-file history (LIVE-VERIFIED)**: the
  long-deferred columnar history. **Verified end-to-end** with the user's S3 key
  against `files.massive.com` (bucket `flatfiles`, prefix `us_options_opra`,
  products `day_aggs_v1`/`minute_aggs_v1`, `…/YYYY/MM/YYYY-MM-DD.csv.gz`): day-aggs
  rebuilt a 6,319-quote / 35-expiry SPY close chain (parity spot 741.56) in ~3s,
  minute-aggs a 6,240-quote chain at 15:55 ET, and a full-pipeline fit of SPY
  2026-07-17 as-of EOD 2026-06-12 gave atmVol 15.62% / skew −0.79 / rms 35bp. Two
  real-S3 bugs fixed in the process: DuckDB only binds a `?` parameter in the LAST
  statement of an execute (each `SET …=?` is now its own call), and the endpoint is
  normalized to DuckDB's bare-host + `s3_use_ssl` form (`_split_endpoint`). Default
  endpoint is now `files.massive.com`.
  `data/occ.py` parses OCC/OPRA option tickers (the flat files carry only the
  `O:` symbol → strike/expiry/type). `data/flatfiles.py` `FlatFileStore` uses
  DuckDB (+bundled httpfs) to read the gzipped daily aggregate CSV from the S3
  bucket, filter to the watchlist roots, cache the day to local Parquet, and
  reconstruct a `ChainSnapshot` at an instant (minute aggs = past intraday, day
  aggs = official Close; zero-spread close, parity spot). It belongs to
  `MassiveProvider` (`flat_store=`), so the as-of layer is untouched:
  `historical_modes` gains `eod`, `available_history` lists ~20 recent weekdays,
  and `fetch_chain(as_of=)` routes eod→day-aggs / past-day-intraday→minute-aggs
  (today-intraday stays REST). serve.py `_flat_store()` builds it from env
  (`VOLFIT_FLATFILES_KEY`/`_SECRET` +optional endpoint/bucket/prefix/cache); duckdb
  is an optional `flatfiles` extra, imported lazily. 19 new offline tests (occ ×11,
  flatfiles ×5 via a local gzip-CSV fixture duckdb reads for real, Massive wiring
  ×3). See the priority-track Tier 2 entry for what live-verify still needs.

- **[2026-06-15] Massive feed Tier 0+1 LIVE-VERIFIED + delayed-cluster WS
  fallback**: with the user's key, `massive_diag.py SPY` confirmed the REST feed
  end-to-end on both hosts (api.massive.com / api.polygon.io): contracts+snapshot
  HTTP 200, two-sided NBBO (`fetch_chain` → 376 quotes / 308 two-sided),
  `underlying_asset.price`=755.21, and the **stocks plan is entitled** (so the
  IV-fallback isn't needed here). **WS finding:** the real-time cluster
  `wss://socket.massive.com/options` connects+auths but is **silent** (no
  subscribe-ack, no quotes) — this key is a **delayed** tier; the delayed cluster
  `wss://delayed.polygon.io/options` auths, acks the subscribe, and streams live
  SPY NBBO. So `MassiveWebSocket` now takes a **candidate URL list** and
  auto-advances past a silent cluster (per-frame `quote_grace`, default 6s) to one
  that streams — works for both real-time and delayed keys.
  `MassiveProvider._ws_urls()` = `[override-or-derived primary,
  wss://delayed.polygon.io/options]`; override via `VOLFIT_MASSIVE_WS_URL` (read by
  serve.py) — **set it to the delayed URL on this key to skip the ~6s warmup on the
  dead real-time cluster.** Live-verified: the book fills from the delayed cluster
  and `fetch_chain(live)` serves REST while the book is cold. 2 more tests (candidate
  list + silent-cluster advance).

- **[2026-06-15] Massive feed Tier 1 finish (the three code sub-tasks of the WS
  live book)**: (1)
  **Contract-listing cache** — `MassiveProvider._intraday_contracts` is cached per
  `(ticker, frozenset(expiries))` (`refresh_contracts()` invalidates), so the WS
  read path (`_chain_from_book`/`option_tickers`) and the per-tick resubscribe diff
  no longer re-paginate the contracts reference each call. (2) **Resubscribe on
  universe change** — `AppState.sync_streaming` now diffs the desired contract set
  (`_desired_stream_contracts`) against the provider's live subscription
  (`MassiveProvider.streaming_contracts()` / `MassiveWebSocket.contracts`) and
  restarts the stream when a ticker/expiry edit changes it (was source/mode-change
  only); providers that can't report their subscription are never thrash-restarted.
  (3) **Throttled full-refit loop** — a new `Scheduler.tick` branch gated by
  `AppState.is_streaming()` **AND `autoCalibrate`** calls `workflow.stream_refit`
  every `OptionsSettings.streamRefitSeconds` (default 5s, frontend type seeded)
  while a live book streams: refetch chains from the book + recalibrate ALL lit
  nodes in the background. **`autoCalibrate` is the master switch for unattended
  refits** — with it OFF the streaming loop is a no-op (the surface still tracks
  spot via the transport poll; nodes stay frozen/stale until an explicit Calibrate),
  matching `fetch_options`. [Corrected 2026-06-15: an earlier cut wrongly bypassed
  `autoCalibrate`, so realtime kept recalibrating with the toggle off.] Distinct
  from the minutes-cadence `optionsFetchMode=="auto"` REST refetch. 5 new offline
  tests (cache hit/invalidate, sync_streaming resubscribe, scheduler
  refit-only-while-streaming, stream_refit refetch+calibrate). ruff + strict-TS
  build green. **Live-unverified** (no Massive key in this environment).

- **[2026-06-15] UI crash hardening (error boundary + null-safe diagnostics)**: a
  per-view **ErrorBoundary** (`components/ErrorBoundary.tsx`, keyed by tab) so a
  render crash shows a recoverable card + logs the stack instead of white-screening
  the app. It pinpointed the real-time-spot crash: a **transported** slice is
  finite near ATM but non-finite at the far wings (±6) where the numeric Lee-slope
  / var-swap diagnostics evaluate it → NaN → JSON `null` → `null.toFixed()` crashed
  `SmileAside`. Fixed both layers — backend `numeric_handles`/`numeric_lee_slopes`/
  `numeric_var_swap_w`/`_max_iv_error` coerce non-finite → finite; frontend
  `SmileAside` renders "—" for null/NaN and `formatPct` is null-safe. Massive spot
  now resolves via the upgraded stock plan (`underlying_asset.price` / stocks
  endpoint), with parity-forward as fallback.

- **[2026-06-15] Massive real-time WebSocket live book (feed workflow phase 1)**:
  first tier of the Massive feed design (3 tiers: **WS live book** for RT · **S3
  flat files** [minute/day aggregates → DuckDB/Parquet] for past days · **REST**
  gap-fill). `volfit/data/massive_ws.py`: a pure thread-safe `LiveBook`
  (`{O:ticker → bid/ask}`, parses Polygon `Q` events) + `MassiveWebSocket` — a
  daemon thread running an asyncio client (`websockets` 16, already installed)
  that connects to the options cluster, auths, subscribes to the active
  universe's `Q.O:…` channels and folds quotes into the book; injectable
  `connect` for offline tests; capped-backoff reconnect. `MassiveProvider`:
  `start_streaming`/`stop_streaming`/`is_streaming`, `option_tickers`, and
  `fetch_chain(live)` now serves from the book (`_chain_from_book`, spot via
  parity) with a REST fallback until the book warms. `AppState.sync_streaming()`
  (called each scheduler tick) starts the stream when Massive is active in
  realtime mode and stops any orphaned stream on source/mode change. 7 tests
  (book parsing, the asyncio session via a fake conn, book-served chain, ws-url,
  sync_streaming). **Live-unverified** (needs the user's key); throttled full-
  refit cadence + flat-file history are the next steps. The surface updates on
  the existing realtime spot-poll (reads the book) between Calibrates.

- **[2026-06-15] Massive fits on the base tier (IV fallback) + As-of Prev-Close
  discoverability**:
  * **Fit Massive from its IVs without the paid NBBO add-on.** When the live
    snapshot has no two-sided `last_quote` (gated) but still carries Massive's
    per-contract `implied_volatility` (entitled), `MassiveProvider.fetch_chain`
    auto-falls-back to `_chain_from_iv`: each contract is priced from its IV with
    `core.black.black_call` at forward = spot, DF = 1 (`_price_from_iv`, puts by
    parity), quoted bid = ask = price and marked **european** (no de-Am of a clean
    Black value). The fitter re-inverts those prices and recovers exactly Massive's
    IV smile (exact at zero carry; a tiny shift otherwise) — verified end-to-end
    (atmVol 0.2003 vs 0.20 input). Toggle `iv_fallback` (default on). Needs the
    underlying price (present in the option snapshot) + ≥3 strikes paired call/put
    (real chains have both). 2 tests. NB this fits *Massive's reported* IVs, not an
    independent inversion.
  * **As-of "Previous Close" explicit again**: the day→moment dropdown now shows a
    top-level **Previous Close** row when the source supports `prev_close`
    (Bloomberg/Massive), plus a "this source serves live data only" hint for
    live-only sources (**Yahoo** — it has no option-chain history, so it never
    offered closes; that was not a regression). `useAsOf` gained `setPrevClose`.

- **[2026-06-15] As-of selector reworked to day → moment**: the As-of dropdown is
  now a two-level pick — choose a recent business **day**, then a **moment** within
  it: **Close** (official EOD), **Latest snapshot**, or **N min before close**
  (preset 15/30/60). Backend (`api/asof.py`): `asof_payload` returns the recent
  business days that have data, each flagging `hasClose` / `hasCaptures` /
  `intraday`; `set_moment` + `_resolve_moment` map a (day, moment) to a concrete
  selection — close→`eod`/`prev_close`, latest→newest capture, before_close→the
  capture nearest at-or-before `market_close_utc(day) − N` (16:00 ET via zoneinfo,
  DST-correct, with a fixed-offset fallback). `AsOfSelection` gained display
  metadata (`day`/`moment`/`offset`); `AsOf` + state gained an `intraday` mode.
  Intraday moments come from captured snapshots for Yahoo/Bloomberg; **Massive
  fetches the instant from Polygon `/v3/quotes`** (`intraday_capable`,
  `_fetch_intraday` — per-contract historical NBBO + underlying mid; offline-tested
  via injected `http_get`). POST `/asof` accepts the new `{mode:"moment", on,
  moment, offsetMinutes}` and still the legacy `{mode:"eod"|"captured"|…}`.
  Frontend: `useAsOf` (days + `setLive`/`setPrevClose`/`setMoment`) and a TopBar
  accordion (Live · **Previous Close** when the source supports it · then each day
  expands to its available moments; a "live data only" hint when the source has no
  closes — e.g. Yahoo). 6 new tests (resolution, DST close, Massive intraday).
  Verified end-to-end over HTTP. NB historical/close moments need a provider that
  serves them: **Yahoo is live-only** (no option-chain history), **Bloomberg** does
  live+prev_close+eod (needs an open Terminal), **Massive** does prev_close + the
  intraday fetch but its chain quotes need the paid NBBO entitlement (the contracts
  reference that fills the expiry picker is free, so the picker can list expiries
  the fitter then can't price → "0 selected").

- **[2026-06-15] False "Mock Data" — the actual root cause + ROBUST fallback**:
  the decisive trigger was a backend **500 on `/smiles`**, not a connectivity
  problem. `models/lqd/basis.lee_slopes` did `1/A_R` where a degenerate
  sparse-data fit (a far-dated QQQ node with the stale custom expiry picks carried
  over from a source switch) drove `R≈-1000`, **underflowing `A_R = exp(R+…)` to
  exactly 0.0** → `ZeroDivisionError` → `/smiles` 500. The universe loaded ("Live"
  for a moment), then the first smile fetch 500'd and the old frontend dropped to
  mock. Fix: `lee_slopes` guards the reciprocals and takes the finite limits
  (`psi(1/A−…) → 0` as `A → 0`; verified live — the two far-dated QQQ nodes now
  return 200). `test_lee_slopes_handle_underflowed_endpoint_scales`.
  Plus the mock payload is now reserved for a genuinely UNREACHABLE backend; a
  reachable backend with no data / a node-level error never trips it:
  * **Smile fetch never mocks (`useSmile.ts`)**: a failed `/smiles` retries a few
    times (chain may be warming) then, if still failing, stays LIVE and surfaces
    the error in the chart ("Couldn't load this smile: …") — never the mock badge.
  Three more layers (already this day):
  * **Frontend never latches onto mock (`state/useSmile.ts`)**: the mount path
    became a *retry loop*. `/universe` 200-but-all-ladders-empty (active provider
    warming up / Yahoo throttling a fresh process / a momentarily capped feed) is
    treated as "reachable, no data yet" — stay on the live source, show a
    "Connecting to market data…" state, and re-poll every `UNIVERSE_RETRY_MS`
    (2.5 s) until a ladder appears. Only a thrown request (connection refused)
    falls to mock, and even then it keeps polling so a backend that comes up
    reconnects automatically. The old code dropped to mock the instant the first
    payload was empty and never re-checked — the root of the recurring restart
    bug. (`sourceRef` lets the poll read the live source without restarting.)
  * **Backend serves 200 under provider failure** (already landed earlier this
    day): `AppState.snapshot()` degrades a raised provider fetch to an empty
    uncached snapshot, so `/universe` never 500s.
  * **Startup auto-pick lands on a source that SERVES** (`serve._pick_active` +
    new `_can_serve`/`_bounded`): now that `feed_status` is a cheap connectivity
    check (the Bloomberg quota fix), a connected-but-capped Bloomberg would read
    green and be auto-picked → empty surface. `_pick_active` now additionally
    verifies each non-synthetic candidate can resolve a non-empty ladder for its
    first ticker (retried a few times to tolerate a transient Yahoo throttle; a
    hard cap/gate fails every attempt and is skipped), falling through to the
    next source and finally synthetic. The probe shares the app's provider
    instance, so a successful enumeration warms its chain cache (no extra call).
    4 tests (`test_serve_pick.py`).

- **[2026-06-15] Bloomberg daily-cap drain + Fetch-button gauges**:
  * **Status light no longer burns the Bloomberg quota.** The Data Source
    selector polls `GET /datasources` every 30 s, and Bloomberg's `feed_status()`
    was firing a real `bdp(PX_LAST)` on every probe → ~120 billable ref-data
    hits/hour purely for the light, independent of the On-demand fetch settings —
    that drained the daily cap. `feed_status()` is now a CHEAP, quota-free probe:
    it reads the blpapi session (`session_connected()` / `is_connected()`, no data
    request) and the cached outcome of the last *on-demand* fetch. New
    `BloombergProvider._last_error` + `_record(exc)`: `fetch_chain` (the on-demand
    path, covering the spot probe via `provider.spot`) records a connected-but-
    refused reason (entitlement / *workflow review* / *daily capacity reached*) and
    clears it on success; benign ValueErrors (no contracts/spot for a selection)
    are ignored. So the light still shows a real account gate — established by an
    actual fetch, never by a poll. 3 bloomberg tests updated/added (green w/o
    billable probe, refusal surfaced from last fetch, success clears refusal).
  * **Fetch buttons show an indeterminate gauge while fetching.** `useWorkflow`
    now exposes `pending: "spots"|"options"|"calibrate"|null` (per-action, was a
    shared `busy`); `WorkflowControls` overlays an animated indeterminate bar
    (`@keyframes volfit-indeterminate` in index.css) + "Fetching spots…/quotes…"
    label on the active button. Calibrate keeps its existing determinate
    progress gauge (it's a real background job with done/total).

- **[2026-06-15] False "Mock Data" round 2 — provider failing mid-session**: the
  earlier fix (411e29c) stopped a *transient empty* ladder from freezing, but
  `AppState.snapshot()` still let a *raised* provider `fetch_chain` error escape
  unhandled → `/universe` 500 → frontend falls to mock. Hit in the wild when the
  active source was **Bloomberg** and it went red ("daily capacity reached")
  *after* startup auto-pick had selected it (`_AUTO_ORDER` prefers bloomberg;
  the active source is never re-evaluated at runtime). Fix: `snapshot()` now
  treats any provider fetch exception (UnknownNodeError excepted, still a 404)
  as a transient miss → returns an empty, UNCACHED snapshot via new
  `_empty_snapshot()` helper, so `/universe` and all downstream views degrade to
  "no data" (HTTP 200) and re-probe once the feed recovers. Regression test
  `test_provider_chain_failure_degrades_not_500` (CappedProvider). To get live
  data back when a source is capped, switch the TopBar Data Source selector to a
  reachable feed (Yahoo) — `POST /datasource/{id}` keeps the watchlist, clears
  caches and re-resolves on the new feed.

- **[2026-06-15] Save current selection as default (Options + View)**: both tabs
  gained an explicit **"Save as default"** + **"Reset to defaults"** bar.
  * **Options/Fit** persist to the app store (SQLite, VOLFIT_DB): new
    `app_settings(key, value_json)` table (VolStore schema **v2 → v3**,
    `save_setting`/`load_setting`/`delete_setting`); `volfit/api/settings_persist.py`
    serializes the live `FitSettings` + `OptionsSettings` under keys
    `fit_settings`/`options_settings` (best-effort: no store = no-op, stale blob
    discarded). `AppState.__init__` restores them at startup (a backend restart
    boots on the saved defaults, not code defaults); `save_settings_defaults` /
    `reset_settings_defaults` / `settings_defaults_saved` / `store_enabled` on
    AppState. Endpoints `GET/POST/DELETE /settings/defaults`
    (`SettingsDefaultsStatus` / `SettingsDefaultsReset`) — POST 422s when no
    store. Frontend: `state/useSettingsDefaults.ts`; `OptionsViewer` sticky bar
    now Reset · Save as default · Apply (Save first applies pending edits then
    persists; Reset adopts the reverted code-defaults into both drafts + reloads).
    `useOptions`/`useFitSettings` `apply()` now returns a Promise + an `adopt()`
    setter. 3 new API tests (`test_api_settings_defaults.py`): no-store disables
    Save, save survives a fresh app on the same DB, reset clears + reverts.
  * **View** stays localStorage but switched to the **explicit-save** model:
    `viewSettings`/`expiryFormat` apply changes live (instant preview) but only
    `saveDefault()` persists; both expose `dirty`. `ViewSettingsViewer` got the
    same Save/Reset bar (covers scheme + contrast/brightness + expiry format);
    the per-card Reset button was removed. NB the chart-header ↻ expiry cycle no
    longer auto-persists — persistence is now via the View tab's Save button.

- **[2026-06-15] Calibration compute speed-ups** (branch `perf/calibration-speedups`,
  all byte-identical or within golden tolerances):
  * **LQD slice fit 96 → 35 ms (2.7x)** — the atom of every parametric
    calibration (smile/surface/term/graph baseline all inherit it). (1) Cache
    the parameter-independent quadrature grid and Legendre basis in
    `models/lqd/quadrature.py` (`build_slice` runs ~900x/fit; it was recomputing
    `linspace`/`expit` + the order-6 Legendre matrix every call) and pass `dx=`
    (not `x=`) to `cumulative_simpson` (uniform fast path). (2) Optimize on a
    2001-node grid (`OPT_N_POINTS`), rebuild the accepted slice at the full 8001
    nodes for the result/diagnostics (converged params agree to ~1e-6). The
    calendar constraint moved from grid-index- to z-VALUE-based (new
    `LQDSlice.asset_share_at` Hermite eval + `calendar.calendar_floor_targets`),
    bit-identical at native resolution and correct on the coarse grid; threaded
    through `calibrate_surface` + `service.fit_surface_slice`.
  * **Affine local-vol Dupire fit** (`models/localvol/affine.py`): hoisted the
    theta-INDEPENDENT hat basis out of the per-eval solve (`precompute_dupire_steps`
    / `DupireSteps`, reused across all trial thetas) and sliced the multi-RHS
    sensitivity solve to its active (non-zero) column prefix (`active_k`, derived
    from the real basis sparsity). ~1.15x at optimal-grid scale; PDE-solve 2.05x /
    total fit ~1.6x at large grids (533 vertices). Sensitivity output diff exactly 0.0.
  * **Vectorized `implied_total_variance`** (`core/black.py`): replaced the
    per-strike `scipy.brentq` Python loop with one vectorized safeguarded Newton
    (`rtsafe`, analytic `black_vega_w`, bisection fallback). ~39x on a 241-pt
    curve render (27 → 0.7 ms); matches Brent to ~1e-13 with identical nan
    behaviour. Speeds every smile/affine render, term overlay and `max_iv_error`
    (full-suite wall-clock ~130s → 75s as a side effect). `brentq` no longer used
    in black.py.
  * **Parallelism (roadmap "parallelize slice fits") — measured & rejected.**
    Threads are GIL-negative for both LQD (0.5x) and affine (0.75x) fits;
    process-parallelism gives ~3.9x on LQD but is not worth the live-backend
    integration risk (persistent pool, Windows spawn, large-object serialization,
    cancellation) for a benefit that lands on the already-non-blocking background
    Calibrate job. Coarse-grid-during-opt is viable for LQD but NOT affine
    (it shifts the calibrated nodal variances 30x over the golden tolerance — the
    LV surface is the product output). Kept sequential.

- **[2026-06-14] UX/viewer batch — theming, layout, zoom, true-coordinate axis,
  Forwards chart**:
  * **View tab + full theming** (7th top tab): a `state/viewSettings.tsx`
    provider (localStorage) drives `data-theme` on `<html>` + a CSS
    contrast/brightness filter on `#root`. Tailwind v4 compiles colour utilities
    to `var(--color-*)`, so `index.css` re-skins the whole palette per
    `[data-theme]` scope with **no per-component migration** — four schemes
    **Dark / Light / High-contrast / Warm** (dark's dim text tiers lifted to fix
    "too dimmed"). New `views/ViewSettingsViewer.tsx` (scheme picker + contrast /
    brightness sliders + expiry format + live preview). Chart hardcoded hexes
    routed through tokens so charts flip too. Light mode verified end-to-end.
  * **Options tab reorganized by theme** (`OptionsViewer` 307 lines): Model &
    hyperparameters (model + N/damping/cores, model penalties, the local-vol
    grid) · Calibration (fit target, haircut, quote weighting, band mid anchor,
    var-swap weight, normalize events, calendar weight, calibration penalties,
    graph prior) · Workflow & engine features · Spot-vol dynamics. FitSettings
    lifted into `state/useFitSettings.ts` so its controls span two cards sharing
    one draft; `HyperparamPanel`/`PenaltyCoefficients` are now controlled +
    group-aware; one **Apply** bar commits both `/settings/fit` + `/settings/options`.
    Shared controls extracted to `components/OptionsControls.tsx`.
  * **Calibration gauge** in TopBar `WorkflowControls` (progress bar + current
    item label while a job runs). **As-of dropdown split into date → time** for
    captured snapshots, **weekday-only** (no weekend captures). **Local-Vol
    expiry selector → dropdown** (parity with Parametric). **Universe tab**:
    Active set and Lit/Dark matrix side by side.
  * **Zoom on every chart** (`lib/useZoom.ts`: base-relative wheel-zoom +
    drag-pan + dbl-click/⌂ reset, zoom-out beyond data): Smile (x+y, x beyond
    data), Stacked densities (x), Stacked IV (x+y), 3D Surface (scene scale),
    LocalVol Smile, Density / Log-Q-density. The Smile brush is kept as the
    coarse control.
  * **Smile true-coordinate x-axis** (`SmileChart` rewrite): geometry is plotted
    in the SELECTED coordinate (ln(K/F) / strike / %ATM / Δ / normalized), so the
    smile genuinely reshapes when switching (delta runs high→low) — no longer a
    fixed log axis. `axisModes.axisDisplayTicks` ticks the display domain.
  * **Curves drawn to k ∈ [-1, 1]** (`service.model_curve` 241 pts, `surface`
    81 pts extended to ±1; brush/default `kMin/kMax` stay the OBSERVED range, so
    zoom/pan out reveals the wings). New `service.fill_nonfinite` keeps the
    extreme-wing arrays finite (NaN would serialize to JSON null). 4 grid tests
    updated to the new semantics.
  * **T / √T toggle** on `TermChart`, the Forwards chart, and `SurfaceMesh`
    (`lib/timeAxis.ts`); **Surface coarse k-brush** (shrinks the strike axis,
    Parametric + LV IV-surface).
  * **Forwards-curve chart** (`components/ForwardCurveChart.tsx`): active-forward
    curve + dashed dividend ex-date verticals (amount labels), click-to-add a
    dividend, slider/numeric to set the amount, Apply (PUT `/settings/market`;
    continuous tickers switch to discrete cash so manual divs bite). Verified
    live on a throwaway synthetic backend.
  * Hardened `chartScale.niceTicks` against a sub-ULP step on flat domains
    (was an "Invalid array length" infinite-push crash). No new backend tests
    (existing grid tests updated); frontend strict-TS build green.

- **[2026-06-14] Local-Vol (affine) workspace overhaul**: (1) the vertex grid +
  roughness (λ, ρ) are now GLOBAL hyperparameters in Options only (the LV
  workspace's own sliders are gone); the affine fit reads them directly and they
  are in its cache key. Strike-node max raised to 200; **time vertices default to
  the observed expiries** (`gridTNodes = 0` = auto, one per expiry; > 0 caps).
  (2) An **"Optimal size"** button (Options) sizes the grid to the observed quotes
  (`GET /fit/affine/{t}/optimal-size`: strike nodes ≈ avg quotes/expiry, capped to
  ~160 total vertices so the heavy LSQ stays tractable). (3) The lowest strike
  vertex is placed strictly **between the lowest and 2nd-lowest observed strike**
  (no vertex below the data) — `_lowest_vertex_x`. (4) **LV joins the trigger
  model**: a per-ticker affine calibrated-pointer freezes the surface and reports
  `stale` (a STALE chip in the LV header) until Calibrate; the read path
  (`affine_payload`) NEVER recalibrates synchronously (the affine LSQ scales with
  vertex count — SPY ~minute) — it bootstraps once then serves frozen. The global
  background **Calibrate job now includes each lit ticker's LV surface** as
  labelled work items (`"TICKER · LV surface"`) so progress covers them
  (`workflow.calibrate_all`, jobs take `(label, thunk)` items); fetch-options
  auto-calibrate rebuilds them too. `calibrate_affine_surface` is the force path.
  Frontend: `useAffine`/`useAffineView` drop the grid params (POST `{fitMode}`
  only). 5 tests updated for the trigger model + new affine-grid/optimal-size
  tests; live-verified on SPY (optimal-size 977 quotes/8 expiries → capped grid,
  arb-free fit).

- **[2026-06-14] Trigger-gated calibration workflow** (what calibrates, on what,
  when): calibration is now decoupled from input changes. **Stale model** — each
  node carries a CALIBRATED pointer (the fit-key + spot it was last calibrated at)
  on AppState; `service.fit_or_get` bootstraps one fit, then with
  `Options.autoCalibrate` ON refits on any input change (old behaviour) and OFF
  *freezes* the last fit, reporting `SmileData.stale=True` until an explicit
  Calibrate (`node_dirty`/`calibrate_node`; a per-ticker `data_version` in the fit
  key bumps on a fresh options fetch). The spot-move transport anchors on the
  *calibration* spot (`anchor_spot`), not the live snapshot. **Actions**
  (`api/workflow.py` + `routers/workflow.py`): `POST /fetch/spots` (probe live spot
  → transport, no refit), `POST /fetch/options` (refetch chains + auto-calibrate
  when enabled), `POST /calibrate` (BACKGROUND job over all lit nodes via
  `api/jobs.CalibrationJobs`, `GET /calibration/status` for progress + lit/stale
  counts), `POST /calibrate/{ticker}[/{expiry}]` (sync), `POST /priors/seed`
  (explicit prev-close → calibrate → save). **Backend scheduler**
  (`api/scheduler.py`, opt-in `create_app(enable_scheduler=True)`; serve.py turns
  it on): a daemon thread polls live spots every `spotPollSeconds` when
  `spotMode=realtime` and refetches chains every `optionsFetchMinutes` when
  `optionsFetchMode=auto` (then auto-calibrates if enabled); `GET /scheduler` gives
  modes + countdowns. New OptionsSettings fields `spotPollSeconds`,
  `optionsFetchMode`, `optionsFetchMinutes` (autoCalibrate/spotMode now wired, not
  stubbed). **Frontend**: `state/useWorkflow.ts` (polls status, edge-reloads all
  views on job-completion / backend RT spot move) drives TopBar `WorkflowControls`
  (Fetch spots / Real-time Spots · Fetch Options Quotes / auto-countdown ·
  Calibrate with progress + stale-count badge); a STALE chip on the Parametric
  header; a "Calibration & data workflow" Options card; `useSmile` owns a single
  view-refresh counter (`spotVersion`/`refreshViews`) threaded into every
  workspace's fetchers; `useSpot` slimmed to the manual slider (backend owns RT).
  13 new tests (stale model, workflow endpoints, scheduler ticks); live-verified
  over HTTP (stale↔calibrate↔fetch cycle, scheduler thread running).

- **[2026-06-14] Fast spot-move transport (no recalibration)** per
  `Docs/spot_move_vol_surface_note_updated.tex`: a spot change — the user sliding
  the spot level OR a real-time spot tick — refreshes the calibrated smile / term
  / LV-grid **analytically**, never refitting (full recalibration only on the
  explicit Calibrate button). New `volfit/dynamics/transport.py`: the SSR
  horizontal total-variance transport `w₁ᴿ(k)=w₀(k+R·h_T)` (recovers
  sticky-moneyness/strike exactly at R=0/1), the exact sticky-local-vol `ℓ_T(k,h)`
  displacement (R=2 double-skew), an optional finite-move ATM re-anchor, and the
  LV-grid node rule `Kᵢ¹=Kᵢ⁰e^{(1−R/2)h_t}` (`TransportedSlice` SmileModel +
  `transport_grid_logk/strikes`). `h_T` comes from the FORWARD per the note
  (multiplicative under continuous yield, additive `ΔF=ΔS·e^{rt}` under discrete
  cash divs, so h differs per expiry). Integration: AppState holds a per-ticker
  spot SHIFT + `spot_version` (NOT in the slice fit-cache key — the anchor stays
  warm and is transported on read); `service.fit_or_get` wraps the cached
  `_anchor_fit` with `transport_record` (new forward, quotes re-indexed to new
  moneyness k−h, transported slice as a DisplayFit so EVERY view — smile, term,
  surface, density, var-swap, table, and the Dupire `/localvol` extraction —
  follows). The affine Local-Vol surface transports at the `affine_payload`
  boundary (`affine_transport.py`: per-expiry smile transport + grid relabel),
  `spot_version` busting the two derived caches. New endpoints
  `GET/PUT /spot/{ticker}`, `POST /spot/{ticker}/calibrate` (re-anchor: clear
  shift + drop chain caches + refit at live spot), `GET /spot/{ticker}/live`
  (provider spot re-probe for RT polling; cheap Yahoo override). Frontend:
  `state/useSpot.ts` (debounced PUT, RT poll when Options.spotMode='realtime',
  `spotVersion` folded into every workspace's fetchers), the aside "Spot scenario"
  slider repurposed into a live `SpotPanel` (slider moves the surface +
  anchor→shifted readout + regime·R + Calibrate button). 25 new tests
  (engine golden + service integration + API); live-verified over HTTP
  (synthetic +3%: fwd ×1.03, ATM 21.87%→21.73%, LV grid recenters, calibrate
  restores). The graph universe deliberately still reads the un-transported LQD
  anchor.

- **[2026-06-14] Auto-calibrate Events (Term)**: a horizon drop-list (an expiry T)
  plus a Calibrate button solve — all at once — one candidate event before each
  expiry up to T so the event-time forward variance `Δw/Δτ` is as flat and
  monotone-increasing as possible with events as small and sparse as possible
  (`volfit/calib/event_autocalibrate`: bounded L-BFGS-B over per-interval extra
  days, jaggedness + asymmetric non-monotonicity penalty + L1/ridge, tiny events
  thresholded out, the first post-T interval anchors the tail). Events only move
  the weighted clock, so the optimizer targets the *dilated* forward variance (the
  real-time one is event-invariant). `POST /events/{ticker}/autocalibrate`
  installs the result as the shared calendar. 4 tests.

- **[2026-06-14] Event-weighted VARIANCE CLOCK**: events are now a real variance
  clock (not just term interpolation). Each calendar day weighs 1; an event adds N
  *extra equivalent days* to its day (`volfit/calib/weighted_time.py`); the smile
  is calibrated/quoted in weighted years τ. Total variance is price-derived (clock-
  invariant), so the working IV = √(w/τ) **drops when an event sits before the
  expiry** (verified exact: ATM 0.2187→0.1980 = ×√(T/τ)) — quote bands, ATM,
  var-swap, table, term and the Local-Vol reconstruction all follow. Dual clock:
  calendar `t` still drives discounting / forwards / de-Americanization / the
  maturity axis; `prepared.tau` drives every vol↔variance conversion. An Options
  **Normalize events** toggle (default off) rescales all days so the 1Y weight
  budget stays 365 — 1Y vols unchanged, events redistribute variance within the
  year (verified). `eventsEnabled` is the master switch; the per-ticker calendar +
  `eventsEnabled`/`normalizeEvents` are folded into the fit-cache keys. Event
  weight is now *extra days* (was years); the Term editor labels it "days" and the
  master on/off lives in Options (the local checkbox is gone). No events ⇒ τ = t,
  byte-identical to before. 11 new tests.

- **[2026-06-14] Variance-swap quotes (Smile · Term · Table, Parametric + Local
  Vol)**: gated by the Options "Variance-swaps" toggle. A node carries at most one
  var-swap quote (the var-swap is a single log-contract scalar per smile),
  model-independent and SHARED across the Parametric (LQD/SVI/sigmoid) and
  Local-Vol (affine) fits, with its OWN undo/redo/reset history separate from the
  option-quote edits (`volfit/api/varswap_session.py` + AppState registry +
  `varswap_version` in the fit-cache key). Adding a quote adds a soft calibration
  penalty pulling the model's own fair var-swap toward the quote
  (`volfit/calib/varswap.py`, vol-space residual `sqrt(u)·(σ_vs_model−σ_vs_quote)`):
  threaded into all three parametric calibrators (scipy numerical Jacobian, so no
  analytic gradient) and the affine surface fit (reusing its existing
  `VarSwapQuote`). **Perf gotcha**: LQD's `implied_w` solves a per-point root, so
  the generic replication made one fit ~158 s under the FD Jacobian — LQD now uses
  its exact closed form `LQDSlice.var_swap_strike()` (≈0.7 s, vs 0.087 s
  unpenalized); SVI/sigmoid keep the cheap arithmetic-curve replication. The
  penalty weight is `OptionsSettings.varSwapWeightPct` (% of the node's summed
  option-quote weights; default 10%), so the var-swap competes with the options at
  a chosen relative strength regardless of quote count; `varSwapEnabled` /
  `varSwapWeightPct` now bump the options version. New endpoints
  `POST /smiles/{t}/{e}/varswap[/undo|/redo]` (shared by both workspaces). `SmileData`
  /`AffineSmile` gain `varSwap: VarSwapInfo`; `TermPoint` gains the per-expiry
  quote. Frontend: reusable `VarSwapPanel` (entry + slider + Exclude/Undo/Redo/Reset,
  Options-gated), a horizontal teal line on the Smile & Local-Vol smile charts, a
  Table footer row, and a Term overlay (hollow teal rings, click a rung to edit +
  a per-expiry panel/ladder column). 10 new backend tests; strict-TS build green.

- **[2026-06-14] All calibration/optimization coefficients exposed in Options**:
  every previously-hardcoded calibration constant is now a tunable parameter
  (each default = the historical constant, so default fits stay byte-identical
  and all golden tests pass) and surfaced explicitly in the Options tab —
  **LQD** A_R soft-barrier centre/scale, **SVI** no-arb penalty weight + Lee-slope
  bound, **Multi-Core SIV** hat-amplitude ridge, the **band** mid-anchor weight
  (threaded through `band_residuals` into LQD/SVI/sigmoid/affine), the **affine**
  roughness ρ, and the **graph** prior strength κ + η/λ/ν. Added to FitSettings
  (per-model, bumps the settings version) and OptionsSettings (graph-prior
  defaults + gridRegRho). Frontend: a `PenaltyCoefficients` sub-panel (grouped by
  model, greyed off-family) in HyperparamPanel + a "Graph prior (defaults)"
  section in OptionsViewer; `useAffine`/`useGraph` seed ρ and κ/η/λ/ν from the
  Options defaults. 1 new test (coefficients reach the calibrators).

- **[2026-06-14] Phase 10 viewer refinements** (third request batch):
  * **Local Vol IV surface is now 3D** (not a heatmap): the 3D renderer was
    extracted from SurfaceChart into a presentational `SurfaceMesh`; SurfaceChart
    is a thin fetching wrapper and the LV "IV surface" sub-tab builds a (T×k→σ_IV)
    mesh from the reconstructed affine smiles and renders it through SurfaceMesh,
    matching the Parametric Surface.
  * **Global expiry-format toggle** (`lib/expiryFormat.formatExpiry`): five
    formats — `dd-mmm-yy`, `(dd)mmmyy` (**smart-day**: the day is shown only on
    non-3rd-Friday listings, so monthlies read "Dec26", weeklies "11Dec26"),
    `1.25y`, `15.0m`, `15m 0d`. One global preference via a lightweight
    `ExpiryFormatProvider` context (localStorage-persisted), a full selector in
    the Options "Display" card + a ↻ cycle toggle in the Parametric/Local-Vol
    headers, applied across the expiry dropdown, chart titles, Local-Vol
    chips/diagnostics, Forwards & Term ladders, the lit/dark matrix and the
    stacked-chart legends.

- **[2026-06-14] Phase 10 viewer refinements** (second request batch):
  * **Aside/header slimmed**: the Parametric expiry-class chips (D/W/M/Q/All) are
    gone (the Expiry dropdown lists every selected expiry); the aside keeps only
    diagnostics + the spot-scenario *slider* — the **dynamics regime moved
    entirely to Options** (Mny / Strike / LV / LV-grid / custom-SSR; backend
    `dynamicsRegime` widened to a string literal incl. `custom`), and the **model
    selector moved to Options** too (ModelPanel retired). `useSmile` sources the
    scenario regime from `/settings/options` and re-pulls it on reload, so an
    Options change propagates.
  * **Stacked views (Parametric)**: the single-node Density tab is replaced by
    **Stacked densities** — every selected expiry's risk-neutral density overlaid
    (all ≥ 0 ⇒ no butterfly arb), new `GET /smiles/{ticker}/densities`
    (model-aware; declared before `/{expiry}`). A **Stacked IV** tab beside
    Surface overlays **total variance** w(k)=σ²·T per expiry (the correct space:
    non-crossing ⇔ no calendar arb), from the existing `/surface` mesh. New
    zero-dep `OverlayCurvesChart` (maturity-graded).
  * **Local Vol IV surface**: the Surface sub-tab is now **LV surface**; a new
    **IV surface** sub-tab shows the reconstructed implied-vol heatmap (per-expiry
    affine smiles resampled on a shared intersection grid). `LocalVolHeatmap`
    generalized with a legend label.
  * **Lit/dark nodes**: per-(ticker,expiry) lit/dark designation on AppState
    (lit by default; lit = observed source, dark = extrapolation target),
    `GET /universe/lit` + `PUT /universe/lit/{ticker}[/{expiry}]`, `GraphNodeInfo`
    reports `lit`. New `LitDarkMatrix` in the Universe tab; `useGraph` seeds its
    observed set from the designation on load and persists toggles back, so the
    Universe and Graph tabs stay in sync. 11 new backend tests (options/custom,
    stacked-densities, lit/dark); strict-TS build green; endpoints live-verified.

- **[2026-06-14] Phase 10 — workspace restructuring (tabs, Forwards & Options)**:
  top tabs are now **Parametric · Local Vol · Forwards · Options · Graph ·
  Universe** (Smile → Parametric; Term-Structure is no longer a top tab).
  * **Parametric**: Term-Structure embedded as a chart sub-tab next to Density
    (`components/TermPanel.tsx`, reuses useTerm + TermChart; aside hidden on it);
    the standalone `TermStructureViewer` is retired. The aside is slimmed to its
    live per-node controls — new `ModelPanel` (smile-family selector that PUTs
    the *full* FitSettings so other fields survive) + ScenarioPanel.
  * **Local Vol**: Parametric-style sub-tabs Smile / Density / Term / Surface
    (heatmap) / Table, every view DERIVED from the calibrated affine LV surface.
    Backend `api/affine_views.py` reconstructs them from the cached fit (wrap
    each reconstructed (k,vol) smile in an interpolating SmileModel, reuse the
    Breeden-Litzenberger density / log-contract var-swap / Black-price pipeline);
    `POST /fit/affine/{ticker}/{density,term,table}` share the AffineFitRequest
    body → same cache key. Frontend `state/useAffineView.ts` (only the active
    sub-tab fetches) + presentational `LocalVolTable`.
  * **Forwards** tab (`views/ForwardsViewer.tsx`): per-ticker forwards table
    across the ladder (parity/theo/manual/active) + the per-expiry ForwardPanel
    reused verbatim; edits refit both Parametric & Local Vol via the forwards
    version. (ForwardPanel left the aside.)
  * **Options** tab (`views/OptionsViewer.tsx` + `state/useOptions.ts`): new
    global `OptionsSettings` (GET/PUT /settings/options on AppState; options
    version folded into the fit-cache key, bumped only by the calibration-
    affecting `calendarWeight`). Hybrid meta page: calibration defaults (reuses
    HyperparamPanel + fit-mode), engine toggles (arb-fix / events / var-swap /
    auto-load-prior), spot-vol dynamics default (regime + SSR), local-vol grid
    defaults, the **penalty catalogue** (descriptions + formulas verified
    against the calibrators, editable `calendarWeight`), and the stubbed
    workflow toggles (auto-on-demand calibration, real-time/static spot).
  * **Wiring (per the "wire cheap / stub new" decision)**: `calendarWeight`
    fully affects surface slice fits (threaded into calibrate_slice, tested);
    `useAffine` seeds the LV grid from Options (untouched-only) and `useTerm`
    seeds the events default. The remaining toggles (enforceCalendar,
    varSwapEnabled, dynamicsRegime/ssr, autoLoadPrior) are persisted global
    defaults surfaced in the UI — deeper per-view consumption is the Phase 10
    follow-up; auto-calibrate + spot mode stay stubbed. 10 new backend tests
    (`test_api_options.py` ×6, `test_api_affine_views.py` ×4); strict-TS build
    green; new endpoints live-verified on uvicorn (synthetic ALPHA: options
    round-trip, /term 4 points, /density 169 pts, /table 14 rows, F 87.80).

- **[2026-06-14] "Quantile" chart replaced by the log quantile density**: the
  Smile Viewer's distribution tab now plots the LQD model's own backbone,
  ℓ(u) = log q(u) = −log f_X(Q(u)) = −log(pdf) vs u (Docs/lqd_model_note.tex eq
  lqd_main), with the y-axis **capped at ymax = 2.5** (ℓ is a bowl that diverges
  at the tails; the divergent tails are clipped to the plot box). Computed
  frontend-side from the existing `density` array (so it follows the chosen
  model, like density/quantile already do — no backend change). Tab renamed
  Quantile → "Log Q-density" (`logqd` view), legend/hover/hint updated, SVG
  clipPath added. Frontend strict-TS build green.

- **[2026-06-13] Weighted RMS fit error in the diagnostics**: every calibrated
  smile now reports its RMS vol error using the active weighting scheme —
  `sqrt(sum u_i (sigma_model - sigma_mid)^2 / sum u_i)` over the edited quotes,
  with u_i the equal/TV-density weights actually used by the fit (pure helper
  `models.diagnostics.weighted_rms_vol`; `service.weighted_rms_error` gathers the
  displayed slice + scheme weights). New `SmileDiagnostics.rmsError` (decimal
  vol) shown as a "RMS error" % row in the Smile aside. 2 new tests.

- **[2026-06-13] Time-value density quote weighting (all models, per maturity)**
  per `Docs/iv_time_value_density_weights.tex`: new `volfit/calib/weights.py` —
  `w_i = max(TV_i, eps) * s_i / s_bar` where TV_i is the OTM quote's time value
  (its normalized forward option price, `otm_time_value`) and s_i is the 1-D
  Voronoi cell width in log-moneyness, so the *aggregate* weight density follows
  TV(x) with the strike oversampling divided out (dense regions down-, sparse
  wings up-weighted; uniform grid → w_i = TV_i exactly). New FitSettings
  `weightScheme` ("equal" = historical unit weights | "tv_density"; room for a
  third) drives `resolve_weights(scheme, k, w)` — mean-normalized so the
  data-vs-regularization balance is identical to equal weighting. Applies to
  EVERY model and EVERY fit mode: SVI/Sigmoid/LQD multiply the (IV-space)
  residual by sqrt(w), LV-affine folds sqrt(w) into the vega tolerance, and the
  band objective scales its violation+anchor by it too. Computed on the *edited*
  slice quotes (exclusions define the Voronoi cells, amends move TV). Refactor:
  `fit_weights`/`fit_band` removed; `surface_inputs` returns (iso, prepared) and
  weights/band are derived per slice at fit time. New "Quote weighting"
  segmented control in HyperparamPanel. 9 new tests incl. the note's exact
  5-quote golden example + uniform-grid benchmark + per-model effect.

- **[2026-06-13] Term-structure & local-vol now follow the chosen model too**
  (correcting an earlier overstatement that they "need" LQD): neither has a
  structural LQD dependency. **Term-structure** only reports per-expiry ATM vol /
  ATM total variance / var-swap — all model-agnostic and already computed for
  overlays — so `analytics.term_structure` now reads them from the *displayed*
  fit (bitwise-equal to GET /smiles' diagnostics for the same model).
  **Local-vol** (`GET /localvol`) is a Dupire extraction that only uses the
  `implied_w(k)` SmileModel interface, so it now extracts from the displayed
  surface (`displayed_slice`); the SSR scenario uses the displayed skew. Caveat
  documented: Dupire's denominator is ill-conditioned and assumes an arb-free
  smooth input — LQD/SVI are arb-free by construction, the signed MC-SIV cores
  can violate butterfly, in which case the extraction clips and the no-arb
  diagnostics flag it. Only the **graph universe** genuinely stays LQD (it needs
  exact ATM-orthogonal coordinates + Newton retargeting). Refactor: the
  `displayed_*` accessors moved to `api/displayed.py` (service.py back to 379
  lines); added `displayed_var_swap_w`/`displayed_max_iv_error`. 2 new tests.

- **[2026-06-13] Density / Quantile views now follow the chosen model**: the
  density chart was hard-wired to the LQD backbone (`record.result.slice`) even
  when SVI/sigmoid was displayed. Added a model-agnostic Breeden-Litzenberger /
  Durrleman-Gatheral density `numeric_density(slice_)` in `models/diagnostics.py`
  (`p(k) = g(k)/sqrt(2πw) e^{-d_-^2/2}` from `implied_w(k)` alone, FD w'/w'',
  pdf floored at 0 + renormalized for non-arb-free overlays). `density_payload`
  now uses the displayed slice's own density for a non-LQD overlay (LQD keeps its
  exact closed form; saved prior stays the LQD snapshot). Validated: integrates
  to 1, matches the exact LQD pdf to <0.4% over the central mass, and exactly
  reproduces the flat-smile Gaussian N(-a/2, a). 3 new tests. (Frontend already
  labels the curve "Current fit" — no UI change.)

- **[2026-06-13] Bid-ask / haircut band fitting objective for ALL models**:
  the band fit modes no longer fit |mid - model|; they penalize the model
  *leaving the quoted band* — `max(model-ask,0)^2 + max(bid-model,0)^2` — plus a
  small `MID_ANCHOR_WEIGHT=0.05` |mid-model| anchor (new `volfit/calib/band.py`:
  `resolve_band`/`band_residuals`). "haircut" tightens each side toward mid by a
  tunable `haircut` (default 0.5 vol pts = 0.005, clamped never to cross mid:
  `modified_bid=min(bid+h,mid)`, `modified_ask=max(mid,ask-h)`), replacing the
  old HAIRCUT_SHRINK weight factor. The hinge is monotone so each model keeps
  its native residual space: **SVI/Sigmoid** vol-space hinge, **LQD** vega-
  normalized price hinge (band vols → call-price edges), **LV-affine** price
  hinge with the analytic Jacobian preserved (subgradient 0 inside band;
  `OptionQuote` gained `price_lo`/`price_hi`). Band-only weighting (no inverse-
  spread on top — the band encodes the spread; `fit_weights` now returns unit).
  "mid" mode is byte-identical (golden tests untouched). `haircut` added to
  FitSettings + a "Haircut (vol pts)" control in HyperparamPanel; threaded
  through fit_or_get / surface / WS / display-overlay / affine fit
  (`apply_band_edits`/`edited_band`, aligned to quote edits). Fixed a latent
  calib/__init__ import cycle (lazy `surface` via PEP 562). 13 new tests
  (band core + per-model in-band/smoothing/outside-pull + LV band modes).

- **[2026-06-13] Multi-Core SIV ("sigmoid") model rewrite** per
  `Docs/Multi_Core_SIV_Technical_Note.tex`: the legacy 4-param monotone sigmoid
  is replaced by `v_R(z) = v_SIV(z;theta) + sum_r alpha_r B_{c_r,h_r,kappa_r}(z)`
  — a one-core SIV base (level/skew/convexity/asymmetric wings, 6 params) plus R
  signed **zero-wing hat kernels** (eq B-def) that reshape the body for WW /
  dual-hat smiles WITHOUT moving the Lee wing slopes (eq model-wing-preservation).
  `models/sigmoid/kernels.py` (Phi primitive, base SIV, hat B + derivatives,
  Durrleman/Gatheral g diagnostic), `sigmoid.py` (`MultiCoreSiv` SmileModel,
  `SigmoidSmile` kept as alias), `calibrate.py` (base fit → greedy hat seeding on
  residuals → bounded trf joint refine + amplitude ridge; cores capped so
  6+4R ≤ N). **R is a slider** (`nCores` on FitSettings, 0–6, the analogue of the
  LQD Legendre order) threaded through `build_display_fit`/service → a "SIV cores
  R" range control in HyperparamPanel (active only for the sigmoid family).
  Golden tests reproduce the note's Table 1 coefficients, RMSE (8.62e-4), feature
  table, min v (0.03824) and min g (0.1553) to published precision; the slider
  monotonically buys fit (WW smile: R=0 base 105 bp → R=3 0.4 bp). 14 sigmoid
  tests + 2 settings tests; ruff + strict-TS build green.


- **[2026-06-13] As-of (timestamp) selector under Data Source**: choose the
  observation time — **Live / Real-time**, **Previous Close**, a provider **EOD
  trading day** (~30 days), or a **captured intraday** snapshot replayed from the
  store. Everything re-prices because it all flows through
  `AppState.snapshot()`. Provider contract gained `AsOf` + `fetch_chain(as_of=)`
  + `historical_modes()`/`available_history()` (`data/provider.py`, default
  live-only). Bloomberg does eod/prev-close via `bdh` (`data/bloomberg_history.py`,
  narwhals long `ticker/date/field/value`; ~30 trading-day list); Massive does
  prev-close from the snapshot `day.close` (zero-spread); Yahoo/Synthetic
  live-only. AppState `set_as_of` clears chain caches + routes live(+auto-capture
  to VolStore, dedup ~60 s) / provider-EOD / captured-replay
  (`store.snapshot_at`); `data/store.py` gained `list_snapshots`/`snapshot_at`/
  `last_snapshot_ts`. `api/asof.py` + `routers/asof.py` (GET/POST /asof).
  Frontend `state/useAsOf.ts` + a TopBar "As of" dropdown (amber when
  historical). 7 new tests. Live-verified: Bloomberg eod 2026-06-11 fits a real
  historical SPY smile (ATM 16.27%).

- **[2026-06-13] In-app Data Source selector** (Yahoo / Bloomberg / Massive /
  Synthetic) with a per-source status light (green=real-time, amber=delayed,
  red=unavailable). `AppState` now holds a **provider registry** instead of one
  provider (`self.provider` is a property over `_active_source`);
  `set_active_source` switches at runtime — keeps the watchlist + custom expiry
  picks, clears data caches, refetches on the new feed (auto selections
  re-resolve lazily, custom picks intersect the new available list). Each
  provider gains a cheap `feed_status()` probe (`data/provider.py` default +
  yahoo/bloomberg/massive overrides; Massive's is two single-page GETs, never
  full pagination). New `api/datasource.py` (concurrent probing + 30 s TTL
  cache) + `routers/datasource.py` (GET /datasources, POST /datasource/{id}).
  `serve.py` registers ALL sources and auto-picks the best-reachable active one
  (bloomberg→yahoo→massive→synthetic; `VOLFIT_PROVIDER` forces one). Frontend
  `state/useDataSources.ts` + a TopBar dropdown selector with status dots;
  switching fires the session's refreshUniverse()+reload(). `restart.ps1` now
  brings all sources up by default (flags only force the active one). 13 new
  tests. Live-verified: lights = bloomberg green / yahoo amber / synthetic
  green / massive amber, switch + 404 work end-to-end.

- **[2026-06-13] Bloomberg + Massive market-data providers** (CLAUDE.md data
  layer; ROADMAP Phase 3 + "Next up" #2). Both implement the
  `OptionChainProvider` contract so the whole stack runs on them unchanged.
  * **Bloomberg** (`data/bloomberg.py` + `data/bloomberg_parse.py`): via xbbg
    against a live Terminal. `available_expiries` parses the OPT_CHAIN
    descriptor strings (one cheap `bds`, no per-contract `bdp`); `fetch_chain`
    bulk-`bdp`s only the selected expiries' contracts (liquid names list 1000s).
    Reads xbbg's **narwhals long-format** frames column-wise (they lack
    `index`/`itertuples`). Real `OPT_EXER_TYP` sets `exercise_style`.
    `search_symbols` uses the blpapi `//blp/instruments` service so the Universe
    picker resolves "Nvidia"/"NVDA" -> "NVDA US Equity" (Massive search hits
    `/v3/reference/tickers`); the picker is source-aware via the active provider.
    `dividend_schedule()` imports `DVD_HIST_ALL` (future-declared rows, else
    projects the trailing quarterly cadence forward) → seeded into per-ticker
    MarketSettings at startup (`serve._seed_bloomberg_dividends`).
    Live-verified: SPY 13 expiries, 1026 quotes, spot+american+forwards+divs.
  * **Massive** (`data/massive.py`): Massive.com = rebranded Polygon.io
    (`api.massive.com`, Bearer auth, `/v3/...`). `available_expiries` via the
    contracts reference; `fetch_chain` via the chain snapshot (last_quote
    bid/ask + day OHLC + OI + underlying price); `NOT_AUTHORIZED` →
    actionable `RuntimeError`. **The supplied key's tier DOES return snapshot
    quotes + spot**, so Massive is a fully-working fitter source today
    (live-verified: 32 expiries, spot 741.75, 291/366 usable mids).
  * **Massive IV overlay** (`api/routers/massive_iv.py`, GET
    /massive/iv/{ticker}): Massive's own American IV/greeks per contract as a
    read-only comparison (entitled without quotes). Frontend toggle in the
    Smile Viewer (`state/useMassiveIv.ts` + cyan OTM scatter on SmileChart).
  * Wiring: `serve.py`/`snapshot.py`/`restart.ps1` gain `bloomberg`/`massive`
    selection (`VOLFIT_PROVIDER`, `VOLFIT_MASSIVE_KEY`; `restart.ps1
    -Bloomberg`/`-Massive`). Shared `data/fieldmap.py` (price/int coercion,
    also adopted by yahoo). Optional `providers` extra in pyproject (xbbg,
    blpapi, httpx, yfinance — not in CI). 16 new offline tests (injected
    `blp_module` / `http_get`); both providers live-verified end-to-end.

- **[2026-06-13] Per-ticker expiry-depth/window selection**: the Universe tab
  now picks each ticker's expiries from the FULL provider list. Provider
  exposes `available_expiries` (cheap — Yahoo `Ticker.options`, no chain fetch;
  horizon raised to ~2Y) and `fetch_chain(ticker, expiries)` fetches only the
  selected rungs. `data/expiry_select.py`: buckets (0dte / weekly = M/W/F /
  monthly = 3rd Fri / quarterly / daily), the **default rule** (first 2 M/W/F
  weeklies >=2 days + first 2 monthlies + quarterlies <=18M; sparse ladders
  <=8 take all), and bulk-filter resolution. AppState gains per-ticker
  available/selected/mode (auto vs custom), lazily applied to watchlist
  tickers; selection changes re-fetch the chosen expiries (extracted to
  `api/state_universe.UniverseMixin` to keep state.py <400). Endpoints: GET
  /universe/{t}/expiries (full list + buckets + selected flags), PUT (set),
  POST .../reset (default rule). Named universes now persist per-ticker
  selection ("auto" re-resolves the rule, "custom" re-applies explicit picks).
  Frontend `ExpiryPicker.tsx` in the Universe tab: bulk chips (0DTE/Weeklies/
  Monthly/Quarterly/<=1Y/<=2Y/All) + per-expiry checkboxes + Reset; edits
  refit every workspace via the shared session. 11 new tests; verified
  end-to-end on live SPY (29 available -> 8 default-selected; picker + chips).

- **[2026-06-13] Universe-selection UI**: a dedicated "Universe" tab (5th
  workspace) to curate the working set of underlyings. Backend: AppState now
  holds a mutable active-ticker set (`add_ticker` validates by fetching the
  chain + a parity forward, `remove_ticker` keeps >=1 and drops the ticker's
  caches, `set_active_tickers` for loading a saved set); `snapshot()` gates on
  the active set so dynamically-added symbols work. Symbol search
  (`provider.search_symbols`: default substring+echo, **YahooProvider override
  hits Yahoo's autocomplete** via httpx with offline fallback). New endpoints
  (`api/universe_service.py` + router): GET /universe (active), GET
  /universe/search, POST/DELETE /universe/tickers, and named universes wired to
  the existing SQLite persistence (`data/universe.py`) — GET/POST/DELETE
  /universes + POST /universe/load/{name} (no-op without VOLFIT_DB). Frontend:
  `views/UniverseManager.tsx` + `state/useUniverse.ts` (debounced search,
  add/remove, save/load/delete named) + `useSmile.refreshUniverse()` so edits
  propagate to every workspace's selectors. 7 API tests; verified end-to-end in
  headless Edge (search → add DELTA → save named universe).

- **[2026-06-13] Discrete cash-dividend de-Americanization**: the proper cure
  for the residual ATM kink on dividend-straddling expiries (the continuous-
  yield de-Am smears a discrete cash dividend into an average yield and
  mis-models the call/put early-exercise asymmetry near the ex-date). New
  escrowed-Hull cash schedule in the CRR tree (`core/american.py`: `_escrow` +
  `div_times`/`div_amounts` on `binomial_price`/`_batch`/`deamericanize`/
  `_batch`; recombining, base lattice on S-PV, actual spot = lattice + remaining
  dividend PV). Consistency: the tree uses the ticker's physical `rate` and the
  schedule's ex-date timing, with cash amounts SCALED so the escrowed forward
  reproduces the resolved forward exactly (`data/dividends.forward_consistent_
  cash_schedule`, alpha=(S-F e^{-rt})/PV) — the IV level is untouched, only the
  ex-date EEP asymmetry is corrected. Wired opt-in through quote prep
  (`api/quotes.prepare_quotes` + state `cash_dividend_schedule`): activates when
  the ticker has a discrete/mixed dividend mode with a cash leg in (0,t] and a
  rate high enough to admit positive dividends (else falls back to continuous-q,
  unchanged). Golden test: flat-vol American chain with a mid-period cash
  dividend — continuous-q leaves a 62 vol-bp ATM kink, discrete de-Am brings it
  to 1.5 bp and recovers the flat 20% smile (tests/test_discrete_deam.py).

- **[bugfix 2026-06-13] American parity-forward ATM kink**: put-call parity is
  an equality only for European options, so a forward implied from raw American
  C - P is biased (~40 bp), and quote prep then de-Americanized OTM puts/calls
  under that biased carry in opposite directions → a visible IV jump at the
  money (reproduced flat-vol: 93 vol bp; live SPY: 22-308 bp per expiry). Fix in
  `data/forwards.py`: when a reference date is supplied for an American snapshot,
  de-bias **only the forward** (iterating the carry q via de-Americanized
  European-equivalent mids to the fixed point that reconciles the two OTM sides)
  while **holding the discount at its raw parity value** — re-implying the
  discount (the fragile regression slope) drifted to absurd rates on short-dated
  / dividend chains and shifted the IV level through 1/(D F). Threaded
  `reference_date` through `implied_forwards` (api/state, snapshot.py); coarse
  near-ATM de-Am keeps it ~0.1 s/expiry (cached). Live SPY now joins smoothly
  across ATM with sane discounts. Discrete-dividend chains can keep a small
  residual kink (continuous-yield tree); **now cured opt-in by discrete cash-
  dividend de-Americanization — see the dated entry above**.
  4 golden tests (tests/test_forward_debias.py).
- Phase 0 scaffold (no CI yet), Phase 1 complete (LQD engine reproduces both
  paper benchmarks; ATM-orthogonal coordinates with exact Newton retargeting).
- **Phase 2 complete**: calendar constraint = elementwise asset-share
  comparison; local-vol grid model done (`models/localvol/`): bilinear/pw_t
  grid, Crank–Nicolson Dupire forward PDE pricer (adaptive 7.5-sd mesh,
  <0.5 vol bp flat round trip in ~20 ms), Dupire extraction with butterfly
  gating, no-arb diagnostics. Not yet exposed via the API.
- Phase 3 near-complete (M3 reached): synthetic + **Yahoo provider**
  (`data/yahoo.py`, yfinance, sqrt-time expiry thinning, 0-bid→None mapping),
  parity forwards, SQLite VolStore, snapshot CLI (`backend/snapshot.py`).
  Live-verified 2026-06-12: SPY/QQQ/AAPL chains fitted end-to-end in the UI
  (SPY 5.5M: ATM 17.2%, skew -0.41; clean monotone variance term structure).
  Run live: `$env:VOLFIT_PROVIDER='yahoo'; $env:VOLFIT_TICKERS='SPY,QQQ,AAPL'`
  before serve.py. (Bloomberg/Massive providers + DuckDB/Parquet history TODO)
- Phase 4 complete (dense path): 6-node golden example reproduced exactly;
  smile-universe round trip works (graph posterior on (atm_vol, skew, curv)
  handles → exact arbitrage-free LQD smiles + credible bands); 1k nodes < 1 s.
  Matrix-free/Hutchinson large-N path deferred to Phase 9.
- Phase 5 core: FastAPI backend live (`volfit/api`): /universe, /smiles
  (3 fit modes, prior save), /fit/surface (POST + WebSocket per-expiry
  progress), /graph/solve (12-node universe), /scenario/ssr. Quote prep with
  parity normalization + 4-sd wing filter (`api/quotes.py`). Run it:
  `.venv\Scripts\python backend\serve.py` (port 8000, CORS for Vite).
- Phase 5 fit sessions: per-(ticker, expiry) quote edits (exclude/include/
  amend/reset) with bounded undo/redo (`api/session.py`), instant refit via
  POST /smiles/{t}/{e}/edits|undo|redo; edits shared across fit modes via a
  version-stamped fit-cache key.
- Phase 6 partial: SmileViewer wired to the live API (`state/useSmile.ts` +
  `state/smileSession.tsx` context): universe-driven selectors, fit-mode
  refetch, mock fallback when offline, TopBar live/mock/connecting status.
  Quote interaction done: click-select quotes, Del exclude/restore, arrow-key
  mid amend (Shift = coarse), Ctrl+Z/Y undo/redo, excluded quotes dimmed,
  amended mids amber (drag-to-amend not implemented; keyboard-first per spec).
- Phase 7 core: Graph Viewer live (`views/GraphViewer.tsx` + `useGraph.ts` +
  `GraphChart.tsx`): SVG lattice (tickers × expiries, calendar/cross edges),
  click to light nodes, per-node dAtmVol inputs, η slider, solve via
  /graph/solve (+ new GET /graph/nodes baseline endpoint), shift coloring +
  sd halos + tooltips, double-click drills into the Smile tab. Verified in
  headless Edge (screenshots: 2 observed → 10 extrapolated, sane decay).
- Phase 6 near-complete: Term-Structure view live (POST /term + `useTerm` +
  `TermChart`: vol & variance vs T, real/event-dilated clock toggle, editable
  event markers, expiry ladder table); density & quantile chart views
  (GET /smiles/{t}/{e}/density + `DistributionChart`, prior overlay once
  saved); Save-prior button (priors now store LQDParams via `PriorRecord`).
- Phase 8 complete: SSR scenario engine + frontend regime selector
  (Mny/Strike/LV) with spot-return slider and dotted overlay on the smile
  chart. (true sticky-local-vol-grid mode still awaits localvol API wiring)
- API slice fits use gentle high-order damping (default REG_LAMBDA=1e-6) —
  without it, slices left with ~7 quotes after the wing filter interpolate
  exactly with wild handles (GAMMA 1M fitted skew +0.78). Now user-tunable:
  **fit-settings hyperparameters** (GET/PUT /settings/fit: nOrder, regLambda,
  regPower) held on AppState with a settings version folded into every
  fit-cache key; HyperparamPanel in the Smile Viewer aside drives it.
- **[REQ done] Piecewise-affine local-variance calibration** per
  `Docs/piecewise_affine_local_variance_calibration.tex`:
  `models/localvol/affine.py` (P1 hat-function surface; **scipy Delaunay
  triangulation reproduces the note's quote table to every published
  decimal** — fixed-diagonal splits land ~2e-5 off; implicit-Euler forward
  Dupire in normalized strike with analytic multi-RHS forward sensitivities)
  + `affine_calib.py` (option + var-swap LSQ per eq. calibration_objective;
  log-contract replication; second-difference roughness **lambda=50**
  reproduces the note's calibrated nodal table to 1.5e-3 and all fit
  metrics). 10 golden tests in tests/test_localvol_affine.py.
- **Local-vol grid exposed via API** (`api/localvol.py`, GET /localvol/{t}):
  pw_t forward-variance buckets extracted at bucket midpoints from the
  fitted surface, session/settings-aware cache, no-arb diagnostics in the
  payload. **Sticky-local-vol-grid SSR regime** (exact: grid fixed in
  absolute strike, Dupire reprice, realized SSR reported; "LV grid" button
  in ScenarioPanel). Caveat documented in api/localvol.py: the shortest
  bucket's ATM slope is ill-conditioned (bp-level fit wiggles amplified by
  the small-w Dupire denominator) — realized short-expiry SSR can sit well
  below the theoretical ~2; mid/long buckets land in 1.5-2.5.

- **Realism block, part 1 done**: `core/american.py` (CRR binomial
  American/European pricer + `deamericanize()` → European-equivalent IV by
  Brent inversion) and the **stale parity-pair filter** in `data/forwards.py`
  (iterative 4-robust-sigma MAD trim floored at 1bp of spot, `n_outliers`
  reported).
- **[REQ done] Realism block, part 2 (complete)**:
  * **Dividends model** (`data/dividends.py`): continuous yield / discrete
    absolute (escrowed) / discrete proportional / mixed (cash near-dated
    switching to proportional past `switch_years` — desk practice);
    `theoretical_forward()` + `equivalent_yield()`, golden-tested.
  * **Forward mode per expiry** (`api/market.py`, `routers/forwards.py`):
    parity-implied (default) / theoretical (rate + dividend model, per-ticker
    `MarketSettings` via GET/PUT /settings/market/{ticker}) / manual override
    — GET /forwards/{ticker} shows all three side by side, PUT
    /forwards/{t}/{e} sets the policy; a `forwards_version` on AppState is
    folded into every fit-cache key so policy changes refit cleanly. Frontend
    `ForwardPanel` in the Smile Viewer aside (mode segmented control, manual
    input, carry r/q inputs); verified in headless Edge (manual override
    89.56 vs parity 87.80 refits the smile end-to-end).
  * **De-Americanization wired into quote prep** (`api/quotes.py`):
    `ChainSnapshot.exercise_style` flag (Yahoo heuristic: `^`-prefixed
    indices European, stocks/ETFs American; VolStore schema v2 persists it);
    American mids inverted via vectorized-bisection `deamericanize_batch`
    (one (n_quotes × steps) CRR sweep per iteration — chain-scale, ~50 ms vs
    seconds scalar), early-exercise premium subtracted from bid/mid/ask alike
    (spread preserved in price space); carry derived from the resolved
    forward (r = -ln D/t, q = r - ln(F/S)/t). Golden round trip: CRR-priced
    American chain at known σ(k) recovered within 30 vol bp.

- **[REQ done] Chart & UX block (2026-06-13)**:
  * **Strike-axis modes** on the smile chart (`lib/axisModes.ts` +
    SmileChart): k / fixed strike / %ATM / delta (numeric-bisection inverse,
    "25Δ"-style ticks) / normalized / log-normalized — geometry stays in
    k-space, only ticks/crosshair labels transform; selector in the chart
    header.
  * **3D vol-surface view** (`components/SurfaceChart.tsx`, zero-dep SVG:
    painter-sorted quads, drag-to-rotate yaw, vol colormap + legend) fed by
    GET /surface/{ticker} (`api/surface.py`: shared 61-pt union k grid over
    the fitted ladder, cached slice fits).
  * **Table export**: GET /smiles/{t}/{e}/table (JSON) + /table.csv
    (attachment download; `api/table.py`, prices reconstructed via
    normalized Black) and a Table chart-card view (`QuoteTable.tsx`) with
    Copy-TSV / CSV-download.
  * **Expiry classification** (`data/expiries.py`: leaps > quarterly >
    monthly (3rd Friday) > weekly (Friday) > daily; `expiryType` on
    /universe) + class filter chips next to the expiry selector (only
    classes present render; auto-reselects when the current rung filters
    out). **Full universe-selection UI now done** (the Universe tab: provider
    symbol search, add/remove, named universes); the chips still cover bulk
    expiry selection within a ladder.
  * SmileViewer split into UniverseHeader / SmileAside / useSmileShortcuts
    to stay under the 400-line policy. All verified in headless Edge
    (surface mesh, delta ticks, table grid, CSV Content-Disposition).

- **[REQ done] Fit time-series scaffold (2026-06-13)**: every calibrated
  slice (POST/GET/WS paths alike) persists into the VolStore `fits` table
  keyed by SNAPSHOT timestamp (`api/history.py`: fresh WAL connection per
  write for thread safety, dedupe on (ticker, expiry, ts, fitMode),
  exception-safe — persistence can never fail a fit; opt-in via env
  `VOLFIT_DB=path`, off by default). Query: GET /history/{ticker}/{tenorDays}
  ?fit_mode= — per snapshot picks the expiry nearest the tenor, returns
  {ts, expiry, t, atmVol, skew, curvature, varSwapVol, maxIvErrorBp,
  forward} ascending. Charting UI deferred.

- **[REQ done] CI + perf benchmarks (2026-06-13)**:
  * **GitHub Actions** (`.github/workflows/ci.yml`): three jobs — `backend`
    (py3.11/3.12 matrix: `ruff check .` + `pytest -m "not live and not perf"`),
    `perf` (single 3.11 runner: `pytest -m perf -s`), `frontend`
    (`npm ci` + `npm run build` strict-TS gate). Per-branch `concurrency`
    cancels superseded runs; pip + npm caches keyed on lockfiles.
  * **Perf budget suite** (`tests/test_perf.py`, `@pytest.mark.perf`): a
    `BUDGET_MS` table enforced by warmup-then-median timing of the four hot
    paths — LQD slice fit (~95 ms local), 1k-node graph update (~700 ms),
    local-vol CN forward solve (~20 ms), ~80-quote de-Am batch (~630 ms);
    budgets sit ~2.5-3.5x above local medians for slow-runner headroom.
  * Registered `perf`/`live` pytest markers + a `test` extra (httpx, pandas)
    in pyproject; tagged the live Yahoo test `@pytest.mark.live`; cleaned the
    6 pre-existing ruff findings so lint gates clean. Generated
    `frontend/package-lock.json` for reproducible `npm ci`.
    (process-pool for parallel slice fits still deferred — single fit ~95 ms,
    instant-refit target already met.)

- **[REQ done] Graph Viewer remainder (2026-06-13)**:
  * **Full solver panel**: GraphSolveRequest now carries the prior knobs —
    kappaScale (local stiffness), etaScale (reach), lambdaScale (OT flux, 0 =
    off, preserves the legacy regime), nu (source allowance) — plus
    calendarWeight/crossWeight edge overrides. Wired in the new
    `api/graph_service.py` (extracted from service.py to keep both under the
    400-line policy): `_reweighted_universe` rebuilds only the cheap graph from
    the cached handles when weights change; `_build_priors` applies the scales
    per handle coordinate. SolverPanel.tsx (η/κ log sliders, λ slider, ν +
    edge-weight inputs) drives it via useGraph; default solve unchanged.
  * **Auto-tune η** (POST /graph/autotune, `autotune_graph`): leave-one-out
    cross-validation over the lit observations across a geometric η grid,
    minimizing held-out ATM-vol RMSE; returns the chosen η + scored grid
    (rendered as bars in the panel, ≥2 lit nodes required).
  * **Lasso selection** in GraphChart: drag a rectangle on the lattice
    background to light every enclosed node (node groups stop mousedown so a
    plain click still toggles). 7 new graph API tests; verified end-to-end in
    headless Edge (lasso lit all 12 nodes, solve propagated, auto-tune adopted
    η=10×).

- **Model choice in the hyperparameter panel (2026-06-13)**: the Smile
  Viewer can now fit the displayed smile with **LQD** (default, arbitrage-free
  quantile density + the analytic backbone), **SVI** (raw-SVI own calibration,
  new `models/svi_jw/calibrate.py`: reparametrized LM fit, data-driven init,
  soft Lee-wing + min-variance no-arb penalties; recovers the note's SPX
  benchmark to machine precision — 7 golden tests) or **sigmoid** (existing
  `calibrate_sigmoid`). LQD is *always* fitted under the hood; a non-LQD choice
  attaches a `DisplayFit` overlay (`api/fit_models.py`) read by the smile
  chart, diagnostics, quote table, 3D surface and SSR scenario, while density,
  term-structure, local-vol and the graph universe stay LQD-based (they need
  the exact LQD coordinates). Overlay diagnostics (ATM handles, var-swap by
  log-contract replication, Lee wing slopes) come from the new model-agnostic
  `models/diagnostics.py` (matches the LQD closed forms on an LQD slice — 4
  tests); A_L/A_R report 0 (no endpoint-scale analogue off LQD). FitSettings
  `model` is now `lqd|svi|sigmoid`; the LQD-only N/damping knobs grey out off
  LQD in HyperparamPanel. Frontend strict-TS build green.

- **Direct local-vol-affine fit + Local Vol view (2026-06-13)**: the
  model-choice bullet is now fully closed. `POST /fit/affine/{ticker}`
  (`api/affine_fit.py` + `schemas_affine.py` + `routers/affine.py`) calibrates
  the piecewise-affine local-VARIANCE surface of the Docs note straight to a
  ticker's option quotes — gathers every expiry's edited quotes, converts mid
  IVs to normalized forward call prices with vega-scaled tolerances, builds a
  tensor vertex grid (0 + a spread of expiries × a strike grid incl. x=1) and
  the fine PDE x/t grids (t hits every quoted expiry), runs
  `calibrate_affine`, and reconstructs each expiry's arbitrage-free smile by
  inverting the Dupire PDE call prices through Black. Distinct from
  GET /localvol (Dupire *extraction* from the LQD fit). Cached per request
  hyperparameters. New frontend **Local Vol tab** (`views/LocalVolViewer.tsx`
  + `state/useAffine.ts` + `LocalVolHeatmap.tsx` nodal σ heatmap +
  `LocalVolSmile.tsx` reconstructed-smile-vs-quotes chart): vertex-grid /
  roughness controls, per-expiry fit + butterfly (min φ) diagnostics, arb-free
  badge. 6 API tests; verified end-to-end in headless Edge (ALPHA: arb-free,
  21 bp max error, 4×8 vertex heatmap, 0.5 s fit).

- **Realism leftovers done (2026-06-13)**: the last [REQ] bullet is closed.
  * **Dividend ex-date markers in the Term view**: POST /term now returns a
    `dividends` list (`DividendMarker`: exDate, real-time t, dilated tau,
    amount) for the ticker's discrete schedule within the curve range, emitted
    only under the discrete/mixed dividend modes (`api/analytics.py`
    `_dividend_markers`). TermChart draws them as emerald dashed verticals with
    a $amount label on both the real-time and event-dilated clocks (the
    per-expiry forward already drops across each ex-date; these are
    informational). 3 API tests.
  * **Dividend-schedule editor**: new `DividendEditor.tsx` embedded in the
    ForwardPanel — a mode picker (continuous / discrete cash / discrete
    proportional / mixed), an editable (ex-date, amount) row list with
    add/remove, and the mixed-mode switch horizon. ForwardPanel now PUTs the
    full MarketSettings (mode + schedule + switchYears, not just r/q), so the
    smile refits via the forwards version. Verified end-to-end in headless
    Edge (cash dividend → Term marker at t≈0.12y; editor shows the schedule).

**>>> MASSIVE FEED ROADMAP (the priority track — 3-tier source router) <<<**

The design (agreed 2026-06-15): all three tiers sit behind the as-of `(day →
moment)` model so the fitter never sees the difference.

0. **[DONE — verified 2026-06-15] Live REST feed confirmed end-to-end.**
   `massive_diag.py SPY` on both hosts: two-sided NBBO (376 quotes / 308
   two-sided), `underlying_asset.price` populated, stocks plan entitled. See the
   dated STATUS entry.
1. **[Tier 1 finish — CODE DONE + LIVE-VERIFIED 2026-06-15]** The three code
   sub-tasks of the live book are shipped (451 tests green), and the WS book is
   live-verified — but only via the **delayed cluster** (`wss://delayed.polygon.io/
   options`): the real-time cluster is silent on this (delayed-tier) key, so
   `MassiveWebSocket` now auto-advances a candidate URL list to the cluster that
   actually streams (`VOLFIT_MASSIVE_WS_URL` to override; set it to the delayed URL
   here to skip the ~6s warmup). The three sub-tasks:
   * **Contract-listing cache** (`MassiveProvider._intraday_contracts` keyed by
     `(ticker, frozenset(expiries))`, `refresh_contracts()` to invalidate) — the
     WS read (`_chain_from_book`/`option_tickers`) and the per-tick resubscribe
     diff no longer re-paginate the contracts reference every call.
   * **Resubscribe on universe change** (`AppState.sync_streaming` +
     `_desired_stream_contracts` + `MassiveProvider.streaming_contracts()` /
     `MassiveWebSocket.contracts`): a ticker added/removed or an expiry-selection
     edit while streaming now restarts the WS on the new subscription (was
     source/mode-change only). Providers that can't report their subscription are
     never thrash-restarted.
   * **Throttled full-refit loop** while a live book streams: a new scheduler
     branch (`Scheduler.tick`, gated by `AppState.is_streaming()` AND
     `autoCalibrate`) calls `workflow.stream_refit` every
     `OptionsSettings.streamRefitSeconds` (default 5s) — refetch chains from the
     book + recalibrate ALL lit nodes (background). `autoCalibrate` is the master
     switch: OFF ⇒ the loop is a no-op (surface still tracks spot via the transport
     poll; nodes stay stale until explicit Calibrate). Distinct from the
     minutes-cadence `optionsFetchMode == "auto"` REST refetch.
   **Remaining (optional) live-UI check:** drive the running app (Massive +
   Real-time) to confirm the throttled refit + resubscribe paths end-to-end in the
   scheduler thread (the engine paths are verified by the probe + tests).
2. **[Tier 2 — flat-file history — BACKEND DONE 2026-06-15, live-verify pending
   S3 creds]** S3 flat files → DuckDB/Parquet local store (the long-deferred
   columnar history). Shipped:
   * `volfit/data/occ.py` — OCC/OPRA option-symbol parse/format (the flat files
     carry only the `O:` ticker, which encodes strike/expiry/type). 11 tests.
   * `volfit/data/flatfiles.py` — `FlatFileStore`: DuckDB (+bundled `httpfs`)
     reads the gzipped daily aggregate CSV straight from S3, filters to the
     watchlist roots, caches the day to local **Parquet** (lazy, once per
     date×product), and reconstructs a `ChainSnapshot` at a target instant —
     **minute aggregates** for a past intraday moment, **day aggregates** for the
     official Close — quoting `close` as a zero-spread bid=ask=close, spot by
     parity. Injectable `source_uri` ⇒ offline tests run the real duckdb read of
     a local gzip CSV fixture. 5 tests.
   * Wiring: the store belongs to `MassiveProvider` (`flat_store=`), so the as-of
     layer is unchanged — `historical_modes()` gains **`eod`**,
     `available_history()` lists the last ~20 weekdays, and `fetch_chain(as_of=)`
     routes `eod`→day-aggs and a **past-day** `intraday` instant→minute-aggs
     (today-intraday still the REST `/v3/quotes` path). serve.py `_flat_store()`
     builds it from env `VOLFIT_FLATFILES_KEY`/`_SECRET` (+ optional
     `_ENDPOINT`/`_BUCKET`/`_PREFIX`/`_CACHE`); None without creds. 3 tests.
   `duckdb` is an optional `flatfiles` extra, imported lazily (core runs without
   it; tests `importorskip`). **LIVE-VERIFIED 2026-06-15** against `files.massive.com`
   (see the dated STATUS entry): bucket/layout confirmed, day + minute aggs
   reconstruct real SPY chains, full-pipeline EOD fit lands atmVol 15.6% / rms 35bp.
   Set `VOLFIT_FLATFILES_KEY`/`_SECRET` (+ `_ENDPOINT=files.massive.com`) to enable.
   Quote-level flat files only if true historical NBBO depth is needed (heavy).
3. **[Tier 3 — REST gap-fill]** Extend `_fetch_intraday` to aggregates for
   today's pre-connect intraday + single-contract lookups (the per-contract
   `/v3/quotes` path already exists).
4. **Spot source**: now that the stock plan is live, prefer the real
   `underlying_asset.price` / stocks spot; keep parity-forward as the fallback.
   Consider streaming the underlying quote channel for a true live spot.

**Then (general, in order):**
1. Phase 10 follow-ups still open: `enforceCalendar` on the per-view paths,
   `varSwapEnabled` hiding the var-swap rows, `autoLoadPrior`.
2. Phase 9 hardening: arbitrage invariants as property tests, fuzzed quote
   sets, provider-failure injection; UX polish (skeletons, layout persistence;
   the error boundary + null-safe diagnostics now landed); Docker-compose
   packaging + user/API docs.
3. Smaller leftovers: process-pool for parallel slice fits; editable ATM handles
   + prior load/diff UI; cross-ticker "apply expiries to all" in the picker.

**Environment notes:**
- venv at repo root `.venv`; run tests: `cd backend; ..\.venv\Scripts\python -m pytest tests -q`
  (334 green as of 2026-06-14, incl. 4 perf-budget tests; opt-in live Yahoo
  test via `$env:VOLFIT_LIVE="1"`). Run only perf: `pytest -m perf -s`.
- Data sources: `restart.ps1` registers ALL feeds and auto-picks the best
  reachable as active; switch live via the TopBar **Data Source** selector
  (status light per source). Force one active on launch with
  `-Live`/`-Bloomberg`/`-Massive`/`-Synthetic`. Set `$env:VOLFIT_MASSIVE_KEY`
  to light up Massive (else it shows Red; the rest still work). Bloomberg needs
  an open Terminal (xbbg+blpapi are in .venv).
- API server: `.venv\Scripts\python backend\serve.py` (uvicorn :8000, CORS for
  Vite). Live data: set `$env:VOLFIT_PROVIDER='yahoo'` and
  `$env:VOLFIT_TICKERS='SPY,QQQ,AAPL'` first (yfinance installed).
- Snapshot CLI: `.venv\Scripts\python backend\snapshot.py SPY QQQ` → SQLite
  (`backend/data/snapshots.sqlite`, gitignored) + parity-forward diagnostics.
- Frontend: `cd frontend; npm run dev` — talks to :8000 when up, else mock
  fallback with an amber MOCK badge; `npm run build` is the strict-TS gate.
- Engine demo: `.venv\Scripts\python backend\demo.py`.
- PyPI is **intermittently flaky** on this machine (TLS resets toward Fastly;
  npm/Cloudflare fine). pip is configured with retries=15 in pip.ini — installs
  succeed with patience. Suspected AV/router TLS filtering.
- Sub-agents have no shell access here: they write code, the lead runs/verifies.
- UI smoke-testing recipe: `npm i --no-save puppeteer-core` in frontend, drive
  headless Edge (`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`)
  against the Vite dev server, screenshot and inspect; delete the throwaway
  driver script afterwards.

---

## Architecture overview

```
┌─────────────────────────────── Frontend (React + TS) ───────────────────────────────┐
│  Smile Viewer        Surface/Term-Structure Viewer        Graph Viewer              │
│  (Plotly/visx)       (vol & variance, event time)         (force-directed, WebGL)   │
└───────────────▲──────────────────────────▲──────────────────────────▲───────────────┘
                │ REST (FastAPI) + WebSocket (live fit progress)      │
┌───────────────┴──────────────────────────┴──────────────────────────┴───────────────┐
│                              Python backend (FastAPI)                               │
│  ┌────────────┐  ┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │ data layer │  │  quant core      │  │ calibration     │  │ graph solver       │  │
│  │ providers, │  │  models: LQD,    │  │ slice fits,     │  │ Gaussian update,   │  │
│  │ universe,  │  │  SVI-JW, sigmoid,│  │ calendar/no-arb │  │ OT mobility,       │  │
│  │ storage    │  │  local-vol grid  │  │ event dilation  │  │ marginal precision │  │
│  └────────────┘  └──────────────────┘  └─────────────────┘  └────────────────────┘  │
└──────────────────────────────────────┬───────────────────────────────────────────────┘
                                       │
                            SQLite (quotes, fits, priors, graphs)
```

**Package layout** (Python monorepo, each file ≤ 400 lines):

```
backend/
  volfit/
    core/        # Black/Bachelier pricing, implied vol inversion, quadrature, Lee bounds
    models/      # lqd/, svi_jw/, sigmoid/, localvol/  — one model = one subpackage
    calib/       # objectives, weights, constraints (butterfly/calendar), event time
    graph/       # operators (L_rev, L_dir, A_rho), prior, posterior, hyperparam calib
    dynamics/    # SSR, sticky-strike, sticky-local-vol scenario engine
    data/        # providers (yahoo, bloomberg, massive), dividends, universe, db
    api/         # FastAPI routers, schemas (pydantic), websocket fit-progress
frontend/
  src/
    views/       # SmileViewer, TermStructure, GraphViewer, UniverseSelector
    components/  # charts, sliders, quote-table, parameter panels
    state/       # zustand stores, API client, websocket hook
tests/           # pytest (unit + golden-number + arbitrage invariants), vitest/playwright
Docs/            # technical notes (existing)
```

**Tech decisions** (answering the open questions in CLAUDE.md):

| Question | Recommendation | Why |
|---|---|---|
| Front-end | **React + TypeScript + Vite**, Plotly.js (charts) + Sienna/visx or regl for graph view | Mature, fast iteration, professional look with Tailwind + Radix; nothing materially better for this use case |
| Storage | **SQLite for app state** (universes, fits, priors, graph configs) + **Parquet via DuckDB for quote history** | SQLite is perfect for transactional app data; columnar Parquet/DuckDB is far better for bulk option-chain snapshots and backtests |
| Compute | **NumPy vectorized + Numba JIT** for hot loops (LQD quadrature, graph solves via `scipy.sparse` + CHOLMOD/`sksparse`), optional JAX later for autodiff gradients | "Lightning-fast" target: one slice fit < 50 ms, full surface < 1 s, graph update on 10k nodes < 1 s |
| API | **FastAPI + WebSockets** | Async, pydantic schemas shared with frontend via OpenAPI codegen |

---

## Phase 0 — Foundations (week 1)

- [x] Git init, `pyproject.toml` (setuptools), pytest; frontend scaffold (Vite + TS + Tailwind v4). (ruff configured, mypy not yet)
- [x] CI: lint (ruff) + unit/golden tests + perf budgets + frontend build
  (`.github/workflows/ci.yml`). Type-check (mypy) still TODO.
- [x] Shared conventions: ≤400-line files, module docstrings referencing Doc equation numbers (established in code).
- [x] React shell with tab routing (Smile / Term Structure / Graph); FastAPI skeleton pending (deps installed late due to network).

**Exit criteria:** `make dev` runs backend + frontend hot-reload; CI green.

## Phase 1 — Quant core: pricing & LQD slice engine (weeks 2–4)

The LQD note (`Docs/lqd_model_note.tex`) is the centerpiece; implement it first
since other models are standard.

- [x] `core/black.py`: normalized Black formula B(k,w), vega, robust implied-variance inversion (Brent; closed-form ATM).
- [x] `models/lqd/basis.py`: Legendre recursion, endpoint scales A_L/A_R, Lee slopes.
- [x] `models/lqd/quadrature.py`: logit quadrature, martingale shift μ, asset-share A(z), analytic tail corrections (NumPy-vectorized; Numba not needed — slice fit ≈ 30 ms).
- [x] Pricing via cubic-Hermite interpolation on exact nodal derivatives (`models/lqd/interp.py`) — required for clean FD Greeks; density/quantile extraction in `LQDSlice`.
- [x] `models/lqd/atm.py` exact ATM functionals + `models/lqd/ortho.py` (Jacobian, least-norm primary directions, kernel shape modes, exact Newton retargeting).
- [x] `models/lqd/calibrate.py`: vega-weighted LSQ, A_R barrier, n^{2r} regularization, logistic initializer. (wing-aware & quantile-projection initializers still TODO)
- [x] Golden tests: both note benchmarks reproduced (μ to 4e-8; SVI fit < 2 vol bp; double-hat bimodal).

**Exit criteria:** both paper benchmarks reproduced to stated accuracy; slice fit < 50 ms.

## Phase 2 — Quant core: remaining models & no-arbitrage (weeks 4–6)

- [x] `models/svi_jw/`: raw-SVI + JW conversion (Appendix A) + **own
  calibration** (`calibrate.py`: reparametrized LM, data-driven init, soft Lee
  wing-slope & min-variance penalties; recovers the benchmark to machine
  precision). (full Gatheral–Jacquier butterfly conditions still TODO)
- [x] `models/sigmoid/`: 4-param sigmoid curve + LM fit (round-trip exact).
- [x] `models/localvol/`: bilinear (continuous piecewise-affine) and pw-const-in-t grid variants; CN Dupire forward PDE pricer (Rannacher startup, adaptive span); Dupire extraction with butterfly-gated denominator; round-trip + consistency tests. Exposed via the API (GET /localvol extraction + POST /fit/affine direct calibration) and the Local Vol view.
- [x] [REQ 2026-06-12] Local-vol calibration per `Docs/piecewise_affine_local_variance_calibration.tex`: `models/localvol/affine.py` + `affine_calib.py`, golden tests vs every table of the note (Delaunay triangulation is the note's convention; lambda=50 roughness reproduces the calibrated nodal table). **Exposed via the API** (POST /fit/affine/{ticker}, `api/affine_fit.py`) and the **Local Vol frontend view** (direct surface fit + reconstructed arbitrage-free smiles + no-arb diagnostics).
- [x] [REQ 2026-06-12] American-options handling, de-Americanization first: `core/american.py` CRR binomial + `deamericanize()` scalar and `deamericanize_batch()` (vectorized bisection, chain-scale). **Wired into quote prep**: `ChainSnapshot.exercise_style` flag (Yahoo heuristic + VolStore v2), EEP stripped from bid/mid/ask in `api/quotes.py`, carry from the resolved forward.
- [x] Common `SmileModel` protocol (`models/base.py`): `implied_w(k)`, `implied_vol(k, t)` — satisfied by LQD/SVI/sigmoid. (richer `density()`/`diagnostics()` surface TBD)
- [x] Calendar check via G_i(α) ≤ G_j(α): implemented as elementwise asset-share comparison on the shared logit grid (`calib/calendar.py`), soft-slack penalty in `calibrate_slice`, **toggleable**. (model-free butterfly check for non-LQD models TODO)
- [x] `calib/event_time.py`: dilated clock + variance-lumping term-structure interpolation; toggleable.
- [x] Surface construction: sequential nearest-to-farthest with warm starts and violation diagnostics (`calib/surface.py`).

**Exit criteria:** all 4 model families fit a test surface; arbitrage diagnostics (A_L, A_R, Lee slopes, μ, calendar residuals) reported for every fit.

## Phase 3 — Data layer (weeks 5–7, parallel with Phase 2)

- [x] Provider interface `OptionChainProvider` + deterministic `SyntheticProvider` (offline dev/tests) + `yahoo.py` (yfinance, lazy import, injectable factory, sqrt-time expiry thinning) + **`bloomberg.py`** (xbbg, OPT_CHAIN descriptor parse for cheap `available_expiries`, bulk `bdp` for the selected expiries, real `OPT_EXER_TYP` exercise style, `DVD_HIST_ALL` dividend import w/ forward projection) + **`massive.py`** (Massive/Polygon REST, contracts-reference expiries, chain snapshot quotes/greeks/IV, `NOT_AUTHORIZED` -> clear upgrade error, `iv_surface` overlay). Shared field coercion in `data/fieldmap.py`. Both live-verified.
- [x] Implied forwards by put-call parity regression (`data/forwards.py`, recovers F to <0.1% on synthetic).
- [x] [REQ 2026-06-12] Dividends model selection: continuous yield, discrete absolute (escrowed), discrete proportional, or mixed (absolute short-dated switching to proportional long-dated — standard desk practice) — `data/dividends.py`, feeds the theoretical forward. **Discrete schedule editable in the UI** (DividendEditor in the ForwardPanel) and **ex-dates surfaced as markers in the Term view** (event-time clock).
- [x] [REQ 2026-06-12] Forward fitting mode per expiry: **theoretical** (spot + carry from rate/dividend model), **parity-implied** (default), or **manually adjusted** (ForwardPanel UI override, held on AppState with a forwards version in fit keys); GET /forwards/{ticker} shows the three side by side.
- [x] [REQ 2026-06-12] Fit time-series scaffold: every calibration persists (params, ATM handles, diagnostics) keyed by snapshot timestamp into VolStore `fits` (`api/history.py`, opt-in via VOLFIT_DB) + GET /history/{ticker}/{tenorDays}; charting UI deferred.
- [x] Quote prep: mid/bid/ask + haircut modes, spread-based weights, 4-sd wing filter (`volfit/api/quotes.py`). (per-quote liquidity haircuts and richer outlier rules TODO)
- [x] Storage: SQLite `VolStore` (instruments, snapshots, quotes, fits, priors, universes; WAL, versioned schema). Parquet/DuckDB history TODO.
- [x] Universe dataclass + persistence, **now wired to the API and a dedicated
  Universe tab** (add/remove tickers via provider symbol search, save/load named
  universes). AppState holds the mutable active set.
- [x] [REQ 2026-06-12] Expiries bulk selection by type: `data/expiries.py` classification (`expiryType` on /universe) + class filter chips in the Smile header. (Full provider-driven universe-selection UI still TODO.)

**Exit criteria:** one command snapshots a 20-ticker universe from Yahoo into storage; forwards implied; quotes ready for calibration.

## Phase 4 — Graph extrapolation engine (weeks 7–10)

Direct implementation of `Docs/ot_bayesian_graph_extrapolation_expanded.tex`.
Nodes = smiles `(underlying, T)`; node scalar field = smile parameters in
**ATM-orthogonal coordinates** (level w₀, skew s₀, curvature κ₀, shape modes ξ)
— this is what makes the LQD ATM orthogonalization load-bearing: each
coordinate is propagated as its own graph signal `z = x¹ − x⁰`.

- [x] `graph/build.py`: node registry, row-normalized K, stationary π (dense solve), reversibilized conductances. (default-weight rules from sector/maturity proximity TODO)
- [x] `graph/operators.py`: L_rev, L_dir, mobility Laplacian A_ρ (log + arithmetic means).
- [x] `graph/prior.py`: Q_Δ = D_κ + ηL_dir + λ(A_ρ+νI)⁻¹ — **dense path** (fine to ~2k nodes; matrix-free/sparse deferred to Phase 9).
- [x] `graph/posterior.py`: covariance-form update, marginal precisions 1/K⁺_ii. (Hutchinson/selected-inverse large-N path deferred)
- [x] `graph/hyper.py`: marginal likelihood ℓ(θ) (Cholesky), standardized residuals ζ_i. (analytic gradient + auto-tune optimizer TODO)
- [x] Round trip (`graph/smile_universe.py`): handles (atm_vol, skew, curv) propagated per-coordinate → exact ATM retargeting → arbitrage-free LQD smiles + credible bands. Tuning insight: η such that smoothness residual ≈ 1/3 of increment scale gives ~75% same-ticker / ~6% cross-ticker propagation.
- [ ] Validation harness: hide x% of liquid smiles, extrapolate, score vs truth; calibration plots. (basic version exists in tests; systematic harness TODO)

**Exit criteria:** 6-node running example of the note reproduced exactly (μ⁺, π⁺ tables); 1k-node synthetic universe updates < 1 s; held-out validation report.

## Phase 5 — Backend API (weeks 9–11)

- [x] Routers: `/universe`, `/smiles/{ticker}/{expiry}` (fit_mode=mid/bidask/haircut, prior save), `/fit/surface` (POST + WS per-expiry progress), `/graph/solve`, `/scenario/ssr`, `/smiles/{t}/{e}/edits|undo|redo`.
- [x] Fit session model: edited quote set per smile (exclude/include/amend/reset), bounded undo/redo, version-stamped fit cache (`api/session.py`).
- [x] Var-swap level computation per slice (exact integral; in `SmileDiagnostics.varSwapVol`).
- [ ] Performance: process-pool for parallel slice fits across expiries/assets; cache quadrature grids. (in-process fit cache exists; pool TODO)

**Exit criteria:** full fit-edit-refit loop driveable from HTTP/WS; OpenAPI schema published for frontend codegen.

## Phase 6 — Smile Viewer frontend (weeks 10–14)

Professional, commercial, sleek (dark theme default, dense layouts, keyboard-first).

- [x] Smile chart (pure SVG, zero deps): prior vs current vs bid/ask I-beams, log-moneyness axis (fixed-strike mode designed in via `axisMode` prop), strike-range brush, crosshair readout. **Wired to live fits** via `useSmile` (universe selectors, fit-mode refetch, mock fallback when backend offline).
- [x] Quote interaction: click to select, Del to exclude/restore, arrow-key mid amend, Ctrl+Z/Y undo/redo; fit-to-bid-ask / mid / haircut toggle; instant refit on edit (~30 ms server-side). (drag-to-amend TODO if wanted)
- [x] Quantile-function & LQD density chart: prior vs current (`DistributionChart`, GET /smiles/{t}/{e}/density).
- [x] Term-structure view: vol and total variance vs T, calendar in real time **and** event-dilated time; event markers editable (POST /term).
- [ ] Diagnostics panel: A_L/A_R, Lee slopes, var-swap level shown; directly *editable* ATM handles (w₀, s₀, κ₀ via exact retargeting) TODO.
- [x] Prior management: save current fit as prior (button + PriorRecord with params); load/diff UI TODO.
- [x] Hyperparameter panel: **model choice** (LQD/SVI/sigmoid overlays, the
  N/damping knobs grey out off LQD), Legendre N, penalty coefficients.
  (arbitrage/event toggles in the panel still TODO)
- [x] [REQ 2026-06-12] Strike-axis modes on the smile chart: all six modes via `lib/axisModes.ts` (geometry stays in k-space; ticks/crosshair labels transform; delta inverted numerically).
- [x] [REQ 2026-06-12] 3D vol-surface chart: `SurfaceChart.tsx` zero-dep SVG mesh (painter-sorted quads, drag-rotate, colormap) on GET /surface/{ticker}.
- [x] [REQ 2026-06-12] Table export: GET /smiles/{t}/{e}/table + /table.csv attachment; QuoteTable grid view with Copy-TSV and CSV-download.

**Exit criteria:** trader workflow demo — load universe, inspect smile, drag ATM skew, erase a bad quote, refit, save prior — all fluid.

## Phase 7 — Graph Viewer frontend (weeks 13–16)

- [x] Graph visualization: structured SVG lattice (ticker columns × expiry rows, calendar + cross-ticker edges) — chosen over force-directed for legibility at current scale; WebGL/pan-zoom deferred to large-universe work.
- [x] Node states: **lit** (observed) vs **dark** (extrapolated), toggled by click or **lasso** (drag-rectangle lights all enclosed nodes), with per-node dAtmVol inputs. (ticker/expiry filters TODO)
- [x] Edge-weight input: calendar (same-ticker) and cross-ticker weight overrides in SolverPanel (rebuild only the cheap graph, fits cached). (per-edge matrix editor + sector rules + CSV upload TODO)
- [x] Solver panel: κ, η, λ, ν controls (SolverPanel.tsx) + leave-one-out "Auto-tune η" with a scored-grid readout. (live re-solve on every drag still manual via Solve; per-edge κ/λ TODO)
- [x] Result overlay: posterior shift as diverging node color, marginal sd as halo size/fade, hover tooltip with base→post + credible band; double-click → jump to that smile in the Smile Viewer.

**Exit criteria:** end-to-end demo — observe 5 smiles, light them, solve, watch 200 dark smiles update with uncertainty, drill into any one.

## Phase 8 — Vol-spot dynamics & scenarios (weeks 15–17)

- [x] `dynamics/ssr.py`: SSR on ATM vol, configurable; sticky-moneyness / sticky-strike / sticky-local-vol (SSR=2 short-maturity rule) regimes with exact shape-preservation invariant. (true sticky-local-vol-grid mode awaits the localvol model)
- [x] Frontend: regime selector + spot-shift slider with live re-render of shifted smile (ScenarioPanel + dotted overlay).

**Exit criteria:** spot ±5% scenario renders all three regimes consistently for any fitted surface.

## Phase 9 — Hardening, performance & polish (weeks 17–20)

- [x] Perf pass: budget table (`tests/test_perf.py`) enforced in the CI `perf` job — slice fit, local-vol forward solve, 1k-node graph update, de-Am batch. (Profiling-driven Numba/JAX tuning not needed yet; all paths inside budget.)
- [ ] Test depth: arbitrage invariants as property tests (every LQD iterate butterfly-free; calendar residuals ≤ τ), fuzzed quote sets, provider failure injection.
- [ ] UX polish: loading/skeleton states, error surfaces, layout persistence, theming, onboarding tour.
- [ ] Packaging: Docker compose (backend + frontend), one-line local install; user guide + API docs.

---

## Phase 10 — Workspace restructuring: tabs, Forwards & Options (SHIPPED 2026-06-14)

> Shipped — see the dated STATUS entry at the top for what landed. The checklist
> below is the original plan; the only deferred items are the deeper "wire
> cheap" consumers (scenario auto-seed, enforceCalendar/varSwap per-view,
> autoLoadPrior) and the two stubs, now tracked as Phase 10 follow-ups in
> "Next up".

Reorganize the top-level tabs and consolidate the global / meta controls into a
single **Options** workspace, so the per-workspace asides only carry the live
controls a trader touches per node. No new quant math — this is an
information-architecture + settings-plumbing phase that surfaces engine switches
that already exist (and stubs the two that do not yet).

**Decisions locked in the 2026-06-14 planning Q&A (do not re-litigate):**
- **Options is hybrid**: it holds meta/UX + *defaults* + the penalty catalogue.
  The Parametric aside keeps only the live per-node controls (model, fit-mode,
  scenario). The Forward / Dividend panels *leave* the aside for a dedicated
  Forwards tab.
- **Wiring scope = "wire cheap, stub new."** Wire the toggles that map to an
  existing engine switch now (calendar/arb-fix, event-time dilation, var-swap,
  quote weighting, fit-mode + haircut, dynamics regime + SSR, all defaults).
  **Stub** the genuinely new ones as persisted UI state with a clear TODO:
  *auto-on-demand calibration* and *real-time spot streaming*.
- **auto-on-demand calibration** = a toggle between auto-refit on every edit
  (default ON, today's behavior) and a manual **Calibrate** button that gates
  refits (OFF). **Real-time / static spot** = stream live spot and re-price
  (real-time) vs freeze spot at load (static); pairs with the existing As-of
  selector. Both are stubbed this phase (UI + persisted flag; behavior TODO).
- **Local Vol sub-tabs mirror Parametric**, every view derived from the
  calibrated piecewise-affine LV surface (new backend derivations).
- **sticky-delta** maps to the existing `sticky_moneyness` regime (delta-space ≈
  moneyness-space); the UI labels it "sticky-delta", the `Regime` enum is
  unchanged (`sticky_moneyness` | `sticky_strike` | `sticky_local_vol`).

**Top-level tabs (before → after):**
```
before:  Smile · Term Structure · Local Vol · Graph · Universe
after:   Parametric · Local Vol · Forwards · Options · Graph · Universe
```
Term Structure ceases to be a top tab (it becomes a Parametric/Local-Vol
sub-tab). `App.tsx` `TabId`/`TABS` updated; `TopBar` unchanged structurally.

### 10A — Parametric workspace (rename Smile → Parametric, embed Term)
- [ ] Rename the tab **label** to "Parametric" (`App.tsx`). Keep the `smile`
  route id and `SmileViewer` component to minimize churn (or rename to
  `parametric` if cheap — label is what the user sees).
- [ ] Chart-card sub-tabs become **Smile · Density · Log Q-density · Term ·
  Surface · Table** — i.e. embed Term-Structure *alongside Density*. Add a
  `term` case to `ChartView` + `VIEW_HINTS` in `SmileViewer.tsx`; render
  `TermChart` (existing) in the chart body for the current ticker.
- [ ] Move the Term-Structure controls (event markers + real-time/dilated-clock
  toggle + expiry ladder table from `TermStructureViewer.tsx`) into a compact
  **TermControls** aside panel shown only when the Term sub-tab is active
  (mirrors how the strike-axis `select` shows only for the Smile view). The
  global Events ON/OFF *default* lives in Options; live per-session event
  editing stays here.
- [ ] Retire the standalone `TermStructureViewer.tsx` top-level view (its parts
  are reused: `TermChart` in the sub-tab, the controls in TermControls).
- [ ] Slim the aside (`SmileAside.tsx`) to **diagnostics + live model/fit-mode +
  scenario** only; remove `ForwardPanel` (→ Forwards tab) and the
  defaults-y knobs of `HyperparamPanel` (→ Options). Keep a minimal live
  model + fit-mode selector seeded from the Options defaults.

### 10B — Local Vol workspace (model-aware sub-tabs, derived from the LV surface)
- [ ] Add Parametric-style chart-card sub-tabs to `LocalVolViewer.tsx`:
  **Smile (reconstructed) · Density · Term · Surface (heatmap) · Table**, every
  view derived from the calibrated piecewise-affine local-vol surface (the
  existing `POST /fit/affine/{ticker}` result), not from the LQD backbone.
- [ ] Backend derivations from the cached affine fit (each ≤ 400 lines, new
  helpers next to `api/affine_fit.py`):
  - **Density**: Breeden–Litzenberger on the reconstructed arbitrage-free call
    prices per expiry (reuse `models/diagnostics.numeric_density` on the
    reconstructed slice).
  - **Term**: ATM vol / total variance / var-swap per expiry from the
    reconstructed smiles (same shape as `POST /term`).
  - **Table**: per-strike reconstructed prices/IVs (same shape as
    `GET /smiles/{t}/{e}/table`).
  Expose either as fields on the affine response or sibling GET endpoints that
  read the per-request affine cache; keep the response under the size policy.
- [ ] Frontend: reuse `DistributionChart` / `TermChart` / `QuoteTable` against
  the LV-derived payloads; the heatmap stays the "Surface" sub-tab.

### 10C — Forwards tab (new top-level, shared by Parametric + Local Vol)
- [ ] New `views/ForwardsViewer.tsx`: a per-ticker **forwards table** across all
  listed expiries (`GET /forwards/{ticker}` already returns every entry) — one
  row per expiry with the parity / theo / active columns and an inline
  mode selector + manual override (`PUT /forwards/{t}/{e}`), plus the
  ticker-level **carry (r/q)** and **dividend schedule** editor (reuse
  `DividendEditor`; `PUT /settings/market/{ticker}`).
- [ ] No engine change: both Parametric and Local Vol already read the active
  forward through the `forwards_version` fit-cache key, so edits here refit both
  workspaces automatically. Removing `ForwardPanel` from the aside is pure UI
  relocation.

### 10D — Options tab (new top-level: meta + defaults + penalties)
A preferences workspace (`views/OptionsViewer.tsx`, split into section
components to stay ≤ 400 lines). Sections:

1. **Calibration defaults** — seed every new fit/ticker/session:
   - Vol-surface model default (LQD / SVI / Sigmoid).
   - LQD: Legendre order N, damping λ + power r.
   - Sigmoid: SIV cores R + the MC-SIV defaults.
   - "Default parameters for LQD and Sigmoid" (initial-guess / bounds presets).
   - Quote weighting scheme (equal | tv_density).
   - Fit mode (Mid / Bid-Ask / Haircut) + Haircut value.
   - Local-vol **grid-size default** (nXNodes, nTNodes) + roughness λ.
   - **Prior default** (auto-load the saved prior as the fit prior on node load,
     on/off + behavior).
2. **Penalty catalogue** — each row: description + coefficient knob + formula +
   source module (formulas verified against the code 2026-06-14):

   | Penalty | Coefficient (knob) | Penalty term | Module |
   |---|---|---|---|
   | LQD high-order damping | `regLambda` λ, `regPower` r | λ · n^{2r} · a_n² (n ≥ 4; modes a₂,a₃ free) | `models/lqd/calibrate.py` |
   | Calendar slack (arb-fix) | `calendar_weight` (1e6) | w · Σ max(floor − Gᵢ(α), 0)² | `calib/calendar.py`, `lqd/calibrate.py` |
   | SVI min-variance | `_PENALTY_WEIGHT` P | P · max(−(a + bσ√(1−ρ²)), 0)² | `models/svi_jw/calibrate.py` |
   | SVI Lee wing | `_PENALTY_WEIGHT` P | P · max(b(1+|ρ|) − 2, 0)² | `models/svi_jw/calibrate.py` |
   | Band hinge + mid anchor | `haircut` h, `MID_ANCHOR_WEIGHT` (0.05) | max(model−ask,0)² + max(bid−model,0)² + 0.05·(model−mid)² | `calib/band.py` |
   | Affine LV roughness | `regLambda` (note λ=50) | √λ · L(θ − θ_ref), L = 2nd diff in (t, x) | `models/localvol/affine_calib.py` |
   | Sigmoid amplitude ridge | `_RIDGE` | ridge · Σ α_r² (hat amplitudes) | `models/sigmoid/calibrate.py` |

   Editable where a coefficient is a real knob (λ, r, haircut, calendar_weight,
   roughness); the others render formula + description read-only.
3. **Toggles — wired this phase** (map to existing engine switches):
   - **Arbitrage fix** ON/OFF → `enforceCalendar` (promote the per-request
     `SurfaceFitRequest.enforceCalendar` to a global default on `AppState`).
   - **Events** ON/OFF default → `eventsEnabled` (promote from
     `TermStructureRequest.eventsEnabled`).
   - **Variance-Swaps** ON/OFF → compute/show the var-swap level + column.
   - **Spot-Vol dynamics** default → regime (sticky-strike / sticky-delta /
     sticky-LV) + **SSR value** (feeds the Scenario panel's default).
4. **Toggles — stubbed this phase** (persisted UI state + behavior TODO):
   - **Auto-on-demand calibration**: auto-refit on edit (ON, current) vs manual
     **Calibrate** button (OFF). Persist the flag; gating behavior is TODO.
   - **Real-time / static spot prices**: stream live spot + re-price vs freeze
     at load. Persist the flag; streaming behavior is TODO (pairs with As-of).

### Backend — global settings plumbing
- [ ] New global **app/meta settings** on `AppState` (extend `FitSettings` or add
  a sibling `OptionsSettings` schema; keep schema files ≤ 400 lines) covering:
  model/N/damping/haircut/weighting (already in `FitSettings`) + grid-size
  default, var-swap on/off, prior default, events default, arb-fix default,
  dynamics regime + SSR default, spot mode (stub), auto-calibration (stub).
- [ ] `GET/PUT /settings/options` (or extend `GET/PUT /settings/fit`); fold the
  fit-affecting fields into the existing **fit-cache version** so every view
  refits consistently (same pattern as `settings_version` / `forwards_version`).
- [ ] Thread the promoted globals (`enforceCalendar`, `eventsEnabled`, var-swap,
  regime/SSR, grid-size) into the surface/term/affine/scenario call sites as the
  *default*, with any live per-node control still overriding.

### Tests & exit criteria
- [ ] Backend: settings round-trip + cache-version bump tests; LV-derived
  density/term/table golden tests (match the Parametric-shape payloads on an
  arbitrage-free affine fit); arb-fix/events/var-swap default propagation tests.
- [ ] Frontend: strict-TS build green; the six top tabs render; Parametric shows
  the Term sub-tab next to Density; Local Vol shows the five derived sub-tabs;
  Forwards edits refit both workspaces; Options persists and refits.
- [ ] Headless-Edge smoke: rename verified (Parametric), Term embedded, Forwards
  table edits a forward end-to-end, Options toggles persist across reload.
- **Exit:** tabs reorganized to Parametric · Local Vol · Forwards · Options ·
  Graph · Universe; Term embedded; Local Vol mirrors Parametric off the LV
  surface; Forwards & dividends live in one shared tab; Options drives all
  defaults/penalties/toggles (two stubbed) with a single global settings round
  trip; all tests green; files ≤ 400 lines.

---

## Execution policy (per CLAUDE.md)

- **Sub-agents:** parallelize by vertical — quant-core agent, data agent, graph agent, frontend agent — coordinated through the `SmileModel` and API interface contracts frozen at end of Phase 1/5 respectively. Spawn review agents for arbitrage-math correctness on every quant PR.
- **File size:** hard cap 400 lines; split by responsibility (basis/quadrature/pricing/calibrate pattern above).
- **Speed:** every quant function vectorized; benchmarks in CI with regression gates.
- **Comments:** every module gets a header docstring linking to the equation numbers of the relevant Doc note (e.g. "implements eq. (mu_norm) of lqd_model_note").

## Key risks & mitigations

1. **Yahoo scraping fragility** → cache snapshots, provider abstraction, fall back to stored data; treat Bloomberg/Massive as optional plug-ins.
2. **Dividends/forwards quality** → parity-implied forwards first (robust), explicit dividend curves later; sanity-check vs spot-carry.
3. **Graph hyperparameter opacity** → empirical Bayes + held-out ζ calibration baked in from day one (note §9); never ship point estimates without marginal precision.
4. **Local-vol grid arbitrage** → grid model is the hardest to keep arbitrage-free; gate it behind diagnostics and ship it last within Phase 2.
5. **Performance creep in UI** → WebSocket incremental updates, debounced refits, WebGL graph rendering from the start.

## Milestone summary

| Milestone | Content | Target |
|---|---|---|
| M1 | LQD engine reproduces both paper benchmarks | end W4 |
| M2 | 4 model families + no-arb surface construction | end W6 |
| M3 | Live Yahoo universe snapshot → calibrated surfaces | end W7 |
| M4 | Graph solver reproduces 6-node example; 1k-node < 1 s | end W10 |
| M5 | Smile Viewer trader-workflow demo | end W14 |
| M6 | Graph Viewer end-to-end extrapolation demo | end W16 |
| M7 | Vol-spot dynamics scenarios | end W17 |
| M8 | v1.0: packaged, benchmarked, documented | end W20 |
