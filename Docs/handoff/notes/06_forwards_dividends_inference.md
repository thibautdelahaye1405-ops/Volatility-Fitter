# One Straight Line

**Note 06 — forwards, discounting and dividends · lecture edition ("told as a problem of statistical inference") · converted from 06_forwards_dividends_inference.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> Every smile in this series is drawn in forward-normalized coordinates, so before any volatility model runs, two numbers must be estimated from the chain itself: the forward $F$ and the discount $D$. Put–call parity makes them the two parameters of one straight line, $C-P=D\,(F-K)$, and this lecture reads the whole production apparatus as a single exercise in statistical inference on that line. Ordinary least squares identifies the line's *level* superbly and its *slope* poorly — on a realistic chain with two-cent quote noise, the forward is pinned to a fraction of a basis point while the implied rate wanders by tens (12 basis points measured, 11 predicted by the textbook variance formula) — and every robustness device in production is a response to that asymmetry, matched to how the data fails. A residual-trim loop rejects incoherent stale quotes; an exact lever-arm identity shows why re-deriving the forward from the ATM-weighted price *level* transmits almost none of a corrupted slope's error (0.8 bp per percent of rate error, against 50 for the intercept-over-slope reading); a physical band clamps the rate when the slope is untrustworthy; and when a delayed feed synthesizes a chain at zero carry, the design matrix is vacuous — regressed on the real captured fixture it returns rates from $-30.8\%$ to $-0.6\%$, several perfectly plausible — so an ingestion-time flag pins the forward to the chain's own construction convention rather than regressing at all. Dividends supply the carry model (four modes, distinguished less by their term structures than by the forward's spot-elasticity); an American de-bias removes the early-exercise contamination of the line at a fixed point that closes the put/call join (a raw 116-vol-bp ATM gap and 46 bp forward bias fall to 1 and 0.4); and the same estimation lens ends the note at the borrow — the carry component whose identifiability floor (13 bp at three months, 3 at one year, per ten basis points of quote noise) decides whether a hard-to-borrow read is a measurement or a guess.

**Contents**

1. One straight line
2. What the line identifies
3. Estimating on a dirty chain
4. A prior on the rate: the clamp
5. A design with no information: the pin
6. Dividends: the carry the forward carries
7. The American de-bias
8. The borrow, at the edge of identifiability
9. What is genuinely original here
10. Limitations
Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementations · References

---

## 1. One straight line

The forward is the anchor of the whole smile. Log-moneyness $k=\log(K/F)$, the at-the-money point, the put/call OTM split, the de-Americanization carry (Note 05) and the variance-swap replication (Note 08) are all defined relative to $F$; the discount $D$ normalizes every price. An error of a fraction of a percent in $F$ shifts the ATM strike and tilts the put–call balance, and the symptom is unmistakable: a *gap* in the at-the-money smile where the two OTM sides fail to meet. Neither number is quoted. Both are *estimated*, from the option prices themselves, through the one identity that European prices must satisfy:

**Central equation.**

$$
C(K)-P(K)\;=\;D\,(F-K).
\tag{1}
$$

A portfolio long a call and short a put pays $S_t-K$ at expiry, a forward contract; its price today is the discounted forward value of that payoff. Equation (1) is a straight line in $K$, and everything in this note is inference on that line: the discount is (minus) its slope, the forward is its root, and each production device below answers one question a statistician would ask of any regression. What do the data identify well, and what poorly ("What the line identifies")? What do outliers do ("Estimating on a dirty chain")? What prior knowledge should constrain the ill-identified direction ("A prior on the rate: the clamp")? When does the design contain no information at all ("A design with no information: the pin")? What does model error — here, early exercise — do to the observations ("The American de-bias")? And where is the edge beyond which a parameter, though real, is simply not identified by the data at hand ("The borrow, at the edge of identifiability")?

> **Heuristic.** The forward is a *fitted quantity with error bars*, and the two parameters of equation (1) are not equally blessed. The price difference $C-P$ is dollars tall (its level) but changes slowly across strikes (its slope), so the level is measured by every quote while the slope must be teased out of small differences between them. The design of this note's machinery is one epistemic rule applied three times: extract the forward where the data is informative (the level), refuse to trust what is ill-identified (the slope, on a noisy feed), and refuse to infer anything at all where the information is absent (a synthesized chain, "A design with no information: the pin").

> **Invariant.**
> 1. On a clean chain, every robustness device is byte-identical to the plain parity regression — the trim loop, the clamp and the de-bias engage only on demonstrably bad inputs.
> 2. The implied rate never leaves a physical band; when the slope is untrustworthy, the forward is re-derived from the well-identified price level.
> 3. The discount is *held* through the American de-bias — the two corrections never fight over the same parameter.
> 4. Parity is regressed only on prices that *contain* parity information: a chain synthesized from provider vols at zero carry is flagged explicitly and pinned to its construction convention $F=S$, $D=1$. The flag is never inferred from zero spreads — EOD close marks also quote $\mathrm{bid}=\mathrm{ask}$ yet their mids carry genuine parity information.
> 5. Editing a name's rate or dividends refits only that name: one ticker's noise never touches the universe.
> 6. Borrow is read only where identifiable — `unidentified` is an explicit state, never a silent zero — and the joint fixed point feeds fits only through an explicit toggle behind a materiality gate; below the gate the parity forward is kept exactly ("The borrow, at the edge of identifiability").

**Conventions and the notation ledger.** $S$ is spot, $F$ the forward and $D$ the discount to expiry, $K$ a strike, $t$ the calendar year fraction, $r=-\log(D)/t$ and $q=r-\log(F/S)/t$ the rate and carry the pair implies. $y(K)=C(K)-P(K)$ is the observed call–put mid difference; $\varepsilon$ the quote-noise standard deviation of one mid; $n$ the number of paired strikes; $\bar K$ their mean and $\bar K_w$ a weighted mean; $S_{KK}=\sum_i(K_i-\bar K)^2$ the design's strike dispersion. Hats mark estimates ($\hat F$, $\hat D$). Dividends are cash amounts $\delta_i$ at ex-dates $t_i$; $b$ is the borrow spread; $\pi$ the early-exercise premium of Note 05. One differentiation convention: subscripted $\partial$ for partials; no primes. One basis point of $F$ means $10^{-4}$ relative; a vol bp is $10^{-4}$ of absolute volatility.

**Table 1 — Every symbol in the note.** Regression coefficients get no letters of their own: the model *is* $(F,D)$.

| Symbol | Meaning |
|---|---|
| $S,\ F,\ D$ | spot, forward, discount |
| $K,\ \bar K,\ \bar K_w,\ S_{KK}$ | strikes; means; dispersion |
| $t,\ r,\ q$ | year fraction; implied rate, carry |
| $y(K)=C-P$ | the regressed observable |
| $\varepsilon,\ n$ | quote-noise sd; paired strikes |
| $w_i$ | level-estimator quality weights |
| $\delta_i,\ t_i$ | cash dividends, ex-dates |
| $b$ | borrow spread (carry $q=q_{\mathrm{div}}+b$) |
| $\pi_C,\ \pi_P$ | early-exercise premia (Note 05) |
| $\sigma,\ d_1$ | implied vol; Black argument |

## 2. What the line identifies

Fit equation (1) by least squares — regress $y$ on $K$, read $\hat D$ from the slope and $\hat F$ from the root. In production the fit is wrapped in the trim loop of "Estimating on a dirty chain", but on a clean chain the wrapper is inert and the algorithm of Appendix D is the whole procedure. Figure 1 runs it on the note's synthetic running example — $S=100$, $r=4\%$, a 1% carry, six months, cent-rounded quotes — and recovers the forward to 0.02 bp and the rate to 0.5 bp, with residuals at the tick scale (0.48 cents RMS over 20 paired strikes). So far, textbook. The lecture starts with the question of *how differently* the two parameters are identified.

> **Figure 1 — The whole estimation problem on one axis (figure not included in this pack).** The whole estimation problem on one axis (production fit, running example). A: the call–put difference is a straight line in strike; its slope is $-\hat D$, its root is $\hat F$. B: the residuals — cent rounding is the only noise here, and the line comes back to 0.02 bp of forward. Everything else in this note is about what happens to this picture on real feeds. Panel A plots $y(K)=C-P$ against strike for the 20 paired strikes of the running example: a visually perfect straight line descending through zero at $K=\hat F$. Panel B plots the fit residuals against strike: sub-cent scatter (0.48 cents RMS) with no structure, the signature of pure tick rounding.

**Proposition 1 (What OLS delivers on the parity line).** Let each mid carry independent noise of standard deviation $\varepsilon$, so the difference $y$ carries $\varepsilon\sqrt2$. Then the least-squares estimates of the line's *slope* and of its *level at $\bar K$* are uncorrelated, with

$$
\operatorname{sd}(\hat D)=\frac{\varepsilon\sqrt2}{\sqrt{S_{KK}}},
\qquad
\operatorname{sd}\big(\widehat{\,y(\bar K)\,}\big)=\frac{\varepsilon\sqrt2}{\sqrt n},
\tag{2}
$$

and the induced errors on the two market parameters separate, to first order, as

$$
\frac{\delta F}{F}
=\underbrace{\frac{\delta y(\bar K)}{D\,F}}_{\text{level noise}}
+\underbrace{\frac{F-\bar K}{F}\,\frac{\delta D}{D}}_{\text{slope noise}\times\text{lever}},
\qquad
\delta r=-\frac{\delta D}{D\,t}.
\tag{3}
$$

*Proof.* Center the regressor: with $x=K-\bar K$ the design columns $(1,x)$ are orthogonal, so the intercept (the level at $\bar K$) and the slope are uncorrelated with the standard variances (2) [SeberLee2003]. For (3), write the fitted root as $\hat F=\bar K+\hat y(\bar K)/\hat D$ (exact for OLS, in any parametrization) and expand to first order in the two independent errors; $\delta r$ is the chain rule on $r=-\log D/t$. ∎

Now put numbers in, because the asymmetry is the whole story. On the running example's design ($n=20$ strikes spanning $\pm20\%$), $\sqrt{S_{KK}}$ is of order fifty strike-dollars while $\sqrt n$ is of order four — but the slope error is then *divided by $t$* to become a rate, and multiplied only by the small lever $F-\bar K$ to reach the forward. The prediction: two cents of quote noise should scatter the implied *rate* by $\approx11$ bp while the *forward* moves by well under a basis point. Figure 2 runs 400 noisy chains through the production estimator: measured, 12 bp of rate scatter against 0.6 bp of forward scatter — the formula audited, and the design asymmetry established as fact. The slope is the worst-identified object in the problem; the level is nearly noiseless. Every section that follows leans on that fact.

> **Figure 2 — The identifiability asymmetry, measured (figure not included in this pack).** The identifiability asymmetry, measured (400 trials of two-cent quote noise through the production estimator). A: the parity-implied *rate* scatters by 12 bp (Proposition 1 predicts 11). B: the *forward* scatters by 0.6 bp (predicted 0.6). Same line, same noise, a two-orders-of-magnitude gap in reliability: the level is gold, the slope is lead. Each panel is a histogram over the 400 Monte-Carlo trials: panel A's rate histogram is wide, spanning tens of basis points around the true 4%; panel B's forward histogram is a needle, sub-basis-point around truth, with the predicted standard deviations overlaid and matching.

**Exercise 1.** Derive the two predictions quoted above from equation (2): with $\varepsilon=2$ cents, $n=20$ equally spaced strikes from $82$ to $120$, $D\approx0.98$, $t\approx0.5$, compute $\operatorname{sd}(\hat r)$ in basis points and $\operatorname{sd}(\hat F)/F$ in basis points (ignore the lever term first; then bound its contribution using $|F-\bar K|<1$). Compare with the measured 12 and 0.6.

## 3. Estimating on a dirty chain

Real chains carry stale and crossed quotes, and one gross point can drag a least-squares line. Production's answer is the classical one — an iterated trim: fit, form residuals, estimate a robust scale $\hat\sigma=\max(1.4826\cdot\mathrm{median}|{\rm resid}|,\ \text{a one-bp-of-spot floor})$, drop pairs beyond $4\hat\sigma$, refit — at most three rounds, never below three surviving pairs [RousseeuwLeroy1987]. Figure 3 stages the intended failure: a single deep put marked \$1.20 stale drags the raw regression to a 5.8% implied rate and an 8 bp forward error; the loop isolates the point in one round (1 trimmed) and the refit recovers the truth to 0.0 bp.

> **Figure 3 — The trim loop doing its job (figure not included in this pack).** The trim loop doing its job (production fit). A: one grossly stale deep put; the fitted line ignores it. B: residuals against the trimmed fit — the stale quote stands 30 robust sigmas out of a band whose other members are at the cent scale; it is dropped in the first round and the refit is exact to 0.0 bp. Without the loop the same point tilts the implied rate to 5.8%. Panel A shows the parity line through the paired strikes with the single stale point sitting visibly off the line; the trimmed fit passes through the clean points and ignores it. Panel B shows the residuals against the trimmed line: a cent-scale band of clean points and one 30-robust-sigma outlier, flagged and removed in round one.

**Remark 1 (What the trim cannot see: coherent staleness).** A residual trim detects points that disagree with the consensus line. Two stale quotes that agree *with each other* on the same wing are a different animal: rerunning the experiment with two coherent stale puts, the corrupted line fits them well, nothing is trimmed (0 outliers flagged), and the implied rate lands at 8.1% — *inside* the physical band of "A prior on the rate: the clamp", so the clamp passes it too. This is the masking phenomenon of robust statistics [RousseeuwLeroy1987]: coherent contamination on one wing is observationally a carry change. What contains the damage is Proposition 1's asymmetry itself — the level stays robust, so the forward moves only 12 bp while the rate absorbs the staleness. The honest summary of the defence ladder: the trim catches incoherent outliers, the clamp catches absurd slopes, and coherent plausible staleness is caught by neither — it is bounded, not fixed.

## 4. A prior on the rate: the clamp

"What the line identifies" says the slope is fragile; "Estimating on a dirty chain" says some failures evade the trim. On a noisy or stale delayed feed the parity slope drifts far enough to imply a discount above one — a *negative* rate — and the question is what to do when the data's least reliable parameter contradicts prior knowledge.

> **Caution.** A negative implied rate on a US equity chain is not a market signal; it is feed noise sitting in the regression's worst-identified direction. Letting it through converts a small price error into a large level error downstream — the discount scales every normalized price, and the tilted slope reaches the forward through the lever of equation (3). The forward's level is well identified; its slope is not; treat them accordingly.

The device is Bayesian in spirit if not in ceremony: a hard prior on the rate, $r\in[-5\%,30\%]$, applied only when a reference date pins the year fraction. The year fraction itself is settlement-aware down to the sub-day: a same-day expiry is clamped over the hours to its settlement instant rather than an unrepresentable zero, while chains without settlement metadata keep the legacy whole-day skip — both paths test-locked. Clean chains sit strictly inside the band and pass byte-identically (invariant 1). When the clamp bites, the discount is set to the band edge — and the forward must then be re-estimated, because $\hat F=\hat a/\hat D$ would inherit the very slope just rejected. Production re-derives it from the price *level*: a per-strike average of $K+y(K)/D$, weighted by quote quality (inverse spread, floored) times a Gaussian ATM kernel of width $0.10$ in log-moneyness. Why that works is an identity worth isolating:

**Proposition 2 (The lever arm of a level estimator).** Let $\hat F_w(D')=\sum_iw_i\big(K_i+y_i/D'\big)$, $\sum w_i=1$, be a level estimator evaluated at a possibly wrong discount $D'$. On noiseless data obeying equation (1),

$$
\hat F_w(D')-F=\Big(1-\frac{D}{D'}\Big)\,\big(\bar K_w-F\big),
\qquad \bar K_w=\sum_iw_iK_i .
\tag{4}
$$

The transmitted error is the discount error times the *lever arm* $\bar K_w-F$: where the estimator centers its strikes decides how much a wrong discount can hurt it.

*Proof.* Substitute $y_i=D(F-K_i)$: $K_i+y_i/D'=K_i(1-D/D')+F\,D/D'$, and average. ∎

Three readings of equation (4), measured in Figure 4. The intercept-over-slope reading $\hat F=\hat a/\hat D$ is the $w$ concentrated at $K=0$: lever $=F$ itself, and a 1% rate error moves the forward 50 bp. A uniform average over the board has lever $\bar K-F$ — small only by the accident of a balanced board (3.2 bp per percent here, on a deliberately asymmetric one). The production kernel centers $\bar K_w$ at the money, lever $\approx S-F$ — the carry itself — and transmits 0.8 bp per percent: the forward is read where the discount error *cannot reach it*. A final sanity bound $|\log(F/S)|<0.5$ falls back to spot if even the level is unusable.

> **Figure 4 — The lever-arm identity, measured (figure not included in this pack).** The lever-arm identity, equation (4), measured on an asymmetric board. Impose a rate error and re-derive the forward three ways: through the intercept-over-slope reading (lever $=F$: 50 bp per percent of rate error), a uniform level mean (lever $=\bar K-F$: 3.2), and the production ATM-kernel level (lever $\approx S-F$: 0.8). The clamp can afford to be crude about the rate precisely because the level estimator barely feels it. The figure plots transmitted forward error against imposed rate error for the three estimators: three straight lines through the origin whose slopes are the three lever arms, spanning nearly two orders of magnitude from the naive reading down to the production kernel.

> **Example — Case file: the delayed feed that gapped the ATM smile.**
>
> **Setup.** Live SPY on the Massive delayed feed; also reproduced on a Bloomberg fixture. Quotes individually sane but collectively stale — mids drifting asynchronously across strikes.
>
> **Failure.** Parity discounts of $1.01$–$1.015$ live (up to $1.024$ on the fixture): implied *negative* rates. The tilted slope dragged the forward, and every ATM smile showed the telltale gap between the put and call sides.
>
> **The failed first fix.** Anchoring the rate per expiry to a smoothed term structure looked principled — and broke everything: the per-expiry discounts came out jagged, the LV benchmark regressed, and the attempt deadlocked the forwards state. Reverted. The lesson: do not repair an ill-identified parameter by giving it *more* fitted structure; stop trusting it.
>
> **Fix.** The clamp: pin the rate to the physical band, re-derive the forward from the quality-weighted level (Proposition 2), keep spot as the last resort. The discount stays exactly what parity gave whenever it is physical.
>
> **Verdict (test-locked).** Clean chains recover truth and pass unclamped, byte-identical; stale-wing chains that break the raw regression stay sane; zero-spread close-like marks still resolve; with no reference date the clamp correctly stands down. The residual ATM jitter on the delayed feed is feed noise, not the forward. The scenario is registered as certification case `stale_crossed_markets`.

**Exercise 2.** Prove the corollary used above: for the intercept-over-slope reading, $\hat F(D')=\hat a/D'$ with $\hat a=DF$ exactly, so $\hat F(D')-F=F\,(D/D'-1)$ — i.e. equation (4) with $\bar K_w=0$. Then explain, in one sentence, why quoting options on a *forward-moneyness* grid (strikes labelled by $K/F$) would make the uniform level mean nearly as good as the kernel one.

The clamp bounds an *absurd* answer. One failure mode remains that it cannot see: a chain whose parity content is exactly zero, where the regression returns wrong answers that are perfectly *plausible*. That needs its own device, and its own section.

## 5. A design with no information: the pin

Delayed data tiers can gate the live quote stream. When that happens the provider does not return an empty chain — it *synthesizes* one from its per-contract implied vols, pricing every contract with Black at $F=S$, $D=1$, and quoting it with zero spread. Statistically, the resulting design is *vacuous*: the forward and discount were not observed but assumed, so the true parity content of the prices is zero. Worse, the provider's call and put vols embed its *own* carry model, so once its contracts are re-priced at zero carry a call/put asymmetry survives in the prices — and a parity regression dutifully reads that asymmetry as a forward and discount nobody ever quoted.

Figure 5 regresses the real captured fixture — the very chains the incident below was about — one expiry at a time. The implied rates run from $-30.8\%$ at the short end to $-0.6\%$ at a year: the shortest are absurd (the clamp would bound them), but most sit *inside* the physical band, wrong in a way no bound can detect. And the residuals offer no warning either: the fits are feed-noise sized (median 21.2 bp of spot). A regression cannot diagnose the vacuity of its own design from within; the only honest detector lives *upstream*, where the synthesis is known.

> **Figure 5 — The vacuous design, on the real synthesized SPY fixture (figure not included in this pack).** The vacuous design, on the real synthesized SPY fixture (production regression per expiry, no pin). A: parity-implied rates — all negative here, running to $-30.8\%$ at the short end; the absurd ones would be clamped, the plausible ones would pass, and *all* of them are artifacts of the provider's synthesis at $F=S$, $D=1$. B: the fit residuals are ordinary feed noise — no diagnostic in the regression says the design carries zero parity information. The pin answers with the only thing the chain truly contains: its construction convention. Panel A plots the per-expiry parity-implied rate against maturity for the captured fixture's expiries: a curve of negative rates from $-30.8\%$ at the short end shrinking toward $-0.6\%$ at one year, with the physical band drawn so the reader can see most points landing inside it. Panel B plots the per-expiry fit RMS residual: a flat, unremarkable band around the 21.2-bp-of-spot median — indistinguishable from a healthy chain.

> **Example — Case file: the garbage forwards the clamp could not see.**
>
> **Setup.** Live SPY on the Massive delayed tier, recurring over several sessions: the tier gated the NBBO stream, so every chain the application received was IV-synthesized at zero carry.
>
> **Failure.** Recurring garbage forwards on a healthy-looking feed: short-dated implied rates near $-4\%$, discounts above one, a one-year forward $1.7\%$ *above* the $F=S$ the prices had been built with. The discount clamp stayed silent throughout — the spurious rates sat inside the physical band, so there was nothing absurd to bound. (The same saga's failed first fix — the smoothed rate term structure — is the one already dissected in "A prior on the rate: the clamp".)
>
> **Diagnosis.** The regression was not noisy; it was answering a question the data could not ask. Every synthesized price is Black at $F=S$, $D=1$, so the only structure left is the provider's call/put vol asymmetry — a spurious signal small enough to be plausible, which is exactly why a clamp built for absurd slopes never fired.
>
> **Fix.** Recognize the regime at ingestion, not in the regression. The provider layer flags the synthesized snapshot; for a flagged chain the resolver returns the chain's own construction convention — $F=S$, $D=1$, zero residual — and never regresses. The flag is explicit and persists with the snapshot, so captured chains replay correctly; it is deliberately *not* inferred from chain-wide zero spreads, because EOD close marks also quote $\mathrm{bid}=\mathrm{ask}$ yet their mids carry genuine parity information (invariant 4). The Forwards tab badges the regime so the desk knows the forward is a convention, not a market read.
>
> **Verdict (test-locked).** A flagged zero-carry chain pins to $F=S$, $D=1$ on both resolution paths; an *unflagged* zero-spread chain still regresses and recovers its true carry; the flag round-trips through the store. The recurring SPY forward incident is closed at the root, and registered as certification case `zero_carry_chains`.

The pin completes an epistemic ladder that is worth stating as the section's moral. *The regression* extracts the forward where parity is informative; *the clamp* refuses the slope where parity is noisy; *the pin* refuses the regression entirely where parity is vacuous, returning the only honest answer the chain contains — its own construction convention. The regime matters downstream too: on such feeds anything that needs a carry (Note 05's de-Americanization, for one) must source it externally, because the parity-implied carry is not merely noisy but meaningless.

## 6. Dividends: the carry the forward carries

The carry linking spot to forward must account for dividends, and the model is per ticker, editable, and shared with the de-Americanization tree (Note 05). Four modes coexist. **Discrete cash**: a schedule of ex-dates and amounts $\delta_i$, priced by escrow — $F=(S-\sum_i\delta_ie^{-rt_i})\,e^{rt}$, the diffusing base being spot minus the present value of the dividends the holder will not receive. **Discrete proportional**: percentage haircuts per event, $F=S\,e^{rt}\prod_i(1-\delta_i)$. **Continuous yield**: a constant $q$, the cheap proxy. **Mixed**: cash for near ex-dates, switching to a proportional treatment beyond a horizon — the realistic single-name default shape. An equivalent-yield round trip across all four modes is test-locked; on the running schedule the one-year cash leg is worth $q_{\mathrm{eq}}=2.59\%$ of continuous carry.

What distinguishes the modes is *not* primarily the term structure. Figure 6A shows the static picture: the cash schedule is a sawtooth in implied carry — violent at the short end, where one \$0.65 ex-date thirty days out annualizes to nearly 8% — against the flat continuous proxy. But at a fixed spot a cash schedule and a proportional one of matching size produce nearly identical forwards; the economic difference appears when *spot moves*. Differentiating the escrow formula, the forward's spot elasticity is

$$
\frac{\partial\log F}{\partial\log S}
=\frac{S}{S-\sum_i\delta_ie^{-rt_i}}\;>\;1
\quad\text{(cash)},\qquad
\frac{\partial\log F}{\partial\log S}=1\quad\text{(proportional, yield)}:
\tag{5}
$$

cash dividends do not scale with the stock, so a rally makes the forward outrun spot. Figure 6B measures equation (5) on the production forward by direct bump: the cash staircase climbs past $1.05$ at two years of accumulated escrow while the proportional and yield modes sit at exactly one. (The mixed mode's far leg re-reads its cash amounts as fractions of the *prevailing* spot, so its elasticity stays cash-like — a subtlety of quoting far dividends in dollars, and the reason the mode exists is the near leg's timing, not its dynamics.) This elasticity is precisely what sticky-strike scenario transport (Note 12) inherits from the dividend model, and why the mode choice is a risk decision, not a cosmetic one.

> **Figure 6 — Dividend modes, static and dynamic (figure not included in this pack).** Dividend modes, static and dynamic (production forwards, one \$0.65-quarterly schedule). A: the implied-carry term structure — the cash schedule's sawtooth against the flat continuous proxy; each tooth is one ex-date entering the horizon. B: the honest discriminator, the forward's spot elasticity, equation (5): cash escrow makes the forward outrun spot by an accumulating margin; proportional and yield modes track it exactly. At a fixed spot the modes look alike; on a moving one they are different risk models. Panel A plots implied carry against maturity: the cash mode's sawtooth spikes toward 8% annualized at the shortest horizons (one \$0.65 ex-date thirty days out) and decays as the horizon accumulates more ex-dates, while the continuous-yield proxy is a flat line. Panel B plots the bump-measured elasticity $\partial\log F/\partial\log S$ against maturity: the cash mode is a staircase climbing past 1.05 by two years, the proportional and yield modes sit pinned at exactly 1.

## 7. The American de-bias

For American chains the observable itself is contaminated: parity (1) is a *European* identity, but the mids on the line are American,

$$
y_{\mathrm{Am}}(K)=y_{\mathrm{Eu}}(K)+\pi_C(K)-\pi_P(K),
\tag{6}
$$

and the early-exercise premia $\pi_C,\pi_P$ (Note 05) are neither equal nor constant in strike — under positive rates the put premium dominates and grows with $K$. In regression language this is structured errors-in-variables: a strike-dependent bias in the observable that corrupts both level and slope. The measured damage on the running American example (a 5%-rate board): the raw regression's forward is biased by 46 bp and its implied rate reads $-1.09\%$ against a true 5% — and, most visibly, the carry error splits the de-Americanized put and call vols by 116 vol bp at the money (Figure 7A), the ATM-kink symptom that first motivated this machinery.

There is an apparent circularity — de-Americanization needs the carry, the carry comes from the forward, the forward needs de-Americanized prices — and production closes it as a fixed point, coarse and cheap, with the discount *held* (invariant 3). Fixing $r=-\log D/t$ from the raw parity: each round sets $q=r-\log(F/S)/t$ from the current forward, de-Americanizes a near-ATM band of mids on a coarse tree, reprices them as European, and re-implies the forward at the fixed slope $-D$; six rounds at most, converged at a relative $5\times10^{-5}$. A full-depth gate then asks whether the de-Americanized put and call vols *join* at the money; if a gap above half a vol bp per side survives, the rate itself is bisected toward the band edge until the join closes — the joint $(r,F)$ refinement, still inside the physical band, still holding the parity residual as the arbiter. On the example the de-biased estimate recovers the forward to 0.4 bp, the rate to $4.74\%$, and the ATM join to 1 vol bp (Figure 7B). Only a near-ATM band and a coarse tree enter — the whole refinement costs milliseconds and locates the forward to a basis point; quote prep then runs the full-precision per-quote de-Americanization downstream, under the refined carry (Note 05's resolution of the same circle, seen from the other side).

> **Figure 7 — The de-bias, before and after (figure not included in this pack).** The de-bias, before and after (production resolution on a 5%-rate American board; production trees for the diagnostic). A: at the raw parity carry, the de-Americanized call and put vols disagree by 116 vol bp at the money and slope apart — the ATM kink, and a 46 bp forward bias underneath it. B: at the de-biased carry the two sides join to 1 vol bp on a common flat 25%; the forward is recovered to 0.4 bp with the discount held throughout. Panel A plots the de-Americanized put-side and call-side implied vols across strikes under the raw parity carry: two branches that fail to meet at the money, gapped by 116 vol bp and sloping apart. Panel B repeats the plot under the de-biased carry: both branches lie on one flat 25% line, joined at the money to 1 vol bp.

## 8. The borrow, at the edge of identifiability

The estimation lens has one more thing to say, about the carry component this note has so far bundled silently into $q$: the *borrow* $b$, the financing spread on hard-to-borrow names, $q=q_{\mathrm{div}}+b$. Before the estimation question, name the object that carries the answer. Production's carry is not a scalar but a versioned per-expiry decomposition — discount, dividends, borrow — in which *every leg carries a source tag*: observed, desk-supplied, parity-implied, or `unidentified`. The last tag is a design decision, not an apology; the identifiability verdict below is rendered per expiry, and an expiry the board cannot resolve says so instead of saying zero.

On top of that object sits a joint solver — the same fixed-point pattern as "The American de-bias", iterating the borrow until the de-Americanized, European-repriced board's parity forward matches the theoretical forward at carry $q_{\mathrm{div}}+b$, with the *same* dividend schedule riding both legs so the early-exercise premium cannot leak twice. The solver works: on a synthetic chain with a planted 300 bp borrow the fixed point returns 299.8 (the regression lock admits 20; the naive read is required to be at least twice as far), contracting in two to four iterations to a parity gap below a tenth of a basis point; an ordinary name converges immediately to the naive read, and a European chain short-circuits in one step. The honest question, in this note's language, is therefore not whether $b$ can be *computed* but whether it is *identified* at all. Two closed forms answer it, both shipped as diagnostics.

First, materiality. At fixed strike and price, a borrow shift moves the forward by $\partial F/\partial b=-tF$, and re-inverting an unchanged ATM price moves the implied vol by

$$
\frac{\partial\sigma}{\partial b}
=\frac{tF\cdot\partial_FC}{\partial_\sigma C}
=\frac{tF\cdot D\,\Phi(d_1)}{D\,F\,\varphi(d_1)\sqrt t}
=\sqrt t\;\frac{\Phi(d_1)}{\varphi(d_1)},
\tag{7}
$$

about $125\sqrt t$ vol bp per 100 bp of borrow near the money (Figure 8A): borrow uncertainty is a first-order smile input at any maturity past a few weeks. Second, precision. The parity forward is known to roughly $\mathrm{rms}/\sqrt n$ of spot (Proposition 1's level line), and the borrow divides that by $t$: the *noise floor*

$$
b_{\min}\approx\frac{\mathrm{rms}/S}{t\,\sqrt n}
\tag{8}
$$

is the smallest borrow the board can resolve — 13 bp at three months and 3 bp at a year for ten basis points of quote noise, but 16 bp at a year on a fifty-bp-noise board, and hundreds at a week on any board (Figure 8B). The floor ships under its own name — `borrowNoiseFloorBp`, riding the carry payload per expiry and drawn as the $\pm\sigma$ columns of the Forwards view — and it states its own honesty: it ignores the regression's leverage on $F$, measured at another $1.5$–$2\times$ on real boards. The conclusion equations (7) and (8) force is the strategic one: borrow *matters* (large $\partial\sigma/\partial b$) exactly where it may not be *measurable* (floor above the plausible borrow), and a publishable borrow read exists only where the sensitivity-times-uncertainty product clears the floor.

What shipped therefore splits into two consumption paths, and the split is the section's practical conclusion. *Measurement is always on*: the Forwards view shows the joint read beside the naive one, with iteration and tree-failure counts, the source tags, and the noise floor. *Fitting is an explicit opt-in*: the converged $(F,D)$ enters fits only through a toggle, engaged per expiry only when the implied borrow clears a 25 bp materiality gate — below it the parity forward is kept exactly, so ordinary names are byte-identical even with the toggle on. The *publishing* gate for the borrow read itself remains open work: on the real hard-to-borrow captures, a flat financing rate biases the borrow one-for-one (a rate *curve* is the missing input), and held-out validation sits below thin-board noise — measured conclusions, recorded with the machinery, waiting on better inputs rather than better mathematics.

> **Figure 8 — The borrow's two closed forms (figure not included in this pack).** The borrow's two closed forms (production diagnostics). A: materiality — ATM implied vol moved per 100 bp of borrow, equation (7): 62 vol bp at three months, 126 at a year. B: precision — the identifiability floor, equation (8), against maturity for two quote-noise levels, with typical hard-to-borrow levels shaded: a week-dated board cannot resolve any realistic borrow; a clean six-month board resolves tens of basis points. A borrow read is publishable exactly where the shaded band clears the floor. Panel A plots $\partial\sigma/\partial b$ against maturity, the $\sqrt t$ growth of equation (7) passing through 62 vol bp per 100 bp of borrow at three months and 126 at a year. Panel B plots the noise floor $b_{\min}$ against maturity on a log scale for ten-bp and fifty-bp quote noise, falling like $1/t$, with a shaded band of typical hard-to-borrow levels crossing the floor curves at the maturities where a read becomes publishable.

**Exercise 3.** From equation (8): how well can a one-week expiry ($t=1/52$) with ten paired strikes and ten basis points of quote noise pin the borrow? (Answer: to no better than about 165 bp — worse than most hard-to-borrow levels themselves.) Conclude which expiries a borrow term-structure read should weight, and why the joint solver's per-expiry results must never be averaged with equal weights.

## 9. What is genuinely original here

Parity forward extraction is textbook [Hull2017]; the contribution is the estimation discipline wrapped around one straight line:

1. the *level/slope epistemics*, made exact by Propositions 1 and 2 and enforced by the clamp: trust the well-identified level, distrust the ill-identified slope, and re-derive the forward with a lever arm of $S-F$ instead of $F$;
2. the *zero-carry pin*: the recognition that a synthesized chain is a vacuous design — undetectable from residuals, undetectable by any bound on plausibility — so the regime is flagged at ingestion and the resolver returns the construction convention rather than an estimate;
3. the *de-bias fixed point* with the discount held, closing the forward/de-Americanization circle at exactly the carry quote prep will use, with the ATM join as the arbiter;
4. the *identifiability accounting for borrow* (equations (7)–(8)): materiality and measurability computed side by side, so an unidentified borrow is reported as such instead of published as a number.

All of it is byte-identical on clean data: the robustness costs nothing when it is not needed (invariant 1).

## 10. Limitations

Where the guarantees stop. Parity (1) is a European identity, and the de-bias removes the American contamination only within Note 05's model (CRR diffusion, deterministic dividends); what the model does not span, the fixed point cannot repair. The clamp's band is a prior — correct for US equity carry today, an assumption nonetheless — and the coherent-staleness masking of Remark 1 passes both trim and clamp, bounded only by the level's robustness. The pin trusts the provider's flag: a synthesized chain that arrives *unflagged* would be regressed in good faith (the flag's persistence and its never-inferred-from-spreads rule are test-locked, but the upstream detection is the provider layer's burden). Each expiry is resolved independently — there is deliberately no cross-expiry smoothing after the reverted term-structure fix, which trades away noise pooling for robustness to one bad expiry. And the borrow work is machinery ahead of its inputs: a flat financing rate biases the read one-for-one, so a rate curve — not more iterations — is the missing piece, and the publishing gate stays open until held-out validation clears thin-board noise.

## Appendix A. Hyperparameter atlas

**Table 2 — Forward/dividend/borrow hyperparameters.**

*Surfaced:*

| Knob | Default | Role |
|---|---|---|
| `ForwardPolicy.mode` | `parity` | `parity` (regression) or `theoretical` (carry model). |
| `MarketSettings.rate` $r$ | — | Risk-free rate for the theoretical forward / trees. |
| `dividendMode` | `continuous` | `continuous`, `discrete_absolute`, `discrete_proportional` or `mixed`. |
| `dividends` / `switch_years` | empty / $1.0$ | Discrete (ex-date, amount) schedule; mixed-mode horizon. |
| `jointCarry` | `false` | Gated fit-path joint borrow ("The borrow, at the edge of identifiability"); ordinary names byte-identical with the toggle on. |
| `jointCarryEngageBp` | $25$ | Borrow materiality gate: the fit path engages per expiry only above it; below, the parity forward is kept exactly. American chains only. |

*Hidden (parity fit / clamp):*

| Knob | Default | Role |
|---|---|---|
| `RATE_MIN/MAX` | $[-5\%,30\%]$ | Physical band for the parity-implied rate. |
| `FWD_CLAMP_LOG` | $0.5$ | Sanity bound on $\lvert\log(F/S)\rvert$; else fall back to spot. |
| `MIN_PAIRED_STRIKES` | $3$ | Minimum paired strikes for a parity fit. |
| `OUTLIER_NSIGMA` / `MAX_TRIM_ROUNDS` | $4$ / $3$ | Residual trim threshold (robust MAD scale, floored at $1$ bp of spot) and iteration cap. |
| `ATM_KERNEL_H` / `SPREAD_FLOOR_FRAC` | $0.10$ / $5\times10^{-4}$ | ATM kernel width and spread floor in the level-re-derivation quality weights. |

*Hidden (American de-bias):*

| Knob | Default | Role |
|---|---|---|
| `DEAM_REFINE_BAND` / `_MAX_STRIKES` | $0.15$ / $11$ | Log-moneyness band and strike cap entering the fixed point. |
| `DEAM_REFINE_STEPS` / `_BISECT` | $48$ / $16$ | Coarse tree for the forward-only fixed point. |
| `MAX_DEAM_ITERS` / `FORWARD_TOL_REL` | $6$ / $5\times10^{-5}$ | Fixed-point cap and convergence tolerance. |
| `GAP_TOL_VOL` / `GAP_KERNEL_H` | $5\times10^{-4}$ / $0.01$ | ATM-join gate: tolerance and kernel width of the read at $F$. |
| `GAP_TREE_STEPS/_BISECT` | $192$ / $24$ | Full-depth tree for the gate and the rate bisection. |
| `GAP_BISECT_ITERS` / `GAP_RATE_TOL` | $24$ / $10^{-4}$ | Rate-bisection caps (bracket toward the band edge; sign change required). |

*Hidden (joint borrow):*

| Knob | Default | Role |
|---|---|---|
| `TOL` / `MAX_ITER` | $10^{-5}$ / $8$ | Borrow fixed-point convergence and cap. |
| `BORROW_CAP` | $2.0$ | Hard cap on $\lvert b\rvert$ (200% financing). |
| `N_STEPS` / `BISECTIONS` | $96$ / $20$ | Coarse de-Am tree inside the borrow loop. |
| `MIN_PAIRS` | $6$ | Minimum call/put pairs for a borrow read. |

## Appendix B. Performance notes

The parity regression is a $2\times2$ least squares per expiry; the trim adds at most three refits; the clamp is a comparison. The de-bias is a handful of coarse-tree de-Americanizations on a near-ATM band — about a basis point of forward located in a few milliseconds — and its full-depth gate runs once, with the rate bisection engaging only when the ATM join fails. All are negligible against a smile fit. Editing a name's rate or dividend schedule bumps only that ticker's forwards version, refitting just that name (invariant 5). The joint borrow solver is likewise a per-expiry fixed point over coarse trees, run as a diagnostic column rather than on the fit path unless its toggle is on.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 3 — Claims in this note and the code/tests that lock them.**

| Claim | Object | Code anchor / *Test anchor* |
|---|---|---|
| Clean chain: truth recovered, clamp inert (byte-identical) | "A prior on the rate: the clamp" | `volfit/data/forwards.py` / *`tests/test_forward_robust.py::test_clean_chain_recovered_to_truth_and_unclamped`* |
| Stale wings break the raw regression; clamp stays sane | case file | `volfit/data/forwards.py` / *`tests/test_forward_robust.py::test_stale_wings_break_unclamped_but_clamp_stays_sane`* |
| Zero-spread close-like marks still resolve | invariant 4 | `volfit/data/forwards.py` / *`tests/test_forward_robust.py::test_zero_spread_close_like_data_still_resolves_sane`* |
| No reference date ⇒ clamp stands down | "A prior on the rate: the clamp" | `volfit/data/forwards.py` / *`tests/test_forward_robust.py::test_no_reference_date_skips_clamp`* |
| Zero-carry chain pinned to $F=S$, $D=1$ (flag decides, both paths) | "A design with no information: the pin" | `volfit/data/forwards.py`, `volfit/data/types.py` / *`tests/test_forward_robust.py::test_zero_carry_chain_pins_forward_to_spot`* |
| Zero spreads alone never trigger the pin | invariant 4 | `volfit/data/types.py` / *`tests/test_forward_robust.py::test_unflagged_zero_spread_chain_still_regresses`* |
| Provider flags synthesized chains; flag persists (schema v5) | "A design with no information: the pin" | `volfit/data/massive.py`, `volfit/data/store.py` / *`tests/test_massive.py::test_iv_fallback_synthesizes_fittable_chain`; `tests/test_data_layer.py::test_snapshot_round_trip_keeps_zero_carry`* |
| Raw American board: biased forward, ATM kink | equation (6) | `volfit/data/forwards.py` / *`tests/test_forward_debias.py::test_raw_american_forward_is_biased_and_kinks`* |
| De-bias holds the discount, recovers forward and rate, joins the sides | "The American de-bias" | `volfit/data/forwards.py` / *`tests/test_forward_debias.py::test_debias_recovers_discount_and_forward_and_smooths`* |
| Short-dated gate keeps the raw discount bit-for-bit | "The American de-bias" | `volfit/data/forwards.py` / *`tests/test_forward_debias.py::test_short_dated_chain_keeps_raw_discount`* |
| No localized ATM spike after de-bias; European chains unaffected | "The American de-bias" | `volfit/data/forwards.py` / *`tests/test_forward_debias.py::test_debiased_smile_has_no_localized_atm_spike`; `::test_european_chain_unaffected_by_reference_date`* |
| 0DTE: sub-day settlement horizon clamps; legacy path skips | "A prior on the rate: the clamp" | `volfit/data/forwards.py` / *`tests/test_forward_robust.py::test_same_day_noisy_discount_clamped_over_subday_horizon`; `::test_same_day_without_settlement_keeps_legacy_skip`* |
| All four dividend modes; equivalent-yield round trip | "Dividends: the carry the forward carries" | `volfit/data/dividends.py` / *`tests/test_dividends.py::test_equivalent_yield_round_trips_every_mode`; `::test_mixed_forward_switches_at_horizon`* |
| Joint borrow fixed point; noise floor; dIV/db | equations (7), (8) | `volfit/data/carry_solve.py` / *`tests/test_carry_solve.py`* |
| Per-ticker forwards version scoping | invariant 5 | `volfit/api/state.py` / *`tests/test_api_forwards.py::test_parity_defaults_cover_the_ladder`* |

## Appendix D. Reference implementations

Two reference listings existed here, both executed against production by this edition's generator before the note was committed; per the transfer policy they are replaced by exact algorithm specifications. The parity regression below reproduces the production fit on the clean running example to $10^{-16}$ (floating-point identity; production wraps the same least squares in the trim loop, inert on clean data). The clamp specification reproduces production's clamped *rate* exactly on the tilted-board demo (raw rate $-6.9\%$, clamped to $-5.0\%$, agreement $0.0\times10^{0}$, i.e. exact) and its re-derived forward to 0 bp — the production version replaces the uniform mean with the quality-weighted, spot-fallback-guarded estimator of Proposition 2, which on this symmetric board is the same number to under a basis point.

> **Algorithm — put–call parity regression for the forward and discount (replaces the reference listing distilled from `data/forwards.py`).**
>
> *Inputs:* a strike vector $K$ and the paired call and put mid vectors on those strikes.
>
> *Outputs:* the implied forward $\hat F$ and discount $\hat D$.
>
> 1. Form the observable $y_i = C_i - P_i$, which by equation (1) obeys $y = DF - DK$.
> 2. Fit a degree-one polynomial of $y$ on $K$ by least squares, obtaining slope $b$ and intercept $a$.
> 3. Read the discount from the slope: $\hat D = -b$.
> 4. Read the forward from the intercept over the discount: $\hat F = a/\hat D$.
>
> Production uses a least-squares solve inside the outlier-trim loop of "Estimating on a dirty chain" (robust-MAD scale, $4\hat\sigma$ threshold, at most three rounds, never below three surviving pairs) and takes the chain snapshot, not raw arrays; on clean data the wrapper is inert and this specification is the whole algorithm, agreeing with production to $10^{-16}$.
>
> **Algorithm — the discount clamp and level re-derivation (replaces the reference listing simplified from `data/forwards.py`).**
>
> *Inputs:* strikes $K$, call and put mids, year fraction $t$, the regression's $(\hat F,\hat D)$, and the physical rate band $[r_{\mathrm{lo}},r_{\mathrm{hi}}] = [-5\%,30\%]$.
>
> *Outputs:* the possibly clamped pair $(F,D)$.
>
> 1. Compute the parity slope's implied rate $r = -\log(\hat D)/t$.
> 2. If $r_{\mathrm{lo}} \le r \le r_{\mathrm{hi}}$: the slope is physical; return the regression result $(\hat F,\hat D)$ unchanged.
> 3. Otherwise clamp the rate to the band, $r \leftarrow \mathrm{clip}(r, r_{\mathrm{lo}}, r_{\mathrm{hi}})$, and set the discount to the band edge: $D = e^{-rt}$.
> 4. Re-derive the forward from the price *level*, not the rejected slope: average $K_i + (C_i-P_i)/D$ over strikes (lever $\bar K - F$, Proposition 2). In production this uniform mean is replaced by the quality-weighted level estimator — weights proportional to inverse spread (floored at `SPREAD_FLOOR_FRAC` $=5\times10^{-4}$) times a Gaussian ATM kernel of width $0.10$ in log-moneyness — with the spot fallback of "A prior on the rate: the clamp" guarding $\lvert\log(F/S)\rvert<0.5$.
> 5. Return $(F, D)$.

## References

- [Hull2017] J. Hull. *Options, Futures, and Other Derivatives*. Pearson, 10th ed., 2017.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.
- [SeberLee2003] G. Seber and A. Lee. *Linear Regression Analysis*. Wiley, 2nd ed., 2003.
- [RousseeuwLeroy1987] P. Rousseeuw and A. Leroy. *Robust Regression and Outlier Detection*. Wiley, 1987.


