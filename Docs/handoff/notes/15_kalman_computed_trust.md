# Trust Is Computed

**Note 15 — observation filter (Kalman/MAP) · lecture edition ("trust is computed") · converted from 15_kalman_computed_trust.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

*The observation filter as two honest covariances: a gain that is an output, and an audit in standardized residuals. Vol-Fitter Technical Notes, No. 15.*

> **Abstract.** Every fitter that carries state through time owns a dial marked *trust*: how far should this morning's noisy quotes move yesterday's surface? This lecture develops the Vol-Fitter's observation filter from one design decision — *the desk never touches that dial*. The gain that moves a smile handle toward the market is the ratio of two covariances, each built honestly from first principles: a measurement covariance propagated from the fit's own information in *stated* noise units (bid–ask half-spreads — double the stated noise, quadruple the covariance, measured slope 0.97), inflated by realized inconsistency (a two-strike contradiction drives the inflation to its cap of 25 and turns the curvature gain from 0.73 down to 0.20 with nobody touching anything); and a prediction covariance grown by a process clock that must itself be honest — on stored thirty-minute data a weekend moves the ATM no more than one overnight (37 vs 52 bp), so no calendar clock calibrates all cadences and the shipped session clock does. The acceptance test is never smoothness: it is whether the standardized residuals $\zeta$ have unit scale — error bars that mean what they say. By that audit a 38,181-step temporal backtest flipped the clock noise default ($10\to30$ bp$/\sqrt{\text{day}}$: $\zeta$ std $5.16\,\to\,1.75$ in the spike regime), chose the Jacobian covariance route ($2$–$3\times$ better contradiction rejection), and convicted the full-covariance update (off-diagonal gains dragged the ATM through junk curvature by 3–28 vol points on coarse chains; production updates per handle). A second 39,190-step sweep scored the active one-stage MAP — the same accounting done inside the objective — as the best denoiser wherever denoising is the job, and its shock lag as the cost of a prior priced before the measurement exists; the shipped answer (a fit-free ATM probe plus one-step-lagged gating) closes that gap by construction and awaits its full-regime validation.

## 1. The dial nobody may own

Two mornings, two failures. On the first, a dense at-the-money cluster contains one stale strike: chase the mids literally and the fit grows a curvature kink that no one traded. On the second, the whole chain genuinely reprices overnight: hold on to yesterday and the book carries a stale surface into a moved market. A fitter that persists state must steer between these, and the tempting instrument is a slider — "how much do we trust this morning?" — tuned by hand, per desk, per mood.

The Vol-Fitter refuses the slider. In one dimension the whole machinery of this note is the identity

$$
m^{+}=\frac{r}{p+r}\,m^{-}+\frac{p}{p+r}\,z ,
$$

the posterior as a precision-weighted average of the predicted handle $m^-$ (variance $p$) and the observed handle $z$ (variance $r$). The weight $K=p/(p+r)$ — the Kalman gain — is not a setting. It is an *output*, computed from two uncertainty budgets, and every design decision in the feature is about making those two budgets tell the truth: $r$ must reflect what the quotes actually pin down, in the market's own noise units; $p$ must reflect how much the smile can genuinely have diffused, on the clock the market actually runs on. When both are honest, the dial turns itself: the stale-strike kink arrives with a large $r$ and is barely admitted; the genuine reprice arrives with a large innovation, widens $p$ through a gated surprise term, and is followed.

> **Heuristic.** This note and Note 13 divide the world by *sufficient statistic*. Prior persistence asks "where did the market not speak?" and acts through a gap gate that is exactly zero where quotes identify a feature. The filter asks "the market spoke here — how noisy was its voice?" and acts through a covariance that is never zero and never infinite. A sparse wing is a gap: persistence fills it. A dense-but-contradictory cluster is a noisy observation: the filter shrinks it. Confusing the two is the classic failure this pair of notes exists to prevent.

> **Invariants protected in this note.**
> 1. Trust enters the update only through an explicit prediction covariance and an explicit measurement covariance — never through a hand-set weight on either side.
> 2. The same quote is never counted twice: once a posterior exists, it may not be re-anchored against the quotes that built it (Proposition 2).
> 3. The filter state is an arbitrage-safe coordinate — the exact ATM handles of Note 01 — never a free raw-IV curve and never native local-vol parameters.
> 4. Mode `off` is byte-identical to the feature never existing, and every filter call on the fit path is advisory: a filter failure cannot break a calibration.
> 5. Every filtered output reports prediction, observation, innovation, gain and posterior uncertainty — the full audit, per handle, per step.
> 6. Prior persistence continues to act only on functionals the current market does not identify; the filter never touches them.

**Conventions and the notation ledger.** One time symbol, $\tau$, the node's variance time; $\Delta t$ is the elapsed process-noise time between snapshots (whose *clock* is the subject of "The clock the variance actually runs on") and $h=\log(F_t/F_{t-1})$ the log-forward move. Subscripted $\partial$ for the rare partial derivative; primes are never used.

**Table 1 — Every symbol in the note.** $\mathcal H$ extracts handles from a model, $\mathcal L$ names a loss; nothing is reused with a second meaning.

| Symbol | Meaning |
|---|---|
| $x=(\sigma_{\mathrm{ATM}},s,\kappa)^\top$ | the handle state |
| $m^{\mp},\,P^{\mp}$ | prediction / posterior law |
| $z,\ R$ | handle observation and its covariance |
| $K,\ S,\ \nu$ | gain; innovation covariance; innovation |
| $Q,\ q$ | process covariance; its ATM clock scale |
| $J,\ G,\ \mathcal I_\theta$ | solver / handle Jacobians; information |
| $\rho,\ \chi^2$ | residual inflation; quote misfit |
| $s_q$ | stated per-quote noise std (vol units) |
| $\zeta$ | standardized residual |
| $\Delta t,\ h,\ \tau$ | elapsed time; forward move; variance time |

The state deserves its sentence. $x_t$ is the compact handle vector (ATM vol, ATM skew, ATM curvature) — the same three coordinates the graph extrapolator of Note 14 propagates, read exactly off the LQD backbone (Note 01), so the filtered object is arbitrage-safe by construction and model-agnostic by carrier (signed operators such as RR25/BF25 are a dimension-agnostic extension left for after the pilot). Raw option mids are a poor state space — contracts appear and disappear, the OTM side flips with the forward, American quotes need de-Americanization, and a smoothed raw-IV vector is not guaranteed butterfly-free — so the filter begins *after* the quote-prep pipeline, and its measurement is a fit, not a quote vector ("The observation budget: what did the market actually say?").

## 2. The update that survives any gain

**Definition 1 (Predicted and observed handle laws).** At snapshot $t$, with $\mathcal F_{t-1}$ the filtration of previous snapshots,

$$
x_t\mid\mathcal F_{t-1}\sim\mathcal N(m_t^-,P_t^-),
\qquad
z_t\mid x_t\sim\mathcal N(H_t x_t,R_t),
$$

where $m_t^-$ is the transported previous filtered state ("The prediction budget: how far can the smile have walked?"), $z_t$ and $R_t$ are extracted from today's prepared quotes without any temporal prior ("The observation budget"), and $H_t$ is the measurement operator ($I$ for a direct handle observation; the equations allow a subset or a linear functional).

The update is the covariance-form Kalman step in Joseph form.

**Central equation.**

$$
\begin{aligned}
S_t&=H_tP_t^-H_t^\top+R_t,\\
K_t&=P_t^-H_t^\top S_t^{-1},\\
m_t^+&=m_t^-+K_t\big(z_t-H_tm_t^-\big),\\
P_t^+&=(I-K_tH_t)P_t^-(I-K_tH_t)^\top+K_tR_tK_t^\top .
\end{aligned}
\tag{1}
$$

The last line is longer than the textbook $P^+=(I-KH)P^-$, and the extra length is the point: the Joseph form is a *sum of two sandwiches*, symmetric and positive semidefinite for *any* gain matrix, optimal or not. That algebraic fact is a design asset. It makes the pilot's own-gain cap safe (a capped $K$ is a valid, merely suboptimal, linear gain whose posterior covariance is still a covariance), and it makes the diagonalized update of "When trust is a matrix" safe for the same reason. The production body is small enough to state whole:

> **Algorithm — the production update (from `calib/observation_filter.py`): equation (1) with the own-gain pilot cap, Joseph covariance, and an explicit PSD guard. Verified against the reference specification of Appendix D to $1.0\times10^{-17}$.** (Replaces the note's quoted code listing; the pack carries no source code.) Inputs: predicted mean $m$ and covariance $P$, observation $z$ and covariance $R$, measurement operator $H$, own-gain cap `max_gain`.
> 1. Innovation $\nu = z - Hm$; innovation covariance $S = HPH^\top + R$.
> 2. Gain $K = PH^\top S^{-1}$, computed by solving the linear system $KS = PH^\top$ (transpose-solve form) — never through an explicit matrix inverse.
> 3. Pilot cap (only when `max_gain` $<1$): form the own-gains $|\operatorname{diag}(KH)|$ and scale each row $i$ of $K$ by $\min\big(1,\ \text{max\_gain}/\max(|\operatorname{diag}(KH)_i|,10^{-300})\big)$ — the cap scales *own*-gains only.
> 4. Posterior mean $m^+ = m + K\nu$.
> 5. Joseph posterior covariance with $A=I-KH$: $P^+ = APA^\top + KRK^\top$ — PSD for *any* gain; then symmetrize, $P^+\leftarrow\tfrac12(P^++P^{+\top})$.
> 6. PSD guard: if any eigenvalue of $P^+$ is below $-10^{-12}$, raise a floating-point error ("posterior covariance lost PSD") rather than continue.

**Proposition 1 (Precision-weighted shrinkage).** In one dimension with $H=1$, prediction variance $p$ and measurement variance $r$,

$$
m^+=\frac{r}{p+r}\,m^-+\frac{p}{p+r}\,z,
\qquad K=\frac{p}{p+r}\in(0,1),
$$

so the posterior always lies strictly between prediction and observation, and moves toward whichever carries the smaller stated variance.

*Proof.* $S=p+r$ and $K=p/S$; substitute into $m^+=m^-+K(z-m^-)$. Positivity of $p$ and $r$ places $K$ in $(0,1)$. ∎

Figure 1 runs the note's canonical vignette through the production update. The transported prediction says $(20.0\%,-0.35,0.10)$ with standard deviations $(0.30\%,0.08,0.05)$; today's data-only fit reads $(20.4\%,-0.37,0.55)$ — a plausible level move, a plausible skew, and a curvature kink manufactured by one stale close strike. The measurement builder of "The observation budget" prices that chain at $\sqrt{\operatorname{diag} R}=(0.15\%,0.05,0.30)$: level and skew tight, curvature wide because the cluster contradicts itself. The computed gains follow: $K_\sigma=0.80$, $K_s=0.72$, $K_\kappa=0.027$. The posterior tracks the market's level to $20.32\%$ and accepts $2.7\%$ of the kink ($m^+_\kappa=0.112$) — not vetoed, priced. No gap logic fired: by quote count this region is superbly observed, which is exactly why Note 13's gate must stay closed and the covariance must do the work.

> **Figure 1 — The case file through the production update (figure not included in this pack).** The case file through the production update. A: the computed per-handle gains — level and skew admitted at 0.80 and 0.72, the contradiction-inflated curvature at 0.027. B: each posterior lands on the prediction$\to$observation segment exactly at its gain: in the normalized coordinate the position *is* the gain, so the reader can check Proposition 1 by eye. *Description:* Panel A is a bar chart of the three computed Kalman gains for the vignette — ATM level 0.80, skew 0.72, curvature 0.027 — showing at a glance that the level and skew moves are largely admitted while the stale-strike curvature kink is almost entirely rejected by its inflated measurement covariance. Panel B draws, for each handle, the segment from prediction to observation in a normalized coordinate and marks where the posterior lands: level at 20.32% (80% of the way to the market's 20.4%), skew 72% along its segment, and curvature only 2.7% along — accepting $m^+_\kappa=0.112$ of a kink stated at 0.55 — so the plotted position of each posterior literally equals its gain.

**Exercise 1.** Show that the Joseph form in equation (1) equals $P^- - K S K^\top$ at the optimal gain, but remains PSD for any $K$ (write it as $A P^- A^\top + K R K^\top$ with $A=I-KH$). Then show the textbook form $(I-KH)P^-$ loses symmetry — and can lose positivity — the moment $K$ is perturbed, e.g. by the own-gain cap of the production-update algorithm above. The cap is safe *because* production pays for the longer formula.

## 3. The observation budget: what did the market actually say?

The Kalman algebra is a page; the work is the covariance. $R_t$ must answer, in vol units, "how precisely do today's quotes pin each handle?" — and it must answer honestly on chains that are sparse, wide, stale, or self-contradictory. Production builds it in four moves.

### 3.1 A fit is the observation

The extractor is a two-step map,

$$
z_t=\mathcal H\Big(\arg\min_\theta\
\mathcal L_{\mathrm{quote}}(\theta;q_t)+\mathcal L_{\mathrm{intrinsic}}(\theta)\Big),
\tag{2}
$$

where $\mathcal L_{\mathrm{quote}}$ is the vega-normalized, bid–ask-aware loss of Note 07, $\mathcal L_{\mathrm{intrinsic}}$ contains only the model regularization needed for a valid no-arbitrage smile (never temporal persistence), and $\mathcal H$ reads the exact ATM handles off the fitted slice. The carrier is the LQD backbone — always fitted, model-agnostic, closed-form handles — so $z_t$ costs nothing extra. When the committed fit did receive persistence targets (hybrid mode with an active prior), the measurement is flagged `contaminated` rather than silently trusted; Note 13's gate keeps the overlap near zero exactly where the filter has signal, and the opt-in `filterDataOnlyPrepass` buys a strictly clean $z_t$ for one extra data-only fit per node.

### 3.2 Information, in stated noise

Near the optimum, linearize the residual stack $r(\theta)\approx r(\hat\theta)+J(\theta-\hat\theta)$; with the handle map $x=g(\theta)$ and its Jacobian $G$, the delta method gives the default (Jacobian) route:

$$
\mathcal I_\theta=J^\top WJ+\Lambda_{\mathrm{intrinsic}},
\qquad
R_x\approx G\,\mathcal I_\theta^{+}\,G^\top .
\tag{3}
$$

Every calibrator retains its solution Jacobian in a diagnostics side-channel with the square-root weights and inverse-vega scaling already folded in, so $J^\top J$ *is* the observed information in vol units and the intrinsic rows (ridge, calendar, barrier) supply $\Lambda_{\mathrm{intrinsic}}$ automatically; $G$ is a central finite difference of the handle map — slice *builds*, not fits, on the coarse optimization grid.

> **Caution.** Information is only information *in stated noise*. The production quote weights are relative (equal or time-value density, Note 07), not $1/\text{noise}^2$; read at face value, $J^\top WJ$ is the information under an implied noise of one full volatility point per quote — so small that $R_x$ saturates every sanity envelope and the filter freezes. The shipped builder fixes the units at the source: the data rows of $J$ and $r$ are divided by the stated per-quote noise standard deviation $s_q$ — the bid–ask half-spread floored at one vol bp, or the haircut — *before* the information and $\chi^2$ are formed, while the intrinsic rows keep their own scale (they are a prior, not a measurement). $R_t$ then obeys the quadratic contract the algebra assumes, and Figure 2, panel A, measures it: log-slope 0.97 of $\sqrt{R_{\sigma\sigma}}$ in $s_q$ — double the stated noise, quadruple the covariance. The same $s_q$ reappears twice in active mode ("Fitting under computed trust: the active MAP"): in the MAP prior weights and in the posterior unwhitening — one consistent value in both places, or the MAP algebra silently breaks.

The pseudo-inverse in equation (3) is deliberately a *regularized* eigen-inverse: eigenvalues of $\mathcal I_\theta$ below $10^{-10}\lambda_{\max}$ are clamped *up* to the cutoff, so a $\theta$-direction the quotes do not identify contributes a large-but-finite handle variance. The sign of this failure mode is the whole point. A strict pseudo-inverse zeroes small eigenvalues — and thereby reports an *unidentified* direction as *zero* uncertainty, the one lie a filter must never inherit from its measurement. On production chains the intrinsic rows usually keep $\mathcal I_\theta$ numerically full-rank (Figure 2, panel B: zero clamped directions even at five quotes, while $\sqrt{R_{\kappa\kappa}}$ grows threefold); strip them and the clamp fires (2 directions on the five-quote chain) — the last fence, behind the fence that usually holds.

> **Figure 2 — The two unit disciplines of the observation budget (figure not included in this pack).** The two unit disciplines of the observation budget (production builder throughout). A: the quadratic contract — the ATM measurement std against the stated per-quote noise has log-slope 0.97; covariance is stated noise squared, propagated, not a house opinion. B: thinning the chain from 21 quotes to 5 triples the curvature uncertainty *finitely*: the intrinsic rows keep the information full-rank (zero clamped directions), and the eigen-clamp stands behind them for the day they do not. *Description:* Panel A plots, on log–log axes, the ATM measurement standard deviation $\sqrt{R_{\sigma\sigma}}$ produced by the production builder against the stated per-quote noise $s_q$; the points lie on a straight line of measured slope 0.97 — essentially the exact quadratic contract, doubling the stated noise quadruples the covariance. Panel B sweeps the chain from 21 quotes down to 5 and tracks the curvature measurement std alongside the count of eigen-clamped information directions: the std grows roughly threefold but stays finite, and the clamp count stays at zero because the intrinsic rows keep $\mathcal I_\theta$ full-rank; a companion bar shows that with the intrinsic rows stripped the clamp fires on 2 directions of the five-quote chain — the last fence engaging.

### 3.3 Contradiction is noise: the $\chi^2$ inflation

The covariance so far measures *geometry* — which directions the quote locations identify. It does not yet know whether the quotes agree with each other. That enters through realized inconsistency:

$$
R_t=\rho_t\,R_x,\qquad
\rho_t=\operatorname{clip}\!\left(\frac{\chi_t^2}{\max(m-d,1)},\,1,\,25\right),
\qquad
\chi_t^2=r(\hat\theta)^\top W r(\hat\theta)\ \text{(quote rows only)},
\tag{4}
$$

with $m$ the quote count, $d$ the handle count, and the cap preventing one broken chain from poisoning the state. A dense cluster that cannot be fitted within its stated noise is not well-observed — it is loud and wrong, and $\rho_t$ says so.

Figure 3 is the mechanism figure of the note. A clean 21-quote chain is progressively contradicted: two adjacent strikes are kinked in opposite directions by up to three vol points (the temporal backtest's `contradiction` scenario). The production pipeline responds exactly as designed: $\chi^2$ grows, $\rho$ climbs from $1$ to its cap of 25, the stated curvature noise triples to the sanity envelope, and the computed curvature gain falls from 0.73 to 0.20 while the ATM gain — whose direction the kink barely pollutes — stays at 0.74. No threshold, no veto, no knob: the misfit turned the dial.

> **Figure 3 — A contradiction prices itself (figure not included in this pack).** A contradiction prices itself (production fit, measurement builder and update; two adjacent strikes kinked $\pm\varepsilon$). A: the realized-misfit inflation $\rho$ climbs to its cap of 25 and the stated curvature noise rises to the envelope. B: the computed gains respond — curvature from 0.73 to 0.20, the better-identified level and skew far less. The flat tails are the caps: beyond them the chain is already maximally distrusted. *Description:* Panel A sweeps the kink amplitude $\varepsilon$ applied in opposite directions to two adjacent strikes of a clean 21-quote chain and plots the resulting inflation factor $\rho$ and the stated curvature noise: $\rho$ rises from 1 to its cap of 25 as the contradiction grows, and the curvature noise roughly triples until it meets the sanity envelope, after which the curves flatten — the chain is maximally distrusted. Panel B plots the computed per-handle gains over the same sweep: the curvature gain falls from 0.73 on the clean chain to 0.20 at the kink, while the ATM gain barely moves (staying at 0.74) because the kink hardly pollutes its direction; no threshold or veto appears anywhere — the misfit itself turned the dial.

> **Remark (Bid–ask bands come for free).** In band mode, quotes inside the spread should not pretend to identify the mid. On the Jacobian route no special-casing is needed: inactive hinge rows differentiate to zero inside the spread, so in-band quotes contribute nothing to $J^\top WJ$ and only the weak mid anchor remains. This matches Note 07's semantics — inside the spread the market is a set, not a point — and is a concrete advantage over the factor route, which must proxy band width through a scalar spread factor.

### 3.4 The fallback route, and the short-dated floor

When no solution Jacobian was retained (cached fits), a cheaper builder reuses the graph layer's precision vocabulary,

$$
R_t^{-1}
=\operatorname{diag}(c_h)\,\pi_{\mathrm{fit}}\,
f_{\mathrm{density}}\,f_{\mathrm{spread}}\,f_{\mathrm{fresh}},
\tag{5}
$$

with per-handle confidences $c_h$, inverse squared fit RMS (floored and capped), and the shared scalar factors of Note 13. The realized misfit already lives in the RMS factor, so no separate $\rho$ is applied — it would double-count. This route also survives as the sweep's A/B column, which is how the Jacobian route's advantage got *measured* rather than assumed ("The audit: were the error bars true?").

One more honesty term, measured before it was priced: below $30$ days to expiry the thinned-vs-full ATM discrepancy runs $2$–$3\times$ the stated half-spread (short-end quote and de-Americanization noise — the Note 04/05 diagnosis, not a filter defect). The stated noise is therefore scaled by $\sqrt{30/\mathrm{DTE}}$ below $30$ DTE (never below one), applied consistently to $R_t$, the active MAP weights and the posterior unwhitening.

> **Case file — close-strike contradiction versus true gap.**
>
> **Setup.** A one-month smile: nine near-ATM quotes, nothing reliable beyond $25\Delta$, one stale close strike forcing a large curvature if mids are chased — the market of Figure 1.
>
> **Diagnosis.** Quote density says the ATM region is superbly observed, so Note 13's activation gate is closed there — using persistence to pull the curvature back would damp with yesterday what should be judged by today. The contradiction instead surfaces as measurement noise through equation (4), and the computed gains split the day correctly: level 0.80, skew 0.72, curvature 0.027.
>
> **Persistence.** The unquoted wing is the opposite case: observation precision below requirement, gate open, transported prior holding the tail. The same morning legitimately carries both mechanisms, each on its own sufficient statistic.
>
> **The other half.** A rejected kink must not become a rejected *move*: when the whole chain genuinely reprices, the innovation is coherent across handles, the surprise gate of "Surprise must widen the budget: the adaptive gate" widens $P^-$, and the filter follows the market. *A dense cluster with a bad internal residual is a high-$R$ observation; a strike range with no reliable quotes is a gap. The first belongs to the filter, the second to persistence.*

## 4. The prediction budget: how far can the smile have walked?

The other covariance is the prediction's. The previous filtered state is transported to today — mean by the spot-vol rules of Note 12, uncertainty by a process budget:

$$
m_t^-=\mathcal T_t(m_{t-1}^+),
\qquad
P_t^-=P_{t-1}^++Q_t,
\qquad
Q_t=Q_{\mathrm{clock}}+Q_{\mathrm{spot}}+Q_{\mathrm{event}}+Q_{\mathrm{source}}+Q_{\mathrm{model}} .
\tag{6}
$$

The mean transport is the first-order handle map of the SSR transport (Note 12): for a log-forward move $h$,

$$
\sigma_{\mathrm{ATM}}\mapsto\sigma_{\mathrm{ATM}}+\mathrm{SSR}\cdot s\,h,
\qquad
s\mapsto s+\kappa\,h,
\qquad
\kappa\mapsto\kappa,
\tag{7}
$$

with the transport Jacobian deferred ($A_t=I$; a full curve transport is not available for a bare handle vector, and seeding uses the exact curve transport through the prior machinery instead) — the uncertainty growth is carried entirely by $Q$. Its terms: a clock term $q^2\,\Delta t$ per handle (the headline knob, in vol bp per $\sqrt{\text{day}}$); a spot-transport term with std proportional to $|h|$ in each handle's typical move scale (the same intuition as persistence's transport-distance factor); and event, source and model widenings supplied by the app layer when the prediction crosses an event window, a provider or as-of switch, or a display-model change.

> **Caution.** Do not filter native local-vol parameters. The local-vol grid (Note 04) is a projection machinery with its own PDE stability and no-arbitrage constraints; filter the target smile handles, then project or refit the surface to the filtered target.

### 4.1 The clock the variance actually runs on

$Q_{\mathrm{clock}}=q^2\Delta t$ looks innocent until one asks what $\Delta t$ *is*. The design note ran on calendar days; Note 11 already warned that the market keeps its own clock, and the stored thirty-minute campaign (three tickers, eight days spanning the July-4th closure) measures the failure directly. On those tables the median absolute ATM move is 14 bp per thirty-minute session step, 52 bp across one overnight — and 37 bp across the entire three-day holiday closure. (Provenance note: these are this note's per-pair medians over the stored per-day tables; the campaign's coarser headline aggregation, quoted in Note 11, reads roughly $19.5/55/55$ — different pooling, same ordering, same lesson.) *A closed market adds nothing an overnight does not already contain.* A calendar clock must therefore be wrong at some cadence: whatever $q$ it picks, it pays three-plus days of variance across a closure that delivers one overnight's worth. The audit shows exactly that (Figure 4, panel B): the best calendar configuration ($q=120$ bp) is calibrated intraday ($\zeta$ std 1.04) but overdispersed into closures ($\zeta$ std 0.53 overnight, 0.23 across the weekend — error bars three and four times too wide). The shipped session clock — $60\%$ of a day's variance in the exchange session, closed days at weight zero; these are the *filter's* own share and weight, and Note 11's maturity clock deliberately carries different defaults tuned for a nesting property — calibrates all three cadences at once ($\zeta$ std 0.95/0.89/0.84 at $q=90$ bp). The default remains `calendar` (byte-identical to the pre-clock filter; the session clock is the sub-day workflow's setting), and the *reset* rule deliberately stays on calendar hours: staleness is about data age, not variance accrual.

> **Figure 4 — The prediction budget runs on the market's clock (figure not included in this pack).** The prediction budget runs on the market's clock (production intraday variance clock; stored 0DTE campaign artifacts). A: accrued variance-days across the July-4th week — the calendar clock pays through the three-day closure; the session clock (share $0.60$, closed days $0$) stops, because measured smiles do too. B: the consequence in the audit currency: no calendar $q$ is calibrated at every cadence — the best one is right intraday and $3$–$4\times$ overdispersed into closures — while the session clock at $q=90$ bp holds $\zeta$ std near $1$ across all three. *Description:* Panel A plots accrued variance-days against wall-clock time across the July-4th week for the two clocks: the calendar clock's line climbs steadily through the three-day market closure, while the session clock's line rises only inside exchange sessions (at share 0.60 of a day per session) and is flat across closed days — matching the measured smile moves, where a weekend (37 bp) contributes no more than one overnight (52 bp). Panel B shows the standardized-residual std at the three cadences (intraday, overnight, weekend) for the best calendar configuration at $q=120$ bp — 1.04, 0.53, 0.23, calibrated intraday but with closure error bars three to four times too wide — versus the session clock at $q=90$ bp, which holds $\zeta$ std at 0.95/0.89/0.84, near 1 across all three cadences at once.

### 4.2 Surprise must widen the budget: the adaptive gate

A fixed clock cannot span calm and spike regimes: a genuine five-point overnight jump is ${\sim}50\sigma$ under a $30$ bp$/\sqrt{\text{day}}$ prior, and a filter that believes its budget lags it. The shipped answer is an innovation-gated widening: per handle, when the standardized innovation $|\nu|/\sqrt{P^-+R}$ exceeds the gate (default $3$), $P^-$ is inflated by $(\zeta/3)^2$, capped, so the surprise reads as ${\sim}3\sigma$ and the gain rises toward the data. Two properties make it safe. Clean days never trip it — below the gate the update is byte-identical. And a *contradictory* chain does not trip it either: its $\rho$-inflated $R$ already shrinks the standardized innovation, so junk is not chased — the two honesty mechanisms compose. Measured on the spike fixtures: shock win rate $0.42\,\to\,1.00$ with $\zeta$ std $3.8\,\to\,0.8$, clean days unchanged; the full-scale validation is in "The audit: were the error bars true?".

### 4.3 Seeding, resets, and what survives a recalibration

A filter is only as trustworthy as its life-cycle rules. Seeding: with a saved prior snapshot, the first state is the *transported* prior through Note 13's provenance hierarchy at provenance-tier covariance; without one, the committed fit's own backbone handles at bootstrap-tier precision — the same information a bootstrap fetch would produce, for free, and deliberately *never* a hidden extra fit (Appendix B records the incident that made this a rule). Resets: a manual quote edit moves the session version and resets the node (the edited chain invalidates the measurement the state was built on); a calendar gap beyond `filterResetHours` resets as `stale` (predicting across a long dark period is worse than reseeding); a source or as-of change wipes the store outright — a live stream and a prior-close snapshot are not the same stochastic clock. Every reset records its reason. And recalibration keeps the state: the update is sequential, one step per genuinely *new* observation, idempotent per (node, data version, session version) — recalibrating an unchanged snapshot re-reads the stored state; a refetch is a new observation, not a reset.

## 5. When trust is a matrix

Everything so far reads naturally per handle. The design allowed more: a full $3\times3$ update, whose off-diagonal gains let one handle's innovation move another's posterior. That is not a bug — it is the optimal estimator when the stated correlations are true. The backtest's second case file is what happens when they are not quite true enough to spend.

> **Case file — the off-diagonal blow-up on coarse chains.**
>
> **Setup.** The Phase-5 temporal backtest replayed the August 2024 spike pair across the eight pilot assets in overlay mode — full-covariance update, Jacobian route, equation (1) verbatim.
>
> **Failure mode.** On EEM and EFA — coarse-strike, wide-spread ETF chains — the posterior ATM error reached 3–28 *vol points*, worse than *both* baselines. A scalar update cannot do that: Proposition 1 pins its posterior between prediction and observation. The damage had to be cross-handle.
>
> **Diagnosis.** On a coarse chain few strikes identify level and curvature separately, so the Jacobian covariance carries strong level–curvature correlation; a junk curvature innovation then drags the ATM level through the off-diagonal entries of $K$. Figure 5 reproduces the mechanism in vitro with the production update: a pure curvature innovation against a correlation-$0.95$ measurement moves the ATM posterior by 20 vol bp while the diagonalized update, fed the same numbers, moves it not at all. The pilot gain cap is no defence: `filterMaxGain` caps the *own*-gains $\operatorname{diag}(KH)$, and the drag travels through terms it never touches.
>
> **Fix.** Production diagonalizes $P^-$ and $R$ before the update — per-handle scalar gains, the Note 14 graph convention. The Joseph form makes the diagonalized gain *valid* ("The update that survives any gain"); the measured incident is what makes it *right*: the off-diagonals of trust must themselves be trusted, and on coarse chains the estimated correlations are exactly the least reliable numbers in the covariance. The full update remains available for later study — the correlations are real information, and a shrunk-correlation update is a live research item, not a closed door.
>
> **Verdict.** Post-fix, EEM wins against the raw measurement (4.5 vs 8.1 bp, $\zeta$ mean 0.14) and EFA degrades gracefully — near-zero gain from its wide-spread $R$, $\zeta$ mean 0.26: conservative rather than wrong. *An honest one-dimensional trust ledger beats a three-dimensional one with unreliable cross-entries.*

> **Figure 5 — The blow-up mechanism in vitro (figure not included in this pack).** The blow-up mechanism in vitro (production update, both paths). A pure junk-curvature innovation is fed to the update as the stated level–curvature correlation in $R$ rises: the full-covariance posterior drags the ATM level by up to 20 vol bp — the level was never observed to move — while the production diagonalized update is immune by construction. The real incident, with correlated prediction uncertainty as well, reached 3–28 vol *points*. *Description:* The figure sweeps the stated level–curvature correlation in the measurement covariance from 0 toward 0.95 while feeding the update a pure curvature innovation (the level observation never moves). Two curves track the resulting ATM posterior displacement: the full-covariance update's curve grows with the correlation, reaching 20 vol bp of ATM drag at correlation 0.95 — movement manufactured entirely by the off-diagonal gain terms — while the production diagonalized update's curve sits identically at zero for every correlation. An annotation notes that the real EEM/EFA incident, where the prediction uncertainty was correlated as well, reached 3–28 vol points.

## 6. Fitting under computed trust: the active MAP

Production ships three modes. `off` is byte-identical to the feature never existing. `overlay` computes and displays — prediction, observation, innovation, gain, posterior, and a drawable filtered curve with a credible band that is the functional pushforward of the full $3\times3$ state covariance through the slice map — but never steers a fit; it is the sandbox in which every budget of "The observation budget" and "The prediction budget" was tuned. `active` moves the same accounting *inside* the calibration.

The wrong way to do that is to build the posterior from today's quotes and then add it as a prior while fitting the same quotes again — the same information counted twice. The correct active objective is the one-stage MAP problem

$$
\mathcal L_{\mathrm{active}}(\theta)
=\mathcal L_{\mathrm{quote}}(\theta;q_t)
+\tfrac12\big\|\mathcal H(\theta)-m_t^-\big\|_{(P_t^-)^{-1}}^2
+\mathcal L_{\mathrm{intrinsic}}(\theta)
+\mathcal L_{\mathrm{persist},\perp}(\theta),
\tag{8}
$$

today's quote likelihood plus the Kalman prediction prior plus the intrinsic regularization plus only the persistence terms orthogonal to the filter state.

**Proposition 2 (No double counting in the MAP form).** If the model is linear, $z=Hx+\epsilon$ with $\epsilon\sim\mathcal N(0,R)$, and $x\sim\mathcal N(m^-,P^-)$, the minimizer of $\tfrac12\|z-Hx\|_{R^{-1}}^2+\tfrac12\|x-m^-\|_{(P^-)^{-1}}^2$ is the Kalman posterior mean of equation (1), and the posterior information is the sum $H^\top R^{-1}H+(P^-)^{-1}$.

*Proof.* The normal equations read $\big(H^\top R^{-1}H+(P^-)^{-1}\big)x=H^\top R^{-1}z+(P^-)^{-1}m^-$. Woodbury rewrites the left inverse as $P^--P^-H^\top(HP^-H^\top+R)^{-1}HP^-$; substitution gives $x=m^-+P^-H^\top(HP^-H^\top+R)^{-1}(z-Hm^-)$. ∎

Production realizes equation (8) with four locked decisions.

1. **The prediction prior is an ungated operator target.** It reuses the smile-factor stencil legs at $k\in\{-b,0,b\}$ with $b=0.06$: on a locally quadratic smile the identities $\sigma(b)-\sigma(-b)=2b\,s$ and $\sigma(b)-2\sigma(0)+\sigma(-b)=b^2\kappa$ are *exact*, so the handle targets convert to stencil targets with no approximation beyond local quadraticity, and the prior flows to LQD, SVI and Multi-Core Sigmoid through the existing operator plumbing with zero per-model wiring. Crucially it carries *no* activation gate: the Kalman prior is always on at its covariance weight — precisely the persistence/filter distinction of "The dial nobody may own".
2. **The weights are the MAP objective in the fit's own units.** The quote rows are near-unit-weighted vol errors — the true MAP objective multiplied through by $s_q^2$ — so the consistent prior weight is $\lambda_j=s_q^2/\operatorname{Var}(O_j)$ with $s_q$ the node's median stated half-spread (the same $s_q$ as "Information, in stated noise").
3. **Persistence auto-exclusion is hard-coded.** In active mode the resolver drops every persistence builder overlapping the handle coordinates — operators, smile factors, the near-ATM strike anchor. What survives is exactly what the filter state does not carry: the deep-tail strike anchor and the graph's dark-node baseline. There is deliberately no knob; two anchors to the same previous state would violate invariant 2.
4. **No second update.** The committed fit *is* the one-stage MAP solution: $m^+$ is its backbone handles, and $P^+$ comes from unwhitening the full solver information (data rows plus whitened prior rows) by the same $s_q$ — landing exactly at $\mathcal I_{\mathrm{data}}+(P^-)^{-1}$, the posterior information of Proposition 2. The MAP-equals-Kalman identity is test-locked to $10^{-10}$. One guard on top: $P^+$ is capped at $P^-$ per handle, because information only adds — inconsistent data ($\rho>1$) should drive $P^+$ *toward* the prediction uncertainty, never beyond it.

### 6.1 Opening the gate before the fit exists

The adaptive gate of "Surprise must widen the budget" reads today's innovation — which, on the active path, does not exist until the MAP fit has run, and by then the prior weight is already spent. This gap was the v2 sweep's one measured weakness (19.5–25.2 bp of shock lag in the spike and high-vol regimes, "The audit: were the error bars true?"), and the shipped fix prices surprise *before* fitting: the *level* row is gated by a fit-free ATM probe — the prepared mid IV interpolated at $k=0$, probe noise $s_q$ — and the *shape* rows by the previous step's realized innovation, a one-step-lagged fading memory (after a surprise day, the next prior is wide). The factors are deterministic in (previous state, prepared chain, options), so the prior builder and the posterior bookkeeping compute identical inflation and the MAP algebra stays consistent. The mechanism is unit-locked (the probe fires on a five-point jump in the prepared mids; clean days are byte-identical; the gate off is the identity). One honesty note for the audit trail: the harness's synthetic shock perturbs only the thinned fit inputs, *not* the prepared mids the probe reads, so the scenario A/B under-reports this fix by construction — the real-world path, a shock present in the prepared chain, is the unit-tested one, and the full-regime validation rides the next sweep.

### 6.2 Where persistence remains

Prior persistence keeps three jobs in active mode, each outside the filter state: deep tails and operator baskets the handles do not represent; the saved prior from which the first filtered state is seeded; and dark graph nodes with no current observation at all. What it never does again is anchor ATM, skew or curvature to the same previous state that already enters as $m^-$ — the auto-exclusion makes that structural rather than procedural.

**Exercise 2.** From Proposition 2, show the posterior information in the MAP form is $\mathcal I_{\mathrm{data}}+(P^-)^{-1}$, and conclude $P^+\preceq P^-$ *exactly* whenever the algebra is exact. The production per-handle cap on $P^+$ therefore only ever binds when the finite-difference handle map or the $\rho$ inflation perturbs the unwhitened information — it is a numerical fence around a theorem, not a new modelling assumption.

## 7. The audit: were the error bars true?

A filter can always make charts smoother; the question worth money is whether its *stated uncertainty* is true. The acceptance metric of the temporal harness is therefore not an RMS but a calibration statistic: the standardized residual

$$
\zeta=\frac{\text{truth}-m^+}{\sqrt{P^++R_{\mathrm{truth}}}},
$$

whose standard deviation should be $1$ if the error bars mean what they say. Even here honesty bites: the held-out "truth" is itself a fitted estimate, and scoring against $\sqrt{P^+}$ alone overstated miscalibration threefold before $R_{\mathrm{truth}}$ was added. The harness drives the *production* commit path over consecutive captured day pairs in three regimes (August 2024 spike, October 2022 high-vol, July 2023 low-vol), eight assets each: fit day $T{-}1$ and commit through the filter; carry the state to day $T$ with the real snapshot $\Delta t$ and forward transport; build day $T$'s measurement from a thinned ATM-only chain under a scenario — `thinned` (plain), `contradiction` (two adjacent strikes kinked opposite ways), `shock` (a true $+5$-point jump with unchanged spreads); score the posterior against the full-chain truth and *two* baselines (raw measurement; gain-zero prediction), bucketed by maturity. Two sweeps: the 38,181-step tuning sweep (overlay only) and the 39,190-step v2 sweep (overlay and active, adaptive gate on). All numbers below are read from the stored artifacts at the decision cell (Jacobian route, $>30$d) — nothing re-run.

> **Figure 6 — The tuning sweep's two headline panels (figure not included in this pack).** The tuning sweep's two headline panels (stored artifacts). A: tripling the clock noise collapses the $\zeta$ std toward $1$ in every regime ($5.16\to1.75$, $1.43\to0.82$, $1.32\to1.05$) — the design value starved the prediction budget, and starved budgets lie. B: on plain thinned days the posterior sits between the raw measurement and the gain-zero prediction: the filter pays for itself on the noisy tail, not on clean liquid days — the success criterion set before the run. *Description:* Panel A is a grouped bar chart of the standardized-residual std under the design clock noise $q=10$ bp$/\sqrt{\text{day}}$ versus the flipped default $q=30$, per regime: spike 5.16 collapsing to 1.75, high-vol 1.43 to 0.82, low-vol 1.32 to 1.05 — every regime moves toward unit scale when the prediction budget stops starving. Panel B plots, per regime on plain thinned days, the median held-out ATM error of the three estimators — raw measurement, filtered posterior, and gain-zero prediction — showing the posterior landing between the other two: better than carrying the prediction alone, not better than a clean measurement on a clean day, exactly the pre-registered success criterion.

**The clock default flipped ($10\to30$), for calibration reasons.** In every regime, on both covariance routes, at every scenario, $q=30$ bp$/\sqrt{\text{day}}$ beats the design value of $10$: the $\zeta$ std collapses toward $1$ (Figure 6, panel A), shock lag shrinks $3$–$7\times$, win rates rise. The lesson generalizes: a too-small process budget does not make a filter cautious — it makes it *overconfident and slow*, the worst pair.

**Jacobian versus factors is a real trade-off; Jacobian stays the default.** On `contradiction` — the core denoising case — the Jacobian route wins $2$–$3\times$ in every regime (spike 15.8 vs 45.9 bp; high 10.5 vs 29.7; low 6.3 vs 21.7): its geometry-aware $R$ sees which directions the kinked cluster fails to identify. On `shock` the ranking reverses (spike 38.6 vs 18.7 bp lag): the factor route's blunter, smaller $R$ yields higher gain. Contradiction rejection is the feature's purpose, the shock gap closes under the adaptive gate below, and the factor route stays one knob away.

**The honest median-day statement.** On plain consecutive days the raw measurement is already good (4.0–7.7 bp median ATM error across regimes) and the filter's median win rate is 0.38–0.49 — *below* one half. The posterior (10.5/9.2/5.3 bp per regime) beats the gain-zero prediction (47/31/22 bp) everywhere but does not beat a clean measurement on a clean day — and should not: the success criterion was "lower held-out error on *noisy* snapshots", never "lower every RMS". Two recorded artifacts of the harness itself: slightly negative $\zeta$ means on thinned days (the ATM-window thinning is mildly biased against the full-chain truth), and a $\le30$ DTE bucket that is a different regime — $90$–$160$ bp thinned-vs-full discrepancies from short-end quote and de-Am noise, reported separately so neither bucket masks the other, and the reason for the maturity noise floor of "The observation budget".

**The adaptive gate, validated at full scale.** The v2 sweep turns the surprise gate on everywhere and the shock columns collapse: $38.6\,\to\,4.6$ bp in the spike regime, $78.6\,\to\,7.9$ in high-vol, $11.6\,\to\,4.9$ in low-vol (Figure 7, panel B), with thinned and contradiction cells unchanged — the gate opens on genuine shocks and stays quiet on clean and on contradictory days, exactly the composition "Surprise must widen the budget" promised.

**Active mode, measured at full scale.** In active mode the committed fit *is* the MAP solution, so the baseline is the overlay run's raw column of the same sweep. The verdict is one-sided wherever denoising is the job (Figure 7, panel A): on plain thinned days the active MAP beats *both* the raw fit and the overlay posterior in every regime (6.5/4.8/3.4 bp against raw 6.7/7.7/4.0), and on contradiction days it wins outright in the high- and low-vol regimes (5.6 vs 9.8 bp raw; 4.5 vs 5.4) while in the spike regime it beats the post-hoc blend (9.1 vs 12.1 bp) though not the raw fit (7.9 bp) — all with honest uncertainty ($\zeta$ std 0.4–1.4 over those cells). Fitting quotes and prediction jointly beats blending them afterwards, exactly as Proposition 2 says it should. The measured weakness is the shock scenario (19.5–25.2 bp lag in the spike and high-vol regimes): the MAP prior weight was priced before the measurement existed. That is precisely the gap the probe-and-lag gate of "Opening the gate before the fit exists" closes by construction; its full-regime scorecard is the flagged item before any active-by-default discussion.

> **Figure 7 — The v2 sweep (figure not included in this pack).** The v2 sweep (stored artifacts; $>30$d, Jacobian route). A: on plain thinned days the active one-stage MAP is the best of the three in every regime — joint fitting beats post-hoc blending. B: the shock columns: the un-gated tuning-sweep overlay lags badly, the adaptive gate collapses the lag ($78.6\to7.9$ bp in high-vol), and the active MAP still lags — its prior was priced before the measurement existed, the gap the fit-path probe gate closes. *Description:* Panel A compares median held-out ATM error on plain thinned days across the three regimes for the raw fit, the overlay posterior, and the active one-stage MAP: the active MAP posts the lowest bar in every regime (6.5 vs raw 6.7 in the spike, 4.8 vs 7.7 in high-vol, 3.4 vs 4.0 in low-vol) — the same accounting done inside the objective beats blending it in afterwards. Panel B shows the shock-scenario lag per regime for three arms: the un-gated tuning-sweep overlay (38.6/78.6/11.6 bp), the gate-on v2 overlay (collapsed to 4.6/7.9/4.9 bp), and the active MAP, which still lags at 19.5–25.2 bp in the spike and high-vol regimes because its prior weight was fixed before the measurement existed — the gap the fit-path probe gate of "Opening the gate before the fit exists" was built to close.

**Exercise 3.** A +5-point overnight jump under a $30$ bp$/\sqrt{\text{day}}$ clock is a ${\sim}50\sigma$ event: compute the un-gated gain for a liquid chain ($r\approx(10\,\text{bp})^2$, $p=q^2\Delta t$) and the residual lag after one update; then apply the $(\zeta/3)^2$ inflation and recompute. Explain why the same inflation does *not* fire on the contradiction scenario even though its innovation is also large in raw units (the $\rho$-inflated $R$ enters the standardization).

## 8. What is genuinely original here

The equations are Kalman's [Kalman1960, AndersonMoore1979]; the contribution is a discipline. *Three notions usually blended in volatility tools are held separate*: today's quote likelihood (Note 07), the temporal state with prediction and measurement covariances (this note), and gap persistence that activates only where quotes do not identify a functional (Note 13) — the separation is what lets the filter denoise without using yesterday as a fake quote, and persistence stabilize wings without damping a real move. *The measurement covariance is a market object*: propagated from the fit's own information in stated bid–ask units, with the eigen-clamp choosing the honest sign of failure and the $\chi^2$ inflation converting internal contradiction into stated noise — so the gain falls on a lying chain with no thresholds anywhere. *The prediction budget runs on the market's clock*, with a measured cadence audit behind the session clock and a surprise gate that composes correctly with the contradiction inflation. *The active mode is an accounting identity*, not a feature: one-stage MAP with the ungated stencil prior, hard-coded persistence exclusion, and a posterior read off the solver's own information — double counting made impossible rather than discouraged. And the whole feature is judged by *calibration of uncertainty* ($\zeta\to1$), the audit that flipped a default, chose a route, and convicted a matrix.

## 9. Limitations

Where the guarantees stop. *The diagonal update discards genuine cross-handle information*; the blow-up showed why that trade is currently right, and a shrunk-correlation update is a live research item, not a closed door. *The session clock is measured but not default*: calendar remains the byte-identical default, and the campaign's residual is real — at the default per-handle scales the skew and curvature $\zeta$ run 1.8 and 6.4 on the thirty-minute cadence, worst on short-dated nodes, so per-maturity handle scales are the recorded follow-up. *The fit-path surprise gate is shipped but not yet sweep-validated*: the harness's synthetic shock cannot see it by construction ("Opening the gate before the fit exists"), so its evidence is unit-level until the next full-regime run — *the* open item before any active-by-default. *The short end stays the weakest bucket*: the $\sqrt{30/\mathrm{DTE}}$ floor sizes $R$ honestly below $30$ DTE, but honest uncertainty is not signal. *The state is per-node*: a graph-coupled filter (Note 14's block covariance with time dynamics) is deferred until the single-node filter has earned trust. And *the measurement carrier is the LQD backbone*: a displayed model whose handles disagree with the backbone's inherits that disagreement through the overlay.

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

**Table 2 — Observation-filter hyperparameters, as shipped.**

*Surfaced (options settings)*

| Knob | Default | Role |
|---|---|---|
| `observationFilterMode` | `off` | `off` / `overlay` / `active` ("Fitting under computed trust: the active MAP"); `off` is byte-identical to the feature never existing. |
| `filterCovarianceMode` | `jacobian` | Measurement route: equation (3) (backtested default) or equation (5) (fallback + A/B column). |
| `filterProcessVolBpSqrtDay` | $30$ | ATM clock noise (vol bp per $\sqrt{\text{day}}$); flipped from the design $10$ by the audit (Figure 6, panel A). |
| `filterProcessSkewSqrtDay` | $0.02$ | Skew clock scale. |
| `filterProcessCurvSqrtDay` | $0.05$ | Curvature clock scale. |
| `filterTransportNoiseScale` | $0.10$ | Extra process std per unit $|h|$ transport distance. |
| `filterResidualInflation` | on | Apply equation (4). |
| `filterAdaptiveSigma` | $3$ | Surprise gate ("Surprise must widen the budget"); overlay gates on today's innovation, active on the ATM probe + lagged innovation ("Opening the gate before the fit exists"); $0$ = off. |
| `filterMaxGain` | $1.0$ | Pilot own-gain cap; never binds at $1.0$. |
| `filterResetHours` | $96$ | Maximum gap predicted across; longer resets as `stale` (spans a weekend plus a holiday). |
| `filterClock` | `calendar` | Process-noise clock: `calendar` (wall-clock days, byte-identical legacy) or `session` (the intraday variance clock, "The clock the variance actually runs on"). Resets stay on calendar hours regardless. |
| `filterSessionShare` | $0.60$ | Share of a day's variance accrued in the exchange session under the session clock. |
| `filterNonTradingWeight` | $0.0$ | A closed day's variance weight under the session clock (a weekend $\approx$ one overnight, measured). |
| `filterDataOnlyPrepass` | off | Opt-in extra data-only fit so $z_t$ is strictly persistence-free; off flags contamination instead. |

*Hidden (internal constants)*

| Knob | Default | Role |
|---|---|---|
| `DIAGONAL_UPDATE` | on | Per-handle scalar gains ("When trust is a matrix"); the measured answer to the off-diagonal blow-up. |
| `FILTER_STENCIL_H` | $0.06$ | ATM stencil half-width of the active MAP prior legs (exact identities on a locally quadratic smile). |
| `RESID_INFLATION_CAP` | $25$ | Cap on $\rho$ and on the adaptive inflation factors: one broken chain cannot poison the state. |
| `SHORT_DATED_REF_DAYS` | $30$ | Noise floor $\sqrt{30/\mathrm{DTE}}$ below $30$ DTE, applied to $R_t$, the MAP weights and the unwhitening. |
| `INFO_RANK_RTOL` | $10^{-10}$ | Eigen-clamp cutoff of $\mathcal I_\theta$: small eigenvalues clamp *up*, so unidentified directions inflate $R$ finitely ("Information, in stated noise"). |
| `CHOL_JITTER` | $10^{-12}$ | Whitening-Cholesky base jitter; any nonzero use is a reported diagnostic event, never silent. |
| `HANDLE_MOVE_SCALES` | $(0.03,0.05,0.5)$ | Typical one-day move scales (the Note 14 units convention) sizing the transport term. |
| `RMS_FLOOR` | $10^{-4}$ | Floor on the stated per-quote noise (one vol bp); chains without band data use $10\times$ this floor. |
| variance envelope | graph floors/caps | Per-handle $R$ diagonals clipped into the graph layer's sanity envelope, correlations rescaled to survive. |
| `_filter_version` | — | Overlay-only knob changes bump a lightweight version (no fit-cache invalidation); only `active`-affecting changes bump the options version. |

## Appendix B. Performance notes

1. **Overlay mode is invisible next to calibration**: a dense $d\times d$ solve with $d=3$, state storage $O(d^2)$ per node.
2. **The Jacobian covariance is nearly free**: $J^\top WJ$ comes from the solution Jacobian the calibrators already retain, and $G$ is $2P$ slice *builds* on the coarse optimization grid — about $4\times$ cheaper per build than the display quadrature.
3. **Seeding must never hide a fit.** The first implementation seeded through the prior bootstrap branch, whose fetch path silently ran a full extra mid calibration per node — switching the filter on made a live universe crawl. The shipped rule seeds from the transported saved prior, else from the committed fit's own handles at bootstrap-tier precision: the same information, for free. Reverted-and-redesigned, per house practice.
4. **Overlay curves are memoized per committed state.** The filtered curve is the backbone retargeted to $m^+$ (a Newton solve, Note 01) plus the functional band; computing them per GET made the live UI feel frozen, since the smile view polls per refresh signal.
5. **Active MAP adds no second fit pass**: three residual rows in the existing stack; the data-only prepass is the only real cost lever and is off by default.
6. **The session clock costs an integral over day segments**, microseconds per prediction; the cadence audit itself (Figure 4) reads stored campaign tables. No benchmark in this note was re-timed; figures and macros were generated at commit `e760d39` on 2026-07-27.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 3 — Claims in this note and the code/tests that lock them.**

| Claim | Object | Code anchor | Test anchor |
|---|---|---|---|
| Joseph update PSD for any gain; own-gain cap; scalar shrinkage; agrees with the graph posterior to $10^{-12}$ | equation (1), Proposition 1 | `calib/observation_filter.py` | `test_observation_filter.py` |
| One-stage MAP minimizer $=$ Kalman posterior to $10^{-10}$; ungated stencil prior; no second update | Proposition 2, equation (8) | `calib/observation_filter.py`, `api/observation_filter.py` | `test_observation_filter.py`, `test_filter_active.py` |
| Jacobian covariance; regularized eigen-inverse; stated-noise units contract | equation (3), "Information, in stated noise" | `calib/observation_measurement.py` | `test_observation_measurement.py` |
| Contradictions inflate $R$; band rows contribute nothing inside the spread | equation (4) | `calib/observation_measurement.py` | `test_observation_measurement.py` |
| Diagonal update; idempotent commits; reset matrix; seeding without a hidden fit; short-dated floor | "When trust is a matrix", "Seeding, resets, and what survives a recalibration" | `api/observation_filter.py` | `test_observation_filter_app.py` |
| Mode resolution; `off` byte-identical; overlay never steers fits | "Fitting under computed trust: the active MAP" | `api/filter_mode.py` | `test_filter_mode.py` |
| Persistence auto-exclusion: only the deep-tail anchor and dark nodes survive in active mode | "Fitting under computed trust: the active MAP" | `api/prior_mode.py` | `test_filter_active.py::test_auto_exclusion_truth_table` |
| Active-path surprise gate: ATM probe + lagged shape gate, deterministic factors | "Opening the gate before the fit exists" | `api/observation_filter.py` | `test_observation_filter_app.py::test_active_adaptive_probe_and_lag` |
| Session clock: nests the calendar convention; shapes the filter $\Delta t$; resets stay on calendar hours | "The clock the variance actually runs on" | `calib/intraday_time.py`, `api/observation_filter.py` | `test_intraday_time.py`, `test_observation_filter_app.py::test_filter_dt_days_session_clock_shapes` |
| Temporal backtest protocol, scenarios and $\zeta$ scoring | "The audit: were the error bars true?" | `backtest/observation_filter.py` | `test_filter_backtest.py` |
| 0DTE cadence campaign (measurement tables and clock sweep) | "The clock the variance actually runs on" | `backtest/observation_filter_intraday.py` | `test_intraday_time.py` |

## Appendix D. Reference implementation

The numerical heart is small and model-free. Per the transfer policy the pack carries no source code; the note's two reference listings are replaced by the exact algorithm specifications below, which carry every algorithmic detail. Executed against the production `kalman_update` on a random-seeded $3\times3$ problem (full covariances, $H=I$), and against the production whitened MAP rows and prior-weight identity, the maximum deviation across mean, covariance, innovation, innovation covariance, gain, whitening and $\lambda_j=s_q^2/\operatorname{Var}(O_j)$ is at most $1.0\times10^{-17}$ — machine precision, as it should be: production adds only input validation, the own-gain cap and the PSD guard around the same algebra.

**Algorithm D.1 — covariance-form update with Joseph covariance (verified against production; agreement stated above).**

*Inputs:* predicted mean $m$ (length-$n$ vector), predicted covariance $P$ ($n\times n$), observation $z$, observation covariance $R$, measurement operator $H$ (defaults to the $n\times n$ identity when a direct handle observation is meant). All inputs are treated in double precision.

*Steps:*

1. Innovation: $\nu = z - Hm$.
2. Innovation covariance: $S = HPH^\top + R$.
3. Gain: $K = PH^\top S^{-1}$, computed by solving the transposed linear system $S^\top X = (PH^\top)^\top$ and setting $K=X^\top$ — no explicit matrix inverse is ever formed.
4. Posterior mean: $m^+ = m + K\nu$.
5. Joseph posterior covariance with $A = I - KH$: $P^+ = APA^\top + KRK^\top$.
6. Symmetrization: return $\tfrac12(P^+ + P^{+\top})$ as the posterior covariance.

*Outputs:* posterior mean $m^+$, symmetrized posterior covariance, innovation $\nu$, innovation covariance $S$, and gain $K$.

**Algorithm D.2 — whitened residual rows for the active MAP prediction prior (distilled from `calib/observation_filter.py`; production escalates a reported jitter — a diagnostic event, never a silent repair).**

*Inputs:* the model's handle vector $\mathcal H(\theta)$, the predicted mean $m^-$, the prediction covariance $P^-$.

*Steps:*

1. Cholesky-factor the prediction covariance: $P^- = LL^\top$ (lower-triangular $L$). If the factorization requires jitter, production adds its base jitter of $10^{-12}$ and *reports* the event as a diagnostic — never silently.
2. Return the whitened residual $L^{-1}\big(\mathcal H(\theta)-m^-\big)$, computed by forward-substitution against $L$ (a triangular solve, not an inverse).

*Output:* the vector of whitened prior residual rows appended to the calibration stack, whose squared norm is exactly the Mahalanobis prior term $\|\mathcal H(\theta)-m^-\|_{(P^-)^{-1}}^2$ of equation (8).

## References

- [Kalman1960] R. E. Kalman. A new approach to linear filtering and prediction problems. *Journal of Basic Engineering*, 82(1):35–45, 1960.
- [AndersonMoore1979] B. D. O. Anderson and J. B. Moore. *Optimal Filtering*. Prentice-Hall, 1979.
- [Gelman2013] A. Gelman et al. *Bayesian Data Analysis*. CRC Press, 3rd ed., 2013.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.



