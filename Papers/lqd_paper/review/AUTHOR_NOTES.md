# Author notes — round 1 draft

Everything the lead should know before compiling, sending to the student
challenger, or briefing the figure engineer.

## File inventory

- `lqd_paper.tex` — master (preamble, notation macros, figure guard
  `\paperfig`, `\providecommand` fallbacks for every data macro, inputs,
  natbib/plainnat).
- `sections/01_introduction.tex` … `15_limitations.tex`,
  `A_implementation.tex`, `B_proofs.tex`, `C_data.tex`.
- `references.bib` — 22 entries, all real; uncertainties below.
- `review/REQUESTED_MACROS.md` — the generator contract (79 macros; the
  master's fallback list is verified in exact 1:1 parity with usage).

## Deviations from the briefs (all deliberate, all flaggable)

1. **One symbol for the log-speed: `g`.**  The author brief's §4 spine uses
   `h(p)` for the transport form and `g(u)` in the LQD form; they are the
   same function, and the style contract forbids near-duplicate symbols, so
   the paper uses `g` throughout (boxed definition included).
2. **Rank symbol `u`, moment order `r`.**  The brief's §7–8 write `p_k`,
   `p*` for ranks while the notation list reserves `p` for moment order.  I
   unified: ranks are `u` (`u_k`, `u_*`), the moment order is `r`
   (freeing `p`; the put is `P(k)`, used essentially only for parity).
   The ATM triple is therefore `(c_0, u_*, f_*)`.
3. **Martingale shift is `m`** (brief spine), not the notes' `μ`.
4. **Logistic-chart coordinate is `ξ`** (`λ_+ = expit ξ`).  The notes call
   it `ρ`, which collides with the logistic density `ρ(z)` that the brief's
   own ledger definition uses.  Declared in the notation table.
5. **Durrleman-type function named `g_D`** (§2, reused §12) to avoid
   collision with the model's `g`.
6. **Universality closure claim weakened to what I can prove.**  The
   internal note asserts the excluded laws are "not even in the closure
   under these metrics with admissible limits".  Under the *uniform call
   metric alone* that is false as stated — smooth convex curves can
   uniformly approximate a kinked (atomic) call curve — so
   Prop. (universality)(ii) claims exclusion-from-closure only under
   uniform convergence of the log-speeds `g_N` (the chart's own topology),
   which Annex B proves.  If the lead wants the stronger statement, it
   needs a genuinely different argument (tail-scale-uniform families), not
   a bolder sentence.
7. **Effective-slope direction.**  The notes-map line says the effective
   slope "sits well below" the Lee limit; the mathematics says it descends
   to the limit **from above** (near ATM it is dominated by `w_0/|k|`).
   The paper and the macro contract use effective/limit ratios > 1.  The
   figure engineer should verify on the fitted node and *stop* if the
   direction disagrees.
8. **Figure order.**  The fixed plan's F-numbers are treated as content
   IDs, not document order.  Placement (first reference = placement order):
   F1 (§3), F2, F3, F7 (§4), F14 (§5), F8, F9 (§6), F12 (§10), F13 (§11),
   F4, F5, F6, F10, F11 (§13).  LaTeX figure numbers therefore ascend in
   text order, satisfying the style contract; if the lead intended
   *plan order = document order*, sections 5–7 would need the SPY gallery
   before the tails discussion, which I judged worse pedagogy.  Amendment
   proposal, not a unilateral plan change: none of the 14 figures' content
   was altered.
9. **`\providecommand` fallback block** in the master: the paper compiles
   without `figures/paper_macros.tex`, rendering `[Name?]` placeholders.
   Generator definitions win automatically (file is input before the
   fallbacks).  This goes beyond the brief's `\IfFileExists` requirement
   but serves its purpose (text and figures buildable independently).
10. **Timing table body is a macro** (`\MacTimingRows`) emitted by the
    generator, following the internal notes' whole-table-macro pattern;
    the table skeleton and caption live in §12.
11. **ATM-orthogonal chart / packages / delta-method bands** are mentioned
    in two sentences (§8 end, Annex A recommendation 3) and *not*
    developed — the briefs put them out of scope; flagged here so nobody
    hunts for a missing section.
12. **Order-guard formula.**  I wrote the guard as
    `N_eff = max(min(N, floor(n_q/2) − 1), min(N, 6))` from the
    implementation brief's "params N+1 ≤ quotes/2, floor min(N,6)".
    Worth one check against the code: off-by-one conventions here are
    easy to fumble, and the NVDA 1d macro (`\MacNvdaOneDayEffOrder`) will
    expose any mismatch publicly.

## Bibliography: confidence notes

Certain: Breeden–Litzenberger 1978; Lee 2004; Benaim–Friz 2009 (MF 19(1),
1–12); Gatheral–Jacquier 2014 (QF 14(1), 59–71); Fengler 2009 (QF 9(4),
417–428); Keelin 2016 (Decision Analysis 13(4), 243–277); Petersen–Müller
2016 (AoS 44(1), 183–218); Neuberger 1994 (JPM 20(2), 74–80); Fritsch–
Carlson 1980 (SINUM 17(2), 238–246); Strassen 1965 (AMS 36(2), 423–439);
Higham 2002; Villani 2003; SciPy 2020; Black 1976 (JFE 3, 167–179);
Branch–Coleman–Li 1999 (SISC 21(1), 1–23).

Verify before print:
- **Gatheral 2004**: cited as a conference presentation (Global
  Derivatives, Madrid) — standard practice for SVI but check the lead is
  happy citing a talk; alternative is Gatheral's 2006 book.
- **Carr–Madan 1998** chapter pages (417–427) in the Risk Books volume —
  believed right, not re-verified against a physical copy.
- **Demeterfi–Derman–Kamal–Zou 1999**: cited as J. Derivatives 6(4), 9–32
  (there is also the longer GS Quantitative Strategies note; the journal
  version is the citable one).
- **Kellerer 1972**: Math. Annalen 198, 99–122 — believed right.
- **Carr–Madan 2005** (Finance Research Letters 2(3), 125–130) — believed
  right.
- **Parzen 1979** (JASA 74(365), 105–121) — believed right.
- SciPy entry uses "and others" — expand the author list if the journal
  demands it.

## Hard-rule self-audit

- **One boxed display**: only eq. (lqd) in §4.  (Checked: no other
  `\boxed` in any file.)
- **Differentiation convention**: primes = one-variable, subscripted
  partials otherwise; declared in Table 1 caption; no `B_k`-style
  subscript-letter derivatives anywhere (Annex B writes
  `\partial_k B` etc.).
- **Figure guard**: every inclusion goes through `\paperfig` (labeled
  placeholder box on missing file).
- **Committee-honesty items**: scope sentence (§1.0 and §5 close);
  tails-as-priors (§6.4, §9.3, §15); calendar control-not-theorem (§11.2,
  §15); discretization-earns-the-theorem (§12.4, §15); median+IQR timing
  (§10, §12.5, Table caption); Petersen–Müller and Keelin acknowledged
  (§1.2, §14) with the "ingredients are classical" positioning (§14 close).
- **No product/repo references**: the implementation is "the reference
  implementation" throughout; no internal names, no note citations.
- **No hand-typed data numbers**: swept twice; the remaining literals are
  mathematical constants (π²/3, 6(log2)²/π ≈ 0.918, log 9 ≈ 2.20,
  36.7 ≈ −log 2⁻⁵³, 709.78 = log DBL_MAX, e^0.05 ≈ 1.051), design
  constants from the defaults table (Z=40, 8001/2001, 700 budget,
  1−10⁻⁶ wall guard, ridge/barrier/haircut constants, 801-point belly
  grid, −10⁻⁴ belly floor, max(49, 4N+1), 15% taper), and the Vogt-dip
  characterization (−0.033 over ≈0.02 in k) which is a property of a
  published SVI counterexample — flag if the lead wants it macro'd or
  cited differently.

## Open questions for the lead

1. **Cold-start bias**: I derive 6(log2)²/π ≈ 0.918 in §4 as a
   mathematical constant and ask the F3 inset to *confirm* it.  OK, or
   macro it too?
2. **The cliff strip vs the snapshot**: §9 quotes the implementation
   study's ~19-quote strip (macros), distinct from the snapshot's NVDA 1d
   node (§13).  Confirm the study fixture is available to the generator,
   or these macros need a source decision.
3. **Canonical node identity**: F5/F7/F8/F9/F12/F14 all anchor on SPY
   2026-12-18 and the ticket is k=+0.05 on that node.  Generator should
   read the node once and share it across figures so every quoted number
   is mutually consistent.
4. **`\MacCalPriceGridWorst`** renders as an inequality (`< 10⁻⁶`) per the
   snapshot README's phrasing; if the generator can compute the actual
   worst, prefer the number.
5. Title is "The Log-Quantile-Density Model of the Volatility Smile:
   Validity, Information, and Convention" — happy to hear alternatives;
   the three-word triad is the paper's spine so it should survive in some
   form.
6. **Benaim–Friz hypothesis precision** (Prop. 6.3, last claim): I invoke
   their limsup→lim upgrade citing regular variation of the return tail,
   which the exact power tails of Prop. 6.1 satisfy.  Someone with the
   paper in hand should confirm the exact hypothesis of the theorem we
   lean on (their conditions are stated via regular variation of the
   tail / mgf and a mild growth condition); the LQD case is about the
   friendliest imaginable, but the citation should name the right
   theorem number at proof stage.

## Theorem/Proposition inventory (for the review round)

Theorems (2): Envelope cancellation (§10, thm:envelope); Calendar order is
ledger order (§11, thm:ledgerorder).
Lemmas (1): Ledger–call conjugacy (§11, lem:conjugacy).
Propositions (9): Martingale normalization (§4, prop:shift); One-expiry
no-arbitrage (§5, prop:noarb); Finite-forward wall (§5, prop:wall);
Universality with exclusions (§5, prop:universal; proof Annex B);
Exponential tails (§6, prop:tails); Moment strip (§6, prop:strip);
Speed-to-slope maps (§6, prop:leeclosed); Ledger pricing (§7,
prop:pricing); Exact ATM handles (§8, prop:atm; proof Annex B).
Definitions (3): Arbitrage-free slice (§2); LQD slice (§4, boxed);
Upper-share ledger (§7).


---

# Round 2 (2026-08-03) — disposition of every objection and ruling

## HARD objections — all ACCEPTED and rewritten

- **O9 (Delta sign — the student is right).** §8's digital-mismatch
  paragraph re-derived from scratch: Delta = u* − Phi(d) = (Black digital)
  − (model digital); null case proved inline (matched lognormal gives
  u* = Phi(d), so Delta = 0 exactly); a left-skewed fit has sigma'(0) < 0,
  hence Delta < 0, hence u* < Phi(d), with the crash-tail mechanism
  spelled out; general rule sign sigma'(0) = sign Delta.  §13.2 and the
  fig_spy_node caption updated (Delta < 0).  **Data note the lead must
  see**: the arbiter ruling's parenthetical said u* for SPY sits above one
  half, but the measured macro \MacSpyDecForwardRankPct = 41.31% — BELOW
  one half.  The text follows the macro: it says u* is below one half AND
  below Phi(d), and uses the symmetric §7 toy (rank 53.34% > 1/2,
  Delta near 0) as the contrast showing the martingale shift owns the
  comparison with 1/2 while the skew owns the comparison with Phi(d).
  Both claims are sign-consistent with \MacSpyDecSkew = −0.430.
- **O11 (calendar premise).** New Lemma (Calendar ordering at equal
  log-moneyness) opens §11: deterministic carry gives one deflator
  M_t = S_t/F_{0,t} with M_{T_i} = Y_i, then tower property + conditional
  Jensen in a three-line display.  States explicitly that equal-k means
  different dollar strikes and that the monetizing trade is the
  forward-scaled calendar spread (cites Carr–Madan 2005).  Adds one lemma
  to the inventory.
- **O7 / A3 (Lee direction, two-sided).** §6.4 and the F9 caption
  rewritten wing-by-wing: near-ATM divergence, then approach governed by
  the wing intercept's sign; SPY Dec call wing overshoots (macros
  1.69/1.05), put wing undershoots (0.70/0.70); conclusion strengthened
  ("the limit misprices the wing in either direction — never price a wing
  off beta").  Truncation rule (price < 1e-13 of forward) stated in the
  F9 and F13 captions.
- **O1 (Durrleman normalization).** §2 now displays the exact
  factorization f_X(k) = g_D(k) phi(d_-)/sqrt(w) with two reader
  checkpoints (flat smile gives g_D = 1 and recovers the Black density;
  ATM cross-check g_D(0) = sqrt(w0) f*/phi(d) via §8) and a section-level
  pinpoint to Gatheral–Jacquier.  §12's belly certificate now states the
  −1e-4 threshold's units (relative to the local Black density factor).
- **O14 / A2 (order control).** §13.4 and both captions rewritten to the
  measured story: N=6 KEEPS both modes (\MacDhModeCountLow = 2) but
  distorts them (peaks overshoot, trough half-filled, modes drift); the
  claim is carried by the L1 doubling (0.047 to 0.108) and the
  mode-location macros; "smooths the trough away" deleted; O16 folded in
  (largest IV gaps beyond the quoted ladder).
- **O17 (figure notation).** Engineer-side relabeling; author side
  verified: no prose leans on any figure-internal symbol (h(u), A, p+/-,
  lowercase psi appear nowhere in the text), and the notation-ledger
  caption now separates g_D from g and Z from Z_max.

## Arbiter items A1–A7 and the addendum

- **A1**: §9.2 gains the live degeneracy example (SPY 0% live bands,
  median spread 4 bp against 2h = 100; NVDA 47%/52% live); §13 intro,
  gallery text, and the F4/F5 captions reworded to raw bid–ask; F5(b)
  described as the residual ladder inside the bid–ask envelope; the F6
  caption now carries the band mechanics.
- **A4 / addendum 1**: §9.5 quotes the multi-start macros (1 basin,
  10 starts x 2 nodes, worst dtheta 2.3e-6, dIV 0.00 bp), scoped as a
  two-node measurement, with the stressed-board caution retained.
- **A5**: F10 caption encoding fixed (true = shaded, recovered = dashed).
- **A6**: all "machine precision" phrasing removed; §4, the F3 caption,
  and §13.5 quote the three measured audit levels and explain the
  near-wall growth of the shift error (decay rate 1 − lambda+ vanishes).
- **Addendum 2 (no cliff)**: §9.4 reframed — identification is the
  principled motivation; the frozen-node over-parameterization probe is
  quoted as FLAT via the Cliff* macros; the historical cliff is stated
  qualitatively (two orders of magnitude in evaluations, tens of
  milliseconds to seconds, book-dependent) with no hand-typed historical
  numerals; the guard is cheap insurance.
- **Addendum 3**: phantom drag labeled as WORST QUOTE ERROR in vol bp.
- **Addendum 4**: §6 and the F8 caption re-pointed to NVDA 2027-12-17
  ("the long NVDA node, December 2027"); added the lambda- = 1.42 > 1
  wall-asymmetry sentence with \MacNvdaLongMomentLeft (E[1/Y] diverges
  while the forward stays finite).
- **Addendum 5**: ticket rewritten around the listed SPY Dec 800 call
  (\MacTicketStrike, \MacTicketK); "5.1% out of the money" deleted.
- **Addendum 6**: \MacFitMsOrderSixteen attributed to the 94-quote SPY
  Dec node; the timing table introduced as the \MacTimingQuoteCount-quote
  synthetic strip; \MacBellyCertMs was already macro-quoted (no 0.05 ms
  text existed).  \MacCalWingPriceOrder retained only as the bound in
  Annex C; §11 quotes the two explicit call-price macros.
- **Addendum 7**: all "one-day/three-day" wording replaced by "the two
  shortest SPY expiries — two and four calendar days"; the NVDA node is
  now "the shortest NVDA node (\MacNvdaOneDayDays calendar days — the
  next session's expiry)"; the §13 subsection retitled.  ("Next-day
  expiry" alone would be wrong: 2026-08-05 is two calendar days after
  the 2026-08-03 reference — hence the chosen wording.)

## SOFT objections — 17/17 ACCEPTED, none declined

O2 Mills-ratio parenthetical (§3).  O3 unshifted-asymptote constants
b-, b+ introduced once in §4 (eq. asymptotes) and used consistently in
prop. shift and prop. tails (prefactor m + b+; the near-collision
symbol "a+" was considered and rejected in favor of spelling out
m + b+).  O4 both receipts inline (m = −pi^2 s^2/6 + O(s^4); E[Z+] =
log 2 via the geometric series).  O5 definition now N >= 2 with the
N >= 4 production convention disclosed.  O6 W_p defined in one sentence
in §5 (quantile form).  O8 inversion line displayed in prop. tails.
O10 barrier units/weight sentence + hinge-kink sentence (relu squared
is C1; the cos^2 care serves the strike-dependent weights).  O12 F13
caption rewritten to the actual two panels, y-axis normalization
sqrt(w/tau_far) defined, truncation + dotted continuation explained,
crossing described as annotated.  O13 beyond-grid asymptote derived
inline (two displayed intermediate expressions).  O15
"demands"/"requires" removed; replaced by the correct two-comparison
statement and "as expected ... since the log contract weights the
wings".  O16 folded into §13.4.  O18 grid half-width renamed Z_max
everywhere (notation table, §12, Annex A listings and defaults).  O19
engineer fixes the dots; the caption was already correct.  O20 caption
now says one secant chord (+ butterfly rel-err macro added).  O21
handled under A6.  O22 fig_tails caption now describes the wall as the
vertical asymptote of the right-tail map.  O23 C_2 defined explicitly
(C_1 e^{sup|m_N|} 2^{lambda-bar} with the two-sided 1 − Lambda bound).

**Q1 (why Legendre)**: answered in §4 — orthogonality under the uniform
rank measure conditions the least-squares normal equations; Chebyshev
comparable, monomials Hilbert-conditioned; labeled a disclosed
convention.

## Beyond the lists

- New §7 worked instance ("A first ticket, on the solvable slice") using
  the engineer's Toy* macros — it makes F1's marked strike roots
  priceable and gives §8's Delta discussion its symmetric contrast.
  ACTION for the engineer/lead: confirm F1's drawn slice is the
  20%-at-6-months toy and its OTM mark is k = 0.10 (assumed; flagged in
  REQUESTED_MACROS Round 2).
- §12's audit paragraph now describes the paper's own 27-slice battery
  (orders via \MacCertOrdersList, equal cells, fixed seed) instead of
  the production battery's shape; the near-wall bound 0.993 (a
  production detail) was dropped.
- Master fallback block updated; macro parity re-verified 117/117 (the late addition is \MacRebuildWorstBp, the Annex C rebuild gate).
- Theorem inventory now: Theorems 2 (envelope cancellation; calendar
  order is ledger order), Lemmas 2 (ledger–call conjugacy; calendar
  ordering at equal log-moneyness), Propositions 9, Definitions 3.


---

# Round 3 (final, narrow) — N1–N5

## N2 (HARD) — closure claim of prop. universal (ii): RESOLVED via option (a), branch added

**Changelog reconciliation first, truthfully.**  The "weakened closure
claim" entry in the round-1 deviations list described a softening made
*during round-1 drafting relative to the internal brief's claim* ("not
even in the closure under these metrics"), not an edit between delivered
rounds.  No round-2 edit of §5.3 ever occurred, and the student is right
that the delivered round-1 and round-2 texts were identical there.  The
deviation entry was accurate about the brief but misleading about the
timeline; this note supersedes it.

**The mathematical resolution.**  Option (a) — the missing branch is now
proved — but with one substantive correction to the student's sketch,
which the lead should see.  The Fatou/escape argument covers the
student's example (constant speeds log(1−1/N): by the paper's own MGF
formula, I_N = pi s_N/sin(pi s_N) → infinity, m_N → −infinity, mass
escapes to −infinity, no weak limit — this is now Annex B's escape
sub-case, two lines via eq. (mgf)).  But escape is NOT automatic on the
whole g_inf(1) = 0 branch: nothing rules out sequences on which the
normalizers stay bounded and the laws remain tight, so "the proposition
survives only vacuously in that branch" would itself have been an
overclaim.  The completed Step 6 therefore proves a dichotomy for the
wall branch: (i) escape can happen (example above); (ii) IF the laws
converge weakly, boundedness of the shifts is forced by tightness,
pointwise quantile convergence identifies the limit, and the limit is a
*boundary law at the wall* — strictly positive continuous density on all
of R (so no atom, no gap, no bounded support, no Gaussian-or-faster
tail), moment strip collapsed to r <= 1, mean <= 1 by Fatou (strict loss
possible).  Not a member of class (i), but not an excluded law either.
Whether the tight sub-case is actually attained by some admissible
sequence is deliberately not claimed in either direction — it is not
needed: the proposition's exclusions hold in both branches regardless.

**Statement/proof now match exactly.**  §5.3(ii) names the convergence
mode (weak convergence of the laws; uniform convergence of the
log-speeds) and states the two-branch dichotomy verbatim as proved:
g_inf(1) < 0 gives class (i) (and weak convergence is proved, not
assumed, in that branch); g_inf(1) = 0 gives escape-or-boundary-law;
"in neither branch is an excluded law reached."

## Copyedits

- **N1**: fig_modes caption now says even modes multiply both scales by
  e^{0.10} while a3 multiplies lambda- by e^{0.10} and lambda+ by
  e^{−0.10} (P_n(−1) = (−1)^n), pointing at the a3 curve ending below
  baseline in panel A.  The §4 body-text echo ("adding 0.10 to a2
  multiplies both") is specific to the even mode and was already
  correct — untouched.
- **N3**: "next-session/next session's expiry" removed in §9.4, §12.5,
  §13.3; the node is now consistently "the shortest NVDA node,
  \MacNvdaOneDayDays calendar days from the reference date".
- **N4**: §9.2 now leads with the correct witness for the universal
  quantifier: "none of the node's bands survives the shrink (live share
  \MacSpyDecBandLivePct\%)" — which IS the statement that every spread
  is tighter than 2h — with the median spread kept as color and no
  phrasing that presumes a nonzero macro value.
- **N5(a)**: fig_exact caption recast as "Panel A / Panel B" (no inset);
  the §4 body reference "visible in the inset" updated to "confirmed in
  panel B".
- **N5(b)**: the §2.2 butterfly half-width renamed h → delta (two
  occurrences plus the display); the ledger's no-reuse sentence
  rephrased honestly: "no ledger symbol is reused with a second
  meaning", with local bound variables (delta, in-proof substitutions)
  explicitly scoped as never entering the ledger.  h now means the
  haircut half-width only.  (Noted, not acted on: "10-Delta" as the
  market's delta unit in §6 coexists with the ledger's digital gap
  Delta; this is universal market idiom, was passed by the student in
  both rounds, and is left alone.)

No other passages were touched.
