# Vol-Fitter — Development Roadmap

Implied-volatility fitter (à la VolaDynamics) with a differentiating feature:
**extrapolation of sparse smile observations to the full universe of smiles**
(across expiries and assets) by propagating signal through a graph whose nodes
are smiles `(underlying, T)`, using the OT-regularized Bayesian solver of
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`.

---

## STATUS — updated 2026-06-10 (resume here)

**Done & verified (97 pytest tests green, `git log --oneline` tells the story):**
- Phase 0 scaffold (no CI yet), Phase 1 complete (LQD engine reproduces both
  paper benchmarks; ATM-orthogonal coordinates with exact Newton retargeting).
- Phase 2 complete **except the local-vol grid model**; calendar constraint =
  elementwise asset-share comparison (G(α) ≡ A(z) on the shared logit grid).
- Phase 3 core: synthetic provider + parity forwards + SQLite VolStore
  (Yahoo/Bloomberg/Massive providers and DuckDB/Parquet history not started).
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
- Phase 8 core: SSR scenario engine (`volfit/dynamics/ssr.py`), backend +
  /scenario/ssr endpoint (frontend regime selector still TODO).

**Next up (in order):**
1. Local-vol grid model (last Phase 2 item — gate behind arbitrage diagnostics).
2. Graph Viewer frontend (Phase 7) and Term-Structure view (Phase 6 remainder).
3. Yahoo provider + real snapshots (needs `yfinance` or stdlib scraping).
4. CI + perf benchmarks (Phase 0 leftover + Phase 9); process-pool for
   parallel slice fits deferred here (single fit ~30 ms, instant-refit
   target already met).

**Environment notes:**
- venv at repo root `.venv`; run tests: `cd backend; ..\.venv\Scripts\python -m pytest tests -q`.
- Engine demo: `.venv\Scripts\python backend\demo.py`.
- Frontend: `cd frontend; npm run dev` (mock data; `npm run build` verified).
- PyPI is **intermittently flaky** on this machine (TLS resets toward Fastly;
  npm/Cloudflare fine). pip is configured with retries=15 in pip.ini — installs
  succeed with patience. Suspected AV/router TLS filtering.
- Sub-agents have no shell access here: they write code, the lead runs/verifies.

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
- [ ] `models/localvol/`: full local-vol grid on strike×T — continuous and piecewise-affine variants; Dupire consistency check; fast pricer for round-trip validation. **← biggest remaining Phase-2 item**
- [x] Common `SmileModel` protocol (`models/base.py`): `implied_w(k)`, `implied_vol(k, t)` — satisfied by LQD/SVI/sigmoid. (richer `density()`/`diagnostics()` surface TBD)
- [x] Calendar check via G_i(α) ≤ G_j(α): implemented as elementwise asset-share comparison on the shared logit grid (`calib/calendar.py`), soft-slack penalty in `calibrate_slice`, **toggleable**. (model-free butterfly check for non-LQD models TODO)
- [x] `calib/event_time.py`: dilated clock + variance-lumping term-structure interpolation; toggleable.
- [x] Surface construction: sequential nearest-to-farthest with warm starts and violation diagnostics (`calib/surface.py`).

**Exit criteria:** all 4 model families fit a test surface; arbitrage diagnostics (A_L, A_R, Lee slopes, μ, calendar residuals) reported for every fit.

## Phase 3 — Data layer (weeks 5–7, parallel with Phase 2)

- [x] Provider interface `OptionChainProvider` + deterministic `SyntheticProvider` (offline dev/tests). `yahoo.py` / `bloomberg.py` / `massive.py` still TODO.
- [x] Implied forwards by put-call parity regression (`data/forwards.py`, recovers F to <0.1% on synthetic). Discrete-dividend model later.
- [x] Quote prep: mid/bid/ask + haircut modes, spread-based weights, 4-sd wing filter (`volfit/api/quotes.py`). (per-quote liquidity haircuts and richer outlier rules TODO)
- [x] Storage: SQLite `VolStore` (instruments, snapshots, quotes, fits, priors, universes; WAL, versioned schema). Parquet/DuckDB history TODO.
- [x] Universe dataclass + persistence; provider-driven enumeration UI flow TODO.

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
- [ ] Quantile-function & LQD density chart: prior vs current.
- [ ] Term-structure view: vol and total variance vs T, calendar in real time **and** event-dilated time; event markers editable.
- [ ] Diagnostics panel: A_L/A_R, Lee slopes, ATM handles (w₀, s₀, κ₀ — directly editable, mapped through exact ATM coordinates), var-swap level, calendar residuals.
- [ ] Prior management: save current fit as prior, load, diff.
- [ ] Hyperparameter panel: model choice, N, penalty coefficients, arbitrage/event toggles.

**Exit criteria:** trader workflow demo — load universe, inspect smile, drag ATM skew, erase a bad quote, refit, save prior — all fluid.

## Phase 7 — Graph Viewer frontend (weeks 13–16)

- [ ] Graph visualization: force-directed / clustered layout (underlyings grouped, expiries ordered radially); WebGL for large graphs; pan/zoom.
- [ ] Node states: **lit** (observed at t=1) vs **dark** (to be extrapolated); selection by click, lasso, ticker/expiry filters.
- [ ] Edge-weight input: matrix editor + bulk rules (same-ticker adjacent-expiry weight, sector weight, custom CSV upload).
- [ ] Solver panel: κ, η, λ, ν sliders with live re-solve; empirical-Bayes "auto-tune" button; convergence/calibration readout.
- [ ] Result overlay: posterior mean shifts as node color, marginal precision as halo/size; click node → jump to its smile in Smile Viewer with confidence bands.

**Exit criteria:** end-to-end demo — observe 5 smiles, light them, solve, watch 200 dark smiles update with uncertainty, drill into any one.

## Phase 8 — Vol-spot dynamics & scenarios (weeks 15–17)

- [x] `dynamics/ssr.py`: SSR on ATM vol, configurable; sticky-moneyness / sticky-strike / sticky-local-vol (SSR=2 short-maturity rule) regimes with exact shape-preservation invariant. (true sticky-local-vol-grid mode awaits the localvol model)
- [ ] Frontend: regime selector + spot-shift slider with live re-render of shifted smile.

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
