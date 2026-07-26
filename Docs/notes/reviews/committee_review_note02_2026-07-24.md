# Committee review — Note 02 (SVI-JW and moments), 2026-07-24

Review of `02_svi_jw_moments.pdf` + TeX by the bank committee (received
2026-07-19, triaged 2026-07-24). Verdict: **more scientifically candid than
Note 01, but the production conclusion is troubling** — after correcting the
diagnostic, 9.2% of historical SVI fits still exhibit genuine belly butterfly
violations, so the current implementation is "suitable as a diagnostic
overlay, not as an unconditional source of marks, Greeks, digitals, densities,
or moments." The decisive revision demanded: move from *"the remaining belly
problem is measured"* to **"an uncertified slice cannot become a mark."**

This file preserves the review verbatim (below) plus the triage, so the
revision arc can be resumed without the original conversation.

## Triage (2026-07-24 — workstream order PROPOSED, awaiting ratification)

Every checkable claim was verified against the code, the TeX source, and
numerically. The committee is right on all of the mathematics and on every
code fact it cites; the pushbacks below are about what is actually shipped
(no JW/moment product surface exists) and about which fixes are new work vs
already-built machinery.

### Verification results, by challenge

1. **β=2 proposition — CONFIRMED (mathematically false at equality).**
   Numerics: their counterexample `(a,b,ρ,m,s) = (0.04, 2, 0, 0, 0.2)` has
   w\* = 0.44 > 0, β_L = β_R = 2 (both shipped screens pass with ZERO
   penalty), yet Durrleman g(10) = −0.04852, matching their asymptotic
   (α−2)/(4k) = −0.049 — and g < 0 at every k ∈ {5, 10, 20, 50} checked:
   the tail density is genuinely negative while the slice is "Lee-clean".
   The note's Prop. states "each tail stays non-negative iff β ≤ 2"
   (02_svi_jw_moments.tex:265-267) — false at β = 2, where the limit
   (4−β²)/16 = 0 is sign-inconclusive and the next-order term (α−2)/(4k)
   decides (the note is already strict, β_R < 2, for the call-price boundary
   two lines later). Shipped code: `_LEE_SLOPE_MAX = 2.0` with hinge
   `max(wing − 2, 0)` (models/svi_jw/calibrate.py:49,110) — zero exactly on
   the broken boundary, as the committee says.
2. **Moment map missing / conditional — CONFIRMED.** Their inverse map
   round-trips Lee's p\* = (2−β)²/(8β) exactly (checked at β = 0.5, 1.0,
   1.5, 1.99). The note never states it. "No moment displayed unless
   globally certified" — accepted as policy; NB nothing ships moments today
   (see pushbacks).
3. **w\* is a belly condition mislabeled as a tail screen — CONFIRMED.**
   The note groups the floor and Lee rows as "both cheap tail screens" /
   "the tail screens" (lines 368, 388, 1055) while its own JW section
   classifies ṽ as a belly handle. Internal inconsistency; relabel (floor
   screen + wing screens) and adopt their 5-tier hierarchy wording.
4. **JW does not separate tails from belly — CONFIRMED from shipped code.**
   From `jw_to_raw` (models/svi_jw/svi.py): b = ½√w₀(p+c),
   ρ = (c−p)/(c+p) ⇒ β_L = p√(vτ), β_R = c√(vτ). An ATM-level bump holding
   (p, c) fixed moves BOTH actual Lee slopes and hence the inferred moments.
   Accept: normalized-indicators vs actual-slopes distinction + the 5×5
   bump-response figure.
5. **The cleaner global chart — ALGEBRA VERIFIED, ADOPT AS OPT-IN.** Their
   (β_L, β_R, k\*, w\*, κ\*) → (a, b, ρ, m, s) identities all check out
   (b = (β_L+β_R)/2, ρ = (β_R−β_L)/(β_R+β_L), s = b(1−ρ²)^{3/2}/κ\*,
   m = k\* + sρ/√(1−ρ²), a = w\* − bs√(1−ρ²); w\* = min-variance identity
   already in `_penalties`). With logistic/softplus lifts it makes every
   finite optimizer point positive-floor and STRICTLY Lee-clean — killing
   the floor penalty, the Lee penalty, the trial-w clip, and the W-units
   problem structurally. This is the exact playbook of Note 01's R1
   (logistic chart), which we adopted and made default after equivalence
   checks — same precedent applies: opt-in chart first, default flip only
   after a benchmark (the fits are NOT byte-identical where penalties were
   active, and conditioning near |ρ|→1 needs the same scrutiny they demand
   in challenge 9).
6. **Production ships screens the note proves insufficient — CONFIRMED;
   the direction is accepted.** The four-layer stack is exactly as cited
   (tex:394-416; core screens always-on / extrapolated-region enforcement
   opt-in default OFF / advisory diagnostics / export-only wing projection
   with the core pinned), and the note itself concedes "none of these turns
   a fitted SVI slice into a certified butterfly-free object". The 9.2% /
   24.3 / 26.8 bp figures are hardcoded HISTORICAL constants in the figure
   generator (gen_svi_moments.py:80-90 "not recomputed by this script"),
   from the frozen benchmark parquet — the committee's reproducibility
   complaint stands. Accept their own suggested resolution: benchmark a
   post-fit certificate + repair/restart path (core fit ≈ 1.8 ms, so
   "certification is unaffordable" indeed needs evidence, not assertion).
7. **The rigidity benchmark is itself arbitrageable — CONFIRMED.** The
   generator's two-minimum target (gen_svi_moments.py:186) gives
   g(0) = −0.05893 by direct computation. Partial defense: the figure's
   POINT (one convex hyperbola cannot reproduce a non-convex w) survives,
   but the 147.6 vol-bp miss must not be quoted as an expressiveness
   deficit against a legal target. Replace with a martingale-normalized
   mixture + report the committee's five-metric panel with comparators.
8. **ψ=0 singularity + unguarded converter — CONFIRMED.** `jw_to_raw` has
   zero domain checks (svi.py:54-67: |χ| ≥ 1 → NaN through
   √(1−χ²); ψ = 0 stratum; no structured failures) and the note's caution
   (tex:669+) says so verbatim. Accept: validate-with-reasons or make it
   private; condition atlas is a note-revision item.
9. **Optimizer less smooth than prose — MECHANICS CONFIRMED.** The
   w ≤ 1e-12 floor zeroes the data-Jacobian rows (the note SAYS so,
   tex:745: "zeroed wherever the floor is active"; `max(w, 1e-12)` in
   calibrate.py:196); hinge subgradients are the documented convention.
   The adversarial battery they list (<5 quotes, one-sided, missing ATM,
   crossed, 0DTE, event kinks, |ρ|≈1, rank-deficiency, eval-cap) is
   accepted as a stress battery; NB part of the input side is already
   handled upstream (quote quarantine, degraded mode, tick floors) — the
   battery should test the SVI slice path specifically.
10. **W=1000 unit mismatch — CONFIRMED** (`_PENALTY = 1e3` multiplies a
    total-variance row and a dimensionless-slope row; the note's caution
    admits the mismatch and leaves it). Resolution: structurally, via the
    challenge-5 chart (penalties disappear), not by unit juggling.
11. **Desk controls not desk instruments — ACCEPT (UI/note layer).**
    v is variance, ψ is total-vol slope, p/c are normalized variance
    slopes; no RR/BF/delta conversions, no forward-bump sensitivity.
    Production today displays only the model-agnostic ATM/skew/curv
    handles (the note's caution) — the trader layer is a design item for
    IF/WHEN JW handles ship.
12. **One canonical surface — PARTIAL, governance questions legitimate.**
    Production has ONE displayed object per slice, but the publish-time
    projection means exported wing prices CAN differ from the displayed
    raw curve — the committee's "can a trader arbitrage one representation
    against another" is a fair audit demand. Fold into the acceptance-rule
    work: canonical post-repair object policy + a calendar audit of the
    wing projection.

### What the committee did not know (pushbacks recorded)

- **There is no JW or moments product surface.** No `raw_to_jw`, no
  five-handle API/UI, no JW bumping/export, no moment or digital
  publication — the note's own caution states this and the verdict quotes
  it. Challenges 2/11 therefore gate FUTURE surfaces; nothing currently
  shipped displays an uncertified moment.
- **The candor they praise is the same machinery they indict.** The 9.2%
  number exists because the advisory layer measures the belly honestly; the
  four-layer stack was built knowing the core screens are tail-only. The
  disagreement is the acceptance RULE, and for bank marks the committee is
  right — which is why R2 below is the arc's centerpiece rather than a
  rebuttal.
- **The acceptance-rule skeleton already exists**: publish gates
  (PublishBlockedError), the certification pack, quote quarantine, the
  extrapolated-region tail certificates (Notes 09/10). The new work is the
  BELLY certificate + the certified/repaired/rejected rule, not a new
  governance layer.
- **Challenge 5 is the Note-01 R1 playbook repeated** (structural chart
  replaces penalties) — we have the precedent, the equivalence-lock
  pattern, and the benchmark harness to adjudicate a default flip.

### Workstreams (proposed order)

1. **R1 — strict Lee buffer + proposition repair (DONE 2026-07-24).**
   Default cap = 2 − LEE_SLOPE_BUFFER = **1.95** (calibrate.py, FitSettings,
   frontend defaults; the backtest harness stays PINNED at 2.0 for
   part-comparability). Spot-check on the reference live fixture (12 real
   SPY/NVDA/AAPL nodes): **SPY 2026-08-21 was sitting EXACTLY at wing =
   2.0000 under the old cap** — the committee's trap was live in
   production; the buffered refit lands at 1.9500 with max IV change
   0.03 vol bp, and the other 11 nodes are byte-identical. ε rationale:
   at 1.95 the excluded laws have moment budget p\* < 2e-4 beyond the
   first moment, and the tail limit is strictly positive (0.0123).
   Proposition restated in the note (strict trichotomy + the next-order
   boundary law g = (α−2)/(4k) with proof + counterexample caution box);
   intro/invariant/tier-table de-weakened; macros regenerated
   (\svimomleecap 1.95, fresh single-run timings 1.30/3.12 ms = 2.40×);
   PDF rebuilt. Locks: tests/test_svi_lee_boundary.py (3 tests: the trap,
   the buffered defaults everywhere, the fence + explicit-config escape
   hatch) = certification case **svi_lee_boundary** (model_stress).
   CAVEAT: installs with previously SAVED fit settings keep the persisted
   2.0 (full-snapshot persistence) until re-saved — the dev store
   backend/data/volfit.sqlite is in that state.
2. **R2 — belly certificate + acceptance rule (DONE 2026-07-24, v1).**
   `belly_certificate` (models/diagnostics.py): dense 801-point Durrleman-g
   over the TRADED range from the model's own curve — the region the wing
   screens miss and the projection never touches. Cost measured ≈0.05 ms
   per slice (vs the ~1.8 ms fit: the committee's affordability challenge
   answered with a number). Wired NON-advisory into quality
   (`bellyMinG`/`bellyArgminK`/`butterflyCertified`; uncertified fails
   `ready`) and into the export publish gate (`_node_blockers` →
   PublishBlockedError/409 naming the node + min g; `allow_dirty` still
   exports a stamped DRAFT). The published-family calendar audit
   (`projectionCalendarWorstBp` on the manifest, blocker past 1 bp)
   answers "can the projection introduce calendar crossings?" on every
   artifact. Canonical-object policy stated in export.py's module
   docstring (published projected curve = THE object; displayed core
   byte-identical; lqdParams = fit lineage). Note's four-layer stack
   updated to five (certificate = the gate). Locks:
   tests/test_belly_certificate.py (Vogt fails where screens pass; clean
   certifies + cost rail; end-to-end certify+publish; forced-uncertified
   409 + draft escape) = certification case **belly_certificate**.
   Riders → R3: the belly-hinge repair-refit (today: repair = refit with
   enforcement or fall back; the structural chart changes the same
   objective) and the exact Martini–Mingone certificate as a
   cross-check tier; Quality-view UI chip for the verdict.
3. **R3 — structural chart + belly repair (DONE 2026-07-24, opt-in).**
   `models/svi_jw/structural.py`: (β_L, β_R, k\*, w\*, κ\*) with
   logistic(·cap)/softplus/exp lifts — every finite iterate strictly
   positive-floor and strictly Lee-clean under the R1-buffered cap; the
   penalty rows are structurally zero and the trial-w clip never fires.
   `calibrate_svi(chart=...)` via `FitSettings.sviChart` (default "raw"
   until the benchmark adjudication; FD Jacobian for the structural
   chart — analytic chain is the adoption follow-up). SPOT-CHECK
   (reference fixture, 12 real nodes): charts agree to 0.0000 bp
   wherever the raw chart converged — but the raw chart EXHAUSTED its
   500-evaluation cap on 5/12 real nodes (challenge 9's concern, live)
   while the structural chart converged in 30–86 evals on all 12, and
   was ~3× FASTER overall (82 vs 233 ms) despite FD. Strong prima facie
   case for the default flip; the frozen-regime benchmark remains the
   deciding evidence. Also shipped the R2 repair rider:
   `bellyRepair` (default ON) — a failed certificate triggers ONE
   belly-hinge refit (`belly_grid` rows `W·max(−g+2e-4, 0)`, closed-form
   g), kept only if it re-certifies; Vogt-sampled quotes repair to a
   certified slice at ~460bp worst-quote cost (the slice is
   pathologically deep); clean first fits never see a second solve.
   `DisplayFit.belly_repaired` → quality `bellyRepaired`. All 12 real
   nodes certify (min g +0.026…+0.33). Locks:
   tests/test_svi_structural_chart.py (chart algebra/round-trip,
   clean-fit equivalence, fence-without-penalties, Vogt repair
   end-to-end) — added to the belly_certificate certification case.
4. **R4 — Note 02 revision (DONE 2026-07-26).** New generator
   `gen_svi_committee.py` (4 figures + macros, all from production
   modules): (a) **moment map** §"The moment map, and when a moment may
   be shown" — eq. both directions, conditioning figure (|dp\*/dβ| ~
   1/(2β²) explosion at 0, collapse to p\*=1.6e-4 at the buffered cap),
   policy = moments certificate-gated like marks; (b) **bump-response
   matrix** — +Δv moves β_R by +0.0017 and p\*_R by −0.60 with (p,c)
   fixed: JW = normalized quoting convention, not an orthogonal
   decomposition (challenge 4 quantified); (c) **arb-free expressiveness
   benchmark** — martingale two-lognormal mixture (target min g +0.389
   verified): SVI 118.7bp RMS vs LQD 19.7 / MCS 15.0 (held-out ≈
   in-sample; all three FITS certify — SVI's miss is expressiveness,
   not arbitrage); old two-min figure recaptioned honestly (its target
   has g(0)≈−0.059; measures convexity rigidity only); eSSVI/spline
   column = recorded outstanding work; (d) **condition atlas** over the
   (ψ, p+c) wedge w/ the 12 real nodes overlaid — nearest node at
   |ψ|=0.059 AND short-dated nodes at p+c ~ 10-100 where the chart is
   ill-conditioned (1e5-1e7) everywhere. Hierarchy relabeled (5 honest
   tiers; "tail screens" phrasing removed; slogan revised to "fence the
   floor and the wings; the belly needs a certificate"); structural-
   chart subsection added to §calibration (spot-check evidence incl.
   the 5/12 eval-cap exhaustion); historical replay numbers already
   labeled not-checked-in. PDF rebuilt clean.
5. **R5 — guarded converter + desk layer + adversarial battery (DONE
   2026-07-26).** `jw_to_raw_checked` promoted to production
   (models/svi_jw/svi.py): complete-domain validation with structured
   `JWDomainError` reason codes (six inequalities incl. the singular
   stratum, rejected explicitly), the Appendix-D cancellation-resistant
   denominator (round-trips the five functionals at ψ=1e-5); the
   unguarded fast path stays documented-unsafe for validated callers.
   Desk layer (models/svi_jw/desk.py): DeskTicket = ATM convention +
   25/10Δ RR/BF solved on the model smile via forward Black delta +
   ACTUAL wing slopes + var-swap vol; `forward_bump` = the committee's
   missing derivative (a +1% F error on a put skew reads as a phantom
   HIGHER ATM + RR move — sign verified; a flat smile reads zero; a
   k-symmetric smile has POSITIVE 25Δ RR, the delta-convention subtlety
   the layer exists to expose). No JW UI ships; the layer is the
   contract any future one sits behind. Adversarial battery
   (challenge 9, BOTH charts): 1-2 quote boards now refuse
   DETERMINISTICALLY with a reason (calibrate_svi guard — previously a
   raw scipy crash), one-sided chains / missing ATM / 0DTE-scale w /
   |ρ|≈1 / duplicate strikes / 50% noise / crossed bands /
   eval-cap exhaustion all finite + fence-respecting (structural chart:
   fences exact). Locks: tests/test_svi_desk_and_guards.py +
   tests/test_svi_adversarial.py (17 tests) = certification case
   **svi_adversarial_inputs**. Note caution updated; PDF rebuilt.

Deferred: equal-snapshot cross-model market evidence (rides the existing
benchmark-pack campaigns); hedge-P&L (the standing deferred campaign, shared
with Note 01's arc).

---

## The review (verbatim)

## Committee verdict on Note 02

This note is more scientifically candid than Note 01. The distinction between structural SVI, positive total variance, tail admissibility, butterfly freedom, and calendar freedom is excellent; the Axel Vogt example is exactly the warning a quant should see.

But the production conclusion is troubling: after correcting the diagnostic, **9.2% of historical SVI fits still exhibited genuine belly butterfly violations**. For a bank marking model, that outweighs the 2.29× Jacobian speed-up. The current implementation is suitable as a diagnostic overlay, not as an unconditional source of marks, Greeks, digitals, densities, or moments.

Reviewed: [rendered note](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.pdf) and [TeX source](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex).

## The most important challenges

### 1. The proposition at \(\beta=2\) is mathematically false

The note proves only

\[
\lim_{|k|\to\infty}g(k)=\frac{4-\beta^2}{16}.
\]

It then concludes that the tail density remains non-negative iff \(\beta\le2\) ([Proposition 2](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:257)). At \(\beta=2\), however, the limit is zero and says nothing about the sign of the next term.

For a right SVI wing

\[
w(k)=2k+\alpha+O(k^{-1}),\qquad \alpha=a-2m,
\]

one obtains

\[
g(k)=\frac{\alpha-2}{4k}+O(k^{-2}).
\]

So it may approach zero from below. A direct counterexample is

\[
(a,b,\rho,m,s)=(0.04,2,0,0,0.2).
\]

It has \(w_\star=0.44>0\) and \(\beta_L=\beta_R=2\), yet \(g(10)\approx-0.0485\).

The correct statement is:

- \(\beta<2\): \(g\) is eventually positive;
- \(\beta>2\): \(g\) is eventually negative;
- \(\beta=2\): the leading limit is inconclusive, and the right-call boundary fails anyway.

The default cap is exactly \(2.0\), and its hinge is zero at equality. It should be a strict buffered constraint such as \(\beta\le2-\varepsilon_\beta\).

### 2. “Moment-controlled” is conditional on global butterfly freedom

Lee’s formula applies to a genuine arbitrage-free distribution. A tail-clean SVI curve with \(g<0\) in the belly has no risk-neutral law; therefore its wing slopes cannot legitimately be called the moments of that law.

At most they are candidate moment indicators, conditional on the slice first passing a global butterfly certificate.

The note also never writes the actual moment map. For \(0<\beta\le2\),

\[
\beta
=2-4\left(\sqrt{(p^\star)^2+p^\star}-p^\star\right),
\qquad
p^\star=\frac{(2-\beta)^2}{8\beta},
\]

with the corresponding right and left critical-moment conventions.

This should be central to a note titled “moments.” It should also show conditioning:

- as \(\beta\to0\), the inferred moment explodes and is highly unstable;
- as \(\beta\to2\), the moment budget collapses;
- small quote-window changes can create large inferred-moment changes.

No moment should be displayed unless the slice is globally certified.

### 3. The minimum-variance screen is a belly condition, not a tail condition

The paper repeatedly calls

\[
w_\star\ge0,\qquad \max(\beta_L,\beta_R)\le2
\]

the “two tail screens” ([validity hierarchy](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:343)). But \(w_\star\) is attained at the hyperbola’s vertex and \(\widetilde v=w_\star/\tau\) is explicitly classified as a belly handle.

The honest hierarchy is:

1. Structural hyperbola: \(b>0,\ |\rho|<1,\ s>0\).
2. Positive total variance: \(w_\star>0\), a global vertex/belly condition.
3. Admissible asymptotic boundaries: strict Lee caps, a tail condition.
4. Butterfly freedom: \(g(k)\ge0\) globally plus price boundaries.
5. Calendar freedom across expiries.

This correction weakens the slogan “every cheap guarantee lives in the wings,” but makes the mathematics internally consistent.

Also, a finite penalty does not “forbid” negative total variance; it penalizes it.

### 4. JW does not actually separate tail and belly

The note defines

\[
p=\frac{\beta_L}{\sqrt{w_0}},\qquad
c=\frac{\beta_R}{\sqrt{w_0}},
\]

hence

\[
\beta_L=p\sqrt{v\tau},\qquad
\beta_R=c\sqrt{v\tau}.
\]

Thus \(p,c\) do not determine the actual tails without the supposedly belly-only level \(v\). An ATM-level bump holding \(p,c\) fixed changes both Lee slopes and inferred moments.

JW is a useful normalized quoting convention, not an orthogonal decomposition into two independent tails and three independent belly coordinates. The note should distinguish:

- normalized wing indicators \(p,c\);
- actual asymptotic slopes \(\beta_L,\beta_R\);
- moment exponents;
- the effects of holding one set fixed while bumping another.

A five-by-five bump-response figure would help: show changes in ATM, 25d/10d RR and BF, \(w_\star\), actual wing slopes, moments, density, and var swap.

### 5. There is a cleaner global parameterization

The current unconstrained chart structurally guarantees only

\[
b>0,\quad |\rho|<1,\quad s>0,
\]

then relies on two unit-incompatible penalties, a trial-\(w\) floor, and optional repairs.

A stronger generic chart is

\[
(\beta_L,\beta_R,k_\star,w_\star,\kappa_\star),
\qquad \kappa_\star=w''(k_\star)>0.
\]

The raw parameters follow exactly:

\[
b=\frac{\beta_L+\beta_R}{2},\qquad
\rho=\frac{\beta_R-\beta_L}{\beta_R+\beta_L},
\]

\[
s=\frac{b(1-\rho^2)^{3/2}}{\kappa_\star},\qquad
m=k_\star+\frac{s\rho}{\sqrt{1-\rho^2}},
\]

\[
a=w_\star-bs\sqrt{1-\rho^2}.
\]

Then parameterize

\[
\beta_L=(2-\varepsilon)\operatorname{logistic}(\ell),\qquad
\beta_R=(2-\varepsilon)\operatorname{logistic}(r),
\]

\[
w_\star=\operatorname{softplus}(h),\qquad
\kappa_\star=e^q.
\]

Every finite optimizer vector now has:

- strictly positive total variance;
- strict Lee-clean wings;
- actual, unnormalized tail coordinates;
- explicit belly location, floor, and curvature;
- no trial-\(w\) clipping;
- no floor or Lee penalty;
- no JW singularity at \(\psi=0\).

It still does not guarantee \(g\ge0\), but it removes several layered remedies and matches the note’s own tail/belly philosophy much better.

For trader-facing coordinates, ATM level/skew/curvature plus \(\beta_L,\beta_R\) may be preferable and would align with the model-agnostic handles used elsewhere.

### 6. Production demonstrates the inadequacy of its screens, then ships them

The note’s strongest figure is Axel Vogt’s counterexample: positive total variance, convex \(w\), harmless Lee slopes—and negative belly density.

But production nevertheless uses only those insufficient core screens. Full enforcement is optional and off by default; the diagnostic is advisory; and the export projection changes only sampled wings while leaving the core pinned ([four-layer stack](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:394)).

The reported corrected violation rate is 9.2% ([lines 419–430](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:419)). That is approximately one fit in eleven.

For model approval, every published slice should:

1. pass an exact or certified global Durrleman test;
2. be repaired coherently;
3. or be rejected in favour of a deterministic fallback.

The exact Martini–Mingone domain is already cited. If enforcing it during every LM iteration is deemed expensive, benchmark a post-fit certificate and repair/restart path. With a core fit around 1.8 ms, the claim that certification is operationally unaffordable needs evidence.

### 7. The rigidity benchmark is itself arbitrageable

The two-minimum target behind Figure 9 is

\[
w(k)=0.018+0.050k^2-0.010k
+0.010e^{-(k/0.095)^2}
\]

([generator line 186](C:/Users/thiba/Vol-Fitter/Docs/notes/figures/gen_svi_moments.py:186)). Substitution into the note’s own Durrleman formula gives

\[
g(0)\approx-0.0589.
\]

So the target is butterfly-arbitrageable. The reported 147.6-vol-bp SVI miss does not demonstrate a commercially meaningful expressiveness failure; an arbitrage-aware model should refuse to reproduce that target.

Replace it with an unquestionably arbitrage-free multi-turn benchmark generated from a genuine distribution—for example, a martingale-normalized mixture—and report:

- minimum \(g\);
- call-price boundaries;
- density error;
- held-out quote error;
- comparison with LQD, eSSVI, and a constrained spline.

The present example proves only that one convex hyperbola cannot fit an arbitrary non-convex function.

### 8. JW’s singularity occurs at an ordinary market shape

The theorem describing the \(\psi=0\) stratum is excellent. But ATM sitting at the smile minimum, or nearly flat ATM skew, is not exotic. It is precisely where a trader would expect a coordinate system to be simplest.

Near \(\psi=0\),

\[
D=O(\psi^2),\qquad v-\widetilde v=O(\psi^2),
\]

so quote noise and rounding are strongly amplified. Other ill-conditioned boundaries deserve similar treatment:

- \(p+c\to0\);
- \(p\to0\) or \(c\to0\), giving \(|\rho|\to1\);
- \(v\to0\);
- \(\psi\to-p/2\) or \(c/2\);
- \(\widetilde v\uparrow v\) along an incompatible path.

Add a condition-number atlas and market-frequency study. The unguarded `jw_to_raw` converter should either be made private or validate the complete domain and return structured failure reasons ([product caution](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:669)).

### 9. The optimizer is less smooth and robust than the prose suggests

The mathematical reparameterization is clean, but floating-point and LM see:

- softplus underflow;
- `tanh` saturation at \(\pm1\);
- exponential underflow/overflow in \(s\);
- \(q=\sqrt{1-\rho^2}\) near singularity;
- a trial-\(w\) clipping kink;
- zero IV derivatives where the floor is active;
- floor and Lee hinges;
- \(|\rho|\) at zero;
- bid/ask hinges.

In particular, when trial \(w\le10^{-12}\), the data Jacobian is set to zero ([lines 698–760](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:698)). That creates a flat artificial region in which only the large feasibility penalty points the optimizer back.

“LM crosses kinks faster than TRF” is an empirical observation, not a robustness guarantee. The note needs adversarial tests for:

- fewer than five usable quotes;
- one-sided chains;
- missing ATM;
- zero bids and crossed markets;
- 0DTE or almost-zero total variance;
- event kinks;
- extreme starts and \(|\rho|\approx1\);
- rank-deficient Jacobians;
- evaluation-cap exhaustion.

A deterministic last-good-surface or fallback-model policy is essential.

### 10. Penalty scaling is economically arbitrary

The same multiplier \(W=1000\) acts on:

- a total-variance violation;
- a dimensionless wing-slope violation.

The note admirably admits the unit mismatch ([lines 450–460](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:450)), but does not resolve it. Its economic strength also changes with maturity: a short-dated variance violation can be numerically tiny even when its annualized-vol consequence is material.

This is another reason to enforce floor and Lee admissibility structurally rather than through common residual scaling.

### 11. The desk controls are not desk instruments yet

The units in Figure 5 are explained unusually well. But they reveal that:

- \(v\) is variance, not quoted ATM volatility;
- \(\psi\) is total-volatility slope, not plotted IV slope;
- \(p,c\) are asymptotic normalized variance slopes, not 25d/10d vols;
- \(\widetilde v\) may occur outside the liquid strike window.

A trader-facing layer needs explicit conversion to ATM convention, RR, BF, delta convention, and sticky-strike/sticky-delta shocks. It should also state exactly which quantities remain fixed under each bump.

Forward sensitivity is missing. An error in \(F_T\) shifts every \(k\) and is easily misread as \(m,\rho,\psi\), or wing movement—particularly around dividends, borrow stress, and corporate actions.

### 12. One canonical surface is required

The note describes raw SVI fits, advisory diagnostics, optional extrapolation fences, and a publish-time projection that raises exported wing prices while leaving the core fixed.

That creates unanswered governance questions:

- Which object supplies marks?
- Which supplies Greeks?
- Which supplies moments and var swap?
- Can the projection introduce calendar crossings?
- Does the displayed raw curve differ from exported prices?
- Can a trader arbitrage one representation against another?

A bank needs one canonical post-repair object for prices, Greeks, diagnostics, risk, and export, followed by a global butterfly and calendar audit.

## Evidence still needed

The exact SVI-to-SVI round trip correctly validates implementation, but not modelling. The only live figures—24.3 vol bp in-sample, 26.8 out-of-sample, the 9.2% arbitrage rate, and a historical 2.58× speed-up—depend on unavailable historical parquet files ([lines 814–871](C:/Users/thiba/Vol-Fitter/Docs/notes/02_svi_jw_moments.tex:814)).

Add:

- fit-in-spread and price-error distributions;
- equal-snapshot comparisons with eSSVI/SSVI, LQD, and constrained splines;
- hold-out and leave-one-strike-out tests;
- quote-window and quote-perturbation tail fans;
- static-arbitrage magnitude and location, not just incidence;
- rolling stability of ATM, density, digitals, wings, and moments;
- next-snapshot repricing and hedge P&L;
- explicit event, 0DTE, sparse, and dividend subsets;
- end-to-end CPU including cleaning, certification, calendars, fallback, and export.

The analytic Jacobian is a genuine strength: 4.15 ms to 1.81 ms on the stated microbenchmark. But it is a constant-factor improvement for a fixed five-parameter model, and optional blocks disable or hybridize it.

## Questions we would insist the author answer

1. Why can a slice with known \(g<0\) still become a displayed or published surface?
2. What is the hard post-fit acceptance rule and deterministic fallback?
3. Why is the shipped cap \(2.0\) when the note itself requires a strict right boundary?
4. Why not parameterize \(w_\star\) and \(\beta_L,\beta_R\) structurally?
5. How expensive is the exact Martini–Mingone certificate?
6. Are moments suppressed whenever global butterfly certification fails?
7. Why use normalized \(p,c\) rather than actual wing slopes as tail controls?
8. Why is \(\widetilde v\) preferable to ATM or vertex curvature?
9. How frequent and unstable is the \(\psi\approx0\) region on real chains?
10. What happens with fewer than five good quotes, zero bids, a bad forward, or 0DTE?
11. Which single surface supplies marks, Greeks, moments, calendars, and exports?
12. Can the 24.3/26.8-vol-bp and 9.2% results be reproduced from checked-in data?

## What should be preserved

- The distinction between convexity of \(w\) and convexity of option price.
- The Axel Vogt counterexample and four-tier validity table.
- The raw-SVI geometric derivations.
- The JW image theorem and quadratic singularity analysis.
- The unusually careful treatment of units and clocks.
- The explicit separation of code validation from market evidence.
- The analytic Jacobian derivation and performance measurement.
- The candid product-status and converter warnings.

The decisive revision is conceptual: move from “the remaining belly problem is measured” to **“an uncertified slice cannot become a mark.”**
