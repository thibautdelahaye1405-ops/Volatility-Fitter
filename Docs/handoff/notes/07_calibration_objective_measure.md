# What the Optimizer Sees

**Note 07 — The calibration objective as a choice of units, a measure, and a tolerance · lecture edition ("units, measure, tolerance") · converted from 07_calibration_objective_measure.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** Every model in this series — LQD, SVI, Multi-Core Sigmoid, local volatility — is calibrated by minimizing the same kind of objective, and before any model-specific mathematics runs, three decisions have already shaped what the optimizer can possibly find: the *units* the residual is measured in, the *measure* the residuals are summed against, and the *tolerance* inside which a residual counts as zero. This lecture develops the shared objective as exactly those three choices. Units: a least-squares loss silently asserts a noise model, and the vega-normalized price residual is the change of coordinates under which quote noise is homogeneous — a uniform $50$ vol bp misfit that price units squash by an order of magnitude in the wings reads flat to 3.0 vol bp after normalization (and the dictionary is honestly local: at $300$ bp the second-order vomma term is worth up to 125 bp in the wings). Measure: per-quote weights are a quadrature rule — equal weights integrate the smile against the accident of the exchange's listing density, while the density-corrected time-value scheme integrates against the declared time-value measure, tracking its continuum integral to a Kolmogorov distance of 0.062 where equal weights distort it to 0.14. Tolerance: the bid–ask band objective is an $\varepsilon$-insensitive loss whose per-quote tube is the quoted spread; alone it has a flat valley of minimizers 126 vol bp wide on a clean chain, and the small mid anchor is the declared rule for selecting one representative from it. The band's practical value is then stated more sharply than "it ignores noise": inside the tube the data term's weight drops from $1$ to $0.05$, a factor-twenty relief in the data-versus-regularization contest — worth 6 vol bp on a rigid model and 47 on a flexible one, measured on production fits. The reported RMS mirrors whichever objective was actually minimized, and a haircut dial sweeps the whole construction continuously from band back to mid.

**Contents:** 1. Three decisions before any model fits · 2. Before the objective: which quotes enter at all · 3. Units: the residual as a change of coordinates · 4. Measure: weights as a quadrature rule · 5. Tolerance: the band, the tube, and the anchor · 6. What the tolerance is worth: the contest with the regularizer · 7. The honest metric, and the dial that connects the modes · 8. What is genuinely original here · 9. Limitations · Appendix A. Hyperparameter atlas · Appendix B. Traceability · Appendix C. Reference implementation · References

---

## 1. Three decisions before any model fits

Strip any of this series' calibrations to its skeleton and the same object appears: a vector of per-quote residuals, squared, weighted, summed, and handed — together with each model's own penalty blocks — to a least-squares engine. The master data term, shared verbatim by every model, is

**Central equation.**

$$
\sum_i \lambda_i\Big[\big(m_i-\mathrm{hi}_i\big)_+^2
+\big(\mathrm{lo}_i-m_i\big)_+^2
+\theta_{\mathrm{mid}}\,\big(m_i-\mathrm{mid}_i\big)^2\Big],
\tag{1}
$$

with $m_i$ the model's value at quote $i$ *in the residual units*, $[\mathrm{lo}_i,\mathrm{hi}_i]$ a per-quote tolerance band (which may collapse to the mid), $\lambda_i$ the observation weights and $\theta_{\mathrm{mid}}$ a small anchor. Everything in equation (1) that is not the model is one of three choices, and each is a piece of applied mathematics worth a section:

- **Units** (§3 "Units: the residual as a change of coordinates"): in what coordinates is $m_i$ measured? A least-squares loss is a Gaussian likelihood in whatever units its residuals live in; choosing the units *is* choosing the noise model.
- **Measure** (§4 "Measure: weights as a quadrature rule"): the sum over quotes is a quadrature of a continuum misfit functional; the weights decide which measure on the strike axis that quadrature approximates — and the exchange's listing schedule is the wrong default.
- **Tolerance** (§5 "Tolerance: the band, the tube, and the anchor"): a quote is an interval, not a number; the hinge terms make the interval a zero-cost tube, and the anchor decides which member of the tube's flat valley of minimizers is returned.

The remaining sections measure what the tolerance is worth in a real contest with a regularizer ("What the tolerance is worth: the contest with the regularizer") and insist that the reported error mirror the objective actually minimized ("The honest metric, and the dial that connects the modes"). The models' own penalty blocks — calendar floors, wing slopes, butterfly hinges, priors — stack into the same least-squares vector but are documented where they belong (Notes 03, 09, 10 and 13); this note owns only the shared machinery.

> **Invariant.**
> 1. One objective vocabulary for every model: same residual units, same weight schemes, same band construction — a mode or scheme change means the same thing on LQD, SVI, MCS and LV.
> 2. Weights are mean-normalized to one, so switching schemes never silently re-tunes the data-versus-regularization balance.
> 3. Inside the quoted band the fit pays only the small mid anchor — the band never pushes, it only stops punishing.
> 4. The reported RMS is the distance to the objective that was actually minimized, under the weights that were actually used.
> 5. No quote is dropped silently: every screen names its reason, and naming a drop never changes it — the kept and dropped sets are byte-identical to the pre-quarantine pipeline ("Before the objective: which quotes enter at all").

**Conventions and the notation ledger.** $k$ is log-moneyness, $T$ the year fraction, $w=\sigma^2T$ total implied variance, $B(k,w)$ the normalized Black call and $\partial_\sigma B=\varphi(d_+)\sqrt T$ its vega. Per quote $i$: model value $m_i$, quoted $\mathrm{mid}_i$ and band $[\mathrm{lo}_i,\mathrm{hi}_i]$, weight $\lambda_i$, time value $\mathrm{TV}_i$ (the OTM option's normalized price), Voronoi cell width $s_i$ in log-strike with mean $\bar s$. $\theta_{\mathrm{mid}}$ is the mid-anchor weight, $h$ the haircut in vol points, $\eta$ the vega floor, $\varepsilon$ a numerical floor, $\mu$ a measure on the strike axis. One vol bp is $10^{-4}$ of absolute volatility. Subscripted $\partial$ for partials; no primes.

| Symbol | Meaning |
|---|---|
| $k,\ T,\ w$ | log-moneyness, expiry, total variance |
| $m_i,\ \mathrm{mid}_i,\ [\mathrm{lo}_i,\mathrm{hi}_i]$ | model value; quote; band |
| $B,\ \partial_\sigma B,\ \eta$ | Black call, vega, vega floor |
| $\lambda_i,\ \mathrm{TV}_i,\ s_i,\ \bar s$ | weights; time value; cell widths |
| $\theta_{\mathrm{mid}},\ h$ | mid anchor; haircut (vol pts) |
| $\mu,\ \varepsilon$ | strike-axis measure; floor |
| $d_\pm$ | Black arguments |
| $(x)_+$ | $\max(x,0)$ |

*Table 1 — Every symbol in the note. Weights are $\lambda_i$, never $\omega$ — total variance $w$ keeps sole claim to a $w$-like glyph.*

## 2. Before the objective: which quotes enter at all

The three decisions this lecture studies — units, measure, tolerance — all presuppose a sample. There is a fourth decision, taken earlier and easy to leave undocumented: which quotes the objective is allowed to see. The screens' *mechanics* belong to the data layer (Note 05 owns the tick floor and the de-Americanization hygiene); what belongs to this note is the *contract* that none of them acts silently. Every dropped quote carries a machine-readable reason, one of seven: `missing_or_crossed` (no two-sided market), `tick_floor` (an OTM bid worth no more than three ticks — ticks, not volatility, because that is the unit in which the information dies), `nonpositive_bid` (an unclearable lower bound), `below_intrinsic` (a side at or below intrinsic value — near-zero time value, no stable implied volatility exists), `price_bound` (a side at or above the upper static bound), `iv_unresolvable` (inside the bounds but the inversion fails), and `wing` (beyond the standardized-moneyness filter). The counts are surfaced per slice as *advisories*, never a readiness gate: a thin board is a fact to display, not a failure to manufacture.

One constant in that list is a design statement worth a paragraph. The intrinsic classification tolerance is exactly zero (`INTRINSIC_TOL` $=0$): the taxonomy *names* drops the pipeline was already making, and naming a drop must not change it — the kept and dropped sets are byte-identical to the pre-taxonomy pipeline. A diagnostic that alters what it observes has stopped being a diagnostic; holding the tolerance at zero is what keeps the quarantine an observation rather than an intervention. The complementary question — what about quotes that are *kept* but whose residual unit is failing — is answered inside the units discussion of §3 "Units: the residual as a change of coordinates", where it belongs.

## 3. Units: the residual as a change of coordinates

A smile is quoted in volatility but the arbitrage-free object — for the density models, LQD and LV — is the *price*: their parametrizations guarantee a valid density at every iterate precisely because they live in price space (Notes 01 and 04). Prices, however, are terrible residual units: the same volatility error is worth wildly different amounts of price across moneyness. Figure 1, panel A makes the point with one experiment — a *uniform* $50$ vol bp misfit, expressed in price, is an order of magnitude smaller in the wings than at the money. A least-squares loss on raw prices would therefore concentrate all its attention at the money and let the wings drift: not because anyone chose that, but because the units chose it.

> **Heuristic.** A least-squares objective is the maximum-likelihood estimator for independent Gaussian noise *in the units of its residuals*. Fitting raw prices asserts "quote noise is a constant number of dollars at every strike"; fitting vols asserts "a constant number of vol points". The second is far closer to how markets quote and how desks think, so the residual should live in vol units — the question is how to get there without giving up the price-space parametrizations that make arbitrage freedom free.

The resolution is one division. For a quote with total variance $w$ at $k$, the shared residual is

$$
r=\frac{C^{\text{model}}(k)-B(k,w)}
{\partial_\sigma B(k,w)+\eta},
\tag{2}
$$

the model's price error divided by Black vega, floored at $\eta$ in the far wings. The numerator is computed in the model's native, arbitrage-preserving price space — every iterate is a valid density — and the division is a change of coordinates:

**Proposition 1 (The dictionary, with its error term).** *Let the model and market vols at a strike differ by $\Delta\sigma$. Then the residual of equation (2) satisfies*

$$
r=\Delta\sigma\Big(1+\tfrac12\,\frac{d_+d_-}{\sigma}\,\Delta\sigma
+O(\Delta\sigma^2)\Big)\quad(\eta\ \text{negligible}):
\tag{3}
$$

*to first order the vega-normalized price residual* is *the vol residual, uniformly across strikes; the leading correction is the vomma-to-vega ratio $\partial^2_\sigma B/\partial_\sigma B=d_+d_-/\sigma$, largest in the wings where $|d_\pm|$ grow.*

*Proof.* Taylor-expand the numerator in $\sigma$: $C^{\text{model}}-B=\partial_\sigma B\,\Delta\sigma+\tfrac12\partial^2_\sigma B\,\Delta\sigma^2+\dots$, divide by $\partial_\sigma B$, and use the classical $\partial^2_\sigma B=\partial_\sigma B\,d_+d_-/\sigma$. ∎

Figure 1, panel B audits both halves of Proposition 1 on the running smile: at a $50$ bp misfit the normalized residual is flat to 3.0 vol bp across the whole strike range — the dictionary in its domain — while at $300$ bp the vomma term bends it by up to 125 bp in the wings. The dictionary is local, and honestly so: during the early iterations of a cold fit the loss is only *approximately* a vol loss, converging to exactly one as the misfit shrinks. For the vol-space models (SVI, MCS) the residual is natively $\Delta\sigma$ and equation (2) degenerates to exactly that: one residual concept, two implementations, identical units (invariant 1). The floor $\eta$ is the deliberate exception to the dictionary: where vega falls below it — strikes several standard deviations out — the denominator stops shrinking, which caps the vol-amplification of a price error and quietly down-weights quotes whose vol content is numerically vacuous. Production does not stop at down-weighting; it *counts*: per slice, a diagnostic reports how many kept quotes have Black vega below $10^{-3}$ (a separate, coarser threshold than $\eta$). Where the count is material — very short-dated slices — an IV-space residual is numerically meaningless, and the vega-normalized *price* objectives (LQD, LV) are the authoritative view. That is this note's thesis applied to itself: the residual's unit is a claim, and the diagnostic reports where the claim thins out.

> **Figure 1 — The change of units, audited (production Black machinery, running smile) (figure not included in this pack).** A: a *uniform* $50$ vol bp misfit expressed in price units — the bell of vega: a raw-price loss would see the wings at a tenth of their true size. B: the same misfit after vega normalization (equation (2)) reads flat at $50$ bp to 3.0 bp (teal); a $300$ bp misfit (rust, scaled $\div6$ for display) bends away from the dictionary by up to 125 bp in the wings — the vomma term of Proposition 1, the price of using a first-order dictionary far from the optimum. Panel A plots, across strike, the price-unit size of a constant 50 vol bp vol misfit: the curve is the bell shape of vega, tall at the money and an order of magnitude smaller in both wings — the distortion a raw-price loss would silently inherit. Panel B plots the same experiments after vega normalization: the 50 bp misfit reads as a nearly perfect flat line at 50 bp (within 3.0 bp everywhere), while the 300 bp misfit's normalized curve visibly bends away from flat in the wings, by up to 125 bp, tracing exactly the vomma correction the second-order term of equation (3) predicts.

**Exercise 1.** Evaluate the correction in equation (3) at the left edge of Figure 1 ($k=-0.42$, $\sigma\approx28\%$, $T=0.5$, so $d_+d_-/\sigma\approx7$) for $\Delta\sigma=0.03$, and check the order of magnitude against the measured 125 vol bp. Then explain why the same computation at $\Delta\sigma=0.005$ predicts a deviation below $5$ bp — and why an optimizer that starts within a few hundred bp of the truth therefore feels an almost exactly vol-metric loss for its entire descent.

## 4. Measure: weights as a quadrature rule

### 4.1 What a sum over quotes integrates

Idealize the fit as a continuum problem: minimize $\int\big(m(k)-\text{market}(k)\big)^2\,\mathrm{d}\mu(k)$ for some measure $\mu$ on the strike axis. Any finite quote set turns the integral into a sum, and the weights $\lambda_i$ are the quadrature rule. Equal weights make $\mu$ the *empirical measure of the listing* — the exchange's strike schedule, dense at the money, sparse in the wings. That measure was chosen by a listings committee, not by anyone's view of where smile errors matter: a tight ATM cluster of near-duplicate quotes outvotes an isolated wing quote by sheer count, and the fit follows the sampling accident.

The desk's declared measure is different: strike ranges should matter in proportion to the *time value* they carry — $\mathrm{d}\mu=\mathrm{TV}(k)\,\mathrm{d}k$, economic content times length. The production scheme implements precisely the midpoint quadrature of that measure:

$$
\lambda_i\;\propto\;\max(\mathrm{TV}_i,\varepsilon)\;\frac{s_i}{\bar s},
\tag{4}
$$

where $s_i$ is quote $i$'s one-dimensional Voronoi cell width in log-strike — half the gap to each neighbour, one-sided at the ends: the stretch of strike axis this quote alone represents.

**Proposition 2 (The weights are a quadrature).** *For any smooth integrand $f$, $\sum_i \mathrm{TV}_i\,s_i\,f(k_i)$ is the midpoint-type Riemann sum of $\int \mathrm{TV}(k)f(k)\,\mathrm{d}k$ over the Voronoi partition; in particular the weighted loss with equation (4) discretizes the continuum time-value objective, up to the global normalization. On a uniform grid all $s_i$ are equal, $s_i/\bar s=1$, and equation (4) reduces to the pure time-value weighting $\lambda_i\propto\mathrm{TV}_i$ — there is no double-counting left to correct.*

*Proof.* The cells $\{s_i\}$ partition the quoted interval and $k_i$ lies in cell $i$, so the sum is a Riemann sum over that partition; refinement convergence is the standard statement. The uniform-grid case is arithmetic. ∎

Two guard rails keep the quadrature honest on real ladders. The cell width of an isolated far-wing quote is unbounded, so the spacing multiplier $s_i/\bar s$ is capped (at $10\times$): beyond the cap the scheme deliberately *under*-integrates the deep wing rather than let one quote carry a tenth of the objective. And the final weights are mean-normalized to one — a scaling detail with a design consequence: every regularizer in the series (the LQD ridge, the MCS hat ridge, the LV roughness penalty) is tuned against unit-mean data weights, so switching schemes re-*distributes* the data term without re-*scaling* it, and the data-versus-regularization balance survives untouched (invariant 2).

### 4.2 The audit

Figure 2 runs the production weights on a realistic ladder — a dense ATM cluster flanked by sparse wings. Panel A is the per-quote view: the clustered quotes are individually down-weighted, the sparse wing quotes up-weighted (the largest wing weight is $1.3\times$ the ATM one). Panel B is the measure-level audit this edition adds: the *cumulative* weight across the strike axis, compared with the continuum time-value integral it is supposed to discretize. The density-corrected scheme tracks the continuum to a Kolmogorov distance of 0.062; equal weights distort the measure to 0.14 — pushed above the target through the cluster, starved in the wings. A fit is an average against a measure; panel B shows which measure each scheme actually supplies.

> **Figure 2 — Weights as quadrature (production weights, realistic ladder) (figure not included in this pack).** A: per-quote weights — the dense ATM cluster down-weighted, sparse wings up-weighted, wing-to-ATM ratio $1.3$. B: the measure-level audit: cumulative weight against the continuum time-value integral (black). The density-corrected scheme (teal) is a faithful quadrature of the declared measure (Kolmogorov distance 0.062); equal weights (rust) integrate against the listing histogram instead (0.14) — the fit inherits the exchange's strike schedule as an accidental prior. Panel A is a per-strike bar/stem plot of the weights on a ladder with thirteen of twenty-one quotes clustered near the money: under the density-corrected scheme each clustered quote is individually down-weighted while the isolated wing quotes are up-weighted, the largest wing weight reaching 1.3 times the ATM weight. Panel B plots three cumulative-weight curves across the strike axis: the continuum time-value integral in black, the density-corrected scheme in teal hugging it to a Kolmogorov distance of 0.062, and the equal-weight scheme in rust rising too steeply through the ATM cluster and flattening prematurely in the wings, 0.14 away from the target.

**Exercise 2.** On Figure 2's ladder, thirteen of twenty-one quotes sit in $|k|\le0.10$. Compute the fraction of total weight the equal scheme assigns that interval, and compare with the time-value measure's fraction (read both off panel B). Conclude in one sentence why adding *more* ATM listings — which adds information — would make an equal-weighted fit *worse* in the wings, and why that paradox disappears under equation (4).

## 5. Tolerance: the band, the tube, and the anchor

### 5.1 A quote is an interval

A mid pretends a price is known exactly; the market's actual statement is an interval, $[\mathrm{bid},\mathrm{ask}]$, and any curve inside it is consistent with the quote. The band terms of equation (1) encode exactly that: a two-sided squared hinge that vanishes identically inside the band and grows quadratically outside, plus a small anchor. Readers from machine learning will recognize the construction: it is the (squared) $\varepsilon$-insensitive loss of support-vector regression [Vapnik1998], with the tube half-width set per quote by the market itself — the half-spread — rather than by a global hyperparameter. Equivalently, it is the log-likelihood shape of an interval-censored observation: inside the interval, all values are equally credible.

Three modes span the construction. *Mid*: the band collapses, $\mathrm{lo}=\mathrm{hi}=\mathrm{mid}$, and equation (1) reduces to weighted least squares on mids. *Bid–ask*: the raw quoted band. *Haircut*: each side is pulled toward mid by $h$ vol points, never crossing it,

$$
\mathrm{lo}=\min(\mathrm{bid}+h,\mathrm{mid}),\qquad
\mathrm{hi}=\max(\mathrm{mid},\mathrm{ask}-h),
\tag{5}
$$

so a quote tighter than $2h$ collapses gracefully to a mid fit on that strike. One dial therefore spans the whole spectrum: tight ATM spreads behave as mids (the fit follows them exactly where they are informative) while wide wing spreads keep a live tolerance. The hinge is monotone in the quote value, so the same construction works unchanged in any monotone residual space — implied vol for SVI/MCS, vega-normalized price for LQD/LV — and its subgradient is a sign, which is what plugs it into every model's analytic Jacobian. Both maps are one line each in production; the pack carries no source code, so they are stated as exact specifications (Appendix C "Reference implementation" states the verified agreement):

**Specification — the two-sided band hinge and its subgradient** (verbatim semantics of the production `calib/band.py` maps):

- *Band violation:* per quote, $\operatorname{viol}(m;\mathrm{lo},\mathrm{hi})=\max(m-\mathrm{hi},\,0)+\max(\mathrm{lo}-m,\,0)$ — strictly positive only outside $[\mathrm{lo},\mathrm{hi}]$, identically zero inside; since $\mathrm{lo}\le\mathrm{hi}$, at most one of the two terms is nonzero at any $m$.
- *Subgradient sign:* $+1$ where $m>\mathrm{hi}$, $-1$ where $m<\mathrm{lo}$, $0$ inside the band.

Figure 3 draws what one quote contributes under each mode: the mid parabola, the flat-bottomed tube of the hinge alone, and the production band loss whose interior is not perfectly flat but a parabola scaled by $\theta_{\mathrm{mid}}=0.05$ — twenty times gentler than the mid mode's.

> **Figure 3 — One quote's loss under the three constructions (production residuals) (figure not included in this pack).** The mid mode is a full-strength parabola; the hinge alone is a flat zero-cost tube over the quoted band; the shipped band mode adds the $\theta_{\mathrm{mid}}=0.05$ anchor — a parabola twenty times shallower inside the tube, steepening to hinge strength outside. The band never pushes the fit anywhere; it only stops punishing it (invariant 3). The figure plots one quote's loss as a function of the model value: the mid-mode curve is a single full-strength parabola centred on the mid; the hinge-alone curve is exactly zero across the whole quoted band and rises quadratically outside its edges; the shipped band-mode curve follows the hinge outside the band but inside it shows a shallow parabola — the $0.05$-weighted anchor — one-twentieth the curvature of the mid mode's.

### 5.2 The flat valley, and who selects from it

The hinge alone has a defect a lecture should exhibit rather than paper over: its minimizer is not a point.

**Proposition 3 (The tube's null set).** *With $\theta_{\mathrm{mid}}=0$, the set of observation vectors minimizing the band terms of equation (1) is the product of intervals $\prod_i[\mathrm{lo}_i,\mathrm{hi}_i]$: every curve lying inside every quoted band attains the same (zero) data cost. Any strictly positive $\theta_{\mathrm{mid}}$ restores strict convexity in the observation space and selects the unique mid-closest member.*

*Proof.* Inside all bands both hinges vanish, so the data cost is zero on the product set and positive outside it; the anchor term is a strictly convex quadratic, and the sum of a convex function and a strictly convex one is strictly convex. ∎

This is Note 04's equivalence-class situation in miniature: the data (here, deliberately weakened data) does not single out an answer, so the objective must *declare* its representative, and $\theta_{\mathrm{mid}}$ is that declaration — of all curves the market tolerates, return the one nearest the mids. Figure 4 measures the valley on a clean production fit: level-shifting the fitted curve, the hinge-only cost is exactly flat over a 126-vol-bp-wide interval — every shift in it keeps the curve inside every band — while the anchored objective is a clean strictly convex bowl through the same region. An optimizer given the flat version stalls wherever it first enters the tube, and *where* it enters depends on the seed: the anchor is what makes band fits reproducible.

> **Figure 4 — The tube's flat valley, measured (production band residuals on a clean chain; the fitted curve is level-shifted through the bands) (figure not included in this pack).** Hinge alone: a 126 vol bp plateau of exact minimizers — the null set of Proposition 3, where the answer would be seed-dependent. With the $\theta_{\mathrm{mid}}$ anchor: one strictly convex bowl, one declared representative — the mid-closest curve the bands allow. The figure plots total data cost against a level shift applied to the fitted curve: the hinge-only cost traces a perfectly flat floor across a 126 vol bp wide interval of shifts (every curve in that range sits inside every quoted band) before rising on both sides, while the anchored objective drawn through the same region is a single smooth strictly convex bowl with one interior minimum at the mid-closest member.

**Exercise 3.** From equation (1), compute how far beyond a band edge the fit will sit when something else (a regularizer, a neighbouring quote) pulls it outward with the strength of a full mid residual of size $\delta$: balance the hinge gradient against $\theta_{\mathrm{mid}}$ times the anchor gradient and show the concession is $O(\theta_{\mathrm{mid}}\,\delta)$ — a twentieth of what the mid mode would concede. The band is soft, but twenty times harder than the pull toward mid.

## 6. What the tolerance is worth: the contest with the regularizer

It is tempting to summarize the band as "the fit ignores noise inside the spread", and the temptation should be resisted, because it is not what equation (1) says. Inside the tube the data term does not vanish — it survives at weight $\theta_{\mathrm{mid}}$. The precise statement is a re-weighting: *entering the band divides the data term's strength by $1/\theta_{\mathrm{mid}}=20$ in its contest with everything else in the objective*. Whether that relief buys anything depends on who the "everything else" is:

- A *rigid* model is its own regularizer: it cannot chase quote-frequency noise in any mode, so mid and band fits nearly coincide — measured at 6 vol bp apart on the running example (Figure 5, panel A).
- A *flexible* model with a live smoothness penalty is where the tolerance earns its keep: in mid mode the full-weight residuals overrule the regularizer and the fit tracks the tick bounce; in band mode the regularizer wins inside the tube and the curve cuts smoothly through — the two fits separate by 47 vol bp, with the roughness of the mid fit at $0.2$ against the band fit's $0.1$ (Figure 5, panel B).
- A flexible model with *no* counterforce gains nothing: inside the tube the anchor is the only force left, and the anchor points at the mids — the band fit returns to the noise it was meant to ignore. The tolerance does not smooth; it *liberates whatever smooths*.

The band is still fairly called a regularizer that costs no bias — it pushes the fit nowhere it was not already going — but its mechanism is the re-weighting above, and the measured factor-eight gap between the rigid and flexible rows is the honest size of the effect.

> **Figure 5 — The contest, measured (production LQD fits; alternating tick-bounce mids inside a wing-widening band; everything shown as deviation from the true smile) (figure not included in this pack).** A: a rigid model smooths in either mode — mid and band fits are 6 vol bp apart. B: a flexible model with a live ridge: the mid fit (rust) bends toward the bounce, the band fit (teal) lets the ridge win inside the tube — the fits separate by 47 vol bp. The band's value is exactly the counterforce it liberates. Panel A plots the rigid model's mid-mode and band-mode fits as deviations from the true smile: the two curves nearly coincide, at most 6 vol bp apart, because the model's own rigidity already refuses the tick bounce in either mode. Panel B plots the same two modes for a flexible model carrying a live ridge: the mid fit visibly zig-zags toward the alternating tick-bounce mids while the band fit cuts smoothly through the tube, the two separating by 47 vol bp, with the mid fit's roughness measure at 0.2 against the band fit's 0.1.

## 7. The honest metric, and the dial that connects the modes

A reported fit error should measure the objective that was minimized, not a decorative quantity. The production RMS therefore mirrors the active configuration exactly: distance to mid in mid mode; band *violation* in the band modes (a fit sitting contentedly inside the tube reports near-zero error however far it is from the mids); the active weights $\lambda_i$ throughout; returned as the pair $(\sum\lambda r^2,\sum\lambda)$ so per-expiry numbers pool correctly into a surface RMS (invariant 4). The same fitted curve can then legitimately print different numbers under different modes — Figure 6 shows the whole story on one axis by sweeping the haircut $h$ of equation (5). At $h=0$ (raw band) the fit is free inside the tube: band-metric 0.0 vol bp, while its distance to the noisy mids is 84. As $h$ grows the tube tightens strike by strike, the band metric climbs, and at full collapse both metrics agree at 82 bp: the haircut is one dial that sweeps the objective — and its honest metric with it — continuously from band fitting back to mid fitting.

> **Figure 6 — The haircut dial and the honest metric (production fits and production RMS at every point) (figure not included in this pack).** Sweeping $h$ from raw bid–ask to full collapse: the fitted curve barely moves (its distance to mid stays near 84 vol bp throughout) but the *reported* error runs from 0.0 to 82 bp as the metric follows the objective. Two lessons: the dial connects the modes continuously, and an RMS quoted without its mode is not a number. The figure plots two curves against the haircut $h$: the fitted curve's distance to the noisy mids, nearly flat around 84 vol bp across the whole sweep, and the reported band-metric RMS, which starts at 0.0 vol bp at $h=0$ (the fit sits wholly inside the raw bid–ask tube), climbs monotonically as the tube tightens strike by strike, and meets the mid metric at 82 bp when the band has fully collapsed to the mids.

## 8. What is genuinely original here

Vega normalization is standard practice; the contributions are the framings made exact and the two constructions built on them:

1. the *density-corrected time-value weighting* (equation (4)), separating economic importance (time value) from sampling density (the Voronoi widths) — a declared quadrature of a declared measure, audited against its continuum target in Figure 2 — with the mean-one normalization that keeps every model's regularization invariant across schemes;
2. the *space-agnostic squared-hinge band* with its monotone subgradient, making bid–ask fitting a first-class mode of every model's analytic Jacobian rather than a bolt-on — and its anchor understood as the selection rule for the tube's null set (Proposition 3);
3. the *sharpened account of the band's value* as a factor-$1/\theta_{\mathrm{mid}}$ relief in the data-versus-regularization contest, measured on production fits rather than asserted ("What the tolerance is worth: the contest with the regularizer").

Together the weights and the band let the desk say "fit what matters, to within the spread" in two orthogonal dials.

## 9. Limitations

Where the design's guarantees stop. The objective carries *no robust loss*: outside the band the hinge grows quadratically, so a single insane quote retains full quadratic leverage — by design, the defence against outliers lives upstream, in the quarantine of "Before the objective: which quotes enter at all" (screen mechanics in Notes 05 and 06), not in the loss. The Gaussian reading of least squares is a choice, not a fact about markets; so is the time-value measure — a vega-squared measure is equally defensible and one model family carries it internally — and declaring the measure is the point, not deriving it. The quadrature is truncated: the spacing cap deliberately under-weights isolated deep-wing quotes, trading fidelity to the declared measure for robustness to listing accidents. The dictionary of Proposition 1 is first order, and a cold fit starting far from the truth descends a loss that is only approximately vol-metric. And the band's value is contingent ("What the tolerance is worth"): it liberates a counterforce it does not supply, so a flexible model fitted in band mode *without* a live regularizer inherits the mids' noise through the anchor — tolerance is not smoothness.

## Appendix A. Hyperparameter atlas

*Table 2 — Calibration-objective hyperparameters.*

*Surfaced (FitSettings / OptionsSettings)*

| Knob | Default | Role |
|---|---|---|
| `weightScheme` | `equal` | `equal` or `tv_density` (equation (4)). |
| `fitMode` | `mid` | `mid` / `bidask` / `haircut`. |
| `haircut` $h$ | $0.005$ | Haircut in vol points (each band side toward mid), equation (5). |
| `midAnchorWeight` $\theta_{\mathrm{mid}}$ | $0.05$ | Mid anchor strength vs the unit hinge. |

*Hidden*

| Knob | Default | Role |
|---|---|---|
| `DEFAULT_MAX_MULT` | $10$ | Cap on the Voronoi spacing multiplier $s_i/\bar s$ (truncated quadrature). |
| $\varepsilon$ | $10^{-12}$ | Floor on time value / spacing. |
| $\eta$ (vega floor) | $10^{-4}$ | Floor on Black vega in equation (2) — the *residual* floor; distinct from the diagnostic threshold below. |
| `VEGA_FLOOR_DIAG` | $10^{-3}$ | Per-quote vega threshold of the kept-quote incidence count (§3 "Units"); diagnostic only. |
| `TICK_FLOOR_TICKS` | $3$ | OTM bid floor in ticks on real-feed chains — mechanics in Note 05, reason taxonomy here (§2 "Before the objective"). |
| `INTRINSIC_TOL` | $0$ | Intrinsic classification tolerance; zero by design so naming a drop changes no fit (§2 "Before the objective"). |

**Performance.** Weighting is $O(m\log m)$ (one sort); the band residual and its subgradient are $O(m)$ and analytic, adding nothing to Jacobian assembly. Both are negligible against any fit. Switching a scheme or mode bumps the options version and triggers exactly one refit.

## Appendix B. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

*Table 3 — Claims in this note and the code/tests that lock them.*

| Claim | Object | Code anchor / *test anchor* |
|---|---|---|
| Clean chains quarantine nothing (taxonomy is observation, not intervention) | "Before the objective" | `volfit/api/quotes.py` — *`tests/test_quote_screen.py::test_clean_chain_screens_nothing`* |
| Seven-reason taxonomy; tick-floor and crossed reasons named | "Before the objective" | `volfit/api/quotes.py` — *`tests/test_quote_screen.py::test_tick_floor_and_crossed_reasons`* |
| Screen counts surfaced as advisories, never a readiness gate | "Before the objective" | `volfit/api/quality.py` — *`tests/test_quote_screen.py::test_quality_surfaces_screen_counts_advisory`* |
| Vega-floor incidence counts *kept* quotes below $10^{-3}$ | "Units" | `volfit/api/quotes.py` — *`tests/test_quote_screen.py::test_vega_floor_diagnostic_counts_kept_quotes`* |
| Density-corrected weights match the design note's worked example | equation (4) | `volfit/calib/weights.py` — *`tests/test_weights.py::test_doc_worked_example`* |
| Uniform grid reduces to pure time value | Proposition 2 | `volfit/calib/weights.py` — *`tests/test_weights.py::test_uniform_grid_reduces_to_time_value`* |
| Dense cluster down-weighted; mean-one normalization | equation (4) | `volfit/calib/weights.py` — *`tests/test_weights.py::test_dense_region_downweighted`, `::test_resolve_weights_equal_is_none_and_tv_is_mean_one`* |
| The scheme moves every model (shared vocabulary) | invariant 1 | `volfit/calib/weights.py` — *`tests/test_weights.py::test_weight_scheme_moves_every_model`* |
| Band modes; haircut collapses gracefully to mid | equation (5) | `volfit/calib/band.py` — *`tests/test_band_fit.py::test_resolve_band_modes`, `::test_haircut_default_is_half_vol_point`* |
| Zero residual inside the band; edge pull outside | equation (1) | `volfit/calib/band.py` — *`tests/test_band_fit.py::test_band_residuals_zero_inside_band`, `::test_outside_band_mid_is_pulled_to_edge`* |
| Band fit stays in band and smooths (the contest) | "What the tolerance is worth" | `volfit/calib/band.py` — *`tests/test_band_fit.py::test_band_fit_stays_in_band_and_smooths`* |
| RMS mirrors the minimized objective | "The honest metric" | `volfit/calib/rms.py` — *`tests/test_rms.py::test_mid_mode_is_weighted_rms_distance_to_mid`, `::test_band_mode_zero_inside_band_distance_outside`* |
| Band-mode RMS never exceeds mid-mode; surface pooling; weights bias the RMS | "The honest metric" | `volfit/calib/rms.py` — *`tests/test_rms.py::test_band_mode_rms_not_above_mid_mode`, `::test_surface_rms_pools_expiries`, `::test_weights_bias_the_rms`* |

## Appendix C. Reference implementation: the band residual stack

The full data term stacks two blocks per quote: the band violation (scaled by the per-quote weight, or $1/\text{vega}$ in the LQD/LV price space) and the weak mid anchor, so squaring and summing reproduces equation (1). All three maps in this note — the band violation and its subgradient sign (specified in §5.1 "A quote is an interval") and the stacked residual below — were executed against their production counterparts by this edition's generator on every run: agreement to $10^{-16}$ (floating-point identity). (The pack carries no source code; the algorithm specification below carries every step of the original listing.)

**Algorithm C.1 — the stacked band-objective residual.**

*Inputs:* per-quote arrays of length $N$: model values $m$, band edges $\mathrm{lo}$, $\mathrm{hi}$, mids $\mathrm{mid}$, a per-quote scale (the observation weight in the residual space — $1/\text{vega}$ for the LQD/LV price-space objectives), and the scalar mid-anchor weight $\theta_{\mathrm{mid}}$.
*Output:* a least-squares residual vector of length $2N$.

1. *Violation block:* for each quote $i$, the row $\text{scale}_i\cdot\big(\max(m_i-\mathrm{hi}_i,0)+\max(\mathrm{lo}_i-m_i,0)\big)$ — the push toward the inside of the bid/ask band, zero when already inside.
2. *Anchor block:* for each quote $i$, the row $\sqrt{\theta_{\mathrm{mid}}}\cdot\text{scale}_i\cdot(m_i-\mathrm{mid}_i)$ — the weak pull to mid.
3. Concatenate the two blocks, violation rows first, into one vector of length $2N$; its squared Euclidean norm under the observation weights reproduces equation (1) exactly.

*Stated agreement:* $10^{-16}$ (floating-point identity) against the production stack.

## References

- [tvweights] Vol-Fitter Technical Note, *Density-corrected time-value weights* (`Docs/iv_time_value_density_weights.tex`).
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.
- [Vapnik1998] V. Vapnik. *Statistical Learning Theory*. Wiley, 1998. (The $\varepsilon$-insensitive loss.)
- [Huber1981] P. Huber. *Robust Statistics*. Wiley, 1981.

