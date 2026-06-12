# Vol-Fitter — Development Roadmap

Implied-volatility fitter (à la VolaDynamics) with a differentiating feature:
**extrapolation of sparse smile observations to the full universe of smiles**
(across expiries and assets) by propagating signal through a graph whose nodes
are smiles `(underlying, T)`, using the OT-regularized Bayesian solver of
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`.

---

## STATUS — updated 2026-06-12 PM (resume here)

**Done & verified (152 pytest tests green + 1 live-optional, `git log --oneline` tells the story):**
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
  Brent inversion; continuous-yield dividends only until the dividends model
  lands) and the **stale parity-pair filter** in `data/forwards.py`
  (iterative 4-robust-sigma MAD trim floored at 1bp of spot, `n_outliers`
  reported). NOT yet wired into quote prep / providers — that wiring belongs
  with the dividends + forward-mode work below.

**Next up (in order — items marked [REQ] were requested by the user on
2026-06-12; details in the phase checklists below):**
1. [REQ] Real-data realism block (Phase 3) remainder: dividends model
   selection (continuous / discrete absolute / discrete proportional / mix),
   forward mode choice (theoretical carry / parity-implied / manual
   override), and wiring de-Americanization (`core/american.py`, done) into
   single-name quote prep (needs a per-instrument exercise-style flag plus
   rate/dividend inputs through `api/quotes.py`).
2. [REQ] Chart & UX additions (Phase 6): 3D vol-surface chart; strike-axis
   modes (delta / fixed strike / %ATM / normalized / log-normalized); table
   export (prices, IV) as save/download; expiries bulk selection by type
   (monthly, quarterly, weekly, LEAPS) + universe-selection UI.
3. [REQ] Time-series scaffold (Phase 3): persist every fit keyed by snapshot
   timestamp + history query API (charting UI later).
4. CI + perf benchmarks (Phase 0 leftover + Phase 9); process-pool for
   parallel slice fits deferred here (single fit ~30 ms, instant-refit
   target already met).
5. Graph Viewer remainder: edge-weight editor, full solver panel (kappa,
   lambda, nu, auto-tune), lasso selection.
6. Model choice in the hyperparameter panel beyond LQD (SVI-JW own
   calibration, sigmoid, direct localvol-affine fit through the API).

**Environment notes:**
- venv at repo root `.venv`; run tests: `cd backend; ..\.venv\Scripts\python -m pytest tests -q`
  (125 green as of 2026-06-12; opt-in live Yahoo test via `$env:VOLFIT_LIVE="1"`).
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
- [ ] CI: lint, type-check, unit tests, golden-number tests.
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

- [x] `models/svi_jw/`: raw-SVI + JW conversion (Appendix A). (SVI own calibration & Gatheral–Jacquier butterfly conditions still TODO)
- [x] `models/sigmoid/`: 4-param sigmoid curve + LM fit (round-trip exact).
- [x] `models/localvol/`: bilinear (continuous piecewise-affine) and pw-const-in-t grid variants; CN Dupire forward PDE pricer (Rannacher startup, adaptive span); Dupire extraction with butterfly-gated denominator; round-trip + consistency tests. API exposure TODO.
- [x] [REQ 2026-06-12] Local-vol calibration per `Docs/piecewise_affine_local_variance_calibration.tex`: `models/localvol/affine.py` + `affine_calib.py`, golden tests vs every table of the note (Delaunay triangulation is the note's convention; lambda=50 roughness reproduces the calibrated nodal table).
- [x] [REQ 2026-06-12] American-options handling, de-Americanization first: `core/american.py` CRR binomial + `deamericanize()` (European-equivalent IV; continuous-yield divs). **Provider/quote-prep wiring still TODO** (exercise-style flag, r/q inputs).
- [x] Common `SmileModel` protocol (`models/base.py`): `implied_w(k)`, `implied_vol(k, t)` — satisfied by LQD/SVI/sigmoid. (richer `density()`/`diagnostics()` surface TBD)
- [x] Calendar check via G_i(α) ≤ G_j(α): implemented as elementwise asset-share comparison on the shared logit grid (`calib/calendar.py`), soft-slack penalty in `calibrate_slice`, **toggleable**. (model-free butterfly check for non-LQD models TODO)
- [x] `calib/event_time.py`: dilated clock + variance-lumping term-structure interpolation; toggleable.
- [x] Surface construction: sequential nearest-to-farthest with warm starts and violation diagnostics (`calib/surface.py`).

**Exit criteria:** all 4 model families fit a test surface; arbitrage diagnostics (A_L, A_R, Lee slopes, μ, calendar residuals) reported for every fit.

## Phase 3 — Data layer (weeks 5–7, parallel with Phase 2)

- [x] Provider interface `OptionChainProvider` + deterministic `SyntheticProvider` (offline dev/tests) + `yahoo.py` (yfinance, lazy import, injectable factory, sqrt-time expiry thinning). `bloomberg.py` / `massive.py` still TODO.
- [x] Implied forwards by put-call parity regression (`data/forwards.py`, recovers F to <0.1% on synthetic).
- [ ] [REQ 2026-06-12] Dividends model selection: continuous yield, discrete absolute, discrete proportional, or mixed (absolute short-dated switching to proportional long-dated — standard desk practice); feeds the theoretical forward and the event/ex-date handling.
- [ ] [REQ 2026-06-12] Forward fitting mode per expiry: **theoretical** (spot + carry from rate/dividend model), **parity-implied** (current default), or **manually adjusted** (user override in the UI, persisted with the fit session); diagnostics showing the three side by side.
- [ ] [REQ 2026-06-12] Fit time-series scaffold: persist every calibration (params, ATM handles, diagnostics) keyed by snapshot timestamp — VolStore `fits` table already has the shape — plus history query API (`GET /history/{ticker}/{tenor}`); charting UI deferred.
- [x] Quote prep: mid/bid/ask + haircut modes, spread-based weights, 4-sd wing filter (`volfit/api/quotes.py`). (per-quote liquidity haircuts and richer outlier rules TODO)
- [x] Storage: SQLite `VolStore` (instruments, snapshots, quotes, fits, priors, universes; WAL, versioned schema). Parquet/DuckDB history TODO.
- [x] Universe dataclass + persistence; provider-driven enumeration UI flow TODO.
- [ ] [REQ 2026-06-12] Expiries bulk selection by type: classify listed expiries (daily, weekly, monthly = 3rd Friday, quarterly, LEAPS) in the provider/universe layer and let the user select by class (e.g. "monthlies ≤ 1y + quarterlies") instead of one by one; UI lives in the universe-selection flow.

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
- [ ] Hyperparameter panel: model choice, N, penalty coefficients, arbitrage/event toggles.
- [ ] [REQ 2026-06-12] Strike-axis modes on the smile chart: log-moneyness (current), **fixed strike** K, **%ATM** (K/F·100), **delta** (Black delta of the fitted vol at K), **normalized** (K−F)/(σ_ATM·F·√T), **log-normalized** ln(K/F)/(σ_ATM·√T) — extend `axisMode`; quotes, brush and crosshair must follow the active axis.
- [ ] [REQ 2026-06-12] 3D vol-surface chart: σ(k, T) surface over the fitted expiry ladder (rotatable; start with SVG/canvas mesh — same zero-dep philosophy — WebGL only if needed).
- [ ] [REQ 2026-06-12] Table export: quotes/prices/IV and fit tables viewable as a grid and exportable — copy, save, and CSV download (API endpoint streaming CSV + frontend download button).

**Exit criteria:** trader workflow demo — load universe, inspect smile, drag ATM skew, erase a bad quote, refit, save prior — all fluid.

## Phase 7 — Graph Viewer frontend (weeks 13–16)

- [x] Graph visualization: structured SVG lattice (ticker columns × expiry rows, calendar + cross-ticker edges) — chosen over force-directed for legibility at current scale; WebGL/pan-zoom deferred to large-universe work.
- [x] Node states: **lit** (observed) vs **dark** (extrapolated), toggled by click, with per-node dAtmVol inputs. (lasso + ticker/expiry filters TODO)
- [ ] Edge-weight input: matrix editor + bulk rules (same-ticker adjacent-expiry weight, sector weight, custom CSV upload). (weights currently fixed server-side: 10 calendar / 2 cross)
- [ ] Solver panel: κ, η, λ, ν sliders with live re-solve; empirical-Bayes "auto-tune" button; convergence/calibration readout. (η reach slider done; rest TODO)
- [x] Result overlay: posterior shift as diverging node color, marginal sd as halo size/fade, hover tooltip with base→post + credible band; double-click → jump to that smile in the Smile Viewer.

**Exit criteria:** end-to-end demo — observe 5 smiles, light them, solve, watch 200 dark smiles update with uncertainty, drill into any one.

## Phase 8 — Vol-spot dynamics & scenarios (weeks 15–17)

- [x] `dynamics/ssr.py`: SSR on ATM vol, configurable; sticky-moneyness / sticky-strike / sticky-local-vol (SSR=2 short-maturity rule) regimes with exact shape-preservation invariant. (true sticky-local-vol-grid mode awaits the localvol model)
- [x] Frontend: regime selector + spot-shift slider with live re-render of shifted smile (ScenarioPanel + dotted overlay).

**Exit criteria:** spot ±5% scenario renders all three regimes consistently for any fitted surface.

## Phase 9 — Hardening, performance & polish (weeks 17–20)

- [ ] Perf pass: profile slice fit, surface fit, graph solve; Numba/JAX tuning; target budget table enforced in CI benchmarks.
- [ ] Test depth: arbitrage invariants as property tests (every LQD iterate butterfly-free; calendar residuals ≤ τ), fuzzed quote sets, provider failure injection.
- [ ] UX polish: loading/skeleton states, error surfaces, layout persistence, theming, onboarding tour.
- [ ] Packaging: Docker compose (backend + frontend), one-line local install; user guide + API docs.

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
