# The Premium You Never Observe

**Note 05 — early exercise, optimal stopping, and de-Americanization · lecture edition ("the subtraction that removes it from a quote") · converted from 05_deamericanization_stopping.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> A listed American option quote is the value of an optimal-stopping problem, not of a terminal expectation — and every volatility model in this series prices terminal expectations. The difference between the two, the early-exercise premium, is nonnegative, often zero, sometimes hundreds of basis points of implied volatility, and *never directly observable*: the market quotes one number, and the premium inside it must be inferred. This lecture develops the standard desk repair, de-Americanization, as an exercise in removing an unobservable nuisance with a model in which it cancels. We first locate the nuisance: optimal-stopping theory says exactly when the premium vanishes (never for a call on a name that pays no dividends — a theorem of Merton's) and where it concentrates (deep in-the-money puts under positive rates; calls near dividends), so the whole strike–maturity plane is mapped before anything is subtracted. The subtraction itself is a one-dimensional root find through a Cox–Ross–Rubinstein tree — the classical monotone scheme for the obstacle problem — and the reason it works is a control-variate identity: at the root, the model's premium cancels the market's, and most of the tree's own discretization error cancels between its American and European legs, leaving the reported quote carrying only the European-leg gap (1.2 vol bp at the production batch depth on the worked example, 0.30 at the scalar depth). The mathematics is then held to production discipline: a forward-consistent escrowed cash-dividend tree, spread-preserving subtraction, loud scalar failures and silent batch `NaN` lanes, an 86× compiled kernel behind an unchanged public dispatch, a content cache that scopes the cost to genuine data changes, and a wing-only, band-constrained convex repair for the butterfly arbitrage that per-strike inversion leaves behind — including the reverted global repair that taught the locality rule. On a synthetic 6%-dividend name the naive European inversion is biased by up to 282 vol bp; on a captured SPY chain the same wedge runs to a median 519 vol bp — but only on deep ITM puts the fitter *discards*; on the quotes production actually fits, the premium is worth a median $|\cdot|$ of 4.2 vol bp, maximum 60. Knowing which of those numbers to quote is, in miniature, what this note is about.

**Contents**

1. A quote that lies about volatility
2. Where the premium lives: a little optimal stopping
3. Where the subtraction sits
4. The pricing map
5. The inversion as a control variate
6. The error budget, measured
7. A worked example, by the numbers
8. The cost of a chain, and how it was made to vanish
9. The wings: an approximate projection
10. Real chains, honestly labelled
11. What is genuinely original here
12. Limitations
Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation: convexity building blocks · References

---

## 1. A quote that lies about volatility

Every model in this series prices the same object: the normalized European call,

$$
c(k)=\mathbb{E}^{T}\!\big[(e^{X_t}-e^{k})^+\big],\qquad
X_t=\log(S_t/F),
\tag{1}
$$

a *terminal* expectation under the $t$-forward measure. A US-listed single-stock or ETF option is a different asset. Its holder may exercise at any moment, so its price is the value of an *optimal-stopping* problem, and it decomposes as

$$
A \;=\; E \;+\; \pi,\qquad \pi\ge0,
\tag{2}
$$

where $E$ is the European value the fitter wants and $\pi$ — the early-exercise premium — is the value of the right to stop early. The market prints $A$. It does not print $E$, and it does not print $\pi$: the decomposition (2) is real but unobservable, quote by quote. Feed $A$ into any European inversion and the machinery has no slot for $\pi$, so it books the whole premium as volatility. The smile comes out biased upward — and, as we will see, biased worst precisely where the fitter can least afford it.

This note is the story of how the implementation removes $\pi$ without ever observing it. The plan of the lecture: first say exactly *where* $\pi$ lives, using the little optimal-stopping theory that decides when it is zero ("Where the premium lives: a little optimal stopping"); place the removal step inside the quote pipeline ("Where the subtraction sits"); build the pricing map — a Cox–Ross–Rubinstein tree with a forward-consistent dividend model — and establish the monotonicity that makes inversion well posed ("The pricing map"); expose the inversion as a control variate and account for every basis point of its error budget ("The inversion as a control variate", "The error budget, measured", "A worked example, by the numbers"); count its cost and how production made that cost vanish ("The cost of a chain, and how it was made to vanish"); repair the one arbitrage the per-strike construction leaves behind ("The wings: an approximate projection"); and close with real-chain evidence, honestly labelled ("Real chains, honestly labelled"), what is original ("What is genuinely original here"), and where the guarantees stop ("Limitations").

> **Invariant — invariants protected in this note.** The de-Americanization machinery protects five production invariants:
> 1. European chains are untouched — every step below is a byte-identical no-op unless the snapshot declares itself American.
> 2. One premium per strike, subtracted from bid, mid and ask alike: the quoted *dollar spread* survives de-Americanization.
> 3. A failed inversion never invents an adjustment: the premium is taken as zero and the raw band falls through to the European static-bound filters.
> 4. The dense at-the-money core is never moved by the convexity repair ("The wings: an approximate projection").
> 5. Fit settings — model choice, penalties, weights, optimizer tuning — never re-run the trees (the prepared-quote cache, "The cost of a chain, and how it was made to vanish").

**Conventions and the notation ledger.** $S$ is spot; $F$ the forward and $D$ the discount factor to expiry (both resolved from the chain itself, Note 06); $K$ a strike and $k=\log(K/F)$ its log-moneyness; $r=-\log(D)/t$ and $q=r-\log(F/S)/t$ the continuously compounded rate and carry yield the pair $(F,D)$ implies. $t$ is the *calendar* year fraction to expiry — the clock every tree in this note marches on — and $\tau$ the event-weighted variance-clock years (Note 00), which appears exactly twice ("Where the subtraction sits", "The cost of a chain, and how it was made to vanish"). $w=\sigma^2\tau$ is total implied variance, $z=k/\sqrt{w_{\mathrm{atm}}}$ standardized moneyness. Dollar quotes are $P^{\mathrm b}\le P^{\mathrm m}\le P^{\mathrm a}$ (bid, mid, ask); a *normalized call* is $c=P/(DF)$ plus the parity shift of equation (5). One *vol bp* is $10^{-4}$ of absolute volatility. One differentiation convention throughout: a subscripted $\partial$ is a partial derivative ($\partial_\sigma B$, $\partial_{KK}C$); no primes.

**Table 1 — Every symbol in the note.** The up-probability $p$ is the only $p$; prices are capital letters.

| Symbol | Meaning |
|---|---|
| $S,\ F,\ D$ | spot, forward, discount |
| $K,\ k,\ z$ | strike; $\log(K/F)$; standardized |
| $t,\ \tau$ | calendar years; variance-clock years |
| $r,\ q$ | rate and carry implied by $(F,D)$ |
| $A(\sigma),\ E(\sigma)$ | American / European tree price |
| $N,\ \Delta t,\ u,\ d,\ p$ | tree depth, step, moves, up-probability |
| $\pi,\ \hat\pi$ | premium $A-E$; its estimate, equation (4) |
| $\sigma,\ \sigma^*$ | volatility; the de-Am root, equation (9) |
| $B(k,w)$ | normalized Black call |
| $c,\ w$ | normalized call; total variance |
| $P^{\mathrm b},P^{\mathrm m},P^{\mathrm a}$ | dollar bid / mid / ask |
| $\vartheta,\ \mathcal T_{[0,t]}$ | a stopping time; all of them |
| $\delta_i,\ t_i,\ \alpha$ | cash dividends, ex-dates, rescale |
| $\Delta^2_i$ | divided second difference, equation (11) |

### 1.1 The dictionary between price error and vol error

How much implied volatility does a dollar of unremoved premium buy? To first order, an error $\Delta P$ in the price input moves the inverted vol by $\Delta\sigma\approx\Delta P/\partial_\sigma B$ — divide by vega. Vega peaks at the money and collapses in the wings and deep in the money, so a *fixed* dollar premium translates into a *large* spurious vol move exactly where vega is small. Figure 1 runs the experiment on the note's synthetic running example — American calls on a stock paying a 6% dividend yield against a 2% rate, true volatility 25%, six months — and Figure 2 audits the dictionary: the predicted bias $\pi/\partial_\sigma B$ tracks the measured bias to 1.4 vol bp on the out-of-the-money strikes and under-predicts deep in the money, where the premium is no longer an infinitesimal perturbation. The worst measured bias is 282 vol bp — on an option whose price is *correct*. The quote is not wrong; the model reading it is.

> **Figure 1 — The wrong-way demo (figure not included in this pack).** The wrong-way demo on the running example (American calls, 6% dividend yield, true vol 25%). A: handing the American price to the production European inversion books the premium as volatility — up to 282 vol bp, growing as the option goes in the money; de-Americanization returns a flat 25%. B: the premium itself in price units — *cents*. The damage is measured in vol basis points because the wings divide by a small vega, not because the dollars are large. Panel A plots implied vol against strike: the naive curve starts near the true 25% out of the money and climbs steadily as strikes go in the money, peaking 282 vol bp above truth, while the de-Americanized curve sits flat on 25% across the whole strike range. Panel B plots the early-exercise premium $\pi$ in dollars against the same strikes: a curve of a few cents, largest in the money. The joint takeaway is the vega dictionary of §1.1: cents of premium become hundreds of vol bp exactly where vega has collapsed.

> **Figure 2 — The dictionary, audited (figure not included in this pack).** The measured naive bias (dots) against the first-order prediction $\pi/\partial_\sigma B$ (line): agreement to 1.4 vol bp out of the money, systematic under-prediction deep in the money where $\pi$ is a finite, not infinitesimal, price move. First-order vega reasoning locates the damage; only the full inversion sizes it. The plot overlays the measured bias points from the Figure 1 experiment on the analytic prediction curve: on OTM strikes the dots sit on the line to within 1.4 vol bp; moving in the money the dots pull increasingly above the line, because the first-order (infinitesimal-perturbation) expansion in the price cannot capture a premium that is a finite fraction of the option's value.

The machinery below engages only when a chain snapshot declares itself American-exercise (set by the data layer; US-listed single-stock and ETF chains in practice). European snapshots — index options, synthetic chains — skip every step byte-identically: invariant 1.

## 2. Where the premium lives: a little optimal stopping

Before removing $\pi$ it pays to know where it is — because over much of the strike–maturity plane it is *exactly zero*, and the theory that says so is short enough for a lecture to carry in full. Write the American value as an optimal-stopping problem over stopping times $\vartheta\in\mathcal T_{[0,t]}$ of the price filtration,

$$
A=\sup_{\vartheta\in\mathcal T_{[0,t]}}
\mathbb{E}\big[e^{-r\vartheta}\,g(S_\vartheta)\big],
\qquad g(s)=(s-K)^+\ \text{or}\ (K-s)^+,
\tag{3}
$$

under the risk-neutral measure [PeskirShiryaev2006].

**Proposition 1 (Dominance, both ways).** $A\ge E$ and $A\ge g(S_0)$; hence $\pi=A-E\ge0$, and $A$ never trades below intrinsic.

*Proof.* The stopping times $\vartheta\equiv t$ and $\vartheta\equiv0$ are both admissible, and a supremum dominates every member of its feasible set. ∎

That one line already fixes two production conventions: the estimate of a nonnegative premium may be clamped at zero ("Where the subtraction sits"), and an American quote *below* intrinsic is not a premium puzzle but a broken price ("The inversion as a control variate" returns it as `nan`). The substantive question is when the inequality $A\ge E$ is an equality.

**Theorem 1 (Merton: no dividends, no premium).** For a call on an underlying paying no dividends, with $r\ge0$, early exercise is never strictly optimal: $A=E$ and $\pi=0$ [Merton1973].

*Proof.* Let $E(s,u)$ denote the European call value with time $u$ left. Convexity of $x\mapsto(x-K)^+$ and Jensen's inequality under the martingale spot (no dividends: $\mathbb{E}[e^{-ru}S_u\,|\,S_0=s]=s$) give $E(s,u)\ge(s-Ke^{-ru})^+\ge s-K$, with strict inequality whenever $u>0$, $K>0$ and $r>0$ (and weak throughout at $r=0$). At any interior time the American holder's continuation value is at least the European value of the remaining claim, hence strictly above intrinsic: stopping early forfeits value. The supremum in equation (3) is attained at $\vartheta\equiv t$, which is the European contract. ∎

**Proposition 2 (Puts do carry a premium).** For a put with $r>0$ there are states where $\pi>0$: whenever $S<K(1-e^{-rt})$, exercise-now strictly beats any European continuation.

*Proof.* The European put is bounded by its discounted-strike cap, $E\le Ke^{-rt}$. Deep enough in the money the intrinsic value exceeds that cap: $K-S>Ke^{-rt}\iff S<K(1-e^{-rt})$. Then $A\ge K-S>Ke^{-rt}\ge E$. Interest on the strike is earned by exercising *now*; waiting pays the option's remaining time value, which deep in the money tends to zero while the interest does not. ∎

The same trade-off, run with dividends on the other side, makes the call story symmetric: a dividend is value the call holder collects only by exercising *before* the ex-date, so cash dividends (or a carry yield $q>r$) open a nonempty exercise region on deep in-the-money calls. The boundary between "continue" and "exercise now" is the *free boundary* of the obstacle problem — an object with its own large literature [PeskirShiryaev2006] — and Figure 3 computes its production shadow: the region of quotes whose entire value is intrinsic.

> **Figure 3 — The premium mapped over the quote plane (figure not included in this pack).** The premium mapped over the quote plane by the production tree (true vol 25%). A: puts at $r=4\%$, no dividends — the premium concentrates deep in the money and grows with maturity; right of the rust boundary the price *equals* intrinsic (at $t=0.5$, strikes beyond 130% of spot; premium up to \$2.7). In that dead zone a quote carries no volatility information at all, and the inversion of "The inversion as a control variate" correctly refuses to invert it. B: calls under the running example's 6% carry — the mirror image: dividends pull the exercise region onto deep ITM calls (below 77% of spot at $t=0.5$). A call on a no-dividend name shows no shaded region at all — that is Theorem 1 drawn. Each panel is a heat map of the early-exercise premium over the strike–maturity plane, with a contoured "rust" boundary marking where the American price sits exactly on its intrinsic floor; panel A's premium mass grows to the upper right (deep ITM puts, long maturity, peaking at \$2.7), panel B mirrors it on low strikes for calls under carry.

**Exercise 1.** Convince yourself the fitter needs no de-Americanization for calls on a zero-dividend, zero-borrow name even though the chain is legally American: show from Theorem 1 that the root $\sigma^*$ of equation (9) then coincides with the naive European inversion up to tree error. (This is why Figure 3B needed dividends to be interesting — and why the premium machinery keys on the *chain's* exercise style, not on any per-quote guess about optimality.)

> **Heuristic.** Why the fitter cares where $\pi$ lives: production fits the OTM side of the book ("Where the subtraction sits"), and Theorem 1 plus Proposition 2 say the OTM side is exactly where $\pi$ is small — OTM options have no intrinsic value to trade against carry. The *large* premiums sit on ITM quotes production mostly discards. The honest size of the de-Americanization effect on the fitted population is therefore *a few* vol bp ("Real chains, honestly labelled"), not the hundreds the ITM stress exhibits show — and both numbers are worth knowing, because the few-bp population is fitted against sub-vol-bp error budgets, and the discarded population reappears whenever the forward solver or a user selection touches an ITM quote.

## 3. Where the subtraction sits

De-Americanization is one stage of quote preparation. For one (ticker, expiry) the flow is: resolve $(F,D)$ from the chain (put–call parity plus the American de-bias of "The carry the tree runs on"); keep the OTM side of the book — puts for $K<F$, calls for $K\ge F$, where the vega and the tight relative spreads live — and run the tick-noise and missing-side screens; then, on American chains only, de-Americanize each surviving mid; convert to normalized calls and total variance; optionally repair wing convexity ("The wings: an approximate projection"); hand the result to the model layer. The tick screen deserves its one sentence, because it earned a certification case: on real-feed chains, an OTM quote whose *bid* — not its mid — is worth no more than three ticks is dropped, since a couple of ticks carries no volatility information and was measured whipsawing the fitted wings; the tick size is persisted with the snapshot so a replay screens identically (case `tick_noise_quotes`). The implementation lives in `volfit/api/quotes.py`; everything below is the mathematics of its three de-Am moves.

### 3.1 One root per strike, spread preserved

Given the American mid $P^{\mathrm m}$ at a strike, the pipeline solves for the volatility $\sigma^*$ at which the tree of "The pricing map" reprices it, then reprices the *European* leg at that same volatility:

$$
A(\sigma^*)=P^{\mathrm m},\qquad
\hat\pi=\max\!\big(P^{\mathrm m}-E(\sigma^*),\,0\big),
\tag{4}
$$

and subtracts the *same* $\hat\pi$ from bid, mid and ask. Three design decisions are packed into that line. The clamp at zero is Proposition 1 enforced against quote and tree noise — the true premium cannot be negative, so a negative estimate is noise; it is one-sided by design, and "The wings: an approximate projection" prices what the asymmetry costs. One root per strike, rather than three, preserves the quoted dollar spread exactly (invariant 2) at a third of the cost — the alternative, rooting bid and ask separately, would let tree error breathe the spread. And a quote the tree cannot invert keeps $\hat\pi=0$ (invariant 3): its raw band falls through to the European static-bound filters, which will drop it if it is genuinely unusable.

### 3.2 Into model space

The shifted prices enter the ordinary European pipeline: normalization to undiscounted forward units, put–call parity conversion of the OTM puts,

$$
c=\frac{P}{DF}\ \ \text{(calls)},\qquad
c=\frac{P}{DF}+1-e^{k}\ \ \text{(puts)},
\tag{5}
$$

then a strike-by-strike inversion to total variance $w$. Strikes whose bid, mid or ask violates the static bounds $(1-e^{k})^+<c<1$ are dropped (a one-sided band cannot be weighted), and a wing filter removes strikes beyond $Z_{\max}=4$ ATM standard deviations.

**Remark 1 (The two clocks, once).** Total variance is inverted from the *price*, so it is clock-independent; only the reported vol depends on the working clock, $\mathrm{iv}=\sqrt{w/\tau}$. The $\sigma^*$ of equation (4) is a calendar-time Black vol used *transiently* inside the premium estimate; the vol a user sees for the same quote can differ because $\tau\ne t$ when event weighting is on (Note 00). This is the first of $\tau$'s two appearances; the second is the cache key of "The cost of a chain, and how it was made to vanish", and for the same reason.

## 4. The pricing map

### 4.1 A tree for the obstacle problem

The stopping problem (3) needs a numerical method, and the classical one is Cox–Ross–Rubinstein [CoxRossRubinstein1979]: approximate the diffusion by a binomial lattice and solve the stopping problem by dynamic programming. With $N$ steps of size $\Delta t=t/N$, the spot moves by $u=e^{\sigma\sqrt{\Delta t}}$ or $d=1/u$, and matching the risk-neutral drift fixes the up-probability

$$
p=\frac{e^{(r-q)\Delta t}-d}{u-d},
\qquad 0<p<1
\iff \sigma\sqrt{\Delta t}>|r-q|\,\Delta t .
\tag{6}
$$

The condition on the right is the lattice's no-arbitrage requirement $d<e^{(r-q)\Delta t}<u$: the one-step move must be able to out-run the drift. It fails only for extreme drift-to-vol ratios, and "The inversion as a control variate" shows how each code path treats the failure. The value is then the backward recursion

$$
V^{(N)}_j=g(S_j),\qquad
V^{(m)}_j=\max\Big\{g(S_j),\;
e^{-r\Delta t}\big(p\,V^{(m+1)}_{j+1}+(1-p)\,V^{(m+1)}_{j}\big)\Big\},
\tag{7}
$$

— projected dynamic programming: the discrete Bellman equation of (3), with the $\max$ against the obstacle $g$ applied at every node. Drop the $\max$ and the same recursion prices the European leg $E$. Readers of Note 04 will recognize the family resemblance: the rollback is a monotone scheme (each $V^{(m)}_j$ is a nonnegative combination of the next layer, and $\max$ preserves order), which is the discrete reason tree prices are stable, ordered, and free of invented extrema. Stripped of the dividend machinery the kernel is a dozen lines; the reference listing (distilled from `core/american.py`) is replaced here, per the transfer policy, by its exact algorithm specification. It reproduces the production tree pricer at $q=0$ to $10^{-10}$; the European leg matches Black–Scholes to $2\times10^{-3}$ at this depth.

> **Algorithm — the CRR backward induction with early exercise (replaces the reference listing).**
>
> *Inputs:* a call/put flag; spot $s$; strike $K$; calendar time to expiry $t$; volatility $\sigma$; continuously compounded rate $r$; tree depth $N$ (default $501$); a flag selecting American (obstacle applied) or European (obstacle skipped) valuation.
>
> *Output:* the option value at the root node.
>
> 1. Set the step $\Delta t=t/N$, the moves $u=e^{\sigma\sqrt{\Delta t}}$ and $d=1/u$, the risk-neutral up-probability $p=(e^{r\Delta t}-d)/(u-d)$, and the one-step discount $e^{-r\Delta t}$.
> 2. Build the $N+1$ terminal spots $s\,u^{j}$ for $j=-N,-N+2,\dots,N$ (index stepping by 2, i.e. the recombining lattice's terminal layer).
> 3. Initialize the value vector with the terminal payoff: $(s\,u^{j}-K)^+$ for a call, $(K-s\,u^{j})^+$ for a put.
> 4. For each layer $m=N-1$ down to $0$: replace the value vector by the discounted one-step expectation, $V_j \leftarrow e^{-r\Delta t}\big(p\,V_{j+1}+(1-p)\,V_j\big)$ (the continuation value, shrinking the vector by one entry); then, if American, form the layer-$m$ spots $s\,u^{j}$ for $j=-m,-m+2,\dots,m$ and replace each entry by the maximum of continuation and intrinsic — the obstacle step.
> 5. Return the single remaining entry, the root value.

### 4.2 Monotone in volatility, hence invertible

The inversion of "The inversion as a control variate" treats $\sigma\mapsto A(\sigma)$ as a scalar equation to be rooted. For that to be well posed we need the map to be increasing — which is a theorem, with an honest scope.

**Proposition 3 (Monotonicity of the American price in volatility).** In the Black–Scholes model with convex vanilla payoff, the American value is nondecreasing in $\sigma$ [ElKarouiJS1998]: convexity of the payoff propagates to the value function of the stopping problem, and a comparison argument in the diffusion coefficient then orders the values. Away from the intrinsic plateau the monotonicity is strict, so the root of $A(\sigma)=P^{\mathrm m}$ is unique when it exists.

Two honest footnotes. First, the proposition is about the continuous problem; the discrete tree converges to it [CoxRossRubinstein1979] but a per-$N$ monotonicity proof is not carried here — the implementation's bracketed bisection requires only a sign change, which the bracket-expansion loop of "The inversion as a control variate" certifies before any halving. Second, "when it exists": on the intrinsic plateau of Figure 3 — a deep ITM quote priced *at* its exercise floor — no $\sigma$ reaches the quote from above, there is no root, and the honest answer is "this quote contains no volatility": the `NaN` lane. Figure 4 draws all of this at once.

> **Figure 4 — The inversion, well posed and failing (figure not included in this pack).** The inversion, well posed and failing, on American puts ($r=4\%$, $t=0.5$, production tree). For the OTM and moderately ITM strikes $A(\sigma)$ is strictly increasing and crosses its quote (dots) at a unique $\sigma^*$. The deep ITM strike is pinned at intrinsic (\$40) for every small $\sigma$: a market quote *at* that floor is below every model price on the bracket, no root exists, and the batch path returns `NaN` — premium zero, invariant 3 — rather than inventing a volatility. The figure plots $A(\sigma)$ against $\sigma$ for several strikes: the OTM and moderately ITM curves rise strictly from their floors and each intersects its horizontal quote level exactly once; the deep-ITM curve runs flat along its \$40 intrinsic plateau for small $\sigma$ before rising, and a quote sitting exactly on \$40 never crosses it.

### 4.3 The carry the tree runs on

For a real single name a flat continuous yield is a crude proxy: the call-side stopping decision of "Where the premium lives: a little optimal stopping" keys on *discrete ex-dates*, not on a smear of carry. Production therefore chooses, per (ticker, expiry), one of two carry models for the tree (`volfit/api/quotes.py`, `volfit/data/dividends.py`):

- **Discrete cash schedule, $q=0$.** When the dividend model supplies cash dividends $\delta_i$ with ex-dates $t_i\in(0,t]$, the tree prices them by the escrowed-spot method [Hull2018]. Why escrow? A cash drop applied at the nodes breaks recombination: after an ex-date, "up then down" and "down then up" no longer meet, because the subtracted cash is scaled differently by the subsequent multiplicative moves, and the lattice explodes from $O(N)$ nodes per layer to $O(2^N)$ paths. Escrowing instead diffuses the *base* $X_0=S-\sum_i\delta_ie^{-rt_i}$ — a purely multiplicative, recombining lattice — and adds back the present value of the dividends *not yet paid* at each node before comparing against the obstacle, so exercise is tested against the true cum-dividend spot. The cash amounts are rescaled by
  $$
  \alpha=\frac{S-F e^{-rt}}{\sum_i \delta_i e^{-rt_i}}
  \tag{8}
  $$
  so that the escrowed-tree forward $(S-\mathrm{PV}_0)e^{rt}$ reproduces the resolved forward *exactly*: the timing stays the forecast, the amounts bend to the market. (On the running example of Figure 5, a market forward 15 bp of carry under the forecast rescales the cash by $\alpha=1.037$.) A non-physical $\alpha$ ($\le0$ or beyond a sanity cap) rejects the schedule.
- **Continuous carry fallback.** Otherwise the tree runs on the $(r,q)$ implied by the resolved pair $(F,D)$.

The two never coexist inside one tree, and equation (8) is what keeps the cash choice consistent with a forward whose level partly reflects yield-like far-tail effects.

**Remark 2 (The escrowed model is a displaced lognormal).** The diffusing object under escrow is $S-\mathrm{PV}(\text{dividends})$, so the model's spot distribution is a lognormal *shifted* by the escrow — slightly skewed relative to the plain lognormal at the same forward. The premium estimate $\hat\pi$ inherits this modelling choice; it is part of the "exact in the model, approximate outside it" honesty of "The inversion as a control variate".

Figure 5 shows why production pays for the discrete schedule where it can get one: at the same forward, the cash tree and the yield tree price materially different premia, and only the cash tree knows that an option expiring *before* the ex-date has no dividend to capture — Theorem 1 switching on at a date, not fading in.

> **Figure 5 — Same forward, different exercise value (figure not included in this pack).** Same forward, different exercise value (production trees; one \$3 dividend, ex-date at $0.35$ y, $r=4\%$). A: the call premium across strikes under the forward-consistent cash schedule versus the continuous-yield fallback — the cash tree's premium is up to $3.2\times$ larger, because a lump of value at a date is worth more to an early exerciser than the same value smeared into carry. B: the premium at a fixed ITM strike as a function of expiry: under cash it is *zero* for every expiry before the ex-date (Merton's theorem applies verbatim — nothing to capture) and switches on at the date; the yield model fades in smoothly and misses both regimes. The kink is the call-side ATM signature that motivates the joint refinement of Remark 3. Panel A plots two premium-versus-strike curves at the same resolved forward, cash-schedule above yield-fallback by up to a factor 3.2 on ITM strikes; panel B plots premium versus expiry at a fixed ITM strike, the cash curve identically zero until the 0.35-year ex-date then jumping on, the yield curve rising smoothly from zero and wrong on both sides of the date.

**Remark 3 (The apparent circularity, resolved).** De-Americanization needs $(F,D)$; but put–call parity — the source of $(F,D)$ — is an equality *only for European options*, so raw American mids bias the parity regression. Production resolves the loop in order: the parity regression runs first; then a *coarse* de-Am pass (`volfit/data/forwards.py`) de-biases it — including, where the de-Americanized put and call vols fail to join at the money, a rate bisection that zeroes the gap (the joint $(r,F)$ refinement; the ATM-kink case file of Note 06); only then does the *precise* per-quote de-Americanization of this note run, under the refined carry. The refinement needs the carry to a few bp, not the quote to sub-bp, so it runs fewer bisections at coarser tolerance.

One step deeper exists as an explicit opt-in. The joint borrow/de-Am fixed point of Note 06 iterates the full loop — borrow and dividends into the de-Americanization, the de-Americanized board into the parity forward, the forward back into the borrow — with the same dividend schedule riding both legs, and feeds the converged $(F,D)$ into fits per expiry only when the implied borrow clears a 25 bp materiality gate; below the gate the parity forward is kept exactly, so ordinary names are byte-identical even with the toggle on. It ships default-off.

## 5. The inversion as a control variate

We can now say precisely how the unobservable is removed. The move is a one-dimensional root find,

**Central equation.**

$$
\text{find }\sigma^*:\ A(\sigma^*)=P^{\mathrm m},\quad
\text{return }\sigma^*\text{ as the European-equivalent Black vol,}
\tag{9}
$$

the standard desk workflow — convert American quotes to pseudo-European quotes, then calibrate a European model — studied critically by Burkovska et al. [Burkovska2018]: pragmatic and fast, exact in the model, not exact outside it.

> **Heuristic.** Why is the *tree's* $\sigma^*$ the right European volatility? Because the tree is a *control variate* for the stopping feature. The market price differs from the European price we want by a premium we cannot observe; the tree supplies a model premium $\pi_{\mathrm{tree}}(\sigma)=A(\sigma)-E(\sigma)$ as a function of $\sigma$. Subtracting it at the root,
> $$
> P^{\mathrm m}
> -\underbrace{\big[A(\sigma^*)-E(\sigma^*)\big]}_{\text{model premium at }\sigma^*}
> = E(\sigma^*)\;\approx\;DF\,B(k,{\sigma^*}^2t),
> \tag{10}
> $$
> where the equality uses the defining property $A(\sigma^*)=P^{\mathrm m}$ and the final step is tree discretization only. Two cancellations happen at once: the market's premium cancels against the model's, and the tree's *level* error largely cancels between its American and European legs — the tree only has to price the *difference* well, and the difference is a smooth, slowly varying functional of $\sigma$. "The error budget, measured" measures exactly how much of each cancellation survives discretization.

### 5.1 Failure semantics: loud scalar, silent batch

A price below intrinsic (impossible for an American option, Proposition 1) or above the static cap ($S$ for a call, $K$ for a put) yields `nan`, mirroring the fitter's convention for unusable quotes. The bracket's lower end is lifted just above the CRR drift floor of equation (6) — production uses $\max(10^{-4},\,1.5\,|r-q|\sqrt{t/N})$ — and the upper end doubles until the model price clears the quote, capped at $\sigma=4$; a quote never bracketed under the cap returns `nan`.

The scalar and batch paths then *deliberately* differ. The scalar path (one quote, Brent's method, $N=501$) *raises* on an invalid CRR probability: a single mispriced input should be loud. The batch path must survive mixed inputs, so invalid lanes — static-bound violations, the intrinsic-plateau puts of Figure 4, never-bracketed quotes — return `NaN` and the rest of the chain proceeds; quote prep reads `NaN` as "no premium estimate", sets $\hat\pi=0$, and leaves the untouched band to the European filters (invariant 3).

**Exercise 2.** Derive the drift floor: show from equation (6) that $0<p<1$ is equivalent to $\sigma>|r-q|\sqrt{t/N}$, and evaluate it on the running example's carry ($|r-q|=4\%$, $t=0.5$, $N=192$): $\sigma_{\min}\approx0.2\%$, lifted $1.5\times$ by production. Conclude that the floor excludes only volatilities no equity quote reaches, yet protects every tree the bisection prices.

## 6. The error budget, measured

The returned $\sigma^*$ carries four error sources; a lecture should separate them because they scale differently and are bought back by different levers.

- **Root tolerance.** The batch path runs 24 halvings of a bracket at most $4.0$ wide: $4\cdot2^{-24}\approx 2.4\times10^{-7}$ of $\sigma$, about $0.002$ vol bp — negligible.
- **Finite tree, two legs.** Discretization enters twice, and unequally. The *level* error of the American leg moves the root itself; the *European-leg* gap $E(\sigma^*)-DF\,B$ survives in the price handed downstream. Figure 6 separates them on the worked example: at the batch depth $N=192$ the root carries 0.2 vol bp while the reported quote carries 1.2 (worst strike 2.1); at the scalar depth $N=501$ the reported error drops to 0.30. On the real chain this European-leg gap is directly visible as the small *negative* bias on selected OTM calls (median $-2.1$ bp, "Real chains, honestly labelled") — tree versus analytic Black, not a negative premium.
- **Carry and dividend model.** A wrong forward, discount or cash schedule biases $\sigma^*$ directly; de-Americanization inherits, and cannot repair, its inputs ("The carry the tree runs on"; the closing caution of "Real chains, honestly labelled").
- **Market versus model.** The CRR diffusion between ex-dates, the displaced-lognormal escrow (Remark 2) and the one-sided clamp of equation (4) are modelling choices; their measurable footprint is the wing non-convexity that "The wings: an approximate projection" repairs.

> **Figure 6 — The cancellation, audited (figure not included in this pack).** The cancellation, audited on the worked example (converged-tree quote, production inversion at each depth). A: at $K=90$, the root $\sigma^*$ (teal) and the reported quote (rust) both converge like $1/N$ through the CRR even/odd sawtooth, but at any given depth the root is the cleaner object — the American-vs-European cancellation of equation (10) protects it, while the reported quote re-imports the European-leg gap. B: the same end-to-end error aggregated across all strikes: the shipped batch depth $192$ holds the worst strike to 2.1 vol bp and the median under $0.3$; halving the depth to $128$ roughly saves half the work (the rollback is $O(N^2)$) but lifts the whole error profile — the depth is a numerical-target knob, not a speed dial. Panel A plots the two error curves against tree depth $N$ on the single strike $K=90$: both oscillate through the classic CRR even/odd sawtooth and shrink like $1/N$, the root curve sitting well below the reported-quote curve at every depth (0.2 vs 1.2 vol bp at $N=192$). Panel B plots the reported-quote error across the strike sweep at the shipped depth versus the tempting halved depth, showing the whole profile lifting when the depth is cut.

> **Caution.** The batch depth was once nearly cut to $128$ as a cheap $2\times$ speed-up — the rollback is $O(N^2)$, so depth is the single most tempting dial in the file. Measured on the fitted population of the real chain ("Real chains, honestly labelled"), the cut moves de-Americanized vols by a median 2 and up to 8 vol bp — material against sub-vol-bp fitting budgets, and *structured* (it loads on low-vega strikes), so it changes answers, not just runtimes. The depth is held at $192$ and the speed is bought where it does not touch the numerical target: the kernel and the cache of "The cost of a chain, and how it was made to vanish".

**Exercise 3.** From the budget above, explain why tuning the bisection count from $45$ to 24 sweeps was free ($<0.01$ vol bp, test-locked, a $\sim1.8\times$ saving on the isolated de-Am rail) while the depth cut was not: compare $4\cdot2^{-24}$ against the $N^{-1}$ tree terms at $N=192$, and note which term the extra $21$ halvings were polishing.

## 7. A worked example, by the numbers

Provenance in one line: every number in this note is regenerated by the edition's figure generator at commit `5b5b97f` (2026-07-18), configuration archived alongside (`figures/deam_stopping_numbers.json`); the kernel timing is read from the stored benchmark artifact of the original suite, never re-timed.

> **Example — Case file: one strike of Figure 1.** Setup: American call, $S=100$, $K=90$, $t=0.5$, $r=2\%$, $q=6\%$, true volatility $\sigma=25\%$, scalar tree depth $N=501$. The production tree prices
> $$
> A=11.7856,\qquad
> E=11.2725,\qquad
> \pi=A-E=0.5131 .
> $$
> With a 6% yield against a 2% rate, exercising to capture the dividend stream is genuinely valuable on an ITM call — about 4.4% of this option's value sits in $\pi$. Handing $A$ to the analytic European inversion (production's normalization, $c=A/(DF)$ at $k=\log(K/F)$) returns
> $$
> \sigma_{\text{naive}}=27.19\%,
> $$
> a $+219$ vol bp phantom: the premium, booked as volatility. Solving equation (9) instead gives $\sigma^*=25.00\%$ — the truth, to bisection tolerance. Every number above is generated from `core/american.py`; the full-strike sweep is Figure 1.

## 8. The cost of a chain, and how it was made to vanish

A lecture on a numerical method owes its audience the arithmetic. One rollback (7) touches $N+(N-1)+\dots+1\approx N^2/2$ nodes: one tree is $O(N^2)$. One root is 24 bisections plus a few bracket expansions — call it $30$ trees — and one chain is a few hundred roots: order $10^8$ multiply-adds at $N=192$. On modern silicon that is tens of milliseconds of *arithmetic*; the original NumPy batch took a full second. The gap was not the flops but the memory system: vectorizing across quotes materializes $(n_{\text{quotes}}\times m)$ slabs at every one of the $N$ steps, and the allocator, not the FPU, was the bottleneck. The compiled kernel inverts the loop order — one scalar tree per quote, no per-step allocation, precomputed power tables, the escrow constants hoisted, a parallel loop over quotes — and the same public dispatch then runs 86× faster.

> **Performance.** On a 300-quote synthetic chain the kernel runs in 11.56 ms versus 998.9 ms for the NumPy fallback — 86×. The comparison is like-for-like: both timings call the public batch dispatch (identical static screens, identical drift-floor bracket), the NumPy leg by forcing the fallback; both paths run once untimed first (JIT compile excluded) and the fastest of five repeats is reported; the generator *raises* unless the two paths return identical finite/`NaN` lanes (206 of 300 here — the rest are intrinsic-plateau puts, correctly `NaN` on both) and identical roots (observed max $|\Delta\sigma|=0$). Measured on a 20-thread desktop; this uniform synthetic chain parallelizes especially well — the documented figure on wide *real* chains is $\sim60\times$. Without Numba the fallback serves with identical results.

The second lever is not faster code but *less* code run. The de-Americanized, inverted quotes depend only on the *data* entering quote preparation — never on any fit setting — so the pipeline memoizes each node's prepared quotes on a content-digest key built from (ticker, expiry, raw-chain version, forward, discount, cash-dividend digest, $t$, $\tau$, as-of). Each entry is there for a reason a reader can now predict: the forward and discount absorb forward policy and manual edits; the cash digest absorbs the dividend model and rate; calendar $t$ drives the tree; and $\tau$ appears for the reason of Remark 1 — the cached band *reports* vols on the event clock, so an event edit must re-key. A change to any of these re-runs the trees; model choice, penalties, weights and optimizer tuning do not (invariant 5). The de-Am cost is thus paid once per genuine data change and is *free across an entire calibration sweep* — a complexity-class change, worth more than any constant factor the kernel can buy. A conservative pre-screen (non-positive bids, a buffered wing cut) additionally drops quotes that cannot survive the static bounds before any tree prices them, and is output-preserving by construction; the three-tick OTM bid floor of "Where the subtraction sits" is the separate, deliberately non-output-preserving screen — it genuinely removes quotes, and says so.

## 9. The wings: an approximate projection

De-Americanization inverts each strike *independently* — its own root (9), its own clamp (4) — with no coupling across strikes. That independence is what makes the kernel embarrassingly parallel; its price is that nothing enforces cross-strike coherence on the output. Writing the undiscounted call as $C(K)=\mathbb{E}[(S_t-K)^+]$, its second derivative in strike is the risk-neutral density, $\partial_{KK}C=f_{S_t}(K)\ge0$: *convexity of the call curve in strike is exactly the no-butterfly condition*. On a discrete grid the test is the divided second difference

$$
\Delta^2_i=\frac{C_{i-1}(K_{i+1}-K_i)-C_i(K_{i+1}-K_{i-1})+C_{i+1}(K_i-K_{i-1})}
{K_{i+1}-K_{i-1}}\;\ge\;0 .
\tag{11}
$$

To be precise about the mechanism: per-strike inversion does not by itself create arbitrage — if the inputs were exactly consistent with one arbitrage-free model, the outputs would be too. The non-convexity is *injected*: by quote noise in sparse wings, by the one-sided $\max(\hat\pi,0)$ clamp (a strike-local, asymmetric perturbation), by finite-tree error, and by carry mismatch — and per-strike inversion simply has no cross-strike coupling with which to absorb any of it. The violations concentrate in the sparse, low-vega wings, handing every downstream model a genuine (small) butterfly arbitrage as *input* — the seed of the put-wing violation Note 03 dissects.

> **Example — Case file: the repair that moved the money.**
>
> **Setup.** The first repair projected the *whole* call curve onto the convex cone with a free global affine part — the mathematically obvious $\ell^2$ projection.
>
> **Failure.** A visible ATM smile gap opened on live SPY and NVDA.
>
> **Diagnosis.** Repairing a wing dip with a free global affine part re-tilts the baseline: the projection moved the at-the-money prices it had no business touching. The moves were sub-penny — *small* in vol at the money, where vega peaks — but the ATM core is where quotes are densest, spreads tightest and fit weight heaviest, and the coherent shift opened a discontinuity against neighbouring untouched quotes.
>
> **Fix.** Reverted; redesigned wing-only (below), with the core held byte-identical *by construction* — invariant 4 exists because of this incident.
>
> **Verdict.** The lesson is about locality, not vega: *a repair aimed at a region the data cannot pin down must be structurally incapable of moving the region it can.* Note 04's convex-wing case file and Note 09's tapered enforcement are the same principle wearing other clothes. The revert and the confined repair's clean-chain no-op are locked together as certification case `deam_repair_confinement`.

**Remark 4 (Duplicate strikes: a field hardening worth naming).** One further wing-repair input deserves its own sentence rather than an appendix clause. Overlapping weekly and monthly listings can hand the projection two quotes at *identical* strikes; the core-anchor *slope* — a divided difference across the core boundary — then divides by zero, and the resulting crash killed whole backtest day-pairs before it was traced. The anchor now reads the nearest strictly distinct strike; clean chains are byte-identical, and the scenario is locked as certification case `duplicate_strikes`. The general lesson is the quiet one: *a formula's implicit genericity assumption ("strikes are distinct") is an input contract, and real feeds violate it*.

The shipped repair (`volfit/calib/convex_deam.py`) is therefore *wing-only, band-constrained* and — honestly — *approximate*. It acts on the normalized OTM call curve after the parity conversion (5). Strikes in the core $|z|\le Z_{\mathrm{core}}=1$ are held byte-identical. Each wing, anchored at its core boundary, is replaced by an approximation to the $\ell^2$-closest curve that is simultaneously convex and inside the quoted band — the projection onto the intersection of two convex sets,

$$
\mathcal C=\{\hat C\ \text{convex, leaving the anchor no flatter than the core}\},\qquad
\mathcal B=\{C^{\mathrm b}\le\hat C\le C^{\mathrm a}\},
\tag{12}
$$

computed by *at most 25 iterations* of Dykstra's alternating projection [BoyleDykstra1986] — the cone step a nonnegative-hinge least squares, the band step a clip. Dykstra rather than plain alternation because plain von Neumann alternation between convex sets converges to *a* point of the intersection, not to the *closest* one; Dykstra's correction terms restore the projection. The honesty ledger, stated once and plainly: the implementation does not certify $\mathcal C\cap\mathcal B\ne\emptyset$ (a wing whose convexification demands leaving the band has no exact solution; the iterate then lands near the band); it does not post-check global convexity of the assembled curve; and it cannot, by construction, repair a violation *inside* the held-fixed core. A common per-strike shift is applied to bid, mid and ask — the spread survives, invariant 2 again — and the repaired band is re-inverted to total variance.

> **Heuristic.** Why the band constraint is load-bearing. Plain convex projection of an illiquid, genuinely non-convex wing is free to push a price all the way to the static no-arbitrage boundary — and a wing call price at that boundary inverts to an absurd volatility (a put wing was once watched jumping from 27% to 104%, itself violating Lee's moment bound; Note 03), detonating the downstream fit. Confining the repair to the quoted spread bounds the correction by the market's own stated uncertainty: a price may move exactly as far as the quote is genuinely ambiguous, and no further.

The repair is gated American-only and short-circuits on any curve already convex to a tolerance of $10^{-3}$ in normalized price (Appendix A, "Hyperparameter atlas"). The threshold is calibrated to an observed gap in the data: dense liquid chains carry only $\sim10^{-4}$ de-Am rounding curvature (the captured delayed-tier SPY fixture of "Real chains, honestly labelled" quotes tick-wide spreads, median $2.7\times10^{-5}$ normalized — an order below the gate), while genuinely arbitraged illiquid wings run $10^{-3}$ to $10^{-2}$. Liquid names are therefore *never* touched (byte-identical), and only real wing arbitrage is repaired — roughly one American node in eight, in the production ablations. On those nodes the ablation found the repair both reduces the fitted arbitrage and *lowers* the in-sample error — the model no longer chases the arbitraged quotes — and it composes with Note 03's output-side $g\ge0$ penalty rather than duplicating it: the repair removes the arbitrage at the *source*, and running both attains the penalty's arbitrage removal at a fraction of its standalone in-sample cost.

> **Figure 7 — The repair mechanism, staged (figure not included in this pack).** The mechanism, staged where it actually operates (production repair on a constructed illiquid wing — the real fixture's tick-wide bands cannot host a genuine violation, which is itself the liquid-gate story). A: a sparse put wing whose mids carry a one-sided clamp-scale footprint inside a realistic bid–ask band; the projection returns a convex wing *inside the band*, anchored at the $z=-1$ boundary, and the core to the right moves by exactly 0. B: the divided second differences (11): before, dipping to $-1.6\times10^{-3}$ — through the $10^{-3}$ gate; after, convex to machine precision ($-1.7\times10^{-17}$). The largest vol move used to buy that convexity is 134 vol bp, paid entirely inside the wing's quoted spread. Panel A shows the wing's quoted band with the non-convex mids inside it and the repaired convex curve threading the same band, pinned at the core-boundary anchor; panel B shows the per-strike divided second differences as bars, negative dips before the repair and nonnegative (to floating-point zero) after.

## 10. Real chains, honestly labelled

The synthetic example controls the truth; Figures 8 and 9 show the effect on live market prices, nothing simulated — and on two deliberately different populations, because the single most misquotable number in this subject is "the de-Americanization effect" with the population left unsaid.

**The stress exhibit (Figure 8).** Every two-sided put of one captured SPY expiry (the Massive true-weekly fixture, as-of 2026-06-25; the December-2026 expiry, strikes 55–138% of spot) is inverted both ways: naively through the analytic European Black formula, and through the American tree (9). Since $\pi$ has price units, the wedge between the curves is the *model-implied* vol effect of the premium. Out of the money the two agree to a few vol bp; in the money the wedge runs to a median 519 vol bp across the 54 ITM puts, up to 814. But this population is *not what the fitter fits*: production keeps the OTM side only, so the ITM puts carrying the headline wedge are — in all but the thin band between spot and forward — exactly the quotes production *discards* in favour of their OTM call twins. Figure 8 is an economic stress illustration of what skipping de-Americanization would do to the discarded side, not a statement of fit exposure. Proposition 2 told us in advance this is where the premium had to be.

> **Figure 8 — Real market data, the stress exhibit (figure not included in this pack).** Real market data, one live SPY expiry (Massive capture, as-of 2026-06-25, December-2026): every two-sided put mid inverted as if European versus de-Americanized. The ITM wedge — median 519 vol bp, up to 814 — is the model-implied vol effect of the premium on a side production almost entirely *discards*: a stress exhibit, not the fitted population (that is Figure 9). Carry supplied ($r=4.3\%$, $q=1.2\%$) because the delayed capture's parity carry is unusable (Note 06). The plot shows the two implied-vol curves over strike for the full two-sided put board: they coincide to a few vol bp on OTM strikes and split increasingly in the money, the naive-European curve riding far above the de-Americanized one, with the wedge peaking at 814 vol bp deep in the money.

**The fitted population (Figure 9).** The same two-way inversion on the quotes production actually selects — 109 OTM puts and calls of the same expiry, after the tick floor and the $Z_{\max}$ wing filter — moves the implied vol by a median $|\cdot|$ of 4.2 vol bp, maximum 60 (selected OTM puts: median $10$ bp, max $60$; selected OTM calls: median $-2.1$ bp, max $1.9$). This is the honest statement of what de-Americanization is worth on a liquid, moderate-carry ETF chain at six months: a few vol bp in the body, tens in the put wing — material against sub-vol-bp error budgets, an order of magnitude below the stress exhibit. The small *negative* call-side values are the finite-tree line of the budget in "The error budget, measured", not a negative premium. Single names with hard dividends and higher rates sit between the two panels.

> **Figure 9 — The fitted population (figure not included in this pack).** The same expiry, restricted to the quotes production actually fits (OTM puts below $F$, OTM calls above): a median $|\cdot|$ of 4.2 vol bp, max 60 in the put wing — the fit's real de-Am exposure, an order of magnitude below the discarded-ITM stress exhibit. The gentle put-side rise toward the money and the flat, slightly negative call side are both predicted by "Where the premium lives: a little optimal stopping" and "The error budget, measured": premium from Proposition 2, tree error from the European leg. The plot shows the per-quote vol shift across the 109 selected OTM strikes: the put side rises gently from a few bp in the far wing toward tens of bp near the money (median 10, max 60), while the call side sits flat and slightly negative (median $-2.1$ bp) — the European-leg tree gap, not premium.

One honesty note on inputs: the delayed-tier capture's parity-implied carry is unphysical (Note 06 documents how such feeds synthesize chains from per-contract vols at $F=S$, $D=1$, destroying parity information), so the carry here is supplied explicitly — $r=4.3\%$ money-market, $q=1.2\%$ SPY dividend yield (mid-2026) — a live instance of the caution below.

> **Caution.** What the model does and does not cover. The tree supports a deterministic scheduled cash-dividend path (escrowed, forward-consistent via equation (8)) *or* an equivalent continuous-carry fallback, with a CRR diffusion between ex-dates. It does not model dividend jumps, uncertain dividend timing or amounts, stochastic rates, or stochastic borrow — though a *deterministic* borrow does now feed this machinery through the opt-in fixed point of Remark 3. And $\sigma^*$ is only as good as the resolved forward and dividend inputs (Note 06): the method removes the *early-exercise* bias; it cannot repair a wrong forward.

## 11. What is genuinely original here

The optimal-stopping theory is classical [Merton1973, PeskirShiryaev2006], the control-variate reading of tree inversion is folklore, and the critical literature is Burkovska et al. [Burkovska2018]. The contributions of this implementation are discipline and measurement:

1. the *allocation-free compiled kernel* behind an unchanged public dispatch, with the agreement gate (identical `NaN` lanes, identical roots) asserted before any speed number is reported;
2. the *prepared-quote content cache*, which scopes de-Am cost to genuine data changes rather than fit iterations — a complexity-class change, not a constant factor;
3. the *measured* depth-and-bisection tuning: bisections cut $45\to24$ at $<0.01$ vol bp, the depth cut to $128$ *refused* at a measured median 2 / max 8 vol bp on the real fitted population;
4. the *wing-only, band-constrained convex repair* with the core held byte-identical by construction — the redesign the reverted global projection forced.

The natural next step — documented, not shipped — is seeding the bracket with an analytic American approximation (Barone-Adesi–Whaley [BaroneAdesiWhaley1987] or Bjerksund–Stensland [BjerksundStensland2002]) so each tree starts near its root: seeds, not answers, so no contract changes.

## 12. Limitations

Where the guarantees stop, gathered in one place. De-Americanization is exact *in the model* and only there [Burkovska2018]: the CRR diffusion, the deterministic escrowed dividends (Remark 2), and the flat per-expiry carry are all modelling choices inside $\hat\pi$. Proposition 3's monotonicity is a continuous-problem theorem; the tree inherits it only through convergence, and the implementation leans on bracketing, not monotonicity. The clamp in equation (4) is deliberately one-sided; its footprint is the wing non-convexity of "The wings: an approximate projection", and the repair that removes it is approximate (capped Dykstra, no intersection certificate, core violations out of scope by design). The premium estimate inherits the resolved forward and dividend inputs and cannot repair them. And the intrinsic plateau is a hard information boundary: a quote at its exercise floor contains no volatility, and no method — this one included — can extract what is not there.

## Appendix A. Hyperparameter atlas

**Table 2 — De-Americanization hyperparameters (all hidden / internal).**

| Constant | Default | Role |
|---|---|---|
| `DEFAULT_STEPS` | $501$ | Scalar CRR depth; European leg matches Black to $\sim10^{-5}$. |
| `DEFAULT_BATCH_STEPS` | $192$ | Batch/kernel tree depth (the caution of "The error budget, measured"). |
| `BATCH_BISECTIONS` | $24$ | Bracketed-bisection sweeps ($\sim0.002$ vol bp). |
| `SIGMA_LO` | $10^{-4}$ | Lower vol bracket floor; production lifts it above the CRR drift floor, $\max(10^{-4},\,1.5\,\lvert r-q\rvert\sqrt{t/N})$. |
| `SIGMA_HI` | $4.0$ | Upper vol bracket cap (bracket doubles up to it). |
| escrow PV | — | Discrete-cash escrowed-spot lattice, forward-consistent rescale, equation (8), cap $\alpha\le5$. |
| pre-screen buffer | $1.5\times$ | Wing buffer for the conservative bid/bounds pre-screen (output-preserving). |
| `TICK_FLOOR_TICKS` | $3$ | OTM bid floor in ticks on real-feed chains ("Where the subtraction sits"); tick size persisted with the snapshot; certification case `tick_noise_quotes`. |
| prepared-quote key | — | Cache key: (ticker, expiry, raw-chain version, forward, discount, dividend digest, $t$, $\tau$, as-of). |
| `convex_deam` | `true` | Enable the wing-only convex repair ("The wings: an approximate projection"); American chains only, European a no-op. |
| $Z_{\text{core}}$ | $1.0$ | ATM core half-width (units of $\sqrt{w_{\mathrm{atm}}}$) held byte-identical by the repair. |
| `CONVEX_TOL` | $10^{-3}$ | Convexity short-circuit: a curve convex to this (normalized price) is left untouched. |
| Dykstra iterations | $25$ | Cap on the alternating projection (approximate, not certified). |
| $Z_{\max}$ | $4.0$ | Post-inversion wing filter (ATM standard deviations). |

## Appendix B. Performance notes

Machine-dependent numbers live here, with their protocol.

1. **Numba kernel** ("The cost of a chain, and how it was made to vanish"). Single scalar CRR per quote, no per-step allocation, precomputed powers, parallel loop over quotes; measured 86× over the NumPy fallback on a 300-quote synthetic chain (Table 3; $\sim60\times$ documented on wide real chains). Both paths through the public dispatch; identical roots asserted before the number is reported; graceful NumPy fallback when Numba is absent.
2. **Bisection tuning.** $45\to24$ sweeps, $<0.01$ vol bp drift (test-locked), $\sim1.8\times$ on the isolated de-Am rail.
3. **Depth: measured and refused.** Batch depth $128$ evaluated as a $\sim2\times$ lever and rejected at a measured median 2 / max 8 vol bp shift on the real fitted population ("The error budget, measured").
4. **Prepared-quote content cache.** De-Am re-runs only on a genuine data change, never on fit-setting changes — free across a calibration sweep.
5. **Output-preserving pre-screen.** Drops unusable quotes before any tree prices them; by construction changes no surviving result.
6. **Future (not shipped).** BAW / Bjerksund–Stensland analytic bracket seeds to start each tree near its root.

**Table 3 — De-Americanizing a 300-quote synthetic chain** (206 invertible on both paths, identical roots; $192$-step trees, 24 bisections; one untimed warm-up per path, fastest of five repeats, 20 threads). Timing read from the stored benchmark artifact; never re-timed by this edition.

| Path | time (ms) | relative |
|---|---:|---:|
| NumPy fallback (same dispatch) | 998.9 | $1\times$ |
| Numba kernel | 11.56 | $86\times$ |

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 4 — Claim → equation → code → test.**

| Claim | Equation | Code anchor / *Test anchor* |
|---|---|---|
| $\sigma^*$ root = de-Americanized Black vol; static-bound / drift-floor `NaN` semantics | (9), (10) | `volfit/core/american.py` / *`tests/test_american.py`* |
| Spread-preserving $\hat\pi$ shift of bid/mid/ask; OTM selection; parity conversion | (4), (5) | `volfit/api/quotes.py` / *`tests/test_quotes_deam.py`* |
| 24-bisection drift $<0.01$ vol bp vs the 45-sweep baseline | — | `volfit/core/american.py` / *`tests/test_quotes_deam.py`* |
| Escrowed cash schedule, forward-consistent rescale | (8) | `volfit/data/dividends.py` / *`tests/test_discrete_deam.py`* |
| Kernel $=$ NumPy fallback to tree rounding (incl. cash dividends) | — | `volfit/core/american_numba.py` / *`tests/test_american_numba.py`* |
| Prepared-quote cache: invalidation table | — | `volfit/api/service.py` / *`tests/test_prepared_cache_key.py`* |
| Wing repair: ATM core byte-identical, band-stay, convexity gate | (11), (12) | `volfit/calib/convex_deam.py` / *`tests/test_convex_deam.py`* |
| Joint $(r,F)$ American de-bias joins the ATM sides | — | `volfit/data/forwards.py` / *`tests/test_forward_debias.py`* |

## Appendix D. Reference implementation: convexity building blocks

The convexity test (11) and the convex-cone half of the wing repair are compact; the reference listings showed these two *building blocks*, not the shipped repair. Per the transfer policy the listings are replaced here by exact algorithm specifications. `min_butterfly` is the divided second difference (minimum $\ge0$ iff the curve is butterfly-free); `convex_fit` is the cone projection — the $\ell^2$-closest convex curve leaving the core anchor, written as an affine part plus nonnegative hinge knots, so nonnegativity of the hinge coefficients *is* the convexity constraint. The production module composes `convex_fit` with the bid/ask clip inside the capped Dykstra alternation of "The wings: an approximate projection" and additionally handles duplicate strikes (Remark 4) and the core/wing gating — none of which is specified here. Both building blocks were executed against their production counterparts on the demo wing of Figure 7 before this note was committed: agreement to $10^{-16}$ (floating-point identity), asserted by the edition's generator on every run.

> **Algorithm — the no-butterfly test (`min_butterfly`).**
>
> *Inputs:* an ascending strike grid $K_0<K_1<\dots<K_{n-1}$ and call prices $C_0,\dots,C_{n-1}$ on it.
>
> *Output:* a scalar which is $\ge0$ if and only if the price curve is convex in strike (no butterfly arbitrage).
>
> 1. For each interior index $i=1,\dots,n-2$ form the left and right strike gaps $a_i=K_i-K_{i-1}$ and $b_i=K_{i+1}-K_i$.
> 2. Form the (unnormalized) butterfly value $\text{fly}_i = C_{i-1}\,b_i - C_i\,(a_i+b_i) + C_{i+1}\,a_i$.
> 3. Return $\min_i \text{fly}_i/(a_i+b_i)$ — the minimum divided second difference of equation (11).
>
> **Algorithm — the convex wing fit (`convex_fit`).**
>
> *Inputs:* wing abscissae $u_0,u_1,\dots,u_{n-1}$ (the wing's strike coordinates, anchored at $u_0$, the core boundary), prices $c_0,\dots,c_{n-1}$, and a slope floor (the anchor's departing slope must be no flatter than the core's, per equation (12)).
>
> *Output:* the $\ell^2$-closest convex curve through the fixed anchor value $c_0$.
>
> 1. Build the design matrix $A$ with columns: first the affine column $u$, then one hinge column $(u-u_j)^+$ for each interior knot $j=1,\dots,n-2$.
> 2. Solve the bound-constrained linear least-squares problem $\min_x \lVert A x - (c-c_0)\rVert_2$ subject to $x_0\ge$ slope floor (the affine slope coefficient) and $x_j\ge0$ for every hinge coefficient, with no upper bounds.
> 3. Return $c_0 + A x$. The result is convex by construction: a sum of an affine function and nonnegatively weighted hinges is convex, so the nonnegativity bounds on the hinge coefficients are exactly the convexity constraint, and the slope-floor bound is the "leaving the anchor no flatter than the core" condition.

## References

- [CoxRossRubinstein1979] J. Cox, S. Ross and M. Rubinstein. Option pricing: a simplified approach. *J. Financial Economics*, 7(3):229–263, 1979.
- [Merton1973] R. Merton. Theory of rational option pricing. *Bell J. Economics and Management Science*, 4(1):141–183, 1973.
- [PeskirShiryaev2006] G. Peskir and A. Shiryaev. *Optimal Stopping and Free-Boundary Problems*. Birkhäuser, 2006.
- [ElKarouiJS1998] N. El Karoui, M. Jeanblanc-Picqué and S. Shreve. Robustness of the Black and Scholes formula. *Mathematical Finance*, 8(2):93–126, 1998.
- [Hull2018] J. Hull. *Options, Futures, and Other Derivatives*. Pearson, 10th edition, 2018. (Escrowed-dividend binomial trees.)
- [BoyleDykstra1986] J. Boyle and R. Dykstra. A method for finding projections onto the intersection of convex sets in Hilbert spaces. *Advances in Order Restricted Statistical Inference*, Springer, 1986.
- [BaroneAdesiWhaley1987] G. Barone-Adesi and R. Whaley. Efficient analytic approximation of American option values. *J. Finance*, 42(2):301–320, 1987.
- [BjerksundStensland2002] P. Bjerksund and G. Stensland. Closed form valuation of American options. Working paper, NHH, 2002.
- [Burkovska2018] O. Burkovska et al. Calibration to American options: numerical investigation of the de-Americanization method. *arXiv:1611.06181*.



