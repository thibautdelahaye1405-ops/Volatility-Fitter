# Beyond the Last Quote

**Note 09 — what a fitter can prove, must choose, and has to police in the wings · lecture edition ("beyond the last quote") · converted from 09_wings_last_quote.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** On a live SPY surface, 48% of the strike range the application draws lies beyond the quoted board: no quote constrains it, no fit error reports it, and yet the var-swap pairing of Note 08, every tail risk metric, and the graph extrapolator of Note 14 all integrate straight through it. This lecture organizes the wing treatment shared by the four smile models around a three-way division of epistemic labour. What can be *proved*: model-free asymptotics — the total-variance wing slope of any arbitrage-free smile obeys $\beta\le2$ (derived here from first principles: along a steeper ray the far-OTM call refuses to become worthless), and Lee's moment formula $\beta=\psi(p)$ ties the slope to the tail's critical moment exponent. What must be *chosen*: inside that cone the quotes cannot select — the three parametric models fitted to one window print slopes $(0.0971, 0.1093, 0.1057)$ on the put side by three different mechanisms (structural, soft-capped, inherited), and the local-vol deep-put slope moves a two-year fair var-swap strike by 284 vol bp — each wing is a stated contract, not an estimate. What has to be *policed*: the limit is not the wing — a hat whose realized slope perturbation measures below $10^{-16}$ still drives the Durrleman density to $g=-2.0$ at $z=-2.8$, so finite-range admissibility needs its own machinery: the census-guided put-wing hinge (worst $g$ $-8.8\to-0.027$ on the synthetic arb slice, byte-identical to $1.3\times10^{-13}$ on a clean one, validated by the input/output ablation of the case file), and the *confinement principle* deciding where each constraint has jurisdiction — a two-curve constraint sampled in the extrapolated region manufactures a 142.0-variance-bp phantom violation between two fictions, while the same constraint confined to the traded range sees exactly none.

**Contents.** 1. The last quote · 2. What can be proved: the admissible cone · 3. What must be chosen: four wing contracts · 4. What has to be policed: the finite wing · 5. Where constraints have jurisdiction: the confinement principle · 6. What is genuinely original here · 7. Limitations · Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation: the Lee maps · References

## 1. The last quote

Figure 1 is a production exhibit: the longest SPY expiry from a live surface, with 48%[^1] of its drawn strike range beyond the last quote. Nobody quotes the far wings, yet everything downstream reads them: the var-swap replication integrates $1/K^{2}$-weighted prices into the tails (Note 08's pairing loads *exactly* on this region), risk metrics difference the wings, and the graph extrapolator (Note 14) inherits whatever tail the fitted model draws. Wing errors are invisible in the fit RMS — there are no quotes to miss — and surface later as a mispriced tail somewhere else.

[^1]: Share of the drawn strike range outside the prepared quotes; the drawing range itself is a display choice — see "Limitations".

> **Figure 1 — The production problem on a live SPY expiry (figure not included in this pack).** The production problem, on a live SPY expiry (2027-06, Massive feed). The prepared quotes (dots) span the shaded band; 48% of the drawn curve is extrapolation. The wing the application draws there is not an estimate — it is the model's stated law, with structural Lee slopes $\beta_L=0.422$, $\beta_R=0.054$ computed from the stored slice parameters. *Description:* A single long-dated SPY smile drawn in total variance against log-moneyness; a shaded central band marks the strike interval covered by prepared quotes (dots), and the fitted curve continues well beyond it on both sides. Nearly half of the drawn strike axis — 48% — lies outside the quoted band, and there the curve is drawn purely by the model's extrapolation law, with structural Lee slopes 0.422 on the put side and 0.054 on the call side, computed from stored slice parameters rather than any quote. The exhibit establishes the note's premise: what the application draws past the last quote is a stated law, not an estimate.

Two different things can go wrong out there, and the whole note turns on keeping them distinct. The *asymptotic* slope of total implied variance can violate a model-free bound — an arbitrage against the existence of any terminal law at all ("What can be proved: the admissible cone"). And the *finite* wing can lose density positivity even with perfectly admissible slopes — a butterfly arbitrage parked in the extrapolated region where no quote objects ("What has to be policed: the finite wing"). The first failure is excluded by theorems; the second only by machinery. Between the two sits a region the mathematics deliberately leaves open: within the admissible cone, the data cannot choose the wing, so the model must ("What must be chosen: four wing contracts").

One boundary fixes this note's scope. This note owns the strike axis *beyond* the quotes; its complement on the traded range is Note 02's belly butterfly certificate, which hard-gates readiness and publish for any displayed slice. Together the coverage is complete: certificate with teeth where the money is, this note's prove/choose/police machinery where the quotes end.

> **Invariants protected in this note.**
> 1. Every displayed wing is Lee-admissible: $\beta\le2$, structurally where possible, and by a soft cap *strictly buffered under the ceiling* otherwise ("What must be chosen: four wing contracts").
> 2. Single-slice (butterfly) constraints *extend* into the wings; two-slice (calendar) constraints are *confined* to the traded range ("Where constraints have jurisdiction: the confinement principle").
> 3. Every wing guard is strictly additive: on an already-clean slice it is byte-identical to no guard.
> 4. The tail is a property of the model's extrapolation law, not of the quotes; where the desk needs control (the local-vol deep puts) the slope is an explicit knob, and a calibrated variable exactly when an instrument exists that observes it.

**Conventions and the notation ledger.** $T$ is the expiry; $t$ appears only as the local-vol running clock. Subscripted $\partial$ for all derivatives; no primes. One vol bp is $10^{-4}$ of absolute volatility; a variance bp is $10^{-4}$ of total variance.

| Symbol | Meaning |
|---|---|
| $k,\ K=e^{k},\ F=1$ | log-moneyness; strike; forward |
| $w(k),\ B(k,w)$ | total implied variance; Black call |
| $\beta_L,\ \beta_R$ | wing slopes $\limsup w/\lvert k\rvert$ |
| $p,\ q,\ \psi$ | moment exponents; the Lee map |
| $A_L,\ A_R$ | LQD endpoint tail scales |
| $z,\ v(z),\ \sigma_{\mathrm{ref}}$ | standardized moneyness; variance; scale |
| $g(z)$ | Durrleman density factor |
| $\alpha,\ c,\ h,\ \kappa$ | a hat's amplitude, centre, width, decay |
| $\nu(t,x),\ a$ | local variance; left-slope multiplier |
| $\lambda$ | penalty weights |

*Table 1 — Every symbol in the note. $p$ and $q$ are always moment exponents (never model parameters); the SVI wing formulas use only $b,\rho$.*

## 2. What can be proved: the admissible cone

Extrapolation begins where estimation ends, so start with what holds with *no* data at all. Let $w(k,T)$ be total implied variance and define the wing slopes

$$
\beta_R=\limsup_{k\to+\infty}\frac{w(k,T)}{k},\qquad
\beta_L=\limsup_{k\to-\infty}\frac{w(k,T)}{|k|} .
$$

### 2.1 The ceiling, from first principles

**Proposition 1 (The model-free ceiling).** *For any arbitrage-free smile, $\beta_L,\beta_R\le2$.*

*Proof.* Take the right wing. Because the terminal law has a finite mean ($\mathbb{E}[S_T]=1$), dominated convergence forces the OTM call to become worthless: $C(k)=\mathbb{E}[(S_T-e^{k})^{+}]\to0$ as $k\to\infty$. Now compute what the Black functional does along a ray $w=\beta k$. Its arguments are

$$
d_{\pm}=-\frac{k}{\sqrt{w}}\pm\frac{\sqrt{w}}{2}
=\sqrt{k}\Big(\mp\frac{1}{\sqrt\beta}\pm\frac{\sqrt\beta}{2}\Big)\Big|_{\pm}
=\sqrt{k}\,\Big(\frac{\sqrt\beta}{2}-\frac{1}{\sqrt\beta}\Big)
\ \text{ for } d_{+}.
$$

If $\beta>2$ then $\sqrt\beta/2>1/\sqrt\beta$, so $d_{+}\to+\infty$ and $B(k,\beta k)=\Phi(d_{+})-e^{k}\Phi(d_{-})\to1$ (the second term vanishes: $e^{k}\Phi(d_{-})\sim e^{k}\varphi(d_{-})/|d_{-}|$ and $k+\ln\varphi(d_{-})\to-\infty$ for $\beta>2$). A smile with $w(k)\ge\beta k$ along a sequence $k\to\infty$ therefore prices calls bounded away from zero at arbitrarily high strikes — contradicting $C(k)\to0$. Monotonicity of $B$ in $w$ converts the ray statement into the $\limsup$ statement. The left wing mirrors through the put per unit of strike: $P(k)/e^{k}=\mathbb{E}[(1-S_T e^{-k})^{+}]\to\mathbb{P}(S_T=0)$ as $k\to-\infty$, while along a ray of slope $\beta>2$ the Black put forces $P(k)/e^{k}\to1$ — the entire mass at zero, impossible for a law with mean one. ∎

Figure 2B draws the proof: along rays $w=\beta k$ the production Black evaluator sends the call to $0$ for $\beta<2$ and to $1$ for $\beta>2$. The boundary ray $\beta=2$ pins the call at exactly $\tfrac12$ — also inconsistent with $C\to0$, which sharpens the statement in a way worth a remark:

**Remark 1 (The ceiling is a supremum, not a member).** $\beta_R=2$ is attainable as a $\limsup$ — $w(k)=2k-c\sqrt{k}$ type wings approach the ceiling from below — but the exact ray $w=2k$ is itself already inadmissible at large $k$. A model that caps its wing *at* $2$ must therefore approach the cap, never sit on it; the LQD guard below ($A_R<1$ strictly) is this remark in production form — and the SVI cap's $0.05$ buffer ("What must be chosen: four wing contracts") is the same remark on the other model, bought after a production SPY wing sat at exactly $2.0000$ (certification case `svi_lee_boundary`).

### 2.2 Lee's moment formula

The ceiling says how steep a wing *cannot* be. Lee's theorem says exactly how steep it *is*, in terms of the tail of the law:

**Theorem 1 (Lee [Lee2004]).** *Let $p^{*}=\sup\{p:\mathbb{E}[S_T^{1+p}]<\infty\}$ and $q^{*}=\sup\{q:\mathbb{E}[S_T^{-q}]<\infty\}$. Then* — the note's central equation —

**Central equation.**

$$
\beta_R=\psi(p^{*}),\qquad \beta_L=\psi(q^{*}),\qquad
\psi(p)=2-4\big(\sqrt{p^{2}+p}-p\big)\in[0,2].
\tag{1}
$$

*Proof sketch (the easy half).* Suppose $\mathbb{E}[S_T^{1+p}]<\infty$. From the elementary bound $(s-K)^{+}\le c_p\,s^{1+p}K^{-p}$ with $c_p=p^{p}/(1+p)^{1+p}$ (maximize over $s$), $C(K)=O(K^{-p})$. Matching this decay against the Black asymptotics of a wing of slope $\beta$ — the same $d_\pm$ computation as in Proposition 1, one order deeper — shows the call along a ray of slope $\beta$ decays like $K^{-\left(\frac{1}{2\beta}+\frac{\beta}{8}-\frac12\right)}$ up to algebraic factors; consistency forces $\frac{1}{2\beta}+\frac{\beta}{8}-\frac12\ge p$, i.e. $\beta\le\psi(p)$. Hence $\beta_R\le\psi(p)$ for every $p<p^{*}$. The converse — that the $\limsup$ *attains* $\psi(p^{*})$ — is the substance of [Lee2004]; regular-variation refinements are in [BenaimFriz2009]. ∎

**Lemma 1 (Properties of the Lee map).** *$\psi$ is a strictly decreasing bijection from $[0,\infty]$ onto $[0,2]$, with $\psi(0)=2$, $\psi(\infty)=0$, and explicit inverse $p=\tfrac{1}{2\beta}+\tfrac{\beta}{8}-\tfrac12$.*

*Proof.* Write $\psi(p)=2\big(\sqrt{p+1}-\sqrt p\big)^{2}$: the parenthesis is positive and strictly decreasing (derivative $\tfrac12(1/\sqrt{p+1}-1/\sqrt p)<0$), with limits $1$ at $p=0$ and $0$ at $\infty$. Solving $\beta=2(\sqrt{p+1}-\sqrt p)^{2}$ for $p$ is elementary algebra. ∎

> **Figure 2 — What can be proved (figure not included in this pack).** A: the Lee map $\beta=\psi(p)$ — heavier tails (smaller critical exponent) force steeper variance wings, capped at the model-free ceiling. B: the ceiling derived visually (production Black evaluator): along rays $w=\beta k$ the far-OTM call dies for $\beta<2$, is pinned at $\tfrac12$ on the boundary ray, and tends to $1$ for $\beta>2$ — a smile that steep prices calls that refuse to become worthless, which no terminal law can produce (Proposition 1). *Description:* Panel A plots the strictly decreasing map $\psi$ from the critical moment exponent $p$ to the wing slope $\beta$, running from $\psi(0)=2$ (the ceiling) down to $0$ as $p\to\infty$. Panel B evaluates the production Black call along rays $w=\beta k$ for several $\beta$ values straddling 2: the sub-ceiling rays' call prices decay to zero as $k$ grows, the ray $\beta=2$ holds the call pinned at exactly one half, and rays with $\beta>2$ push the call toward 1 — the visual form of the contradiction used in Proposition 1's proof.

> **Heuristic.** The wing slope and the tail heaviness are two faces of one coin. A fat right tail (few finite positive moments) *must* show up as a steep right variance wing; a model that draws a flat wing over a fat-tailed density is internally inconsistent and will misprice far-OTM calls. Lee's formula is not a nuisance constraint but a consistency condition between the smile and the law it implies — which is why the model built from the law outward (LQD) satisfies it automatically, and the models built from the smile outward (SVI, MCS) need a cap or a diagnosis.

**Remark 2 (Evaluating $\psi$ is itself a lesson).** The textbook form $\psi(p)=2-4(\sqrt{p^{2}+p}-p)$ subtracts two $O(p)$ quantities whose difference is $O(1)$: catastrophic cancellation. At $p=10^{16}$ it returns $-6.0$ — outside the codomain $[0,2]$ entirely — while the algebraically identical $\psi(p)=2-4/\big(\sqrt{1+1/p}+1\big)$ returns $0.0$, the correct limit to double precision. The production implementation uses the stable form ("Reference implementation: the Lee maps"); extreme exponents are not academic — they arise whenever an endpoint scale underflows ("What must be chosen: four wing contracts").

## 3. What must be chosen: four wing contracts

Everything inside the cone of "What can be proved: the admissible cone" is mathematically admissible, and the quotes — which end at the last strike — cannot select among admissible tails. Figure 3 makes the indeterminacy concrete: three parametric models fitted to the same twenty-three quotes agree to vol bps inside the window and then each draws its own wing. That divergence is not a defect to be averaged away: past the last quote a wing is a modelling *choice*, and what the fitter guarantees is not agreement but a stated, tested *wing contract* per model, with per-model teeth. Table 2 collects the fitted slopes; the four contracts follow.

> **Figure 3 — What must be chosen (figure not included in this pack).** Three models fitted to the same window (shaded) agree to vol bps where quotes exist and then diverge — each tail is the property of *its* extrapolation law, not of the identical data. All three are Lee-admissible; the data has no further opinion. Choosing a model *is* choosing an extrapolation law. *Description:* Three fitted smiles (LQD, SVI, MCS) over one shaded quote window: inside the window the three curves are visually indistinguishable, agreeing to vol basis points on the twenty-three shared quotes. Outside the window the curves fan apart, each following its own extrapolation mechanism — LQD's structural exponential-tail slopes, SVI's linear variance wings, MCS's inherited base wings. All three drawn tails are Lee-admissible (Table 2's slopes are far below the cap), so nothing in the data can prefer one over another.

| Model | $\beta_L$ (put) | $\beta_R$ (call) | mechanism |
|---|---|---|---|
| LQD | 0.0971 | 0.0358 | structural via $\psi(1/A)$ |
| SVI | 0.1093 | 0.0364 | linear $b(1\mp\rho)$, soft Lee cap |
| MCS | 0.1057 | 0.0297 | base wings, hats neutral (Proposition 2) |

*Table 2 — Analytic asymptotic wing slopes on the benchmark window (fresh production fits); all far below the operative cap 1.95, itself strictly below the ceiling 2.*

### 3.1 LQD: Lee-consistent by construction

The LQD slice (Note 01) parametrizes the log quantile density with logarithmic endpoints, which makes the return tails exactly *exponential* with scales $A_L,A_R$ read off the endpoint values of the basis expansion. The moment exponents follow in two lines: the right tail of $X=\log S_T$ decays like $e^{-x/A_R}$, so $\mathbb{E}[S_T^{1+p}]=\mathbb{E}[e^{(1+p)X}]$ converges iff $1+p<1/A_R$, giving $p^{*}=1/A_R-1$; the left tail decays like $e^{x/A_L}$ as $x\to-\infty$, so $\mathbb{E}[S_T^{-q}]=\mathbb{E}[e^{-qX}]$ converges iff $q<1/A_L$, giving $q^{*}=1/A_L$. By Theorem 1,

$$
\beta_L=\psi(1/A_L),\qquad \beta_R=\psi(1/A_R-1),\qquad A_R<1 .
\tag{2}
$$

No penalty enforces this — it is structural, the law-outward construction of the Heuristic above. The only wing constraint is the hard $A_R<1$ (finite forward; the strict inequality is Remark 1 in action), held by Note 01's soft barrier. The guards of Remark 2 handle underflowed scales: $A_R\ge1\mapsto\beta_R=2$, $A=0\mapsto\beta=0$. The hero figure's slopes $(0.422, 0.054)$ are exactly equation (2) evaluated on the stored production parameters.

### 3.2 SVI: linear wings under a soft cap

Raw SVI (Note 02) has exactly linear variance wings, $w(k)\sim b(1\mp\rho)|k|$, so $\beta_L=b(1-\rho)$ and $\beta_R=b(1+\rho)$ in closed form. Lee's bound is then one explicit inequality, $b(1+|\rho|)\le2$, enforced as a soft hinge $\max\big(b(1+|\rho|)-\beta_{\max},0\big)$ at weight $10^{3}$ alongside the min-variance penalty — with cap default $1.95$, deliberately *not* the bound itself. A hinge whose cap sits exactly at $2$ charges nothing precisely on the broken boundary ray (Remark 1), and a live SPY expiry was found parked at wing slope $2.0000$ paying no penalty; the buffered cap closed that trap, and the incident is locked as certification case `svi_lee_boundary`. On any admissible smile both hinges are exactly zero — they fence the optimizer out of the inadmissible region without touching admissible fits; the benchmark fit sits at $b(1+|\rho|)=0.1093$, far from the fence. Under the default structural fit chart (Note 02) the fence is not even reachable: both wings are strictly below the cap at every iterate by construction, and the hinge survives as the raw rollback chart's guard.

### 3.3 MCS: inherited wings, and what inheritance does not buy

The Multi-Core Sigmoid slice (Note 03) is a convex base plus up to two *zero-wing* hats.

**Proposition 2 (Zero-wing inheritance).** *Let $v(z)=v_{\mathrm{base}}(z)+\sum_r h_r(z)$ in standardized moneyness $z$, where each hat $h_r$ and its first two derivatives vanish as $z\to\pm\infty$. Then the asymptotic variance slopes of $v$ equal those of the base for any number of hats and any hat parameters; in total-variance $k$-space, with $k=\sigma_{\mathrm{ref}}\sqrt T\,z$ and $w=Tv$,*

$$
\beta_{L,R}
=\frac{\sqrt T}{\sigma_{\mathrm{ref}}}\,
\Big|S_0\mp\frac{2K_0}{\kappa_{P,C}}\Big| ,
\tag{3}
$$

*$S_0,K_0,\kappa_{P,C}$ the base's slope, kink and decay handles.*

*Proof.* $\partial_z v=\partial_z v_{\mathrm{base}}+\sum_r\partial_z h_r\to \partial_z v_{\mathrm{base}}$ as $|z|\to\infty$ since each $\partial_z h_r\to0$; the base is asymptotically linear with the stated slopes. The $k$-space conversion is the chain rule. ∎

Adding cores cannot change the wings — the entire point of the zero-wing design. But two caveats bound precisely what the proposition buys, and the second is the pivot of this lecture. First, wing-*neutral* is not wing-*admissible*: inheritance preserves whatever slopes the base fitted, and nothing in the MCS calibration bounds forces those base slopes into the Lee cone — unlike LQD (structural) and SVI (capped), MCS admissibility is *diagnosed*, not enforced. Second, the proposition pins only the *limit*: a hat can still dent the density at finite $z$, out where quotes are sparse — "What has to be policed: the finite wing" is entirely about this gap.

### 3.4 Local volatility: an explicit knob, priced by one instrument

The piecewise-affine local-vol surface (Note 04) has no closed-form implied wing. Beyond the deepest strike vertex it extrapolates the *local* variance linearly, with slope equal to a multiplier $a$ times the first interior cell's slope; the call side is flat-clamped. The multiplier's life cycle is deliberate: $a=0$ (flat clamp) on the hot path; seeded at $1.5$ when the convex-wing hinge is on; and promoted to a *free calibration variable* (box $[0,20]$) exactly when a var-swap quote is present — the one instrument that genuinely observes the deep-put tail (Note 08). Figure 4 shows why that promotion is principled rather than cosmetic: on a high-vol two-year surface, moving $a$ from $0$ to $5$ moves the fair var-swap strike by 284 vol bp. The knob is materially priced, so an instrument that trades it can identify it; absent that instrument the knob stays a stated constant, not a fitted fiction.

> **Figure 4 — The local-vol wing contract (figure not included in this pack).** The local-vol wing contract (production surface and source-PDE pricer). A: below the deepest strike vertex the local variance continues linearly with slope multiplier $a$ — a knob, not an estimate. B: the fair two-year var-swap strike moves by 284 vol bp across $a\in[0,5]$: the deep-put wing is materially priced by the var-swap, which is exactly why $a$ becomes a free variable only when a var-swap quote is present (Note 08). *Description:* Panel A shows the local-variance profile of a production surface in the deep-put region: below the deepest strike vertex several candidate linear continuations are drawn, each a different value of the slope multiplier $a$ times the first interior cell's slope. Panel B plots the fair two-year var-swap strike, computed by the source-PDE pricer, as a function of $a$ over $[0,5]$: the strike moves monotonically by 284 vol bp across the sweep. The takeaway is that the deep-put wing is a materially priced quantity — which justifies promoting $a$ to a calibrated variable exactly when a var-swap quote observes it.

**Exercise 1.** From the raw-SVI asymptotics $w(k)\to b\big(\rho(k-m)+|k-m|\big)+a$ derive $\beta_L=b(1-\rho)$, $\beta_R=b(1+\rho)$, and hence the cap $b(1+|\rho|)\le2$. Verify from Table 2 that the benchmark fit's cap value is 0.1093, and compute how much steeper the market's put skew would have to be — at this $b$ — before the fence at the shipped cap $1.95$ activates. Then repeat the computation at $2$, and say why the difference is not cosmetic (Remark 1).

**Exercise 2.** The hero slice's put slope is $\beta_L=0.422$. Invert the Lee map (Lemma 1) to find $q^{*}=0.74$: the stored SPY law has finite moments $\mathbb{E}[S_T^{-q}]$ exactly up to that order. Do the same for the call side ($\beta_R=0.054$) and conclude that the right tail is dramatically thinner — then say which of the two statements a desk should trust less, given where the quotes of Figure 1 end.

## 4. What has to be policed: the finite wing

### 4.1 The limit is not the wing

Everything so far concerned $|k|\to\infty$. The claim that now needs demolishing is the comfortable inference "the slopes are admissible, therefore the wing is fine." Density positivity at *finite* strike is governed not by slopes but by Durrleman's function

$$
g(z)=\Big(1-\frac{k\,\partial_k w}{2w}\Big)^{2}
-\frac{(\partial_k w)^{2}}{4}\Big(\frac{1}{w}+\frac14\Big)
+\frac{\partial_{kk}w}{2},
\tag{4}
$$

which is proportional to the risk-neutral density at $k$ [Gatheral2006]: $g\ge0$ everywhere is butterfly admissibility. Being second-order in the smile, $g$ responds to *curvature* — exactly what the asymptotic slope forgets.

Figure 5 is the lecture's thesis in one exhibit, built from the production hat kernels. A single zero-wing hat is added to a clean base: the realized wing slopes change by less than $10^{-16}$ (measured at $k=\pm2.5$: $1.0\times10^{-17}$) — Proposition 2 doing its job — while $g$ is driven to $-2.0$ at $z=-2.8$, deep in the put wing, on a base whose own $g$ stays above 0.14 throughout the range. *The limit theorem is satisfied and the smile is arbitrageable*: asymptotic admissibility and finite-range admissibility are independent failures, and the second needs its own police.

> **Figure 5 — The limit is not the wing (figure not included in this pack).** The limit is not the wing (production sigmoid kernels). A: a single zero-wing hat added to a clean base — the tails coincide, and the realized wing-slope change measures below $10^{-16}$. B: the same hat drives Durrleman's $g$ (equation (4)) to $-2.0$ at $z=-2.8$ while the base stays positive: a butterfly arbitrage manufactured at finite strike with the asymptotics untouched. Admissible slopes do not make an admissible wing. *Description:* Panel A overlays the clean base variance curve and the same curve with one zero-wing hat added: the two curves differ visibly only around the hat's centre, and in the far tails they coincide — the realized wing-slope perturbation, measured at $k=\pm2.5$, is $1.0\times10^{-17}$, at the floating-point noise floor. Panel B plots Durrleman's $g$ for both curves: the base's $g$ stays above 0.14 across the whole drawn range, while the hatted curve's $g$ plunges to $-2.0$ at $z=-2.8$, deep in the put wing. Together the panels prove that a smile can pass the asymptotic slope test perfectly and still carry a finite-strike butterfly arbitrage.

**Exercise 3.** Make the mechanism quantitative. In standardized coordinates the last term of equation (4) is $\partial_{kk}w/2=\partial_{zz}v/(2\sigma_{\mathrm{ref}}^{2})$. For a hat of amplitude $\alpha<0$, width $h$ and decay $\kappa$, its peak negative curvature scales like $|\alpha|\kappa^{2}$ (differentiate the kernel twice). Estimate the amplitude at which the hat of Figure 5 ($\kappa=4$, shoulder near $z=-2.8$, base $g\approx0.2$ there) first pushes $g$ negative, and compare with the drawn $\alpha=-0.07$. Conclude that hats buy *local* explanatory power at a curvature cost the asymptotic theory never sees — which is why their number is capped and their playground policed.

### 4.2 Where the failures actually live: the census

The backtest's arbitrage census located the MCS's finite-wing failures precisely: 64% of butterfly violations sit in the *put* wing (median worst-violation location $z\approx-3.2$), against 4% at the money — hats fitted to sparse illiquid quotes buy in-sample RMS by denting the density where no quote objects. The census itself needed a measurement lesson first: with finite-difference $g$ estimates, 28% of LQD fits appeared to violate; with analytic $\partial_k w, \partial_{kk}w$ per model, the LQD "violations" vanished entirely (structural positivity confirmed) while the MCS ones survived — measure with derivatives you trust before you legislate. (Historical numbers throughout this subsection and the case file are quoted from the stored backtest artifacts, never re-run; "Performance notes" states the provenance.)

### 4.3 The put-wing hinge

The shipped defence has three parts, each aimed by the census:

1. **A capacity cap.** The core count is clamped to $\le2$ at the schema (and to $(n_{\mathrm{quotes}}-6)/4$ in the calibrator): most historical violations came from high-core fits chasing noise.
2. **A one-sided Durrleman hinge.** The refine stage carries residual rows $\sqrt{\lambda_{\mathrm{w}}}\max(-g(z_m),0)$ on a $49$-point grid extending *two standardized units past the traded range* on both sides, with the put side weighted $2\times$ (where the census says the risk lives). The weight is a declared fraction of the $10^{3}$ base (default 100%).
3. **A hybrid Jacobian.** The $g$ rows are finite-differenced, one column at a time, while the quote/ridge/calendar blocks keep their analytic Jacobian — the penalty costs little and perturbs nothing when inactive.

Figure 6 shows the hinge at work on this edition's synthetic arb slice (quotes generated by a hat-broken smile): the unpenalized two-core fit reproduces the arbitrage at $g=-8.8$; with the hinge on, the fit refuses it, $g\ge-0.027$, conceding visible smoothness through the pathological quotes instead. On the clean benchmark slice the penalty rows are identically zero and the fit is unchanged to $1.3\times10^{-13}$ in total variance (invariant 3). On real illiquid wings the stored EEM result is a ≈400× median repair ($-7.86\to-0.019$) at $+79$ bp of in-sample cost.

> **Figure 6 — The police at work (figure not included in this pack).** The police at work (production calibrator, synthetic arb quotes). A: penalty off, the two-core fit tracks every pathological quote; penalty on, it concedes in-sample fit to stay admissible. B: the Durrleman view — worst $g$ goes $-8.8\to-0.027$. The hinge grid (shaded) deliberately extends two standardized units past the traded range: a one-curve constraint is enforced *into* the wings, per the principle of "Where constraints have jurisdiction: the confinement principle". *Description:* Panel A shows two MCS fits to the same synthetic hat-broken quotes: with the penalty off, the two-core fit threads every pathological quote exactly; with the penalty on, the fit visibly smooths through them, trading in-sample accuracy for admissibility. Panel B plots the corresponding Durrleman $g$ curves over the hinge grid, whose shaded extent runs two standardized units past the traded range on both sides: the unpenalized fit's worst $g$ is $-8.8$, the penalized fit's worst is $-0.027$ — essentially at the admissibility boundary. The hinge is one-curve machinery deliberately extended into the wings.

> **Example — Case file: the MCS that invented a put wing.**
>
> **Setup.** The three-regime backtest sweep: the Multi-Core Sigmoid on illiquid single names, where the put wing has a handful of wide quotes.
>
> **Failure mode.** The two-core fit improved in-sample RMS over the zero-core fit — and carried genuine butterfly arbitrage on 76% of arb-prone nodes, almost all in the put wing: a hat parked where no quote could object, buying RMS with a fake weekend wing.
>
> **Diagnosis.** The analytic (FD-free) arb metric separated real violations from finite-difference noise ($28\%\to0$ for LQD — structural positivity confirmed — while the MCS violations survived); the census then localized them: put wing, $z\approx-3.2$.
>
> **Fix.** The two-core cap plus the put-weighted hinge above (output side), composing with the de-Americanization convexity repair of Note 05 (input side).
>
> **Verdict (ablation, test-locked).** On the arb-prone illiquid population (38 census nodes, medians): with neither fix, worst $g$ $-30.4$, arbitrage on 100%, in-sample 92 bp. Input repair alone: arbitrage cut ≈3× *and* RMS improved to 25 bp — the model had been chasing arbitraged de-Am inputs. Output penalty alone: arbitrage essentially eliminated ($g\ge-0.02$) but at 749 bp — brutal, because the model must fight its own corrupted inputs. Both: the penalty's arbitrage removal at 225 bp. One real node makes it concrete — EFA in the Aug-2024 vol spike, 11 days out, 22 quotes: 75 bp at $g=-116$ with neither defence; 18 bp but $g=-12$ with the repair alone; arb-free at 726 bp with the penalty alone; arb-free at 34 bp with both. *Complementary, not redundant: the input repair makes the output penalty affordable.* On liquid names both are byte-identical no-ops.

## 5. Where constraints have jurisdiction: the confinement principle

The hinge of "What has to be policed: the finite wing" is enforced *past* the quoted range; the calendar floor of Note 10 is enforced *only inside* it. Both choices are correct, and four production incidents — the phantom calendar violations (Note 10's case file), the local-vol convex-wing regression (Note 04), the de-Am global-repair revert (Note 05), and the put-wing penalty above — resolve into one rule for telling them apart.

> **Heuristic — The confinement principle.** *A constraint that compares two curves must be sampled only where data pins both; a constraint intrinsic to one curve must hold everywhere, wings included.* A two-curve constraint evaluated where both sides are extrapolation can only compare two fictions — any "violation" there is an artefact of the extrapolation laws, and enforcing it lets the fiction corrupt the fit where data *does* live. A single-curve constraint (density positivity, call convexity) is a property of the law itself: it has no rival extrapolation to be spuriously violated against, and abandoning it in the wings is exactly how fake tails are born.

Figure 7 manufactures the two-curve failure from two clean production fits. A steep short slice and a flatter long slice satisfy the calendar order everywhere the data lives: sampled on the confined floor grid, the worst violation is 0.0 variance bp — none. Sampled on a wide grid running to $|k|=1$, the two *extrapolations* cross and a phantom violation of 142.0 variance bp appears — between two curves, at strikes where neither has ever seen a quote. Enforcing it would bend both fits where the data does live to fix a disagreement between fictions; the production floor grid is confined to the observed span for exactly this reason.

> **Figure 7 — The phantom a wide grid manufactures (figure not included in this pack).** The phantom a wide grid manufactures (two clean production SVI fits). Inside the traded range the calendar order $w(k,T_2)\ge w(k,T_1)$ holds with margin (worst violation 0.0 bp). In the extrapolated region the near slice's steeper stated wing overtakes the far slice's — a 142.0-variance-bp "violation" between two fictions (highlighted), visible only to the wide sampling grid (lower ticks). The production floor grid (upper ticks) is confined to the data span: two-curve constraints have no jurisdiction where neither curve is pinned. *Description:* Two total-variance curves from clean production SVI fits — a steep short-dated slice and a flatter long-dated one — drawn over $k\in[-1,1]$ with the traded span shaded. Inside the span the far curve sits above the near curve everywhere (worst violation 0.0 variance bp). Outside the span the near slice's steeper linear wing crosses above the far slice's flatter wing, and a highlighted region marks the resulting 142.0-variance-bp phantom "violation" — a disagreement between two extrapolations at strikes where neither expiry has a quote. Two rows of ticks show the two sampling grids: the wide diagnostic grid sees the phantom; the confined production floor grid never samples there.

| Constraint | Curves | Treatment | Where |
|---|---|---|---|
| Calendar floor $w_{\mathrm{far}}\ge w_{\mathrm{near}}$ | two | **confined** to traded range | Note 10 |
| LV convex-wing hinge | two[^2] | **confined** to the extrapolation tail below the deepest quote | Note 04 |
| MCS Durrleman $g\ge0$ | one | **extended** $\pm2$ ATM-std past quotes | "What has to be policed: the finite wing" |
| De-Am call convexity | one | **extended** to the wings, but band-constrained and ATM-core-fixed | Note 05 |

[^2]: The LV wing hinge compares the model's wing against the *quotes'* implied shape when sampled inside the quoted range — the regression of Note 04 — so it behaves as a two-curve constraint and is confined; in the pure extrapolation tail it degenerates to a one-curve convexity preference, which is where it is allowed to act.

The de-Am row is the principle's refinement rather than an exception: the *constraint* (convexity, one-curve) rightly extends into the wings, but the *repair* it licenses is confined — to the quoted bid–ask band and away from the ATM core — because a repair, unlike a constraint, moves prices. Extending a one-curve constraint is safe; extending a repair's *authority* unboundedly is how a 27% put wing became 104% (Note 05).

**Remark 3 (Open problem: softer two-curve enforcement in the wings).** Confinement as stated is binary: a two-curve constraint is either sampled (inside the traded range) or ignored (outside). But the extrapolated region is not uniformly worthless — just past the last quote the options still carry genuine premium, and there a calendar inversion between two *stated* wing contracts ("What must be chosen: four wing contracts") is a real inconsistency even if no quote witnesses it. Whether two-curve constraints deserve *softer* enforcement in the near-extrapolation region — weight decaying with distance past the last quote, or with remaining time value — is open (flagged 2026-07), to be settled jointly with Note 10's floor-grid construction. Three production phases already frame it: Phase 1, the Quality report *measures* the region (worst Durrleman $g$, calendar crossings and wing-slope order over the time-value envelope), advisory only, never gating readiness. Phase 2, an opt-in tapered enforcement (off by default) adds exactly those three hinges to the SVI/MCS overlay fits, budgeted in vol units at a fraction of the data weight so it leans without outvoting quotes; the far-field calendar order is enforced through the *scalar* wing-slope condition, never pointwise — and the same toggle arms the LQD surface's per-interface tail contract under the symmetric solver: two seam price rows just beyond the span union and two wing-slope-order rows, so the toggle is not overlay-only. Phase 3, a publish-time wing-only projection lifts exported curve samples onto the discrete arbitrage-free cone in OTM-price space, traded core pinned byte-identically, fits and in-app views untouched — a repair, so its *authority* is confined to the wings even though the constraints it restores extend there; the export manifest audits it via `projectionCalendarWorstBp`, the field that licenses a price-moving repair at the boundary at all. Note 10's matching remark carries the mechanism and the measured lean/cost trade. All three phases are certification-locked together as case `extrap_wing_contracts`; what stays open is doctrine, not machinery.

## 6. What is genuinely original here

The Lee theory is classical; the contributions are structural.

1. The *prove/choose/police division* as an engineering discipline: the same slope $\beta$ is computed three structurally different ways (equation (2), the SVI closed forms, equation (3)) and shown to agree in ordering on one window, so model choice is a choice of *how* to extrapolate, never *whether* the extrapolation is admissible — and each model's contract states which of the three verbs guards it (structural / capped / diagnosed / knob).
2. The *census-guided* put-wing regularizer: placed where the measured violations live, weighted by their measured asymmetry, and validated by an ablation that also proved it composes with the input-side repair rather than duplicating it.
3. The *confinement principle* with its two-curve/one-curve criterion — four hard-won production incidents compressed into one transferable design rule, exhibited here (Figure 7) as a measured phantom rather than an anecdote.

## 7. Limitations

Where the guarantees stop. *MCS base admissibility is diagnosed, not enforced*: Proposition 2 protects the wings from the hats, but nothing bounds the base slopes into the Lee cone — the diagnosis lives in the quality report, not the optimizer. *The ceiling is open at the top* (Remark 1): a model pinned exactly at $\beta=2$ is already wrong, which is why the LQD barrier keeps $A_R<1$ strictly and the SVI cap is a fence set strictly inside the cone ($1.95$), not a target. *The historical numbers are population-specific*: the census asymmetry (64% put wing) and the ablation grid were measured on the illiquid single-name population of one backtest campaign; the hinge's put-side $2\times$ weighting hard-codes that asymmetry until a new census says otherwise. *The hero share is a display statement*: 48% quantifies the drawn curve, whose strike range is itself a UI choice — the economically weighted share (by time value or var-swap mass, Note 08) is smaller but still material. *The hinge's Jacobian is hybrid*: the 49 finite-differenced rows are cheap, but a fully analytic $g$-row Jacobian remains undone. And *confinement is binary* (Remark 3): the near-extrapolation region — real premium, no quotes — currently gets measurement (Phase 1), opt-in leaning (Phase 2) and boundary repair at publish (Phase 3), all three certification-locked (`extrap_wing_contracts`) — but not settled doctrine.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

**Surfaced**

| Knob | Default | Role |
|---|---|---|
| `sivWingPenaltyPct` | 100 | Put-wing Durrleman hinge strength (% of the $10^{3}$ base weight); 0 disables. |
| `nCores` | 2 (max 2) | MCS core count, schema-clamped ("What has to be policed: the finite wing"). |
| `leeSlopeMax` | 1.95 | SVI Lee cap $b(1+\lvert\rho\rvert)\le\beta_{\max}$, strictly buffered under Lee's bound ($\beta=2$ is the broken boundary, Remark 1; certification case `svi_lee_boundary`). |
| `sviPenaltyWeight` | $10^{3}$ | Weight of the SVI Lee / min-variance hinges. |
| `leftWingSlopeMult` | 1.5 | LV left extrapolation slope seed; free variable (box $[0,20]$) under a var-swap quote. |
| `lvVolCapMult` | 3.0 | LV local-vol cap multiple (Note 04). |
| `convexWing` | `false` | LV convex-wing hinge, confined to the $5\Delta$ tail beyond the deepest quote. |
| `extrapEnforce` | `false` | Phase-2 tapered extrapolated-region hinges (Remark 3). |

**Hidden**

| Knob | Default | Role |
|---|---|---|
| `_WING_PAD` | 2.0 | The $g$-grid extends $\pm2$ standardized units past the traded range. |
| `_WING_GRID` | 49 | Points on the $g$-grid. |
| `_WING_PUT_FACTOR` | 2.0 | Extra weight on the put side (the census asymmetry). |
| `EPS_AR` | $10^{-6}$ | LQD $A_R<1$ buffer; the only LQD wing constraint (Note 01, Remark 1). |
| `VAR_FLOOR_N_DATA` | 41 | Points of the confined calendar floor grid (traded span); the wide diagnostic grid is 161 points on $[-1,1]$. |

*Table 3 — Wing-related knobs (cross-model).*

## Appendix B. Performance notes

Protocol: fresh numbers in this edition (slopes, hinge repair, byte-identity, phantom sizes, the LV var-swap swing) are produced by the generator running production code; historical backtest numbers (the census shares and location, the $28\%\to0$ analytic-metric episode, the EEM 400× repair, the ablation grid 92/25/749/225 bp and the EFA node) are quoted from the stored artifacts `backend/backtest/FINDINGS_calibration_arb.md`, `FINDINGS_ablation_arb.md` and `results/spike_aug2024_ablation_arb_EEM_EFA_2d.json`, and are never re-run by a documentation build.

1. Wing handling is essentially free: LQD slopes are a by-product of the endpoint scales; SVI/MCS slopes are closed forms of fitted parameters; the LV wing is part of the surface solve.
2. The put-wing hinge adds 49 residual rows in the refine stage only, with a hybrid Jacobian (analytic blocks untouched, $g$ rows by central differences); on a clean slice the rows are zero and the optimum is unchanged to $1.3\times10^{-13}$.
3. The analytic arb metric replaced a double numerical-gradient pass on 201 points with closed-form $\partial_k w,\partial_{kk}w$ per model — more accurate *and* cheaper; it is what made the census trustworthy ("What has to be policed: the finite wing").
4. Confinement reduces work by not over-constraining the extrapolation region: the floor grid is 41 points on the data span instead of 161 on $[-1,1]$.
5. The stable $\psi$ evaluation (Remark 2) costs one extra division and removes an entire class of underflow misreads at extreme endpoint scales.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

| Claim | Object | Code anchor · *Test anchor* |
|---|---|---|
| LQD structural Lee slopes; underflow-safe | equation (2) | `volfit/models/lqd/basis.py` · *`tests/test_lqd_basis.py::test_svi_fit_lee_slopes_match_note`; `::test_lee_slopes_handle_underflowed_endpoint_scales`* |
| Buffered SVI cap: the $\beta=2$ boundary trap is closed | Remark 1 | `volfit/models/svi_jw/calibrate.py` · *`tests/test_svi_lee_boundary.py`; certification case `svi_lee_boundary`* |
| Three extrapolated-region phases (measure / lean / repair) | Remark 3 | `volfit/calib/extrap.py` / `volfit/models/projection.py` · *`tests/test_extrap_enforce.py`; `tests/test_wing_projection.py`; certification case `extrap_wing_contracts`* |
| SVI Lee cap enforced | "What must be chosen: four wing contracts" | `volfit/models/svi_jw/calibrate.py` · *`tests/test_svi_calibrate.py::test_respects_lee_wing_bound`* |
| MCS hats are zero-wing | Proposition 2 | `volfit/models/sigmoid/sigmoid.py`, `kernels.py` · *`tests/test_sigmoid_model.py`* |
| Two-core cap (schema and calibrator) | "What has to be policed: the finite wing" | `volfit/api/schemas.py`, `volfit/models/sigmoid/calibrate.py` · *`tests/test_siv_wing_penalty.py::test_cores_clamped_to_two`* |
| Put-wing hinge removes wing arb; byte-identical on clean slices | Figure 6 | `volfit/models/sigmoid/calibrate.py` · *`tests/test_siv_wing_penalty.py::test_penalty_removes_wing_arb`; `::test_penalty_byte_identical_on_arb_free_slice`* |
| Analytic FD-free arb metric | "What has to be policed: the finite wing" | `backend/backtest/dispatch.py`, `volfit/models/sigmoid/kernels.py` · *`tests/test_backtest_arb.py`* |
| Input/output ablation: complementary | case file | `backend/backtest/ablation_arb.py` · *`tests/test_ablation_arb.py`* |
| De-Am wing repair (input side; confined authority) | "Where constraints have jurisdiction: the confinement principle" | `volfit/calib/convex_deam.py` · *`tests/test_convex_deam.py`* |
| Calendar floor confined (two-curve) | Figure 7 | `volfit/calib/calendar.py` · *`tests/test_overlay_calendar.py::test_wide_grid_breaks_svi_but_data_grid_does_not`* |
| LV convex wing confined to the tail | "Where constraints have jurisdiction: the confinement principle" | `volfit/api/affine_fit.py` · *`tests/test_affine_grid_design.py::test_convex_wing_confined_to_quoted_extrapolation`* |

*Table 4 — Claims in this note and the code/tests that lock them.*

## Appendix D. Reference implementation: the Lee maps

Both procedures below were executed against their production counterparts by this edition's generator on every run: $\psi$ over $p\in[10^{-4},50]$ and the slopes on the benchmark fit agree to $1.0\times10^{-17}$ (floating-point identity). The $\psi$ procedure is the production *stable* form of Remark 2 — the naive textbook expression is reproduced only to exhibit its failure ($-6.0$ at $p=10^{16}$).

> **Algorithm — Lee's $\psi$ (stable form) and the LQD structural wing slopes from the endpoint scales.** (Replaces the reference-implementation listing, distilled from the LQD basis module; the pack carries no source code.)
>
> *Inputs:* for the map, a moment exponent $p>0$; for the slopes, the LQD endpoint tail scales $A_L\ge0$ and $A_R\ge0$. *Outputs:* the wing slope $\beta=\psi(p)$; the slope pair $(\beta_L,\beta_R)$.
>
> 1. **Stable Lee map.** Evaluate $\psi(p)=2-4\big/\big(\sqrt{1+1/p}+1\big)$. This form is algebraically identical to the textbook $\psi(p)=2-4(\sqrt{p^{2}+p}-p)$ but contains no subtraction of two $O(p)$ quantities, hence no catastrophic cancellation; $\psi$ is decreasing with $\psi(0)=2$ and correct limits at extreme $p$ (in particular $\psi(10^{16})$ evaluates to $0.0$, not $-6.0$).
> 2. **Left slope.** If $A_L>0$, the left return tail is exponential with scale $A_L$, so the left critical exponent is $q^{*}=1/A_L$ and $\beta_L=\psi(1/A_L)$. If $A_L=0$ (underflowed scale), set $\beta_L=0$.
> 3. **Ceiling guard (right side).** If $A_R\ge1$, return $(\beta_L,\,2.0)$: the right tail admits no finite forward moment margin and the slope saturates at the model-free ceiling.
> 4. **Right slope.** Otherwise, if $A_R>0$, the right critical exponent is $p^{*}=1/A_R-1$ and $\beta_R=\psi(1/A_R-1)$; if $A_R=0$, set $\beta_R=0$.
> 5. Return $(\beta_L,\beta_R)$.
>
> *Production-agreement tolerance:* $1.0\times10^{-17}$ (floating-point identity) on every generator run, over $p\in[10^{-4},50]$ for the map and on the benchmark fit for the slopes.

## References

- [Lee2004] R. W. Lee. The moment formula for implied volatility at extreme strikes. *Mathematical Finance*, 14(3):469–480, 2004.
- [BenaimFriz2009] S. Benaim and P. Friz. Regular variation and smile asymptotics. *Mathematical Finance*, 19(1):1–12, 2009.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006. (The density factor $g$.)
- [GatheralJacquier2014] J. Gatheral and A. Jacquier. Arbitrage-free SVI volatility surfaces. *Quantitative Finance*, 14(1):59–71, 2014.


