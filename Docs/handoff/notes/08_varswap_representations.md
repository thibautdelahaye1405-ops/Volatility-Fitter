# One Number, Three Integrals

**Note 08 — variance-swap representations · lecture edition ("the variance swap as a linear functional, and the representation where each model finds it cheap") · converted from 08_varswap_representations.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> Fit two production models — a parametric slice and a local-volatility surface — to the same twenty-three option quotes and they agree to basis points at every quoted strike; yet their fair variance-swap strikes differ by 30 vol bp, because the fair strike is a *global* functional of the smile, and the quotes leave its wing share free. A variance-swap quote is therefore genuinely new information: one number per (underlying, $T$) node that pins what scattered option quotes cannot. This lecture develops that number as a single pairing — the log-contract payoff integrated against the terminal risk-neutral law — and shows that the pairing has *three* exact integral representations: against option prices across strikes (Carr–Madan), against the quantile function of the terminal law, and against the local-variance field along paths (a source PDE). All three are the same number; what differs is the cost of evaluation in each model's native coordinates, and the first production wiring — one uniform replication for every model — turned a millisecond fit into a measured 158-second one because it evaluated the pairing in a chart where every point is a root-find. The per-model routes that replaced it are audited here end to end: the quantile-side closed form agrees with the strike-side replication to 1.53 vol bp on the running slice (and the gap is *spacing*, not truncation: tails beyond the half-width contribute 0.007 bp while the production grid's trapezoid carries 0.06–1.53 bp of $O(\Delta k^2)$ error); the source PDE matches its own strike-side value to 0.78 variance bp with analytic parameter sensitivities equal to finite differences at $1.2\times10^{-10}$; and the closed form re-derives the six fair strikes published by the application for a real SPY surface to 0.00 vol bp. As a calibration target the quote enters as one extra residual in volatility units, weighted as a fraction (default ten percent) of the node's option weight; at the default it moves a smile whose natural fair strike is 24.47% to 25.75% against a 25.97% quote — 85% of the way — at a worst option-quote concession of 52 vol bp.

**Contents**

1. The number the quotes leave free
2. Three integrals for one pairing
3. Where the number lives
4. Evaluating the pairing inside the optimizer
5. The quote as one more residual
6. The real object
7. What is genuinely original here
8. Limitations
Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation: both exact routes · References

---

## 1. The number the quotes leave free

Start with the failure the machinery exists to prevent. Figure 1 shows two fits to one quote set: the parametric slice this series calls LQD (Note 01) and the piecewise-affine local-volatility surface (Note 04), both production calibrations, both threading the same twenty-three quotes — inside the quoted band the two implied-volatility curves are within 13 vol bp of each other. Outside it they separate by up to 3.6 vol *points*, and their fair variance-swap strikes — 24.47% and 24.17% — differ by 30 vol bp. Nothing has gone wrong: both models price every quote correctly, and the data simply does not decide the quantity. A desk that marks variance swaps, or hedges wing risk, needs that quantity decided.

> **Figure 1 — The identifiability gap (figure not included in this pack).** The identifiability gap, exhibited with two production models on one quote set. Inside the quoted band (shaded) the parametric and local-vol fits agree to 13 vol bp — the quotes pin both. Outside it they diverge by up to 3.6 vol points, and the fair var-swap strikes printed by the two models differ by 30 vol bp. The fair strike is a global functional; option quotes constrain it only through the belly. The plot overlays the two fitted implied-vol curves across strike with the twenty-three quotes and the quoted band shaded: inside the band the curves are visually one line threading the quotes; outside the band they fan apart by up to 3.6 vol points, and the two models' printed fair strikes (24.47% vs 24.17%) are annotated to make the 30-bp consequence concrete.

### 1.1 The instrument, and the functional it prices

A variance swap pays the realized variance of the underlying up to $T$ against a fixed strike. Work throughout in forward-normalized units: the underlying is quoted as a ratio of the forward for $T$, so $F=1$, strikes are $K=e^{k}$ with $k$ the log-moneyness, and $X=\log S_T$ is the terminal log-return. Under a continuous forward-measure diffusion $\mathrm{d} S_t/S_t=\sigma_t\,\mathrm{d} W_t$, Itô's formula applied to $\log S_t$ gives

$$
\mathrm{d} \log S_t=\frac{\mathrm{d} S_t}{S_t}-\tfrac12\sigma_t^2\,\mathrm{d} t
\qquad\Longrightarrow\qquad
\int_0^T\!\sigma_t^2\,\mathrm{d} t
=2\!\int_0^T\!\frac{\mathrm{d} S_t}{S_t}-2\log S_T .
\tag{1}
$$

The stochastic integral is a martingale, so taking forward-measure expectations kills it, and the fair strike — the expected total variance — is the expectation of a fixed *payoff*:

$$
w_{\mathrm{vs}}=\mathbb{E}\!\Big[\int_0^T\!\sigma_t^2\,\mathrm{d} t\Big]=\mathbb{E}[-2X]
=\langle -2x,\,\mu\rangle,
\tag{2}
$$

where $\mu$ is the law of $X$ under the forward measure and $\langle\cdot,\cdot\rangle$ is the integration pairing. Everything in this lecture flows from reading equation (2) as a *pairing*: a fixed, model-independent test function ($-2x$, the log contract) against a measure the model supplies. The pairing is linear in $\mu$; it is a single moment; and, because a martingale measure must balance $\mathbb{E}[e^X]=1$ with tails that drag $\mathbb{E}[X]$ down, it is dominated by exactly the part of $\mu$ the option quotes describe worst. Where the smile models of this series differ is only in *which coordinates* they hold $\mu$ in — and that, it will turn out, decides where the pairing is cheap.

> **Invariant.**
> 1. One var-swap quote per smile node, model-independent: the same number is shared by the parametric and local-vol views of the node, with its own edit history, separate from the option-quote session.
> 2. With no quote set (or the feature disabled) every calibrator is byte-identical to the un-targeted fit.
> 3. The model's own fair strike is computed by a route that is cheap *inside* the optimizer loop — never by replication against a curve that must be root-found point by point.
> 4. The target's weight is relative — a declared fraction of the node's summed option weight — so the quote means the same thing on a 10-quote node and a 100-quote node.

**Conventions and the notation ledger.** $T$ is the expiry (year fraction) and $t\in[0,T]$ the running time; no other time symbols appear. Subscripted $\partial$ for all derivatives ($\partial_t g$, $\partial_{xx}g$); no primes. $(y)^-=\min(y,0)$ denotes the negative part *with its sign*. One vol bp is $10^{-4}$ of absolute volatility; a variance bp is $10^{-4}$ of $w_{\mathrm{vs}}/T$.

**Table 1 — Every symbol in the note.** Weights are $\lambda$, never $\omega$ — total variance $w$ keeps sole claim to a $w$-shaped glyph, and $w_{\mathrm{vs}}$ is the one subscripted exception.

| Symbol | Meaning |
|---|---|
| $k,\ K=e^k,\ F=1$ | log-moneyness; strike; forward |
| $X,\ \mu$ | terminal log-return and its law |
| $w(k),\ B(k,w)$ | total implied variance; Black call |
| $Q,\ \Lambda,\ u=\Lambda(z),\ z$ | quantile fn; logistic; probability; logit |
| $w_{\mathrm{vs}},\ \sigma_{\mathrm{vs}}=\sqrt{w_{\mathrm{vs}}/T}$ | fair strike (total var); its vol |
| $\nu(t,x),\ g(t,x),\ \rho(t,x)$ | local var; remaining var; density |
| $H,\ \Delta k$ | replication half-width; spacing |
| $\lambda_i,\ \lambda_{\mathrm{vs}},\ p$ | option weights; target weight; fraction |
| $\theta$ | a model's parameter vector |
| $(y)^-$ | $\min(y,0)$ |

## 2. Three integrals for one pairing

The pairing (2) is one number, but it can be handed to three different integrals, each exact, each "native" to one family of models. This section derives all three; Figure 2 draws their integrands side by side for one fitted object.

### 2.1 Against option prices: the strike side

The classical route moves the payoff onto tradeable instruments.

**Proposition 1 (Carr–Madan spanning of the log contract).** For any twice-differentiable payoff $f$ and any law of $S_T>0$ with $\mathbb{E}[S_T]=1$,

$$
\mathbb{E}[f(S_T)]=f(1)+\int_0^{1}\!f_{KK}(K)\,P(K)\,\mathrm{d} K
+\int_1^{\infty}\!f_{KK}(K)\,C(K)\,\mathrm{d} K,
$$

with $C,P$ undiscounted OTM call/put prices and $f_{KK}=\partial_{KK}f$. For $f(s)=-2\log s$, $f_{KK}(K)=2/K^{2}$, and in log-moneyness $K=e^{k}$ this collapses to a single integral against the normalized Black call $B(k,w(k))$ evaluated on the smile:

$$
w_{\mathrm{vs}}
=2\!\int_{-\infty}^{\infty}\!
\Big[B\big(k,w(k)\big)+(e^{k}-1)^-\Big]e^{-k}\,\mathrm{d} k .
\tag{3}
$$

*Proof.* Write $f(S)=f(1)+\partial_K f(1)(S-1)+\int_0^{1}f_{KK}(K)(K-S)^+\mathrm{d} K +\int_1^{\infty}f_{KK}(K)(S-K)^+\mathrm{d} K$ — the fundamental theorem of calculus applied twice, splitting at the forward. Take expectations; the linear term dies because $\mathbb{E}[S_T]=1$. For the log contract $f(1)=0$ and $f_{KK}=2/K^2$, so $w_{\mathrm{vs}}=2\int_0^1 P/K^2\mathrm{d} K+2\int_1^\infty C/K^2\mathrm{d} K$ — the familiar $1/K^{2}$ portfolio. Substituting $K=e^{k}$, $\mathrm{d} K=e^{k}\mathrm{d} k$ gives weight $2e^{-k}\mathrm{d} k$; on the put side ($k<0$) parity $P=C-(1-e^{k})$ turns the put into the call plus $(e^{k}-1)$, which is exactly the $(e^{k}-1)^-$ term of equation (3). ∎

Equation (3) is model-free: it consumes only the implied total-variance curve $w(k)$. That is its virtue — any model that can state its smile can be integrated — and, as "Evaluating the pairing inside the optimizer" will measure, its trap: some models can only state their smile by *inverting* prices.

### 2.2 Against the quantile function: the measure side

A model that owns the law of $X$ directly should never leave it.

**Proposition 2 (The quantile representation).** Let $Q$ be the quantile function of $\mu$ ($Q=$ inverse cdf). Then

$$
w_{\mathrm{vs}}=-2\,\mathbb{E}[X]=-2\!\int_0^1\!Q(u)\,\mathrm{d} u
=-2\!\int_{-\infty}^{\infty}\!Q(z)\,\Lambda(z)\big(1-\Lambda(z)\big)\,\mathrm{d} z,
\tag{4}
$$

where the last form substitutes the logit coordinate $u=\Lambda(z)=(1+e^{-z})^{-1}$, $\mathrm{d} u=\Lambda(1-\Lambda)\,\mathrm{d} z$.

*Proof.* $\mathbb{E}[X]=\int_0^1 Q(u)\,\mathrm{d} u$ is the layer-cake / inverse-cdf representation of the mean: if $U$ is uniform on $(0,1)$ then $Q(U)$ has law $\mu$. The change of variables is calculus. ∎

For the LQD model the smile *is* the pair (quantile $Q(z)$, logistic weight) on a precomputed logit grid (Note 01), so equation (4) is a single trapezoid against arrays the slice has already built — no Black inversion, no new grid, and ("Evaluating the pairing inside the optimizer") sensitivities inherited by linearity. The integrand $Q(z)\Lambda(1-\Lambda)$ decays like $|z|e^{-|z|}$ for the exponential-tailed laws LQD produces, so the model's standing grid (half-width 40) truncates it at double-precision level; Exercise 2 quantifies this.

### 2.3 Along paths: the generator side

A local-volatility model holds neither the smile nor the terminal law as a formula — pricing *any* single strike means a PDE solve. What it does hold is the generator: the local-variance field $\nu(t,x)$. Return then to the *left*-hand side of equation (2), before the log contract was ever introduced: $w_{\mathrm{vs}}=\mathbb{E}\int_0^T\nu(t,S_t)\,\mathrm{d} t$ — an accumulation along paths.

**Proposition 3 (The source PDE).** Let $g(t,x)=\mathbb{E}\big[\int_t^T\nu(s,S_s)\,\mathrm{d} s\,\big|\,S_t=x\big]$ be the expected remaining variance. Then $g$ solves the backward problem

$$
\partial_t g+\tfrac12\,\nu(t,x)\,x^{2}\,\partial_{xx}g
+\nu(t,x)=0,
\qquad g(T,\cdot)=0,
\qquad w_{\mathrm{vs}}=g(0,1),
\tag{5}
$$

and equivalently $w_{\mathrm{vs}}=\int_0^T\!\!\int\nu(t,x)\,\rho(t,x)\,\mathrm{d} x\,\mathrm{d} t=\langle \nu,\,\rho\rangle$, where $\rho(t,\cdot)$ is the forward density of $S_t$.

*Proof.* Feynman–Kac for the running-cost functional with zero terminal condition: the generator of $\mathrm{d} S=S\sqrt{\nu}\,\mathrm{d} W$ is $\tfrac12\nu x^2\partial_{xx}$, and the accumulated cost $\nu$ enters as a source. The occupation form follows by writing the expectation of the time integral as an integral against the marginal laws, $\rho(t,\cdot)$ being available from option prices as $\partial_{KK}C$ (Breeden–Litzenberger). ∎

The pairing has moved again: not payoff against terminal law, but generator against *occupation measure*. One backward solve reads off the number at $(0,1)$; no strike grid is inverted, and $g(0,1)$ is determined by the diffusion *around* $x=1$, so the read is far less sensitive to coarsening or truncating the strike grid in the wings than the $K^{-2}$-weighted replication tail — but the solve still runs on a finite domain with approximate boundary conditions, so "no truncation dependence" would be too absolute (Note 04 states the same scope). The three representations are collected in the note's central identity:

**Central equation.**

$$
w_{\mathrm{vs}}=\langle -2x,\,\mu\rangle
=2\!\int_{\mathbb{R}}\!\Big[B\big(k,w(k)\big)+(e^{k}-1)^-\Big]e^{-k}\mathrm{d} k
=-2\!\int_{\mathbb{R}}\!Q\,\Lambda(1-\Lambda)\,\mathrm{d} z
=\langle \nu,\,\rho\rangle.
\tag{6}
$$

> **Figure 2 — One number, three integrands (figure not included in this pack).** One number, three integrands (all panels production machinery). A: the strike side — the integrand of equation (3) on the running LQD slice, option quotes marked; the area is $w_{\mathrm{vs}}$. B: the measure side — the integrand of equation (4) on the same slice's logit grid; the positive left-tail lobe outweighs the negative right lobe (the skew), and the signed area is the *same* $w_{\mathrm{vs}}$ to 1.53 vol bp. C: the generator side — the local-variance field of the local-vol fit to the same quotes, with occupation-measure contours ($\rho=\partial_{KK}C$ from production prices) fanning out of the spot; the pairing $\langle \nu,\,\rho\rangle$ is read off one backward solve at the marked point $(0,1)$, and matches that surface's own strike-side value to 0.78 variance bp. Panel A's integrand peaks at the money and decays into both wings under the $e^{-k}$ weight; panel B's integrand has two signed lobes whose imbalance encodes the skew; panel C is a heat map of $\nu(t,x)$ over time and space with the occupation density's contours spreading from $(0,1)$, showing which region of the field the pairing actually weights.

> **Heuristic.** Where is the number linear? In the terminal law $\mu$, in the option prices $C(K)$, and in the quantile $Q$ — three linear pairings. It is *not* linear in the implied-variance curve $w(k)$: the smile enters equation (3) through the nonlinear map $w\mapsto B(\cdot,w)$. This is worth internalizing, because it predicts the whole cost story of "Evaluating the pairing inside the optimizer": a model parametrized in a chart where the pairing is linear (LQD: $Q$ is linear in its coefficients) gets the number and its gradient at one quadrature; a model living in the nonlinear chart pays for the coordinate change — per point, per parameter, per iteration.

**Exercise 1.** Take a flat smile, $w(k)\equiv w_0$. Show directly from equation (3) — without invoking equation (2) — that $w_{\mathrm{vs}}=w_0$. (Hint: run the spanning proof backwards: the integral is $\mathbb{E}[-2\log S_T]$ for the lognormal law with variance $w_0$, and $\mathbb{E}[\log S_T]=-w_0/2$ by the martingale normalization.) Conclude that for a flat smile the fair var-swap vol equals the implied vol exactly — so everything a var-swap quote adds beyond the ATM level is a statement about *curvature and wings*.

## 3. Where the number lives

Whose opinion is $w_{\mathrm{vs}}$? Figure 3A integrates the strike-side integrand cumulatively across the running slice: 48% of the number accrues within $|k|\le0.10$ — the belly the quotes nail — but 13% accrues *outside the entire quoted range*, where the smile is pure extrapolation. That residual share is the identifiability gap of Figure 1 made quantitative: the 30-bp disagreement between two models fitted to the same quotes lives almost entirely in that unquoted 13%. A var-swap quote is the market pricing exactly the piece the option board cannot.

> **Heuristic.** Think of the var-swap quote as one very reliable *wing quote*. Liquid options cluster near the money, where they say little about the tails; the var-swap is a traded instrument whose value loads on the $1/K^{2}$-weighted wings. Adding it to the objective is the cheapest way to discipline the extrapolation the option quotes leave free — complementary to the Lee wing control of Note 09, which constrains the wing *slope* while the var-swap constrains the wing *mass*. The extrapolated-region machinery of Notes 09/10 polices the same territory for arbitrage; this note's quote prices it.

Two sanity checks calibrate the intuition. First, the share is a statement about the *smile's* wings, not about deep-OTM dollar prices: the $e^{-k}$ weight in equation (3) decays, but the Black prices it multiplies decay much faster, so the integrand (Figure 2A) peaks at the money — the wings matter through their *width*, tens of percent of strike space each side, not through any single strike. Second, by Exercise 1 the quote adds nothing on a flat smile; its information content scales with skew. On the real SPY surface of "The real object" the published fair strikes sit up to 717 vol bp above the ATM vol — that spread *is* the priced wing mass.

## 4. Evaluating the pairing inside the optimizer

A quote is only useful if the model's own fair strike can be compared to it at every optimizer iteration — and differentiated. This section is the numerical heart of the lecture: what each representation costs, what the production grid's error actually is (and where it comes from), and the audit trail for each route.

### 4.1 The replication as a quadrature, and its error budget

Production evaluates equation (3) by a trapezoid on $k\in[-H,H]$ with $H=6$ and 801 points; the reference listing is verbatim in structure and matches production to floating-point identity ($10^{-17}$, Appendix D). Per the transfer policy it is replaced here by its exact algorithm specification.

> **Algorithm — the strike-side quadrature of equation (3) (replaces the reference listing distilled from `calib/varswap.py`; verified identical to production).**
>
> *Inputs:* a total implied-variance curve $w(\cdot)$ evaluable at arbitrary log-moneyness; a half-width $H$ (default $6.0$); a point count (default $801$).
>
> *Output:* the fair variance-swap strike $w_{\mathrm{vs}}$ in total variance.
>
> 1. Build a uniform grid of the given number of points $k_1,\dots,k_n$ on $[-H,H]$.
> 2. Evaluate the smile $w(k_i)$ at every grid point and floor it at $10^{-12}$ (the total-variance floor — the wing guard for inversion-free models whose extrapolated curve could otherwise cross zero).
> 3. Form the integrand as the OTM call leg $B(k_i, w(k_i))\,e^{-k_i}$, the normalized Black call under the $e^{-k}$ weight.
> 4. On the put side ($k_i<0$) add $1-e^{-k_i}$ to the integrand — this is the $(e^{k}-1)^{-}e^{-k}$ term of equation (3).
> 5. Return $2$ times the trapezoid-rule integral of the integrand over the grid.

Two numerical parameters, two error terms, and it pays to know which one is binding. Figure 3B measures both against the *exact* value (the closed form of Proposition 2 on the same slice — the first dividend of having two representations: one audits the other). Sweeping the half-width at a fixed fine spacing isolates *truncation*: the tails are exhausted by $H\approx2.2$, and beyond the production half-width they contribute 0.007 vol bp — the integrand of Figure 2A is dead there. Sweeping $H$ at the production point count instead lets the spacing $\Delta k=2H/(801-1)$ grow, and the error *rises* — $O(\Delta k^{2})$, the trapezoid's curvature term, doubling as $H^{2}$: 1.53 bp at $H=6$, 2.72 bp at $H=8$ (ratio $(8/6)^2$). The production setting's 1.53-bp bias is therefore *spacing*, not tails: refining to the $4001$-point diagnostics grid at the same $H$ collapses it to 0.06 bp. Widening $H$ "to be safe" at fixed points would make the estimate strictly worse.

> **Figure 3 — Where the number lives, and what the quadrature costs (figure not included in this pack).** Where the number lives, and what the quadrature costs. A: the cumulative share of $w_{\mathrm{vs}}$ across strikes on the running slice — 48% accrues in $|k|\le0.10$, but 13% accrues outside the quoted band entirely (shaded): the var-swap prices the extrapolated region. B: the replication's error budget against the exact closed form. At fixed fine spacing (teal) the error is pure truncation, exhausted by $H\approx2.2$ (the mid-sweep cusp is a sign change: left- and right-tail truncation errors briefly cancel). At the production point count (rust, dashed) the spacing grows with $H$ and the $O(\Delta k^{2})$ trapezoid term takes over, growing like $H^{2}$. The production grid ($H=6$, $801$ points, dot) carries 1.53 bp — all spacing, no tails. Panel A is a cumulative-integral curve rising from 0 to 100% across log-moneyness, steep through the belly and with its unquoted-region share shaded; panel B plots absolute quadrature error against half-width for the two sweeps, a falling truncation curve and a rising spacing curve crossing near the production point.

Why tolerate 1.53 bp in the loop at all? Because the quadrature runs at *every objective evaluation* for the models that use it, and a $5\times$ finer grid is $5\times$ the Black arithmetic in the innermost loop for an error already far below quote noise and the penalty's tolerance; the display and diagnostics path uses the $4001$-point twin of the same integrand. The floor on $w$ in the algorithm guards the inversion-free models' wings, where an extrapolated curve could otherwise cross zero.

### 4.2 The chart mismatch, as a production incident

> **Example — Case file: the fit that took minutes.**
>
> **Setup.** The first wiring of the var-swap penalty used the generic replication, equation (3), for every model — correct, uniform, and apparently innocent: the integral is just a trapezoid.
>
> **Failure mode.** LQD fits with a var-swap target went from milliseconds to *minutes* — a 158-second fit was measured — hanging the calibrate loop.
>
> **Diagnosis.** The replication consumes $w(k)$ on $801$ points. LQD does not *have* $w(k)$: it has prices, so each point is a Black *inversion* of a quadrature-priced call — the nonlinear chart of the Heuristic in "Three integrals for one pairing". Inside a finite-difference Jacobian that is $801$ root-finds per parameter column per iteration: for a nine-parameter slice, tens of thousands of inversions per iteration to price one number the model knows in closed form.
>
> **Fix.** Route each model through the representation of equation (6) native to its chart ("The three routes, costed"): LQD prices the log contract as $-2\,\mathbb{E}[X]$ on its existing quantile grid; SVI and MCS keep the replication because their $w(k)$ is arithmetic (evaluated, never solved); the local-vol surface gets the source PDE with analytic sensitivities.
>
> **Verdict.** The closed form agrees with the replication to 1.53 vol bp (each validating the other), and the var-swap penalty now costs essentially nothing in any model. *A uniform implementation is not a virtue when the models' native objects differ — evaluate a shared functional in each model's own coordinates.*

### 4.3 The three routes, costed

**LQD: the quantile side, one trapezoid.** The slice's standing grid already carries $Q(z)$ and $u(1-u)=\Lambda(1-\Lambda)$, so equation (4) is one dot product over the grid — $O(n)$ with no new function evaluations (Appendix D gives the specification). Linearity pays twice: $Q$ is linear in the slice's coefficients, so $\partial w_{\mathrm{vs}}/\partial\theta_\ell$ is the *same* quadrature applied to the basis responses — no extra solves.

**SVI and MCS: the strike side, arithmetic.** For SVI (a hyperbola, Note 02) and Multi-Core Sigmoid (a log-cosh sum, Note 03) the total variance $w(k)$ is closed-form arithmetic, so the quadrature of §4.1 is $801$ arithmetic evaluations — no inversion, negligible against the data residuals. These models were never the problem; the case file's trap was applying their route to a model in the other chart.

**Local volatility: the generator side, one backward sweep.** The production discretization of equation (5) reuses the forward Dupire march's machinery wholesale: the same $\tfrac12\nu x^{2}\partial_{xx}$ stencil, the same implicit-Euler tridiagonal factor per step, marched backward from $g(T,\cdot)=0$ with $+\nu$ as source; at the degenerate boundaries $x^2\partial_{xx}\to0$ and the rows reduce to pure accumulation $g\mathrel{+}=\Delta t\,\nu$. The number is read at the grid node $x=1$ (enforced to be one). Sensitivities come from the same factorization: differentiating the marched system in $\theta_\ell$ yields companion problems with source $\tfrac12\phi_\ell x^{2}\partial_{xx}g+\phi_\ell$ ($\phi_\ell$ the affine basis), solved as extra right-hand sides against the already-factored operator — the multi-RHS pattern of Note 04's forward sweep. When a var-swap quote frees the left-wing extrapolation slope ("Limitations"), one more column prices its sensitivity.

Figure 4 is the route's audit. Panel A compares every analytic $\partial w_{\mathrm{vs}}/\partial\theta_\ell$ against central finite differences: agreement to $1.2\times10^{-10}$ absolute across sensitivities spanning four orders of magnitude — relative error $1.7\times10^{-6}$ on the 19 of 21 parameters the horizon actually sees (the two excluded are far-wing corners of the initial time row, whose true sensitivity is $\sim10^{-11}$: no path mass ever visits them). Panel B closes the loop between representations: across horizons, the backward solve's $g(0,1)$ tracks the surface's own strike-side replication within 0.78 variance bp — two discretizations of two different integrals in equation (6), agreeing because the mathematics says they must.

> **Figure 4 — The generator-side route, audited (figure not included in this pack).** The generator-side route, audited (production local-vol machinery). A: analytic sensitivities $\partial w_{\mathrm{vs}}/\partial\theta_\ell$ from the multi-RHS backward solve against central finite differences — on the diagonal to $1.2\times10^{-10}$ across four decades; the two parameters with no path mass under this horizon are omitted. B: the source PDE's $g(0,1)$ against the same surface's static $1/K^{2}$ replication across horizons — two representations of equation (6), within 0.78 variance bp at every $T$. Panel A is a log–log scatter of analytic versus finite-difference sensitivity, all 19 live parameters sitting on the identity line across four orders of magnitude; panel B plots the two fair-strike reads against horizon, visually indistinguishable curves with their gap never exceeding 0.78 variance bp.

> **Performance.** Cost accounting per objective evaluation, $n$ grid points, $m$ parameters: LQD closed form $O(n)$ with gradient by linearity (free); SVI/MCS replication $O(801)$ arithmetic; LV source PDE one backward sweep $\approx$ one extra value solve, plus $m$ extra right-hand sides on factored tridiagonal systems ($O(n_x m)$ per step) for the full gradient. The route that was retired — replication over an inversion-priced smile — was $O(801)$ root-finds per Jacobian *column*: the measured 158-second fit. The Jacobian story is now asymmetric and worth stating exactly: for LQD the var-swap derivative is native — $\partial w_{\mathrm{vs}}/\partial\theta$ rides the analytic sensitivity pass the fit already owns, so a var-swap-targeted LQD fit never falls back — while a var-swap target on SVI or MCS still switches those fits to a finite-difference Jacobian (each column re-evaluates a cheap closed form, so the cost is benign); wiring their rows analytically remains deferred (Appendix B).

**Exercise 2.** The measure-side integrand decays like $|z|e^{-|z|}$ (exponential tails make $Q$ asymptotically linear in $z$; the logistic weight supplies $e^{-|z|}$). Bound the truncation error of equation (4) beyond the standing grid's half-width $z_{\max}=40$ by $\int_{40}^{\infty}ze^{-z}\mathrm{d} z=41\,e^{-40}$, and evaluate it. Compare with double-precision machine epsilon, and with the strike-side truncation error at $H=6$ from Figure 3B (0.007 vol bp): both representations truncate infinite integrals, but the measure side's grid was built once for *pricing*, and the var-swap rides it for free.

## 5. The quote as one more residual

The pairing priced, the quote must now *act* on the fit. Both are stated in volatility — $\sigma_{\mathrm{vs}}=\sqrt{w_{\mathrm{vs}}/T}$ — and the target enters every parametric model's least-squares stack as a single extra residual,

$$
r_{\mathrm{vs}}
=\sqrt{\lambda_{\mathrm{vs}}}\,
\big(\sigma_{\mathrm{vs}}^{\mathrm{model}}-\sigma_{\mathrm{vs}}^{\mathrm{quote}}\big),
\qquad
\lambda_{\mathrm{vs}}=p\sum_i\lambda_i ,
\tag{7}
$$

with $p$ the declared fraction (default ten percent) of the node's summed option-quote weight. Three design decisions, each doing quiet work:

*Vol units.* The data residuals are vol-metric for every model — natively for SVI/MCS, via the vega-normalized dictionary of Note 07 for LQD/LV — so equation (7) stacks onto them without a hidden exchange rate; a one-vol-point var-swap miss trades against a one-vol-point quote miss at the declared ratio and nothing else.

*A relative weight.* An absolute weight would mean something different on every node; $\lambda_{\mathrm{vs}}=p\sum\lambda_i$ makes the quote carry a declared *share* of the objective whether the node has ten quotes or a hundred (invariant 4) — the same normalization philosophy as Note 07's mean-one weights, applied to a functional observation.

*A soft target.* Equation (7) is a pull, not a constraint: the quote bargains with the option quotes at strength $p$.

The local-vol calibrator states the same trade in its own residual space. Its var-swap rows live in total variance, so the vol-space weight must be converted: a tolerance of one vol point corresponds, by $\partial w_{\mathrm{vs}}/\partial\sigma_{\mathrm{vs}}=2\sigma_{\mathrm{vs}} T$, to a total-variance tolerance $\zeta=2\sigma_{\mathrm{vs}} T\times0.01/\sqrt{\lambda_{\mathrm{vs}}}$, and the residual $(w_{\mathrm{vs}}^{\mathrm{model}}-w_{\mathrm{vs}}^{\mathrm{quote}})/\zeta$ then squares to exactly the weight of equation (7) — one functional, one weight semantics, two coordinate systems.

### 5.1 The dial, and a worked pull

Figure 5 sweeps the fraction $p$ against a quote pitched $1.5$ vol points above the running slice's natural 24.47%: the fitted fair strike rises monotonically toward the quote — the pull is a continuous dial, not a switch — reaching 25.75% at the shipped default ($p=10\%$): 85% of the gap.

> **Figure 5 — The relative-weight dial (figure not included in this pack).** The relative-weight dial (production fits at every point). A var-swap quote $1.5$ vol points above the smile's natural fair strike pulls the fitted fair strike monotonically toward it as the declared weight fraction grows; at the shipped default of ten percent the fit concedes 85% of the gap. The quote bargains — it does not dictate. The plot shows the fitted fair var-swap vol against the weight fraction $p$ on a sweep of full production fits: a smooth monotone curve rising from the natural 24.47% at $p=0$ toward the 25.97% quote, passing 25.75% at the marked default $p=10\%$.

Figure 6 shows *how* the smile pays for the pull at the default weight. Panel A: the targeted fit steepens both wings while still threading the quotes — the worst option-quote concession is 52 vol bp (against 0.2 bp for the untargeted fit): visible, bounded, and exactly the bargain $p=10\%$ declares. Panel B looks underneath, at the risk-neutral density: the extra variance is bought with tail mass on both sides, the belly barely moving — the var-swap target edits precisely the region the option quotes do not own ("Where the number lives"). Table 2 collects the numbers.

> **Figure 6 — Anatomy of a pull (figure not included in this pack).** Anatomy of a pull (running slice; quote 25.97%, default weight). A: the targeted fit (dashed) lifts its fair strike from 24.47% to 25.75% by steepening the wings, conceding at most 52 vol bp at any option quote. B: the same two fits as densities (log scale): the added variance is wing mass — both tails fatten while the belly, where the quotes live, is untouched. The target spends its budget exactly where Figure 3A said the number lives. Panel A overlays the untargeted and targeted implied-vol curves on the quotes: they coincide through the belly and separate in the wings, the targeted fit steeper on both sides. Panel B overlays the two risk-neutral densities on a log scale: the targeted density's tails sit visibly above the untargeted ones on both sides while the central mass is unchanged.

**Table 2 — The worked pull** (fresh production run): the two exact representations on the untargeted slice, and the targeted refit at the default weight.

| Quantity | Value |
|---|---:|
| Natural fair var-swap vol (closed form, equation (4)) | $24.47\%$ |
| Same slice by strike-side replication, equation (3) | $24.49\%$ |
| Representation agreement | $1.53$ vol bp |
| Var-swap quote (target) | $25.97\%$ |
| Targeted fit's fair var-swap vol | $25.75\%$ |
| Share of the gap conceded | $85\%$ |
| Worst option-quote concession | $52$ vol bp |

**Exercise 3.** Model the fit's resistance as one effective stiffness: near the optimum the fitted fair vol solves $\sigma_{\mathrm{vs}}=\sigma_{\mathrm{vs}}^{\mathrm{nat}}+\frac{\lambda_{\mathrm{vs}}}{\lambda_{\mathrm{vs}}+\kappa}\big(\sigma_{\mathrm{vs}}^{\mathrm{quote}}-\sigma_{\mathrm{vs}}^{\mathrm{nat}}\big)$ for some $\kappa$ summarizing how strongly the data-plus-ridge terms resist a wing steepening. Calibrate $\kappa$ from the default point of Figure 5 ($\lambda_{\mathrm{vs}}=0.10\times23=2.3$, conceded share 85%), then predict the conceded share at $p=2.5\%$ and compare with the figure. The one-parameter model tracks the whole dial to a few points of share — the pull really is a scalar bargain.

## 6. The real object

Figure 7 leaves the running example for the application's own output: a live SPY surface (Massive feed, 6 expiries, valuation date 2026-07-18), fitted in production with a twelve-parameter slice per expiry. The teal curve is the fair var-swap vol the application *publishes* per node; the crosses re-derive each one by Proposition 2's closed form from the stored slice parameters — agreement 0.00 vol bp, an end-to-end audit that the shipped number is the mathematics of this note and nothing else. The var-swap vol rides above the ATM vol at every expiry, by up to 717 vol bp at the long end: the skew's wing mass, priced ("Where the number lives"); the term structure of that spread is itself a tradeable object, and the calendar machinery of Note 11 consumes these per-node strikes.

> **Figure 7 — The real object (figure not included in this pack).** The real object: a live SPY surface's published fair var-swap vols across 6 expiries (teal), re-derived from the stored slice parameters by the closed form, equation (4) (crosses) — agreement 0.00 vol bp. The fair strike sits above the ATM vol (dashed) everywhere, by up to 717 vol bp at the long end: the skew's wing mass is priced into the swap, and the spread grows with the skew's room to act. The plot shows three term-structure curves against expiry: the published fair var-swap vol, the independent closed-form re-derivation sitting exactly on it (crosses on the teal curve), and the ATM vol running below both, with the var-swap-over-ATM spread widening monotonically toward the long end up to 717 vol bp.

Operationally the quote is a first-class citizen of the smile session: one scalar per node (invariant 1), shared verbatim by the parametric and local-vol views, settable, excludable and removable with a hundred-deep undo/redo history kept separate from the option-quote edits, versioned so an edit refits exactly once, and serialized with the workspace. Setting the feature off, or the node having no quote, reproduces the untargeted fit byte for byte (invariant 2) — the smile payload also carries the model's own fair strike when no quote is set, so the desk can seed a quote *at* the model before nudging it. A companion prior-side target reuses the same residual machinery to hold a fit near its prior's fair strike under the persistence framework of Note 13.

## 7. What is genuinely original here

The spanning identity is Carr–Madan; the quantile representation of a mean and Feynman–Kac are classical. The contributions are practical and, in one case, a small piece of numerical epistemology:

1. the *per-model routing* of one functional through three representations, equation (6) — closed form for the quantile-chart model, arithmetic replication for the vol-chart models, a source PDE with multi-RHS analytic sensitivities for the generator-chart model — which is what makes a var-swap target affordable *inside* the optimizer loop rather than as a post-hoc check;
2. the *relative weighting* of a functional observation, equation (7), keeping the quote's share of the objective declared and node-independent, with the exact vol-to-variance weight conversion for the local-vol residual space;
3. the *cross-representation audit discipline*: every route is checked against a mathematically distinct route of the same number (closed form vs replication at 1.53 bp; source PDE vs static at 0.78 variance bp; published app values vs re-derivation at 0.00 bp) — representations are cheap redundancy, and redundancy is how a pricing library audits itself.

One capstone completes the redundancy story from the model's side: the functional posterior band (Note 14's machinery) pushes a fitted slice's handle covariance through to a var-swap *standard deviation*, so a targeted quote can be read against the fit's own uncertainty rather than as a bare number — the fair strike arrives with an error bar computed from the same fit it summarizes.

## 8. Limitations

Where the guarantees stop. *The diffusion assumption is load-bearing*: equation (1) uses Itô on a continuous path, and under jumps the realized-variance/log-contract equivalence acquires a cubic correction: a jump of relative size $J$ contributes $2[J-\log(1+J)]-\log^{2}(1+J)=\tfrac13J^{3}+O(J^{4})$ to the gap between the replicated and realized strikes, so for jumpy underliers the quote and the replication price subtly different things — the models here fit the *diffusion* fair strike. Discrete cash dividends sit outside the clean forward-normalized derivation for the same reason. *The number inherits the model's extrapolation*: 13% of it lives beyond the quoted strikes (Figure 3A), so a var-swap-targeted fit is only as meaningful as the wing behaviour of the model absorbing it — indeed on the local-vol surface a var-swap quote deliberately *frees* the left-wing extrapolation slope so the target has a wing lever to act on; the fitted slope is then an inference, not an observation. *The strike-side quadrature carries a measured $O(\Delta k^{2})$ bias* (1.53 bp at production settings, "The replication as a quadrature, and its error budget") — far below quote noise, but a bias with a sign, and the error budget shows widening $H$ without refining $\Delta k$ worsens it. *The penalty is a pull, not a constraint*: at the default weight the fit concedes 85% of a $1.5$-point gap (Figure 5); a desk wanting the quote hit exactly must say so through the weight, and accept the option-side concessions of Figure 6A. *Provenance is the user's problem*: var-swap quotes are OTC marks, not exchange prints; the machinery applies whatever level is set, one per node, with no staleness screen of its own. And the Jacobian asymmetry: the LQD var-swap row is analytic — that deferral closed — while SVI and MCS still fall back to finite differences when a target is active, cheap here but a deliberate, documented deferral (Appendix B).

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

**Table 3 — Variance-swap hyperparameters, surfaced and hidden.**

*Surfaced (OptionsSettings):*

| Knob | Default | Role |
|---|---|---|
| `varSwapEnabled` | `true` | Master toggle (surfaces the var-swap level in the UI); the penalty activates only when a quote is set on the node. |
| `varSwapWeightPct` $p$ | $10\%$ | The quote's weight as a fraction of the node's summed option weight, equation (7). |
| `varSwapMethod` (LV) | `static` | Local-vol fair-strike pricer: strike-side replication or the source PDE, equation (5); parametric models always use their own routes. |

*Hidden:*

| Knob | Default | Role |
|---|---|---|
| `VS_HALF_WIDTH` $H$ | $6$ | Replication half-width in log-moneyness (in-loop grid). |
| `VS_POINTS` | $801$ | Replication trapezoid points (in-loop); the diagnostics/display twin uses $4001$ on the same $H$. |
| `_W_FLOOR` | $10^{-12}$ | Total-variance floor inside the integrand (wing guard). |
| `_VARSWAP_K_LO` (LV) | $0.01$ | Lower strike-ratio cutoff of the LV static replication weights. |
| `_VOL_TOL` (LV) | $0.01$ | The one-vol-point unit in the vol-to-variance weight conversion $\zeta$ of "The quote as one more residual". |
| `MAX_UNDO_DEPTH` | $100$ | Depth of the var-swap session's undo/redo stacks. |

## Appendix B. Performance notes

Protocol: timings quoted here are historical measurements from the production incident ledger (never re-timed for this edition); accuracy numbers are from this edition's generator, which runs the production code on the running slice and the standing SPY export.

1. **Retired: generic replication for LQD.** $801$ Black inversions per finite-difference Jacobian column per iteration; measured at 158 seconds for a fit that runs in milliseconds without a target. Replaced by the closed form, equation (4): one $O(n)$ quadrature on the slice's existing grid, gradient by linearity. The two routes agree to 1.53 vol bp (Table 2).
2. **SVI/MCS replication.** 801 arithmetic smile evaluations per objective call; negligible against the data residuals. The in-loop grid's 1.53-bp $O(\Delta k^2)$ bias ("The replication as a quadrature, and its error budget") is a deliberate latency/accuracy trade; the $4001$-point diagnostics twin reads 0.06 bp.
3. **LV source PDE.** One extra backward sweep reusing the forward march's factored tridiagonal steps; full analytic gradient via multi-RHS at $O(n_x m)$ per step; verified against finite differences at $1.2\times10^{-10}$ (Figure 4A). Basis precomputation is $\theta$-independent and shares the forward solver's memory-budget guard. The static route remains the shipped default; the source PDE is the wing-robust alternative a coarsened calibration grid needs — local around $x=1$, on a finite domain with approximate boundaries (the scope stated in "Three integrals for one pairing").
4. **Landed (LQD):** the var-swap and prior var-swap rows ride the analytic Jacobian — the derivative is the same quadrature applied to the basis responses, so the deferral closed at zero marginal complexity once the sensitivity pass existed.
5. **Deferred, deliberately (SVI/MCS):** those models still switch to a finite-difference Jacobian whenever a var-swap (or prior var-swap) target is active — each column re-evaluates only cheap closed forms, so the observed cost is benign; wiring their target rows into the analytic Jacobians remains shelved until it earns its complexity.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 4 — Claims in this note and the code/tests that lock them.**

| Claim | Object | Code anchor / *Test anchor* |
|---|---|---|
| Penalty pulls every model's fair strike toward the quote | equation (7) | `volfit/calib/varswap.py` / *`tests/test_varswap.py::test_penalty_pulls_model_varswap_toward_quote_all_models`* |
| LQD var-swap rows ride the analytic Jacobian (no FD fallback) | equation (4) | `volfit/models/lqd/jacobian.py` / *`tests/test_lqd_jacobian.py::test_jacobian_matches_fd_varswap_rows`; `::test_varswap_fit_ungated_and_agrees_with_fd`* |
| No target / disabled is byte-identical | invariant 2 | `volfit/calib/varswap.py` / *`tests/test_varswap.py::test_none_target_is_byte_identical`; `::test_disabling_varswap_drops_the_penalty`* |
| The pull is monotone in the weight (the dial) | Figure 5 | `volfit/calib/varswap.py` / *`tests/test_varswap.py::test_weight_strength_monotone`* |
| One quote per node; set/exclude/undo/redo; validation without mutation | invariant 1 | `volfit/api/varswap_session.py` / *`tests/test_varswap.py::test_session_set_exclude_include_remove`; `::test_session_undo_redo_and_validation`* |
| Payload carries the level and the model's own fair strike; endpoints refit and undo | "The real object" | `volfit/api/routers/varswap.py` / *`tests/test_varswap.py::test_smile_payload_carries_varswap`; `::test_varswap_endpoints_refit_and_undo`; `::test_term_reports_varswap_quote`* |
| The LV fit carries and honours the shared quote | "The three routes, costed" | `volfit/api/affine_fit.py` / *`tests/test_varswap.py::test_affine_fit_carries_and_honours_varswap`* |
| Source PDE matches static; analytic sensitivities match FD; both methods hit quotes | equation (5) | `volfit/models/localvol/varswap_pde.py` / *`tests/test_varswap_source.py::test_source_pde_value_matches_static`; `::test_source_pde_theta_sensitivity_matches_fd`; `::test_source_pde_a_sensitivity_matches_fd`; `::test_calibrate_source_pde_hits_varswaps`* |
| LQD closed form (the case-file fix) | equation (4) | `volfit/models/lqd/quadrature.py` / *`tests/test_varswap.py` (all-models pull); agreement 1.53 bp (Table 2); hero audit 0.00 bp (Figure 7)* |

## Appendix D. Reference implementation: both exact routes

Both reference listings were executed against their production counterparts by this edition's generator on every run: agreement $10^{-17}$ (floating-point identity). Per the transfer policy they are replaced here by exact algorithm specifications. The strike-side quadrature is the algorithm of "The replication as a quadrature, and its error budget" in the body; the measure side is essentially one quadrature, because the slice's pricing grid already carries everything the log contract needs (the quantile $Q(z)$ and the logistic weight $u(1-u)$; the integrand decays like $|z|e^{-|z|}$, Exercise 2):

> **Algorithm — the quantile-side closed form, equation (4): the fair strike as the mean log-return (replaces the reference listing distilled from `models/lqd/quadrature.py`).**
>
> *Inputs:* the slice's standing logit grid $z_1,\dots,z_n$; the quantile values $Q(z_i)$ on that grid; the probabilities $u_i=\Lambda(z_i)$ (the logistic function of $z_i$).
>
> *Output:* the fair variance-swap strike $w_{\mathrm{vs}}$ in total variance.
>
> 1. Form the integrand $Q(z_i)\,u_i\,(1-u_i)$ at every grid point.
> 2. Return $-2$ times the trapezoid-rule integral of that integrand over the $z$ grid — which is $-2\,\mathbb{E}[X]$ by equation (4).

## References

- [Neuberger1994] A. Neuberger. The log contract. *J. Portfolio Management*, 20(2):74–80, 1994.
- [CarrMadan1998] P. Carr and D. Madan. Towards a theory of volatility trading. In *Volatility*, Risk Books, 1998.
- [DemeterfiDermanKamalZou1999] K. Demeterfi, E. Derman, M. Kamal and J. Zou. A guide to volatility and variance swaps. *J. Derivatives*, 6(4):9–32, 1999.
- [BreedenLitzenberger1978] D. Breeden and R. Litzenberger. Prices of state-contingent claims implicit in option prices. *J. Business*, 51(4):621–651, 1978.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.


