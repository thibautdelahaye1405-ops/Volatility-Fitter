# Base and Correction

**Note 03 — The Multi-Core Sigmoid: local body detail the wings never feel, and the budget that keeps it honest · lecture edition ("base and correction") · converted from 03_multicore_mcs_corrections.tex on 2026-07-29 · figures omitted, all measured numbers inlined.**

> **Abstract.** Note 02 was about the wings: a smile's tails are a moment reading of the risk-neutral law, and one convex hyperbola pins them cleanly. This note fixes the wings as a solved problem and asks the complementary question — how to add detail in the *body* of a smile without disturbing the tails at all. Some smiles are not convex: ahead of a binary event, or in bimodally-positioned names, the curve develops a WW shape (a central trough, a shoulder on each side). We prove that no globally convex slice can carry such a shape, so a hyperbola is structurally disqualified, and we build the answer by *superposition*: a convex log-cosh *base* owns the wings and the overall skew, and $R$ signed *corrections* add local humps or notches. The mathematical heart is a single fact — a centred second difference annihilates affine functions, and the log-cosh primitive is asymptotically affine, so each correction kernel and its first two derivatives vanish in both tails. The hats therefore reshape the body while leaving the base wing slopes *exactly* fixed: expressiveness and tail control are decoupled by construction. The model carries $6+4R$ parameters and a closed-form Durrleman diagnostic, and is fitted in three layered stages with an analytic Jacobian 2.36× faster than finite differences. The second half of the note is the cost of flexibility. A flexible model over-fits: on a WW target two cores cut the miss from 153.05 to 2.55 vol bp, but on a liquid smile a third core lowers the in-sample error while *raising* the true-curve error and manufacturing butterfly arbitrage out in the sparse wing. So the cores slider is governed — an identifiability cap, an amplitude ridge, a hard cap at two, and a default-on put-wing regularizer that is zero on any clean slice. The cores slider is a scalpel, not a default.

**Contents:** 1. Two jobs, one curve · 2. The base owns the wings · 3. A basis that vanishes in the tails · 4. The full model: superposition · 5. Static no-arbitrage · 6. Calibration · 7. Expressiveness on a budget · 8. Worked example: a WW smile · 9. What is original, and limitations · Appendix A. Hyperparameter atlas · Appendix B. Performance notes · Appendix C. Traceability · Appendix D. Reference implementation · References

---

## 1. Two jobs, one curve

A volatility smile does two jobs, and Note 02 did one of them. Far from the money the smile reports the *tails* of the risk-neutral distribution, and there one convex hyperbola — raw SVI — is enough: its two straight wings are a moment reading, capped by Lee's bound. Near the money the smile reports the *body*, the local shape around the forward, and there a hyperbola runs out of room. Some smiles are simply not convex.

**Proposition 1 (A convex slice cannot make a WW).** *If total variance $w(k)$ is convex on an interval, it has no interior strict local maximum there, hence no shoulder flanked by two troughs. A WW smile — a central trough with a shoulder (interior local maximum) on each side — can therefore not be represented by any globally convex slice, in particular by raw SVI, whose $w''>0$ everywhere.*

*Proof.* A convex function on an interval has non-decreasing one-sided derivatives; an interior strict local maximum would force the derivative to fall from positive to negative, contradicting monotonicity. Raw SVI has $w''=b\,s^2/r^3>0$ (Note 02), so it is strictly convex and admits a single minimum only. ∎

Figure 1 shows the situation. The convex base misses the two shoulders by 153.05 vol bp, and — the point of the whole note — the residual it leaves is *structured*: two localized shoulder features and a wing compromise, not white noise. A structured residual invites a structured correction. The design question is what that correction should be, and it has a sharp constraint: it must reshape the body without touching the wings, because the wings are the solved problem.

> **Figure 1 — Why one convex base is not enough (figure not included in this pack).** Panel A: a WW target (trough plus two shoulders); the convex base ($R=0$) tracks the overall V but misses both shoulders by 153.05 vol bp. Panel B: the base residual is structured — two shoulder features and a wing compromise — exactly the kind of thing a few *local* corrections can absorb. Panel A overlays the synthetic WW target slice on the best-fitting purely convex base: the base follows the overall V-shape of the smile but cuts straight under both interior shoulders, its worst miss being the quoted 153.05 vol bp. Panel B plots the base's residual across strike: rather than noise, it shows two localized positive humps sitting exactly at the two shoulder positions, plus a low-amplitude wing-level compromise between them — a structured pattern that motivates a structured, strictly local correction basis.

**Conventions and clocks.** Throughout, $k=\log(K/F)$ is log-moneyness and $v=\sigma_{\mathrm{imp}}^2$ is *annualized implied variance* — the quantity this model works in — while $w=\tau v$ is total variance. Here $\tau=\tau_T$ is the production *variance clock*, calendar time dilated by scheduled events (Notes 00, 11), equal to the calendar year fraction $t$ only when the event clock is off; production passes $\tau$ to the calibrator, and wherever a bare $t$ plays a time role below, read $\tau$. The $z$-scale reference $\sigma_{\mathrm{ref}}$ is the *quoted* volatility nearest the money (with a median-of-quotes fallback when that quote is degenerate); it is fixed before the fit and never optimized. A *volatility basis point* (vol bp) is $10^{-4}$ in volatility. One differentiation convention: a prime is the derivative of a one-variable function ($\Phi'$, $B'$, $v'$), a subscripted or explicit $\partial$ is a partial.

| Symbol | Meaning | First used |
|---|---|---|
| $k,\ z$ | log-moneyness; dimensionless log-strike $k/(\sigma_{\mathrm{ref}}\sqrt t)$ | equation (1) |
| $v(z)$ | annualized implied variance (the modelled quantity) | equation (4) |
| $w,\ \tau,\ t$ | total variance $\tau v$; variance clock; calendar fraction | §1 ("Two jobs, one curve") |
| $\sigma_{\mathrm{ref}}$ | reference vol fixing the $z$-scale | equation (1) |
| $\Phi_\kappa$ | log-cosh convexity primitive | equation (2) |
| $V_0,S_0,K_0,z_0$ | base level, slope, convexity, centre (at $z_0$) | equation (4) |
| $\kappa_P,\kappa_C$ | asymmetric put/call wing steepnesses | equation (4) |
| $B_{c,h,\kappa}$ | zero-wing hat: centre $c$, half-width $h$, steepness $\kappa$ | equation (6) |
| $\alpha_r,\ R$ | signed hat amplitude; number of cores | equation (7) |
| $g(k)$ | Durrleman density factor (butterfly diagnostic) | equation (9) |
| $\beta_P,\beta_C$ | $k$-space total-variance wing slopes | equation (8) |

*Table 1 — Notation ledger. Nothing is reused with a second meaning; $v$ is always variance, $\sigma$ always a volatility.*

> **Invariant.**
> 1. Adding cores never moves the asymptotic wings: every hat and its first two derivatives vanish in both tails (Lemma 1), so the base owns the wing slopes regardless of $R$.
> 2. Expressiveness is budgeted: cores are capped by the quote count (equation (11)) and the surfaced slider is clamped to two.
> 3. The model reports its own butterfly diagnostic $g$ per fit; it is *not* arbitrage-free by construction, and the put-wing hinge rows are exactly zero on any clean slice — penalty off is byte-identical, penalty on over a clean slice unchanged to solver tolerance. At the product boundary the same diagnostic acquires teeth: a dense traded-range certificate gates readiness and publish for the displayed slice, MCS included ("Static no-arbitrage").
> 4. The parameters are a means, not the object: hats are non-unique by design, and only the fitted *curve* is contractual ("Calibration").

> **Heuristic.** The correction must be *local*: it changes a bounded region of the body but must not alter the asymptotic wings, which liquid risk-reversals and Lee's law already pin. So the kernel must vanish — in value, slope, *and* curvature — in both tails. "Zero-wing" does not uniquely select a kernel (a Gaussian and its derivatives also vanish), but the centred second difference of the same log-cosh primitive the base uses is the convenient choice: model and Jacobian then share one set of analytic jets, the kernel is unit-height at its centre so its amplitude reads as a variance displacement, and its plateau width and shoulder steepness are separate dials ($h$, $\kappa$) where a Gaussian has only one.

## 2. The base owns the wings

Work in the dimensionless log-strike

$$
z=\frac{k}{\sigma_{\mathrm{ref}}\sqrt t},
\tag{1}
$$

so $z$ measures moneyness in standard deviations and the model is roughly scale-free across expiries. The convexity primitive is the *log-cosh*

$$
\Phi_\kappa(u)=\frac{4}{\kappa^2}\log\cosh\!\Big(\frac{\kappa u}{2}\Big),\quad
\Phi_\kappa'(u)=\frac{2}{\kappa}\tanh\!\Big(\frac{\kappa u}{2}\Big),\quad
\Phi_\kappa''(u)=\operatorname{sech}^2\!\Big(\frac{\kappa u}{2}\Big).
\tag{2}
$$

$\Phi_\kappa$ is a smooth, convex, even softened absolute value. Two facts about it carry the whole note. Near the origin $\Phi_\kappa(u)\approx u^2/2$ (a rounded vertex). Far out it is *asymptotically affine*,

$$
\Phi_\kappa(u)=\frac{2}{\kappa}\,|u|-\frac{4}{\kappa^2}\log 2+o(1),
\tag{3}
$$

a straight wing of slope $2/\kappa$ (Figure 2, panel A). For numerical safety the log-cosh switches to its exact asymptote $|x|-\log2$ beyond $|x|=50$ to avoid $\cosh$ overflow — clipping $x$ instead would freeze $\Phi$ constant and destroy the wing slopes.

The base slice and its $z$-derivatives are

$$
\begin{aligned}
v_{\mathrm{base}}(z)&=V_0+S_0(z-z_0)+K_0\,\Phi_{\kappa_i}(z-z_0),\\
v_{\mathrm{base}}'(z)&=S_0+K_0\,\Phi_{\kappa_i}'(z-z_0),\qquad
v_{\mathrm{base}}''(z)=K_0\,\Phi_{\kappa_i}''(z-z_0),
\end{aligned}
\tag{4}
$$

with the steepness switching $\kappa_i=\kappa_P$ for $z<z_0$ and $\kappa_C$ for $z\ge z_0$. The six parameters are the variance level $V_0$ *at the fitted centre* $z_0$, the slope $S_0$ there, the convexity amplitude $K_0\ge0$, the centre $z_0$, and the asymmetric put/call wing steepnesses $\kappa_P,\kappa_C$. Be precise about what $V_0,S_0$ are *not*: $z_0$ is fitted and generally $\ne0$, so they are not the ATM level and skew, and the corrections of the next section can move the full model's ATM handles besides — the displayed ATM level, skew and curvature always come from the full curve. Because $\Phi$ and $\Phi'$ both vanish at the origin, the slice is $C^2$ across $z_0$ even though the steepness switches there: the asymmetry is in the *rate* at which each wing straightens, not a kink. By equation (3) the asymptotic wing slopes are

$$
v_{\mathrm{base}}'(z)\to S_0\mp\frac{2K_0}{\kappa_{P,C}}\quad(z\to\mp\infty),
\tag{5}
$$

a left slope $S_0-2K_0/\kappa_P$ and a right slope $S_0+2K_0/\kappa_C$. These six numbers set the wings, and — the design goal — the corrections must leave them untouched.

## 3. A basis that vanishes in the tails

The correction kernel is the normalized centred second difference of the same primitive,

$$
B_{c,h,\kappa}(z)=\frac{\Phi_\kappa(u-h)-2\Phi_\kappa(u)+\Phi_\kappa(u+h)}{2\Phi_\kappa(h)},
\qquad u=z-c,
\tag{6}
$$

centred at $c$, of half-width $h$ and steepness $\kappa$, normalized so $B_{c,h,\kappa}(c)=1$. Its derivatives are the same second difference of $\Phi'$ and $\Phi''$ over the same normalizer. Now the one fact everything rests on.

**Lemma 1 (Zero wings).** *$B_{c,h,\kappa}(z)\to0$, $B_{c,h,\kappa}'(z)\to0$ and $B_{c,h,\kappa}''(z)\to0$ as $z\to\pm\infty$.*

*Proof.* A centred second difference annihilates affine functions: for any $L(u)=pu+q$, $L(u-h)-2L(u)+L(u+h)=0$ identically. By equation (3) $\Phi$ is affine plus $o(1)$ in each tail, so its second difference tends to $0$ there. The same argument applies to $\Phi'$ (which tends to the constants $\pm2/\kappa$, affine of zero slope) and to $\Phi''$ (which decays), so $B$, $B'$ and $B''$ all vanish in both tails. ∎

Lemma 1 is the whole design. Adding $\alpha B$ to the base changes the body but leaves the wing slopes of equation (5) *exactly* unchanged. The amplitude $\alpha$ is in variance units and, since $B(c)=1$, is approximately the variance displacement at the centre; a positive $\alpha$ raises a shoulder, a negative one digs a notch. The centre curvature $B''(c)=(\operatorname{sech}^2(\kappa h/2)-1)/\Phi_\kappa(h)<0$, so a positive hat is locally concave (a hump), as a shoulder should be. Figure 2 draws both halves of the mechanism.

> **Figure 2 — The mechanism, in two facts (figure not included in this pack).** Panel A: the log-cosh primitive is asymptotically affine — it merges with the straight line $\frac2\kappa|u|-\frac4{\kappa^2}\log2$ in both tails, differing only at the rounded vertex. Panel B: the centred second difference of an asymptotically-affine function is a localized bump whose value, slope *and* curvature all decay to zero. A correction built this way is silent in the wings to all three orders. Panel A plots $\Phi_\kappa(u)$ against its two-sided affine asymptote: the curve and the straight lines are visually indistinguishable except in a neighbourhood of the origin, where the log-cosh rounds the vertex of the absolute value. Panel B plots the hat kernel $B_{c,h,\kappa}$ together with its first and second derivatives: all three are compactly concentrated around the centre and decay to zero on both sides, illustrating the three-order tail silence Lemma 1 proves.

**Exercise 1.** Verify the annihilation directly: for $L(u)=pu+q$, expand $L(u-h)-2L(u)+L(u+h)$ and confirm it is identically zero. Conclude that *any* asymptotically-affine primitive — not just the log-cosh — yields a zero-wing kernel by the same second difference, and that the log-cosh is a convenience (shared jets, unit height, two dials), not a necessity.

## 4. The full model: superposition

**Central equation.** The Multi-Core Sigmoid (MCS) slice is the base plus $R$ signed corrections,

$$
v_R(z)=v_{\mathrm{base}}(z)+\sum_{r=1}^{R}\alpha_r\,B_{c_r,h_r,\kappa_r}(z),
\qquad w(k)=t\,v_R(z),
\tag{7}
$$

with $6+4R$ parameters. Figure 3 shows the decomposition on the WW fit: the convex base owns the V, and two signed hats add precisely the two shoulders, each localized. By Lemma 1 every member of this family has the *same asymptotic wings as its base*, whatever $R$ is — Figure 4 makes that visible, overlaying the base and the base-plus-hats: the bodies differ, the wings coincide, and the difference $\sum_r\alpha_r B_r$ decays to zero out of the money. Expressiveness in the body and control of the tails are, by construction, two separate concerns.

> **Figure 3 — Superposition (figure not included in this pack).** The convex base carries the overall V; each signed hat is a localized bump that adds one shoulder; their sum is the fitted slice. The hats live where the residual of Figure 1, panel B lived. The figure stacks the three ingredients of the two-core WW fit: the convex log-cosh base curve, the two individual signed hat contributions $\alpha_r B_r(z)$ drawn as localized bumps centred on the shoulder positions, and their sum — the full fitted MCS slice tracking the WW target. Visually, each hat occupies exactly the strike neighbourhood where the base residual of Figure 1 showed a structured feature, and is negligible elsewhere.

> **Figure 4 — The correction is local (figure not included in this pack).** Panel A: base and base-plus-hats differ in the body but their total-variance wings coincide exactly. Panel B: the difference $w_{\mathrm{full}}-w_{\mathrm{base}}$ is a bump that decays to zero in both tails (the put and call sides overlie), so the wing slopes are preserved pointwise, not merely on average. Panel A overlays the total-variance curves of the base alone and of the base plus both hats over a wide strike range: the two curves separate visibly through the body of the smile and then re-merge exactly in both wings. Panel B plots the difference of the two curves on a scale that shows it as a localized bump decaying to zero on both sides, with the put-side and call-side decay overlying each other — pointwise wing preservation, the visible form of Lemma 1.

There is one honest subtlety, and it is worth stating in Note 02's vocabulary. *Wing-neutral* is weaker than *Lee-compatible*. The hats preserve the base wing slopes, but nothing constrains those base slopes to be admissible in the first place. In total-variance $k$-space the wing slopes are

$$
\beta_P=\frac{\sqrt{\tau}}{\sigma_{\mathrm{ref}}}\Big(\frac{2K_0}{\kappa_P}-S_0\Big),\qquad
\beta_C=\frac{\sqrt{\tau}}{\sigma_{\mathrm{ref}}}\Big(S_0+\frac{2K_0}{\kappa_C}\Big),
\tag{8}
$$

and admissibility asks $0\le\beta_P,\beta_C\le2$ (upward wings under Lee's cap). The calibration bounds of "Calibration" do *not* enforce this: the hats guarantee the base slopes are *preserved*, and whether the preserved slopes are themselves Lee-clean is a separate, diagnosed condition (the cross-model wing treatment is Note 09).

The cores count $R$ is the user's "cores" slider — the direct analogue of the LQD Legendre order, the one dial that trades expressiveness for parsimony. The rest of the note is about reading that dial correctly.

## 5. Static no-arbitrage

Butterfly-freedom is the Durrleman condition, evaluated by converting the $z$-space variance and its derivatives to total-variance $k$-space via $k=\sigma_{\mathrm{ref}}\sqrt t\,z$ and $w=tv$:

$$
g(k)=\Big(1-\frac{k\,w'}{2w}\Big)^2-\frac{w'^2}{4}\Big(\frac1w+\frac14\Big)+\frac{w''}{2}\ \ge\ 0.
\tag{9}
$$

Unlike LQD, and unlike the base alone, *MCS is not arbitrage-free by construction*. A signed hat can drive the raw variance negative (there is no positivity penalty in the fit) or, more commonly, break convexity locally, so the equivalence "$g\ge0\iff$ non-negative density" comes with conditions worth stating: it presumes $v_R>0$, a smooth slice, and appropriate wings, and on a finite grid $g$ is a *diagnostic*, never a global certificate. That is a statement about the whole real line; on the traded range, a dense sampling of the same functional is exactly what production now enforces as a gate, and the distinction between the two scopes is drawn at the end of this section.

**Remark 1 (Which curve's $g$?).** Positivity and the floor interact in code. Pricing floors the variance at $10^{-8}$, and the reported diagnostic is the Durrleman functional of that *priced* (floored) curve: where the floor binds, the priced slice is locally constant, its derivatives are zero, and the separate raw-positivity check flags the slice as not butterfly-free. (An earlier revision mixed the floored *value* with the raw *derivatives* — a functional of no curve at all; fixed and test-locked.) The *penalty*-path $g$ inside the calibrator deliberately keeps the raw derivatives instead: at a collapsed-variance grid point the $1/w$ term then explodes negative, a harsh de-facto barrier against hats that drive variance through zero.

### 5.1 Where the arbitrage lives, and the put-wing regularizer

When cores over-reach they break equation (9) not near the money — where dense quotes discipline the curvature — but out in the sparsely quoted wings, where each hat's local curvature is unconstrained by data. The offline backtest localizes the violation sharply: across the audited over-parametrized spike-regime refits, about 64% of the $g<0$ points sit in the *put* wing (the steep, variance-loaded side of the equity skew) against only $\sim4\%$ near the money, with the worst point at a median standardized moneyness $z\approx-3.2$. To discipline that region the joint refine carries an optional *put-wing Durrleman penalty*: on a grid $\{z_j\}$ of $M=49$ points spanning the quoted range extended $\Delta z=2$ into both tails, it appends the rows

$$
r^{\mathrm{wing}}_j=\sqrt{\lambda_j}\,\max\!\big(-g(z_j),\,0\big),
\qquad \lambda_j=\Lambda\,\lambda_0\,\big(1+\mathbf{1}\{z_j<0\}\big),
\tag{10}
$$

with base strength $\lambda_0=1000$, surfaced dial $\Lambda=$ `sivWingPenaltyPct` $/100$ (product default $1$; $0$ disables), and the indicator *doubling* the weight on the put side to match the measured asymmetry. Because $\max(-g,0)=0$ wherever the slice is butterfly-free, equation (10) is exactly zero on an admissible fit: a liquid, arbitrage-free name is byte-identical with or without it. The penalty bites only where a hat would otherwise manufacture a wing violation.

Figure 5 demonstrates the penalty on a genuine over-reach. A convex truth is handed two arbitraged put-wing quotes (a localized non-convex kink of the kind a per-strike de-Americanization can produce, Note 05); a hat chases the kink and drives $g$ to −2.45 in the put wing. The same quotes refit with the penalty on are pulled back to the admissible boundary ($g\ge-0.03$) — at the cost of fitting the arbitraged quotes less, which is the right trade.

> **Figure 5 — The put-wing penalty (figure not included in this pack).** Panel A: with the penalty off, a hat chases two arbitraged put quotes and breaks convexity, $g\to-2.45$ in the put wing (the positive spike is the local hump the kink induces; the $y$-axis is clipped to the violation). Panel B: with the penalty on, the fit is pulled back to $g\ge-0.03$ there, fitting the bad quotes less. The hinge is one-sided and zero wherever $g\ge0$. Panel A plots the Durrleman function of the unpenalized fit across standardized moneyness: it dips to −2.45 in the put wing where the hat has chased the two arbitraged quotes, and a positive spike marks the localized hump the injected kink induces. Panel B shows the same functional for the penalized refit: the deep negative excursion is gone, the minimum sitting at −0.03 — essentially the admissible boundary — while the fit concedes some accuracy on the two bad quotes.

> **Heuristic.** The penalty is a one-sided hinge on the same $g$ the model already reports. Although its grid covers the quoted region too, it *bites* only where the model extrapolates: where quotes are dense they discipline the curvature, so $g\ge0$ there and the rows are zero. It does not *guarantee* $g\ge0$ (a soft penalty trades the violation against the data fit), but on genuinely arbitraged illiquid wings it shrinks the worst violation by orders of magnitude — the backtest measured a median wing $\min g$ moving from $\approx-7.9$ to $\approx-0.02$.

Beyond the core diagnostic and this penalty, three further layers stand at increasing distance from the fit. An always-on advisory measures the remaining extrapolated-region $g<0$ per fit. An export-only wing projection raises exported prices to convexity while leaving the fitted core pinned (Note 09). And — the layer with teeth — every slice a user sees is re-measured by the display *certificate*: Durrleman's $g$ from the analytic jets, sampled at 801 points across the traded strike range with tolerance $g\ge-10^{-4}$; a failing slice fails readiness, and the publish gate refuses the surface outright. The certificate is a statement about the sampled grid on the traded range, no more — but within that scope it is binding, for MCS exactly as for the other families. What MCS does *not* yet have is the automatic certified *repair* refit that SVI runs when its certificate fails; that asymmetry is an open rider, and until it closes the fitter's defences here are the calibration bounds, the amplitude ridge, the put-wing regularizer, and the certificate's hard gate itself.

## 6. Calibration

The fit is a three-stage workflow that respects the model's layered structure.

1. **Base fit ($R=0$).** Fit the six base parameters to the mid quotes under bound constraints, from a data-driven start that reads the ATM variance, the local skew and the local convexity off three interpolated points. This stage is always mid, so its residual is meaningful for the next.
2. **Greedy hat seeding.** Compute the base residual in variance space and place each hat at the largest remaining $|\text{residual}|$, masking a neighbourhood after each placement so two hats cannot seed on one feature. Each seed starts at half-width $h=0.40$ and steepness $\kappa=5.0$, its amplitude read from the local residual and clipped to $[-1,1]$.
3. **Joint bounded refine.** Refine all $6+4R$ parameters together under the requested objective (mid or band) with a mild ridge $\sqrt{\varrho}\,\alpha_r$ on the hat amplitudes, $\varrho=0.01$. The ridge keeps overlapping cores from exploding against each other without biasing a well-determined amplitude.

All positive parameters ($K_0$, the steepnesses, the hat half-widths and steepnesses) are bound-constrained directly through scipy's trust-region reflective solver, the hat half-width held in $[0.15,1.5]$ and its steepness in $[1.0,12.0]$.

**The identifiability cap.** The cores count is capped by the quote count,

$$
R\le\Big\lfloor\frac{N_{\mathrm{quotes}}-6}{4}\Big\rfloor,
\tag{11}
$$

so the model never has more free parameters than quotes, guarding sparse short-dated chains against spurious narrow kernels. Be precise about what this does and does not prevent: it caps only the *hats*, so with $N_{\mathrm{quotes}}\ge6$ it stops under-identified hats — but the application's minimum of five included quotes per node means the six-parameter base can still be fitted to five quotes (one parameter over the data; the bounds and the data-driven start keep it tame, but it is not a guarantee).

**The hard cap, and non-unique hats.** Independently of equation (11), the surfaced slider is *hard-capped at two*, $R\in\{0,1,2\}$: "Expressiveness on a budget" shows a third core buys almost nothing out-of-sample while manufacturing wing arbitrage, so any incoming setting above two is silently clamped. Precision matters: the clamp lives in the *schema*, not the calibrator — the library `calibrate_sigmoid(n_cores=3)` runs happily and its tests exercise it. The cap is a product decision at the settings boundary; research code below it keeps the full family. Relatedly, the hats are *non-unique* by construction: two overlapping hats can trade amplitude against each other, so the round-trip test recovers the *curve*, not the parameters, and nothing downstream ever consumes a hat parameter. The individual $(\alpha_r,c_r,h_r,\kappa_r)$ are not trader handles.

The refine stage carries the same optional blocks as the other models — band fit (Note 07), var-swap target (Note 08), the model-agnostic calendar hinge (Note 10), prior persistence (Note 13), the put-wing regularizer of equation (10), and the default-off tapered extrapolated-region fences (Notes 09–10) — each byte-identical to its own absence, so the sigmoid overlay is no longer a prior exception. The one block MCS does *not* get is the automatic certified belly repair that SVI runs when the display certificate fails — the open rider of "Static no-arbitrage".

> **Performance.** The dominant cost of an $R$-core fit is the $(6+4R+1)$-evaluation finite-difference Jacobian. The closed-form Jacobian of the residual stack (data $+$ ridge $+$ calendar), propagated through the log-cosh primitive, replaces it in one pass: a fresh run measured 161.3 ms $\to$ 68.3 ms (2.36×), optimum unchanged to $1.5\times10^{-15}$ in cost. Scope of that number — it is the $R=2$ mid *final-refine* microbenchmark alone (base fit, seeding and the product-default wing penalty excluded), single-threaded, not an end-to-end calibration timing. The analytic path is gated to the var-swap/prior-free configuration. When the wing penalty of equation (10) or the extrapolation fences are active the Jacobian is *hybrid*: analytic for the data/ridge/calendar rows and finite-difference only for the small penalty blocks, so the penalized fit keeps most of the analytic speed. See Appendix B ("Performance notes").

> **Figure 6 — Analytic-Jacobian timing (figure not included in this pack).** The closed-form Jacobian through the log-cosh replaces the $(6{+}4R{+}1)$-evaluation finite difference on the $R=2$ final refine (2.36× here; machine-dependent, protocol in Appendix B "Performance notes"). The figure is a two-bar timing comparison of the $R=2$ mid final-refine microbenchmark: the finite-difference Jacobian path at 161.3 ms against the analytic path at 68.3 ms — a 2.36× speedup with the optimum unchanged to $1.5\times10^{-15}$ in cost.

**Exercise 2.** The centre curvature is $B''(c)=(\operatorname{sech}^2(\kappa h/2)-1)/\Phi_\kappa(h)$. Show it is strictly negative for every $h,\kappa>0$, and deduce that a positive amplitude always produces a local hump and a negative amplitude a local notch — so the *sign* of $\alpha_r$ is the only thing a reader needs to know a core's qualitative effect.

## 7. Expressiveness on a budget

A flexible model has two failure modes, and MCS shows both cleanly. Too few cores and it *underfits*: on the WW target one convex base leaves a 153.0 vol bp miss, and — because a single off-centre hat cannot address two symmetric shoulders — one core barely helps (154.7 bp); only at $R=2$ does the error collapse, to 2.5 bp (Figure 7, panel A). Too many cores and it *over-fits*: on a liquid, genuinely convex smile fitted to noisy quotes, each extra core drives the in-sample error down but the error against the *true* curve up — from 23.9 vol bp at $R=0$ to 37.7 bp at $R=3$, the classic bias–variance scissor (Figure 7, panel B). The cores are chasing quote noise.

> **Figure 7 — The two failure modes of the wrong core count (figure not included in this pack).** Panel A (a WW smile): too few cores is bias — the error stays near 153.0 vol bp until two hats can seat both shoulders, then collapses; a third buys nothing. Panel B (a noisy liquid smile): too many cores is variance — the in-sample error keeps falling while the true-curve error rises, the signature of over-fitting. The right core count is neither the most nor the fewest. Panel A plots maximum fit error against core count $R$ on the WW target: 153.0 bp at $R=0$, essentially unchanged at 154.7 bp for $R=1$ (one off-centre hat cannot seat two symmetric shoulders), collapsing to 2.5 bp at $R=2$ and flat thereafter (2.6 bp at $R=3$). Panel B plots two error curves against $R$ on a noisy liquid smile: the in-sample error falls monotonically with each added core, while the error against the noiseless true curve rises from 23.9 vol bp at $R=0$ to 37.7 bp at $R=3$ — the bias–variance scissor opening.

This is why the slider is governed rather than free. The backtest made the cost concrete on real data: on liquid index chains the extra cores chase quote noise and manufacture butterfly arbitrage (the analytic diagnostic flags $g<0$ on a majority of nodes at $R\ge2$ on dense data), while the base $R=0$ behaves comparably to SVI. The honest marginal number for the third core, from the spike replay: out-of-sample RMS 13.99 $\to$ 13.58 bp — a gain of a fraction of a basis point — for roughly the fourfold fit cost the two harness timings show ($514\to2023$ ms) and worse arbitrage. Not negative precision, but nowhere near worth it. Hence the hard cap at two, on top of the identifiability cap, the amplitude ridge, and the $g$ diagnostic.

> **Caution.** With great expressiveness comes over-fitting, and MCS is the one model in the series where the default posture is restraint. The operational guidance: *use cores only when the smile is genuinely non-convex* (events, bimodal positioning), and prefer LQD or Local-Vol for routine fitting. The cores slider is a scalpel, not a default — which is why the product default model is LQD, and MCS is the event/WW specialist.

> **Case file: two defences, one pathology.** The put-wing violation has *two* sources: the flexible model genuinely over-reaching (cured by the penalty of equation (10)), and *arbitraged inputs* — the per-strike de-Americanization of Note 05 can hand every model a call curve already slightly non-convex in the wings. An ablation isolating the two defences (the de-Am convex repair of Note 05 versus the penalty) on illiquid American ETFs found them *complementary, not redundant*. On the arb-prone population (medians over 38 nodes): with neither, worst $g\approx-30$ and in-sample RMS 92 bp; the de-Am repair alone cuts the violation about threefold *and lowers* the RMS to 25 bp (it removes the arbitraged quotes the model was chasing); the penalty alone nearly eliminates the violation but at 749 bp (it must fight those same quotes); both attain the penalty's arbitrage reduction at 225 bp, because the inputs are cleaned before the constraint is imposed. Reduction, not elimination: even with both defences on, 26% of the population stays flagged. One node makes it vivid (EFA in the Aug-2024 spike, 11 days, 22 quotes): neither, 75 bp with worst $g=-116$; repair alone, a tight 18 bp but $g=-12$; penalty alone, arbitrage-free but 726 bp; both, arbitrage-free at 34 bp. *The fence is expensive only when it must fight arbitraged inputs — cleaning the inputs at the source is what makes the constraint affordable.*

## 8. Worked example: a WW smile

The target in Figure 1 is a synthetic WW built to be *globally* admissible, not merely clean on a window. Its total variance is a hyperbolic base plus two Gaussian shoulders, $w(k)=a+b\sqrt{k^2+\varsigma^2}+\sum_\pm A\,e^{-((k\mp c)/s)^2}$. Gaussians vanish with all derivatives, so the $w$-wings are exactly linear with slope $\beta=0.055\le2$ (Lee-admissible for every $k$), and $g$ tends to the positive limit $(4-\beta^2)/16=0.250$ in both tails. The generator computes $g$ from analytic jets (no finite differences, the measurement lesson of Note 02) and asserts $g>0$ for target *and* fit on a dense grid to $|k|=12$ before writing anything.

The base ($R=0$) fits it only to 153.05 vol bp, missing both shoulders. Two hats ($R=2$, $6+4\cdot2=14$ parameters) reduce the maximum error to 2.55 vol bp — report two numbers and keep them separate: the *quote* error 2.55 vol bp is the fit's miss on the target, while the fit stays globally butterfly-clean, its wide-grid minimum $g=0.28$ (the target's is 0.25). Meanwhile the preserved base wing slopes $(S_0-2K_0/\kappa_P,\,S_0+2K_0/\kappa_C)=(-0.017,\,0.017)$ in $z$-space are exactly the base's, cores or no cores. Figure 8 plots the diagnostic for both curves.

> **Figure 8 — The butterfly diagnostic for the fitted slice and the target it chased (figure not included in this pack).** Both stay non-negative on the display window; with the wide-grid assertion to $|k|=12$ and the positive analytic tail limits, the cleanliness claim is global, not per-window. The figure plots Durrleman's $g$ across the display strike window for both the two-core fitted slice and the synthetic WW target: both curves stay strictly positive throughout, the fit's wide-grid minimum being 0.28 and the target's 0.25, and both approach the analytic tail limit $(4-\beta^2)/16=0.250$ far from the money.

**Remark 2 (The target must be clean too — a bug fixed twice).** A diagnostic is only as strong as the exercise it certifies, and this figure's target needed two rounds of honesty. An early revision built a WW target whose *own* Durrleman function dipped to $g\approx-0.38$ near the shoulders: the synthetic "market" itself carried butterfly arbitrage, so no admissible slice could both track it and honour $g\ge0$, and the figure's claim was quietly false. The first fix re-chose the shoulder amplitudes and widths (the shoulder-top curvature scales like $2A/s^2$, which drives $w''$, hence $g$, negative) — but that target was built in *volatility* space with linear tails, so its total variance grew quadratically and still violated Lee far outside the window: cleanliness only per-window. The current construction builds the target in *total-variance* space, so the $w$-wings are exactly linear and the tail $g$ limit is positive analytically. The lesson is the same one Note 02 drew about measuring $g$: compute it from analytic jets, and certify globally (a wide grid plus a tail limit), never on a plotted window alone.

**Exercise 3.** The identifiability cap of equation (11) counts parameters against quotes. Show that with $N_{\mathrm{quotes}}=5$ it gives $R=0$, yet the base alone has six parameters — one more than the data. Explain why this is not an outright failure (bounds and the data-driven start regularize it) but is also not an identifiability guarantee, and why a desk should distrust the individual base parameters, though not necessarily the fitted curve, on such a chain.

## 9. What is original, and limitations

The genuinely original elements are the *zero-wing hat* (equation (6) with Lemma 1) — a correction basis local in the body and provably neutral in the wings, so expressiveness and tail control are decoupled by an elementary annihilation property — and the *layered three-stage calibration* that places the corrections on residuals rather than optimizing them blind. Together they let one model span from a clean index smile ($R=0$, a convex family in its own right, not an SVI equivalent) to an event-shaped WW smile ($R=2$) on a single slider. (A WW *implied-volatility* curve suggests, but does not by itself prove, a bimodal risk-neutral density: the density is the Breeden–Litzenberger second derivative of price, not a re-reading of the vol curve.)

Limitations, stated plainly. MCS is *not* arbitrage-free by construction: signed hats can drive variance negative or break convexity; the wing penalty is a soft, non-guaranteeing fence, and while the traded-range certificate now hard-gates what a user can see or publish, MCS still lacks the automatic certified repair SVI carries when that gate fails — its open rider ("Static no-arbitrage"). Its wings are wing-*neutral*, not Lee-guaranteed: admissibility of the preserved base slopes is a separate check, equation (8). It over-fits liquid data when the slider is pushed, which is why the surfaced cap is two and the default model is LQD. And its hats are non-unique, so comparisons across fits must be made on curves and handles, never on the correction parameters. The cores slider earns its keep exactly when the smile is genuinely non-convex, and nowhere else.

## Appendix A. Hyperparameter atlas

*Table 2 — Multi-Core Sigmoid (MCS) hyperparameters.*

*Surfaced. Product defaults shown (the product's default model is LQD; these apply when MCS is selected). Library defaults differ: $R=0$, penalty off.*

| Knob | Default | Role |
|---|---|---|
| `nCores` $R$ | $2$ | Number of zero-wing hats, $R\in\{0,1,2\}$ (schema-clamped at two on every parse; the library is uncapped, and equation (11) may reduce $R$ further). $0$ = pure base. |
| `sivWingPenaltyPct` $\Lambda$ | $100$ | Put-wing Durrleman penalty (equation (10)) strength; $100=$ base $\lambda_0=1000$, $0=$ off. |
| `sigmoidRidge` $\varrho$ | 0.01 | $\ell^2$ penalty on hat amplitudes in the refine stage. |
| `midAnchorWeight` | $0.05$ | Band-fit mid anchor (Note 07). |
| `weightScheme` | `equal` | Per-quote weights (Note 07). |
| `calendarWeight` | $10^{6}$ | Calendar hinge penalty (Note 10). |
| `extrapEnforce` | off | Tapered extrapolated-region fences (Notes 09–10); hybrid Jacobian when on. |

*Internal (seeding / bounds)*

| Knob | Default | Role |
|---|---|---|
| `_H_INIT` | 0.40 | Hat half-width seed. |
| `_KAPPA_INIT` | 5.0 | Hat steepness seed. |
| `_H_BOUNDS` | $[0.15,1.5]$ | Hat half-width bounds. |
| `_KAPPA_BOUNDS` | $[1.0,12.0]$ | Hat steepness bounds. |
| `_C_PAD` | $0.5$ | Centre padding beyond the quoted $z$-range. |
| `_V_FLOOR` | $10^{-8}$ | Variance floor so $\sqrt v$ stays real. |
| `_LOGCOSH_CLIP` | $50$ | $\vert x\vert$ beyond which $\log\cosh$ uses its asymptote. |
| `xtol/ftol` | $10^{-12}$ | trf tolerances. |

## Appendix B. Performance notes

1. **Analytic Jacobian** through the log-cosh primitive replaces the $(6+4R+1)$-evaluation finite difference; measured 2.36× on the $R=2$ mid *final-refine* microbenchmark (base fit, seeding and the product-default wing penalty excluded; single-threaded development machine, fastest of several), optimum unchanged to $1.5\times10^{-15}$. Machine-dependent numbers belong here, not in the body. Gated to the var-swap/prior-free path; hybrid (analytic core $+$ FD penalty blocks) under the wing penalty or extrapolation fences.
2. **Layered warm start.** Fitting the base first and seeding hats on its residual gives the joint refine an excellent start, so the bounded trf converges quickly even with several cores.
3. **Vectorized kernels.** $\Phi,\Phi',\Phi''$ and the hat second differences are NumPy-vectorized and side-effect free, shared between the model and its Jacobian — one set of jets, computed once.
4. **Identifiability cap.** Limiting $R$ by the quote count avoids wasting iterations on under-determined narrow kernels, and is the first line of defence against the over-fit of "Expressiveness on a budget".

## Appendix C. Traceability

A scoping word first. The "zero-wing / diagnostics" rows anchor this note's current construction; the legacy over-parametrized golden tests lock the library's uncapped behaviour and are kept as regression tripwires, not as evidence for these figures — the regenerated two-core example has its own lock. The penalty rows are locked with stated tolerances: penalty-off is byte-identical; penalty-on over a clean slice is unchanged to $10^{-9}$ relative; and the repair test accepts a repaired $\min g\ge-0.05$, not exactly zero. Two tolerances now coexist and must not be conflated: the $-0.05$ above is the *wing-repair regression* bar (orders of magnitude better than the injected violation), while the display *certificate* of "Static no-arbitrage" demands $g\ge-10^{-4}$ at all 801 traded-range points before a slice is publishable. A finite diagnostic grid is not a global proof.

*Module and test names refer to the reference implementation this pack was distilled from; treat them as a capability and test checklist, not as file names to reproduce.*

*Table 3 — Claims in this note and the code/tests that lock them.*

| Claim | Object | Code anchor / *test anchors* |
|---|---|---|
| Hat is unit-height, flat at centre, zero-wing in value/slope/curvature | Lemma 1 | `models/sigmoid/kernels.py` — *`test_sigmoid.py::test_hat_is_zero_wing_and_unit_height`* |
| Wing slopes preserved under cores; $g$ and $\min v$ diagnostics match note | equation (5) | `models/sigmoid/sigmoid.py` — *`test_sigmoid.py::test_note_arbitrage_diagnostics`* |
| Reported $g$ is the priced (floored) curve's functional; degenerate slices flagged not-free | "Static no-arbitrage" | `models/sigmoid/sigmoid.py::gatheral_g` — *`test_sigmoid.py::test_floored_diagnostic_is_priced_curve_functional`* |
| This note's two-core WW example (fit tight, base misses shoulders; target and fit globally butterfly-clean) | "Worked example: a WW smile" | `models/sigmoid/calibrate.py` — *`test_sigmoid.py::test_note03_ww_two_core_example_regression`, `::test_note03_ww_target_globally_clean`* |
| Cores improve the WW fit monotonically (legacy synthetic) | "Expressiveness on a budget" | `models/sigmoid/calibrate.py` — *`test_sigmoid.py::test_more_cores_fit_better_on_ww_smile`* |
| Hat-count cap $R\le\lfloor(N-6)/4\rfloor$ (hats only; the base still fits at $N=5$) | equation (11) | `models/sigmoid/calibrate.py` — *`test_sigmoid.py::test_cores_are_capped_to_quote_count`* |
| Surfaced slider clamped to two (schema boundary, every parse) | "Calibration" | `api/schemas.py` — *`test_siv_wing_penalty.py::test_cores_clamped_to_two`* |
| Traded-range certificate gates readiness and publish for displayed MCS slices | "Static no-arbitrage" | `models/diagnostics.py::belly_certificate`, `api/quality.py` — *`tests/test_belly_certificate.py`; certification case `belly_certificate`* |
| Put-wing hinge repairs wing arb (to $\min g\ge-0.05$); clean slices unchanged ($10^{-9}$ rel); off by library default (byte-identical) | equation (10) | `models/sigmoid/calibrate.py` — *`test_siv_wing_penalty.py::test_penalty_removes_wing_arb`, `::test_penalty_byte_identical_on_arb_free_slice`, `::test_penalty_off_default`* |
| Analytic Jacobian matches FD (base, cores, band, calendar) | "Calibration" | `models/sigmoid/jacobian.py` — *`test_sigmoid_jacobian.py::test_two_cores_mid`, `::test_two_cores_band`, `::test_calendar_active`* |
| Curve identified, parameters deliberately not | "Calibration" | `models/sigmoid/calibrate.py` — *`test_sigmoid.py::test_round_trip_curve_recovery`* |
| Prior blocks reach the MCS overlay | "Calibration" | `models/sigmoid/calibrate.py` — *`test_prior_parametric.py::test_operator_prior_pulls_all_models_toward_prior_skew`* |
| Over-parametrized ablation numbers (two defences, one pathology) | "Expressiveness on a budget" | `backend/backtest/ablation_arb.py` — *`test_ablation_arb.py`* |

## Appendix D. Reference implementation

The full slice $v_R(z)$ of equation (7) and the butterfly diagnostic $g(k)$ of equation (9) are a few lines built on the production kernels. The $z$-jets (value, slope, curvature) are carried together because $g$ needs all three; the zero-wing second difference is written once and reused for the hat and its derivatives. The reference maps are imported and executed by the note's figure generator, which asserts they agree with the production `MultiCoreSiv` to $10^{-13}$ before drawing a figure, so the specification below is the exact computation that produced the note's numbers. (The source listing itself is not carried in this pack; the following algorithm specification carries every step.)

**Algorithm D.1 — MCS slice evaluation with $z$-jets ($v_R$, $v_R'$, $v_R''$).**

*Inputs:* an array of dimensionless log-strikes $z$; the base parameter tuple $(V_0,S_0,K_0,z_0,\kappa_P,\kappa_C)$; a list of $R$ cores $(\alpha_r,c_r,h_r,\kappa_r)$.
*Outputs:* the three arrays $v_R(z)$, $v_R'(z)$, $v_R''(z)$ (value, slope, curvature in $z$).

1. Set $u=z-z_0$ elementwise, and choose the steepness pointwise: $\kappa(u)=\kappa_P$ where $u<0$ and $\kappa(u)=\kappa_C$ where $u\ge0$ (the asymmetric wings; the slice remains $C^2$ at $z_0$ because $\Phi$ and $\Phi'$ vanish at the origin).
2. Evaluate the base jets from equation (4): $v=V_0+S_0u+K_0\,\Phi_{\kappa}(u)$, $v'=S_0+K_0\,\Phi'_{\kappa}(u)$, $v''=K_0\,\Phi''_{\kappa}(u)$, using the log-cosh primitive of equation (2). For numerical safety $\log\cosh(x)$ is evaluated as its exact asymptote $|x|-\log 2$ whenever $|x|>50$ (the clip is on the asymptote substitution, never on $x$ itself).
3. For each core $r=1,\dots,R$, add the signed zero-wing hat and its derivatives: $v \mathrel{+}= \alpha_r B_{c_r,h_r,\kappa_r}(z)$, $v' \mathrel{+}= \alpha_r B'_{c_r,h_r,\kappa_r}(z)$, $v'' \mathrel{+}= \alpha_r B''_{c_r,h_r,\kappa_r}(z)$, where $B$ is the normalized centred second difference of equation (6) and $B'$, $B''$ are the same second difference applied to $\Phi'$ and $\Phi''$ over the same normalizer $2\Phi_\kappa(h)$.

*Production-agreement tolerance:* the generator asserts agreement with the production `MultiCoreSiv` to $10^{-13}$ before any figure is drawn.

**Algorithm D.2 — Durrleman butterfly diagnostic $g(k)$ from the $z$-jets.**

*Inputs:* the $z$ grid, base and cores as above, the time $t$, the reference volatility $\sigma_{\mathrm{ref}}$, and a variance floor $v_{\mathrm{floor}}=10^{-8}$.
*Output:* the array $g$ over the grid; $g\ge0$ on the grid is the no-butterfly condition (a diagnostic on a finite grid, not a global certificate).

1. Evaluate the jets $(v,v',v'')$ by Algorithm D.1.
2. Floor the value only: $v\leftarrow\max(v,\,10^{-8})$. The derivatives $v'$, $v''$ are left *unfloored* (this is the reference/diagnostic convention of this listing; see Remark 1 for how the priced-curve diagnostic and the penalty-path $g$ each treat the floor).
3. Convert to total-variance $k$-space: $k=\sigma_{\mathrm{ref}}\sqrt t\,z$, $w=t\,v$, $w'=(\sqrt t/\sigma_{\mathrm{ref}})\,v'$, $w''=v''/\sigma_{\mathrm{ref}}^2$.
4. Return equation (9): $g=\big(1-\tfrac{k\,w'}{2w}\big)^2-\tfrac14\,w'^2\big(\tfrac1w+\tfrac14\big)+\tfrac12\,w''$.

## References

- [Gatheral2006] J. Gatheral. *The Volatility Surface: A Practitioner's Guide*. Wiley, 2006.
- [Durrleman2010] V. Durrleman. From implied to spot volatilities. *Finance and Stochastics*, 14(2):157–177, 2010.
- [Lee2004] R. W. Lee. The moment formula for implied volatility at extreme strikes. *Mathematical Finance*, 14(3):469–480, 2004.


