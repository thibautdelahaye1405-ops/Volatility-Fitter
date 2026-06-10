# Vol-Fitter — Development Roadmap

Implied-volatility fitter (à la VolaDynamics) with a differentiating feature:
**extrapolation of sparse smile observations to the full universe of smiles**
(across expiries and assets) by propagating signal through a graph whose nodes
are smiles `(underlying, T)`, using the OT-regularized Bayesian solver of
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`.

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

- [ ] Git init, `pyproject.toml` (uv or poetry), ruff + mypy, pytest; frontend scaffold (Vite + TS + Tailwind).
- [ ] CI: lint, type-check, unit tests, golden-number tests.
- [ ] Shared conventions doc: file-size policy (≤400 lines), docstring style, commenting policy.
- [ ] Skeleton FastAPI app + React shell with routing (Smile / Surface / Graph tabs).

**Exit criteria:** `make dev` runs backend + frontend hot-reload; CI green.

## Phase 1 — Quant core: pricing & LQD slice engine (weeks 2–4)

The LQD note (`Docs/lqd_model_note.tex`) is the centerpiece; implement it first
since other models are standard.

- [ ] `core/black.py`: normalized Black formula B(k,w), vega, implied-vol inversion (Jäckel-style rational guess + Householder), total-variance utilities.
- [ ] `models/lqd/basis.py`: Legendre basis P₂..P_N (recursion), logit grid, endpoint scales A_L/A_R, Lee slopes β_L/β_R (eqs. AL/AR, betaL/betaR).
- [ ] `models/lqd/quadrature.py`: logit-coordinate quadrature for Q̄(z), martingale shift μ, asset-share integral A(z), analytic tail corrections (eqs. right/left_tail_corr); single grid reused for all strikes; Numba-jitted.
- [ ] `models/lqd/pricing.py`: C(k) via eq. call_logit, monotone interpolation; density & quantile extraction for charts.
- [ ] `models/lqd/atm.py`: exact ATM level/skew/curvature functionals (σ₀, s₀, κ₀), Jacobian J, ATM-orthogonal coordinates (linear + implicit-function exact version).
- [ ] `models/lqd/calibrate.py`: vega-weighted least squares (eq. calib_objective), hard constraint A_R < 1−ε, n^{2r} regularization, 3 initializers (logistic, wing-aware, quantile-projection).
- [ ] Golden tests: reproduce the note's two benchmarks — SVI-JW SPX-like fit (max err ≈1.2 vol bp, coefficients of eq. svi_lqd_coeffs) and N=12 double-hat event fit.

**Exit criteria:** both paper benchmarks reproduced to stated accuracy; slice fit < 50 ms.

## Phase 2 — Quant core: remaining models & no-arbitrage (weeks 4–6)

- [ ] `models/svi_jw/`: raw-SVI + JW parametrization, conversion (Appendix A formulas), Gatheral–Jacquier butterfly conditions, calibration.
- [ ] `models/sigmoid/`: sigmoid smile parametrization + fit.
- [ ] `models/localvol/`: full local-vol grid on strike×T — continuous and piecewise-affine variants; Dupire consistency check; fast PDE/analytic pricer for round-trip validation.
- [ ] Common `SmileModel` interface: `price(k)`, `iv(k)`, `density()`, `quantile()`, `params`, `diagnostics()` so the viewer & graph layer are model-agnostic.
- [ ] `calib/arbitrage.py`: butterfly check (model-free, for non-LQD models), calendar check via integrated upper-quantile constraint G_i(α) ≤ G_j(α) (eq. lqd_calendar) with slack diagnostics; **toggleable** per CLAUDE.md.
- [ ] `calib/event_time.py`: event-dilated time — business-time clock with event variance bumps; toggleable; feeds term-structure charts.
- [ ] Surface construction: sequential nearest-to-farthest fitting with calendar constraints on a logit-uniform α-grid (note §10.2).

**Exit criteria:** all 4 model families fit a test surface; arbitrage diagnostics (A_L, A_R, Lee slopes, μ, calendar residuals) reported for every fit.

## Phase 3 — Data layer (weeks 5–7, parallel with Phase 2)

- [ ] Provider interface `OptionChainProvider`: `yahoo.py` (scraper w/ rate limiting & caching), `bloomberg.py` (blpapi, stub if no terminal), `massive.py`.
- [ ] Forward & dividend implication: put-call parity regression per expiry → implied forward + borrow; explicit dividend curve input as fallback (decision recorded: start with parity-implied forwards, add discrete-dividend model later).
- [ ] Quote prep: mid/bid/ask, haircut bid-ask mode, outlier filters, vega/spread-based weights ω_i.
- [ ] Storage: SQLite schema (instruments, snapshots, fits, priors, graph configs) + Parquet/DuckDB for chain history; migration tooling.
- [ ] Universe selection service: enumerate available tickers/expiries from providers; user picks subset → persisted universe.

**Exit criteria:** one command snapshots a 20-ticker universe from Yahoo into storage; forwards implied; quotes ready for calibration.

## Phase 4 — Graph extrapolation engine (weeks 7–10)

Direct implementation of `Docs/ot_bayesian_graph_extrapolation_expanded.tex`.
Nodes = smiles `(underlying, T)`; node scalar field = smile parameters in
**ATM-orthogonal coordinates** (level w₀, skew s₀, curvature κ₀, shape modes ξ)
— this is what makes the LQD ATM orthogonalization load-bearing: each
coordinate is propagated as its own graph signal `z = x¹ − x⁰`.

- [ ] `graph/build.py`: node registry, directed weights W (user input + defaults from sector/maturity proximity), row-normalized K, stationary π, reversibilized conductances c_ij, incidence B.
- [ ] `graph/operators.py`: L_rev = BCBᵀ, directed residual L_dir = (I−K)ᵀΠ(I−K), mobility Laplacian A_ρ = BMBᵀ (log-mean θ).
- [ ] `graph/prior.py`: increment precision Q_Δ = D_κ + ηL_dir + λ(A_ρ+νI)⁻¹ (matrix-free matvec, sparse solve); predictive K⁻ = P₀⁻¹ + Q_Δ⁻¹.
- [ ] `graph/posterior.py`: covariance-form update exploiting n≪N (n solves Q_Δu_a = Hᵀe_a, small S_y solve); posterior means μ⁺ and **marginal** precisions 1/K⁺_ii (selected-inverse via sparse Cholesky, Hutchinson fallback).
- [ ] `graph/hyper.py`: empirical-Bayes marginal likelihood ℓ(θ) + gradient, held-out standardized-residual calibration ζ_i.
- [ ] Round-trip: posterior coordinates → exact ATM Newton solve → full arbitrage-free LQD smiles for **every** node, with per-node confidence bands from marginal precision.
- [ ] Validation harness: hide x% of liquid smiles, extrapolate, score vs truth; calibration plots.

**Exit criteria:** 6-node running example of the note reproduced exactly (μ⁺, π⁺ tables); 1k-node synthetic universe updates < 1 s; held-out validation report.

## Phase 5 — Backend API (weeks 9–11)

- [ ] Routers: `/universe`, `/quotes`, `/fit` (slice & surface, async with WebSocket progress), `/prior` (save/load), `/graph` (build, weights, solve), `/scenario` (vol-spot dynamics).
- [ ] Fit session model: prior fit + current fit + edited quote set per smile, undo/redo.
- [ ] Var-swap level computation per slice (from LQD density — exact integral).
- [ ] Performance: process-pool for parallel slice fits across expiries/assets; cache quadrature grids.

**Exit criteria:** full fit-edit-refit loop driveable from HTTP/WS; OpenAPI schema published for frontend codegen.

## Phase 6 — Smile Viewer frontend (weeks 10–14)

Professional, commercial, sleek (dark theme default, dense layouts, keyboard-first).

- [ ] Smile chart: prior vs current fit vs bid/ask quote bands; normalized (k = log K/F or delta) and fixed-strike axes; strike-range slider, wheel zoom, crosshair readout.
- [ ] Quote interaction: click to select/erase/amend calibration points; fit-to-bid-ask / mid / haircut toggle; instant refit on edit (< 100 ms perceived).
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

- [ ] `dynamics/ssr.py`: SSR (skew-stickiness ratio) on ATM vol; configurable SSR parameter.
- [ ] Sticky-strike and sticky-local-vol-grid scenario modes; spot-shift scenario engine producing shifted surfaces for all three regimes.
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
