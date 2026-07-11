# Prior Persistence Design Options

Status: design note, no code change implied.

## 1. Problem Statement

The app currently has a useful but opinionated prior-persistence mechanism:
after a prior surface is saved or fetched, calibration can be anchored toward the
transported prior where the live strike grid is sparse. The current mechanism is
implemented as prior-derived pseudo-observations at delta-locations, with a
data-gap weighting scheme. In words:

```text
transport prior to current forward
choose anchor strikes from prior delta locations
measure live quote density around those strikes
add prior price residuals only where desired coverage exceeds observed coverage
add a companion prior var-swap moment when the whole smile is under-covered
```

This is a sensible Bayesian-MAP interpretation if the prior is treated as extra
evidence in parts of strike space with little current evidence. But it can be too
literal in strike space. A single tight ATM quote can be strong evidence for a
parallel level move of the whole smile, yet the current data-gap anchor may still
preserve prior wings because those wings are locally unobserved. The resulting
fit can look like "ATM moved, wings persisted", when the intended economic move
was "level moved, shape persisted".

The design goal is therefore:

```text
Use the prior only where the current market has insufficient information,
without damping a genuine current signal.
```

That means the key question is not only "where are quotes sparse?" It is also
"which smile factors or quote operators are sufficiently observed?"

## 2. Current Mechanism: Strike-Space Data-Gap Anchor

Current behavior is broadly:

- Priors are saved as full per-ticker surface snapshots, including the LQD
  backbone and, when present, the affine local-vol surface.
- Fetching priors activates one prior per ticker. Saved priors win; otherwise the
  system can seed from previous close.
- Active priors are transported to the current forward under the selected
  spot-vol dynamics.
- If `autoLoadPrior` is on, calibration receives prior-anchor residuals.
- LQD receives the anchor directly as vega-normalized price residuals.
- Affine local vol receives extra prior-derived option quotes and a prior
  var-swap quote.
- SVI and Multi-Core SIV display overlays currently do not receive the same
  prior-anchor residual directly; they are fitted as display overlays to the
  live quotes and other overlay-supported penalties.
  **[HISTORICAL — superseded by roadmap Phase 3: the prior-anchor and
  operator-prior blocks now reach the SVI and MCS overlays too (see
  `models/{svi_jw,sigmoid}/calibrate.py` and
  `test_prior_parametric.py::test_operator_prior_pulls_all_models_toward_prior_skew`);
  this snapshot describes the pre-Phase-3 state.]**

The important current knobs are:

| Control | Meaning |
| --- | --- |
| `autoLoadPrior` | Turn calibration anchoring on/off when an active prior exists. |
| `priorAnchorWeightPct` | Total prior-anchor budget as percent of live quote weight. |
| `priorAnchorDeltas` | Per-side delta locations for prior anchors. ATM is always included. |
| `dynamicsRegime` / `ssr` | Transport rule from old prior forward to current forward. |
| `weightScheme` | Shapes desired coverage: equal or time-value density. |

This mechanism is model-agnostic in spirit because it creates price-space
pseudo-evidence. In implementation today, it is direct for LQD and LV, but not
yet direct for all displayed parametric overlays.

### 2.1 Current Code Touchpoints

The current behavior is concentrated in a few places:

| Area | Current responsibility |
| --- | --- |
| `backend/volfit/calib/prior.py` | Builds transported-prior strike anchors, local data-gap weights, vega caps, and residuals. |
| `backend/volfit/api/service.py` | Turns `autoLoadPrior` plus active priors into LQD calibration anchors and prior overlays. |
| `backend/volfit/api/affine_fit.py` | Converts prior anchors into synthetic affine local-vol option and var-swap quotes. |
| `backend/volfit/api/schemas.py` | Defines the user-facing options: `autoLoadPrior`, `priorAnchorWeightPct`, and `priorAnchorDeltas`. |
| `backend/volfit/api/state.py` | Persists option changes and invalidates fits when prior-anchor knobs change. |
| `backend/volfit/graph/precision.py` | Defines graph observation and baseline precision heuristics. |
| `backend/volfit/graph/posterior.py` | Combines graph baseline and observation precision into posterior handles. |
| `backend/volfit/api/graph_extrapolation.py` | Applies the graph prior in increment space rather than strike space. |

These touchpoints suggest that the clean implementation path is additive: keep
the current strike-anchor machinery, introduce a new operator/factor residual
builder beside it, and select the builder from a single prior-persistence mode.

## 3. Design Principle: Persist Information, Not Shape Blindly

Prior persistence should be understood as a hierarchy:

1. Fresh market data wins.
2. The prior fills missing factors or regions.
3. The prior should not resist a well-observed move.
4. The prior's precision decays with age, transport distance, and weak provenance.
5. The user should choose the persistence space: strike-space, operator-space,
   factor-space, or graph-increment space.

The main technical object is a residual of the form:

```text
sqrt(lambda_j) * (O_j(model) - O_j(prior)) / scale_j
```

where `O_j` can be a strike price, an implied-vol quote operator, a model factor,
or a graph handle. The central question is how to set `lambda_j`.

A robust activation rule is:

```text
gap_j = max(1 - obs_precision_j / required_precision_j, 0) ^ gamma
lambda_j = global_strength * prior_precision_j * gap_j
```

If `obs_precision_j >= required_precision_j`, then `lambda_j = 0`: the prior is
not active for that operator. This is the "do not damp the signal" rule.

## 4. Option A: Keep Strike-Space Data-Gap Anchors

This is the current design, cleaned up and made explicit.

Definition:

```text
O_j(model) = model call price at anchor strike k_j
O_j(prior) = transported-prior call price at the same k_j
```

Weights are determined by local quote-density gaps over the chosen delta anchor
span.

Advantages:

- Simple and already mostly implemented.
- Works naturally for affine local vol via synthetic option quotes.
- Preserves wing shape where there are no wing quotes.
- Easy to explain as "prior pseudo-quotes in data gaps".

Problems:

- Local quote density is not the same as information about global smile factors.
- A strong ATM signal may not propagate as a level move across the anchor set.
- It can preserve prior wings even when the market has clearly shifted level.
- It is sensitive to anchor placement and KDE bandwidth.

Suggested UI mode:

```text
Prior persistence mode = Strike gaps
```

Suggested knobs:

| Knob | Default | Meaning |
| --- | ---: | --- |
| Strength | `50%` | Prior budget as percent of live quote weight. |
| Anchor deltas | `2,5,10,25,40` | Per-side forward deltas plus ATM. |
| Density bandwidth | `0.06 k` | KDE width for observed coverage. |
| Desired density | `equal` / `time-value` | Same concept as quote weighting. |
| Tail vega cap | `25x` | Prevents one deep tail anchor from dominating. |
| Var-swap carry | on | Adds aggregate tail/level prior when coverage is poor. |

Best use:

- Very sparse wings.
- Desk wants yesterday's smile extrapolation to survive in unquoted areas.
- A fit is used for risk/extrapolation more than for reading a new market signal.

## 5. Option B: Quote-Operator Prior Anchors

This is the proposed middle path. Instead of anchoring individual strike quotes,
anchor simple trader quote operators:

```text
ATM
10d collar / risk reversal
25d risk reversal
25d butterfly
var-swap
optional wing slopes or 5d/10d tail operators
```

The prior then persists only the operators that are not sufficiently observed.
For example, if there is one tight ATM quote but no wings:

- observed precision for ATM is high, so ATM prior weight is zero;
- observed precision for skew/collar is low, so skew prior can remain active;
- observed precision for butterfly/wing convexity is low, so curvature prior can
  remain active;
- the fit can move in level without dragging the old level back.

### 5.1 Operator Definitions

All operators should be computed in a consistent current-forward delta convention.
For a model smile `sigma(k)` and expiry `T`:

```text
ATM        = sigma(0)
RR_25      = sigma(k_call_25) - sigma(k_put_25)
BF_25      = 0.5 * (sigma(k_call_25) + sigma(k_put_25)) - sigma(0)
RR_10      = sigma(k_call_10) - sigma(k_put_10)
BF_10      = 0.5 * (sigma(k_call_10) + sigma(k_put_10)) - sigma(0)
VarSwapVol = sqrt(K_var / T)
```

Some desks call a "collar" with the opposite sign from risk reversal. The UI
should make the convention explicit:

```text
Collar sign = Call minus put | Put minus call
```

The prior operator value is evaluated on the transported prior:

```text
O_prior_j = O_j(transported_prior)
```

The calibration residual is:

```text
sqrt(lambda_j) * (O_j(model) - O_prior_j) / operator_scale_j
```

### 5.2 Synthetic Quotes vs Direct Operator Residuals

There are two implementation styles.

Synthetic basket quotes:

```text
ATM quote      -> one synthetic ATM option or vol quote
RR quote       -> signed basket: call-delta vol minus put-delta vol
BF quote       -> basket: half call + half put - ATM
VarSwap quote  -> existing var-swap pseudo-quote
```

Direct operator residuals:

```text
compute O_j(model) directly
stack residual into optimizer
```

Direct residuals are cleaner because risk reversals and butterflies are signed
baskets, not literal option prices. Synthetic baskets are attractive only if the
calibrator infrastructure strongly prefers quote-like inputs. The UI can still
call them "synthetic quote operators".

### 5.3 Observation Precision for Operators

The hard part is estimating whether an operator is sufficiently observed.

A practical first version can use local quote support:

```text
I(k_a) = sum_i quote_weight_i * exp(-0.5 * ((k_i - k_a) / h)^2)
```

For an operator with basket locations `a` and coefficients `c_a`, define:

```text
obs_info_j = 1 / sum_a c_a^2 / (I(k_a) + eps)
```

This harmonic-style aggregation has the right behavior:

- ATM needs support near ATM.
- A risk reversal needs support on both put and call deltas.
- A butterfly needs support on both wings and ATM.
- If one leg is missing, precision stays low.

Then scale by fit quality and spread:

```text
obs_precision_j
  = obs_info_j
    * spread_factor_j
    * fit_quality_factor
    * freshness_factor
    / operator_scale_j^2
```

Better later version:

```text
obs_cov_O = J_O * cov(theta_data_only) * J_O^T
obs_precision = diag(obs_cov_O)^-1
```

where `theta_data_only` is the data-only fit and `J_O` is the operator Jacobian.
This is more statistically faithful but heavier. It can be introduced after the
heuristic version.

### 5.4 Two-Pass Activation

To avoid damping genuine signal, operator priors should ideally be activated
after a provisional data-only fit:

```text
1. Fit current quotes with no prior.
2. Compute operator values and observation precisions.
3. Activate only the prior operators whose observation precision is insufficient.
4. Refit with those operator-prior residuals.
```

This means an ATM quote can move the level in pass 1, and the prior does not
pull the level back in pass 2 if ATM precision is high.

Suggested UI mode:

```text
Prior persistence mode = Quote operators
```

Suggested knobs:

| Knob | Default | Meaning |
| --- | ---: | --- |
| Operator set | `ATM, RR25, BF25, VarSwap` | Which operators can persist. |
| Strength | `50%` | Base operator-prior budget. |
| Required precision | per operator | Precision threshold above which prior turns off. |
| Gap exponent | `1.0` | Sharpness of transition from active to inactive. |
| Support bandwidth | `0.06 k` | Quote support kernel around operator legs. |
| Min leg support | `on` | Prevents RR/BF precision from being high if one leg is missing. |
| Operator covariance | `diagonal` | Diagonal first; full covariance later. |
| Data-only prepass | `on` | Enables "do not damp signal" activation. |
| Collar sign | desk choice | `call-put` or `put-call`. |

Best use:

- User wants the prior to persist smile shape factors, not raw strike points.
- One or a few liquid quotes should update level or skew coherently.
- The product should feel model-agnostic and trader-readable.

## 6. Option C: Factor or Parameter Distance Regularizer

This is the cleanest mathematical version if the chosen factors are stable.

Define a normalized factor vector:

```text
f(model) = [
  ATM vol,
  ATM skew,
  ATM curvature,
  left wing slope,
  right wing slope,
  var-swap vol,
  optional low-order LQD shape modes
]
```

Then add:

```text
lambda * || W * (f(model) - f(transported_prior)) ||^2
```

or, with covariance:

```text
(f - f_prior)^T Sigma_prior^-1 A_gap (f - f_prior)
```

where `A_gap` turns off coordinates that current data observes well.

Advantages:

- Very direct answer to the ATM-level concern.
- Good separation between level, skew, curvature, and wing/tail shape.
- Can be made model-agnostic by computing factors from any smile.
- Easier to reason about than many strike anchors.

Problems:

- Requires stable factor definitions across all models.
- Some factors, especially wing slopes, may be mostly extrapolation rather than
  market evidence.
- Native model parameters should generally not be regularized directly unless
  they have comparable meaning across expiries and models.

Suggested UI mode:

```text
Prior persistence mode = Smile factors
```

Suggested knobs:

| Knob | Default | Meaning |
| --- | ---: | --- |
| Factor set | `ATM, skew, curvature, varswap` | Coordinates to persist. |
| Strength | `50%` | Base prior precision. |
| Factor scales | auto | Normalizers, e.g. vol bp, skew units, curvature units. |
| Covariance | diagonal | Diagonal first; historical covariance later. |
| Coverage gate | on | Turn off factors with sufficient observed precision. |
| Include wings | off by default | Wing slopes are powerful but can over-constrain. |

Best use:

- Clean daily stability.
- Sparse but meaningful quotes.
- Users think in level/skew/curvature rather than individual strikes.

## 7. Option D: Hybrid Operator and Strike Prior

This is likely the best production default after experimentation.

Use operator priors for global factors:

```text
ATM, RR25, BF25, VarSwap
```

Use strike-space data-gap anchors only for residual tail shape beyond the chosen
operators:

```text
deep 2d/5d wing anchors, only if no quote support and no operator covers them
```

This gives the desired behavior:

- ATM quote can update level.
- RR quote can update skew.
- BF quote can update curvature.
- Var-swap can update aggregate variance/tail level.
- Deep strike anchors preserve unquoted tail details only when no current
  operator or quote says otherwise.

Suggested UI mode:

```text
Prior persistence mode = Hybrid
```

Suggested knobs:

| Knob | Default | Meaning |
| --- | ---: | --- |
| Operator strength | `50%` | Prior budget for operators. |
| Tail-anchor strength | `20%` | Residual strike-space tail budget. |
| Operator set | `ATM, RR25, BF25, VarSwap` | Main persisted factors. |
| Tail deltas | `2,5` | Deep anchors only. |
| Coverage gate | on | Turns off prior where data is sufficient. |
| Data-only prepass | on | Prevents damping current signal. |

Best use:

- Default desk workflow.
- Strong ATM or near-ATM data with sparse tails.
- Need both trader-readable factors and tail preservation.

## 8. Option E: Graph-Increment Prior Only

The graph extrapolation path already has a cleaner prior semantics:

```text
baseline = transported prior handles
observation = calibrated lit handles
innovation = observation - baseline
posterior = graph propagation of innovations
```

This regularizes increments rather than absolute levels. It is the right
semantics for cross-expiry/cross-asset extrapolation. A user could choose to
disable calibration prior anchoring entirely and rely on:

```text
data-only calibration at lit nodes
graph prior for dark nodes
```

Advantages:

- Avoids polluting calibration with prior pseudo-evidence.
- Clean Bayesian interpretation in handle space.
- Current signal at lit nodes is not damped by yesterday's smile.

Problems:

- Does not stabilize a single sparse lit-node calibration by itself.
- If a lit node has only one ATM quote, the data-only calibration can be
  underdetermined unless the smile model has its own regularization.
- Dark nodes get graph posterior, but sparse lit nodes may still be noisy.

Suggested UI mode:

```text
Prior persistence mode = Graph only
```

Suggested knobs:

| Knob | Default | Meaning |
| --- | ---: | --- |
| Graph kappa | existing | Local increment stiffness. |
| Graph eta | existing | Directed smoothness / propagation reach. |
| Graph lambda / nu | existing | OT transport/source-sink regularization. |
| Baseline precision | data-derived | Source, age, transport distance. |
| Observation precision | data-derived | Fit RMS, quote density, spread. |

Best use:

- Multi-node extrapolation.
- User wants lit nodes to be pure market fits.
- Prior should affect only dark or under-observed graph inference.

## 9. Precision Estimation: What "Enough Signal" Means

Every mode should share a common precision vocabulary.

### 9.1 Observation Precision

For quote operators or factors:

```text
obs_precision =
  quote_support
  * bid_ask_quality
  * fit_quality
  * freshness
  / scale^2
```

Components:

| Component | Meaning |
| --- | --- |
| Quote support | Are there quotes near all operator legs? |
| Bid-ask quality | Tight quotes imply higher precision. |
| Fit quality | A high RMS fit should reduce confidence. |
| Freshness | Historical/stale observations decay. |
| Scale | Normalizes ATM, RR, BF, var-swap into comparable units. |

### 9.2 Prior Precision

Prior precision should decay with:

| Component | Meaning |
| --- | --- |
| Source | Saved active prior > previous-close fallback > bootstrap. |
| Age | Older priors less precise. |
| Transport distance | Larger `abs(log(F_now/F_prior))` less precise. |
| Model mismatch | If prior model differs from displayed model, lower confidence. |
| Prior fit quality | Bad prior snapshot should not dominate. |

### 9.3 Activation Gate

Recommended universal gate:

```text
gap_j = max(1 - obs_precision_j / required_precision_j, 0) ^ gamma
active_prior_precision_j = base_prior_precision_j * gap_j
```

This is stricter than the current local strike-density gap. It says:

```text
If current observations are precise enough for this operator, do not persist
the prior for this operator at all.
```

### 9.4 Diagnostics

The UI should expose enough diagnostics to make the prior auditable. For each
expiry and each active operator or factor, show:

| Diagnostic | Meaning |
| --- | --- |
| Prior value | Transported-prior operator value. |
| Data-only value | Operator value after the no-prior prepass. |
| Final value | Operator value after prior-gated refit. |
| Observation precision | How strongly current quotes identify this operator. |
| Required precision | Threshold above which prior turns off. |
| Gap | Activation factor between `0` and `1`. |
| Active prior weight | Final penalty precision used in calibration. |
| Binding reason | Example: missing put leg, stale prior, wide quote, good ATM support. |

This matters because the prior should not be a hidden stabilizer. The user
should be able to see why ATM was allowed to move, why skew was still anchored,
or why deep tails were preserved.

## 10. Recommended User-Facing Modes

Expose one main selector:

```text
Prior persistence:
  Off
  Overlay only
  Strike gaps
  Quote operators
  Smile factors
  Hybrid
  Graph only
```

Mode meanings:

| Mode | Calibration effect | Best for |
| --- | --- | --- |
| Off | No prior overlay or anchor. | Pure current market. |
| Overlay only | Draw transported prior, no calibration penalty. | Visual comparison. |
| Strike gaps | Current data-gap synthetic option anchors. | Preserve unquoted wings. |
| Quote operators | Persist ATM/RR/BF/varswap only if under-observed. | Trader-readable shape persistence. |
| Smile factors | Penalize factor distance to prior. | Clean level/skew/curvature control. |
| Hybrid | Operators plus residual deep-tail strike anchors. | Likely default. |
| Graph only | Prior only as graph baseline for extrapolation. | Lit nodes stay market-pure. |

Advanced controls should be grouped by mode, not shown all at once.

## 11. Implementation Sketch

### Phase 1: Schema and UI

Add an options field:

```text
priorPersistenceMode:
  off | overlay | strike_gap | quote_operator | smile_factor | hybrid | graph_only
```

Keep existing fields but make them mode-specific:

```text
priorAnchorWeightPct
priorAnchorDeltas
```

Add new fields:

```text
priorOperatorSet
priorOperatorStrengthPct
priorOperatorRequiredPrecision
priorOperatorGapExponent
priorOperatorBandwidth
priorOperatorCovarianceMode
priorDataOnlyPrepass
priorFactorSet
priorFactorStrengthPct
priorTailAnchorStrengthPct
```

### Phase 2: Operator Library

Add a model-agnostic operator module:

```text
volfit/calib/operators.py
```

Responsibilities:

- Locate Black delta strikes from a model smile and current forward convention.
- Evaluate ATM, RR, BF, collar, and var-swap operators.
- Compute operator scales.
- Compute heuristic observation precision from quote support.
- Optionally compute covariance from a data-only fit later.

### Phase 3: Calibrator Integration

Add direct operator residual support to:

- LQD calibration.
- SVI calibration.
- Multi-Core SIV calibration.
- Affine local-vol calibration, probably via direct operator rows or synthetic
  basket quotes.

This would also fix the current asymmetry where LQD/LV get the prior anchor more
directly than SVI/Sigmoid overlays.

### Phase 4: Two-Pass Data-Only Gate

Implement:

```text
data_only_fit = fit without prior
operator_precision = estimate from quotes + data_only_fit
prior_residuals = build only for under-observed operators
final_fit = fit with active residuals, initialized from data_only_fit
```

Cache keys must include the mode and all operator/factor knobs.

### Phase 5: Validation

Add tests and backtests:

- Tight ATM quote turns off ATM prior.
- Sparse wings keep RR/BF/tail priors active.
- Adding a tight 25d call and put quote turns off RR/BF prior.
- Operator mode allows a parallel level bump without prior damping.
- Hybrid mode preserves unquoted deep tails more than operator-only mode.
- SVI/Sigmoid overlays receive the same prior semantics as LQD.
- Graph-only mode leaves lit calibration unchanged while changing dark nodes.

## 12. Recommendation

The current strike-space data-gap anchor should remain available because it is
simple and useful for unquoted wings. But it should not be the only prior
persistence model.

The best next design is:

```text
Default candidate: Hybrid
  operator priors for ATM / RR25 / BF25 / var-swap
  deep-tail strike anchors only where no operator or quote covers the tail
  two-pass activation so well-observed operators receive zero prior weight
```

This gives the user the behavior they likely expect:

- A tight ATM quote can move the whole level.
- Sparse skew/curvature remains stabilized by yesterday's shape.
- Deep unquoted tails can still persist.
- Prior influence is visible, controllable, and explainable by operator-level
  precision diagnostics.
