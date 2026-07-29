# Where the Likelihood Is Flat

**Note 13 — prior persistence · lecture edition ("where the likelihood is flat") · converted from 13_prior_flat_directions.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

*Prior persistence as estimation in the flat directions of today's data: yesterday may speak only where today is silent. Vol-Fitter Technical Notes, No. 13.*

> **Abstract.** A sparse morning does not determine a smile. On a real SPY expiry with quotes confined to the at-the-money band, 8 production calibrations agree to 1 vol bp where quoted and disagree by 2.6 vol points at $k=-0.30$: the likelihood has flat directions, and something other than the data must choose along them. This lecture develops the Vol-Fitter's prior persistence as the answer to exactly that question. Yesterday's surface enters today's fit as extra least-squares rows, but a row is admitted only where today's quotes fail to identify its coordinate: an *activation gate* with a provable dead zone (a well-observed coordinate receives exactly zero prior weight, not a small one), an information price for every persisted quantity (the precision of a signed basket is the harmonic combination of its legs' quote support — one dead leg unidentifies the basket), and a choice of coordinates that keeps yesterday out of what today has measured (risk-reversals and butterflies annihilate the level direction that per-strike anchoring damps). The same principle in coverage currency gives the strike-gap anchor, whose absolute-price rows are right when the level is stable and wrong across a jump — measured here on a controlled 4-point overnight jump, where the operator rows reconstruct the lifted wing to 0.3 vol points while the strike anchor misses it by 3.7. We also prosecute the gate's own blind spot: its support proxy credits identification one kernel bandwidth beyond the last quote, which closes every vol-operator gate on a liquid morning — the measured reason the pure operator modes add nothing at the median of the stored 1116-node temporal backtest, while the shipped hybrid default (shape operators plus deep-tail strike anchors) improves held-out wing reconstruction by $\sim$32 vol bp, 66% of the time. On the running SPY node the hybrid refit holds the retained band to 2 vol bp while reconstructing the withheld wing to 42 vol bp rms against the market-only fit's 90.

## 1. The morning after

Overnight, two things change unevenly. The at-the-money level moves on fresh news and is immediately re-quoted; the wings may receive no fresh quote at all, yet the book still needs values there. The naive alternatives both fail in known ways: refit today's quotes alone and the unconstrained wings *flap*; anchor the whole fit to yesterday and the prior *damps* the genuine at-the-money move. Before designing anything, it pays to say precisely what a sparse morning leaves undetermined.

Figure 1 does this on the note's running character — a real SPY expiry (December 2026) from a live production export, its 30 morning quotes confined to $|k|\le0.10$. We fit the band 8 times with production calibrators: one model family at three resolutions and two regularization strengths, plus two entirely different parametric families. Panel A shows all eight: on the quoted band they are one curve (maximum disagreement 1 vol bp); at $k=-0.30$ they disagree by 2.6 vol points. The likelihood — the weighted sum of squared quote residuals, whatever the model — is *flat* along the directions that move the wings while leaving the band unchanged, and every fitter must pick a point on that flat set by some rule: a regularizer, a parametric family's built-in tail habit, a prior. Panel B quantifies where the flatness lives: the effective quote count $s(k)$ (defined in "Measuring flatness: the information of a functional") collapses outside the band exactly where the ensemble spread opens.

> **Figure 1 — What a sparse morning does not determine (figure not included in this pack).** What a sparse morning does not determine (real SPY node, production calibrators). A: 8 fits — one family at several resolutions and regularizations, plus two other model families — agree to 1 vol bp on the quoted band (shaded) and spread 2.6 vol points at $k=-0.30$. The data does not choose; the extrapolation rule does. B: the quote-support profile $s(k)$ (left axis) collapses precisely where the ensemble spread (right axis) opens: flatness is measurable, coordinate by coordinate. *Description:* Panel A overlays eight fitted implied-volatility smiles against log-moneyness on the real SPY December-2026 expiry, with the quoted band $|k|\le0.10$ shaded; inside the band the eight curves are visually a single line (maximum spread 1 vol bp), while to the left of the band they fan out to a 2.6-vol-point disagreement at $k=-0.30$. Panel B plots the Gaussian-kernel effective quote count $s(k)$ on the left axis against the same $k$ grid, and the cross-fit ensemble spread on the right axis; the two curves are near mirror images — $s(k)$ falls toward zero exactly where the spread opens, making the flat directions of the likelihood measurable coordinate by coordinate.

The design question of this note is therefore *not* "how hard should the prior pull?" but "*where* is the prior allowed to pull at all?" The answer the fitter ships: only along the flat directions. A feature today's quotes identify belongs to today; a feature they do not belongs to yesterday, transported to today's market. Damping is what happens when the prior leaks into the identified directions; flapping is what happens when nothing occupies the unidentified ones.

> **Invariants protected in this note.**
> 1. **Do not damp the signal.** A coordinate today's quotes identify at the required precision receives prior weight exactly zero — a dead zone, not a small bias.
> 2. **Fill the gap.** A coordinate today's quotes do not identify is held at the transported prior, with strength growing as coverage falls.
> 3. **Strictly additive.** Mode `off` is byte-identical to a plain fit; every prior block is a no-op when its target is empty.
> 4. **Coupled features persist coupled.** A risk-reversal is one statement about the smile, not two statements about strikes; persistence must not silently decompose it.

**Conventions and the notation ledger.** One time symbol: $\tau$, the node's variance time (Note 11 owns the clock question; every prior value below is re-expressed at the node's $\tau$, and the rescale cancels in vol space). Subscripted $\partial$ for the rare partial derivative; primes are never used. One move symbol: $h=\log(F_{\text{now}}/F_{\text{prior}})$, reserved for the transported forward distance. One bandwidth symbol: $b$, the Gaussian kernel width of the support measure *and* the factor stencil step — production deliberately ties both to a single knob.

**Table 1 — Every symbol in the note.** Nothing is reused with a second meaning; $b$ is one symbol because production makes it one knob.

| Symbol | Meaning |
|---|---|
| $k,\ \tau$ | log-moneyness; variance time |
| $\sigma(k),\ w(k)=\sigma^2\tau$ | implied vol; total variance |
| $O=c^\top\sigma=\sum_a c_a\sigma(k_a)$ | a signed basket over legs $k_a$ |
| $s_a,\ s(k),\ b$ | quote support; its bandwidth |
| $\pi,\ \pi_{\mathrm{req}}$ | observation precision; requirement |
| $g,\ \gamma$ | the activation gate; its exponent |
| $\lambda_j,\ B$ | row weight; a mode's budget |
| $\rho_{\mathrm{obs}},\rho_{\mathrm{des}},\Delta x_j,u$ | densities; cell width; unmet fraction |
| $h$ | transported forward move |
| $\Delta,\ \mathbf{1}$ | option delta; the level direction |

## 2. Yesterday as evidence: the Bayesian rows

The mechanics are ordinary Bayesian least squares. Yesterday's surface, transported to today's forward (see "The prior must arrive in today's chart"), supplies *pseudo-observations*: functionals $O_j$ evaluated on the prior become targets for the same functionals evaluated on the model, appended to the data rows. Every persistence mode in the fitter — strike anchors, quote operators, smile factors — adds rows of one universal shape.

**Central equation.**

$$
r_j=\sqrt{\lambda_j}\;\frac{O_j(\theta)-O_j(\text{prior})}{\text{scale}_j},
\tag{1}
$$

where $O_j$ is a call price at a delta location, a quote operator (ATM, risk-reversal, butterfly, var-swap), or a local smile factor, depending on the mode (see "The policy layer: seven modes"), and $\theta$ is whichever model is being calibrated — the rows are model-agnostic because they only consult the model's smile.

Everything therefore reduces to choosing the weights $\lambda_j$. For one scalar coordinate the posterior is the precision-weighted average: a datum $d$ at precision $\pi$ against a prior mean $\mu$ at precision $\lambda$ gives posterior mean $(\lambda\mu+\pi d)/(\lambda+\pi)$, so the *share of the posterior owned by the prior* is $\lambda/(\lambda+\pi)$. Here is the first design fork. A *ridge* — fixed $\lambda>0$, however small — owns a positive share of every coordinate: it biases the well-observed ATM exactly as surely as it stabilizes the dark wing, only less. Under invariant 1 that is not a small flaw but a disqualification: no fixed prior precision has a dead zone. The prior precision must depend on the data.

**Definition 1 (Activation gate).** For observation precision $\pi\ge0$, required precision $\pi_{\mathrm{req}}>0$ and sharpness $\gamma>0$,

$$
g(\pi)=\Big(\min\big(\max\big(1-\pi/\pi_{\mathrm{req}},\,0\big),\,1\big)\Big)^{\gamma}.
\tag{2}
$$

The gate is $1$ where the data says nothing, decreases monotonically as the data improves, and — the decisive property — is *exactly zero* for all $\pi\ge\pi_{\mathrm{req}}$, not asymptotically small. $\gamma$ sharpens the edge. The prior precision actually entering the fit is $\lambda\,g(\pi)$, and Figure 2, panel B, shows the resulting posterior share against the ridge's: same behaviour in the dark, a hard zero in the light.

**Proposition 1 (The no-damp guarantee).** Fix a mode and let coordinate $j$ satisfy $\pi_j\ge\pi_{\mathrm{req},j}$, so $g_j=0$ and hence $\lambda_j=0$ in equation (1). Then $r_j\equiv0$ for every parameter vector $\theta$: the objective, its gradient and its Gauss–Newton model are independent of the prior value $O_j(\text{prior})$. In particular, with all gates closed the fit is the prior-free fit, and with mode `off` the fit is byte-identical to a plain fit.

*Proof.* $\lambda_j=0$ makes $r_j$ the zero function of $\theta$: it contributes $0$ to the cost and a zero row to the Jacobian, so nothing downstream can depend on the prior through it. The byte-identity claims are locked by `test_none_anchor_leaves_the_fit_byte_identical` and the `off`-mode routing tests (Appendix C, Traceability). ∎

This is the difference between gating and shrinkage, and it is worth naming in the standard vocabulary: Tikhonov regularization [Tikhonov1977] stabilizes by biasing everywhere; the gate is a data-dependent penalty whose support is confined to the coordinates the data left unidentified. It spends its entire budget where the likelihood is flat and nothing anywhere else.

> **Algorithm — the activation gate, equation (2), from the shared vocabulary (`calib/precision.py`); executed against production in Appendix D.** (Replaces the note's code listing; the pack carries no source code.) Input: observed precision $\pi\ge0$, requirement $\pi_{\mathrm{req}}$, sharpness $\gamma$ (default $1$). Output: $g=\big(\mathrm{clip}(1-\pi/\max(\pi_{\mathrm{req}},10^{-12}),\,0,\,1)\big)^{\gamma}$. The $10^{-12}$ floor guards the division; the clip realizes the min/max of equation (2). The value reads $1$ when the data is silent and exactly $0$ once $\pi\ge\pi_{\mathrm{req}}$: the coordinate is identified.

> **Figure 2 — The gate and why shrinkage cannot replace it (figure not included in this pack).** The gate and why shrinkage cannot replace it (production `activation_gap`). A: the gate of equation (2) for three sharpness values — past the required precision the prior weight is exactly zero. B: the share of the posterior owned by the prior. A ridge with fixed prior precision (dashed) still owns a quarter of a coordinate observed at twice the requirement; the gated prior (solid) owns exactly nothing — the dead zone that turns "do not damp the signal" from a preference into a theorem. *Description:* Panel A plots $g(\pi)$ against $\pi/\pi_{\mathrm{req}}$ for three values of $\gamma$; all three curves start at $1$ at $\pi=0$, descend monotonically, and hit exactly zero at $\pi=\pi_{\mathrm{req}}$, with larger $\gamma$ bending the descent harder near the threshold. Panel B compares the posterior share $\lambda/(\lambda+\pi)$ under a fixed-$\lambda$ ridge (dashed, strictly positive everywhere — about $25\%$ at $\pi=2\pi_{\mathrm{req}}$) with the gated share $\lambda g(\pi)/(\lambda g(\pi)+\pi)$ (solid), which coincides with the ridge in the data-silent region and is identically zero past the requirement.

**Exercise 1.** Show that under a fixed-precision ridge the posterior bias of a coordinate with true value $d$ and prior mean $\mu$ is $(\mu-d)\,\lambda/(\lambda+\pi)$, and that requiring this to vanish for all well-observed coordinates while keeping $\lambda>0$ for unobserved ones forces $\lambda$ to depend on $\pi$ with a zero at finite $\pi$ — i.e. forces a gate of the form of equation (2) up to the choice of the descent profile.

## 3. Measuring flatness: the information of a functional

The gate consumes a precision $\pi$; the fitter must produce one per persisted coordinate, cheaply, before fitting. The shipped currency is *quote support*: each leg location $k_a$ receives the Gaussian-kernel effective quote count

$$
s_a=\sum_q \tilde\omega_q\, e^{-(k_q-k_a)^2/2b^2},
\tag{3}
$$

with $k_q$ the live quote locations, $\tilde\omega_q$ the fit weights normalized to mean one (so $s_a$ reads as "how many quotes effectively sit on this leg" under any weighting scheme), and $b$ the bandwidth. A quote exactly on the leg contributes one; a quote a few bandwidths away contributes nothing.

Support prices a *leg*. The persisted objects are *baskets* $O=c^\top\sigma$ over several legs, and their price follows from the standard sampling theory of a linear functional [LehmannCasella1998]:

**Assumption 1.** Each leg vol is estimable from today's quotes with variance proportional to $1/s_a$, independently across legs (a diagonal information model; "What the proxy cannot see" examines where it fails).

**Proposition 2 (Harmonic support is the propagated basket precision).** Under Assumption 1, the implied estimate of $O=\sum_a c_a\sigma(k_a)$ has variance proportional to $\sum_a c_a^2/s_a$, i.e. precision

$$
\pi(O)=\Big(\sum_a\frac{c_a^2}{s_a+\varepsilon}\Big)^{-1}.
\tag{4}
$$

In particular one unquoted leg ($s_a\to0$) drives $\pi(O)\to0$ however well the other legs are quoted: a risk-reversal with a missing put leg is unidentified, and its gate opens.

*Proof.* $\operatorname{Var}\big(\sum_ac_a\hat\sigma_a\big)=\sum_ac_a^2\operatorname{Var}(\hat\sigma_a)\propto\sum_ac_a^2/s_a$ by independence; take reciprocals. The $\varepsilon$ regularizes the empty-leg limit. ∎

Figure 3 shows both faces of equation (4) computed by the production builder. Panel A sweeps a widening quote band on a controlled smile: the ATM basket is identified almost immediately, while the risk-reversal and butterfly stay dark until the band approaches their $25\Delta$ legs — and begin to rise *one bandwidth before* the quotes actually arrive, the kernel bleed we prosecute in "What the proxy cannot see". Panel B is the dead-leg law: with the call leg well quoted, the basket precision still collapses linearly as the put leg's support vanishes.

> **Figure 3 — The information price of a basket (figure not included in this pack).** The information price of a basket (production support and gate machinery). A: precision of ATM, RR25 and BF25 as a fixed budget of quotes spreads over a widening band — the wing baskets cross the requirement (dotted) only when coverage approaches the $25\Delta$ put leg (vertical line), and decline again as the same quotes thin out. B: one dead leg unidentifies the whole basket, however well the others are quoted — the harmonic law of equation (4). *Description:* Panel A plots the basket precisions $\pi(\mathrm{ATM})$, $\pi(\mathrm{RR25})$ and $\pi(\mathrm{BF25})$ against the half-width of a widening quote band on a controlled smile; the ATM curve jumps above the dotted requirement line almost immediately, while the RR25 and BF25 curves stay near zero until the band edge nears the $25\Delta$ put-leg location (marked by a vertical line), start rising roughly one kernel bandwidth before the quotes reach the leg, cross the requirement, then decline again as the fixed quote budget spreads thin. Panel B fixes the call leg's support high and sweeps the put leg's support toward zero: the risk-reversal's basket precision falls essentially linearly to zero — the dead-leg limit of the harmonic law — regardless of how well the other leg is quoted.

**Remark 1 (Identifiability belongs to the functional, not the legs).** Take symmetric wing support $s_c=s_p=s$ and abundant ATM support. Then $\pi(\text{RR})=s/2$ but $\pi(\text{BF})\approx2s$: the butterfly's wing coefficients of $\tfrac12$ enter equation (4) squared, so *the same legs* make the butterfly four times easier to identify than the risk-reversal. This is visible in production: on the case-file market of "Choosing coordinates: why baskets" the gate closes BF25 while leaving RR25 open (Figure 5, panel B) — the budget concentrates on the one shape coordinate the morning genuinely left dark.

The active weights split a mode's budget over the open gates,

$$
\lambda_j=B\,\frac{g_j}{\sum_i g_i},
\qquad B=\frac{\text{strength}\,\%}{100}\sum_q\omega_q ,
\tag{5}
$$

and operators with $g_j=0$ are dropped from the target entirely — they never reach the optimizer. Making the budget a percentage of the summed quote weights keeps the prior's strength proportional to how much evidence the fit actually has.

**Remark 2 (What the shipped gate does *not* use).** The requirement $\pi_{\mathrm{req}}$ is one scalar for all operators (a per-operator schedule is declared in the design but not implemented), and the split of equation (5) does *not* multiply a base prior precision. The richer vocabulary that lives beside the gate in `calib/precision.py` — the scalar confidence factors

$$
\begin{aligned}
\text{density}&=\mathrm{clip}(n/8,\,0.15,\,1), &
\text{spread}&=\frac{1}{1+\text{rel spread}/0.05},\\
\text{freshness}&=2^{-\text{age}/\text{half-life}}\ (3\,\text{d obs},\ 30\,\text{d prior}), &
\text{transport}&=e^{-|h|/0.10},
\end{aligned}
\tag{6}
$$

plus fit quality $1/\text{rms}^2$ floored at one vol bp and `active_prior_precision` — is consumed by the *graph baseline* of Note 14, which imports these functions from here. The re-export is golden-locked, so the persistence gate and the graph price identifiability in one language and cannot silently drift apart.

**Exercise 2.** A risk-reversal has call-leg support $s_c=6$ and put-leg support $s_p=0.1$. Compute $\pi(\text{RR})$ from equation (4) ($\approx0.098$ — so at any requirement $\pi_{\mathrm{req}}$ of order one the gate is nearly fully open), then let $s_p\to0$ and confirm the basket is unidentified regardless of $s_c$. Repeat for the butterfly with abundant ATM support and conclude the factor-of-four of Remark 1.

## 4. Choosing coordinates: why baskets

The gate acts coordinate by coordinate. That makes the *choice of coordinates* load-bearing: gating can only keep yesterday out of what today has measured if "measured" and "unmeasured" land in different coordinates. The smile's natural trader coordinates do exactly this, and the fitter persists them directly.

**Definition 2 (Quote operators).** With $\sigma(k)$ a slice's implied vol, $k_{c,\delta},k_{p,\delta}$ the call/put strikes at delta $\delta$ located on the *prior* smile and frozen, and `collarSign` fixing the orientation:

$$
\text{ATM}=\sigma(0),\qquad
\text{RR}_\delta=\pm\big(\sigma(k_{c,\delta})-\sigma(k_{p,\delta})\big),\qquad
\text{BF}_\delta=\tfrac12\big(\sigma(k_{c,\delta})+\sigma(k_{p,\delta})\big)-\sigma(0),
$$

plus $\text{VarSwap}=\sqrt{K_{\mathrm{var}}/\tau}$ by log-contract replication. Each is a signed basket $O=c^\top\sigma$; the registry knows $\{$ATM, RR25, BF25, RR10, BF10, VarSwap$\}$. Because the legs are frozen on the transported prior, prior and model are compared at the same log-moneyness, and the variance-time rescale between the prior's clock and the node's cancels in vol space — what persists is the *shape*, not the variance.

**Definition 3 (Smile factors).** The factor mode replaces delta legs by ATM-local stencils of step $b$: $\text{skew}=\sigma(b)-\sigma(-b)$, $\text{curvature}=\sigma(b)-2\sigma(0)+\sigma(-b)$, $\text{leftWing}=\sigma(-3b)-\sigma(0)$, $\text{rightWing}=\sigma(3b)-\sigma(0)$ — raw differences, not divided by the step, so they remain vol-magnitude quantities comparable to the level, and prior and model use the same stencil. Factors are structurally identical baskets and reuse the operator gate, budget split and target machinery verbatim; they bite on genuinely sparse smiles, where even the local shape is dark.

Why baskets and not legs? Because the coordinates decide what the penalty can damp.

**Proposition 3 (Baskets annihilate exactly the directions legs would damp).** Consider one operator $O=c^\top\sigma$ over $L$ legs and compare two penalties on the leg vols $\sigma\in\mathbb{R}^L$: the basket row $r_{\mathrm{bsk}}=\sqrt\lambda\,(c^\top\sigma-c^\top\sigma^{\mathrm{prior}})$ and the per-leg stack $r_a=\sqrt{\lambda_a}\,(\sigma_a-\sigma_a^{\mathrm{prior}})$, $a=1,\dots,L$. The basket penalty is invariant under every move $\delta$ with $c^\top\delta=0$ — an $(L{-}1)$-dimensional space that, for RR and BF, contains the common level shift $\delta=\mathbf{1}$, since their coefficients sum to zero. The per-leg stack is invariant only under $\delta=0$: at $\sigma^{\mathrm{prior}}+t\mathbf{1}$ its cost grows as $t^2\sum_a\lambda_a$, i.e. it damps a market-wide vol move even when the market's RR and BF are unchanged.

*Proof.* $r_{\mathrm{bsk}}$ depends on $\sigma$ only through $c^\top\sigma$, so its level sets are affine hyperplanes with normal $c$; any $\delta\in c^{\perp}$ leaves it fixed and $\dim c^{\perp}=L-1$. For RR, $c=(+1,-1)$; for BF, $c=(\tfrac12,\tfrac12,-1)$; both satisfy $c^\top\mathbf{1}=0$, so $\mathbf{1}\in c^{\perp}$. The per-leg stack has Jacobian $\operatorname{diag}(\sqrt{\lambda_a})$ of full rank, so its only invariant direction is $0$, and its value at $\sigma^{\mathrm{prior}}+t\mathbf{1}$ is $t^2\sum_a\lambda_a$. ∎

This is invariant 4 made precise, and it is the theorem behind a design reversal. The first local-volatility route emitted synthetic *per-leg* quotes at the operator legs — and silently damped the level, exactly as the proposition predicts. The shipped design emits one signed basket per operator; on the local-vol surface, where the natural unknowns are call prices, the basket is transported to price space by the frozen-vega linearization $\sigma(k_a)\approx\sigma^{\mathrm{prior}}_a+(P_a-P^{\mathrm{prior}}_a)/\text{vega}_a$: weights $c_a/\text{vega}_a$, target $\sum_a(c_a/\text{vega}_a)P^{\mathrm{prior}}_a$, tolerance $1/\sqrt\lambda$. The same reform cured a long-standing asymmetry: the SVI and Multi-Core Sigmoid overlays, which previously received no prior at all, consume the same operator targets as the LQD path — one target, every model.

Figure 4 runs the whole argument through the production calibrator on a controlled experiment: yesterday's smile, today's truth the *same shape lifted by 4 vol points*, quotes only at the money. The operator rows (which cannot see the level) ride today's quotes and reconstruct the lifted wing to 0.3 vol points at $k=-0.20$; the per-strike price anchors of "The same principle in coverage currency" cling to yesterday's absolute wing — 3.7 vol points below today's truth, and only 3.3 from yesterday's un-jumped curve. Meanwhile the at-the-money fit under the operator prior matches the data-only fit to 0.00 vol points (factors: 0.00) — the dead zone holding in a live calibration.

> **Figure 4 — Coordinates decide what gets damped (figure not included in this pack).** Coordinates decide what gets damped (production calibrator, a controlled 4-point overnight level jump, quotes only in the shaded band). The operator prior — shape baskets that annihilate the level direction (Proposition 3) — rides today's level and lands on the lifted truth; the strike anchor — absolute price rows — pins the unquoted wing to yesterday's curve. The kink in the strike-anchor fit on the call side is the same cling on the other wing, where the anchors pull below today's smile. *Description:* The panel draws four smiles against log-moneyness: yesterday's prior curve, today's truth (the identical shape lifted by 4 vol points), and the two refits — operator-prior and strike-anchor — with today's quotes confined to a shaded at-the-money band. The operator-prior fit tracks today's lifted truth across the unquoted put wing to within 0.3 vol points at $k=-0.20$; the strike-anchor fit instead hugs yesterday's un-lifted wing, sitting 3.7 vol points below today's truth and only 3.3 from yesterday's curve, and shows a visible kink on the call side where its anchors pull below today's smile. Inside the shaded band all fits coincide with the data-only fit to 0.00 vol points — the dead zone in action.

**Exercise 3.** For the RR pair $c=(+1,-1)$ verify $\mathbf{1}\in c^{\perp}$ and compute the per-leg penalty of the level shift $t\mathbf{1}$ at weights $\lambda_1=\lambda_2=\lambda$: cost $2\lambda t^2$, gradient $2\lambda t$ per leg — a restoring force toward yesterday's level proportional to the jump. With $t=4$ vol points and the case-file budget this is the entire damping measured in Figure 4; the basket penalty's force along $\mathbf{1}$ is identically zero.

## 5. The same principle in coverage currency

The strike-gap mode is the older mechanism, and it answers the same question — where may the prior pull? — with a different measurement. Instead of pricing the precision of a functional, it measures a *density deficit* in strike space. With $\rho_{\mathrm{obs}}$ the Gaussian kernel density of today's quote locations (total mass the quote count, bandwidth $0.06$) and $\rho_{\mathrm{des}}$ a desired coverage of the same mass spread over the wider anchor span (uniform, or shaped by the prior's time value), each anchor strike $x_j$ — placed at the deltas $\{2,5,10,25,40\}\Delta$ through the Black delta map $k=\tfrac12\sigma^2\tau-\sigma\sqrt\tau\,\Phi^{-1}(c)$, with $\sigma$ resolved locally by a two-step fixed point — receives

$$
\text{weight}_j
=B_{\mathrm{sg}}\,
\frac{\big(\rho_{\mathrm{des}}(x_j)-\rho_{\mathrm{obs}}(x_j)\big)^{+}\,\Delta x_j}
{\sum_i\big(\rho_{\mathrm{des}}(x_i)-\rho_{\mathrm{obs}}(x_i)\big)^{+}\,\Delta x_i},
\qquad
u=\frac{\sum_i(\cdots)^{+}\,\Delta x_i}{\text{desired mass}},
\tag{7}
$$

with $\Delta x_j$ the anchor's Voronoi cell width, so each weight is the missing quote mass in its cell. The residual is the vega-normalized *call-price* difference at $x_j$ — the same form as the data block, so it reads as a vol error — with the deep-wing $1/\text{vega}$ capped at $25\times$ its minimum so a vanishing tail vega cannot let one anchor amplify noise unboundedly. Where quotes already meet the desired density the deficit is zero: the same "off where the data speaks" behaviour as Definition 1, expressed as coverage rather than precision, and never multiplied by a prior confidence. The companion var-swap pull is scaled by the unmet fraction $u$: a fully covered smile persists nothing, including its var-swap level. On the running SPY morning, $u=48\%$ — half the desired coverage is missing, all of it in the wings, and Figure 5, panel A, shows the budget landing exactly there.

> **Caution.** The two mechanisms persist different *things*. Strike-gap rows anchor absolute call prices: if the whole vol level jumps overnight, an unquoted wing is pulled toward yesterday's *absolute* wing — correct when the level is stable, wrong across a jump (Figure 4, measured: 3.7 vol points of miss). Operator and factor rows anchor level-invariant shape — RR, BF, curvature are unchanged by $\sigma\mapsto\sigma+c$ — so the persisted wing rides today's level. This is why the shipped default carries the shape on operators and reserves strike anchors for the deep tail no operator covers (see "The policy layer: seven modes").

> **Figure 5 — Both mechanisms placing their budget (figure not included in this pack).** Both mechanisms placing their budget, computed by the production builders. A: the strike-gap deficit of equation (7) on the running SPY morning — anchors inside the quoted band get zero budget; the deep put anchors get most of it (unmet fraction 48%). B: the operator gate on the case-file jump market — ATM is identified (gate closed, dropped from the target), the butterfly is closed by its easier information price (Remark 1), and the budget concentrates on the open risk-reversal and var-swap rows. *Description:* Panel A is a bar chart of the strike-gap anchor weights of equation (7) across the anchor strikes of the running SPY morning: the anchors that fall inside the quoted band carry zero weight (their density deficit is zero), while the deep put-side anchors absorb most of the budget; the unmet coverage fraction reads 48%. Panel B renders the operator-gate diagnostic on the case-file jump market as per-operator bars of gate value and allocated weight $\lambda_j$: ATM's gate is 0.00 (identified, dropped), BF25's gate is closed by its four-fold cheaper information price, and the surviving budget concentrates on the open RR25 and var-swap rows.

## 6. The policy layer: seven modes

Everything so far is machinery; the mode is policy. The single source of truth is `priorPersistenceMode` (the legacy `autoLoadPrior` toggle is retired; a saved settings blob from the old world migrates to `strike_gap` or `off`, and new installs default to `hybrid`). A resolver maps the mode to plan flags consumed by every fit path:

| Mode | overlay | strike | operators | factors | tail |
|---|:---:|:---:|:---:|:---:|:---:|
| `off` | | | | | |
| `overlay` | ✓ | | | | |
| `strike_gap` | ✓ | ✓ | | | |
| `quote_operator` | ✓ | | ✓ | | |
| `smile_factor` | ✓ | | | ✓ | |
| `hybrid` (default) | ✓ | | ✓ | | ✓ |
| `graph_only` | ✓ | | | | |

`graph_only` routes the prior exclusively into the graph baseline of Note 14 — dark nodes receive propagated innovations, no direct anchor rows. The `hybrid` *tail anchor* is the strike-gap machinery restricted to the deltas strictly below the shallowest active wing operator (here $\{2/5/10\}\Delta$; fallback $\{2,5\}\Delta$ when the operator set has no wing operator), at its own budget. Figure 6 draws the resulting division of labour on the running node: quotes own the level, operators carry the shape as far as their legs reach, strike anchors hold the tail beyond — each mechanism confined to the directions the previous one leaves flat.

> **Figure 6 — The hybrid division of labour (figure not included in this pack).** The hybrid division of labour on the running SPY node (production leg and anchor placement). Inside the quoted band every gate closes and the data rules. The $25\Delta$ operator legs carry yesterday's shape onto today's level. The tail anchors — the strike-gap machinery restricted to $\{2/5/10\}\Delta$ — hold the deep wing that no shape operator reaches. *Description:* The figure lays the running SPY smile over an annotated strike axis divided into three regimes: the shaded quoted band, where every activation gate is closed and today's quotes fully determine the fit; the intermediate region out to the $25\Delta$ operator legs (marked on the curve), where the RR25/BF25 shape baskets transport yesterday's smile shape onto today's level; and the deep tail beyond, where the hybrid's strike-gap anchors at the $\{2,5,10\}\Delta$ locations (also marked) hold the wing that no shape operator reaches. The visual point is complementarity: each mechanism's markers occupy exactly the region the previous one leaves flat.

### 6.1 Two-pass activation

The sharpest observation precision is the *realized* one — how well each operator is actually pinned by the fit — which is a chicken-and-egg with the fit the prior modifies. The opt-in `priorDataOnlyPrepass` resolves it exactly: fit once on data alone, measure each operator's realized precision, refit with priors active only on the genuinely under-observed coordinates. It is the most faithful no-damp behaviour at ${\sim}2\times$ cost per node; the default single pass gates on quote support, equation (4), with no extra fit, and "What the proxy cannot see" is the honest account of the difference.

**Remark 3 (The filter already carries yesterday: auto-exclusion).** When the observation filter of Note 15 runs in `active` mode, its Kalman prediction *is* a prior on the ATM level and local shape — yesterday's state, propagated. Anchoring the same coordinates to the persisted prior as well would count yesterday twice, so the resolver drops every overlapping builder — operators, factors, the near-ATM strike anchor — and keeps exactly what the filter state does not carry: the deep-tail strike anchor (for any mode that had a calibration prior) and the graph's dark-node baseline. There is deliberately no knob; the exclusion is test-locked (Appendix C, Traceability).

## 7. The prior must arrive in today's chart

A prior fitted at yesterday's forward may not be compared to today's smile raw — the comparison itself must happen in today's coordinates. The stored prior's LQD backbone (the canonical persisted object per expiry) is *transported* to the current forward under the active spot-dynamics regime of Note 12, with $h=\log(F_{\mathrm{now}}/F_{\mathrm{prior}})$ the move; every operator, factor and anchor target above is evaluated on the transported smile. The regime matters: under sticky-strike and sticky-local-vol the same stored surface yields different transported priors, and the persistence layer inherits whichever dynamics the desk has chosen — one more reason the prior's job is confined to the flat directions, where the transport error has no data to contradict it.

Provenance is part of the contract. A snapshot stores, per expiry, the LQD backbone plus the displayed-model parameters, forwards, discounts and both clocks $(\tau,t)$; persistence is to the `VolStore` database with history; and the active prior carries a provenance source (`saved` / `15min` / `close` / `none`) and a per-ticker monotone version that busts the fit cache — a fetched prior can never silently coexist with fits made under the old one.

One provenance rule outranks the others, because it guards the loop this note's own machinery invites. *Graph output is never prior input*: only lit nodes with an actual calibration record enter a prior snapshot, and a dark node's graph-extrapolated surface can never become a later transported-prior baseline. The rule matters most where the temptation is greatest — `graph_only` mode routes the prior into the graph baseline of Note 14, and without this filter the loop would echo: today's extrapolation would seed tomorrow's prior, which seeds the next extrapolation, and the graph would gradually be listening to itself. In this note's language, the prior may speak only where today is silent — and a surface that was itself inferred from neighbours has nothing of its own to say. The invariant is certificate-locked (the prior-save guard).

## 8. Reading the gates: diagnostics

A prior that acts silently is a prior that gets blamed for everything. Persistence is therefore *inspectable*: per node, `GET /smiles/{ticker}/{expiry}/prior-diagnostics` answers "is the prior pulling here, and how hard?" without reading code:

| Field | Type | Meaning |
|---|---|---|
| `mode` / `active` | str / bool | Resolved mode; whether any prior row is live on this node. |
| `operators[]` | list | One row per operator (active *and* gated-off). |
| — `operator` | str | ATM / RR25 / BF25 / VarSwap / factor name. |
| — `priorValue` | float | The operator on the transported prior. |
| — `obsPrecision` | float | Quote support, equation (4). |
| — `requiredPrecision` | float | The gate threshold in force. |
| — `gap` | float | The gate, equation (2): $0$ = off, $1$ = full pull. |
| — `activeLambda` | float | The LSQ weight, equation (5), actually applied. |
| `varSwapPriorVol` / `varSwapWeight` | float | The var-swap pull, if active. |
| `strikeAnchorCount` | int | Tail/strike anchors in force. |

The endpoint is best-effort — it reports *inactive* rather than failing — and drives the frontend persistence panel, whose table shows the same gap and $\lambda$ columns. Figure 5 is precisely this diagnostic rendered for the two shipped mechanisms.

## 9. What the proxy cannot see

The gate is only as honest as its precision measure, and quote support is a proxy, not the Fisher information. Its blind spot has a sign: the Gaussian kernel of equation (3) credits a leg with support from quotes up to a bandwidth away, so support *overstates* identification just beyond the last quote — precisely the region a wing prior exists to protect. The requirement $\pi_{\mathrm{req}}=1$ reads "one effective quote suffices," and a dense at-the-money cluster radiates enough kernel mass to satisfy it well outside the band.

The running character measures the consequence. On this node the $25\Delta$ legs sit at $k=0.06$ and $k=-0.08$ — inside the morning's quoted band — so on the dense morning every vol-operator gate closes (ATM 0.00, RR25 0.00, BF25 0.00), and even on a 5-quote skeleton of the same band they stay closed; only the var-swap probe, which reaches $1.4$ ATM standard deviations into the wings, remains under-observed (gate 0.57 on the sparse morning). The pure operator modes are therefore *inert* on liquid mornings: their rows never enter the optimizer, and the fit is the prior-free fit — which the temporal backtest of "Evidence" confirms at scale, showing exactly zero median improvement for both pure basket modes. The blind spot is why the hybrid's tail anchor is not a refinement but a necessity: the strike-gap deficit measures coverage *against a desired span* rather than radiated kernel mass, so it stays open in the wings that support declares covered.

Two honest escapes exist. The two-pass prepass ("Two-pass activation") replaces the proxy by the realized precision of a data-only fit — exact, at twice the cost, and opt-in. And the graph baseline of Note 14 prices the prior with the full vocabulary of equation (6) rather than support alone. What ships as the default is a calibrated compromise: proxy gates for the cheap common case, deficit anchors where the proxy is blind, and the exact pass available where a node justifies the spend.

## 10. Evidence

### 10.1 Worked example: the running node, wing withheld

The protocol isolates the mechanism. Take the running SPY node's stored full-chain fit as the prior; keep only the 30 quotes with $|k|\le0.10$ as "this morning"; withhold the other 71 real quotes; refit market-only and hybrid through the production calibrator; score both against what was withheld. Figure 7 shows the result, and the two error numbers the protocol was designed to separate: on the *retained band* the hybrid fit sits 2 vol bp rms from the quotes — the prior has not damped the data it was given — while on the *withheld wing* the market-only fit drifts 90 vol bp rms from the real quotes and the hybrid fit 42. Because the prior here is the same-day full fit, this is a mechanism test, not a forecast: it certifies that the gates route yesterday's information into exactly the coordinates the morning left dark. The forecast test — where the prior is genuinely yesterday's — is the second case file below.

> **Figure 7 — The hero protocol on the running SPY node (figure not included in this pack).** The hero protocol on the running SPY node (production fits throughout). Retained band (shaded): hybrid refit 2 vol bp rms from the quotes — no damping. Withheld wing (open markers): market-only 90 vol bp rms, hybrid 42 — the gap is filled with the prior's wing, visible on the call side where the market-only fit misses the upturn entirely. *Description:* The figure shows the SPY smile with the 30 retained at-the-money quotes as filled markers inside a shaded band and the 71 withheld quotes as open markers in the wings; over them run the market-only refit and the hybrid refit. Inside the band both fits thread the quotes (hybrid rms 2 vol bp — the dead zone means no damping). In the withheld wings the market-only fit drifts away from the open markers (90 vol bp rms) and visibly misses the call-side upturn, while the hybrid fit, carrying the prior's wing through operators and tail anchors, stays at 42 vol bp rms from quotes it never saw.

### 10.2 Case file: the jump the strike anchor damped

> **Case file — the jump the strike anchor damped.**
>
> **Setup.** The controlled experiment of Figure 4, which is the runnable form of the production no-damp test: a $\tau=0.5$ node, an overnight level jump of 4 vol points with the shape unchanged, today's quotes dense at the money and absent in the wings. Operator prior (ATM/RR25/BF25) versus the strike-gap anchor, both through the production calibrator.
>
> **Failure mode.** The strike anchor pins the unquoted wing to yesterday's absolute wing vol — after a level jump, the *wrong* wing: it undershoots today's true (lifted) wing and drags the nearby smile with it.
>
> **Diagnosis.** Proposition 3: per-strike price rows penalize the level direction $\mathbf{1}$; RR/BF baskets are invariant under it. The gate also drops ATM automatically — its quote support exceeds the requirement — so the operator target contains no row that could damp the level (Proposition 1 in action), and on this market it drops BF25 too (Remark 1), spending the whole budget on the risk-reversal.
>
> **Fix.** Persist shape, not level: the operator rows carry yesterday's skew onto today's level, and the wing is reconstructed as "today's ATM $+$ yesterday's shape".
>
> **Verdict (test-locked, measured this build).** At $k=-0.20$ the operator prior lands 0.3 vol points from the true jumped wing; the strike anchor misses it by 3.7 and sits 3.3 from yesterday's curve — still clinging. The operator and factor fits match the data-only ATM to 0.00 and 0.00 vol points: no damping. *Coordinates that separate what the data measures from what it does not are not a convenience; they are the difference between filling a gap and fighting the tape.*

### 10.3 Case file: the backtest that confirmed the default

> **Case file — the backtest that confirmed the default.**
>
> **Setup.** The temporal harness over the stored August-2024 spike regime: for each asset and day pair $T{-}1\to T$, fit day $T{-}1$'s full chain, freeze it as the active prior, thin day $T$ to its ATM region, refit under each mode, and score the reconstructed held-out moderate wing against day $T$'s true quotes; `off` is the baseline. 1116 node-days per mode; the stored artifact is read, never re-run.
>
> **Verdict.** Figure 8: the shipped **hybrid** default reconstructs the held-out wing $\sim$32 vol bp better than no prior at the median, winning 66% of node-days; strike-gap is a close second (28 bp, 63%). The *pure* basket modes do not beat `off` at the median — their win rates (30% and 34%) are below coin-flip and their median improvement is exactly zero, the inertness of "What the proxy cannot see" at scale: with the wing dark but the band dense, the proxy closes their gates and the fit is prior-free. The recorded knob sweep from the same campaign found neither the kernel bandwidth nor the var-swap probe a productive lever; both stayed at their defaults (the atlas rows `DEFAULT_BANDWIDTH` and `_VARSWAP_PROBE_STD`).
>
> **Lesson.** The backtest *confirmed* rather than changed the configuration: operators to avoid damping (previous case file), the tail anchor to actually rebuild a dark wing. *Neither component suffices alone; the composite does — and the failure of the pure modes is not noise but the measured shadow of the proxy's blind spot.*

> **Figure 8 — The stored temporal adjudication (figure not included in this pack).** The stored temporal adjudication (1116 node-days per mode, spike regime; improvements clipped to $[-200,400]$ bp for display). A: distribution of held-out wing improvement over no prior. The vertical mass at zero for the pure basket modes is inertness, not mediocrity: their gates close and the fit is byte-identical to `off`. B: medians with win rates — hybrid 32 bp at 66%, strike-gap close behind, the pure modes at zero. *Description:* Panel A shows, per persistence mode, the distribution (clipped to $[-200,400]$ bp for display) of held-out wing improvement relative to the no-prior baseline across the 1116 node-days of the August-2024 spike regime; the hybrid and strike-gap distributions sit visibly right of zero, while the pure operator and pure factor modes concentrate a vertical spike of mass exactly at zero — their gates closed, so those refits were byte-identical to `off`. Panel B condenses each distribution to its median improvement annotated with its win rate: hybrid 32 bp at 66%, strike-gap 28 bp at 63%, and both pure basket modes at a median of exactly zero with win rates of 30% and 34% — below coin-flip.

## 11. What is genuinely original here

The Bayesian framing is standard [Gelman2013]; the contributions are operational. The *activation gate*, equation (2), turns "do not damp the signal" into one differentiable factor with a provable dead zone (Proposition 1) — gating where the literature reaches for shrinkage. The *harmonic basket support*, equation (4), prices the identifiability of a combination rather than of legs, with the dead-leg law and the RR/BF factor-of-four (Remark 1) as measurable consequences. The *signed-basket coordinates* preserve exactly the level direction per-leg persistence would damp (Proposition 3) — the theorem behind the measured case file, and the reform that cured the SVI/MCS missing-prior asymmetry. The *shared vocabulary* keeps the persistence gate and the graph baseline of Note 14 speaking one identifiability language under golden re-export tests. And the whole framework is strictly additive: mode `off` is byte-identical to a plain fit, so the prior can be adopted, audited and abandoned per node without residue.

## 12. Limitations

Where the guarantees stop. *The information model is diagonal* (Assumption 1): support prices legs independently, ignoring the covariance a smooth smile induces between neighbouring strikes, and `priorOperatorCovarianceMode` accepts `full`, which busts the fit cache and changes nothing else — only the diagonal covariance is ever built or persisted. *The proxy overstates coverage near the band edge* ("What the proxy cannot see"); the exact remedy costs a second fit and is opt-in, and the shipped compensation is a second mechanism, not a sharper measure. *One scalar requirement governs all operators*: a per-operator $\pi_{\mathrm{req}}$ schedule is declared in the design and not implemented. *Strike anchors are wrong across level jumps* by construction (Figure 4); the hybrid confines but does not eliminate them — across a jump, the deep tail is still pulled toward yesterday's absolute prices. *The gate is heuristic identifiability, not inference*: nothing estimates the actual posterior variance of a persisted coordinate, and $\gamma$, $\pi_{\mathrm{req}}$ and the budgets are set by judgment plus the backtest, not by any optimality criterion. *Persistence is per-node*: nothing here couples expiries or assets — propagating a lit node's innovation to a dark neighbour is the graph's job (Note 14), which is why `graph_only` exists. A lecture that sells a mechanism without drawing its boundary is an advertisement; the boundary here is one honest sentence: *the gate keeps yesterday out of what today measured, to the accuracy of a kernel proxy for "measured".*

## Appendix A. Hyperparameter atlas

The only home for settings names: the body speaks mathematics, this table speaks configuration.

**Table 2 — Prior-persistence hyperparameters.**

*Surfaced (options settings)*

| Knob | Default | Role |
|---|---|---|
| `priorPersistenceMode` | `hybrid` | The mode selector ("The policy layer: seven modes"); sole gate — `autoLoadPrior` is retired (migration only). |
| `priorAnchorWeightPct` | $50$ | Strike-gap budget (% of summed quote weights). |
| `priorAnchorDeltas` | $\{2,5,10,25,40\}\Delta$ | Delta locations for strike anchors. |
| `priorOperatorSet` | ATM, RR25, BF25, VS | Operators to persist (registry also knows RR10, BF10). |
| `priorOperatorStrengthPct` | $50$ | Operator budget. |
| `priorOperatorRequiredPrecision` | $1.0$ | Gate threshold $\pi_{\mathrm{req}}$ (one scalar for all operators). |
| `priorOperatorGapExponent` $\gamma$ | $1.0$ | Gate sharpness. |
| `priorOperatorBandwidth` $b$ | $0.06$ | Quote-support kernel bandwidth; also the factor stencil step. |
| `priorOperatorCovarianceMode` | `diagonal` | Declared `diagonal`/`full`; `full` is cache-key only — it busts fits and changes nothing else, only the diagonal covariance is ever persisted. |
| `collarSign` | `call_put` | RR orientation ($\pm(\sigma_c-\sigma_p)$). |
| `priorFactorSet` | ATM, skew, curv, VS | Factors to persist. |
| `priorFactorStrengthPct` | $50$ | Factor budget. |
| `priorTailAnchorStrengthPct` | $20$ | Hybrid deep-tail anchor budget. |
| `priorDataOnlyPrepass` | `false` | Two-pass activation ("Two-pass activation"). |

*Hidden (persistence path)*

| Knob | Default | Role |
|---|---|---|
| `DEFAULT_BANDWIDTH` | $0.06$ | Strike-gap KDE bandwidth. |
| `MAX_INV_VEGA_RATIO` | $25$ | Cap on deep-wing $1/\text{vega}$ amplification. |
| `_VARSWAP_PROBE_STD` | $1.4$ | Var-swap coverage probe half-width (ATM std units). |
| `_WING_MULT` | $3$ | Factor wing stencils at $\pm3b$. |
| `_VOL_TOL` (LV) | $0.01$ | Vol tolerance behind LV basket/var-swap tolerances. |

*Hidden (shared vocabulary; consumed by the graph baseline, Note 14)*

| Knob | Default | Role |
|---|---|---|
| `RMS_FLOOR` | $10^{-4}$ | Fit-quality precision floor (1 vol bp). |
| `REF_ATM_QUOTES` | $8$ | Density credit saturation. |
| `MIN_DENSITY_FACTOR` | $0.15$ | Density credit floor. |
| `SPREAD_HALF` | $0.05$ | Relative spread at which precision halves. |
| `OBS/PRIOR` freshness half-lives | $3$ / $30$ d | Observation / prior age decay. |
| `TRANSPORT_SCALE` | $0.10$ | Transport-distance decay scale. |

## Appendix B. Performance notes

The prior blocks add a handful of constant-length residual rows — constant so the numeric Jacobian's sparsity never changes shape — and the single-pass gate is free: it reuses the quote locations the fit already holds, and equations (3)–(5) cost $O(\#\text{quotes}\times\#\text{legs})$ kernel evaluations per node. The two-pass prepass costs ${\sim}2\times$ per node and is opt-in. Every prior knob bumps the options version (one refit on change), and a fetched prior busts the fit cache through its monotone version ("The prior must arrive in today's chart") — correctness spends, speed defaults. Mode `off` is byte-identical to a plain fit, so the entire feature has zero cost when idle. The temporal-backtest numbers of "Evidence" are read from the stored artifact (`spike_aug2024_temporal_prior.json`); no benchmark in this note was re-timed. Figures and macros were generated at commit `652da29` on 2026-07-19.

## Appendix C. Traceability

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

**Table 3 — Claims in this note and the code/tests that lock them.**

| Claim | Object | Code anchor | Test anchor |
|---|---|---|---|
| Echo-free prior save: graph output never becomes prior input | "The prior must arrive in today's chart" | `volfit/api/priors.py` | `test_graph_dynamic_production.py::test_prior_save_guard_graph_output_never_prior_input` |
| Gate: zero past requirement, monotone, $\gamma$ sharpens | Definition 1 | `calib/precision.py` | `test_precision_shared.py::test_gap_zero_when_well_observed`, `::test_gap_monotone_and_gamma_sharpens` |
| No-damp / byte-identical off | Proposition 1 | `calib/prior.py`, `api/prior_mode.py` | `test_prior_anchor.py::test_none_anchor_leaves_the_fit_byte_identical`, `test_prior_parametric.py::test_none_arguments_are_noops` |
| Operator math (RR sign, BF convexity) | Definition 2 | `calib/operators.py` | `test_operators.py::test_risk_reversal_sign_and_collar`, `::test_butterfly_positive_on_convex_smile` |
| Gate closes ATM on dense quotes, keeps wings | Proposition 2 | `calib/operators.py` | `test_operators.py::test_dense_atm_turns_off_atm_keeps_wings`, `::test_full_coverage_returns_none` |
| Budget splits across open gates | equation (5) | `calib/operators.py` | `test_operators.py::test_budget_splits_across_active_operators` |
| Factor stencils; hybrid tail below shallowest operator | Definition 3 | `calib/factors.py` | `test_prior_factors.py::test_factor_legs_stencils`, `::test_hybrid_tail_deltas_below_shallowest_operator` |
| Strike-gap deficit weights; vega cap | equation (7) | `calib/prior.py` | `test_prior_anchor.py::test_prior_targets_gating`, `::test_inv_vega_cap_bounds_tail_amplification` |
| Mode resolver; autoLoadPrior migration | "The policy layer: seven modes" | `api/prior_mode.py`, `api/settings_persist.py` | `test_prior_mode.py::test_resolver_flags_per_mode`, `::test_migration_legacy_autoloadprior_on` |
| Observation-filter auto-exclusion | Remark 3 | `api/prior_mode.py` | `test_filter_active.py::test_auto_exclusion_truth_table` |
| All models consume the prior (SVI/MCS asymmetry fixed) | "Choosing coordinates: why baskets" | `models/{lqd,svi_jw,sigmoid}/calibrate.py` | `test_prior_parametric.py::test_operator_prior_pulls_all_models_toward_prior_skew` |
| LV route emits signed baskets, not per-leg quotes | Proposition 3 | `api/prior_lv.py` | `test_prior_lv.py::test_rr_basket_is_a_signed_difference`, `test_prior_factors.py::test_factor_lv_targets_are_baskets` |
| No-damp under a level jump (case file) | "Evidence" | `calib/operators.py` | `test_prior_nodamp.py::test_operator_prior_follows_level_and_reconstructs_jumped_wing` |
| Diagnostics endpoint | "Reading the gates: diagnostics" | `api/routers/smiles.py` | `test_prior_diagnostics.py::test_diagnostics_endpoint_ok` |
| Vocabulary shared with the graph (no drift) | Remark 2 | `calib/precision.py`, `graph/precision.py` | `test_precision_shared.py::test_graph_reexports_shared_factors`, `::test_graph_design_point_unchanged` |
| Persistence round-trip; transported identity | "The prior must arrive in today's chart" | `api/priors.py`, `api/prior_transport.py` | `test_priors.py::test_priors_persist_across_restart`, `::test_transported_prior_identity_and_shift` |

## Appendix D. Reference implementation: the gated pipeline

The note's appendix distills the full single-pass pipeline — support, basket precision, gate, budget split, and the scalar posterior a gated row implements — as a short reference implementation. Per the transfer policy the pack carries no source code; the listing is replaced by the following exact algorithm specification, which carries every algorithmic detail. Executed against the production builders on the case-file market and a $\gamma$ sweep of the gate, the maximum discrepancy across gates, basket precisions and split weights is at most $1.0\times10^{-17}$ — exact in double precision; the formulas are the same arithmetic.

**Algorithm — the gated single-pass pipeline (verified against `calib/precision.py` and `calib/operators.py`).**

*Inputs:* live quote locations $\{k_q\}$ with fit weights normalized to mean one; leg locations $\{k_a\}$ per persisted basket; basket coefficient vectors $c$; kernel bandwidth $b$; gate requirement $\pi_{\mathrm{req}}$ and sharpness $\gamma$; mode budget $B$; per-coordinate prior means $\mu$ and (for the posterior identity) a datum $d$ at precision $\pi$.

*Steps:*

1. **Quote support per leg** (equation 3): for each leg $a$, form $z_{aq}=(k_a-k_q)/b$ and set $s_a=\sum_q e^{-z_{aq}^2/2}$ under the mean-one weights.
2. **Basket precision** (equation 4, the harmonic law): restricting the sum to the nonzero coefficients of $c$, $\pi(O)=\big(\sum_{a:\,c_a\neq0} c_a^2/(s_a+\varepsilon)\big)^{-1}$ with $\varepsilon=10^{-9}$.
3. **Activation gate** (equation 2): $g=\big(\mathrm{clip}(1-\pi/\max(\pi_{\mathrm{req}},10^{-12}),\,0,\,1)\big)^{\gamma}$.
4. **Budget split** (equation 5): $\lambda_j = B\, g_j/\sum_i g_i$; any coordinate with $g_j=0$ receives exactly zero weight and drops out of the target.
5. **Scalar posterior implemented by one gated row:** $(\lambda\mu+\pi d)/(\lambda+\pi)$. The two limits state the note's contract: $\lambda\to0$ (gate closed) gives posterior $d$ — no damping; $\pi\to0$ (data silent) gives posterior $\mu$ — the gap filled.

*Output:* per-coordinate gates $g_j$, basket precisions $\pi(O_j)$, active weights $\lambda_j$, and the gated posterior. Production-agreement tolerance: at most $1.0\times10^{-17}$ across all quantities on the case-file market and the $\gamma$ sweep.

## References

- [Gelman2013] A. Gelman et al. *Bayesian Data Analysis*. CRC Press, 3rd ed., 2013.
- [Gatheral2006] J. Gatheral. *The Volatility Surface*. Wiley, 2006.
- [LehmannCasella1998] E. Lehmann and G. Casella. *Theory of Point Estimation*. Springer, 2nd ed., 1998.
- [Tikhonov1977] A. Tikhonov and V. Arsenin. *Solutions of Ill-Posed Problems*. Winston, 1977.



