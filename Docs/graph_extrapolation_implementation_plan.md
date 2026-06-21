# Graph Smile-Extrapolation — Production Implementation Plan

*Written 2026-06-21 for a fresh session. Companion to
`Docs/graph_extrapolation_status_note.md` (gap analysis) and
`Docs/graph_extrapolation_status_note_addon.md` (the six design decisions).
Read all three before starting.

**STATUS (updated 2026-06-21): Phases 1–9 are IMPLEMENTED and merged to `main`**
(commit `3cc909f` + the LV-projection follow-up); Phase 10 (sparse perf) is
deferred. See ROADMAP.md "STATUS" for the as-built summary. This document is kept
as the original plan of record; the wording below ("nothing implemented yet", "this
is a plan only") describes its state at authoring time, not the current code.*

---

## 0. Orientation (read first)

**What exists and is solid — DO NOT rewrite.** The OT-Bayesian graph *math* in
`backend/volfit/graph/` implements `Docs/ot_bayesian_graph_extrapolation_expanded.tex`
faithfully and is golden-tested (`tests/test_graph_example.py` reproduces the note's
6-node example):

- `build.py` — row-normalized kernel `K`, stationary `π`, reversibilized conductances.
- `operators.py` — `L_rev`, `L_dir = (I−K)ᵀΠ(I−K)`, mobility `A_ρ`.
- `prior.py` — `Q_Δ = D_κ + η L_dir + λ(A_ρ + νI)⁻¹` (`build_increment_prior`).
- `posterior.py` — Gaussian conditioning, covariance form, marginal precision `1/K⁺ᵢᵢ`.
- `hyper.py` — marginal likelihood + standardized residuals.
- `smile_universe.py` — bridge: node = `(ticker, expiry-ISO)`, carrier = 3 ATM handles
  `(atm_vol, skew, curvature)`, per-coordinate independent propagation, LQD
  reconstruction via `models/lqd/ortho`.

**What is wrong for production** (the manual ATM-shift sandbox): baseline `x⁰` is
*today's mid fit* not a *transported prior*; observations are *hand-typed shifts* not
*calibration-minus-prior innovations*; the universe is *all provider tickers × expiries*
not the *selected lit+dark set*; reconstruction/quote-comparison is never surfaced;
precision is hard-coded; there is no per-edge scaling (beta).

**The target workflow (the spine of this whole plan):**

```
transported prior  →  lit calibration innovation  →  graph posterior increment
                   →  dark reconstructed smile     →  quote comparison
```

**Design decisions locked by the add-on (do not re-litigate):**
1. Default prior hierarchy: `active_transported` → `nearest_expiry_transported` →
   `today_bootstrap` (weak) → `flat_atm` (diagnostic only).
2. Production graph is built over the **selected lit+dark nodes only**. Full-universe
   stays as a separate diagnostic mode.
3. Scaling = per-edge **beta on the directed increment**, separate from conductance,
   per-handle and per-direction (`β_ij ≠ β_ji`).
4. Carrier stays the **3 ATM handles** for v1.
5. Precision is **derived** from fit quality / quote density / bid-ask / freshness /
   prior provenance (constants become floors/caps only).
6. Validation = **both** live overlay and batch backtest.

**Key principle (Amendment A):** keep the existing manual `/graph/solve` endpoint as a
*sandbox*. Build the production path as **new, separate** endpoints + service module so
the two semantics never get tangled.

**Conventions (from CLAUDE.md — non-negotiable):** files ≤ 400 lines; module
docstrings cite the relevant equation/section; golden tests against the Docs notes;
sub-agents write code, the lead runs `cd backend ; ..\.venv\Scripts\python -m pytest
tests -q` and verifies; commit after each green batch; ruff + strict-TS build green.

### Code anchors (verified 2026-06-21)
- Graph engine: `backend/volfit/graph/{build,operators,prior,posterior,hyper,smile_universe}.py`
- Service: `backend/volfit/api/graph_service.py` (`ensure_universe`, `_lattice_weights`,
  `solve_graph`, `autotune_graph`; consts `SAME_TICKER_WEIGHT=10`, `CROSS_TICKER_WEIGHT=2`,
  `GRAPH_PRIOR_HYPER`, `GRAPH_PRECISION`).
- Router: `backend/volfit/api/routers/graph.py` (`GET /graph/nodes`, `POST /graph/solve`,
  `POST /graph/autotune`).
- Schemas: `backend/volfit/api/schemas.py:558-658` (`Graph*`).
- Prior transport: `backend/volfit/api/prior_transport.py` (`prior_node`,
  `transported_prior_slice`, `transported_prior_points`).
- Service hooks: `service.fit_or_get` (`service.py:575`), `fit_and_commit_slice` (1017),
  `varswap_target` (237), `prior_anchor_targets` (259), `weighted_rms_error` (651),
  `model_info` (728), `displayed_base` (547).
- State: `state.active_prior` (`state.py:1155`), `active_prior_source` (1160),
  `active_prior_version` (1150), `node_lit` (1166), `set_node_lit` (1171),
  `_dark_nodes` (282), `forwards` (566), `set_calibrated_ptr` (811).
- Universe: `state_universe.UniverseMixin.selected_expiries` (`state_universe.py:206`).
- LQD: `models/lqd/atm.atm_handles` → `ATMHandles(sigma0, skew, curvature)`;
  `models/lqd/ortho.{build_atm_coordinates, ATMCoordinates.retarget}`.
- LV transport target: `backend/volfit/api/affine_transport.py`.
- Frontend: `frontend/src/views/GraphViewer.tsx`, `components/GraphChart.tsx`,
  `components/SolverPanel.tsx`, `state/useGraph.ts`.

---

## 1. Target architecture

New backend module **`backend/volfit/api/graph_extrapolation.py`** (the production
service; keep `graph_service.py` as the sandbox). It may grow past 400 lines — if so,
split into `graph_extrapolation.py` (orchestration) + `graph_nodes.py` (prior/precision
resolution) + `graph_reconstruct.py` (smile reconstruction + quote metrics).

New engine additions under `backend/volfit/graph/`:
- `beta.py` — directed residual with per-edge per-handle beta (Phase 6).
- extend `smile_universe.py` only if needed; prefer a new
  `graph/extrapolation_universe.py` to keep the sandbox path untouched.

New routes (router `routers/graph.py`, or a new `routers/graph_extra.py`):
- `POST /graph/extrapolate` — production solve (prior-anchored, calibration-fed).
- `GET  /graph/extrapolate/nodes/{ticker}/{expiry}` — full reconstructed smile + prior +
  lit-calibration curve + quote metrics for one node (lazy, Amendment E).
- `POST /graph/backtest` — leave-one-node-out / blocked-holdout batch (Phase 8).

Frontend: a new **"Extrapolate"** mode in the Graph workspace (toggle vs. the existing
"Sandbox"), reusing `GraphChart` but driven by the new hook `useGraphExtrapolation.ts`.

---

## 2. Phased plan (sequencing per the add-on's revised order)

Each phase is independently shippable and ends green. Phases 1–6 are the production
spine; 7–10 are model-agnostic + perf follow-ups.

---

### Phase 1 — Selected-universe construction (Amendment C)

**Goal:** the production graph is built over the user-selected lit+dark nodes only.

**Files:** new `graph_extrapolation.py`; reads `state.selected_expiries(ticker)` +
`state.node_lit` + active ticker list.

**Work:**
- `build_selected_universe(state) -> SelectedUniverse`: iterate active tickers ×
  `selected_expiries`; classify each as lit/dark via `state.node_lit`. Build the node
  list = lit ∪ dark (all selected). Do **not** call `provider.list_tickers()` blindly
  for fits — only build nodes for selected expiries.
- Edge generation: reuse `_lattice_weights` logic (calendar chains + cross-ticker
  same-expiry) but **restricted to the selected node set**. Factor the lattice builder
  into a shared helper so both sandbox and production use it.
- A new `SelectedUniverse` dataclass carrying nodes, lit/dark flags, the `SmileGraph`,
  and (Phase 2/3) per-node prior/precision — keep it separate from sandbox
  `SmileUniverse` to avoid coupling.

**Schema:** none yet (internal).

**Tests** (`tests/test_graph_extrapolation.py`): selected set excludes unselected
provider nodes; lit/dark split is respected; dark-only selection still builds nodes;
empty selection → empty graph (no crash).

**Acceptance:** building a graph over a 2-ticker × 3-expiry selection yields exactly 6
nodes regardless of how many expiries the provider exposes.

---

### Phase 2 — Transported-prior baselines with provenance (Amendments B + the Q1 hierarchy)

**Goal:** every node's baseline `x⁰` = transported-prior ATM handles, with explicit
provenance + precision metadata.

**Files:** `graph_extrapolation.py` (or split `graph_nodes.py`); reuses
`prior_transport.transported_prior_slice`, `state.active_prior`,
`state.active_prior_source`, `models/lqd/atm.atm_handles`.

**Work — resolve each node's prior by the locked hierarchy:**
1. `active_transported` — `state.active_prior(ticker)` node for this ISO, transported to
   the current forward via `transported_prior_slice(node, forward, regime)`; read handles
   off the transported LQD slice.
2. `nearest_expiry_transported` — if no node for this ISO, take the nearest-ISO prior
   node on the same ticker, transport it, **reduce precision**, flag
   `prior_source="nearest_expiry"`.
3. `today_bootstrap` — else use today's mid fit handles (`fit_or_get(...,"mid")`), **low
   precision**, flag `today_bootstrap`; **mark `valid_for_validation=False`** (prevents
   the circular "today vs today" backtest, Amendment B).
4. `flat_atm` — only if explicitly requested as a diagnostic.

Define a `NodePrior` dataclass: `handles: np.ndarray(3)`, `source: str`,
`as_of`, `prior_forward`, `transport_distance` (`log(F_now/F_prior)`),
`precision: np.ndarray(3)`, `valid_for_validation: bool`.

**Schema:** extend node-info response with `priorSource`, `priorAsOf`,
`transportDistance`, `priorAtmVol/Skew/Curv`, `validForValidation`.

**Tests:** transported-prior identity when forward unchanged (`h=0` ⇒ handles ==
prior handles); nonzero shift when forward moves; nearest-expiry fallback fires + flags;
bootstrap flagged `valid_for_validation=False`; provenance string is correct per branch.

**Acceptance:** a node with a saved prior at a different spot shows a transported
baseline ≠ raw prior; a node with no prior anywhere shows `today_bootstrap`.

---

### Phase 3 — Lit-calibration innovation feed (Amendment A, the production solve)

**Goal:** the propagated observation is `d = calibrated_handles − transported_prior_handles`
on lit nodes; the posterior increment is added back onto the prior.

**Files:** `graph_extrapolation.py`; new route `POST /graph/extrapolate`.

**Work:**
- For each **lit** node: ensure a current-spot calibration exists (`fit_or_get` /
  `fit_and_commit_slice` at `state.last_fit_mode`), read its ATM handles `y`. Innovation
  `d = y − x⁰_transported`. This `d` (not a manual shift) becomes the `observations`
  argument to `posterior_update` via the existing `propagate_handles`.
- **Dark nodes are never observations** — they only receive propagation (Amendment H
  test). Their reconstructed handles = `x⁰_transported + posterior_increment`.
- Reuse `propagate_handles` unchanged (it already loops the 3 coordinates). The novelty
  is *what* is fed as baseline/observations/precision — all assembled here.
- Response: per node `priorAtmVol → postAtmVol`, `shiftBp`, `sd`, band, `lit/dark`,
  `priorSource`, and `innovationBp` for lit nodes.

**Schema** (`schemas.py`, new block — keep `Graph*` sandbox schemas intact):
`GraphExtrapolateRequest(GraphSolverParams)` (no manual observations — derived
server-side), `GraphExtrapolateNode`, `GraphExtrapolateResponse`.

**Tests:** lit innovation equals `calibrated − transported_prior` (exact); zero
innovation when calibration == transported prior (dark nodes then stay at prior);
posterior increment added back reproduces lit handles at lit nodes within solver
tolerance; dark node with quotes is NOT used as an observation.

**Acceptance:** lighting one node, recalibrating it after a real market move, and
solving propagates a sensible signed ATM shift to its calendar/cross neighbours with
credible bands — no manual typing.

---

### Phase 4 — Derived precision plumbing (Amendment F, before any autotune)

**Goal:** observation/baseline precision come from data quality, not constants.

**Files:** new `backend/volfit/graph/precision.py` (pure, testable);
wired in `graph_extrapolation.py`.

**Three precision concepts kept separate (Amendment, Q5):**
- **Observation precision** (lit nodes): start from `1/rms²` (reuse
  `service.weighted_rms_error`), scale by near-ATM quote-density factor and
  bid-ask-width / haircut-mode factor and freshness (as-of mismatch). Per-handle:
  atm_vol gets the most precision, curvature the least.
- **Baseline/prior precision** (all nodes): from `prior_source` (active > nearest >
  bootstrap), prior age, and `transport_distance` (further transport ⇒ less precise).
- **Edge precision/conductance**: keep the conductance as-is for v1 (Phase 6 adds beta;
  a learned edge confidence is a later follow-up).

Implement a conservative, documented formula with explicit **floors and caps** per
handle (so a single great fit can't dominate; mirror the `MAX_INV_VEGA_RATIO` pattern in
`calib/prior.py`). Surface every factor in diagnostics (Amendment F: "plumb the source
and expose it before tuning").

**Schema:** add `precisionAtmVol/Skew/Curv` + the factor breakdown to node diagnostics.

**Tests:** lower fit quality ⇒ lower observation precision; wider bid-ask ⇒ lower; staler
as-of ⇒ lower; bootstrap prior ⇒ lower baseline precision than active; floors/caps hold.

**Acceptance:** a dense fresh SPY chain enters with materially higher observation
precision than a sparse stale one, visible in the node diagnostics.

---

### Phase 5 — Reconstructed smiles + quote comparison (Amendment E, live overlay)

**Goal:** return full smiles (not just ATM scalars) and compare dark nodes to quotes.

**Files:** new `graph_reconstruct.py`; route `GET /graph/extrapolate/nodes/{ticker}/{expiry}`.

**Work:**
- Reconstruct each requested node's smile: `x⁰_transported + posterior_increment` →
  target handles → `ortho.retarget` (LQD v1) → curve points on the shared display
  k-grid (reuse `service.K_DISPLAY_LO/HI`).
- Return: posterior smile curve + posterior credible band (from per-handle `sd`), the
  prior smile curve, the lit-calibration curve (lit nodes), and **quote-comparison
  metrics** for nodes that have quotes: residuals by strike, weighted RMS (reuse
  `calib/rms.py`), inside-spread hit rate, ATM-handle residuals, and standardized
  residuals using posterior uncertainty (eq. standardized-residual-final in the note;
  `graph/hyper.standardized_residuals`).
- **Payload discipline (Amendment E):** the bulk `/graph/extrapolate` returns ATM
  summaries only; full curves are fetched **per node on demand** via the GET route.

**Schema:** `GraphNodeSmile` (curve arrays, band, prior curve, lit curve, quote points,
metrics).

**Frontend:** overlay the reconstructed dark smile + band against live quote bands in
the Smile viewer when drilling in from the graph; show RMS / hit-rate / standardized
residual in the aside.

**Tests:** reconstructed lit node ≈ its calibration; dark node reconstruction is arb-free
(density ≥ 0 via Breeden-Litzenberger check, reuse existing density helper);
quote-metric math matches `calib/rms.py`; standardized residuals computed for quoted
dark nodes only.

**Acceptance:** drilling into a dark node shows its extrapolated smile + uncertainty band
overlaid on real quotes, with an RMS-vs-market readout.

---

### Phase 6 — Per-edge beta on the directed increment (Amendment D, Q3)

**Goal:** cross-node scaling separate from conductance, per-handle, per-direction.

**Files:** new `backend/volfit/graph/beta.py`; integrate into the directed-residual term
used by `build_increment_prior`.

**Math (locked):** replace `zᵢ ≈ Σⱼ Kᵢⱼ zⱼ` with `zᵢ ≈ Σⱼ Kᵢⱼ βᵢⱼ zⱼ`, i.e. a
beta-weighted directed residual `L_dir^β = (I − K∘B)ᵀ Π (I − K∘B)` where `B` holds the
per-edge betas for the handle being propagated (one `B` per handle since betas differ by
handle). Keep PSD-ness: `L_dir^β = MᵀΠM` with `M = I − (K∘B)` is PSD by construction
(same proof as eq. Ldir-psd). **Conductance/OT term `A_ρ` is untouched** — beta lives
only in the directed compatibility relation.

**Schema (Amendment D — model the distinction even if UI is simple):** an edge carries
`{conductance/weight, betaAtmVol, betaSkew, betaCurv}` with directional entries
(`beta_ij` independent of `beta_ji`). v1 UI may expose a single scalar beta broadcast to
all handles + calendar-default-1 / cross-ticker-explicit, but the data model must keep
weight (trust) and beta (amplitude) **separate fields** from day one to avoid a later
migration.

**Tests:** beta=1 everywhere ⇒ byte-identical to the no-beta engine (golden guard);
raising a cross edge's beta increases the propagated increment magnitude **without**
changing the conductance/precision diagnostics; asymmetric `β_ij ≠ β_ji` produces
asymmetric propagation; PSD/positive-variance invariant holds.

**Acceptance:** a cross-ticker edge with `betaAtmVol=1.5` propagates a 1-vol-pt source as
~1.5 vol pts to the neighbour, conductance diagnostics unchanged.

---

### Phase 7 — Graph inputs UI (CLAUDE.md "Weights input")

**Goal:** user-supplied sparse bi-directed weighted graph with per-edge weight + beta.

**Work:** persisted per-edge overrides (extend the universe persistence /
`settings_persist`); an edge editor in the Graph workspace (add/remove/weight/beta per
direction). Keep the auto-lattice as the default seed. Backend accepts an explicit edge
list; falls back to the lattice when none supplied.

**Tests:** explicit edges override the lattice; persistence round-trips; bi-directed
asymmetric weights accepted.

---

### Phase 8 — Live overlay + batch backtest workflows (Amendment H, Q6)

**Goal:** both validation loops.

**Work:**
- **Live overlay** — already seeded by Phase 5; finish the desk UX (band + metrics in
  the drill-in).
- **Batch backtest** — `POST /graph/backtest`: leave-one-node-out and blocked holdout
  over **quoted** nodes and historical snapshots (reuse the as-of replay machinery).
  Report per-node residuals + standardized residuals + aggregate calibration (are the
  `ζ` ~ N(0,1)?). Exclude `valid_for_validation=False` nodes (bootstrap priors) from the
  clean prior-vs-market score.

**Tests:** LOO backtest reports residuals + standardized residuals; bootstrap nodes
excluded from clean scoring; aggregate calibration summary computed.

**Acceptance:** a backtest over a saved snapshot ladder produces a residual/standardized-
residual report usable to tune `η/λ/κ/β`.

---

### Phase 9 — Model-agnostic native reconstruction beyond LQD (Amendment G)

**Goal:** SVI, Multi-Core SIV, Local-Vol outputs.

**Work:**
- **SVI / Multi-Core SIV:** propagate the same 3 handles, then retarget each model's own
  ATM `(level, skew, curvature)` (SVI-JW exposes these directly; Sig via a small solve).
  Treat the graph output as a **target smile**, fit the model to it.
- **Local-Vol (the hard case, Amendment G):** **do not** transport native LV params. Use
  the graph-extrapolated parametric smile as a **projection/prior target**, then run an
  LV calibration/projection (reuse `affine_transport.py` / the affine fit). Document that
  LV has no cheap 3-param transport.

**Tests:** SVI reconstruction matches propagated handles' ATM level/skew/curv; LV
projection hits the target smile within tolerance; per-model density ≥ 0.

---

### Phase 10 — Sparse performance (deferred; ROADMAP-flagged)

Only when selected-universe sizes demand it. `prior.py:67,72` form dense `N×N` inverses;
autotune is `O(7·n_obs·N³)`. Move to the note's §8 matrix-free path
(`(A_ρ+νI)u=v` sparse solves + Hutchinson diagonal). Guard with a perf rail. Fine to
skip while selected universes are ≲ 10³ nodes.

---

## 3. Cross-cutting requirements

- **Schema hygiene (Amendment D):** never overload `weight` to mean both trust and
  amplitude. Conductance and beta are separate fields forever.
- **Provenance everywhere (Amendment B):** every node result carries `priorSource`,
  `validForValidation`, and the precision factor breakdown — results must be explainable.
- **Sandbox preserved (Amendment A):** `POST /graph/solve` + `GET /graph/nodes` keep
  their current manual-shift semantics and tests. The new path is additive.
- **Precision before autotune (Amendment F):** Phase 4 lands before any serious
  hyperparameter/beta tuning so we don't tune around a constant artifact.
- **Selected-universe before validation (Amendment C):** Phase 1 lands before Phase
  5/8 so validation measures the product the user selected.

## 4. Suggested commit/test cadence

One commit per phase (or per green sub-batch within a large phase). After each:
`cd backend ; ..\.venv\Scripts\python -m pytest tests -q` green, ruff clean, frontend
`npm run build` (strict TS) green. New tests live in `tests/test_graph_extrapolation.py`
(backend logic), `tests/test_graph_precision.py` (Phase 4),
`tests/test_graph_beta.py` (Phase 6), `tests/test_graph_backtest.py` (Phase 8). Keep the
note-equation citations in every new module docstring.

## 5. Definition of done (v1 = Phases 1–6)

A desk user selects a lit+dark universe; lit nodes are calibrated to today's market;
pressing **Extrapolate** transports each node's prior to the current spot, computes the
lit innovations, propagates them through a beta/weighted bi-directed graph with
data-derived precision, and renders each dark node's reconstructed smile + uncertainty
band overlaid on any available market quotes, with an RMS-vs-market readout — all with
explicit prior provenance and no manual ATM typing. The manual sandbox still works
unchanged.
