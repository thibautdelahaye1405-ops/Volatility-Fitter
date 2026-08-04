# Student review — round 1

Reader profile: strong undergraduate; comfortable with Black–Scholes (both derivations),
put–call parity, Greeks, calculus, linear algebra, first-course probability (CDFs, MGFs).
Never studied smile modeling, quantile mechanics, convex order, Lee's formula, Legendre
expansions, envelope theorems, or numerics beyond Newton and Simpson.

I read the paper start to finish in order, redid every derivation I could with pen and
paper, and looked at every figure PDF the text leans on. Ratings: **BLOCKING** (could not
continue past it), **HARD** (continued but did not understand / believe), **SOFT**
(understood after rereading; could be smoother). Placeholder macros `[X?]` were ignored
as instructed.

## What I verified myself (so the objections below are from doing the math, not skimming)

- The Euler MGF chain (eq. mgf): B(1+t,1−t) = Γ(1+t)Γ(1−t) = πt/sin(πt); the π²/3
  variance; the cold-start seed s = √(3w₀)/π; the 6(log2)²/π ≈ 0.918 bias constant.
- Prop. shift (both tails of the normalizing integral) and the wall λ₊ < 1.
- Prop. tails, the moment strip, and **both closed-form Lee maps** in prop. leeclosed —
  the s and t substitutions check out exactly, including the small-speed limits λ±/2.
- All five ledger identities (eqs. call/put/cprime/csecond/bl_division), including the
  vanishing bracket, and the digital reading −e^{−k}c′(k) = 1−u_k.
- The envelope theorem (thm. envelope) and all three Jacobian passes, including the
  absorbed 1/I in the App. A code (w = e^x ρ carries e^m = 1/I — nice).
- The full ATM proof in App. B line by line: all five Black partials, the cancellation
  of the digital-mismatch terms against the cross term, the (1/(2w₀)+1/8) coefficient,
  and the 1/16√w₀ collapse in Step 4. It is correct.
- Both conjugacy identities and the calendar order theorem (lem. conjugacy,
  thm. ledgerorder).
- The tail corrections (eq. tailcorr), the beyond-grid asymptote (eq. beyondgrid — I had
  to derive it myself, see O16), the chart-compression derivative (1−λ₊), the
  endpoint-vanishing body combinations, and the order-guard arithmetic (17 quotes → 7).
- Cross-figure consistency of the tail chain: fig_tails' SPY left dot A ≈ 0.43 maps to
  β_L = 2·0.43/(1+√1.43)² ≈ 0.179, exactly the dotted line in fig_lee. Internally
  consistent.

---

## Objections

### §2 — The constraint set (`sections/02_constraint_set.tex`)

**O1. [HARD] The Durrleman function (eq. durrleman) falls from the sky, and
"proportional" hides an unstated k-dependent factor.**
Quote (~line 97): *"Substituting c=Black(k,w(k)) and differentiating twice, the density
is proportional to g_D(k) = (1 − kw′/2w)² − (w′²/4)(1/w + 1/4) + w″/2 ≥ 0."*
My attempt: differentiating B(k, w(k)) twice through the five Black partials took me
half a page **at k = 0 alone**; the general-k identity is far beyond "a few minutes",
and I could not check it. Also, for a flat smile (w′ = w″ = 0), g_D ≡ 1 while the
lognormal density in k is certainly not constant — so "proportional" must mean "up to
an explicit positive k-dependent factor", which is never displayed. This matters later:
the belly certificate (§12) thresholds g_D at −10⁻⁴, and without the factor I cannot
translate that tolerance into density or price units. What I *could* verify: at k = 0,
substituting eq. atm_wpp gives g_D(0) = √w₀ f*/φ(d) ≥ 0 — a nice consistency check the
paper never makes.
**Ask:** one displayed line of the form f_Y(e^k)·(explicit positive factor) = g_D(k)·(…),
or a pinpoint citation (equation number) into Gatheral–Jacquier; ideally also the ATM
cross-check above, which would let a reader like me verify the formula at one point.

### §3 — Heuristic (`sections/03_heuristic.tex`)

**O2. [SOFT] The Gaussian quantile-density asymptotic needs the Mills ratio, which I
had to reconstruct.**
Quote (~line 62): *"q(u)=1/φ(Φ⁻¹(u)), which blows up like 1/(u√(2log(1/u))) as u→0."*
I got there via u = Φ(x) ~ φ(x)/|x| and |x| ~ √(2log(1/u)), but that tail equivalent is
not first-course material and cost me twenty minutes.
**Ask:** a parenthetical "(using Φ(x) ~ φ(x)/|x| as x → −∞)".

Otherwise §3 is the best-written section in the paper; eq. speed's cancellation of both
singularities is genuinely satisfying and I verified it.

### §4 — The LQD family (`sections/04_model.tex`)

**O3. [SOFT] The constants m^± are silently reused for two different functions.**
Below eq. speeds (~line 81): *"x(z)=m⁻+λ₋z+o(1) … x(z)=m⁺+λ₊z+o(1)"* — asymptotes of
the **shifted** transport x. In the proof of prop. shift (~line 140): *"x̄(z)=m⁺+λ₊z
+O(e^{−z})"* — now the **unshifted** x̄. The two constants differ by m. Prop. tails
(§6) then uses m⁺ for x again, and K₊ = e^{m⁺/λ₊} inherits the ambiguity. In a paper
whose notation table boasts *"none is reused with a second meaning"*, this tripped me.
**Ask:** write m̄⁺ (or m⁺ − m) in the prop. shift proof.

**O4. [SOFT] E[Z⁺] = log 2 is asserted inside the seed-bias derivation.**
Quote (~line 203): *"the at-the-money call of this slice is c(0) ≈ s E[Z⁺] = s log 2."*
Two unstated steps: (i) (e^X − 1)⁺ ≈ X⁺ ≈ sZ⁺ needs m = O(s²) (true: m ≈ −π²s²/6, but
say so); (ii) E[Z⁺] = log 2 needs a computation (I did it by expanding the logistic
density in a geometric series: Σ(−1)^{n−1}/n = log 2).
**Ask:** one footnote for each.

**O5. [SOFT] "Fix an order N ≥ 4" — why 4?**
Def. lqd (~line 17). Nothing in the definition breaks at N = 2 or 3; the bound seems to
exist so the ridge (which starts at n = 4) and the guard floor (6) make sense later.
A definition should not quietly carry a calibration convention.
**Ask:** either allow N ≥ 2 and say the ridge convention motivates 4, or say why 4.

### §5 — Validity (`sections/05_validity.tex`)

**O6. [SOFT] Wasserstein-p is used in prop. universal without a definition, for a
reader who was promised to need only Black–Scholes.**
Quote (~line 150): *"the laws of the gross returns converge in Wasserstein-p distance
for every p ∈ [1, 1/λ₊*)."* The only definition ever given is implicit, in App. B
Step 5, via the quantile-coupling identity plus a citation to Villani. I could follow
the *proof* (the coupling formula is stated there), but reading §5 I had to take the
term on faith.
**Ask:** one sentence in §5: "W_p(μ,ν)^p = ∫₀¹|Q_μ − Q_ν|^p du for laws on ℝ — the
p-th mean cost of moving one law onto the other rank by rank."

Everything else in §5 I verified: the layer-cake argument in prop. wall is complete and
elementary, and prop. noarb (i)–(iv) all check, including the log-strike concavity
computation.

### §6 — Tails and moments (`sections/06_tails_moments.tex`)

**O7. [HARD] Figure fig_lee (left panel) contradicts the text and its own caption: on
the put wing the effective slope sits BELOW the Lee limit and approaches it from
below.**
Text (~line 204): *"The effective variance slope w(k)/|k| descends toward β from above
… at the strikes a desk actually trades, ten-delta and one-delta, the effective slope
still **exceeds** the limit by an economically large factor."* Caption: *"The effective
slope descends toward the limit from above and is still [ratio] times the limit at the
10Δ put…"*
The figure's left panel shows: effective slope falling from 0.17, bottoming at ≈ 0.117,
then **rising** back to 0.173 at |k| ≈ 5, with the Lee limit β = 0.179 dotted **above
the entire curve**; both the 10Δ and 1Δ diamonds sit at ≈ 0.125, i.e. ratio ≈ 0.70 —
*below* one, not an "economically large factor" above. The right panel does match the
text (0.058 vs 0.034 at 10Δ, from above). So on the put wing the honest warning flips:
pricing a 10Δ put off β_L would *over*-price it, not underprice it. (Geometrically
w(k) ≈ β|k| + c with c < 0 explains an approach from below — but then "descends from
above" is simply wrong there, and the promised ratios > 1 cannot come out of this
panel.)
**Ask:** either the figure generator is wrong, or the §6.4 prose and the fig_lee caption
must be rewritten wing-by-wing. As written I cannot reconcile them.

**O8. [SOFT] Prop. tails, inversion step.**
Quote (~line 35): *"inverting the asymptote gives z(x) = (x−m⁺)/λ₊ + O(e^{−z(x)})."*
True — z = (x − m⁺ − ε(z))/λ₊ — but the one-line substitution is skipped and I stalled
briefly on whether the error keeps its form under inversion.
**Ask:** show that intermediate line. (Also inherits the m⁺ ambiguity of O3.)

### §8 — The ATM microscope (`sections/08_atm.tex`)

**O9. [HARD — my #1 objection] The sign of the digital mismatch story is backwards:
by the paper's own formula, Δ > 0 makes the smile tilt UP to the right, and a fitted
index slice must have Δ < 0.**
Quote (~line 84): *"A fitted index slice has Δ>0: the model puts the forward at a
higher rank than flat-Black would --- more than the Black share of outcomes finish
below the forward, compensated by a fatter left tail --- and the smile tilts down to
the right accordingly."*
My derivation, three independent ways:
1. **From the paper's own formulas.** eq. atm_w: w′(0) = (2√w₀/φ(d))·Δ, so
   sign(w′(0)) = sign(Δ). An index smile tilts *down* to the right (σ′(0) < 0 —
   confirmed by the paper's own SPY figures: in fig_spy_node/fig_spy_gallery the
   December 2026 smile decreases through k = 0 with its minimum near k ≈ +0.12).
   Therefore the fitted SPY slice has Δ < 0, and "Δ > 0 … tilts down to the right" is
   self-contradictory: Δ > 0 tilts it *up*.
2. **A worked counterexample.** Crash mixture: X = −0.20 w.p. 0.05, else
   N(0.00449, 0.10²), martingale-normalized (E[e^X] = 1 to 4 decimals). I compute
   u* = P(X ≤ 0) = 0.508, c₀ = 0.0428 ⇒ d = 0.0537, Φ(d) = 0.5214, so
   Δ = u* − Φ(d) = **−0.013 < 0** for an unambiguously left-skewed law (third central
   moment < 0). A cruder two-point version gives the same sign.
3. **The digital heuristic.** With negative skew, the market digital is *rich* versus
   flat Black (D = −∂C/∂K = Black digital − vega·∂σ/∂K, and ∂σ/∂K < 0), so
   1 − u* > 1 − Φ(d), i.e. u* < Φ(d): *fewer*, not more, outcomes finish below the
   forward relative to Black.
The same wrong sign is repeated in the fig_spy_node caption (§13, ~line 69: *"the same
fact the digital mismatch Δ>0 of prop:atm states in one number"*). Note §13's separate
claim u* > 1/2 is compatible with Δ < 0, since Φ(d) > 1/2 too — but that means §13's
fitted numbers, once the macros fill, will contradict §8's sentence directly (the
fitted skew macro must be negative).
**Ask:** decide the intended orientation of eq. digitalgap. Either flip the sentence
("a fitted index slice has Δ < 0: fewer than the Black share of outcomes finish below
the forward — the fat left tail pushes the body of the law above the forward — and the
smile tilts down to the right accordingly"), or redefine Δ = Φ(d) − u* and flip
eq. atm_w/eq. atm_sigma. Everything else in §8 and App. B I verified and believe.

### §9 — Calibration (`sections/09_calibration.tex`)

**O10. [SOFT] The barrier row's units and weight are unstated, and hinge rows are not
C² at the band edge.**
Quote (~line 56): *"One more residual row rides along in every fit: a smooth barrier
log(1+e^{50(λ₊−0.90)})."* All other rows are (to first order) vol errors; this row is
dimensionless with an implicit weight of 1. How was 50 chosen, and what makes a squared
softplus commensurate with vol-bp rows? Relatedly, the band hinge (eq. band) is C¹ but
not C² at the band edge, and §10 says its Jacobian row is *"(eq. envelope) multiplied by
the violation sign"* — undefined exactly at the edge. Trust-region LSQ presumably
tolerates this, but the paper is otherwise scrupulous about smoothness (the calendar
taper is explicitly "continuously differentiable, so the solver sees no kink" — why is
the same care not needed here?).
**Ask:** a sentence on the barrier weight/units and one on the hinge kink.

### §11 — Calendar (`sections/11_calendar.tex`)

**O11. [HARD] The section's premise — that no calendar arbitrage ⟺ c₁(k) ≤ c₂(k) at
equal log-moneyness — is asserted, not derived, and at my level it is not obvious:
equal k means different dollar strikes.**
Quote (~line 8): *"nothing yet prevents a longer-dated call from pricing below a
shorter-dated one at the same log-moneyness --- a calendar spread the market would pay
you to own."*
My attempt: the two normalized calls at the same k are options struck at K₁ = F₁e^k and
K₂ = F₂e^k — different dollar strikes when F₁ ≠ F₂ — so the monetizing portfolio is not
the plain calendar spread the sentence evokes, and I could not write down the arbitrage
in a few minutes. I could only reconstruct the claim by inventing the deterministic-carry
martingale M_t = S_t/F₀(t) (deterministic rates make all forward measures coincide;
M_{T_i} is exactly the normalized return of slice i) and conditional Jensen:
E[(M_{T₂} − e^k)⁺ | F_{T₁}] ≥ (M_{T₁} − e^k)⁺. That is three lines, but they are *my*
three lines, and the two "standing assumptions" at the top of the section are doing all
of the work invisibly.
**Ask:** state and prove (or cite) this as a one-lemma preamble to eq. calreq, and say
explicitly that the monetizing trade is forward-scaled in strike.

**O12. [SOFT] fig_calendar does not match its caption.**
Caption promises **three** panels (A: term structure; B: the pair in total variance
with common span; C: the far-wing crossing). The PDF has **two** panels: (a) the term
structure, (b) a single panel carrying both the shaded span and the crossing
annotation. Further: (i) panel (b)'s y-axis is *"vol at the 4d maturity (%)"* — a
normalization (both slices' total variance through the same τ?) explained nowhere;
the caption says the panel is in *total variance*; (ii) the promised crossing is not
actually visible — the 4d curve sits above the 2d curve everywhere in frame, both
curves go dotted where "double-precision resolution" ends, and the crossing location is
indicated only by a dotted vertical and an annotation; (iii) the legend says
"2026-08-05 (2d)" and "2026-08-07 (4d)" while the text and App. C call this pair "the
one-day and three-day SPY expiries" throughout. Which day-count is in force is never
stated (§13 also says "from one day to about 1.4 years" while the gallery's first panel
is titled "(2d)").
**Ask:** regenerate or re-caption; define the y-axis normalization; pick one day-count
naming and use it in both text and figures.

### §12 — Computation (`sections/12_computation.tex`)

**O13. [SOFT] eq. beyondgrid is stated without its (short) derivation.**
Quote (~line 47). I could derive it — substitute the ledger tail estimate
G(z_k) ≈ e^{k−z_k}/(1−λ₊) and the cash leg e^k(1−u_k) ≈ e^{k−z_k} into eq. call — but
the paper gives neither line, and the λ₊/(1−λ₊) factor looks mysterious until you see
the subtraction.
**Ask:** those two intermediate expressions, inline.

(The floating-point catalogue is excellent and I verified the stable Lee form and the
36.7 saturation threshold. The three-chart discussion checks: I verified the
endpoint-vanishing combinations and the unit determinant.)

### §13 — Examples (`sections/13_examples.tex`)

**O14. [HARD] The order-control text says the N=6 density is unimodal; the figure
shows it plainly bimodal.**
Quote (~line 132): *"but the density is unimodal: the trough is smoothed away
entirely."* Caption of fig_order_control: *"N=6 smooths the trough away."*
The figure's N=6 curve has two clear peaks (≈ 4.5 at x ≈ ±0.1) and a trough (≈ 1.8 at
x ≈ 0, versus the true 1.3); it is *more* bimodal-looking in the peaks than N=16, and
the trough is shallower than truth but very much present. The exhibit's honest story
seems to be "N=6 half-fills the trough and overshoots the peaks", which still makes the
information-vs-convention point — but the current text asserts something the panel
visibly refutes.
**Ask:** regenerate the figure from the intended parameters, or rewrite the two
sentences to describe the actual curves.

**O15. [SOFT] Two rhetorical overclaims: "as the martingale shift demands" and "as the
skew requires".**
Quote (~line 54): *"the fitted forward rank is u* = […] --- above one half, as the
martingale shift demands for a left-skewed law"*; and *"the var-swap strike […] above
the ATM volatility, as the skew requires."* Neither is a theorem. Counterexample to the
first: X = +0.10 w.p. 0.6, X = −0.1716 w.p. 0.4 has E[e^X] = 1.0000, third central
moment < 0 (left-skewed), and u* = P(X ≤ 0) = 0.4 < 1/2. (Discrete, hence outside the
family, but a smoothed version stays a counterexample, so the martingale shift *demands*
no such thing in general.) Both facts are true of typical equity fits; "demands" and
"requires" claim more.
**Ask:** soften to "as expected for…" or state the actual sufficient conditions.

**O16. [SOFT] "Nearly indistinguishable" vs a 42 vol bp gap.**
§13 (~line 131): *"the smile fit is nearly indistinguishable --- the two fits agree in
implied volatility to [MacHumpIvAgreeBp] vol bp"*; the figure annotates "fits differ by
≤ 42 vol bp". Forty-two bp is an order of magnitude above the quoted fit rms elsewhere
in the paper; from the panel the divergence looks concentrated *outside* the quoted
ladder (|k| > 0.25).
**Ask:** if the max gap is attained beyond the outermost quote, say so — it makes the
point sharper, not weaker.

### Figures generally

**O17. [HARD] The figures speak a different notation from the paper, and none of the
figure symbols are defined anywhere.**
fig_modes' y-axis is "log-speed **h(u)**" — the paper's g(u) (and the ledger assigns h
to the haircut half-width!). fig_tails uses **h±** for the endpoint log-speeds (paper:
g(0), g(1)), **A = e^{h±}** for the tail scales (paper: λ±), **p±** for the critical
moment orders (paper: r±*), and lowercase **ψ** for the Lee map (paper: Ψ).
fig_spy_node's legend says "bid-ask spread" where the caption says "haircut bands".
For a reader cross-referencing tab. ledger — which promises *"every recurring symbol in
the paper … none is reused with a second meaning"* — this is disorienting out of
proportion to its cause.
**Ask:** regenerate figure labels in the paper's notation (or add a translation line to
each caption).

**O18. [SOFT] The notation ledger's no-reuse claim is violated by Z itself.**
tab. ledger (~§2 line 157): *"Z is the quadrature half-width in log-odds and nothing
else"* — yet Def. lqd says *"Let Z be a standard logistic variable"*, and eq. ledger
writes G(z) = E[Y·1{Z>z}]. Two meanings, both load-bearing.
**Ask:** rename the grid half-width (Z_grid?) or the random variable.

**O19. [SOFT] fig_transport: the middle percentile dots are quartiles, not the
promised 10th/90th.**
Caption: *"the marked ticks are the 1st, 10th, 50th, 90th, and 99th percentiles."*
The inner dots sit at z ≈ ±1.10 with ρ ≈ 0.187 = 0.75·0.25 — exactly logit(0.75) and
the quartile density. The 10/90 marks would be at z = ±2.20 with ρ = 0.09. (§3's text
"z = ±log 9 ≈ ±2.20 are the 90th and 10th percentiles" is correct; the figure isn't.)
**Ask:** fix the dots or the caption.

**O20. [SOFT] fig_butterfly: caption says "two secant chords drawn"; the panel has
one.**
Panel (a) shows a single dotted secant (≈ 0.88 to 1.12). Minor, but a caption that
promises what the eye can count invites exactly this check.

**O21. [SOFT] fig_exact: "worst error […], i.e. machine precision" vs a shift error
climbing to ~3×10⁻⁹ near the wall.**
Panel (a) shows |m − m_s| rising steeply with s to about 3e−9 by s ≈ 0.95. That is nine
orders above 2⁻⁵³; the honest caption is "near machine precision away from the wall,
degrading (as expected — the normalizing integrand decays like e^{(λ₊−1)z}) as s → 1".
**Ask:** scope the phrase, and say *why* the blue curve grows.

**O22. [SOFT] fig_tails caption: "the dashed line is the finite-forward wall λ₊=1" —
but the figure's dashed line is the right-hand moment map itself.**
Panel (b)'s legend labels the dashed curve "right: p₊ = 1/A_R − 1"; the wall appears
only as that curve's vertical asymptote at A = 1, not as a drawn dashed wall line.
**Ask:** align caption and legend (or actually draw the wall).

### Appendix B (`sections/B_proofs.tex`)

**O23. [SOFT] Step 4 of the universality proof: the constant C₂ appears from nowhere.**
Quote (~line 191): *"dominated by e^{Q_N}+e^{Q*} ≤ 2C₂(1−u)^{−λ̄}+2C₂ … (translate
(envelopeB) through 1−Λ(z)∼e^{−z})."* C₁ was carefully constructed in Step 2; C₂ is
used without definition. I believe it is C₁·e^{sup_N|m_N|}·(a constant from
1−Λ(z) ≍ e^{−z}), with sup|m_N| finite because m_N converges — but the proof should say
this, since it is the only place uniform control of the shifts is needed.
**Ask:** one sentence defining C₂.

### A question, not an objection

**Q1.** Why Legendre? §4 justifies the basis as "readable endpoints, flexible,
well-conditioned, cheap" — but orthogonality is never actually *used* anywhere in the
paper (the endpoints use only P_n(±1) = (±1)^n, which monomials in (1−2u) also give).
If the conditioning claim is the real reason, one sentence connecting Legendre
orthogonality under the uniform rank measure to the Gauss–Newton normal equations would
turn a convention into a reason. If Chebyshev or monomials would work identically, say
that too — it would strengthen, not weaken, the "convention, disclosed" doctrine.

---

## (a) The three objections I would most want answered before an exam

1. **O9 (the sign of Δ).** The "skew is a digital mismatch" reading is the paper's most
   quotable sentence, and as written it contradicts the paper's own formula, its own
   SPY figures, and every example I could build. I need to know which orientation of
   Δ is intended before I can trust anything I'd say about eq. atm_w.
2. **O11 (why equal-k call ordering is the calendar no-arbitrage condition).** Without
   the deterministic-carry martingale lemma, eq. calreq is a convention dressed as a
   requirement — precisely the failure mode the paper preaches against.
3. **O1 (the Durrleman factor).** I can't audit the belly certificate's −10⁻⁴ threshold,
   or reproduce §2's central "why volatility space is expensive" claim, without knowing
   what g_D is proportional to.

## (b) Sections that read perfectly (for this reader)

- §1 (introduction), §3 (heuristic — the best exposition in the paper), §5 (validity,
  modulo the Wasserstein term), §7 (the ledger — every identity verified, flawless),
  §10 (the envelope theorem and passes — crisp, honest about the interpolation caveat),
  §12's floating-point catalogue, §14 (related work — unusually honest), §15
  (limitations), App. A (the code snippets match the text's equations, including the
  absorbed 1/I), and App. B's ATM proof, which I verified line by line.
- The overall validity/information/convention frame is genuinely clarifying and is used
  consistently, not just announced.

## (c) Verdict

The mathematics I could check — which is most of it — is correct, unusually complete,
and honestly scoped; but the paper's interpretive layer has real faults: one sign error
repeated in two places (Δ), two figures that contradict their own text (fig_lee left
panel, fig_order_control), one asserted-not-derived premise carrying a whole section
(eq. calreq), and a figure set speaking a different notation from the prose. Fix those
and this is the rare paper a student can actually learn smile modeling from end to end.

---

*Tally: 0 BLOCKING, 6 HARD (O1, O7, O9, O11, O14, O17), 17 SOFT (O2–O6, O8, O10,
O12–O13, O15–O16, O18–O23), plus one open question (Q1).*
