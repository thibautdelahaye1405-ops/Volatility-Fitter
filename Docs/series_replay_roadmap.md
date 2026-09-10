# Series — harvest, store and replay a time-series of smiles and surfaces (drafted 2026-09-10)

The user's ask (2026-09-10, verbatim in spirit): *choose a ticker, a frequency
and a number of snapshots; choose a set of {model, model options} — for
instance LQD-24 with prior and Kalman filtering, SVI-JW free, LV native with
prior; press Start; the app harvests the snapshots over the period and
calibrates every one under every selection; then store the series and replay
the time-series of smiles and surfaces cinematically.*

This document refines that ask into a contract, surveys what the codebase
already provides (as of commit 26f90be, the benchmark-integrity fixes), records
the decisions proposed for ratification, and orders the build into phases
S0–S7. Conventions throughout: golden tests citing the Docs notes, files
≤ 400 lines, byte-identity for every default-off path, one commit per green
batch, long runs in the user's own window (a series job runs INSIDE the user's
server, so the tool-job kill rule never applies to it).

---

## 1. Vocabulary

| word | meaning |
|---|---|
| **Series** | one ticker, one ordered set of instants, one set of lanes, one stored result. The user-facing object (named, listed, deletable, exportable). |
| **Frame** | one instant of a series: the chain snapshot fetched AS OF that instant (quotes + spot + forwards + quote kind) and, per lane, the fits made from it. |
| **Lane** | one model configuration evaluated THROUGH TIME: a settings patch over the series' frozen base settings, plus its own temporal state (prior chain, filter state). Lanes are what the ask calls "selected models". |
| **Stage** | a view of the replay: Smile · Surface · Term · Lanes (evidence) · Frames (table). |
| **Playhead** | the frame under display; the transport bar moves it. |

The lens is called **Series** (activity `series`, Alt+6). Nothing here is a
"variant calibration" of the live Options — see §3.3 and the anchoring-axis
ruling of 2026-09-07.

---

## 2. What the refinement changes in the ask

1. **A lane is a temporal chain, not a point-wise setting.** "LQD-24 with
   prior and Kalman filter" only means something across successive frames:
   its prior at frame *i* is ITS OWN fit at frame *i−1*, and its filter
   state is carried from frame to frame with `dt` read off the snapshot
   timestamps. A free lane has no temporal state (its frames are
   independent). The runner treats the two differently (§4).
2. **Three ways to get frames, one storage.** Historical (the Massive
   per-contract NBBO history, marks fallback labelled), forward live (the
   app takes N snapshots as time passes, respecting the 2026-09-02 data
   model), and import (the app's captured snapshots, a backtest store, a
   fixture). Import gives usable series on day one, before any harvest code.
3. **Isolation from the live desk.** A series never touches the live
   workspace: not its settings, priors, filter states, calibrated pointers
   or governance log. Each lane runs on its own detached `AppState`, the
   pattern `backtest/filter_replay.py` already uses. The user can keep
   fetching and calibrating while a series runs.
4. **Faithful replay.** A frame is an observation. Nothing is interpolated
   between instants; the playhead always names the instant and the quote
   kind; ghost trails are real previous frames; a crossfade is a visual
   transition of at most 150 ms and never a data state.
5. **The cost is known before Start.** Frames × per-lane wall time from the
   measured rails, and the harvest time by source, shown in the dialog.
6. **Resumable, cancellable, restart-proof.** Frames and lane fits persist as
   they complete; a killed server resumes the job at the next frame.
7. **The evidence stage closes a standing rider.** The anchoring-axis wrap
   said the Kalman's value is temporal and asked for "a Free lane in the
   FilterTimeline / filter-replay report". A series with the lanes Free,
   + Prior, + Filter IS that report, on any ticker, any period, in the app.
8. **Ladder policy is explicit.** Pinned to the ticker's universe expiries
   (default) or a rolling ladder; each frame keeps only the expiries alive at
   its instant, so τ shrinks frame by frame and the surface stays faithful.
9. **A series is a file too.** `volfit-series/1` export / import beside the
   workspace and snapshot files; the MCP connector gets series tools.
10. **Adopting a frame is explicit.** "Adopt as prior" saves one lane's fit
    at one frame as the live prior through the normal save-equals-activate
    route; nothing else in a series writes a prior.

---

## 3. Contract

### 3.1 Creating a series (the dialog)

- **Ticker** — the node tab's ticker by default; any universe ticker. One
  ticker per series in v1 (the spec carries `tickers: [t]` so a basket is a
  non-breaking extension; cross-ticker graph replay stays with the backtest
  scenarios harness until a later arc).
- **Source** — the ticker's pinned source (`state_sources.provider_for`),
  shown with its capabilities: history yes/no, intraday yes/no, quote kind.
  Massive is the only intraday-capable history source today
  (`massive.py:447`); Bloomberg serves `prev_close` / `eod` only (daily
  series); Yahoo / exchange adapters are forward-only.
- **Mode** — *Historical* (instants in the past, harvested now) · *Live*
  (instants from now on, one frame per tick) · *Import* (pick stored
  snapshots: the app's captures, a backtest store, a fixture directory).
- **Clock** — `from`, `step`, `count` (or `to`). Steps: 1 m · 5 m · 15 m ·
  30 m · 1 h · session close · daily (a time of day, default 15:45 ET, the
  pack's "before close") · weekly. `sessionOnly` (default on) skips
  non-trading days and out-of-session instants (`expiry_time.is_trading_day`
  + the session grid `intraday_cli.grid_times`). The dialog lists the
  resolved instants and marks the ones the source cannot serve (the as-of
  capability payload, `asof.py:131-202`). Floors: 15 s live (the
  auto-update floor), 1 m historical.
- **Ladder** — `pinned` (the ticker's universe expiries at creation; a frame
  drops the ones expired at its instant) · `term` · `0dte` (the intraday
  capture ladders, `intraday_ladder.py`) · `maxExpiries` crop. Strike window
  = the source's history window (Massive: nearest-the-money first up to
  `NBBO_MAX_CONTRACTS = 1500`).
- **Lanes** — composed from presets, each a patch over the frozen base
  (§3.3): `LQD-N free` · `LQD-N + prior` · `LQD-N + prior + filter` ·
  `SVI-JW free` · `MCS free` · `LV affine free` · `LV affine + prior` ·
  `Current Options` (the live settings verbatim). Per lane: name, colour,
  family, order / cores, fit target (mid · bid-ask · haircut), weighting,
  prior mode, filter mode, LV on/off. One lane is the **production lane**
  (starred) — the one ghost trails, differences and "Adopt as prior" refer
  to. A full per-lane Options editor is a rider.
- **Estimate** — harvest time (frames × measured seconds per chain for the
  source; live = frames × step) and calibration time (frames × Σ lane cost
  from the rails; LV lanes dominate) before Start.
- **Start** — the job runs server-side; the dialog closes; progress reaches
  the status bar and the lens header through the calibration-style SSE.

### 3.2 Frames

A frame stores the chain the way the app already stores one: a `snapshots`
row + its `quotes` rows in the VolStore (`store.py:263-313`), tagged with the
source and, new, the series id (so the as-of picker keeps listing explicit
captures only — a 1-minute series must not flood `asof._captures_by_date`,
which caps at 8 per day). A frame whose (ticker, ts, source) snapshot already
exists (an import, a capture) reuses that row. Per frame the series keeps:
instant, spot, quote kind (`quotes` NBBO or `marks`), expiries present,
quote count, harvest status / error.

Historical harvest = the provider's as-of path (`AsOf(mode="intraday",
ts=…)` through `state._fetch_asof`, i.e. `massive_history` for Massive:
12 requests in flight, ~14 s per SPY chain measured 2026-09-10c, progress
narrated through `volfit.data.progress`). Live harvest = the unified
snapshot sequence at each tick (`workflow_fetch.fetch_snapshot` step (i) +
(ii) semantics: quotes AND spot from one snapshot; a streaming book is read
synchronously like `workflow.calibration_chains`). A spot-only tick never
makes a frame (the 2026-09-02g model, points 1 and 5).

### 3.3 Lanes

A lane's settings = `base_fit_settings.model_copy(update=patch_fit)` and
`base_options.model_copy(update=patch_options)`, the in-process partial
override idiom already used by `compare_anchoring.py:115,140`. The base is
the live settings snapshot at creation, frozen into the series document, so
a replay is reproducible after the live Options change. Lanes live in the
series dialog, never in Options — the 2026-09-07 anchoring ruling stands:
Options describes ONE production configuration; the anchoring cells are
shadow fits of it; lanes are jobs on stored frames.

Temporal semantics, per lane:

| lane state | frame *i* reads | seed at frame 0 |
|---|---|---|
| free | nothing from frame *i−1* | — (frames may run in parallel) |
| prior (any persistence mode ≠ off) | the lane's own frame *i−1* surface as the active prior (`priors.capture_snapshot` → `set_active_prior` on the lane's private state; transported to frame *i*'s forwards at read time by `prior_transport`) | cold: frame 0 fits free and is tagged `seed`; option `warmup = k` harvests k extra frames before `from` used only to seed; option `seed from live prior` (live mode only) |
| filter (`observationFilterMode` overlay / active) | the lane's own `NodeFilter` per (expiry, fit mode) carried across frames; `dt` from the snapshot timestamps; the 64-step history ring kept | the first commit seeds the filter from the fit's own handles (existing rule) |
| LV | the lane's own previous affine surface as the LV prior when the patch says so (`prior_lv` baskets) | cold |

Every lane fit goes through the production path — `service.calibrate_node`
→ `commit_record` → `observation_filter.commit_hook` — on the lane's
detached `AppState`, so the seed / reset / adaptive / idempotence logic runs
exactly as live. Lock: a free lane's frame fit is byte-identical to
`POST /calibrate/{ticker}` on the live state holding the same chain under
the same settings.

### 3.4 Replay (the Series lens)

Layout, top to bottom:

- **Header** — series picker for the tab's ticker (+ New series…, status
  pill running · paused · done · failed, frames n/N), lane chips (visibility
  toggle, colour, production star), stage tabs.
- **Stage** —
  - *Smile*: `SmileChart` with the frame's quotes drawn as bands per the
    lane's fit target, every visible lane's curve overlaid (a new `lanes`
    overlay slot; family colours from `lib/modelColor.ts`, dashes from
    `lib/anchoring.ts`), the expiry = the node tab's (nearest alive expiry
    when it has rolled off), axis k · K/F · **fixed strike** (the
    sticky-strike reading through time), the k-window brush persisting
    across frames, ghost trail of the production lane (0–5 previous frames,
    fading), the footer strip showing the frame's weights when the lane's
    scheme is not `equal`.
  - *Surface*: one `SurfaceMesh` per visible lane, shared camera / crop /
    crosshair (the `LvCompareView` precedent), or a signed difference sheet
    vs the production lane; τ recomputed per frame; ATM ridge.
  - *Term*: `TermChart` gains a lanes slot — ATM vol and var-swap vol per
    expiry per lane, both clocks, the frame's events / dividends.
  - *Lanes* (evidence): per-lane time series over the frames — rms bp, max
    error bp, arbitrage flags, prior pull (ATM / skew / curvature distance
    from the free lane, `compare_anchoring.attach_pull` vocabulary), filter
    ζ and gain, fit ms — and a summary table: mean rms, worst frame,
    **handle-path roughness** = mean |Δσ_atm|, |Δskew| between consecutive
    frames (the damping a prior or a filter buys, at what rms cost). The
    filter lane's ring renders through the existing `FilterTimeline`
    (`components/FilterTimeline.tsx`) with the playhead as its cursor.
  - *Frames*: a table (instant, spot, quotes, quote kind, per-lane status /
    rms); click = jump.
- **Filmstrip** — sparklines across all frames: spot, ATM vol of the shown
  expiry per lane, rms per lane; the playhead line crosses them; hover
  previews the frame.
- **Transport bar** — ⏮ ◀ ▶ ⏸ ▶ ⏭ · speed 0.25× … 8× (1× = 500 ms per
  frame) · loop · frame-index-linear scrubber with instant ticks and
  session-gap markers (a wall-clock axis option shows the gaps) · readout
  `2026-09-08 15:45 ET · frame 37/60 · NBBO`. Keys: Space play/pause, ←/→
  step, Shift+←/→ ×10, Home/End, L loop. The pacer follows the
  `useWaveTimeline` doctrine already followed by `lib/lvTrace.ts`:
  epoch-keyed, `prefers-reduced-motion` short-circuits autoplay, terminal
  frame absorbing unless loop.

Frame payloads are fetched per (series, frame) — the frame's market plus
every lane's curves, surface grid and metrics in one response — and kept in
a client LRU with prefetch ±24 frames so playback never waits at 8×.

### 3.5 Persistence, export, handoff

- The series, its frames, lanes and fits live in `VOLFIT_DB` (schema v11,
  §5). Retention: explicit delete only (cascades to series-owned snapshots
  that no capture or other series references).
- `volfit-series/1` file = spec + lanes + frames (chains via
  `export_inputs.export_chain`, the snapshot-file convention) + fits;
  import recreates the series (idempotent by id). File ▾ rows beside the
  workspace and snapshot files.
- "Adopt as prior" (lane, frame) → `priors.capture_snapshot` on the lane's
  state → `state.save_prior_snapshot` on the live state (save = activate,
  the 2026-09-07c ruling), logged as a governance event with the series id.
- PNG of the current frame through `lib/chartPng.ts`. A WebM export of a
  playback (`MediaRecorder` on the stage canvas) is a rider.
- MCP tools: `create_series`, `wait_for_series`, `series_report`,
  `chart_series_frame` (S6), on the background-job pattern of
  `volfit_mcp/jobs.py`.

---

## 4. What exists (verified 2026-09-10 — reuse, do not rebuild)

**Storage.** `volfit/data/store.py` (schema v10 at `:55`): `snapshots`
keyed (ticker, ts, source) with `save_snapshot(:263)`, `list_snapshots(:375)`,
`snapshot_at(:403)` (at-or-before); `fits` mirrored per slice by
`api/history.py persist_fit(:44)` keyed by the chain's snapshot timestamp,
read by `GET /history/{ticker}/{tenorDays}` (no frontend consumer yet);
`prior_snapshots`; workspace docs. No retention anywhere. Captured live
snapshots are lossy by design: one per ~60 s per ticker and never for
Massive / Bloomberg / file (`state.py:87 NO_AUTO_CAPTURE_SOURCES`,
`_persist_capture :798`).

**History.** `volfit/data/massive_history.py` (per-contract NBBO at any
instant, 12 in flight, 1500 contracts nearest-the-money first, marks
fallback gated per session, live-verified 2026-09-10c); `flatfiles.py`
(minute / day marks); the as-of dispatch `state._fetch_asof(:762)`; the
capability payload `api/asof.py asof_payload(:131)`.

**Multi-instant capture.** `backtest/capture_intraday_rest.py` already
writes N instants per (ticker, day) into a VolStore, resumable per instant,
with settlement + tick metadata; grid `intraday_cli.grid_times(:37)`, ladders
`intraday_ladder.py`. Fixtures: `fixtures/intraday/*.json` = one file per
(asset, day) holding an ordered `snapshots` list; daily fixtures = one file
per (regime, date, ticker).

**Detached states.** `volfit/replay_report.py _StoredChains(:44)` (a
production provider over stored snapshots), `backtest/graph_intraday.
instant_state(:98)` (one AppState per instant, intraday clock on),
`backtest/filter_replay.py replay_day` (filter states + rings carried across
per-instant states; data version bumped per instant — the exact live
fetch → calibrate → commit sequence, artifact byte-identical to the live
ring wire shape).

**Calibration.** `service.calibrate_node` → `commit_record(:2005)`;
`workflow_stages` + `api/jobs.py CalibrationJobs` (ONE job process-wide,
`:86`) + `fit_pool` (`VOLFIT_CALIB_WORKERS`); SSE `GET /calibration/stream`.
Settings: `FitSettings` (25 fields) + `OptionsSettings` (92 fields) in
`api/schemas.py`; `model_copy(update=)` is the override idiom; `fitMode` is a
per-request parameter. Priors: `priors.capture_snapshot(:88)`,
`state.set_active_prior(:1725)`, `save_prior_snapshot(:1620)`,
`prior_transport`. Filter: `observation_filter.on_fit_commit(:409)`,
states in `Workspace.filter_states`, rings in `AppState._filter_history`.
Anchoring shadow fits: `compare_anchoring.py` (cells free / prior / filter).

**Rails (dev box).** LQD-16 slice ≈ 13.5 ms; MCS n=3 ≈ 33 ms; symmetric
exchange ≈ 74 ms; LV SPY cold (176 vertices) ≈ 1.2 s, a wide ladder with a
0–2-day front rung ≈ 25 s, 533 vertices ≈ 86 s; whole Calibrate SPY + NVDA
(8 nodes + 2 LV) ≈ 4 s; the LV client budget is 300 s.

**Frontend.** Lens registration is a six-file mechanical change
(`state/workbenchPersist.ts:13` union + bar entries, `shell/ActivityBar.tsx:
17-23` icons, `shell/MainPane.tsx:57-63` switch, `lib/commands.ts:67-71` +
`state/commands.tsx`, `lib/shortcuts.ts:26`, `state/useDeepLink.ts:21-33`,
`lib/help/guides/index.ts:46-52 LENS_GUIDE` + `content.test.ts:20`,
`state/useLensViewMemory.ts:15`). Playback: `lib/lvTrace.ts` +
`components/LvTracePlayer.tsx` (scrubber, pacer, reduced motion, pure and
vitest-locked). Overlays: `components/OverlayCurvesChart.tsx` (N series,
brush, hover), `SmileChart.tsx` (props-only, named overlay slots + footer
render-prop), `SurfaceMesh.tsx` (data-in, shared camera / crop / hover),
`localvol/LvCompareView.tsx` (two sheets + difference), `TermChart.tsx`
(single curve set), `FilterTimeline.tsx` + `FilterTimelineSection.tsx`
(the Live | Replay chip). Progress: `state/useWorkflow.ts` (SSE + poll),
`state/workflowTypes.ts`. Colours: `lib/modelColor.ts`, `lib/anchoring.ts`.
Files: `lib/snapshotFile.ts`, `lib/workspaceFile.ts`. Smoke checks own their
ports (4188–4196; the series check takes **4197**).

**Missing, in one list.** A series entity and the fit ↔ stored-chain link; a
configuration dimension on fits and on filter state; an in-app harvester
(historical or scheduled); a second job slot; a per-request settings
override (today A/B mutates the globals); series read / frame endpoints;
a time-indexed scrubber with speed / loop / keys; a lanes overlay on the
smile, surface and term charts; a client series cache; help + smoke.

---

## 5. Data model (schema v11)

```
series        (id TEXT PK, name, ticker, source, mode, created_ts, status,
               spec_json,           -- clock, ladder, tickers[], options
               base_fit_json, base_options_json,   -- frozen live settings
               fit_mode, note, error)
series_lanes  (series_id FK, lane_id TEXT, ord, name, colour, family,
               patch_fit_json, patch_options_json, production BOOL,
               PRIMARY KEY (series_id, lane_id))
series_frames (series_id FK, idx INT, ts TEXT, snapshot_id FK snapshots.id NULL,
               spot, quote_kind, n_quotes, expiries_json, status, error,
               harvested_ts, PRIMARY KEY (series_id, idx))
series_fits   (series_id FK, lane_id, idx INT, expiry TEXT DEFAULT '',  -- '' = LV surface
               model, params_json, display_json, diagnostics_json,
               metrics_json, fit_ms, status, error,
               PRIMARY KEY (series_id, lane_id, idx, expiry))
snapshots     + series_id TEXT NULL (additive ALTER; excluded from the as-of picker)
```

(S0 as built, 2026-09-10i: the LV row stores `expiry = ''` rather than NULL
because SQLite treats NULLs as distinct inside a primary key; the wire
`LaneFitDoc.expiry` is `None` for that row and the store maps between the
two. The child tables cascade on the series' delete. The tables live in
`data/store_series.py`; the shapes in `api/schemas_series.py` with the
presets in `api/series_presets.py`.)

`params_json` / `display_json` follow the snapshot-file calibration shape
(`snapshot_files.py:121-146`: `lqd{L,R,a,alphaL,alphaR}`, `display`,
`diagnostics`), so a stored fit re-renders without a refit and the existing
`FileProvider` import path understands it. The LV surface row stores the
nodal variance grid the way `PriorSurfaceSnapshot.lvSurface` does. Per-lane
filter rings persist under the series (`series_filter_json` on the lane row,
`filter_history.step_doc` shape), so the Lanes stage can draw them after a
restart.

Sizes: a SPY frame ≈ 1–3 k quote rows; 60 frames ≈ 180 k rows ≈ 20 MB; fits
are a few KB per (lane, frame). A 1-minute full-session series (390 frames)
is the upper design point.

---

## 6. API surface

| verb | route | purpose |
|---|---|---|
| POST | `/series/estimate` | resolve instants, servability, cost (dry run) |
| POST | `/series` | create (spec + lanes), returns id + estimate |
| GET | `/series?ticker=` | list (id, name, ticker, mode, status, n/N, created) |
| GET | `/series/{id}` | spec, lanes, frame index (no payloads) |
| DELETE | `/series/{id}` | delete (cascade rule §3.5) |
| POST | `/series/{id}/start` · `/pause` · `/resume` · `/cancel` | job control |
| GET | `/series/{id}/status` · `/series/stream` | progress (SSE, the calibration stream pattern) |
| GET | `/series/{id}/frame/{idx}?lanes=&expiry=` | the frame payload: market (quotes per expiry, spot, forwards, events), per lane curves per expiry, surface grid, term points, metrics |
| GET | `/series/{id}/strip?lanes=` | the filmstrip: per frame per lane scalars |
| GET | `/series/{id}/lanes/{lane}/filter/{expiry}` | the lane's ring (FilterStepOut wire shape) |
| POST | `/series/{id}/adopt-prior` | `{lane, idx}` → live prior (save = activate) |
| POST | `/series/{id}/export` · `/series/import` | `volfit-series/1` |
| POST | `/series/import-store` | from a backtest store / fixture dir / the app's captures |

Frame and strip payloads are cached server-side per (series, frame, lanes)
in an LRU; curves are evaluated from stored params (`service.model_curve`),
never refit on read.

---

## 7. Decisions proposed for ratification (veto here)

- **D1 Names** — Series / frame / lane / stage; lens "Series" on Alt+6.
- **D2 Scope** — one ticker per series in v1; spec carries `tickers[]`.
- **D3 Lanes = patches over a frozen base**, composed from presets in the
  series dialog; never in Options (anchoring ruling). No per-lane full
  Options editor in v1.
- **D4 Chaining** — a lane's prior is its own previous frame; cold start
  (frame 0 tagged seed) by default; `warmup` and `seed from live prior`
  (live mode) as options; the live prior is otherwise never read.
- **D5 Isolation** — detached `AppState` per lane; a separate `SeriesJobs`
  slot (one series at a time, a queue of pending); the fit pool shared with
  the live Calibrate (CPU contention accepted, both stay usable); nothing
  of the live workspace or its governance log is written by a series;
  results persist in `VOLFIT_DB` v11; frames excluded from the as-of picker.
- **D6 Ladder** — `pinned` default, `term` / `0dte` optional, `maxExpiries`.
- **D7 Sources** — historical (Massive NBBO, marks fallback labelled per
  frame), live (any source, 15 s floor, streaming book sampled
  synchronously), import. Bloomberg = daily series only; Yahoo = live only.
- **D8 Faithful replay** — no interpolation; crossfade ≤ 150 ms visual only;
  playhead names instant + quote kind; ghost trails are real frames.
- **D9 Fixed-strike axis** on the Smile stage; k-window persists.
- **D10 Evidence** — rms / max / arb / pull / ζ / gain / fit ms per frame per
  lane + handle-path roughness; filter rings through `FilterTimeline`. This
  closes the anchoring-axis phase-two rider.
- **D11 Locks** — free-lane byte-identity with live Calibrate; a lane with
  the filter reproduces `backtest/filter_replay` on the same store; a
  re-run of a stored series reproduces its fits (certification case).
- **D12 Handoff** — `volfit-series/1` file; MCP tools in S6; WebM a rider.

---

## 8. Phases

### S0 — Contract (one small commit, the parallel-wave convention)

Schemas in a new `api/schemas_series.py`: `SeriesClock`, `SeriesSpec`,
`LaneSpec` (+ `LANE_PRESETS`), `SeriesDoc`, `FrameDoc`, `LaneFitDoc`,
`SeriesStatus`, `SeriesEstimate`, `FramePayload`, `StripPayload`. Store v11
migration in `data/store.py` (additive DDL + the `snapshots.series_id`
column; the picker's `_captures_by_date` filters it). Decision record (this
section) linked from the ROADMAP arc header. No new Options field, so the
help schema does not move; the Docs catalog entry for this file is added.
Tests: schema round trip, migration from a v10 file, picker exclusion.

### S1 — Store + import + read API

`api/series_store.py` (CRUD over the four tables, ≤ 400 lines),
`api/series_import.py` (from the app's captured snapshots of a ticker; from
a backtest VolStore via `list_snapshots`; from an intraday fixture's
`snapshots` list and from daily fixtures across dates — the two fixture
shapes get ONE loader), router `api/routers/series.py` (list / get / delete
/ import-store). Exit: the 0DTE campaign store and the V3.8 replay-day store
import as series in seconds; `GET /series/{id}` lists their frames; tests on
the tiny synthetic store `test_filter_replay` already uses.

(S1 as built, 2026-09-10j: `POST /series/import-store` takes
`SeriesImportRequest {name, ticker, source: {kind: captures | store |
fixtures, path?, start?, end?, maxFrames?}, lanes? | presets?, fitMode?,
ladder?, note}`; captures are REFERENCED by snapshot id, store / fixture
chains are copied as series-owned rows; the clock is derived from the
median gap; daily-fixture hygiene is a rider. Measured: the 0DTE campaign
store → 60 SPY frames in 1.2 s, the replay-day store → 25 in 0.3 s.)

### S2 — Harvest engine + job slot

`api/series_instants.py` (resolver: step grid, session calendar, servability
from the as-of payload, floors), `api/series_harvest.py` (historical: the
provider's as-of path per instant, concurrency = the provider's, progress
narrated; live: a `SeriesSchedule` armed on the scheduler tick, one frame per
step, reading the book synchronously when streaming; both persist the frame
as it lands), `api/series_jobs.py` (`SeriesJobs`: one running series, a
queue, pause / resume / cancel, per-frame checkpoints, restart recovery →
`paused`), `/series/estimate`, `/start` … `/cancel`, `/status`, `/stream`.
Exit: a 20-frame × 15-minute historical SPY series harvests on the user's
key in under 6 minutes; a kill mid-harvest resumes at the next frame; a live
5-frame × 15 s series on the synthetic source runs green in the suite; the
as-of picker's listing is unchanged by a 60-frame series.

(S2 as built, 2026-09-10k: the live runner waits for each frame's instant
in its own daemon thread — a 1 s wake-able wait — instead of a
`SeriesSchedule` on the scheduler tick (same effect, no coupling to the
Auto-update timer); the stream route is `GET /series/stream/{id}`; the
`term` / `0dte` ladders crop after the fetch of the provider's natural
ladder; unservable instants are stored as `skipped` frames. Live check on
the user's Massive key: SPY 15 m × 2 on the latest completed session, done
in 32.7 s against a 28 s estimate, both frames real NBBO.)

### S3 — Lane calibration

`api/series_lanes.py` (detached `AppState` per lane over a `_SeriesChains`
provider — generalize `replay_report._StoredChains`; patch application;
prior / filter chaining per §3.3; commit → `series_fits` with metrics;
per-frame checkpoints), `api/series_metrics.py` (rms / max / arb flags /
pull vs the free lane / ζ / gain / roughness), LV lanes through the affine
path (`affine_fit.calibrate_affine_surface` on the lane state), lanes run
concurrently (one thread per lane, slice fits through the shared pool; free
lanes frame-parallel). Locks: free-lane byte-identity with
`POST /calibrate/{ticker}`; prior lane equals a manual roll; a filter lane
reproduces the `filter_replay` ring on the same store; cancel then resume
continues at the frame; the whole S1 import store calibrates under three
lanes inside the perf rail (60 frames × 2 LQD lanes < 60 s on the dev box).

(S3 as built, 2026-09-10l: lanes run SEQUENTIALLY in the job thread (the
concurrency of free lanes is a rider); the lane frame is calibrated by
`workflow.calibrate_ticker` — the desk's own items — and the carry (prior
snapshot + filter docs) is checkpointed per (lane, frame) into the lane
row; the intraday clock is ON for a sub-day series unless the lane patch
says otherwise, and a rung past its settlement instant is dropped. The
rail as measured on the 0DTE campaign store (60 SPY frames, 7.3
expiries, 1,961 quotes, American): free lane 28 s (391 ms per frame
median) — inside the rail; hybrid-prior lane 160 s (1,266 ms median, a
44 s outlier where the calendar repair grinds under the prior anchor
rows) — the rail is honoured by free lanes only; both lanes 192 s wall.
Finding: the ACTIVE filter under the calendar-coupled solver on a dense
intraday ladder does not converge — its per-node predictions are not
calendar-consistent, the symmetric repair grinds to its escalation limit
(451 s on one frame) and dies in a NaN; creation warns for that lane
combination and a dying repair keeps the phase-A fits. The fix belongs to
the observation-filter arc.)

### S4 — Series lens v1 (frontend)

Lens registration (the six files) + guide `series` + command docs + Alt+6 +
deep link `?node=T|E&activity=series&series=ID&frame=I` +
`useLensViewMemory` widened. `lib/seriesPlayback.ts` (pure: playhead, speed,
loop, keys, prefetch window — vitest-locked, generalizing `lvTrace`),
`state/useSeries.ts` (list / doc / status via SSE + poll), `state/
useSeriesFrames.ts` (LRU + prefetch), `components/series/` (SeriesHeader,
LaneChips, TransportBar, Filmstrip, FramesTable, NewSeriesDialog with the
estimate and the lane composer), `views/SeriesViewer.tsx` (≤ 400 lines:
header + stage switch + transport) with the Smile stage first: `SmileChart`
gains a `lanes: OverlaySeries[]` slot (bands, crosshair, brush, footer
untouched; ghost trail = extra faded series). Smoke `scripts/series_check.mjs`
on 4197 (import a stored series on the smoke server, play, scrub, keys,
screenshots). Exit: play / pause / scrub / step at 8× without a fetch stall on
a 60-frame series; the walkthrough gains a Series step.

(S4 as built, 2026-09-10m: the frame payload is `GET /series/{id}/frame/
{idx}?lanes=` with `market[expiry] = {expiry, t, tau, forward, discount,
spot, quotes: QuoteBand[]}` and per lane `{slices[{expiry, t, forward, k[],
iv[], atmVol, skew, curvature, metrics}], surface{k[], tau[], expiries[],
sigma[][]}, term[{expiry, t, atmVol, varSwapVol}], metrics, status}`,
memoized per (series, frame, lanes, stored fits); the strip carries
`atmVol[lane][]` of the shown expiry and `lanes[lane][rmsBp | maxIvBp |
pullAtmBp | zetaAtm | fitMs][]`; `GET /series/presets` resolves the eight
presets against the live settings. The lens: a series never autoplays;
1× = 500 ms per frame; the smoke check creates a LIVE series through the
API (the synthetic source has no history) rather than importing a stored
one; the walkthrough step is deferred; the Surface · Term · Lanes tabs are
disabled until S5.)

### S5 — Surface · Term · Lanes stages

Surface stage (N `SurfaceMesh` sheets with shared camera / crop / hover, the
difference sheet vs production, τ per frame), Term stage (`TermChart` lanes
slot), Lanes stage (`OverlayCurvesChart` over the strip metrics, the summary
table, `FilterTimeline` fed by the lane ring with the playhead cursor),
ghost trails on the surface (rider if the SVG mesh cost bites). Exit: the
three lanes Free / + Prior / + Filter on the V3.8 replay-day store show the
damping and its rms cost in one screen; the roughness table matches the
metrics endpoint (vitest + a backend lock on a synthetic series).

(S5 as built, 2026-09-10n: the evidence is a backend route
(`GET /series/{id}/evidence`) derived from the strip; the lane filter
ring route carries `frameIdx` per step (matched by order — a step's `ts`
is a local-clock epoch); `FilterTimeline` gained an optional `cursor`;
the difference surface reuses the LV compare's diverging heatmap (axis
K/F, outside the shared crop); the term lanes sit on the calendar clock.
Exit readout on the replay-day SPY series (25 × 15 min, six expiries),
one-day rung: free rms 4.66 bp / roughness ATM 18.36 bp per frame;
+ prior 5.20 bp / 17.49 bp, |pull| 3.57 bp; the overlay filter leaves the
fit untouched and adds the ring (ζ std 0.82). The "+ Filter" lane of the
exit had to be the OVERLAY filter: the active MAP block is not usable at
intraday cadence on short rungs today (313 s on one frame, 10 failed
slices, 299 bp median rms with calendar coupling off) — the finding of S3
widened; creation warns for any active-filter lane on a sub-day series.
The evidence check `frontend/scripts/series_evidence_check.mjs` (:4198)
serves the prepared store through `smoke_server.py --db … --tickers SPY`.)

### S6 — Files, adopt, connector

`volfit-series/1` export / import (`api/series_files.py`, `lib/seriesFile.ts`,
File ▾ rows through the command registry, drop routing beside the snapshot
file), `POST /series/{id}/adopt-prior`, PNG frame export, MCP tools
`create_series` / `wait_for_series` / `series_report` / `chart_series_frame`
(an MCP App with a scrubber over frame payloads) + a connector guide
paragraph. Exit: export → delete → import round-trips byte-identically;
Adopt as prior lights the live + Prior cell for that node.

(S6 as built, 2026-09-10o: the bundle is `{schema, savedAt, app, series
(the SeriesDoc), chains[{idx, spot, timestamp, chain}], fits[], carries{}}`;
import keeps the file's series id and is idempotent; the adopted prior's
`dataTs` is the frame's instant and its `asOfLabel` names the frame; the
header carries Export and Adopt as prior, the File menu Open series…, a
drop on the shell imports; the connector gained `list_series`,
`create_series`, `import_series`, `wait_for_series`, `series_report`,
`series_control`, `series_frame` and the `chart_series_frame` app with a
PNG fallback. Both exits hold: the round trip is byte-identical on
everything the store keeps, and Adopt lights the + Prior cell on the live
smile — locked in the backend suite and in the live check.)

### S7 — Hardening + docs

Perf rails (frame payload warm < 50 ms; strip < 100 ms for 390 frames × 3
lanes; the S3 calibration rail), the certification case
`series_replay_determinism` (a stored series re-run reproduces every fit),
retention / delete cascade lock, a shared-prep optimization when lanes agree
on the prep-affecting settings (de-Am once per frame), Help Center (guide
polish, glossary `series` / `lane` / `frame`, What's new, tips), CLAUDE.md
command line, ROADMAP wrap.

---

### Arc wrap (2026-09-10p — S0–S7 shipped)

Everything in §8 shipped the same day the decisions were ratified, with
these deviations from the plan, all recorded in the as-built notes: the
live runner waits in its own thread (no scheduler hook); lanes run
sequentially in the job thread; the intraday clock is on for sub-day
series; the evidence is a backend route; the filter ring maps steps to
frames by order; the difference surface reuses the LV compare's heatmap;
the term lanes sit on the calendar clock; the walkthrough keeps its
ratified twelve steps; the shared de-Am prep stayed a rider (measured
11–34 % of a frame). The rails as measured: free lane 391 ms per frame
on the 0DTE store (28 s for 60 frames), hybrid-prior lane 1,266 ms
(160 s), filmstrip 90 ms and evidence 120 ms at the 390 × 3 design point,
a warm frame 3 ms. Two findings belong to other arcs: the ACTIVE
filter's MAP block is not usable at intraday cadence on short rungs
(NaN fits, minutes per frame — creation warns, the overlay filter keeps
the ring evidence), and the prior lane's calendar repair grinds on a few
frames (a 44 s outlier). The exit readout (§8 S5) stands: on the
replay-day SPY series the hybrid prior damps the one-day rung's ATM path
18.4 → 17.5 bp per frame for +0.5 bp of rms.

## 9. Standing constraints (from the ratified rulings)

- **Anchoring axis (2026-09-07)** — no variant calibrations in Options;
  lanes are series-dialog objects over stored frames; shadow fits stay
  read-only. The Series lens is the temporal phase two the ruling asked for.
- **Auto-update model (2026-09-02g)** — a frame prices spot and quotes from
  one snapshot; a spot-only update never makes a frame nor a fit; live
  series respect the 15 s floor and the freeze switch.
- **One prior per node, active on save (2026-09-07c)** — a series never
  writes a prior; Adopt as prior is explicit and goes through the save
  route.
- **Per-ticker sources (2026-09-02h)** — the series source is the ticker's
  pinned source at creation; the as-of picker stays on the default source
  and never lists series frames.
- **Bloomberg one root per date (2026-09-09j)** and the capture twins'
  OCC-root policy apply to every harvested frame (the provider path already
  enforces them).
- **400-line files; golden / invariant tests; byte-identity for default-off
  paths; help locks (`commandDocs`, `LENS_GUIDE`, `GUIDE_IDS`, chord docs);
  smoke on its own port; long runs in the user's window.**

## 10. Risks

- **Harvest cost on names with wide boards** — 1500 contracts per instant
  is the Massive budget; a 1-minute series on a mega-cap is minutes per
  frame at worst. The estimate must be shown and the strike window
  configurable.
- **LV lanes dominate wall time** — 1–25 s per frame; the dialog warns past
  a budget and the lane can be limited to every k-th frame (rider).
- **Filter semantics at coarse steps** — the session clock (2026-07-16) is
  the right `dt` for sub-day steps; daily and weekly steps fall back to the
  calendar clock (the lane patch decides; the default preset sets
  `filterClock` from the step).
- **Ladder roll-off in long series** — pinned expiries vanish frame by
  frame; the Smile stage must degrade to the nearest alive expiry and say
  so in the readout.
- **SVG surface cost with N sheets** — three `SurfaceMesh` sheets at 8×
  playback may drop frames; prefer the difference sheet when more than two
  lanes are visible (rider: a canvas renderer).
- **Schema churn** — v11 is additive; the picker exclusion is the only
  behavioural change on existing paths (locked).

## 11. Deferred (explicitly out of this arc)

Multi-ticker series and graph replay (rides the scenarios harness); a
per-lane full Options editor; WebM export; morphing between frames; a
canvas surface renderer; retention policies beyond explicit delete; series
on the remote MCP path (M3).
