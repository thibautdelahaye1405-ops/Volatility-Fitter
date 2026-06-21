# Graph Extrapolation Status Note - Add-on

Date: 2026-06-21

This note is an add-on to `Docs/graph_extrapolation_status_note.md`. It records my answers to the six open design questions after reading the repository docs and the current graph implementation. It is intentionally a design note only; no code changes are implied here.

## Executive view

The status note is directionally right. The graph math layer is already quite close to the intended model: it propagates increments, uses a row-normalized directed kernel, forms a directed residual precision, adds an OT-style mobility term, and solves a Gaussian posterior. The main mismatch is not the solver. It is the production workflow around the solver.

Today the graph is effectively a manual ATM-handle what-if tool over the provider-visible fitted universe. The intended product is a prior-anchored extrapolator over the user-selected lit and dark universe:

- transported prior is the baseline;
- lit calibration produces the observed innovation relative to that baseline;
- dark nodes receive propagated innovations;
- reconstructed smiles are compared to live or historical quotes.

I would preserve the current manual-shift graph as a useful sandbox, but introduce a separate production extrapolation path that is explicitly prior-anchored and calibration-fed.

## Answers to the six questions

### 1. Default prior when a node has none

Recommendation:

Use a hierarchy, not one global default.

1. Prefer the active saved or fetched prior transported to the current forward.
2. If that is missing, use a nearest-expiry transported prior on the same ticker, with visibly reduced precision and a `prior_source=nearest_expiry` flag.
3. If no prior exists anywhere useful, use today's fit only as a neutral bootstrap baseline, with low confidence and a `prior_source=today_bootstrap` flag.
4. Avoid flat or ATM-only defaults except as an explicit diagnostic or stress mode.

Rationale:

The model is supposed to propagate innovations, not absolute smile levels. A flat prior creates artificial innovations wherever the market has a real smile. Today's fit creates a circular validation problem if it is treated as a historical prior, because a dark-node quote comparison can become "today versus today." But today's fit is still useful as a bootstrap baseline: it gives a stable local smile shape and a zero self-innovation when no prior history exists.

Implementation consequence:

The graph node should expose prior provenance and precision, for example:

- `active_transported`
- `saved_transported`
- `nearest_expiry_transported`
- `today_bootstrap`
- `none`

The solver should be allowed to include a node with a weak bootstrap prior, but validation reports should not present that node as a clean prior-vs-market test.

### 2. Selected universe

Recommendation:

For the production extrapolator, build the graph over the selected lit plus dark nodes only. Keep the full provider universe as a separate research, backtest, or diagnostic mode.

Rationale:

The user-selected universe is the product boundary. It controls what the user intends to reason about, which nodes should be calibrated, and which nodes should be extrapolated. Building over every fitted provider node introduces hidden propagation paths, hidden liquidity assumptions, extra cost, and harder-to-explain results.

Lit and dark should not mean "in graph" versus "out of graph." They should mean:

- lit: selected node with a calibration observation;
- dark: selected node receiving graph extrapolation, with quotes optionally used only for validation.

Unselected nodes should normally be excluded. If a future mode wants broad-market context, it should be explicit.

Implementation consequence:

The production graph builder should use `UniverseMixin.selected_expiries` plus the lit/dark map, not `provider.list_tickers()` crossed with every currently fetched forward. Dark selected nodes should be allowed to exist with a transported prior even if they have not been calibrated today.

### 3. Scaling factor

Recommendation:

Treat scaling as an edge-level beta on the propagated increment, and place it in the directed prediction residual, not in the OT conductance.

Conceptually, instead of:

```text
z_i ~= sum_j K_ij z_j
```

use:

```text
z_i ~= sum_j K_ij B_ij z_j
```

where `B_ij` is the cross-node increment beta. For the current 3-handle carrier, `B_ij` should ideally be diagonal:

```text
B_ij = diag(beta_atm, beta_skew, beta_curvature)
```

Rationale:

Conductance answers "how much should this edge be trusted?" Beta answers "how large is node i's move when node j moves?" Those are different ideas. Mixing beta into conductance loses sign, asymmetry, and handle-specific behavior. It also makes uncertainty calibration harder to interpret.

The OT conductance or mobility term should remain a geometry and precision object. The beta belongs in the directed compatibility relation.

Implementation consequence:

The schema can start simple with one beta per edge and internally broadcast it to all handles, but the data model should be ready for per-handle beta. Cross-asset edges especially need this: ATM level beta, skew beta, and curvature beta can differ materially. Calendar edges can default closer to one, while cross-ticker edges should be explicitly estimated, configured, or learned.

Bi-directed edges should not force symmetric beta. `beta_ij` and `beta_ji` may differ.

### 4. What propagates

Recommendation:

Keep the three ATM handles as the v1 carrier:

- ATM vol;
- ATM skew;
- ATM curvature.

Do not propagate full LQD vectors or native per-model parameters in the first production version.

Rationale:

The three ATM handles are the right abstraction for v1 because they are compact, comparable across expiries and tickers, and already supported by the current LQD bridge. They also match the existing graph code's independent Gaussian propagation pattern. A full LQD vector would introduce more dimensions, more conditioning risk, and more model-specific interpretation. Native params would fragment the graph by smile model.

The current LQD reconstruction path is a reasonable production bridge: propagate ATM handles, then retarget the LQD smile through `build_atm_coordinates`. For SVI, Sigmoid, and local-vol surfaces, the graph output should initially be treated as a target smile or prior target, not as native parameter transport.

Implementation consequence:

The plan should explicitly define the carrier units and semantics:

- `atm_vol`: volatility units, not total variance;
- `skew`: first derivative of implied vol with respect to log-moneyness at ATM;
- `curvature`: second derivative of implied vol with respect to log-moneyness at ATM.

The local-vol path deserves special care. The local-vol docs make clear that LV calibration is a full surface optimization, not a cheap parameter mutation. For LV, use graph-extrapolated smiles as projection targets or prior targets, then calibrate/project the LV representation afterward.

### 5. Precision inputs

Recommendation:

Yes. Replace the production hard-coded precision constants with per-node and per-handle precision estimates from calibration quality and quote coverage. Keep constants only as floors, caps, and sandbox defaults.

Rationale:

The graph is Bayesian enough that precision is not a UI nicety; it is part of the product truth. A dense, tight, recent options chain should not enter the solver with the same observation precision as a sparse, wide, stale, or poorly fitted chain.

Useful precision inputs already exist or are close to existing infrastructure:

- fit RMS or weighted RMS;
- quote density by strike and near-ATM coverage;
- bid/ask width and haircut mode;
- quote age or as-of mismatch;
- number of usable quotes;
- prior snapshot source and age;
- transport distance from prior forward to current forward;
- fallback source, such as nearest-expiry or today-bootstrap.

Implementation consequence:

Separate at least three precision concepts:

- observation precision: confidence in today's lit-node calibrated innovation;
- baseline/prior precision: confidence in the transported prior level at each node;
- edge precision/conductance: confidence in the graph dependency relation.

A first implementation can use a conservative formula with floors and caps. For example, start from inverse squared fit error, multiply by quote-density and freshness factors, then cap by handle-specific maximums. The important part is to plumb the source and expose it in diagnostics before attempting serious hyperparameter tuning.

### 6. Quote comparison

Recommendation:

Do both live overlay and batch backtest.

Live overlay:

Show the extrapolated dark-node smile against live quotes and quote bands, ideally with posterior uncertainty for the ATM handles. This is necessary for desk workflow and immediate debugging.

Batch backtest:

Run leave-one-node-out or blocked holdout tests over quoted nodes and historical snapshots. This is necessary for calibrating hyperparameters, beta, precision formulas, and uncertainty calibration.

Rationale:

Live overlay is operationally useful but visually easy to overfit. Batch backtest is statistically useful but too slow and abstract to be the only user feedback loop. The two answer different questions:

- live overlay: "Does this dark node look sane right now?"
- batch backtest: "Does this graph methodology predict held-out smiles reliably?"

Implementation consequence:

The production solve response should support quote metrics and full-smile diagnostics, at least for requested or selected nodes:

- fitted or extrapolated curve points;
- quote bid/mid/ask points;
- residuals by strike;
- weighted RMS;
- inside-spread hit rate;
- ATM handle residuals;
- standardized residuals using posterior uncertainty.

For large graphs, do not always return dense smile curves for every node. Return summaries by default and fetch full curves on demand.

## Suggested amendments to the implementation plan

### Amendment A - Split sandbox solve from production extrapolation

Keep the current manual-shift graph solve as a sandbox or what-if endpoint. It is useful and already tested.

Add a production path whose observations are not manual shifts. They should be computed as:

```text
lit innovation = today's calibrated handles - transported prior handles
```

The posterior mean increment is then added back to the transported prior to reconstruct each node's extrapolated smile.

This avoids overloading one endpoint with two very different semantics.

### Amendment B - Make prior provenance first-class

Before adding richer edge editing, add explicit per-node prior state:

- prior source;
- prior as-of time;
- forward used for transport;
- transport distance;
- prior precision;
- whether the prior is valid for validation scoring.

This will make graph results explainable and prevent circular backtests.

### Amendment C - Build from selected lit/dark universe

Move production graph construction from "all provider tickers and current fetched forwards" to "selected universe plus lit/dark flags." The current full-universe builder can remain behind a diagnostic mode.

This change should happen early, because it affects every downstream result and all UX expectations.

### Amendment D - Add beta schema now, even if UI is simple

Even if v1 UI exposes only calendar weight, cross weight, and maybe one cross-asset beta, the backend schema should distinguish:

- edge conductance or confidence;
- edge beta or scaling;
- beta per handle versus scalar beta;
- directionality.

This prevents a later migration where `weight` has silently meant both trust and amplitude.

### Amendment E - Return smile-level artifacts, not only ATM summaries

The current ATM-only result is too thin for the stated objective. The production path should be able to return:

- posterior ATM handles;
- reconstructed smile;
- prior smile;
- lit calibration smile where applicable;
- quote comparison metrics.

This can be lazy or node-scoped to control payload size.

### Amendment F - Put precision plumbing before autotune

Autotuning over hard-coded precision constants will tune around a modeling artifact. Fit-derived and quote-density-derived precision does not have to be perfect in v1, but it should exist before serious lambda, eta, kappa, and beta tuning.

### Amendment G - Treat local-vol as a projection target

Do not try to propagate native LV parameters. Use the graph smile as a target or prior for an LV projection/calibration step. This matches the local-vol methodology docs and avoids pretending that a local-vol surface has stable three-parameter transport semantics.

### Amendment H - Add validation gates with targeted tests

Before calling the graph extrapolator production-ready, add tests for:

- transported-prior identity when forward is unchanged;
- nonzero transported-prior shift when forward changes;
- lit innovation equals calibrated handles minus transported prior handles;
- dark selected nodes are not calibrated as observations;
- selected universe excludes unselected provider nodes;
- beta changes propagated increment magnitude without changing conductance semantics;
- lower fit quality reduces observation precision;
- live quote comparison metrics are stable;
- leave-one-node-out backtest reports residuals and standardized residuals.

## Revised sequencing

I would slightly reorder the status note's proposed plan:

1. Preserve current manual graph as sandbox.
2. Add selected-universe graph construction.
3. Add transported-prior node baselines with provenance.
4. Add lit calibration innovation feed.
5. Add per-node/per-handle precision plumbing.
6. Return reconstructed smiles and quote comparison metrics.
7. Add beta/scaling to directed residuals.
8. Add live overlay and batch backtest workflows.
9. Add model-agnostic native reconstruction beyond LQD.
10. Optimize sparse performance only when selected-universe sizes demand it.

The main reorder is that precision and prior provenance should arrive before serious autotune/backtest work, and selected-universe construction should arrive before full-smile validation. Otherwise the validation will measure a different product from the one the user actually selected.

## Bottom line

The current implementation is a good graph-math prototype and a useful manual what-if visualizer. The next production step should not be to make the existing manual solver more elaborate. It should be to introduce a prior-anchored extrapolation workflow:

```text
transported prior -> lit calibration innovation -> graph posterior increment -> dark reconstructed smile -> quote comparison
```

The six answers are therefore:

1. transported prior first, nearest-expiry transported second, today's fit only as weak bootstrap, flat only as explicit diagnostic;
2. selected lit plus dark universe for production;
3. beta on directed increments, separate from conductance, preferably per-handle and per-direction;
4. keep the three ATM handles as v1 carrier;
5. yes, use fit quality and quote density for precision;
6. both live overlay and batch backtest.

