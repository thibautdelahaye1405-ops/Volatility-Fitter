# API surface and UI inventory — the reference application's externally visible shape

**Companion to `VOL_FITTER_CLEAN_ROOM_REBUILD.md`. Route list extracted from the
running reference backend on 2026-07-29 (107 routes). The rebuild is free to
choose different URL names and groupings; what must be preserved is the
*capability* each route represents, the read/write discipline, and the
workflow semantics. Use this as a completeness checklist.**

Conventions in the reference implementation worth keeping:

- One FastAPI app, typed request/response models for every route, camelCase
  JSON field names throughout.
- Read endpoints never fit or mutate; expensive work happens in the background
  Calibrate job; progress is pushed over Server-Sent Events.
- Draft vs active lifecycle for graph configuration; what-if/preflight/holdout
  routes never persist state.
- Publish is guarded: a blocked publish returns HTTP 409 with typed reasons
  before any manifest persists.

---

## 1. Data sources, as-of, fetch, scheduler

| Route | Semantics |
|---|---|
| `GET /datasources` | All configured sources with status lights (`?refresh=true` re-probes health). |
| `POST /datasource/{source_id}` | Switch the active source; refetches on the new feed. |
| `GET /asof`, `POST /asof` | Global as-of selection (live / previous close / historical). |
| `POST /fetch/spots` | Fetch spots; transports surfaces analytically (no refit). |
| `POST /fetch/options` | Fetch option chains; marks affected nodes stale; calibrates only if auto-calibrate is on. |
| `GET /scheduler` | Scheduler state (spot polling, auto-fetch, stream-refit loops). |
| `GET /massive/iv/{ticker}` | Provider-computed IV/greeks passthrough diagnostic (optional, provider-specific). |

## 2. Universe and lit/dark state

| Route | Semantics |
|---|---|
| `GET /universe` | Selected universe (tickers, expiries, counts). |
| `GET /universe/search` | Provider symbol search. |
| `POST /universe/tickers`, `DELETE /universe/tickers/{symbol}` | Add/remove tickers. |
| `GET/PUT /universe/{ticker}/expiries`, `POST .../expiries/reset` | Per-ticker expiry selection with expiry-type labels. |
| `GET /universe/lit`, `PUT /universe/lit/{ticker}`, `PUT /universe/lit/{ticker}/{expiry}` | Lit/dark state at ticker and node granularity. |
| `GET /universes`, `POST /universes/{name}`, `DELETE /universes/{name}`, `POST /universe/load/{name}` | Named universe save/list/delete/load. |

## 3. Settings

| Route | Semantics |
|---|---|
| `GET/PUT /settings/fit` | Fit settings (see `SETTINGS_REFERENCE.md` §1). |
| `GET/PUT /settings/options` | Engine/meta settings (§2). |
| `GET/PUT /settings/market/{ticker}` | Per-ticker carry inputs (§3). |
| `GET/POST/DELETE /settings/defaults` | Persist current Fit+Options as startup defaults / read status / reset to code defaults. |

## 4. Market data views: carry, forwards, spot

| Route | Semantics |
|---|---|
| `GET /carry/{ticker}` | The versioned per-ticker carry curve: forward/discount/dividend/borrow with per-component source and confidence. |
| `GET /forwards/{ticker}` | Forwards by maturity: active, parity, theoretical, manual; provenance; American-correction materiality. |
| `PUT /forwards/{ticker}/{expiry}` | Per-expiry forward policy override (with provenance). |
| `GET/PUT /spot/{ticker}` | Spot state; manual spot moves trigger analytic transport. |
| `GET /spot/{ticker}/live` | Live provider spot. |
| `POST /spot/{ticker}/calibrate` | Re-anchor: explicit calibration clearing temporary transport state. |

## 5. Calibration workflow

| Route | Semantics |
|---|---|
| `POST /calibrate` | Background calibration of all lit nodes (slice fits in a bounded process pool + per-ticker LV fits as separate tasks). |
| `POST /calibrate/{ticker}`, `POST /calibrate/{ticker}/{expiry}` | Scoped calibration. |
| `POST /calibrate/cancel` | Cancel between bounded work units. |
| `GET /calibration/status` | Poll status (progress, stale counts, failures). |
| `GET /calibration/stream` | **SSE push stream** of calibration status — the UI's progress source. |

## 6. Smiles, edits, priors, filter (per node)

| Route | Semantics |
|---|---|
| `GET /smiles/{ticker}/{expiry}` | Smile data: quote bands, fit curve(s), prior overlay, filtered overlay, diagnostics, var-swap info, certificate state. |
| `GET .../density` | Density / log-quantile-density arrays. |
| `GET /smiles/{ticker}/densities` | Stacked densities across expiries. |
| `GET .../table`, `GET .../table.csv` | Per-quote table (also CSV download). |
| `POST .../edits` | Quote include/exclude/amend edit session. |
| `POST .../undo`, `POST .../redo` | Quote-edit undo/redo. |
| `POST .../varswap`, `.../varswap/undo`, `.../varswap/redo` | Var-swap quote edit session with its own undo/redo. |
| `POST .../prior` | Save prior snapshot for the node. |
| `GET .../prior-diagnostics` | Auditable prior-persistence state: active mode, per-operator prior value, observed precision, required precision, activation gap, active weight. |
| `GET .../filter` | Observation-filter step: prediction, observation, innovation, gain, posterior, uncertainty, transport distance, contamination, reset reason. |
| `GET /priors`, `POST /priors/fetch`, `POST /priors/save-all`, `POST /priors/seed` | Prior inventory; resolve each ticker's prior via the freshness ladder (saved → 15-min-before → …); bulk save; seed. |

## 7. Surfaces, term structure, local vol, history, scenarios

| Route | Semantics |
|---|---|
| `POST /fit/surface` | Joint surface fit (calendar-coupled per Options). |
| `GET /surface/{ticker}` | Fitted surface view (ordered slices + calendar/LV diagnostics). |
| `POST /term/{ticker}` | Term structure (vol and variance; calendar and event-dilated clocks; dividend markers). |
| `POST /fit/affine/{ticker}` | Local-vol (piecewise-affine) joint surface calibration. |
| `POST .../density`, `.../table`, `.../term` | LV-derived views from converged PDE reprices. |
| `GET .../grid-info` | The actual vertex grid the current Options produce (renders in the Options panel). |
| `GET .../optimal-size` | Suggested grid sizing diagnostic. |
| `GET /localvol/{ticker}` | LV surface view (heatmap/3D data). |
| `GET /history/{ticker}/{tenor_days}` | Fit history time series at a tenor. |
| `POST /scenario/ssr` | Spot-move scenario under the selected dynamics regime (sticky strike/moneyness/local-vol/custom SSR); returns pre/post curves. |
| `GET/PUT /events/{ticker}`, `POST /events/{ticker}/autocalibrate` | Event calendar read/edit; infer event weights from the observed term structure (the calendar as an inverse problem). |

## 8. Graph

| Route | Semantics |
|---|---|
| `GET /graph/nodes` | The chart-baseline lattice: selected universe, transported-prior handles, provenance — the zero-observation baseline. |
| `GET/PUT /graph/edges` | Persisted per-edge overrides (weight + beta); empty = auto-lattice. |
| `GET /graph/edges/lattice` | Auto-lattice edges as editable rows ("seed from lattice"). |
| `GET/PUT /graph/edges/blocks` | Ticker-block rule (bulk relationship spec) + its expansion into per-edge overrides. |
| `GET/PUT /graph/edges/messages` | DRAFT message-relation rows (GET falls back to active when no draft). |
| `GET /graph/edges/messages/auto` | Auto relations over the selected universe as editable rows. |
| `GET /graph/config/messages` | Both lifecycle slots (draft + active), rows included. |
| `POST /graph/config/messages/activate` | Promote draft to ACTIVE (event-logged); 400 when nothing staged. |
| `POST /graph/config/messages/revert` | Discard draft — back to a clean copy of active. |
| `PUT /graph/config/messages/policy` | Stage layered-mode policy dials (residual half-life, clamp policy, …) on the DRAFT. |
| `POST /graph/preflight` | DRY RUN over the same request Run would use: blockers and warnings (empty universe, missing priors, unsupported components, extreme beta, precision outliers, directed cycles, conditioning, residual-config mismatch, stale residuals). Never mutates. |
| `POST /graph/extrapolate` | Production prior-anchored extrapolation over the selected lit+dark universe; solver params on the request (wire default remains smooth_field; UI sends its configured mode). Supports synthetic what-if observations (non-persisting) and calendar policy overrides. |
| `GET /graph/extrapolate/nodes/{ticker}/{expiry}` | One node's full reconstructed smile + prior/lit overlays + quote metrics + decomposition (baseline + systematic + residual + harmonic, with consistency χ) + exact attribution rows. |
| `POST /graph/extrapolate/lv/{ticker}` | Project the ticker's graph-extrapolated smiles onto an affine local-vol surface. |
| `POST /graph/observation-plan` | Rank non-observed nodes by closed-form exposure-weighted posterior-variance reduction: "which node should be quoted next?" with per-beneficiary breakdown. |
| `POST /graph/backtest` | Current-day leave-one-node-out comparison over validation-clean calibrated nodes (transported prior vs smooth field vs messages). |
| `POST /graph/autotune` | LOO-tune the smooth-field reach on the production solve. |
| `GET /graph/benchmark/artifact` | Newest offline benchmark-pack HTML artifact (404 until a pack ran). |

## 9. Quality, export, publish

| Route | Semantics |
|---|---|
| `GET /quality` | Universe quality report for the given fit mode: per-node data age, RMS/max error, quote counts, convergence, certificate status, butterfly/calendar diagnostics, prior/filter/graph provenance, LV health, stale/degraded status, publish-ready boolean + reasons. Reads committed artifacts only — never fits. |
| `GET /export/surfaces` | Download calibrated surfaces (fitted nodes only) + manifest; all inputs embedded so an export is self-contained. |
| `GET /export/report` | Self-contained HTML quality/publish report (served inline). |
| `GET /publish/history` | The manifest chain, newest first (content-addressed, parent lineage). |
| `POST /publish/{manifest_id}/recall` | Recall a published surface — a lifecycle transition, not a delete. |

Publishing is hard-blocked (HTTP 409, typed `PublishBlockedError`) on: an
uncertified displayed slice, red-stale data age, unresolved intrinsic or
calendar inconsistency, or an unsupported required dark component.

## 10. Infrastructure

`GET /docs`, `GET /redoc`, `GET /openapi.json` — generated API docs. The
frontend is served by Vite in dev and can run against a mock fallback with an
unmistakable MOCK badge when the backend is down.

---

## 11. Frontend inventory

React + TypeScript (Vite). Eight workspaces behind a persistent top bar;
state-based routing; each workspace wrapped in its own error boundary (keyed
by tab) so a render crash in one view never takes down the shell. Workspace
session state survives tab switches.

**Top bar:** data source selector with health lights, as-of selector, data-age
pill (green/amber/red), Fetch ▾ (one verb: Snapshot — quotes + spot; the split
Fetch Spots / Fetch Options Quotes survive only as "(legacy)" command-palette
entries over `POST /fetch/spots` / `POST /fetch/options`), Calibrate/Cancel
with SSE-driven progress, stale count, prior actions, tab navigation.

| Workspace | Content |
|---|---|
| **Parametric** | Ticker/expiry selectors; model + settings summary; quote bands with include/exclude/amend/reset + undo/redo; prior, current fit, pre-transport anchor, filtered overlay, graph reconstruction overlays; var-swap editor; spot-move scenario controls + regime; stale/no-fit/degraded/certificate states. Sub-tabs: Smile, stacked Densities, log-quantile density, Term structure, 3D surface, stacked total variance, Table. Strike coordinates: log-moneyness, strike, %ATM, delta, normalized. Wheel zoom, drag pan, reset, range brush. |
| **Local Vol** | Joint surface status + per-expiry diagnostics (vertex coverage, vega-floor incidence, PDE steps, timings); smile/reprice view, density, term, local-vol heatmap, 3D IV surface, table. No local knobs — grid/solver settings live in Options; clean disabled state when LV is off. |
| **Forwards** | Active/parity/theoretical/manual forwards by maturity; discount/carry provenance + confidence (incl. joint-borrow columns with a noise floor); dividend ex-date markers + schedule editor; forward curve + table; warnings for unidentified carry or material American correction. |
| **Options** | Every meaningful coefficient with label, plain-language purpose, unit, range, default, activation condition, and invalidation note; grouped (model, objectives, arbitrage/calendar, var-swaps/events, prior/filter, local variance, graph, dynamics, workflow); Apply / Save as default / Reset. |
| **Graph** | Three-pane shell — left: relationships and policy (edge editor, block rules, message-relation editor with per-row semantics, policy card, dynamics-policy card); center: node/edge canvas (network chart, expiry-ladder matrix, lit/dark selection, σ-edge lens, wave overlay); right: selected node/edge inspector (handles, uncertainty, innovation, incoming confidence, provenance, attribution card, decomposition card with boundary chip and χ badge). Bottom drawer: Preview, Diagnostics, Validation (side-by-side LOO + benchmark artifact link + plan WHY-badges), Observation Plan. Draft/active lifecycle with activate/revert/diff; live preflight with blockers/warnings; unified what-if pulses (non-persisting). Desk language first ("A informs B", "relationship uncertainty"); raw precision behind an advanced toggle. |
| **Quality** | Headline ready/stale/arbitrage/RMS tiles; per-ticker rollup incl. LV health; filterable per-node exception table; publish/export controls; manifest/report history. Never fits on view load. |
| **Universe** | Provider symbol search; per-ticker expiry selection with expiry-type labels; lit/dark matrix; named universe save/load/delete; selected-node count and expected calibration load. |
| **View** | Dark/light/high-contrast/warm schemes; contrast/brightness; expiry-label and time-axis preferences; client-side preview with explicit save/reset. |

**Testing:** component tests (vitest) for chart/editor components; a headless
browser smoke run over a production build that walks all workspaces and
screenshots them.
