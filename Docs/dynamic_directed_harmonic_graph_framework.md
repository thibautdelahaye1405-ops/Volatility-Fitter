# Dynamic Directed-Harmonic Graph Extrapolation

## A stateful framework for asynchronous volatility calibration and dark-node marking

**Status:** ADOPTED — Phase 0 executed 2026-07-20 (decision record in
Section 17; golden fixtures locked in
`backend/tests/fixtures/graph_dynamic_golden.json`); decisions D2–D5
RATIFIED 2026-07-20 (user proceed instruction), D6 OPEN by design until the
Phase-3 adjudication. Phase 1 (causal temporal state) SHIPPED 2026-07-21:
`backend/volfit/graph/temporal_state.py`, exit gate green — the Section-5
A/B example reproduced by the state objects alone, no graph solve.
Phase 2 (directed prediction engine) SHIPPED 2026-07-21:
`backend/volfit/graph/directed_state.py` — exact DAG pass with gain-row
propagation over independent roots (full parent covariance, structural
cut, attribution by construction); exit gate green (zero reverse
sensitivity exact; goldens 15.2/15.6/15.10 and the Section-5 sequence
reproduced through the engine, including the correlated-parents variance
via shared-ancestor gains).

**Date:** 2026-07-20

**Relationship to the existing design:** this note refines
`Docs/graph_precision_message_framework.md`. It does not change production
behaviour until its contracts and migration are explicitly approved.

---

## 1. Executive decision

Volatility extrapolation needs two graph semantics that should not be forced
into one operator:

1. **Reciprocal harmonic relations** for interpolation relationships where
   either endpoint legitimately informs the other once expressed in common
   units. Calendar interpolation is the canonical example.
2. **Directed dynamic relations** for economically asymmetric propagation,
   such as a liquid index or ETF informing an illiquid constituent. These
   relations need temporal memory so that an observed idiosyncratic move in
   the target is retained when the target becomes dark again.

The recommended production architecture is therefore a **layered dynamic
harmonic model**:

```text
transported prior
    -> timestamped calibration innovations
    -> causal observation-state update
    -> directed source-to-target prediction
    -> persistent target idiosyncratic residual
    -> reciprocal beta-harmonic completion
    -> smile reconstruction and validation
```

The central product rules are:

- a fresh, certified lit calibration owns its published central value;
- an absent reverse edge means exactly zero reverse influence;
- beta controls transmitted amplitude;
- relation precision controls uncertainty and multi-source weighting;
- a separate temporal coefficient controls persistence or mean reversion;
- only actual calibrations update persistent state;
- graph predictions never become later calibration observations or transported
  priors;
- dark nodes with no observation-supported route remain at the transported
  prior and are reported as unsupported.

This framework retains the useful Gaussian and Laplacian machinery already in
the repository, but removes an ambiguity in the current precision-message
design: a pairwise Gaussian factor is reciprocal information even when stored
with a source and a target. It cannot, by itself, represent high precision
from A to B and zero precision from B to A.

---

## 2. Motivation

### 2.1 The production problem is both spatial and temporal

The graph is not merely filling a static missing value. It is marking a
changing surface from observations that arrive at different times:

- liquid indexes and ETFs may refresh every minute;
- constituents may refresh sporadically;
- expiries within one ticker may have very different liquidity;
- a node can alternate between lit and dark during the session;
- a target can experience a genuine idiosyncratic move while its source does
  not;
- the transported baseline itself can move because forwards, spot, and the
  prior snapshot are transported to the current valuation state.

A memoryless snapshot graph loses an observed target-specific move as soon as
the target becomes dark. A symmetric graph can also allow the target's move to
flow backward into a source that is temporarily unobserved. Both behaviours
are undesirable for liquid-to-illiquid propagation.

### 2.2 Three quantities must remain distinct

For a directed relation from source (j) to target (i), three controls have
different meanings:

1. **Amplitude** (\beta_{ij}): how much of the source move reaches the target.
2. **Relation precision** (p_{ij}): how uncertain that source-to-target
   mapping is.
3. **Temporal persistence** (phi_i(Delta)): how quickly an actually observed
   target-specific residual is forgotten.

Using edge precision to make an old observation fade conflates confidence and
mean dynamics. Using beta to make uncertainty wider conflates amplitude and
confidence. Using a symmetric pairwise factor to encode a one-way economic
relationship conflates relation geometry and causal direction.

### 2.3 Why the existing pairwise factor is not one-way

The precision-message factor

\[
p_{ij}(z_i-\beta_{ij}z_j)^2
\]

is a valid positive-semidefinite Gaussian relation. However, it can be read in
both directions:

\[
z_i\approx\beta_{ij}z_j
\qquad\Longleftrightarrow\qquad
z_j\approx z_i/\beta_{ij}.
\]

Its canonical orientation determines units, not causal influence. In
particular, the reverse precision in (j)'s units is

\[
\boxed{p_{j\leftarrow i}=p_{i\leftarrow j}\,\beta_{ij}^{2}.}
\]

Therefore a beta-one high-precision factor between A and B is high precision
in both directions. Clamping A while it is fresh prevents B from moving A at
that instant, but does not solve the problem when A is temporarily dark.

### 2.4 The required modelling split

The graph should distinguish:

- **relation edges**, which are reciprocal constraints and belong in a
  Laplacian or Gaussian Markov random field;
- **influence arcs**, which are conditional source-to-target equations and
  belong in a directed state-space model.

This distinction is semantic, not merely an implementation detail.

---

## 3. Scope and non-goals

This note specifies:

- timestamped observation and dark-state semantics;
- a directed dynamic source-to-target model;
- persistent idiosyncratic target residuals;
- a reciprocal beta-harmonic completion layer;
- uncertainty, attribution, disconnected components, and no-look-ahead rules;
- product modes, schema implications, tests, and an implementation roadmap.

This note does not propose:

- replacing transported priors;
- propagating absolute smile levels in production;
- replacing the three ATM handles in v1;
- feeding extrapolated graph output into saved priors;
- claiming that per-slice graph propagation alone enforces calendar
  no-arbitrage;
- allowing arbitrary directed cycles in the first production version;
- replacing final smile reconstruction or Local-Vol projection.

---

## 4. State variables and observation semantics

The mathematics is stated for one scalar handle. The same construction is run
for ATM volatility, skew, and curvature, with handle-specific beta, precision,
and temporal parameters. A future version may carry a (3\times3) covariance
per node instead of treating the handles independently.

### 4.1 Transported baseline and innovation

For node (i=(\text{ticker},T)) at time (t), let

\[
h^0_{i,t}
\]

be the transported-prior handle and let

\[
z_{i,t}=h_{i,t}-h^0_{i,t}
\]

be its current innovation.

When node (i) is calibrated, the observed innovation is

\[
d_{i,t}=h^{\mathrm{cal}}_{i,t}-h^0_{i,t}.
\]

The graph continues to operate on (z), never directly on absolute smile
levels. Absolute marks are reconstructed only at the end:

\[
\widehat h_{i,t}=h^0_{i,t}+\widehat z_{i,t}.
\]

### 4.2 Observation classes

Every node at a solve time belongs to one of four observation classes:

1. **Fresh certified observation.** Its published central value is clamped to
   (d_{i,t}). Its calibration uncertainty remains available for downstream
   variance and diagnostics.
2. **Recent carried observation.** The last actual calibration remains within
   an explicit observation lease. Its state is propagated causally by the
   observation filter; it is not a new observation.
3. **Soft stale observation.** It is too old or too weak to be a hard boundary,
   but it may enter as a finite-precision unary constraint.
4. **Unobserved.** It receives only directed predictions, harmonic support,
   temporal state, or the transported prior.

Freshness alone is not sufficient for hard clamping. Boundary certification
should also require acceptable fit quality, quote coverage, arbitrage status,
and provenance.

### 4.3 Published clamp versus uncertainty

Clamping concerns the **central published value**:

\[
\widehat z_{i,t}=d_{i,t}\quad\text{for a certified lit node}.
\]

It does not mean that the calibration has zero statistical uncertainty. The
calibration covariance must still widen dependent dark-node bands and appear
in validation. The graph is not allowed to alter the lit central value merely
because a neighbouring relationship disagrees.

### 4.4 Observation leases

For high-frequency sources, a recent actual calibration can remain the
exogenous source state between expected updates. For example, if A normally
refreshes every minute, its (t=3) calibration may remain the causal source
state at (t=3.5).

An observation lease has:

- the calibration timestamp;
- an expected refresh interval or maximum age;
- a propagation rule for the innovation mean;
- a process variance accumulated since the observation;
- provenance proving that the state descends from an actual calibration.

A lease is not the same as saving graph output as a prior. It is a causal
prediction from the last actual observation.

A lease carries the **innovation** (z), never the absolute level: a carried
node's published mark therefore continues to move with its transported
baseline between observations. Carrying levels would silently break
transported-prior semantics (Phase-0 decision D4).

---

## 5. Running example: asynchronous A and B

### 5.1 Inputs

Consider two assets:

- A is observed at (t=0,1,2,3,4,5) with values
  (10,11,12,13,14,15);
- B is observed only at (t=0) and (t=3.5), with values (10,10);
- snapshots are produced every 0.5 time unit;
- (\beta_{B\leftarrow A}=1);
- A strongly informs B;
- B does not inform A.

For exposition, these values are shown as handle levels. In production, the
same calculation is performed on innovations relative to transported
baselines.

### 5.2 Directed relation and idiosyncratic state

Write

\[
B_t=\beta A_t+u_{B,t},
\]

where (u_B) is B's idiosyncratic residual relative to the A-driven common
component.

At (t=0),

\[
u_{B,0}=10-10=0.
\]

Therefore B follows A until B is observed again.

At (t=3.5), the causal A state is its last observed value, 13. B is observed
at 10, so

\[
\boxed{u_{B,3.5}=10-13=-3.}
\]

This update changes B's idiosyncratic state only. It cannot update A because
there is no B-to-A influence arc.

### 5.3 Persistent-residual result

With (phi_B=1), the residual stays at (-3) until another actual B
calibration changes it:

| Time | A status | A mark | B status | (u_B) | B mark |
|---:|---|---:|---|---:|---:|
| 0.0 | observed | 10 | observed | 0 | 10 |
| 0.5 | carried | 10 | dark | 0 | 10 |
| 1.0 | observed | 11 | dark | 0 | 11 |
| 1.5 | carried | 11 | dark | 0 | 11 |
| 2.0 | observed | 12 | dark | 0 | 12 |
| 2.5 | carried | 12 | dark | 0 | 12 |
| 3.0 | observed | 13 | dark | 0 | 13 |
| 3.5 | carried | 13 | observed | −3 | **10** |
| 4.0 | observed | 14 | dark | −3 | 11 |
| 4.5 | carried | 14 | dark | −3 | 11 |
| 5.0 | observed | 15 | dark | −3 | 12 |

Hence

\[
\boxed{A=(10,10,11,11,12,12,13,13,14,14,15)}
\]

and

\[
\boxed{B=(10,10,11,11,12,12,13,10,11,11,12).}
\]

This is the unique simple path consistent with beta one, causal last-tick
alignment, and a persistent observed B-specific residual.

### 5.4 Why a 10.5 mark at (t=4) needs another assumption

After B is observed at 10 against A at 13, full beta-one propagation of A's
next (+1) move gives B equal to 11. A mark of 10.5 instead requires

\[
10+\beta(14-13)=10.5,
\]

so (\beta=0.5) for that transition. But a B mark of 11.5 at (t=5) would
require

\[
10+\beta(15-13)=11.5,
\]

so (\beta=0.75). No constant beta produces both values.

The same 10.5/11.5 path could be manufactured by measuring B's residual
against an interpolated A value of 13.5 at (t=3.5). In a live system that
would use A's future (t=4) observation and violate causality. It is therefore
not an acceptable production convention.

### 5.5 Optional mean reversion

Let the residual have half-life (H_B):

\[
\phi_B(\Delta)
=
2^{-\Delta/H_B}.
\]

Then after (t=3.5),

\[
B_t=A_t-3\phi_B(t-3.5).
\]

For a conventional mean-reverting process (0\leq\phi\leq1), this implies

\[
B_4=14-3\phi_B(0.5)\geq11.
\]

Mean reversion makes B catch up to A faster; it cannot explain a value below
11. The flat marks between A observations in the running example indicate a
long residual half-life over this short horizon.

### 5.6 What the bad model would do

A memoryless symmetric graph may:

1. let B's (t=3.5) observation pull the temporarily dark A toward 10;
2. forget B's observation when B becomes dark;
3. make both A and B snap to 14 and then 15.

That produces the explicitly rejected behaviour:

\[
A=(10,10,11,11,12,12,13,10,14,14,15),
\]

\[
B=(10,10,11,11,12,12,13,10,14,14,15).
\]

The directed residual state makes this path structurally impossible.

---

## 6. Directed dynamic propagation

### 6.1 One source and one target

For source (j) and target (i), define

\[
z_{i,t}=\beta_{ij}z_{j,t}+u_{i,t}+\epsilon_{ij,t},
\]

with

\[
\epsilon_{ij,t}\sim\mathcal N(0,\tau_{ij}^2),
\qquad
\tau_{ij}^2=1/p_{ij}.
\]

The target-specific residual follows

\[
u_{i,t+\Delta}
=
\phi_i(\Delta)u_{i,t}+\omega_{i,t},
\]

\[
\omega_{i,t}\sim\mathcal N(0,Q_i(\Delta)).
\]

The roles are separate:

- (\beta_{ij}) determines the mean response to a source move;
- (p_{ij}) determines relation noise;
- (phi_i) determines residual persistence;
- (Q_i) determines how uncertain the residual becomes while unobserved.

### 6.2 Dark-target prediction

Suppose the source state has mean (m_j) and variance (V_j), and the
predicted residual has mean (m_u) and variance (V_u). Then

\[
\boxed{m_i^{D}=\beta_{ij}m_j+m_u}
\]

and

\[
\boxed{
V_i^{D}
=
\beta_{ij}^{2}V_j+V_u+1/p_{ij}.
}
\]

For one source, lowering (p_{ij}) widens the target distribution without
mechanically attenuating the mean. This preserves the original
precision-message contract.

### 6.3 Target observation update

When target (i) is actually calibrated, define the residual measurement

\[
e_{i,t}
=
d_{i,t}-\beta_{ij}m_{j,t}.
\]

Under a hard residual update,

\[
m_{u,i,t}^{+}=e_{i,t}.
\]

Under a finite-quality Kalman update,

\[
K_i
=
\frac{V_{u,i}^{-}}
{V_{u,i}^{-}+V_{\mathrm{obs},i}+\beta_{ij}^{2}V_j+1/p_{ij}},
\]

\[
m_{u,i}^{+}
=
m_{u,i}^{-}+K_i(e_{i}-m_{u,i}^{-}).
\]

The published target central value can still be clamped to (d_i) while the
persistent residual state uses the finite-quality update. The running example
uses the hard residual update because the intended subsequent mark must retain
the full observed (-3) dislocation.

Most importantly, this update is **cut** at the source: it never changes
(m_j). A surprising B observation becomes a B residual surprise, not an A
revision.

### 6.4 Multiple sources

Let (P(i)) be the parents of target (i). Define configured weights

\[
w_{ij}
=
\frac{p_{ij}}{q_i},
\qquad
q_i=\sum_{j\in P(i)}p_{ij}.
\]

The systematic target predictor is

\[
s_{i,t}
=
\sum_{j\in P(i)}w_{ij}\beta_{ij}z_{j,t}.
\]

The target equation is

\[
z_{i,t}=s_{i,t}+u_{i,t}+\epsilon_{i,t},
\qquad
\operatorname{Var}(\epsilon_{i,t})=1/q_i
\]

under the initial independent-message convention.

Let (a_i) contain coefficients (w_{ij}\beta_{ij}) and let
(Sigma_{P(i)}) be the parent covariance. Then

\[
\operatorname{Var}(s_i)
=
a_i^\top\Sigma_{P(i)}a_i.
\]

Thus

\[
\boxed{
V_i^D
=
a_i^\top\Sigma_{P(i)}a_i
+V_{u,i}
+1/q_i.
}
\]

The full parent covariance matters. Two parents carrying the same market
factor are not independent merely because two arcs are configured.

### 6.5 Directed topology

The first production version should require the directed influence graph to
be a DAG after contracting reciprocal harmonic blocks. A topological solve
then gives:

- exact one-way semantics;
- no spectral-radius condition;
- transparent attribution;
- deterministic evaluation order;
- no ambiguous simultaneous source/target update.

A future research mode may permit a directed strongly connected component:

\[
z_F=A_{FF}z_F+A_{FS}z_S+u+\epsilon,
\]

\[
(I-A_{FF})z_F=A_{FS}z_S+u+\epsilon.
\]

That mode requires invertibility, gain and condition-number rails, and an
explicit cycle policy. It is not required for v1.

### 6.6 Attribution

For a DAG, target means are linear in observed ancestor innovations and
stored residual states. Attribution should report separately:

- contribution from each actual observed ancestor;
- contribution from the target's persistent residual;
- relation beta and configured precision;
- temporal attenuation (phi);
- direct versus indirect ancestry;
- covariance overlap among sources.

Attribution is by independent observation/state source, not by graph path.

---

## 7. Reciprocal beta-harmonic completion

Directed influence is not the right semantic for every relation. Calendar
interpolation and some symmetric peer relations are naturally expressed as
reciprocal compatibility.

### 7.1 Relation-factor operator

For reciprocal relation (e=(i,j)), choose a canonical orientation and define

\[
r_e(z)=z_i-\beta_{ij}z_j.
\]

With edge precision (p_e),

\[
\mathcal E_H(z)
=
\sum_e p_e r_e(z)^2,
\]

\[
Q_H
=
B_\beta^\top P B_\beta.
\]

This is PSD for arbitrary real beta. For harmonic product semantics, however,
positive and cycle-consistent betas are preferred.

### 7.2 Ordinary harmonic coordinates

If there are positive node scales (g_i) satisfying

\[
\beta_{ij}=g_i/g_j,
\]

write

\[
z_i=g_i y_i.
\]

Then

\[
z_i-\beta_{ij}z_j
=
g_i(y_i-y_j),
\]

and

\[
p_e(z_i-\beta_{ij}z_j)^2
=
c_e(y_i-y_j)^2,
\qquad
c_e=p_eg_i^2.
\]

Therefore (y) is an ordinary weighted harmonic field.

For calendar beta

\[
\beta_{i\leftarrow j}
=
(T_j/T_i)^{\alpha_T},
\]

one may take

\[
g_i=T_i^{-\alpha_T},
\qquad
y_i=T_i^{\alpha_T}z_i.
\]

At (alpha_T=1), the graph harmonically extends (Tz).

### 7.3 Exact Dirichlet boundary

Let (S) contain fresh certified observations and (F) the free nodes. With
zero screening anchor,

\[
\widehat z_S=d_S,
\]

\[
\boxed{
\widehat z_F
=
-Q_{H,FF}^{-1}Q_{H,FS}d_S.
}
\]

For beta one, this is the classical weighted graph Dirichlet problem. A global
rescaling of all relation precisions leaves the mean unchanged and rescales
conditional covariance, exactly separating mean interpolation from confidence.

### 7.4 Uncertain but clamped boundary

Hard central values should not force zero downstream uncertainty. Let (V_S)
be the covariance of the lit innovations and partition the factor matrix into
free and boundary columns:

\[
B_\beta=[B_F\;B_S].
\]

The edge residual covariance after incorporating boundary uncertainty is

\[
\boxed{
\Omega
=
P^{-1}+B_SV_SB_S^\top.
}
\]

This construction has two important effects:

1. a finite-quality boundary widens dark-node uncertainty;
2. shared uncertainty from one boundary is correlated across all of its
   incident factors, preventing naive source duplication.

### 7.5 Directed predictions as soft unary anchors

The directed dynamic layer emits target predictive distributions

\[
z_i\sim\mathcal N(m_i^D,V_i^D).
\]

These enter the harmonic layer as unary information, not as pairwise edges to
their parents. Consequently the harmonic solve may combine a directed target
prediction with calendar or reciprocal peer support, but it cannot update the
source that produced the directed prediction.

Predictions that share parents are correlated, so a diagonal (R_D) overstates
joint confidence across targets; see Phase-0 decision D6 for the v1 treatment
and the Phase-3 adjudication of a low-rank joint (R_D).

Let (H_D) select directed predictions, (R_D=(V_D)^{-1}), and let (H_G,R_G,g)
represent optional stale or ghost soft observations. With an optional screening
anchor (D_\kappa), define

\[
A
=
B_F^\top\Omega^{-1}B_F
+D_{\kappa,F}
+H_D^\top R_DH_D
+H_G^\top R_GH_G
+Q_{\mathrm{optional},FF},
\]

\[
b
=
-B_F^\top\Omega^{-1}B_Sd_S
+H_D^\top R_Dm_D
+H_G^\top R_Gg.
\]

The free-node posterior is

\[
\boxed{
\widehat z_F=A^{-1}b,
\qquad
\Sigma_{FF}=A^{-1}.
}
\]

This is the proposed layered dynamic-harmonic solve.

### 7.6 Screening is not harmonic amplitude

A nonzero innovation anchor

\[
D_\kappa=\operatorname{diag}(\kappa_i)
\]

connects nodes to a zero-innovation ground. The result is a screened or killed
Laplacian, not a pure harmonic extension.

The product should therefore distinguish:

- `harmonic`: (kappa=0);
- `screened_harmonic`: (kappa>0).

An amplitude preset may derive (kappa), but the UI should describe the
result as retention or shrink-to-prior behaviour. It is topology-dependent and
can compound over graph distance.

### 7.7 Components without support

A component is supported if it contains at least one of:

- a fresh Dirichlet boundary;
- a valid carried observation state;
- a soft stale or ghost observation;
- a directed predictive anchor derived from an observation-supported DAG.

A component with none of these remains at zero innovation, hence at the
transported prior. It receives broad uncertainty and a
`no_active_observation_path` diagnostic.

---

## 8. Second running example: calendar completion

Consider one ticker with maturities

\[
T=(0.25,0.5,1.0),
\]

and suppose only 6M is freshly observed with innovation (+1). With
(alpha_T=1),

\[
\beta_{3M\leftarrow6M}=2,
\qquad
\beta_{1Y\leftarrow6M}=0.5.
\]

On the adjacent calendar tree, the exact harmonic extension is

\[
\widehat z_{3M}=2,
\qquad
\widehat z_{1Y}=0.5.
\]

Equivalently,

\[
T_{3M}\widehat z_{3M}
=
T_{6M}d_{6M}
=
T_{1Y}\widehat z_{1Y}
=
0.5.
\]

This is an appropriate reciprocal relation: observing a neighbouring expiry
can legitimately inform the missing expiry in either direction after maturity
normalisation. No causal source-to-target claim is needed.

If a directed cross-asset predictor also supplies a soft 3M prediction, the
harmonic layer combines that unary prediction with the calendar boundary using
their stated covariances.

---

## 9. Model modes and relation ownership

### 9.1 Proposed solver modes

| Mode | Lit central values | Temporal memory | Directionality | Intended use |
|---|---|---|---|---|
| `legacy_soft_joint` | finite-precision joint posterior | none beyond stored priors | symmetric posterior feedback | byte-identical legacy and benchmark control |
| `harmonic_dirichlet` | fresh certified nodes clamped | observation leases only | reciprocal relations | calendar and symmetric interpolation |
| `directed_state` | fresh certified nodes clamped | persistent idiosyncratic state | exact DAG source→target | liquid-to-illiquid propagation |
| `layered_dynamic_harmonic` | fresh certified nodes clamped | persistent directed state | directed predictions plus reciprocal completion | recommended production candidate |
| `screened_layered` | as above | as above | as above | explicitly shrunk/stress policy |

The current generic name `hybrid` is too broad for these semantics. Every mode
should state which operators can change a mean and which can only change
uncertainty.

### 9.2 Recommended relation semantics by class

| Relation class | Default semantic |
|---|---|
| Same-ticker calendar | `reciprocal_harmonic` |
| Truly symmetric same-sector peer | `reciprocal_harmonic` |
| Broad index → constituent | `directed_state` |
| Sector ETF → constituent | `directed_state` |
| Liquid ADR/primary → illiquid listing | `directed_state` |
| Custom | explicit declaration required |

No persisted row should silently change from reciprocal to directed semantics.

### 9.3 Proposed relation schema

Each relation should declare its semantics:

```text
relationSemantics:
  reciprocal_harmonic
  directed_state

sourceTicker
sourceExpiry
targetTicker
targetExpiry
betaAtmVol
betaSkew
betaCurv
relationPrecision
relationClass

# directed_state only
residualHalfLife
residualProcessVariance
parentGroup

# reciprocal_harmonic only
canonicalOrientation
precisionRule
```

Global settings should include:

```text
solverMode
boundaryPolicy
clampMaxAge
clampMinPrecision
observationLeasePolicy
screeningPolicy
cycleBetaTolerance
directedCyclePolicy       # reject in v1
```

---

## 10. Causal snapshot workflow

At valuation time (t), the production solve should execute in the following
order.

### Step 1: resolve transported baselines

Resolve (h^0_{i,t}) using the existing provenance hierarchy. No graph output
may be selected as a baseline source.

### Step 2: ingest actual calibrations

For every calibration whose timestamp is no later than (t):

- calculate handles and innovation (d_{i,t});
- calculate observation covariance and quality diagnostics;
- classify it as hard boundary, carried state, soft observation, or rejected;
- never use a calibration from a later timestamp, even in an offline replay.

### Step 3: predict temporal states

Advance observation leases and idiosyncratic residual states from their last
actual-update timestamps to (t):

\[
m_u^-=\phi(\Delta)m_u^+,
\qquad
V_u^-=\phi(\Delta)^2V_u^++Q(\Delta).
\]

### Step 4: update residuals from target observations

Traverse the directed graph in topological order. When a target is actually
observed, compare it with its causal parent predictor at the same timestamp and
update the target residual state. Do not update the parents.

### Step 5: produce directed dark-node predictions

For dark targets, combine parent states and the predicted idiosyncratic
residual to obtain ((m_i^D,V_i^D)). Record source attribution and residual
provenance.

### Step 6: solve reciprocal harmonic components

Use fresh observations as exact central boundaries, directed predictions as
soft unary anchors, and reciprocal relation factors as the harmonic geometry.
Solve each observation-supported component in information form.

### Step 7: reconstruct smiles

Add innovations to transported baselines, retarget the three handles into the
ATM-orthogonal LQD chart, refit the selected smile family if required, and run
the existing density, wing, and calendar diagnostics.

### Step 8: publish and persist only authorised state

Publish marks and diagnostics. Persist only:

- actual calibration records;
- observation-filter states descended from actual calibrations;
- idiosyncratic residual states updated by actual target observations;
- timestamps, covariances, relation-config version, and provenance.

Do not persist a graph-predicted handle as though it were an observed
calibration or transported-prior node.

---

## 11. Common-epoch and baseline alignment

The dynamic residual must be defined from aligned innovations:

\[
u_{i,t}
=
d_{i,t}
-
\sum_{j\in P(i)}w_{ij}\beta_{ij}z_{j,t}^{\mathrm{causal}}.
\]

The source states must represent information available at or before the target
observation timestamp. Future interpolation is forbidden.

Because (d_i=h_i^{\mathrm{cal}}-h_i^0), changing transported baselines between
timestamps can otherwise masquerade as an idiosyncratic move. Production must
therefore store enough information to re-express the source and target on a
common epoch:

- calibration timestamp and valuation timestamp;
- baseline identifier and baseline handles;
- forward/spot transport metadata;
- the actual observed handles;
- the derived innovation and residual;
- relation-config version.

If a clean common-epoch conversion cannot be constructed, the residual should
receive wider process variance or be rejected rather than silently treated as
exact.

This is not an optional refinement. The asynchronous A/B example shows that
absolute-level ghosts are the wrong state object: the persistent quantity is
the aligned target residual after removing the contemporaneous systematic
prediction.

---

## 12. Uncertainty and diagnostics

### 12.1 Variance decomposition

For a directed prediction, report at least:

\[
V_i^D
=
\underbrace{a_i^\top\Sigma_Pa_i}_{\text{source uncertainty}}
+
\underbrace{1/q_i}_{\text{relation noise}}
+
\underbrace{V_{u,i}}_{\text{idiosyncratic-state uncertainty}}.
\]

After harmonic completion, add:

- harmonic path uncertainty;
- dark-node transported-baseline uncertainty exactly once;
- the existing idiosyncratic smile-band floor;
- reconstruction pushforward uncertainty.

### 12.2 Residual-surprise diagnostic

When a target observation conflicts with its directed prediction, calculate

\[
\chi_{i,t}
=
\frac{d_{i,t}-m_{i,t}^{D}}
{\sqrt{V_{\mathrm{obs},i}+V_{i,t}^{D}}}.
\]

A large (|\chi|) means one of:

- a genuine idiosyncratic shock;
- a stale or bad quote;
- a broken beta or relation class;
- a timestamp-alignment problem;
- a regime change.

The model should preserve the observation if it passes certification, while
surfacing the surprise prominently rather than contaminating the source.

### 12.3 Required node diagnostics

For every node and handle, expose:

- transported baseline and provenance;
- current observation class and age;
- hard boundary, carried, soft, directed-predicted, or harmonic-only status;
- parent systematic prediction;
- persistent residual mean, variance, age, and half-life;
- directed relation precision and beta;
- harmonic incident stiffness, not misleadingly `incomingPrecision`;
- posterior marginal variance;
- source, relation, residual, baseline, and reconstruction variance components;
- top observed-source contributions;
- `no_active_observation_path`, cycle, stale-state, and residual-surprise flags.

### 12.4 Relation correlation

The independent-message rule (q_i=\sum p_{ij}) is only an initial
conditional approximation. Indexes, ETFs, and peers can share the same market
factor. Production safeguards include:

- full or low-rank parent-state covariance;
- relation-cluster precision discounts;
- effective-source-count caps;
- block residual covariance learned from held-out data;
- attribution by original observation, not by graph path.

---

## 13. Computational considerations

### 13.1 Directed state pass

After contracting reciprocal harmonic blocks, a DAG directed pass is

\[
O(E_D)
\]

per handle for means. Diagonal or small-factor covariance propagation is also
linear in edge count. Full dense source covariance is unnecessary for most
universes; a market/sector low-rank representation is preferable.

### 13.2 Harmonic solve

The harmonic precision has sparse form

\[
Q_H=B_\beta^\top P B_\beta.
\]

The free-node system is symmetric positive definite when every free node in a
component is grounded by a hard boundary, a positive unary prediction, or an
explicit screen. Use sparse Cholesky where available; conjugate gradients with
an incomplete-Cholesky or algebraic-multigrid preconditioner are alternatives
at larger scale.

Never emulate hard boundaries with extremely large precision. Eliminate their
rows and columns exactly.

### 13.3 Boundary uncertainty

The edge-space matrix

\[
\Omega=P^{-1}+B_SV_SB_S^\top
\]

need not be densely inverted. Apply the Woodbury identity:

\[
\Omega^{-1}
=
P
-
PB_S
\left(V_S^{-1}+B_S^\top PB_S\right)^{-1}
B_S^\top P.
\]

At current graph sizes, a dense reference implementation is acceptable for
golden tests. Production should preserve the sparse-plus-low-rank structure.

### 13.4 Factor reuse

Topology and beta usually change less frequently than observations. Cache:

- directed topological order;
- reciprocal factor sparsity pattern;
- component partition;
- symbolic Cholesky analysis;
- node-scale or beta-gauge solution;
- relation-cluster covariance structure.

Per snapshot, update timestamps, temporal means/variances, boundaries, unary
precisions, and right-hand sides. Reuse numerical factorisations when the
precision matrix is unchanged; otherwise use diagonal/rank-update paths or
refactor.

### 13.5 State storage

Per node and handle, persistent dynamic state needs only:

```text
residualMean
residualVariance
lastActualObservationTime
lastStateUpdateTime
sourceObservationIds
relationConfigVersion
baselineIds
quality/provenance flags
```

This is (O(NH)) state, excluding optional covariance factors.

### 13.6 Numerical and semantic guards

Required guards include:

- reject directed cycles in v1;
- require positive finite precisions;
- cap or review extreme betas;
- require positive, cycle-consistent beta for strict harmonic mode;
- Cholesky/PD verification of every free component;
- posterior variance positivity;
- condition-number and maximum-gain rails;
- timestamp monotonicity and no-future-observation checks;
- relation-config version matching before residual reuse;
- explicit state invalidation or rebasing after topology/beta changes.

---

## 14. Calibration and extrapolation considerations

### 14.1 Why the model fits volatility marking

The framework is well suited to volatility calibration because it separates
four effects that desks routinely reason about separately:

1. **Transported prior:** what the smile would be without new information.
2. **Systematic innovation:** the move explained by liquid related markets.
3. **Idiosyncratic innovation:** the last actually observed target-specific
   dislocation.
4. **Cross-sectional completion:** smooth interpolation across maturities or
   reciprocal peers.

The decomposition is explainable, causal in time, and compatible with the
existing three-handle reconstruction.

### 14.2 Main risks

#### Stale bad observations

A persistent residual can preserve a stale or erroneous print. Mitigations:

- hard-boundary certification;
- robust residual clipping or heavy-tailed updates;
- residual half-lives by liquidity and handle;
- process variance that grows with age;
- maximum state age and provenance checks;
- surprise diagnostics and manual invalidation.

#### Regime-changing beta

An index/name beta can change during earnings, macro shocks, or dispersion
events. Mitigations:

- relation-specific rolling validation;
- beta uncertainty in the target variance;
- event-aware half-lives or state resets;
- fallback to wider uncertainty rather than forced mean attenuation;
- separate ATM, skew, and curvature beta.

#### Baseline misalignment

Persisting raw innovations across changing baselines can double-count common
moves. Common-epoch metadata and residual rebasing are mandatory.

#### Overconfidence from correlated parents

The full parent covariance or a conservative factor approximation must replace
naive precision addition where sources overlap.

#### Hard clamping of weak calibrations

The word `lit` must mean certified enough to own a boundary. User selection
alone is insufficient.

#### Arbitrage across reconstructed slices

The graph produces handle targets, not a joint calendar-arbitrage proof.
Existing reconstruction, publish-time calendar checks, and Local-Vol projection
remain required.

### 14.3 When not to use directed residual persistence

Do not create a persistent directed residual when:

- the proposed source/target relation has no held-out predictive skill;
- the target observation cannot be aligned causally with its sources;
- the relation configuration is changing too frequently to define a stable
  residual;
- the target is better treated as a reciprocal peer;
- an event has invalidated the previous residual state;
- the target has no recent actual calibration from which to estimate the
  residual.

In these cases, use harmonic completion, a soft prior-only prediction, or the
transported prior with broad uncertainty.

---

## 15. Golden acceptance contracts

These tests are product semantics, not generic numerical checks.

### 15.1 Asynchronous A/B sequence

The Section-5 fixture must reproduce exactly:

\[
A=(10,10,11,11,12,12,13,13,14,14,15),
\]

\[
B=(10,10,11,11,12,12,13,10,11,11,12)
\]

under beta one and persistent residual.

### 15.2 Zero reverse influence

With A-to-B configured and no B-to-A arc,

\[
\frac{\partial\widehat z_A(t)}
{\partial d_B(s)}=0
\]

for every (s\leq t), including times when A is carried rather than freshly
observed.

### 15.3 Exact target observation

At a certified B observation time,

\[
\widehat z_B=d_B
\]

regardless of relation precision or source disagreement.

### 15.4 Persistent common move

After observing target residual (u), a subsequent source innovation
(Delta z_A) changes the dark target mean by

\[
\Delta\widehat z_B
=
\beta\Delta z_A
\]

when (phi=1).

### 15.5 Residual half-life

With no new target observation,

\[
u(t+H)=u(t)/2
\]

and the process variance matches the chosen OU/random-walk transition.

### 15.6 Precision separation

For one source, changing relation precision changes predictive variance but
not the beta-transmitted mean. For multiple sources, precision changes their
configured relative weights and total conditional uncertainty.

### 15.7 No look-ahead

The (t=3.5) A state in the running example is 13, never an interpolation
using the future (t=4) observation at 14. Online and timestamp-truncated
offline replay must agree exactly.

### 15.8 Actual-observation-only state update

Removing every later actual B observation must not cause graph-predicted B
marks to be re-ingested as residual observations or saved priors.

### 15.9 Harmonic calendar identity

The 3M/6M/1Y example of Section 8 must give (2,1,0.5) under alpha one,
and the normalized field (Tz) must be constant.

### 15.10 Reciprocal versus directed discriminator

For the unit path with boundaries (L=1,R=0), the reciprocal harmonic mode
must give interior values (2/3,1/3). A separately configured directed
cascade fixture must give its directed row solution. The two semantics must
never share one ambiguous expected result.

### 15.11 Boundary uncertainty

As source observation variance increases, the lit central value remains
unchanged while dependent dark-node bands widen and conflicting-source weights
adjust according to the configured uncertain-boundary policy.

### 15.12 Disconnected component

A component with no hard, carried, soft, or directed observation support must
remain at zero innovation with broad uncertainty and
`no_active_observation_path`.

### 15.13 Configuration rebase

Changing beta, parent weights, or relation semantics invalidates or explicitly
rebases every affected persistent residual. Reusing a residual under a new
definition is forbidden.

### 15.14 Legacy identity

`legacy_soft_joint` must remain byte-identical at current defaults.

---

## 16. Historical validation plan

The framework should be compared against:

1. transported prior only;
2. current smooth-field graph;
3. current precision-message soft joint posterior;
4. exact reciprocal harmonic Dirichlet;
5. directed state only;
6. layered dynamic harmonic;
7. screened layered variants;
8. nearest-expiry and same-name calendar baselines.

### 16.1 Required replay designs

- full node leave-one-out;
- asynchronous timestamp replay at the finest stored observation frequency;
- liquid-source/illiquid-target split;
- target lit-to-dark transitions;
- isolated idiosyncratic target shocks;
- source shocks with target dark;
- conflicting and correlated multi-source cases;
- calendar-only and cross-asset-only ablations;
- relation-config changes and state invalidation;
- calm, stressed systematic, and dispersion regimes.

Every replay must be timestamp causal. A calibration with timestamp after the
scored snapshot is unavailable, even if it belongs to the same historical day.

### 16.2 Metrics

Report:

- ATM, skew, curvature, and full-smile RMS;
- error immediately before and after target observations;
- discontinuity at lit-to-dark transitions;
- persistence accuracy by elapsed time since target observation;
- source-to-target impulse response by horizon;
- reverse-leakage sensitivity;
- 50%, 80%, and 95% band coverage;
- standardized residuals by source count and path depth;
- relation-surprise distribution;
- calibration by residual age and configured half-life;
- results by asset type, relation class, maturity, and regime;
- reconstructed butterfly and calendar diagnostics.

### 16.3 Adoption gate

The layered mode should become a product default only if it:

1. eliminates measurable reverse leakage by construction;
2. materially reduces lit-to-dark discontinuities;
3. improves dark-target RMS relative to transported prior and static graphs;
4. preserves or improves stressed-regime behaviour;
5. produces calibrated bands after source, residual, and baseline uncertainty;
6. passes timestamp-causal replay with no look-ahead;
7. does not degrade smile or calendar-arbitrage diagnostics;
8. yields stable residual half-lives and betas outside the training sample.

---

## 17. Implementation roadmap

### Phase 0 — Ratify semantics and fixtures

**Goal:** resolve modelling contracts before code changes.

1. Ratify the reciprocal-relation versus directed-influence distinction.
2. Ratify the asynchronous A/B sequence and causal timestamp convention.
3. Choose hard versus finite-quality residual updates for each observation
   class.
4. Define observation leases and certified-clamp eligibility.
5. Define residual state in common-epoch innovation coordinates.
6. Correct the reverse-precision identity in the existing framework.
7. Rename incident relation stiffness so it is not presented as incoming-only
   precision.
8. Add all Section-15 golden fixtures before implementation.

**Exit gate:** every example has one agreed expected mean, variance, state
update, and attribution.

#### Phase-0 decision record (2026-07-20)

- **D1 — notation (APPLIED).** One amplitude symbol: `beta`. The apparent
  `eta`/`beta` split was an encoding mangle (a `\b` escape swallowed as a
  backspace byte); repaired at byte level in this document.
- **D2 — residual transition family (RATIFIED 2026-07-20).** `phi(Delta) = 2^(-Delta/H)`.
  Finite half-life: OU form `Q(Delta) = V_inf (1 - phi(Delta)^2)`; infinite
  half-life: random walk `Q(Delta) = q Delta`. Both are semigroup-consistent
  (two steps of `Delta/2` compose exactly to one step of `Delta`), which the
  goldens verify.
- **D3 — residual update by class (RATIFIED 2026-07-20).** Hard residual update for
  **certified** target observations (required by the Section-5 boxed
  sequence); finite-quality Kalman update for **soft stale** observations.
- **D4 — leases carry the innovation (RATIFIED 2026-07-20).** Stated in Section 4.4: a
  carried node propagates `z`, so its mark keeps moving with the transported
  baseline.
- **D5 — asynchrony attribution convention (RATIFIED 2026-07-20).** At a certified
  target observation, the full aligned residual is attributed to the target's
  idiosyncratic state in the mean; the source-state ambiguity (the source may
  have moved unobserved since its last print) is acknowledged in variance via
  the `beta^2 V_j` innovation term. Production is **filter-only** in v1 — no
  retrospective smoothing of residuals when the source's next print reveals
  the common move; an end-of-day smoother is a possible later mode and must
  never be the live-marking path (golden 15.7 forbids it).
- **D6 — cross-target anchor correlation (OPEN, adjudicated in Phase 3).**
  Directed predictions sharing parents are correlated; v1 may ship a diagonal
  `R_D` with a documented conservative variance treatment, but the low-rank
  joint `R_D` built from shared-parent covariance is the Phase-3 candidate
  and must be adjudicated before the layered mode can claim calibrated bands.
- **D7 — ghost unification (RECORDED).** For a node with no directed parents
  the systematic predictor is zero and the residual state degenerates to
  `u = d`: the previously drafted "aged ghost observation"
  (`graph_precision_message_framework.md` Section 29.3) is exactly this
  special case and is superseded — no separate mechanism.
- **D8 — reverse-precision identity (APPLIED).** With the forward amplitude
  `beta`, the identity is `p_rev = p_fwd * beta^2` (Section 2.3); the
  `p_fwd / beta^2` form holds only in terms of the reverse amplitude
  `1/beta`. The precision-message framework Section 7.6 and the
  `volfit/graph/message.py` module header mixed the two; corrected. The
  assembly code was always correct (`p` to the receiver, `p*beta^2` to the
  informer).
- **D9 — golden fixtures locked (APPLIED).**
  `backend/tests/fixtures/graph_dynamic_golden.json` +
  `backend/tests/test_graph_dynamic_golden.py`: every Section-15 contract
  with a numeric expectation, verified by self-contained brute-force
  references (causal state machine, dense Dirichlet/GLS solves) with no
  imports from `volfit.graph`. Implementation phases must reproduce these
  numbers THROUGH the production modules against the same fixture file
  (the message-arc P0 pattern). The fixtures encode the D2–D5 proposed
  defaults and are the ratification instrument: ratifying Phase 0 ratifies
  these numbers.

### Phase 1 — Temporal observation and residual state

**Goal:** add causal memory independently of graph topology.

Suggested module:

```text
backend/volfit/graph/temporal_state.py
```

Work:

1. Timestamped actual-observation state and lease policy.
2. Residual-state record: mean, variance, timestamp, provenance, baseline IDs,
   and config version.
3. OU/random-walk transition with per-handle half-life and process variance.
4. Hard and Kalman residual-update paths.
5. No-future-observation and monotonic-time guards.
6. Actual-observation-only persistence guard.
7. Schema migration from any ATM-only history used solely for band floors.

**Exit gate:** the A and B local state machines reproduce the running example
without invoking a graph solve.

### Phase 2 — Directed prediction engine

**Goal:** implement true source-to-target semantics.

Suggested module:

```text
backend/volfit/graph/directed_state.py
```

Work:

1. Directed relation schema and per-handle beta/precision.
2. DAG validation and topological ordering.
3. Single- and multi-parent systematic predictor.
4. Parent covariance and effective-source diagnostics.
5. Target residual observation updates with no parent feedback.
6. Predictive unary distributions ((m_i^D,V_i^D)).
7. Exact source and residual attribution.
8. Residual-surprise diagnostics.

**Exit gate:** zero reverse sensitivity is exact, and directed predictions match
independent state-space references.

### Phase 3 — Dirichlet harmonic solver

**Goal:** turn the reciprocal operator into an explicit boundary-value solver.

Suggested additions:

```text
backend/volfit/graph/harmonic_posterior.py
```

Work:

1. Exact hard-boundary partition, never large-precision emulation.
2. Positive/gauge-consistent beta validation for strict harmonic mode.
3. Uncertain-boundary covariance through (Omega).
4. Directed predictions and stale observations as unary factors.
5. Supported-component detection using every active information source.
6. Screened-harmonic option with explicit ground interpretation.
7. Hybrid support detection that includes optional precision off-diagonals.
8. Marginal variance and attribution adapter for reconstruction consumers.

**Exit gate:** harmonic, uncertain-boundary, mixed-unary, and disconnected
goldens match direct Gaussian references.

### Phase 4 — Production orchestration

**Goal:** implement the Section-10 event order.

Work:

1. Timestamp-causal observation feed, including the existing `age_days` wiring.
2. Common-epoch residual construction.
3. Relation-config versioning and state rebase/invalidation.
4. New solver and relation-semantics fields in request and persisted config.
5. Directed pass followed by harmonic completion.
6. Existing reconstruction, band, attribution, and LOO integration.
7. Prior-save guard rejecting extrapolated outputs.
8. Byte-identical legacy mode.

**Exit gate:** one end-to-end asynchronous replay reproduces Section 5 and
returns reconstructed, validated smiles.

### Phase 5 — Historical adjudication

**Goal:** choose defaults from timestamp-causal held-out evidence.

Work:

1. Add dynamic modes to the frozen benchmark harness.
2. Sweep residual half-lives and process variances by relation class and handle.
3. Sweep hard versus finite-quality residual updates.
4. Compare reciprocal, directed, layered, and screened variants.
5. Add transition discontinuity, impulse-response, reverse-leakage, and coverage
   metrics.
6. Publish a decision table against Section 16.3.

**Exit gate:** the production candidate, relation-class defaults, and temporal
parameters are selected from reproducible artifacts.

### Phase 6 — Diagnostics and editor

**Goal:** make semantics visible before users activate them.

Work:

1. Relation editor requires `reciprocal_harmonic` or `directed_state`.
2. Directed arrows show beta, precision, residual half-life, and current state.
3. Reciprocal relations show canonical orientation, reverse precision, and
   harmonic coordinate.
4. Node inspector shows systematic prediction versus persistent residual.
5. Timeline preview reproduces the A/B fixture interactively.
6. Warnings for cycle, stale residual, config mismatch, no support, and large
   residual surprise.
7. Draft/active lifecycle includes policies, not relation rows alone.

**Exit gate:** a user can explain every mark as baseline + systematic move +
idiosyncratic residual + harmonic adjustment.

### Phase 7 — Sparse and streaming production

**Goal:** meet the full-universe latency budget.

Work:

1. Sparse factor assembly and cached symbolic factorisation.
2. Diagonal/rank updates for changing unary precisions.
3. Low-rank source covariance and Woodbury boundary updates.
4. Selected inverse or probing for marginal variances.
5. Incremental state updates on new observations rather than full rebuilds.
6. Latency, memory, and numerical rails at 1k, 10k, and target universe sizes.

**Exit gate:** streaming and batch replay agree within tolerance without changing
golden means or materially changing reported variances.

---

## 18. Recommended product decision

The dynamic directed model is a good fit for volatility calibration and
extrapolation provided it is not presented as a universal replacement for
Laplacian inference.

The recommended division of labour is:

```text
transported prior
    provides the no-new-information baseline

directed state model
    propagates liquid-to-illiquid systematic innovations
    preserves actually observed target-specific residuals
    enforces zero reverse influence

reciprocal harmonic model
    interpolates calendar and genuinely symmetric relations
    combines directed predictions with other cross-sectional support

reconstruction and calibration gates
    return arbitrage-checked smiles and surfaces
```

The A/B example should be treated as a certification fixture, not merely an
illustration. It distinguishes the proposed model from both a symmetric
pairwise graph and an absolute-level ghost heuristic.

The preferred post-(t=3.5) B marks are

\[
\boxed{10,11,11,12,}
\]

not (10,10.5,10.5,11.5), under beta one and causal last-tick alignment. If a
desk wants a different path, it should be expressed through an explicit beta,
residual transition, or observation-alignment rule rather than through an
implicit interaction between precision and stale observations.

The resulting framework is more than a graph smoother: it is a causal,
stateful marking system whose reciprocal interpolation layer remains a proper
Gaussian/Laplacian solve. That separation is the main design improvement.
