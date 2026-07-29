# Every Edge Is a Contract

**Note 14 — graph smile-extrapolation by precision messages · lecture edition ("every edge is a contract") · converted from 14_graph_messages.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

*Graph smile-extrapolation by precision messages: amplitude by contract, confidence by measurement, and a global solve that never counts a source twice. Vol-Fitter Technical Notes, No. 14.*

> **Abstract.** The Vol-Fitter's headline differentiator is filling a mostly-dark universe of smiles — one node per $(\text{underlying},T)$ — from a handful of lit calibrations. This note is the account of how: *precision-message propagation*, a Gaussian graphical model in which every edge is a contract $z_i\approx\beta\,z_j$ at a stated relation variance, and every desk-facing behaviour is a theorem with a golden number locked by tests. A receiver inherits its informer's move at full configured amplitude regardless of confidence — amplitude and trust are separate fields of the edge (Figure 1); competing messages are precision-weighted and averaged, never added (equal opposing signals cancel to 0.00; a $3p$ source outvotes to $-0.50$); a chain multiplies amplitudes while accumulating variance, so distance costs confidence, never amplitude; and a silent neighbour costs exactly nothing — the property that dictates the operator's pairwise-factor form, since the natural alternative (averaging configured precisions row by row) dilutes a live message to 0.40 against an equal-precision dead informer. Amplitude itself splits into a locked maturity *shape* ($\alpha_T=1$) and a measured *level*: per-relation-class multipliers mechanized through a node-linked innovation anchor whose corroboration law was validated on stored benchmark rows with zero free parameters — calibrated only on the one-source transfer slope (0.391), it predicts the two-source slope 0.563 against a measured 0.561, agreement to 0.3%. The information-form posterior is the accountant: repeated routes from one source are priced jointly ($1.67/p$ where naive per-message accounting claims $1.20/p$), disconnected components honestly keep zero innovation and broad bands, and baseline uncertainty enters exactly once per node. Activation as the product default was governed by evidence, and the evidence is in: the pre-registered six-condition daily benchmark gate did *not* clear (gates 1, 4 and 6 failed, recorded verbatim in "Evidence and the gate"), yet the default flipped to precision messages on 2026-07-27 — on the intraday async replay, where the two operators finally separate and the smoothing alternative is measured nearly inert. The smoothing mode remains byte-locked beside this one (Appendix B, "The smoothing-mode alternative"), as the wire default and the explicit rollback.

## 1. A universe, mostly dark

The desk owns a universe of smiles, and on any given morning only a few of them are richly quoted. The production spine that serves every node is fixed and worth stating in one breath: each node receives a *transported prior* baseline (Note 13's saved prior, moved to today's forward under the spot-dynamics regime of Note 12, through a strict provenance hierarchy with data-derived precision tiers); each *lit* node contributes the innovation $d=\text{calibrated}-\text{transported prior}$ — a genuine market-versus-prior move, fitted in pure-market mode; the graph spreads those innovations to the dark nodes as a posterior increment field $\widehat z$ with a marginal uncertainty; and each dark node's absolute handles $h^+=h^0+\widehat z$ retarget into Note 01's arbitrage-free smile machinery, with the functional posterior band and the idiosyncratic ATM band floor carrying the uncertainty into the drawn smile. Residual dark quotes may score a reconstruction afterwards — never steer it. The carrier is the compact handle triple $(\sigma_0,s_0,\kappa_0)$ — ATM vol, skew, curvature — solved as three independent fields.

The interesting question is the middle of that spine: *by what rule do lit innovations reach dark nodes?* The desk's requirements are concrete and quotable. If a configured relation says a 6M move implies twice the move at 3M, the propagated move must be twice — exactly, regardless of how much the relation is trusted. Halving the trust must widen the receiver's band, not shrink its move. When two sources corroborate, confidence must add; when they disagree, they must vote, not sum. A signal crossing three edges must arrive at full composed amplitude with honestly wider uncertainty — distance may tax confidence, never the mean. And no configuration mistake — a silent neighbour, a duplicated route, a contradictory loop — may silently manufacture or destroy information. Precision-message propagation is the operator built so that each of these sentences is a theorem.

> **Invariants protected in this note.**
> 1. A dark node stays at its transported prior unless lit data forces a move; a component with no lit path keeps zero innovation, honestly broad bands, and a `no_lit_path` flag — no invented signal, ever.
> 2. Propagation semantics are *contracts*: amplitude is what the move should be, precision is how much the relation is trusted, and the two never mix. Every contract in "Edges as contracts", "Amplitude: shape locked, level measured" and "The accountant: the information-form posterior" is locked by a golden test.
> 3. One source is one source: however many routes carry it, the global solve prices them jointly — precision never accrues by path counting.
> 4. Every filled node reports its uncertainty, which widens with graph distance and informer uncertainty; reported confidence is always the *marginal* posterior precision, never a conditional.
> 5. The output retargets into the arbitrage-free smile machinery of Note 01; the graph never emits a raw curve.
> 6. Mode and default changes are explicit and evidence-gated: a default moves only on *recorded* held-out evidence — and the record that moves it may be a different horizon than the gate that was written, as it was here ("Evidence and the gate": the daily gate failed and is recorded verbatim; the flip rests on the intraday separation). The smoothing mode ships byte-locked beside this one (Appendix B).

**Conventions and the notation ledger.** Node indices $i,j$; the *receiver* of a relation is $i$, its *informer* $j$, and every ordered object reads "$j$ informs $i$". One time symbol $T$ (maturity, years). Innovations $z$ are in the receiving handle's units; ATM-vol units are quoted so that $0.01$ is one vol point. Subscripted $\partial$; primes never used.

| Symbol | Meaning |
|---|---|
| $z_i,\ d_s$ | innovation field; lit observations |
| $p_{ij},\ \beta_{ij}$ | edge precision; per-handle amplitude |
| $Q_{\mathrm{msg}},\ q_i$ | the factor operator; receiver conditional precision |
| $\alpha_T,\ \rho$ | amplitude shape exponent; class level |
| $\kappa_i$ | node-linked innovation anchor |
| $r^d_s,\ p^0_i$ | innovation observation precision; baseline precision |
| $Q^+,\ \Sigma^+,\ G$ | posterior information; covariance; gain |
| $g_i$ | cycle gauge potential ($\beta_{ij}=g_i/g_j$) |

*Table 1 — Every symbol in the note. $p$ is always an edge's relation precision; baseline precision is $p^0$, never bare $p$. (The smoothing appendix keeps its own two symbols, $Q_{\Delta}$ and $L_{\mathrm{dir}}$.)*

## 2. Edges as contracts

**Definition 1 (Message edge).** A directed relation from informer $j$ to receiver $i$ consists of a conditional relation precision $p_{ij}>0$, a per-handle amplitude triple $\beta_{ij}$, and a relation class (calendar, broad index, sector ETF, sector peer, custom). Its meaning is the Gaussian statement

$$
z_i=\beta_{ij}\,z_j+\epsilon_{ij},
\qquad \epsilon_{ij}\sim\mathcal N(0,\,1/p_{ij}):
$$

*amplitude says what the receiver's move should be; precision says how much the relation is trusted. They never mix.*

Each edge contributes one rank-one Gaussian factor, and the propagation operator is their sum:

**Central equation.**

$$
Q_{\mathrm{msg}}=\sum_{(j\to i)}p_{ij}\,u_{ij}u_{ij}^{\mathsf T},
\qquad
u_{ij}=e_i-\beta_{ij}e_j,
\qquad
q_i=\sum_j p_{ij}.
\tag{1}
$$

Positive semidefiniteness is immediate for arbitrary real betas (a sum of PSD rank-one terms), and the assembly is sparse by construction — each factor touches two nodes.

**Proposition 1 (Receiver conditional).** Minimizing the factor energy over $z_i$ with the informers held fixed gives

$$
z_i\mid\{z_j\}\sim\mathcal N\!\left(
\frac{\sum_jp_{ij}\beta_{ij}z_j}{q_i},\ \frac{1}{q_i}\right).
$$

Incoming messages are precision-weighted and *averaged*; independent incoming conditional precisions *add*.

*Proof.* The terms of equation (1) containing $z_i$ are $\sum_jp_{ij}(z_i-\beta_{ij}z_j)^2$; completing the square in $z_i$ gives the stated mean and variance. ∎

This is the entire desk semantics in one line, and Figure 1 shows its sharpest consequence through the production solve: on the three-expiry ladder (3M/6M/1Y, 6M lit $+1$ vol point, $\alpha_T=1$) the dark receivers land at exactly $\widehat z_{3M}=+2.00$ and $\widehat z_{1Y}=+0.50$ for *every* edge precision across three decades, while the posterior standard deviation scales as $p^{-1/2}$. Amplitude is not a function of confidence — two dials, because two fields.

> **Figure 1 — The contract (figure not included in this pack).** The contract, run through the production operator and posterior (three-expiry ladder, 6M lit $+1$ vol point). A: the dark receivers' posterior means sit at the configured amplitudes $+2$ and $+0.5$ regardless of edge precision. B: what the precision *does* control — the posterior standard deviation, falling as $p^{-1/2}$. Confidence and amplitude are separate dials because they are separate fields of the edge. *Panel A plots the posterior means of the two dark receivers (3M and 1Y) against the edge precision swept over three decades on a log axis: both traces are exactly flat, at $+2.00$ and $+0.50$ vol points, the configured $\alpha_T=1$ amplitudes. Panel B plots the same sweep's posterior standard deviations, which fall along the $p^{-1/2}$ line. The quantitative takeaway: the mean never moves with precision; only the band does.*

### 2.1 Why factors, not averages: the dead informer

There is a natural-looking alternative assembly one should examine before trusting equation (1): normalize each receiver's incoming precisions into weights $K^p_{ij}=p_{ij}/q_i$ and charge the receiver for deviating from its precision-weighted forecast, $q_i\,\big(z_i-\sum_jK^p_{ij}\beta_{ij}z_j\big)^2$. Both assemblies produce the *identical* receiver conditional of Proposition 1, so no local example can tell them apart. They differ in the joint distribution, and the difference has teeth.

> **Case file — the dead informer.**
>
> **Setup.** A receiver hears two informers at equal configured precision: one lit, one *dead* — a dark dead-end with no lit path and no other relations. What should the lit message transfer?
>
> **The contract answer.** Everything: the dead informer carries no information, so configuring trust in it must cost nothing. In the pairwise form this is automatic — marginalizing an unconstrained informer removes its factor exactly (the Gaussian integral over a free $z_j$ of $p\,(z_i-\beta z_j)^2$ is flat in $z_i$) — and the production solve transfers 1.00 of the lit message across four decades of dead-informer precision (Figure 5A), the dead node simply riding along with a broad marginal.
>
> **The averaging answer.** In the row-normalized form the weights are fixed by *configured* precision whether or not an informer carries information: the residual can be zeroed for any $z_i$ by moving the free informer, the posterior is improper, and under a small regularizing anchor the receiver transfers only 0.40 of the lit message at equal precisions — decaying toward zero as the dead informer's configured precision grows. Configuring trust in a silent neighbour *destroys* a live signal.
>
> **Two more properties settle the form.** A reciprocal bidirectional pair collapses to *one* factor, so auto-generated calendar relations cannot double-count precision; and the factor list *is* the sparse assembly — no normalization couples edges into the same receiver. *The joint form of an operator is a modelling decision even when every local conditional agrees.*

The convention that makes one-factor-per-relation well defined is the **canonical orientation**: $p\,(z_i-\beta z_j)^2$ and $p'\,(z_j-z_i/\beta)^2$ are the same factor iff $p_{\mathrm{rev}}=p_{\mathrm{fwd}}/\beta^2$. Auto calendar relations are therefore quoted with the *shorter* maturity as receiver — relation noise in short-dated vol units, where moves are largest and desk intuition lives — with implied reverse amplitude $1/\beta$, and the receiver diagnostic $q_i$ maps every incident factor into $i$'s units by the same identity. Explicit user edges stay directed as entered; entering both directions deliberately creates two distinct relations, and the cycle diagnostics of "Diagnostics and the gauge" apply.

## 3. Amplitude: shape locked, level measured

### 3.1 The maturity shape

For a calendar relation the amplitude is the maturity shape

$$
\beta_{i\leftarrow j}=\Big(\frac{T_j}{T_i}\Big)^{\alpha_T},
\qquad \alpha_T=1\ \text{(default, per-handle configurable)}.
\tag{2}
$$

$\alpha_T=1$ is constant total-variance injection — a $+1$ vol-point move at 6M reads as $+2$ at 3M and $+0.5$ at 1Y (Figure 1) — and reciprocal by construction: $\beta_{i\leftarrow j}\beta_{j\leftarrow i}=1$, so a calendar ladder cannot claim amplification both ways. The exponent is per-handle (ATM level, skew and curvature need not share a maturity scaling; all default $1$). On stored data the shape is *weakly identified* at the day horizon ($R^2$ 0.180 vs 0.181 across $\alpha_T\in\{0,1\}$ once the level refits), so $1.0$ is held by its semantics and the adjudication campaign sweeps it.

### 3.2 The level is an empirical quantity

Full-force transmission ($\widehat z=\beta z$ exactly) is the correct semantics *conditional on a relation the desk asserts*. It is not what the tape does on average: on ~11735 stored adjacent-pair observations the realized day-over-day calendar transfer under the $\alpha_T=1$ shape is 0.23 per unit of predicted move, and the one-source index→name transfer is 0.391. A default transmitting at full force would fail the pre-registered RMS gate on its first day. So amplitude splits: the *shape* stays locked, and the *level* is a per-relation-class multiplier $\rho\in(0,1]$ with two presets — `desk` ($\rho=1$, full force, the belief mode) and `learned` (the measured levels above; they are shape-dependent — $0.23$ is the $\alpha_T=1$ calendar value, and the $\sqrt T$-shape equivalent is $0.34$).

### 3.3 Mechanizing the level: two wrong ways and a measured right one

How should $\rho$ enter? Two natural answers are provably wrong. Scaling the beta ($\beta\to\rho\beta$) shrinks the forward conditional but *amplifies* the reverse one by $1/\rho$ — the reciprocal identity turns attenuation into amplification. Emitting two directed shrunk factors double-counts the relation and composes to $2\rho/(1+\rho^2)\neq\rho$. The consistent mechanization of regression attenuation in both directions of one joint Gaussian is a *local innovation anchor*:

$$
\kappa_i=p_{\mathrm{primary}}\,\frac{1-\rho_{\mathrm{class}}}
{\rho_{\mathrm{class}}},
\tag{3}
$$

with $p_{\mathrm{primary}}$ the largest incident relation precision in node $i$'s units and $\rho_{\mathrm{class}}$ that primary relation's class multiplier — *fixed at build time, never rescaled as further edges arrive*. The desk preset $\rho=1$ gives $\kappa=0$ exactly, recovering the pure contracts of "Edges as contracts".

**Proposition 2 (Corroboration under the node-linked anchor).** With $k$ equal agreeing clamped sources at precision $p$, beta one, and the fixed anchor of equation (3), the receiver's transfer per unit message is

$$
\frac{kp}{\kappa+kp}=\frac{k\rho}{1-\rho+k\rho}:
$$

one source transfers exactly $\rho$; two lift it to $2\rho/(1+\rho)$; independent corroboration keeps raising the effective transfer toward one.

*Proof.* By Proposition 1 the $k$ agreeing messages average to the common value at conditional precision $kp$; the anchor adds a zero-innovation pseudo-message at precision $\kappa$, so the posterior mean shrinks by $kp/(\kappa+kp)$; substitute equation (3). ∎

The fixed anchor is not a preference; it is the mechanization the data chose, through a falsifiable prediction. The alternative — an edge-linked anchor $\kappa_i=\sum_jp_{ij}(1-\rho)/\rho$, under which the transfer is constant at $\rho$ regardless of source count — predicts *no* corroboration lift. The stored benchmark rows adjudicate: across 1007 name-days carrying same-sector peers, the one-source index transfer slope is 0.391 and the measured two-source (index $+$ peer-average) slope is 0.561 — an uplift of $+43\%$ against a pre-registered $15\%$ bar. Calibrating the fixed-$\kappa$ model on the *single-source slope alone* predicts 0.563 for two sources: agreement to 0.3%, with zero free parameters (Figure 2).

> **Figure 2 — Amplitude level as a measured object (figure not included in this pack).** Amplitude level as a measured object (production anchor and posterior; measured points from the stored design-study artifact). The node-linked fixed anchor produces the corroboration curve $k\rho/(1-\rho+k\rho)$; calibrated only on the one-source slope (0.391), it predicts the measured two-source transfer to 0.3% with no free parameters. The edge-linked alternative — constant transfer regardless of source count (dashed) — predicts no lift and is contradicted by the same measurement ($+43\%$ against a $15\%$ bar). *The figure plots effective transfer per unit message against the number of corroborating sources $k$: the node-linked anchor's curve rises from 0.391 at $k=1$ through 0.563 at $k=2$ toward one, and the measured two-source point sits at 0.561, essentially on the curve. A dashed horizontal line at 0.391 marks the edge-linked alternative's prediction of no lift, visibly contradicted by the $k=2$ measurement. The takeaway: the two mechanizations disagree by a testable $+43\%$ uplift, and the data land on the fixed-anchor curve to 0.3% with zero free parameters.*

**Exercise 1.** Derive both rejections of this section: (i) show that replacing $\beta$ by $\rho\beta$ in one factor turns the implied reverse-direction amplitude into $1/(\rho\beta)$; (ii) show that two directed factors $p(z_i-\rho\beta z_j)^2+p'(z_j-\rho z_i/\beta)^2$ with matched units produce a one-source transfer of $2\rho/(1+\rho^2)$, not $\rho$. Then verify from equation (3) that $\rho=1$ gives $\kappa=0$ exactly — the desk preset is the contract semantics, not a limit.

## 4. Confidence: the precision families

Amplitude answers "how large"; precision answers "how reliable", and the defaults are empirical. The calendar family is

$$
p^{\mathrm{cal}}_{ij}
=\frac{p_0}{\epsilon_T+\sqrt{|T_i-T_j|}},
\qquad
p_0\approx 1690\ \text{vol}^{-2},\quad
\epsilon_T\approx 0.97\ \sqrt{\text{years}},
\tag{4}
$$

with the seeds fitted on the same 11735 stored adjacent-pair residuals (Figure 3B): about 2.7 vol points of relation noise at a one-month gap, and — the honest surprise — *nearly gap-flat* at the day horizon: $\epsilon_T$ dominates, the family degrades gracefully toward constant precision, and whether the decay term earns its keep at all is one of the campaign's ablations (`constant` and log-distance families ship beside it). Cross-class seeds from the same study: index→name $p\approx1.3\times10^4$, sector peer $p\approx0.9\times10^4$ (vol units) — with the recorded caveat that both are measured on ticker-day *median* innovations and are therefore upper bounds on per-edge precision.

Two unit disciplines complete the picture. **Per-handle units**: edge precision is quoted in ATM-vol units; the skew and curvature fields scale it by $(s_\sigma/s_h)^2$ with the production per-handle move scales $(0.03,0.05,0.5)$ — a units choice, not a semantics choice, since the precision-weighted *average* is invariant to a global rescale of all incoming precisions. **Variance is the readable coordinate**: an edge carries $z_i=\beta z_j+\epsilon$, $\operatorname{Var}\epsilon=1/p$, so along a chain amplitudes multiply while variances accumulate,

$$
\mathbb E[z_C]=\beta_2\beta_1\,\mathbb E[z_A],
\qquad
\operatorname{Var}(z_C)=(\beta_2\beta_1)^2\operatorname{Var}(z_A)
+\frac{\beta_2^2}{p_1}+\frac{1}{p_2},
\tag{5}
$$

and *no mean haircut is ever applied for distance* (Figure 4): the mean crosses six hops undamped (production: $\widehat z=1.000$ at hop six) while the band pays the toll, the production marginals matching the accumulation identity to 0.0000 exactly.

> **Figure 3 — The calendar relation, split into its two fields (figure not included in this pack).** A: the amplitude shape of equation (2) — what a 6M move implies elsewhere on the ladder, per exponent; $\alpha_T=1$ (locked) is constant total-variance injection. B: the confidence family of equation (4) against the stored residuals it was fitted on — relation noise is nearly gap-flat at the day horizon, so $\epsilon_T$ dominates and the decay term's keep is an open ablation. *Panel A draws the implied move across the maturity ladder for a $+1$ vol-point move at 6M under several exponents $\alpha_T$; the locked $\alpha_T=1$ trace reads $+2$ at 3M and $+0.5$ at 1Y. Panel B overlays the fitted family $p_0/(\epsilon_T+\sqrt{|T_i-T_j|})$ with $p_0\approx1690$, $\epsilon_T\approx0.97$ on the binned relation-noise residuals from the 11735 stored adjacent pairs: roughly 2.7 vol points of noise at a one-month gap, and a nearly flat profile in gap — the visual evidence that $\epsilon_T$ dominates at the day horizon.*

> **Figure 4 — Multi-hop propagation (figure not included in this pack).** Multi-hop propagation (production solve, six-hop chain, $\beta=1$): the posterior mean crosses every hop undamped while the marginal band accumulates exactly the per-edge relation variances of equation (5) (dotted: the closed-form accumulation). Distance costs confidence, never amplitude. *The figure plots posterior mean and $\pm$ one marginal standard deviation against hop index along a six-hop unit-beta chain with the near end lit at $+1$: the mean is a flat line at 1.000 through hop six, while the band widens monotonically with hop count. A dotted curve carries the closed-form variance accumulation of equation (5), and the production marginals sit on it to 0.0000. The takeaway is the contract's signature: distance taxes the band, never the mean.*

## 5. The accountant: the information-form posterior

The factors, the anchors and the lit observations assemble in information form, solved per connected component of the factor support:

**Central equation.**

$$
Q^+=Q_{\mathrm{msg}}+D_\kappa+H^{\mathsf T}R_d H,
\qquad
b^+=H^{\mathsf T}R_d\,d,
\qquad
\widehat z=(Q^+)^{-1}b^+,\quad \Sigma^+=(Q^+)^{-1},
\tag{6}
$$

with three honesty rules that are as load-bearing as the algebra.

**No lit path, no invented signal.** Components are built on $\beta\neq0$ edges (a zero-beta factor couples only its receiver — the reachability guard that stops an information-free informer from destabilizing an observed component); a component with no lit observation is never solved into propriety — it keeps $\widehat z=0$, the transported prior, a `no_lit_path` flag, and an explicitly broad variance (one typical handle magnitude at the production layer). Every observed component is verified positive definite by Cholesky before inversion.

**Innovations are only as precise as their ingredients.** A lit innovation is a difference of two estimates, so its observation precision combines harmonically,

$$
r^d_s=\Big(\frac{1}{r^{\mathrm{cal}}_s}+\frac{1}{p^0_s}\Big)^{-1},
\tag{7}
$$

and the *placement rule* holds baseline uncertainty to exactly one appearance per node: folded into $r^d_s$ for a lit source, added once to the reconstruction band for a dark node — golden-locked so no node is widened twice.

**Attribution is exact.** The gain matrix $G=\Sigma^+H^{\mathsf T}R_d$ decomposes every posterior shift over the observed lit sources, $\widehat z_i=\sum_sG_{is}d_s$, contributions summing to the shift by construction — per independent *source*, never per path, because path contributions are correlated and non-unique.

The accountant's signature behaviours run through the production solve in Figures 5 and 6. Two routes carrying one source are priced jointly: on the triangle fixture (source observed at finite precision $p$, one direct and one two-leg route) the global posterior variance is $1.67/p$, where naive per-message accounting — the equation (5) effective precisions added as if independent — claims $1.20/p$, overstating precision by a factor of $1.39$. Competing messages vote: equal opposing signals cancel to $0.00$ at *doubled* conditional precision $2p$ (disagreement is not silence); a $3p$ source outvotes to $-0.50$; and under $\alpha_T=1$ betas the same $\mp1$ raw signals land at $+0.75$ — not a defect but the contract: signals are mapped into receiver units *before* the vote, and equal-absolute-vol cancellation is a $\beta=1$ statement.

> **Figure 5 — The accountant at work (figure not included in this pack).** The accountant at work (production solves). A: the dead-informer case file — a row-normalized assembly dilutes a lit message toward zero as a silent neighbour's *configured* precision grows; the pairwise factor marginalizes the dead informer away exactly. B: repeated routes from one source — the global posterior variance ($1.67/p$) against naive independent-message accounting ($1.20/p$): path counting would fabricate a $1.39\times$ precision overstatement. *Panel A plots the fraction of the lit message transferred against the dead informer's configured precision swept over four decades: the pairwise-factor trace is flat at 1.00, while the row-normalized trace starts at 0.40 for equal precisions and decays toward zero as the silent neighbour's configured precision grows. Panel B compares the target's posterior variance on the triangle fixture: the correct joint answer $1.67/p$ against the naive independent-route figure $1.20/p$. The gap is the $1.39\times$ precision overstatement that path counting would fabricate.*

> **Figure 6 — Competing messages vote (figure not included in this pack).** Competing messages vote (production solves; 6M dark, 3M and 1Y lit at $\mp1$ vol point). Equal precision and $\beta=1$: exact cancellation at doubled conditional precision. A $3p$ source outvotes. Under the locked $\alpha_T=1$ betas the same raw signals map to $-0.5$ and $+2$ in 6M units before averaging — the receiver hears receiver-unit predictions, not raw levels. *The figure shows the 6M receiver's posterior mean under three configurations of the two lit informers at $\mp1$ vol point: equal precisions with $\beta=1$ cancel exactly to 0.00 (and the conditional precision doubles to $2p$ — disagreement is not silence); tripling one side's precision moves the vote to $-0.50$; and the production $\alpha_T=1$ betas map the same raw signals to $-0.5$ and $+2$ in 6M units before averaging, landing the receiver at $+0.75$. The takeaway: competing messages are precision-weighted votes over receiver-unit predictions, never sums of raw levels.*

**Exercise 2.** Reproduce panel B of Figure 5 by hand: with the source observed at precision $p$ and all three relation precisions $p$, assemble the $3\times3$ information matrix of equation (6), invert, and show the target's marginal variance is exactly $5/(3p)$, while the equation (5) effective-message precisions ($p/2$ direct, $p/3$ through the middle node) sum to $5p/6$, i.e. variance $6/(5p)$. The naive answer is wrong because both routes share the source's own uncertainty — the covariance the global solve refuses to forget.

**Exercise 3.** Three distinct quantities appear at every receiver: edge precision $p_{ij}$, conditional incoming precision $q_i=\sum_jp_{ij}$, and marginal posterior precision $1/\Sigma^+_{ii}$. Construct a two-node example where $q_i$ is large but the marginal precision is small (an uncertain informer), and one where the marginal exceeds $q_i$ (the receiver's own observation). Only in the idealized clamped-independent-informer case do the last two coincide — which is why the wire reports both, and the UI must never present $q_i$ as the final confidence.

## 6. Diagnostics and the gauge

Directedness in a Gaussian is a statement about the *prediction relation*, not about inference: the posterior precision is symmetric, so observing a receiver legitimately updates an uncertain informer. Where strictly one-way conditioning is required, the graph must be a DAG or the source clamped — a UI arrow cannot create one-way Bayes. What the solver *can* police is internal consistency of the amplitudes:

**Proposition 3 (Cycle consistency is a gauge condition).** A positive beta structure is cycle-consistent — every directed cycle's beta product equals one — iff there exist node potentials $g_i>0$ with $\beta_{ij}=g_i/g_j$.

*Proof.* If $\beta_{ij}=g_i/g_j$, every cycle product telescopes to one. Conversely, fix a spanning tree per component, set $\phi_i=\log g_i$ by propagating $\log\beta$ along tree edges from an arbitrary root; a non-tree edge with $\beta_{ij}\ne e^{\phi_i-\phi_j}$ closes a cycle whose product is $\beta_{ij}e^{-(\phi_i-\phi_j)}\ne1$. ∎

Production runs exactly this proof as an algorithm: a union-find sweep with logarithmic offsets assigns the potentials in linear time and flags every closing edge whose implied cycle product strays from one (the reference cross-check of Appendix E plants a consistent triangle — zero flags — and an inconsistent one, flagged at product 0.833). Auto-generated calendar ladders are gauge-consistent by construction ($g_i=T_i^{-\alpha_T}$); the diagnostic exists for explicit edges, where an inconsistent loop means the configuration asserts contradictory amplifications and the posterior will split the difference somewhere the desk did not choose. The wire also carries, per node, the conditional $q_i$, the marginal precision, the `no_lit_path` mask and the anchor provenance — the three-quantity distinction of Exercise 3 made permanently visible.

## 7. Production orchestration

### 7.1 What feeds the solve

The message path consumes exactly what the spine already computes — selected universe, transported priors and provenance tiers, lit innovations and calibration precisions — and feeds the same `HandleField` seam back to reconstruction, functional bands, the idio floor, attribution and the backtest. Auto relations over the selected universe: one calendar factor per adjacent expiry pair per ticker (canonical short receiver, equation (4) precision) and one beta-one cross factor per same-expiry ticker pair (constant precision, orientation-neutral at beta one). Persisted edge rules override auto; request edges override both. The observation-selection plan — which dark node is worth quoting next — ports to the information form through the $\Sigma^+$ columns, the same rank-one algebra as the band-variance accounting. `propagationMode` selects `precision_messages`, the smoothing alternative of Appendix B, or `hybrid` (message factors plus an explicit smoothing term; config-only, locked to coincide with pure messages when its weight is zero); the wire enum also carries the layered dynamic-harmonic mode, an opt-in documented in the companion edition. One scope sentence prevents a misreading: two keys carry two defaults. The *wire* default on a bare solve request stays the smoothing mode — workspace replay, the byte-identity locks and the backtest harness are untouched — while the *Options* default, the one the application seeds and a desk actually runs, is precision messages since 2026-07-27 ("Evidence and the gate").

### 7.2 The edge schema and the editor

Edges persist in an explicit schema: `source`/`informer` → `target`/`receiver` naming (the one unambiguous vocabulary for a directed relation), `messagePrecision`, three handle betas, relation class, and a precision rule (`explicit` or `calendar_distance`, the latter re-deriving from equation (4) on every solve). A one-shot import converts any older weight-based edge list on explicit request only — weight is a relative trust with no canonical precision meaning, so the conversion factor is the caller's stated choice and the old blob round-trips untouched. The edge editor exposes the full contract surface: per-relation precision and betas, relation class, inherited-versus-explicit display, implied-reverse chips, seed-from-auto, receiver diagnostics, and a deterministic scenario preview locked to the golden numbers of this note — a desk can configure the three canonical examples and see these exact means before saving.

### 7.3 The six-node case file

A miniature universe — an SPX calendar chain (1M/3M/6M), the sector ETF XLK, two technology names — makes every mechanism visible at once (Figure 7; lit: SPX 3M $+1.00$ vol point, XLK 3M $+0.55$; empirical precision seeds; `learned` amplitude presets). The table is generated by the production solve; the `desk` column shows the same universe at $\rho=1$:

| Node | Role | $\widehat z$ (pts) | sd (pts) | desk $\widehat z$ | $q_i$ |
|---|---|---:|---:|---:|---:|
| `SPX1M` | dark | $+0.66$ | $1.37$ | $+2.97$ | $1233$ |
| `SPX3M` | lit | $+0.95$ | $0.10$ | $+0.99$ | $51740$ |
| `SPX6M` | dark | $+0.11$ | $0.71$ | $+0.49$ | $4626$ |
| `XLK3M` | lit | $+0.54$ | $0.10$ | $+0.56$ | $31170$ |
| `AAPL3M` | dark | $+0.41$ | $0.49$ | $+0.82$ | $22166$ |
| `MSFT3M` | dark | $+0.41$ | $0.49$ | $+0.82$ | $22166$ |

Every design choice is legible in the numbers. SPX 1M inherits the index move through the ladder at the $\alpha_T{=}1$ shape — $+2.97$ points under desk force, shrunk to $+0.66$ by the learned calendar level, with the widest band in the universe (short-dated vol units are where calendar noise is largest). AAPL and MSFT each hear two corroborating sources — index and sector ETF — so their transfer ($+0.41$; desk $+0.82$) sits *above* what either single-source level would give, exactly the corroboration lift of Proposition 2. And the conditional $q_i$ column differs from the implied marginal everywhere — the Exercise-3 distinction on display.

> **Figure 7 — The six-node case file (figure not included in this pack).** The six-node case file (production solve; learned amplitude presets, empirical precision seeds; arrows point informer → receiver). Lit nodes red, dark teal, each labelled with its posterior innovation and marginal sd in vol points. The names hear index and ETF corroboration and transfer above the single-source level; the 1M node shows the amplified-but-uncertain short end. *The figure draws the six-node graph — the SPX 1M/3M/6M calendar chain, the sector ETF XLK, and AAPL and MSFT — with directed arrows from informer to receiver. The two lit nodes (SPX 3M at $+0.95\pm0.10$, XLK 3M at $+0.54\pm0.10$) are drawn red; the dark nodes teal, labelled SPX 1M $+0.66\pm1.37$, SPX 6M $+0.11\pm0.71$, AAPL and MSFT each $+0.41\pm0.49$. The visual takeaway matches the table: corroborated names transfer above the single-source level, and the short-maturity node carries the largest amplitude and the widest band.*

## 8. Evidence and the gate

The empirical discipline of this system runs in three layers, from contract to campaign.

**Golden contracts.** Every behaviour of "Edges as contracts", "Amplitude: shape locked, level measured" and "The accountant: the information-form posterior" — full transmission, competition, cross-asset averaging, multi-hop accumulation, the dead informer, the repeated path, shrunk-mode transfer and corroboration, baseline-once — is a fixture with an expected number, checked against an independent brute-force Gaussian reference and reproduced through the production modules at $10^{-12}$. The operator's semantics cannot drift without a named test failing.

**The design study.** The empirical inputs quoted throughout — transfer slopes 0.391 (index), 0.762 (peer) and 0.23 (calendar), the corroboration adjudication of Figure 2, the calendar noise seeds of Figure 3 — come from a stored study over three historical regimes of benchmark rows (~47k held-out scores' worth of innovation panels), read from its artifact, never re-run. The same row bank has already measured the *spine's* extrapolation skill — dark single names behind lit indexes and ETFs gain $+7.9$ to $+14.2$ ATM vol bps in the stressed regimes with honest bands after the idio floor (Appendix B) — so graph extrapolation as such is not the hypothesis under test; the operator's marginal value is.

**The pre-registered gate, and its recorded verdict.** The gate was written before the sweep ran: precision messages become the product default *only if*, on the frozen three-regime fixtures over the strict out-of-sample window, a combined adjudication campaign shows material liquid-split dark-name skill over both the transported prior and the smoothing mode; no degradation in the stressed regimes; no calm-regime harm beyond tolerance; standardized residuals near unit scale with 80/95% band coverage near nominal after the idio floor; no unstable cycles; and no wing-RMS deterioration. Expectations were recorded before the sweep: the `desk` preset was *expected* to lose day-horizon RMS (it is a belief mode and ships regardless); the `learned` preset was the candidate; a constant-precision ablation probed whether the gap-flat noise makes the decay term superfluous. (An earlier single-pair smoke, retained in the artifact, seeded expectations; one pair is not a verdict and it was not treated as one.)

The campaign ran, the table filled, and *at the daily horizon the gate did not clear*. Recorded verbatim: gate 1 failed (skill positive everywhere, $+0.35$ to $+2.01$ bp, material nowhere), gate 4 failed ($\zeta$ std $2.29$ against the base arm's over-wide $0.84$, 95% coverage $0.908$ — the message bands are overconfident), gate 6 failed marginally (wing medians $105.2$ against the legacy arm's $99.6$); gates 2, 3 and 5 passed. At one-day granularity the message operator is statistically indistinguishable from the smoothing mode on RMS — the 2026-07-19 hold, now in the pre-registered table.

The default flipped anyway, on 2026-07-27, and the basis is the part that matters: *not* this gate but the intraday async replay (the companion campaign's artifact), where the two operators finally separate. Replaying real intraday sessions through the production solvers, the smoothing mode is nearly inert — $168.6$ bp against a pure-transport baseline of $172.7$, its innovations shrunk to nothing by the zero-innovation anchor at day-scale $\kappa/\eta$ — while the message operator carries the signal at $65.8$ bp with $\zeta$ std $0.88$, 95% coverage $0.964$, and no wing regression. The flip was user-ratified with the failed daily table on the record; it moves the *Options* default only (the wire default and every byte-identity lock keep the smoothing mode), amplitude defaults stay at desk strength (the intraday evidence was measured there), and a store that ever saved Options keeps its explicit value until re-saved. The known daily-horizon characteristics the default now carries are stated plainly rather than argued away: graph credible bands narrow by a factor of about two, and wing medians about $+5$ bp against the legacy arm — the recorded price of an operator whose value lives below the day.

## 9. What is genuinely original here

Gaussian graphical models, information filters and gauge arguments are classical; the synthesis is specific. *Contractual propagation for volatility*: every desk-facing behaviour — full-amplitude transfer, precision addition, averaging, distance costing confidence not amplitude — is a golden test, so the operator's semantics cannot drift. *Amplitude as shape times measured level*, with the level mechanized through a node-linked anchor whose corroboration law was validated on stored rows to 0.3% with zero free parameters — a design decision settled by a falsifiable prediction, not a preference. *The dead-informer analysis* (Figure 5A): a joint-distribution defect invisible to every local conditional, surfaced and used to choose the factor form. *Honesty rules as first-class machinery*: no-lit-path components left improper on purpose, baseline uncertainty placed exactly once, attribution by source never by path. And *evidence discipline*, now demonstrated rather than promised: the pre-registered gate was honoured *by publishing its failure* — the daily table records three failed gates verbatim, and the default moved on different, recorded evidence rather than on a quietly amended criterion ("Evidence and the gate").

## 10. Limitations

Where the guarantees stop. *The daily horizon is a tie, and the default owns that*: at one-day granularity the message operator is statistically indistinguishable from the smoothing alternative on RMS, with overconfident bands ($\zeta$ std near $2$) and mildly worse wings — the recorded reason the daily gate failed ("Evidence and the gate"). The flip rests entirely on the intraday separation, and the daily calibration repair (joint anchors, baseline placement) is open work. *Correlated informers overstate conditional precision*: $q_i$ adds configured precisions as if sources were conditionally independent; the global solve prices shared *routes* correctly, but shared *factors* (SPY and QQQ moving on one macro shock) need class discounts or a common-factor node — open, with the marginal-vs-conditional gap on the wire as the tell. *Cross-class precision seeds are upper bounds* (ticker-median measurement); per-edge noise will be higher. *The amplitude shape is weakly identified at the day horizon* — $\alpha_T=1$ is held by semantics, not by $R^2$. *Hybrid mode is machinery, not a recommendation* (validated only at its zero-weight identity with pure messages). *The solve is dense*, sized for the $O(10^2$–$10^3)$-node selected universe; the factor list is sparse-ready and the sparse pass is deferred until a universe demands it. *Calendar arbitrage remains soft*: calendar factors propagate maturity signals but impose no hard cross-expiry projection — publish-time diagnostics and the LV projection remain the fence. And *curvature stays the weakest handle* end to end, in identification and in units.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

*Table 2 — Message-mode hyperparameters (the smoothing mode's knobs live with its appendix).*

| Knob | Default | Role |
|---|---|---|
| `graphPropagationMode` | `precision_messages` | The mode fork: `precision_messages` / `smooth_field` (Appendix B, explicit rollback) / `hybrid` (config-only). The daily gate ("Evidence and the gate") did not clear; the default was flipped 2026-07-27 on the intraday async-replay separation, where the smoothing operator is nearly inert (its zero-innovation anchor at day-scale stiffness shrinks intraday innovations to nothing) while messages carry them at amplitude $\rho\beta$. |
| `calendarBetaExponent` | $1.0$ (per handle) | The amplitude shape $\alpha_T$ of equation (2). |
| `calendarAmplitude` | $1.0$ | Calendar level $\rho$; presets desk $=1.0$ / learned $\approx0.23$ (the $\alpha_T{=}1$ value). |
| `crossAmplitude` | $1.0$ | Shared level $\rho$ for every cross relation class in v1; learned $\approx0.39$ index. |
| `calendarPrecisionScale` $p_0$ | $1.7\times10^3$ | Calendar precision scale of equation (4), empirical seed. |
| `calendarPrecisionEpsilon` $\epsilon_T$ | $0.97$ | Near-identical-expiry precision cap; dominates at the day horizon. |
| `calendarPrecisionDecay` | `inverse_sqrt_gap` | Family: inverse-sqrt-gap / constant / log-distance. |
| `crossPrecisionScale` | $1.3\times10^4$ | Constant cross-relation precision (index seed; upper bound). |
| `innovationAnchorPrecision` | derived | Override for equation (3); unset $=$ node-linked from $\rho$, and $\rho=1$ gives $\kappa=0$ exactly. |
| `cycleBetaTolerance` | $10^{-9}$ | Gauge-sweep flag threshold (Proposition 3). |
| `messageEdges` / persisted rules | — | Request edges → persisted schema rules → auto relations, in that precedence. |

*Hidden (module constants):*

| Knob | Default | Role |
|---|---|---|
| `HANDLE_PRECISION_SCALE` | $(1,0.36,0.0036)$ | The $(s_\sigma/s_h)^2$ per-handle precision units of "Confidence: the precision families". |
| `RELATION_CLASSES` | 5 classes | calendar / broad_index / sector_etf / sector_peer / custom. |
| `DISCONNECTED_Z_SD` | $(0.03,0.05,0.5)$ | The honest no-lit-path innovation sd per handle (one typical move). |
| canonical orientation | shorter $T$ | Auto calendar receiver; reverse identity $p_{\mathrm{rev}}=p_{\mathrm{fwd}}/\beta^2$. |

## Appendix B. The smoothing-mode alternative

`smooth_field` mode answers the propagation question with a different prior: instead of relation contracts, a global smooth-field regularizer on the increment field,

$$
z\sim\mathcal N(0,Q_{\Delta}^{-1}),
\qquad
Q_{\Delta}=D_\kappa+\eta\,L_{\mathrm{dir}}^{\beta}+\lambda\,(A_\rho+\nu I)^{-1},
$$

a three-member committee — local smallness, a $\pi$-weighted directed neighbour-prediction residual built on a row-normalized trust kernel, and an optional unbalanced-optimal-transport tangent term ($\lambda=0$ shipped) — conditioned on the lit innovations in covariance form, with the same reported-marginal convention and attribution contract as the message mode. It asks "what small, neighbour-consistent, transportable field explains the lit moves?" rather than "what do the configured relations say?", and it is the natural mode when no explicit relation structure is configured and a generic smoothness belief is all the desk wants to assert. Its propagation behaviour is emergent rather than contractual — incoming trust is row-normalized (relative, not absolute), and reach, stiffness and anchoring share coupled dials — which is exactly the trade the mode fork exposes. Its own record stands on the stored benchmarks: dark single names behind lit indexes and ETFs gain $+7.9$ to $+14.2$ ATM vol bps in the August-2024 spike and $+3.8$ to $+7.2$ fully out-of-sample in the October-2022 bear, calm-regime skill $+0.7$ to $+0.8$ — never negative — with the calm-regime dark-name bands made honest by the idiosyncratic ATM floor ($\operatorname{std}\zeta$ $1.91\to1.02$ and $1.85\to1.03$, mean-invariant by construction). The mode is byte-locked at its defaults by the full legacy test suite, its knobs and detailed mathematics live in its own technical note, and the hybrid mode adds its smoothness term to the message factors on explicit opt-in only.

## Appendix C. Performance notes

1. **The assembly is the factor list**: $O(E)$ triplets, dense materialization at the current $O(10^2$–$10^3)$-node design point, and the 1k-node perf rail passes unchanged. Sparse Cholesky / selected-inverse marginals are the deferred scale pass — the pairwise form sparsifies without renormalization coupling.
2. **Per-component solves**: the posterior inverts each factor-support component separately, so one disconnected block never pays for another, and the Cholesky PD guard localizes any conditioning failure to a named component.
3. **The message path adds no new data work**: universe, transported priors, innovations and calibration precisions are the same objects the spine computes for any mode; the fork is downstream of all of them.
4. **Adjudication runs where long jobs survive**: the campaign executes from the user's own shell (chunked, resumable parts beside the frozen fixtures); tool-spawned background jobs are killed on this box — a recorded operational constraint. Both adjudication campaigns — the daily message gate and the intraday async replay — ran this way, each with its own launcher.
5. No benchmark in this note was re-timed; figures and macros were generated at commit `6d8d572` on 2026-07-19, golden numbers through the production modules and empirical numbers from the stored design-study artifact. The campaign verdicts and the default flip quoted in "Evidence and the gate" are current as of 2026-07-27, from the two findings records anchored in Appendix D, "Traceability".

## Appendix D. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

*Table 3 — Claims in this note and the code/tests that lock them.*

| Claim | Object | Code anchor | Test anchor |
|---|---|---|---|
| Pairwise operator PSD; receiver conditional; $q_i$ unit mapping; canonical orientation | equation (1), Proposition 1 | `volfit/graph/message.py` | `test_graph_message.py` |
| Golden contracts (transmission, competition, cross-asset, multi-hop, dead informer, repeated path, shrunk mode, baseline-once) | sections "Edges as contracts", "Amplitude: shape locked, level measured", "The accountant: the information-form posterior" | `tests/fixtures/graph_message_golden.json` | `test_graph_message_golden.py` (brute-force reference), `test_graph_message.py` |
| Information-form component solve; no-lit honesty; reachability guard; exact attribution | equation (6) | `volfit/graph/message_posterior.py` | `test_graph_message_posterior.py` |
| Node-linked anchor $\kappa=p(1-\rho)/\rho$ fixed at build; $\rho=1\Rightarrow\kappa=0$; corroboration law | equation (3), Proposition 2 | `volfit/graph/message.py` | `test_graph_message.py`, `test_graph_message_golden.py` |
| Cycle gauge sweep flags inconsistent products | Proposition 3 | `volfit/graph/message.py` | `test_graph_message.py` |
| Production orchestration: auto relations, $r^d$ harmonic, band placement, mode fork, hybrid $\equiv$ messages at zero weight | section "Production orchestration" | `volfit/api/graph_message.py`, `api/graph_extrapolation.py` | `test_graph_message_production.py` |
| Edge schema; explicit weight-list import preserves economics; old blob untouched | section "Production orchestration" | `api/schemas.py` (`GraphMessageEdge`), `api/graph_message.py` | `test_graph_message_production.py` |
| Smoothing mode byte-locked at defaults; idio band floor | Appendix B | `volfit/graph/prior.py`, `volfit/graph/posterior.py`, `volfit/graph/idio.py` | `test_graph_example.py`, `test_graph_idio.py` |
| Adjudication harness variants, coverage metrics, decision table | section "Evidence and the gate" | `backtest/run_message_adjudication.ps1`, `backtest/graph_edges.py` | `test_message_adjudication.py` |
| Filled daily decision table; the 2026-07-27 flip record | section "Evidence and the gate" | `backtest/FINDINGS_message_phase4.md` | — (a findings record, quoted verbatim) |
| Intraday async replay: the separation the flip rests on | section "Evidence and the gate" | `backtest/FINDINGS_dynamic_intraday.md`, `backtest/graph_intraday.py` | `test_graph_intraday_replay.py` |
| Mode semantics certification (A/B arms byte-identical off) | section "Evidence and the gate" | `backtest/certification.py` | certification case `graph_precision_messages` |
| Design study (anchor choice, seeds, learned levels) | sections "Amplitude: shape locked, level measured", "Confidence: the precision families" | `backtest/message_phase0.py` | artifact `results/message_phase0.json` (regenerable) |

## Appendix E. Reference implementation

The operator and the posterior are each a few lines. Executed against the production modules on a four-node directed universe with a node-linked anchor (operator matrix, posterior mean, marginal variances), the maximum deviation is $2.3\times10^{-13}$; the gauge sweep cross-check flags nothing on a consistent triangle (0 flags) and reports the planted inconsistent product 0.833 on the broken one.

Per the transfer policy of this pack, the reference listing is replaced by an exact algorithm specification. It was verified against the production modules `graph/message.py` and `graph/message_posterior.py` (capability anchors, not files to reproduce), with the agreement stated above.

**Algorithm 1 — the pairwise message operator.**

*Inputs:* the node count $n$; a factor list of quadruples $(i, j, p, \beta)$ — receiver index, informer index, relation precision, amplitude.

*Output:* the $n\times n$ operator $Q_{\mathrm{msg}}$.

1. Initialize $Q$ as the $n\times n$ zero matrix.
2. For each factor $(i,j,p,\beta)$ in list order: form the vector $u\in\mathbb R^n$ with $u_i=1$, $u_j=-\beta$, and zeros elsewhere; add the rank-one term $p\,uu^{\mathsf T}$ to $Q$.
3. Return $Q$. The result is positive semidefinite for any real $\beta$ (each summand is a PSD rank-one term); no normalization step of any kind is applied.

**Algorithm 2 — the information-form posterior solve.**

*Inputs:* the operator $Q$ from Algorithm 1; the anchor vector $\kappa\in\mathbb R^n_{\ge0}$ (identically zero in desk mode, per equation (3) otherwise); the set of observed (lit) node indices; the observed innovations $d_s$; the observation precisions $r_s$ (the harmonically combined $r^d_s$ of equation (7)).

*Outputs:* the posterior mean $\widehat z$ and the posterior covariance $\Sigma^+$.

1. Form $Q^+ = Q + \operatorname{diag}(\kappa)$ — the anchors enter only on the diagonal.
2. For each observed node $s$: add $r_s$ to the diagonal entry $Q^+_{ss}$ (this is the $H^{\mathsf T}R_dH$ term of equation (6)), and set $b_s = r_s\,d_s$; $b$ is zero at every unobserved node (the $H^{\mathsf T}R_d\,d$ term).
3. Invert per lit connected component of the factor support: $\Sigma^+=(Q^+)^{-1}$, after a Cholesky positive-definiteness check on each observed component; components with no lit observation are never inverted (they keep $\widehat z=0$, the `no_lit_path` flag, and the broad `DISCONNECTED_Z_SD` variance).
4. Return $\widehat z=\Sigma^+ b$ and $\Sigma^+$.

*Stated production agreement:* maximum deviation $2.3\times10^{-13}$ across the operator matrix, posterior mean, and marginal variances on the four-node directed test universe with a node-linked anchor.

## References

1. [RasmussenWilliams2006] C. Rasmussen and C. Williams. *Gaussian Processes for Machine Learning*. MIT Press, 2006.
2. [Koller2009] D. Koller and N. Friedman. *Probabilistic Graphical Models*. MIT Press, 2009.
3. [Pearl1988] J. Pearl. *Probabilistic Reasoning in Intelligent Systems*. Morgan Kaufmann, 1988.
4. [Peyre2019] G. Peyré and M. Cuturi. Computational optimal transport. *Found. Trends Mach. Learn.*, 11(5–6):355–607, 2019.

