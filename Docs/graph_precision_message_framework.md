# Precision-Message Graph Propagation

## Current state, target framework, and implementation roadmap

**Status:** design specification  
**Date:** 2026-07-18  
**Locked decision:** the default calendar amplitude exponent is
`alphaT = 1.0`.

---

## 1. Executive summary

Vol-Fitter currently extrapolates dark smiles with a Bayesian graph prior on
the innovation field

\[
z_i = x_i^{\mathrm{today}} - x_i^{\mathrm{transported\ prior}},
\]

where node \(i\) is one smile \((\text{ticker},T)\). The production workflow is
already correctly anchored:

```text
transported prior
    -> lit calibration innovation
    -> graph posterior increment
    -> reconstructed dark smile
    -> quote comparison and validation
```

The current graph operator is primarily a **global smooth-field regularizer**.
It asks for an increment field that is small and compatible with a
row-normalized directed neighbour rule. This is mathematically coherent and
empirically useful, especially for neighbour-supported calendar interpolation,
but it does not give sufficiently direct control over the desired desk
semantics:

1. a signal should be able to cross an edge at full configured amplitude;
2. confidence should decrease independently of that amplitude;
3. incoming signals at a receiver should be precision-weighted and averaged;
4. independent incoming precisions should add;
5. uncertainty should accumulate along a multi-edge path without mechanically
   attenuating the mean;
6. cross-maturity and cross-asset behaviour should be readable directly from
   edge configuration.

The proposed primary propagation operator is a **precision-message Gaussian
operator**. For receiver \(i\), informer \(j\), edge precision \(p_{ij}\), and
handle-specific amplitude \(\beta_{ij}\), define

\[
q_i = \sum_j p_{ij},
\qquad
K_{ij}^{p} = \frac{p_{ij}}{q_i},
\qquad
M = I-K^p\!\circ B.
\]

The propagation precision is

\[
\boxed{
Q_{\mathrm{msg}} = M^\top D_q M,
\qquad
D_q=\operatorname{diag}(q_i).
}
\]

Locally, this means

\[
z_i\mid\{z_j\}
\sim
\mathcal N\!\left(
\frac{\sum_j p_{ij}\beta_{ij}z_j}{\sum_jp_{ij}},
\frac{1}{\sum_jp_{ij}}
\right).
\]

This gives the target behaviour exactly when the informing nodes are known:

- one incoming message has mean \(\beta z\), regardless of its precision;
- two equal-precision messages are averaged, not added;
- their precision is \(2p\), not \(p\);
- lower precision widens the posterior without shrinking the transported mean;
- on a chain, betas multiply while transport variances accumulate.

This framework is still Bayesian. The difference is not Bayes versus
non-Bayes; it is **global graph smoothness versus explicit information
routing**. The current smooth-field operator should be retained as an optional
legacy or hybrid regularizer, while the precision-message operator becomes a
separately selectable propagation mode with explicit semantics and golden
tests.

---

## 2. Scope and non-goals

This document specifies:

- the current graph workflow and mathematical operator;
- the gap between the current operator and the desired propagation semantics;
- the precision-message model;
- maturity amplitude and precision-decay conventions;
- treatment of competing, correlated, and multi-hop signals;
- integration with transported priors, handle reconstruction, uncertainty,
  attribution, and validation;
- an implementation and migration roadmap.

This document does **not** propose:

- propagating absolute smile levels instead of innovations;
- replacing the three-handle carrier in v1;
- propagating native Local-Vol parameters;
- treating every graph path as an independent observation;
- removing posterior uncertainty or prior provenance;
- silently changing the meaning of existing persisted edge weights.

---

## 3. Present production workflow

### 3.1 Selected universe

The production graph is built over the user-selected lit and dark nodes only.
A node is

\[
i=(\text{ticker},\text{expiry}).
\]

- **Lit:** selected and eligible to contribute a current calibration
  observation.
- **Dark:** selected as an extrapolation target. Any quotes or fits on a dark
  node are excluded from propagation and may be used only after the solve for
  validation.
- **Unselected:** excluded from both the node set and all graph paths.

The production builder currently lives in
`backend/volfit/api/graph_universe.py`.

### 3.2 Propagated carrier

Each node carries three model-agnostic ATM smile handles:

\[
h_i=(\sigma_{0,i},s_{0,i},c_{0,i}),
\]

where

- \(\sigma_0\) is ATM implied volatility;
- \(s_0=\partial_k\sigma(0)\) is ATM skew in log-moneyness;
- \(c_0=\partial_{kk}\sigma(0)\) is ATM curvature.

ATM volatility, rather than total variance, is used for the level coordinate so
that it remains comparable across expiries. The three coordinates are solved as
independent graph fields with handle-specific hyperparameters and betas.

### 3.3 Transported-prior baseline

Every node receives a synchronous current-forward baseline from the following
hierarchy:

1. exact-expiry active prior transported to the current forward;
2. nearest-expiry prior on the same ticker, transported with lower confidence;
3. today's fit as a weak bootstrap baseline;
4. a flat ATM fallback for diagnostics or last resort.

The graph propagates only the innovation relative to this baseline. For a lit
node \(s\),

\[
d_s
=
h_s^{\mathrm{calibrated}}
-
h_s^{\mathrm{transported\ prior}}.
\]

For a dark node, the inferred absolute posterior handle is

\[
h_i^+
=
h_i^{\mathrm{transported\ prior}}
+
\widehat z_i.
\]

This prior anchoring remains unchanged under the new operator.

### 3.4 Current topology

The auto-lattice currently contains:

- bidirectional calendar edges between consecutive selected expiries within a
  ticker, with default raw weight 10;
- bidirectional cross-ticker edges between nodes sharing the exact same expiry,
  with default raw weight 2.

The production API also supports a persisted explicit edge graph and ticker
block rules. Explicit edges override the auto-lattice over the same selected
node set.

The current auto-lattice is generic: every selected ticker pair sharing an
expiry is connected. A production economic topology should normally be defined
through the edge matrix, for example index-to-name, ETF-to-constituent,
same-sector peer, and calendar relationships.

### 3.5 Current graph construction

Raw nonnegative weights are row-normalized:

\[
K_{ij}=\frac{w_{ij}}{\sum_\ell w_{i\ell}}.
\]

The current convention in the graph engine is:

\[
w_{ij}>0
\quad\Longleftrightarrow\quad
\text{node }j\text{ informs receiver }i.
\]

The engine then computes a stationary mass \(\pi\), reversible conductances,
and the directed residual

\[
L_{\mathrm{dir}}^\beta
=
(I-K\circ B)^\top
\Pi
(I-K\circ B),
\qquad
\Pi=\operatorname{diag}(\pi).
\]

Weight and beta already have separate intended meanings:

- \(w_{ij}\): relative trust or relevance;
- \(\beta_{ij}\): amplitude of the receiver's predicted move per unit informer
  move, per handle and per direction.

### 3.6 Current increment prior

For one handle, the current innovation prior is

\[
z\sim\mathcal N(0,Q_\Delta^{-1}),
\]

with

\[
Q_\Delta
=
D_\kappa
+
\eta L_{\mathrm{dir}}^\beta
+
\lambda(A_\rho+\nu I)^{-1}.
\]

The terms mean:

- \(D_\kappa\): local zero-innovation stiffness;
- \(\eta L_{\mathrm{dir}}^\beta\): directed neighbour compatibility;
- \(\lambda(A_\rho+\nu I)^{-1}\): optional unbalanced-OT tangent penalty.

The shipped default has \(\lambda=0\). Therefore the default production engine
is currently a directed Bayesian smooth-field model, with the OT term available
but inactive.

### 3.7 Current posterior update

Let \(S\) be the observed lit nodes and \(R\) their observation precision. The
current implementation conditions in covariance form:

\[
\Sigma^-=Q_\Delta^{-1}+P_0^{-1},
\]

\[
G
=
\Sigma^-_{\cdot S}
\left(\Sigma^-_{SS}+R^{-1}\right)^{-1},
\]

\[
\widehat z=Gd,
\]

\[
\Sigma^+
=
\Sigma^-
-
\Sigma^-_{\cdot S}
\left(\Sigma^-_{SS}+R^{-1}\right)^{-1}
\Sigma^-_{S\cdot}.
\]

The displayed posterior precision is the marginal precision

\[
\pi_i^+=\frac{1}{\Sigma^+_{ii}},
\]

not the diagonal of the full precision matrix.

### 3.8 Reconstruction and validation

Posterior handles are retargeted into the node's ATM-orthogonal LQD chart,
leaving the remaining shape modes unchanged. The reconstructed LQD target is
then optionally refit into the selected SVI or Multi-Core Sigmoid family. Local
Vol consumes the graph smile as a projection target for a full surface
calibration.

The production workflow already provides:

- prior-to-posterior node summaries;
- marginal credible bands;
- full node-smile reconstruction on demand;
- quote overlays and residual metrics;
- exact attribution by observed lit source;
- leave-one-node-out validation;
- active observation selection.

These layers remain reusable under the new operator.

---

## 4. Strengths of the current graph-prior regularizer

The existing framework should be preserved because it has genuine strengths:

1. **Correct innovation semantics.** No-change-from-prior is the baseline.
2. **A proper global Gaussian field.** All graph paths and source correlations
   enter one simultaneous solve.
3. **Safe directed beta operator.** The residual is PSD for arbitrary real
   beta.
4. **Marginal uncertainty.** The engine reports the uncertainty of each node,
   not a misleading conditional precision.
5. **No naive path double-counting.** The solution is a covariance-aware global
   posterior rather than a sequence of independent local averages.
6. **Exact lit-source attribution.** Each target shift decomposes over observed
   innovations.
7. **Arbitrage-safe per-slice reconstruction.** Propagated handles map back to a
   genuine smile density.
8. **Measured historical skill.** The graph beats transported-prior baselines in
   neighbour-supported and stressed systematic regimes.

The new framework is not a rejection of these foundations. It changes the
meaning of the directed propagation term so that its local behaviour is more
controllable and desk-readable.

---

## 5. Why the present operator does not meet the new requirements

### 5.1 Row normalization removes absolute incoming information

Under the current kernel,

\[
(p,p)\quad\text{and}\quad(100p,100p)
\]

both normalize to

\[
(1/2,1/2).
\]

The relative average is retained, but the fact that the second pair carries
100 times more total information is discarded. The residual confidence is then
controlled by global \(\eta\pi_i\), not by the incoming sum.

Consequently, the current operator cannot naturally guarantee

\[
p+p=2p
\]

at the receiving node.

### 5.2 Mean strength and confidence are coupled

Increasing \(\eta\) makes the graph relation more influential, but also makes
the prior field tighter. It does not naturally produce

> full mean transmission with deliberately wide uncertainty.

### 5.3 The zero-innovation anchor shrinks valid messages

In a one-source scalar reduction, a receiver with anchor precision \(\kappa_i\)
and incoming precision \(p\) has mean approximately

\[
\widehat z_i
=
\frac{p}{\kappa_i+p}\,\beta_{ij}z_j.
\]

Even when beta is correct, \(\kappa_i>0\) attenuates the message. Increasing
\(p\) removes the attenuation only by simultaneously raising confidence.

### 5.4 Stationary mass obscures edge semantics

The factor \(\pi_i\) is useful for a stationary directed smoothness geometry,
but it does not have the direct meaning

> total precision of the messages received by node \(i\).

It can also make one-way or reducible topologies difficult to reason about.

### 5.5 Configuration-only tuning is insufficient

The existing engine can approximate stronger propagation through:

- larger `etaScale`;
- smaller `kappaScale`;
- larger relative edge weights;
- larger betas.

But this does not provide an exact contract for amplitude, precision addition,
or distance-based confidence decay. A new operator is warranted.

---

## 6. Target semantics

The precision-message mode should satisfy the following invariants.

### Invariant 1: full configured amplitude

With one effectively known informer and no competing innovation anchor, a
receiver's posterior mean is

\[
\widehat z_i=\beta_{ij}z_j
\]

for every positive edge precision \(p_{ij}\).

### Invariant 2: confidence is independent of amplitude

Reducing \(p_{ij}\) widens uncertainty but does not reduce the conditional mean
\(\beta_{ij}z_j\).

### Invariant 3: incoming signals are averaged

For multiple known informers,

\[
\widehat z_i
=
\frac{\sum_jp_{ij}\beta_{ij}z_j}
     {\sum_jp_{ij}}.
\]

Signals are not summed as levels.

### Invariant 4: independent information adds

The receiver's conditional precision is

\[
q_i=\sum_jp_{ij}.
\]

This is a conditional precision. The final posterior marginal precision may be
lower when informers are uncertain or correlated.

### Invariant 5: path variance accumulates

Along a chain, betas multiply in the mean while edge noise and source
uncertainty accumulate in variance.

### Invariant 6: no lit path means no invented signal

A disconnected dark component remains at zero innovation, hence at its
transported prior, with explicitly broad uncertainty and a `no_lit_path`
diagnostic.

### Invariant 7: one source is not counted once per path

Multiple graph routes carrying the same original information must remain
correlated. The global solve must not treat them as independent observations.

---

## 7. Precision-message operator

### 7.1 Edge definition

A directed precision-message edge is defined from **informer** \(j\) to
**receiver** \(i\) by:

- conditional edge precision \(p_{ij}>0\);
- handle-specific amplitude \(\beta_{ij,h}\);
- optional provenance or relation class;
- optional distance-rule parameters used to derive \(p_{ij}\) and beta.

The semantic relation for one handle is

\[
z_i
\approx
\beta_{ij}z_j
\]

with conditional relation variance \(1/p_{ij}\).

### 7.2 Precision-weighted receiver rule

For each receiver, define

\[
q_i=\sum_jp_{ij},
\]

and, when \(q_i>0\),

\[
K^p_{ij}=\frac{p_{ij}}{q_i}.
\]

The receiver prediction is

\[
m_i
=
\sum_jK^p_{ij}\beta_{ij}z_j
=
\frac{\sum_jp_{ij}\beta_{ij}z_j}{q_i}.
\]

Its conditional residual is

\[
r_i=z_i-m_i.
\]

The residual energy is

\[
\mathcal E_{\mathrm{msg}}(z)
=
\sum_{i:q_i>0}q_i r_i^2.
\]

### 7.3 Matrix form and PSD property

Let

\[
M=I-K^p\!\circ B,
\qquad
D_q=\operatorname{diag}(q_i).
\]

Then

\[
\boxed{
Q_{\mathrm{msg}}=M^\top D_qM.
}
\]

For every vector \(z\),

\[
z^\top Q_{\mathrm{msg}}z
=
\|Mz\|_{D_q}^2
\ge0.
\]

Therefore the new operator is symmetric positive semidefinite for arbitrary
real betas, just like the current directed residual.

### 7.4 Receiver-row factor interpretation

The receiver row contributes the Gaussian factor

\[
z_i\mid\{z_j\}
\sim
\mathcal N\!\left(
\frac{\sum_jp_{ij}\beta_{ij}z_j}{q_i},
\frac{1}{q_i}
\right).
\]

This is the direct desk interpretation of the new mode. It is also the exact
receiver conditional in the canonical one-way fixture where the informers are
clamped and no other factor contains the receiver.

In the full graph, node \(i\) may also appear as an informer in other receiver
rows. Those additional factors legitimately contribute information about
\(z_i\). Consequently, the formula above defines the semantics and conditional
precision of **this receiver row**, while the final node conditional and
marginal precision come from the global posterior. This distinction is
especially important for bidirectional edges and cycles.

### 7.5 Conditional versus marginal precision

Three distinct quantities must remain visible:

1. **Edge precision \(p_{ij}\):** confidence in the relation
   \(z_i\approx\beta_{ij}z_j\).
2. **Receiver conditional precision \(q_i=\sum_jp_{ij}\):** precision of the
   receiver conditional on its informers.
3. **Posterior marginal precision \(1/\operatorname{Var}(z_i\mid d_S)\):** final
   reported confidence after accounting for source uncertainty, source
   correlation, cycles, and all observations.

Only in the idealized case of known independent informers does final receiver
precision reduce exactly to \(q_i\).

---

## 8. Maturity amplitude

### 8.1 Locked default

For a calendar edge whose source maturity is \(T_j\) and receiver maturity is
\(T_i\), define

\[
\boxed{
\beta_{i\leftarrow j}^{\mathrm{calendar}}
=
\left(\frac{T_j}{T_i}\right)^{\alpha_T},
\qquad
\alpha_T=1.0\ \text{by default}.
}
\]

The exponent remains configurable, but `1.0` is the product default.

Interpretations include:

| `alphaT` | Meaning |
|---:|---|
| 0 | equal absolute-vol innovation at every maturity |
| 0.5 | square-root maturity scaling |
| **1.0** | inverse-maturity scaling; locked default |

### 8.2 Required three-expiry example

Let

\[
T_{3M}=0.25,
\qquad
T_{6M}=0.5,
\qquad
T_{1Y}=1.0.
\]

Suppose 6M is lit with

\[
z_{6M}=+1.0\ \text{vol point}.
\]

Then

\[
\beta_{3M\leftarrow6M}
=
\frac{0.5}{0.25}
=2,
\]

and

\[
\beta_{1Y\leftarrow6M}
=
\frac{0.5}{1.0}
=0.5.
\]

With no competing signals or zero-innovation anchor,

\[
\boxed{
\widehat z_{3M}=+2.0,
\qquad
\widehat z_{1Y}=+0.5.
}
\]

Their confidence is controlled by their edge precisions, not by these betas.

### 8.3 Reciprocal calendar consistency

If both directions represent the same maturity-scaling relation, their betas
should be reciprocal:

\[
\beta_{i\leftarrow j}\beta_{j\leftarrow i}=1.
\]

With `alphaT = 1`,

\[
\frac{T_j}{T_i}\frac{T_i}{T_j}=1.
\]

This avoids contradictory gain cycles such as both directions claiming a 2x
amplification.

---

## 9. Calendar precision and maturity distance

### 9.1 Separate amplitude from confidence

Calendar beta answers

> how large should the receiver's innovation be?

Calendar precision answers

> how reliable is this maturity-transfer relationship?

They must remain separate fields and separate tuning problems.

### 9.2 Initial default family

The initial configurable calendar precision family should include the proposed
inverse-square-root time-gap rule:

\[
\boxed{
p_{ij}^{\mathrm{calendar}}
=
\frac{p_{\mathrm{calendar}}}
{\epsilon_T+\sqrt{|T_i-T_j|/1\mathrm{Y}}}.
}
\]

Here:

- \(p_{\mathrm{calendar}}\) is the global calendar precision scale;
- \(\epsilon_T>0\) caps the precision of near-identical expiries;
- maturities are measured in years;
- the rule applies to precision only, never beta.

The following alternatives should be available to the benchmark ablation:

1. constant precision per calendar edge;
2. inverse power of raw time gap;
3. exponential decay in log-maturity distance;
4. user-entered per-edge precision;
5. learned, shrunk precision by maturity bucket.

An alternative log-distance family is

\[
p_{ij}
=
p_0\exp\!\left(
-\frac{|\log(T_i/T_j)|}{\ell_T}
\right).
\]

The inverse-square-root gap rule is the initial product default; the benchmark
must decide whether another family is materially better calibrated.

### 9.3 Edge variance interpretation

It is often cleaner to think in variance:

\[
\tau_{ij}^2=1/p_{ij}.
\]

An edge carries

\[
z_i=\beta_{ij}z_j+\epsilon_{ij},
\qquad
\epsilon_{ij}\sim\mathcal N(0,\tau_{ij}^2).
\]

This makes multi-hop uncertainty accumulation transparent.

---

## 10. Competing signals

### 10.1 Equal-precision cancellation

Suppose 3M and 1Y are lit, 6M is dark, both receiver betas are one, and

\[
z_{3M}=-1,
\qquad
z_{1Y}=+1,
\qquad
p_{6M,3M}=p_{6M,1Y}=p.
\]

Then

\[
\widehat z_{6M}
=
\frac{p(-1)+p(+1)}{2p}
=0,
\]

with conditional precision

\[
q_{6M}=2p.
\]

Therefore

\[
\boxed{
\widehat z_{6M}=0,
\qquad
q_{6M}=2p.
}
\]

### 10.2 Unequal precision

If the 3M signal has precision \(3p\) and the 1Y signal has precision \(p\),

\[
\widehat z_{6M}
=
\frac{3p(-1)+p(+1)}{4p}
=-0.5,
\]

and

\[
q_{6M}=4p.
\]

### 10.3 Beta-adjusted competition

Signals are averaged **after** mapping them into receiver units:

\[
\widehat z_i
=
\frac{\sum_jp_{ij}\beta_{ij}z_j}{\sum_jp_{ij}}.
\]

Therefore equal raw innovations do not necessarily cancel when betas differ.

With the default `alphaT = 1`, mapping from 3M and 1Y into 6M gives

\[
\beta_{6M\leftarrow3M}=0.5,
\qquad
\beta_{6M\leftarrow1Y}=2.
\]

Then raw signals \(-1\) and \(+1\), with equal precisions, map to \(-0.5\)
and \(+2\), giving

\[
\widehat z_{6M}=+0.75.
\]

This is not a defect: the incoming signals express different receiver-unit
predictions. If equal absolute-vol signals must cancel regardless of maturity,
that relation must use beta one or propagate a separately normalized calendar
coordinate.

---

## 11. Cross-asset propagation

### 11.1 Two-source average

Let assets A and B be lit and C be dark. Suppose C receives beta-one messages
with precisions \(p_A\) and \(p_B\). Then

\[
\widehat z_C
=
\frac{p_Az_A+p_Bz_B}{p_A+p_B},
\]

with conditional precision

\[
q_C=p_A+p_B.
\]

For equal precisions,

\[
\boxed{
\widehat z_C=\frac{z_A+z_B}{2},
\qquad
q_C=2p.
}
\]

### 11.2 Cross-asset beta

With distinct betas,

\[
\widehat z_C
=
\frac{
p_A\beta_{C\leftarrow A}z_A
+
p_B\beta_{C\leftarrow B}z_B
}{p_A+p_B}.
\]

Betas should be handle-specific because ATM level, skew, and curvature need not
share the same cross-asset response.

### 11.3 Cross-asset precision

Cross-asset precision should be configurable by relation class, for example:

- broad-index to constituent;
- sector ETF to constituent;
- same-sector peer;
- index to ETF;
- custom pair;
- learned and shrunk pair-specific relation.

Amplitude and precision must never be conflated:

- beta describes expected move size;
- precision describes confidence in that relation.

### 11.4 Correlated informers

The rule \(p_A+p_B\) is exact only when A and B provide conditionally independent
information after the model's common factors are accounted for. SPY and QQQ, for
example, are highly correlated sources. Treating both as independent may
overstate confidence.

Mitigations include:

1. a common market-factor node;
2. a source covariance matrix;
3. precision discounts by source cluster;
4. learned residual precision after removing common factors;
5. conservative effective-source-count caps.

The global Gaussian solve should remain the authority for marginal confidence.

---

## 12. Source uncertainty and effective message precision

A lit innovation is not perfectly known. Let informer \(j\) have posterior
mean \(\mu_j\) and variance \(v_j\). An edge relation is

\[
z_i=\beta_{ij}z_j+\epsilon_{ij},
\qquad
\epsilon_{ij}\sim\mathcal N(0,1/p_{ij}).
\]

The arriving message has

\[
m_{j\to i}=\beta_{ij}\mu_j,
\]

and variance

\[
v_{j\to i}
=
\beta_{ij}^2v_j
+
\frac{1}{p_{ij}}.
\]

Its effective precision is

\[
\boxed{
p_{j\to i}^{\mathrm{eff}}
=
\frac{1}
{\beta_{ij}^2v_j+1/p_{ij}}.
}
\]

Thus a low-quality lit calibration cannot become high-confidence merely because
its outgoing edge has high configured precision. In the global solve this
source uncertainty is handled through covariance; the formula is useful for UI
explanation and local golden tests.

---

## 13. Multi-hop propagation

Consider

\[
A\longrightarrow B\longrightarrow C,
\]

with

\[
z_B=\beta_1z_A+\epsilon_1,
\qquad
z_C=\beta_2z_B+\epsilon_2,
\]

and

\[
\operatorname{Var}(\epsilon_k)=1/p_k.
\]

Then

\[
E[z_C]
=
\beta_2\beta_1E[z_A],
\]

while

\[
\boxed{
\operatorname{Var}(z_C)
=
(\beta_2\beta_1)^2\operatorname{Var}(z_A)
+
\frac{\beta_2^2}{p_1}
+
\frac{1}{p_2}.
}
\]

This is the central desired result:

- mean amplitude travels through the product of betas;
- source uncertainty is transported;
- each edge adds relation variance;
- precision becomes dimmer as the path becomes longer.

No additional mean haircut is required.

---

## 14. Innovation anchor and disconnected components

### 14.1 Why a finite anchor causes shrinkage

If the new operator is combined with a zero-innovation anchor

\[
D_\kappa=\operatorname{diag}(\kappa_i),
\]

then a receiver's conditional mean becomes

\[
\widehat z_i
=
\frac{\sum_jp_{ij}\beta_{ij}z_j}
{\kappa_i+\sum_jp_{ij}}.
\]

This attenuates every valid message.

### 14.2 Default in precision-message mode

For a dark node connected to at least one lit-informed component, the default
economic innovation-anchor precision should be

\[
\boxed{\kappa_i^{\mathrm{msg}}=0.}
\]

A tiny numerical jitter may be used internally only when necessary and must not
be presented as economic confidence.

An explicit `innovationAnchorPrecision` knob may be exposed for hybrid or
stress modes, but its default is zero in precision-message mode.

### 14.3 Components without lit observations

The graph should be solved by connected component. For a component with no lit
observation:

- posterior innovation mean is zero;
- the absolute mean remains the transported prior;
- the result is tagged `no_lit_path`;
- uncertainty comes from baseline provenance, an explicit disconnected
  innovation variance, and the idiosyncratic band floor;
- no artificial precision is created merely to make the linear system proper.

This is more honest than anchoring all dark nodes strongly to zero innovation
and thereby weakening connected propagation.

---

## 15. Posterior formulation

### 15.1 Precision-form solve

The precision-message operator is most naturally solved in information form.
Let \(H\) select lit observations, \(R_d\) be their innovation precision, and
\(d\) the observed innovations. For a connected component with lit data,

\[
Q^+
=
Q_{\mathrm{msg}}
+
D_{\mathrm{anchor}}
+
H^\top R_dH
+
Q_{\mathrm{optional}},
\]

where `Q_optional` may contain an explicitly enabled legacy smooth-field or OT
regularizer.

The information vector is

\[
b^+
=
H^\top R_dd
+
D_{\mathrm{anchor}}m_{\mathrm{anchor}}.
\]

The posterior mean is

\[
\boxed{
\widehat z=(Q^+)^{-1}b^+.
}

The posterior covariance is

\[
\Sigma^+=(Q^+)^{-1},
\]

or its selected columns and diagonal in a sparse implementation.

### 15.2 Innovation observation precision

An innovation is the difference between a current calibration and a transported
prior. If their independent precisions are \(r_s^{\mathrm{cal}}\) and
\(p_s^0\), then a clean first-order innovation precision is

\[
\boxed{
r_s^d
=
\left(
\frac{1}{r_s^{\mathrm{cal}}}
+
\frac{1}{p_s^0}
\right)^{-1}.
}

This prevents an uncertain transported prior from producing an artificially
precise source innovation.

### 15.3 Absolute-handle uncertainty

The mean reconstruction remains

\[
h_i^+=h_i^0+\widehat z_i.
\]

If the transported baseline is treated as independently uncertain, an initial
band rule is

\[
\operatorname{Var}(h_i^+)
=
\operatorname{Var}(z_i\mid d)
+
1/p_i^0,
\]

followed by the existing idiosyncratic floor. Correlation between baseline
error and innovations should be reviewed explicitly before locking this formula
for historical priors derived from overlapping data.

### 15.4 Optional hybrid regularization

The legacy operator may be added explicitly:

\[
Q^+
=
Q_{\mathrm{msg}}
+
\eta_{\mathrm{smooth}}L_{\mathrm{dir}}^\beta
+
\lambda(A_\rho+\nu I)^{-1}
+
H^\top R_dH.
\]

However, any nonzero optional regularizer can change the exact full-force
examples. Therefore:

- `precision_messages` mode defaults both optional terms off;
- `smooth_field` preserves the current implementation;
- `hybrid` requires explicit opt-in and separate validation.

---

## 16. Cycles, repeated paths, and information conservation

### 16.1 Naive message iteration is not acceptable

The same SPY innovation may reach AAPL through several routes:

- SPY 3M -> AAPL 3M;
- SPY 3M -> NVDA 3M -> AAPL 3M;
- SPY 3M -> SPY 6M -> AAPL 6M -> AAPL 3M.

These are not three independent observations. They are correlated routes
carrying the same original information. Adding their apparent precisions would
make the target falsely overconfident.

### 16.2 Global Gaussian inference

The primary implementation must assemble one global sparse Gaussian system per
handle and solve it jointly. This preserves covariance between routes and
prevents naïve precision multiplication.

### 16.3 Directed semantics in a Gaussian posterior

The factor is directed in its prediction relation through the ordered beta
\(\beta_{i\leftarrow j}\), but the resulting posterior precision is symmetric.
Therefore observing a receiver can update an uncertain informer through Bayes.
This is appropriate for a joint posterior.

Where strictly one-way causal propagation is required, the graph must be a DAG
or the source must be explicitly clamped. A UI arrow alone cannot create
one-way posterior conditioning.

### 16.4 Cycle consistency diagnostics

The solver should report cycles whose beta product is far from one:

\[
\prod_{(j\to i)\in\mathcal C}\beta_{i\leftarrow j}.
\]

Large amplification or contraction around a closed cycle signals an internally
inconsistent edge configuration and can cause compromises, shrinkage, or
numerical ill-conditioning.

---

## 17. Attribution and explainability

The current attribution decomposes a posterior target shift over observed lit
innovations. That capability should be retained.

For target \(i\),

\[
\widehat z_i=\sum_{s\in S}G_{is}d_s.
\]

The UI should show, per lit source:

- raw source innovation;
- source innovation precision;
- effective global gain \(G_{is}\);
- contribution \(G_{is}d_s\);
- direct edge beta when applicable;
- whether the contribution arrived only through indirect graph paths.

Additionally, precision-message mode should expose:

- receiver conditional incoming precision \(q_i\);
- final marginal posterior precision;
- the gap between the two due to source uncertainty and correlation;
- `no_lit_path` and cycle-consistency diagnostics;
- the configured maturity beta exponent and precision-decay rule.

Attribution must remain by independent observed source, not by graph path,
because path-level contributions are correlated and generally non-unique.

---

## 18. API and data-model proposal

### 18.1 Propagation mode

Add an explicit solver mode:

```text
propagationMode:
  smooth_field         # current implementation, byte-identical
  precision_messages   # new primary information-routing operator
  hybrid               # explicit combination, not default
```

No existing request should change behaviour until the migration decision is
explicitly made.

### 18.2 Edge schema

Do not overload the existing `weight` field. Add explicit message semantics:

```text
sourceTicker
sourceExpiry
targetTicker
targetExpiry
messagePrecision
betaAtmVol
betaSkew
betaCurv
relationClass
precisionRule        # explicit | calendar_distance | learned
```

Recommended relation classes include:

```text
calendar
broad_index
sector_etf
sector_peer
custom
```

### 18.3 Direction naming migration

The current graph engine stores a row relation in which the second endpoint
informs the first, while parts of the schema and UI label `from -> to` as
source-to-target. Symmetric topologies hide this inconsistency.

The new schema must use unambiguous names:

```text
source/informer -> target/receiver
```

The migration must:

1. document the actual semantics of every persisted legacy edge;
2. convert old rows without reversing economic meaning;
3. update arrows and matrix labels;
4. add a one-way-edge integration test from UI payload to posterior effect.

### 18.4 Global settings

Proposed new settings:

```text
messagePropagationEnabled
propagationMode
calendarBetaExponent         # default 1.0
calendarPrecisionScale
calendarPrecisionDecay       # default inverse_sqrt_time_gap
calendarPrecisionEpsilon
crossAssetPrecisionScale
innovationAnchorPrecision    # default 0 in message mode
cycleBetaTolerance
```

Per-edge configuration overrides all global relation defaults.

### 18.5 Persistence and versioning

Message-edge rules must be persisted with:

- schema version;
- creation/update time;
- actor or source;
- learned/configured/manual provenance;
- beta and precision calibration window where relevant;
- benchmark-pack version used to approve the rule.

Legacy smooth-field edges must continue to round-trip without reinterpretation.

---

## 19. Backend module proposal

The implementation should be additive and keep current modules golden.

Suggested modules:

```text
backend/volfit/graph/message.py
    MessageEdge
    build_message_operator
    receiver_precisions
    calendar_beta
    calendar_message_precision

backend/volfit/graph/message_posterior.py
    precision-form component solve
    marginal variance / selected inverse path
    source attribution

backend/volfit/api/graph_message.py
    production request assembly
    edge-rule expansion
    source innovation precision
    diagnostics
```

Reusable existing layers:

```text
api/graph_universe.py       selected lit/dark universe
api/graph_nodes.py          transported-prior hierarchy
api/graph_extrapolation.py  calibration feed and orchestration seam
api/graph_reconstruct.py    full-smile reconstruction and quote comparison
api/graph_band.py           functional posterior band
graph/idio.py               idiosyncratic ATM band floor
graph/select.py             active observation selection, after covariance seam
```

The existing `graph/prior.py` and `graph/posterior.py` should remain the
byte-identical implementation of `smooth_field` mode.

---

## 20. Frontend proposal

The Graph workspace should make the distinction visible.

### 20.1 Mode control

Expose:

- `Smooth field`;
- `Precision messages`;
- `Hybrid` only behind an advanced control until validated.

### 20.2 Edge matrix

Each directed edge should display separately:

- precision \(p\);
- ATM beta;
- skew beta;
- curvature beta;
- relation class;
- inherited versus explicit value.

For calendar blocks, show:

- `alphaT = 1.0` by default;
- the resulting directional beta for each expiry pair;
- the distance-derived precision;
- the reciprocal reverse beta.

### 20.3 Receiver diagnostics

For a selected dark node, show:

- transported-prior handles;
- posterior innovation and handles;
- conditional incoming precision \(q_i\);
- marginal posterior precision;
- top lit-source contributions;
- source innovations and their effective precisions;
- posterior credible band;
- no-lit-path or inconsistent-cycle warnings.

### 20.4 Scenario preview

The editor should provide a deterministic local preview before saving an edge
rule, including the three canonical examples in this document.

---

## 21. Golden acceptance tests

The following tests are product contracts, not merely numerical smoke tests.
The local averaging contracts use directed incoming rows only, with lit sources
clamped or given effectively infinite observation precision. Separate
integration tests cover the additional information created by explicitly
configured reverse rows and cycles.

### 21.1 Full calendar transmission

Given

\[
T=(0.25,0.5,1.0),
\qquad
z_{6M}=+1,
\qquad
\alpha_T=1,
\]

with 3M and 1Y dark and no other messages:

\[
\widehat z_{3M}=+2,
\qquad
\widehat z_{1Y}=+0.5.
\]

Changing edge precision must change posterior SD but not these conditional
means.

### 21.2 Equal competing calendar signals

With beta one for the test relation,

\[
z_{3M}=-1,
\qquad
z_{1Y}=+1,
\qquad
p_3=p_{12}=p,
\]

the dark 6M node must have

\[
\widehat z_{6M}=0,
\qquad
q_{6M}=2p.
\]

### 21.3 Unequal competing precision

With the same signals and

\[
p_3=3p,
\qquad
p_{12}=p,
\]

the receiver must have

\[
\widehat z_{6M}=-0.5,
\qquad
q_{6M}=4p.
\]

### 21.4 Cross-asset average

With A and B lit, C dark, beta one, and equal independent edge precision,

\[
\widehat z_C=\frac{z_A+z_B}{2},
\qquad
q_C=2p.
\]

### 21.5 Multi-hop variance

For a two-edge chain, verify

\[
E[z_C]=\beta_2\beta_1z_A,
\]

and

\[
\operatorname{Var}(z_C)
=
(\beta_2\beta_1)^2v_A
+
\beta_2^2/p_1
+
1/p_2.
\]

### 21.6 Finite source precision

The effective target precision must decrease when the lit source observation
precision decreases, while the high-precision-source limit recovers the exact
edge precision.

### 21.7 Disconnected component

A dark component without a lit path must:

- retain zero posterior innovation;
- stay at its transported-prior mean;
- report `no_lit_path`;
- retain broad nonzero uncertainty.

### 21.8 No path double-counting

Adding a second route from the same lit source must not increase target
precision as though an independent observation had been added. Compare the
global posterior against an exact covariance reference.

### 21.9 Reciprocal maturity beta

For every automatically generated bidirectional calendar pair,

\[
\beta_{i\leftarrow j}\beta_{j\leftarrow i}=1
\]

to numerical tolerance.

### 21.10 Legacy byte identity

`propagationMode="smooth_field"` must reproduce all existing graph means,
variances, attribution, and API payloads byte-for-byte at the current defaults.

---

## 22. Historical validation plan

The new operator must be benchmarked against the strongest existing baselines:

1. transported prior only;
2. current smooth-field graph;
3. precision-message graph;
4. optional hybrid;
5. nearest-expiry fill;
6. same-name calendar-only message graph;
7. cross-asset-only message graph.

### 22.1 Required regimes

Use the frozen benchmark regimes already present in the repository:

- October 2022 high-volatility bear;
- July 2023 calm/idiosyncratic regime;
- August 2024 spike regime.

### 22.2 Designs

Score at least:

- full leave-one-node-out;
- liquid split, with indexes/ETFs lit and single names dark;
- calendar-only holdout;
- cross-asset-only holdout;
- sparse source sets;
- conflicting-source cases.

### 22.3 Metrics

Report:

- ATM RMS skill versus transported prior;
- skew and curvature error;
- full-smile wing RMS;
- posterior standardized-residual mean and standard deviation;
- coverage of 50%, 80%, 95% bands;
- result by asset kind, maturity bucket, source count, and graph distance;
- conditional precision versus realized error;
- calibration by path length;
- sensitivity to `alphaT`, precision decay, and anchor precision.

### 22.4 Pre-registered adoption gate

Precision-message mode should become the product default only if:

1. it improves calendar holdout skill materially over the transported prior and
   current smooth-field graph;
2. it is non-degrading in stressed cross-asset dark-name cells;
3. it does not create negative calm-regime skill beyond tolerance;
4. standardized residuals remain acceptably calibrated after the existing idio
   floor;
5. full-force betas do not introduce unstable maturity or cross-asset cycles;
6. reconstructed-smile and calendar-arbitrage diagnostics do not deteriorate.

---

## 23. Implementation roadmap

### Phase 0 — Contract and fixtures

**Goal:** lock semantics before implementation.

Work:

1. Add this design document to the technical-note index.
2. Create small deterministic fixtures for the three canonical use cases.
3. Lock the informer/receiver direction convention.
4. Lock `alphaT = 1.0` as the default.
5. Define conditional edge precision versus posterior marginal precision in API
   terminology.
6. Decide the initial numeric defaults for calendar precision scale and
   `epsilonT` from dimensional sanity checks.

Exit gate:

- all golden expected means and conditional precisions are agreed before code
  is written.

### Phase 1 — Core precision-message operator

**Goal:** implement the PSD operator independently of the API.

Work:

1. Add `graph/message.py`.
2. Implement informer-to-receiver message edges.
3. Preserve raw edge precisions and receiver sums \(q_i\).
4. Build \(K^p\), per-handle beta matrices, \(M\), and
   \(Q_{\mathrm{msg}}=M^\top D_qM\).
5. Implement calendar beta with default `alphaT=1.0`.
6. Implement inverse-square-root maturity-gap precision.
7. Add PSD, reciprocal-beta, and exact local-conditional tests.

Exit gate:

- the one-source, competing-source, and cross-asset golden tests pass to
  machine precision.

### Phase 2 — Precision-form posterior

**Goal:** solve the global posterior without a forced zero-innovation anchor.

Work:

1. Add component detection and lit-observation anchoring.
2. Assemble \(Q^+\) and \(b^+\) in information form.
3. Solve posterior means and marginal variances.
4. Handle no-lit components explicitly.
5. Incorporate finite innovation precision from calibration and baseline
   uncertainty.
6. Reproduce multi-hop mean and variance identities.
7. Implement exact lit-source attribution.

Exit gate:

- global results match brute-force Gaussian references, including repeated-path
  and cycle fixtures.

### Phase 3 — Production orchestration

**Goal:** connect the new operator to the existing transported-prior workflow.

Work:

1. Add `propagationMode` to production requests and persisted defaults.
2. Reuse selected-universe and transported-prior resolution.
3. Feed real lit calibration innovations into the message posterior.
4. Reuse handle reconstruction, native-model refit, LV projection, and quote
   comparison.
5. Add source/target schema migration without changing legacy edge meaning.
6. Surface conditional and marginal precision diagnostics.

Exit gate:

- one end-to-end production request reproduces every core golden fixture and
  returns a reconstructed smile.

### Phase 4 — Edge editor and diagnostics UX

**Goal:** make the operator directly configurable and explainable.

Work:

1. Add explicit message precision to ticker and expiry matrices.
2. Display generated directional calendar betas.
3. Show the default `alphaT=1.0` control.
4. Show maturity-distance precision and inherited values.
5. Correct all edge direction arrows and labels.
6. Add receiver diagnostics and canonical scenario previews.
7. Preserve the legacy editor for smooth-field mode.

Exit gate:

- a user can configure the three canonical cases in the UI and see their exact
  expected mean and precision before saving.

### Phase 5 — Unit, integration, and migration hardening

**Goal:** prevent semantic drift.

Work:

1. Lock all golden tests in Section 21.
2. Add API round-trip and persistence tests.
3. Add one-way source-to-target UI integration tests.
4. Add malformed, reducible, disconnected, and inconsistent-cycle tests.
5. Verify `smooth_field` byte identity.
6. Add numerical conditioning and variance-positivity guards.

Exit gate:

- full backend and frontend suites are green, and legacy persisted graphs load
  without economic reversal.

### Phase 6 — Backtest adjudication

**Goal:** decide defaults from held-out evidence.

Work:

1. Add precision-message variants to the benchmark pack.
2. Run the three regimes and both full-LOO/liquid-split designs.
3. Sweep calendar precision scale, distance decay, and `epsilonT`.
4. Compare `alphaT` values `{0, 0.5, 1.0}` while retaining `1.0` as the product
   default unless the benchmark rejects it decisively.
5. Ablate cross-asset precision classes and learned betas.
6. Validate marginal uncertainty by distance and source count.
7. Publish a decision table against the pre-registered gate.

Exit gate:

- precision-message mode is activated, retained as opt-in, or rejected based on
  a reproducible benchmark artifact.

### Phase 7 — Sparse production solve

**Goal:** use the new precision-form structure at large universe scale.

Work:

1. Assemble \(Q^+\) as a sparse matrix.
2. Use sparse Cholesky or conjugate-gradient solves for means.
3. Compute observed-source attribution from selected solves.
4. Compute marginal variances with selected inverse, probing, or bounded
   approximations.
5. Add latency and memory rails for 1k, 10k, and target production universes.

Exit gate:

- the selected production universe meets the agreed latency budget without
  changing golden means or materially changing reported marginal variances.

---

## 24. Risks and safeguards

### Risk 1: amplifying noisy short-dated signals

With `alphaT = 1`, a short receiver can amplify a longer-maturity source
substantially. Wide uncertainty helps but does not make an unstable mean safe.

Safeguards:

- source-quality precision;
- beta caps with diagnostics;
- robust innovation clipping or heavy-tail follow-up;
- held-out maturity-bucket validation;
- publish-time calendar and wing checks.

### Risk 2: false confidence from correlated sources

Adding configured edge precisions assumes conditional independence locally.

Safeguards:

- global covariance solve;
- factor or cluster precision discounts;
- effective-source-count diagnostics;
- calibration by number and type of sources.

### Risk 3: cycle amplification

Inconsistent beta products can create contradictory or explosive graph
relations.

Safeguards:

- reciprocal automatic calendar betas;
- cycle-product diagnostics;
- beta caps;
- condition-number rails;
- explicit rejection of unstable learned edges.

### Risk 4: mean semantics changed by optional regularizers

Adding legacy smoothness or a zero anchor changes exact full-force results.

Safeguards:

- separate modes;
- optional terms off by default in precision-message mode;
- golden tests on each mode;
- UI display of every active precision contribution.

### Risk 5: per-slice reconstruction remains only softly calendar-consistent

Calendar message edges propagate maturity signals but do not impose a hard
cross-expiry no-arbitrage projection.

Safeguards:

- post-reconstruction calendar diagnostics;
- publish-time projection or blocking;
- LV projection for a jointly calibrated surface;
- explicit separation of graph calendar precision and calibration calendar
  penalties.

---

## 25. Decisions locked by this specification

1. The graph continues to propagate innovations, not absolute smile levels.
2. The transported prior remains the reconstruction baseline.
3. The three ATM handles remain the v1 carrier.
4. Weight/precision and beta remain separate concepts.
5. Precision-message mode uses precision-weighted averaging, not signal
   addition.
6. Incoming independent conditional precisions add.
7. Full-force propagation requires zero default economic innovation-anchor
   precision on connected dark nodes.
8. The default calendar amplitude is
   \(\beta_{i\leftarrow j}=T_j/T_i\), i.e. `alphaT = 1.0`.
9. Whenever reverse calendar relations are generated, their betas are
   reciprocal.
10. The initial default calendar precision family is inverse square root in
    maturity gap, with tunable scale and epsilon.
11. Posterior marginal precision, not conditional incoming precision, remains
    the authoritative reported confidence.
12. The global Gaussian solve remains responsible for cycles, shared paths, and
    source correlation.
13. The current smooth-field operator remains available and byte-identical.
14. Precision-message, smooth-field, and hybrid semantics are explicit modes.
15. Edge direction naming is migrated to unambiguous informer/source and
    receiver/target terminology.

---

## 26. Final product interpretation

Under the precision-message framework, a dark-node result can be explained in
plain language:

> The transported AAPL 6M prior received beta-adjusted innovations from SPY 6M,
> QQQ 6M, and AAPL 3M. Their configured relation precisions were combined, their
> predicted moves were precision-weighted rather than added, and the global
> Gaussian solve accounted for the fact that SPY and QQQ information overlaps.
> The posterior mean therefore moved by X vol points, while accumulated source
> and path uncertainty produced a marginal standard deviation of Y. Those three
> posterior handles were then retargeted into the node's arbitrage-safe smile.

That is the desired operating model:

```text
full configured signal amplitude
    + explicit edge uncertainty
    + precision-weighted competition
    + covariance-aware global inference
    + transported-prior reconstruction
```

It preserves the strongest parts of the current Bayesian graph workflow while
making cross-maturity and cross-asset propagation substantially more tunable,
potent, and explainable.
