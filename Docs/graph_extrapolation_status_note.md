# Graph Smile-Extrapolation — Context, Current State, and Gap Analysis

*Standalone technical note — 2026-06-21. Written from the codebase + the math note
`Docs/ot_bayesian_graph_extrapolation_expanded.tex`. No code was changed.*

---

## 1. The objective (what we are trying to build)

The differentiating feature of the vol-fitter is **extrapolation of sparse smile
observations to the full universe of smiles**, across expiries *and* assets, by
propagating signal through a graph whose nodes are smiles `(underlying, T)`.

Stated precisely (the brief that motivated this note):

1. We have **`l + d` selected nodes** in the universe — `l` **lit**, `d` **dark**.
2. Every node carries a **synchronous prior**: the saved prior smile transported to
   the *current* spot/forward level, with a sensible **default in the absence of a
   saved prior**. "Synchronous" = all priors live at today's spot, so they are
   mutually comparable.
3. We are given a **sparse, bi-directed, weighted dependency graph**. An edge means:
   node *j*'s signal is sent to node *i* with a **precision weight** (how much to
   trust it) and a **scaling factor** (how much of it applies — e.g. a cross-asset
   beta).
4. The **`l` lit nodes are calibrated at current spot** (real fits to today's quotes).
5. The propagated quantity is the **innovation**
   `signal = calibrated_smile − transported_prior` on each lit node. This signal is
   pushed through the graph toward the **dark** nodes, producing an
   **`extrapolated_smile`** (= transported prior + propagated increment) for each.
6. The mechanism should be **model-agnostic**: trivial for LQD and SVI (they expose a
   small handle vector), less obvious for Multi-Core SIV and the piecewise-affine
   Local-Vol surface.
7. Where a dark node *does* have market quotes, the extrapolated smile can be
   **compared against them** (a backtest / sanity check of the propagation).

The core modelling choice — taken straight from the math note — is to regularize the
**increment** `z = x¹ − x⁰`, not the absolute level. The prior is the default; data
forces coherent, graph-plausible changes on top of it.

---

## 2. The mathematical model (already implemented, faithfully)

The note builds a **linear-Gaussian Bayesian inverse problem on the graph**. The
engine in `backend/volfit/graph/` implements it essentially 1:1 with the equations:

| Concept | Equation | Code |
|---|---|---|
| Row-normalized kernel `K`, stationary `π` | §4.1 | `build.py: _row_normalize, _stationary_distribution` |
| Reversibilized conductances `c_ij = ½(πᵢKᵢⱼ + πⱼKⱼᵢ)` | (reversible-conductance) | `build.py: build_graph` |
| Reversible Laplacian `L_rev = B C Bᵀ` | (Lrev) | `operators.reversible_laplacian` |
| Directed residual `L_dir = (I−K)ᵀ Π (I−K)` | (Ldir) | `operators.directed_residual` |
| Mobility / OT Laplacian `A_ρ = B M Bᵀ` | (Arho) | `operators.mobility_laplacian` |
| Increment precision `Q_Δ = D_κ + η L_dir + λ(A_ρ + νI)⁻¹` | (Qdelta-main) | `prior.build_increment_prior` |
| Predictive prior `μ⁻ = x̄⁰`, `K⁻ = P₀⁻¹ + Q_Δ⁻¹` | (predictive-prior) | `posterior.posterior_update` |
| Gaussian conditioning (covariance form, `n ≪ N`) | (muplus/Kplus-covariance) | `posterior.posterior_update` |
| **Marginal** posterior precision `πᵢ⁺ = 1/K⁺ᵢᵢ` | (marginal-precision-final) | `GraphPosterior.marginal_precision` |
| Empirical-Bayes marginal likelihood + held-out residuals | §9 | `hyper.py` |

This layer is correct, tested (`test_graph_example.py` reproduces the note's 6-node
worked example; `test_graph_scale.py`), and matches the note's "frequent precision
mistake" warning (it reports `1/K⁺ᵢᵢ`, not `Q⁺ᵢᵢ`). **The hard math is done.**

The three hyperparameters carry the intended meaning: `κ` = stiffness toward the
prior, `η` = directed-smoothness reach (how far signal propagates), `λ`/`ν` = the OT
flux / source-sink terms. Hyperparameters are auto-tunable by leave-one-out CV
(`autotune_graph`, sweeping `etaScale`).

---

## 3. The smile integration (what the engine is wired to)

`backend/volfit/graph/smile_universe.py` is the bridge from "abstract scalar field on
a graph" to "smiles":

- A node is one smile `(ticker, expiry-ISO)`; **`t`** is its year-fraction.
- The propagated scalar field is the **3 ATM trader handles**
  `(σ₀ atm-vol, s₀ skew, κ₀ curvature)`, computed exactly from the LQD backbone via
  `models/lqd/atm.atm_handles`. ATM vol (not total variance) is used so the level
  coordinate is comparable across expiries.
- **Each of the 3 coordinates is propagated as an independent Gaussian field**
  (`propagate_handles` loops over the 3, with per-coordinate `κ`/precision because the
  handles have very different scales).
- Posterior handle means are mapped **back to an exact arbitrage-free smile** via the
  ATM-orthogonal retargeting `models/lqd/ortho` (`reconstruct_smiles`): it moves
  `(w₀, skew, curvature)` to the posterior target while leaving the shape/wing modes
  untouched, so every reconstructed slice is a genuine density by construction.

The service + API + UI on top:

- `api/graph_service.py` — `ensure_universe` builds the universe over **all tickers ×
  all expiries** from **current mid LQD fits** (cached via `fit_or_get`).
  `_lattice_weights` auto-generates edges: a **calendar chain** within each ticker
  (weight `10`) plus **cross-ticker, same-expiry** edges (weight `2`).
- `POST /graph/solve` takes user handle **shifts**, runs the Bayesian update, returns
  per-node `baseAtmVol → postAtmVol`, `shiftBp`, `sd`, and a credible band.
- `POST /graph/autotune` — LOO-CV over `etaScale`.
- `GET /graph/nodes` — the baseline lattice.
- Frontend: `views/GraphViewer.tsx`, `components/GraphChart.tsx` (hand-rolled SVG
  lattice; click to light/dim, lasso, double-click to drill into the smile, halo =
  posterior sd, blue→red = shift), `state/useGraph.ts`, `SolverPanel`. Lit/dark is
  shared with the Universe tab (`/universe/lit`).

---

## 4. Objective vs. implementation — the gaps

The **graph mathematics is complete and faithful**. The gap is almost entirely in the
**smile semantics wired around it** — what plays the role of `x⁰`, `y`, and the
reconstructed output. Today the panel behaves as a *manual what-if propagator* ("nudge
these ATM vols by hand and watch them spread"), not the *prior-vs-calibration
extrapolator* the objective describes.

| # | Objective | Current implementation | Gap |
|---|---|---|---|
| **A** | Baseline `x⁰` = **transported prior** (defaulting if none) | `x⁰` = **current mid LQD fit** of every node | Wrong anchor. `prior_transport.py` exists and is correct but is **not wired into the graph at all**. |
| **B** | Signal = `calibrated_smile − transported_prior` on lit nodes | Observation = `baseline_handle + manual user shift` (default +1 vol pt) | The innovation is hand-typed, not derived from a real calibration vs. prior. |
| **C** | Lit nodes are **calibrated at current spot**; that calibration *is* the observation `y` | Lit nodes just carry a manual `dAtmVol` | No automatic "fit the lit node, read its handles" step feeding the solver. |
| **D** | Universe = the **selected `l + d` nodes** | Universe = **all tickers × all expiries**; lit/dark is cosmetic, every node still in the graph | No notion of a *selected* working subset; everything is always present. |
| **E** | All priors at a **synchronous spot** | No spot synchronization; handles are whatever the live mid fits give | The "synchronous" guarantee (B) is absent. |
| **F** | **Model-agnostic** reconstruction (LQD/SVI easy; Sig/LV harder) | Handles come from the LQD backbone; `reconstruct_smiles` is **LQD-only** | The 3-handle intermediate representation is a good model-agnostic *carrier*, but reconstruction back to SVI / Multi-Core SIV / LV is not implemented. |
| **G** | Per-edge **scaling factor** (e.g. cross-asset beta) alongside the precision weight | Edges carry only a conductance weight; the increment propagates **1:1 in handle units** | No scaling/beta channel. A 1-vol-pt SPX move propagates as 1 vol pt to NVDA, not β·1. |
| **H** | Compare extrapolated smile to **actual quotes** on dark nodes | `reconstruct_smiles` is never surfaced; the API returns only scalar ATM shifts + bands; autotune LOO is the only validation | The reconstructed *smile* (not just ATM vol) is never returned, drawn, or compared to quotes. |
| **I** | A **user-supplied sparse bi-directed weighted graph** | Edges auto-generated from a fixed lattice with **2 global knobs** (`calendarWeight`, `crossWeight`) | No per-edge weight editor / arbitrary topology input (CLAUDE.md's "Weights input"). |

What **is** already aligned: the increment-not-level philosophy, the precision
reporting (`πᵢ⁺` → credible bands per node, matching "a value with a given
precision"), bi-directedness (the lattice is symmetric and `K`/conductances support
asymmetry), and the model-agnostic *idea* of propagating a compact handle vector.

---

## 5. What needs to be done (suggested order)

**Phase 1 — re-anchor on the transported prior (makes the feature真 the objective).**
1. Give `ensure_universe` two fields per node instead of one: `x⁰` = **transported
   prior handles** (via `prior_transport.transported_prior_slice` → `atm_handles`),
   with a **default prior** when none is saved (today's fit, or a flat/ATM-anchored
   default — *decision needed, see Q1*).
2. For each **lit** node, run the real **current-spot calibration**, read its handles
   `y`, and feed `d = y − x⁰_transported` as the innovation. Drop the manual-shift
   path (or keep it as an "override" mode).
3. Restrict the universe to the **selected `l + d` nodes** (lit + dark designation),
   not all tickers × expiries.

**Phase 2 — surface the extrapolated smile + validation.**
4. Return `reconstruct_smiles` output through the API (full curve per dark node, with
   the posterior credible band), and overlay it in the Smile/Graph viewers.
5. Where a dark node has quotes, compute and display the extrapolated-vs-market error
   (reuse `calib/rms.py`).

**Phase 3 — model-agnostic reconstruction.**
6. SVI/Multi-Core SIV: same 3-handle propagation, then retarget each model's own ATM
   `(level, skew, curvature)` (a small solve for both — the JW handles carry level and
   skew but not ATM curvature, Note 02). LQD already done.
7. Local-Vol surface: handles are not native; reconstruct by re-fitting the affine
   surface to the propagated parametric smile, or transport the LV grid under the
   propagated ATM move (re-uses `affine_transport.py`). This is the hard case.

**Phase 4 — graph inputs + scaling factor.**
8. Add a **per-edge weight editor** (arbitrary sparse bi-directed graph), persisted
   like the universe.
9. Add a **scaling factor** per edge (cross-asset beta). Mathematically this is a
   change of the directed operator: replace `(zᵢ − Σⱼ Kᵢⱼ zⱼ)` with
   `(zᵢ − Σⱼ Kᵢⱼ βᵢⱼ zⱼ)` in `L_dir`, and/or scale the OT/conductance coupling —
   *decision needed, see Q3.*

**Phase 5 — performance (deferred, already flagged in ROADMAP).** The dense `N×N`
inverses in `prior.py:67,72` and the `O(7·n_obs·N³)` autotune are fine at ~10³ nodes
but should move to the note's sparse matrix-free path (§8) before large universes.

---

## 6. Open questions (please confirm before implementation)

- **Q1 — Default prior.** When a node has *no* saved prior, what is the "default"
  baseline `x⁰`? Options: (a) today's mid fit (so the increment is 0 by definition and
  the node only moves via the graph), (b) a flat/ATM-anchored synthetic smile, (c) the
  nearest-expiry transported prior on the same ticker. The brief says "defaulting in
  the absence of prior" but not which default.

- **Q2 — Selected universe vs. lit/dark.** Should the graph be built **only** over the
  user-selected `l + d` nodes (and lit/dark just splits them), or stay over the whole
  universe with lit/dark as today? The objective implies the former.

- **Q3 — Scaling factor semantics.** Is the per-edge "scaling factor" a **cross-asset
  beta on the increment** (NVDA moves β× SPX), and does it apply per-handle (different
  β for level vs. skew) or one β per edge? And should it live in `L_dir`, in the OT
  conductances, or as a separate term?

- **Q4 — What exactly propagates.** Confirm the propagated object stays the **3 ATM
  handles** `(atm-vol, skew, curvature)` (model-agnostic carrier), rather than, say,
  the full LQD coefficient vector or per-model native parameters. The 3-handle choice
  is what makes model-agnostic reconstruction clean.

- **Q5 — Precision inputs.** The brief says the prior carries "a given precision" and
  edges a "precision weight". Today baseline/observation precisions are hard-coded
  constants (`GRAPH_PRECISION`). Should per-node prior precision come from the fit's
  RMS / quote density, and the observation precision from the lit calibration quality?

- **Q6 — Quote comparison scope.** For dark-node validation against market quotes,
  should this be a live overlay in the viewer, a batch backtest report, or both?
