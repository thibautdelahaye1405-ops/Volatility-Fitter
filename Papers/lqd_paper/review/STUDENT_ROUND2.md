# Student review — round 2

Same persona and rules as round 1. I re-read every revised section in full, re-did the
new derivations by hand (the g_D factorization, the §8 sign chain, the §11 lemma, the
b± asymptote bookkeeping, the C₂ construction, the beyond-grid subtraction, the §7 toy
ticket's Jensen claim), and re-opened the figure PDFs (fig_transport, fig_modes,
fig_tails, fig_lee, fig_exact, fig_order_control, fig_doublehump, fig_spy_node,
fig_nvda_nodes, fig_butterfly, and fig_calendar/fig_spy_gallery against their new
captions). Severity scale unchanged: BLOCKING / HARD / SOFT.

## Part 1 — Round-1 resolution check

| # | Round-1 objection | Status | Verification notes |
|---|---|---|---|
| O1 | Durrleman "proportional to" unstated factor | **RESOLVED** | The new factorization f_X(k) = g_D(k)·φ(d₋(k,w(k)))/√w(k) is **correct — I re-derived it from scratch**: expanded all five general-k Black partials (∂_kB = −e^kΦ(d₋) exactly, etc.), formed e^{−k}(c″−c′), and recovered g_D term by term, including the k²w′²/4w² and −w′²/16 pieces. Both checkpoints verify: flat smile gives g_D ≡ 1 with f_X(k) = φ((k+w/2)/√w)/√w = the exact Black density of X; the ATM checkpoint g_D(0)=√w₀f_X(0)/φ(d) is the identity I derived myself in round 1. The belly-certificate threshold now has stated units through the same factorization (§12.4). Model answer. |
| O2 | Gaussian q(u) asymptotic needs Mills ratio | **RESOLVED** | Parenthetical added with Φ(x) ~ φ(x)/\|x\|, correctly stated for x → −∞. |
| O3 | m^± reused for x and x̄ constants | **RESOLVED** | New eq. (asymptotes) introduces b± for the unshifted transport, states the shifted constants are m+b±, and explicitly warns "the tail prefactor of prop. tails contains m+b₊, not b₊" — and prop. tails now indeed carries K₊ = e^{(m+b₊)/λ₊}. I checked b₋ exists (the deviation integral ∫⁰₋∞ O(e^t)dt converges). |
| O4 | E[Z⁺] = log 2 and small-s steps unproved | **RESOLVED** | Receipts supplied: m = −π²s²/6 + O(s⁴) and the geometric-series computation Σ(−1)^{n−1}/n = log 2 — both correct (they match my own round-1 derivations). |
| O5 | "N ≥ 4" unexplained in the definition | **RESOLVED** | Definition now N ≥ 2; N ≥ 4 explicitly labeled an implementation convention aligned with the ridge. Bonus: my Q1 (why Legendre) is answered — orthogonality under the uniform rank measure = the least-squares inner product, monomials → Hilbert-matrix conditioning, "Chebyshev would serve comparably". That is exactly the sentence I asked for. |
| O6 | Wasserstein-p undefined for the stated audience | **RESOLVED** | Concrete quantile form W_p^p = ∫₀¹\|Q_μ−Q_ν\|^p du now inline in prop. universal(i), with the "rank by rank" reading. |
| O7 | fig_lee left panel contradicted "descends from above" | **RESOLVED** | §6.4 is now genuinely two-sided: the w(k) ≈ β\|k\| + const intercept mechanism, overshoot on the call wing, undershoot on the put wing, ratios below one stated as below one; the caption and §1's triad item were both updated to "in either direction, on one and the same fitted slice". This now matches the figure exactly (put diamonds at ≈0.125 under β=0.179; call side above 0.034). The revised warning ("the limit overstates one wing and understates the other") is the stronger, correct conclusion. |
| O8 | prop. tails inversion step skipped | **RESOLVED** | The inversion is now explicit, including why the error keeps its exponential form (same ε moved across, divided by λ₊). |
| O9 | **Δ sign backwards** (my #1) | **RESOLVED** | The rewritten §8 paragraph is now correct and I verified each leg: (i) *null case*: for X ~ N(−w₀/2, w₀) matched at the ATM price, w₀ recovers the lognormal's own variance and u* = P(X≤0) = Φ(√w₀/2) = Φ(d), so Δ = 0 exactly — checked; (ii) *skewed case*: σ′(0)<0 ⟹ Δ<0 ⟹ u* < Φ(d), the model digital rich vs flat-Black — this is precisely my round-1 derivation, and it now agrees with §13 (u* below one half AND below Φ(d), σ′(0) measured negative) and with the fig_spy_node caption ("negative digital mismatch Δ<0"); (iii) the "not claimed" parenthetical correctly separates u* vs ½ (owned by the martingale shift; the §7 toy has u* > ½ with Δ ≈ 0) from u* vs Φ(d) (owned by the skew). The sign discipline is now airtight across §7, §8, §13, and the figure caption. |
| O10 | Barrier units / hinge kink | **RESOLVED** | Barrier disclosed as dimensionless, unit weight, order-one within a few hundredths past 0.90 (checked: log(1+e¹) ≈ 1.31 at λ₊ = 0.92); hinge argument correct — ((x)⁺)² is C¹, so the summed objective's gradient is continuous even though the residual's Jacobian jumps at an edge where the residual is zero. The contrast with the calendar cos² taper (which smooths *weights*) is a genuine explanation, not hand-waving. |
| O11 | eq. calreq asserted, not derived | **RESOLVED** | Lemma (caljensen) verified line by line: with deterministic carry, M_t = S_t/F_{0,t} is a positive martingale (I checked: E[S_t\|F_s] = S_s e^{∫(r−q)} and the forward curve absorbs it), M_{T_i} = Y_i matches §2's normalization, forward measures coincide with Q when rates are deterministic (Radon–Nikodym = D(T)·B_T = 1), and tower + conditional Jensen + martingale gives c₁ ≤ c₂. The forward-scaled monetizing trade is now named with the right units (1/(D_iF_i) of each leg), and the "not the plain listed spread" warning is exactly the confusion I had. |
| O12 | fig_calendar caption ≠ figure | **RESOLVED** | Caption now says two panels; the y-axis is defined (√(w(k)/τ_far), both legs on the far node's clock — which is what the PDF's "vol at the 4d maturity" axis draws); the crossing is now honestly located "in that censored region" instead of promised as visible; text, App. C, and figure legends all agree on "two and four calendar days". |
| O13 | eq. beyondgrid underived | **RESOLVED** | The two-line derivation now in §12.1 is exactly the one I reconstructed in round 1 (tail correction restarted at z_R where x = k, cash leg single exponential, difference gives λ₊/(1−λ₊)). |
| O14 | "N=6 density is unimodal" vs bimodal panel | **RESOLVED** | Resolved in the honest direction: the text and caption now describe what the panel shows — both modes kept, peaks overshot, trough half-filled, mode locations drifted — with the L¹ doubling (0.108 vs 0.047, "more than double": 2.30, checked) as the carrier, and the information-vs-convention lesson correctly restated as fidelity rather than mode existence. |
| O15 | "demands"/"requires" overclaims | **RESOLVED** | Both gone. Better: the §7 toy now makes the u* > ½ claim where it *is* a theorem (m < 0 forces P(X≤0) = Λ(−m/s) > ½ on the symmetric slice — I checked, including the Jensen reading m = −log E[e^{sZ}] < 0), and §13 replaces the false generalization with the correct two-comparison decomposition. The var-swap sentence is now "as expected … since the log contract weights exactly the wings the smile lifts". |
| O16 | "nearly indistinguishable" vs 42 bp | **RESOLVED** | "the larger gaps sitting out in the wings beyond the quoted ladder" — stated in text and caption, matching the panel (divergence beyond \|k\| ≈ 0.25 where the quote dots end). |
| O17 | Figures in foreign notation | **RESOLVED** | fig_modes now "log-speed g(u)"; fig_tails fully relabeled (g(0), g(1), λ±, r*±, Ψ(r*)) and matches the paper's ledger; fig_spy_node's "bid-ask spread" legend now matches the rewritten §13/§9 story (SPY bands all degenerate to mid — a *better* fix than relabeling, since it explains the data); fig_nvda_nodes keeps "haircut band" where bands are genuinely live. |
| O18 | Z reused (variable vs half-width) | **RESOLVED** | Z_max throughout (§2 table, §12, App. A code `grid.z_max`), with the ledger caption explicitly assigning Z to the score variable and Z_max "and nothing else" to the half-width. But see N5(b): the "none is reused" boast is still not quite true — of h this time. |
| O19 | fig_transport dots were quartiles | **RESOLVED** | Regenerated: dots now at z ≈ ±2.20 with ρ = 0.09, labeled 10%/90%. Checked against logit(0.9) = 2.197. |
| O20 | "two secant chords" vs one | **RESOLVED** | Caption says "a secant chord"; panel has one. A density-agreement macro was added to panel B's caption. |
| O21 | "machine precision" vs 3e−9 near wall | **RESOLVED** | Three error levels now distinguished with separate macros, and the growth mechanism (decay rate 1−λ₊ vanishing at the wall) is stated in both text and caption — it is the correct mechanism. "Machine precision" now survives only for the Newton root polish, where it belongs. |
| O22 | fig_tails "dashed line is the wall" | **RESOLVED** | Caption now: "the finite-forward wall appears as the vertical asymptote of the right-tail map at λ₊=1" — matches the drawn dashed curve. The new NVDA λ₋ > 1 sentence is also correct: E[Y^{−1}] finite iff 1 < 1/λ₋, so λ₋ > 1 ⟹ E[1/Y] = ∞ while the forward stays finite. |
| O23 | C₂ undefined in App. B Step 4 | **RESOLVED** | C₂ = C₁·e^{sup\|m_N\|}·2^λ̄ now constructed. I verified the 2^λ̄ factor: for z ≥ 0, e^{−z}/2 ≤ 1−Λ(z) ≤ e^{−z}, so e^{λ̄z} ≤ 2^λ̄(1−u)^{−λ̄}; and sup\|m_N\| < ∞ from m_N → m* is the right (and now stated) source of uniformity. |
| Q1 | Why Legendre? | **ANSWERED** | See O5. |

**Resolution count: 23/23 RESOLVED, 0 PARTIALLY, 0 NOT (+ Q1 answered).** Nothing was
reworded-around; in the two places where the figure was right and the prose wrong
(O7, O14), the prose was corrected to the figure's truth, which is the honest fix.

## Part 2 — Fresh read of the new/rewritten passages

Verified in full, beyond the table above:

- **§2 factorization block**: correct (my own chain-rule derivation, above).
- **§4.1 eq. (asymptotes) + Legendre paragraph**: correct; the b± bookkeeping now
  propagates correctly into prop. shift and prop. tails.
- **§4.3 three-level audit prose**: matches the PDF (map error flat ≈ 10⁻¹²–10⁻¹¹, shift
  error climbing to ≈ 3×10⁻⁹ by s ≈ 0.95, inset −7.9% at 20% vol against the −8.2%
  limit; 0.918 − 1 = −8.2% checks).
- **§7 toy ticket**: the Jensen-off-a-percentile claim is a theorem on this slice and
  correctly argued; the numbers are macro-pending but the s ≈ 0.081, u* ≈ 53%,
  u_k ≈ 80% magnitudes I computed independently are consistent with the layout of
  fig_transport panel B (root of k = 0.10 near z ≈ 1.4).
- **§8 sign paragraph**: fully verified (see O9) — this was the highest-stakes rewrite
  and it is now right.
- **§9.4 order-guard reframe**: internally honest — the same macro set that round 1
  used to claim a cliff now reports flatness on this book, the historical claim is
  labeled historical and book-dependent, and the guard is re-motivated by
  identification with latency as "cheap insurance". No contradiction anywhere I can
  find (§12.5 and §13.3 quote the same node consistently).
- **§9.5 multi-start audit**: now an actual measurement with five macros and a
  correctly scoped caveat.
- **§11 lemma**: verified line by line (see O11).
- **§13.2 ticket**: now a listed strike; the five-number audit survives intact.
- **App. C**: the new rebuild gate (figures price off the frozen coefficient vectors,
  reproduction to a stated worst-case) closes a reproducibility hole I hadn't even
  flagged.

## Part 3 — New objections

**N1. [SOFT] fig_modes caption still claims every drawn mode multiplies the tail
scales by e^{0.10} — false for a₃ on the right tail, and the panel itself shows it.**
`sections/04_model.tex`, fig:modes caption (~line 135): *"Every raw mode drawn here
also multiplies the tail scales by e^{0.10}, per (eq. endpoints)."* By eq. (endpoints),
g(1) = R + Σ(−1)ⁿaₙ, so a₃ = 0.10 multiplies λ₋ by e^{+0.10} but λ₊ by e^{−0.10}
(P₃(−1) = −1). The relabeled panel (a) draws exactly this: the a₃ curve ends 0.10
*below* baseline at u = 1. (This was my miss in round 1 — the sentence was already
there; the relabeled axis made it jump out.)
**Ask:** "moves both tail scales by a factor e^{±0.10} (even modes both up, odd modes
one up and one down)" — or restrict the sentence to a₂ and a₄.

**N2. [HARD] The closure claim of prop. universal (ii) is stronger than what App. B
Step 6 proves — and the changelog says this claim was weakened, but the file text is
word-for-word identical to round 1.**
`sections/05_validity.tex` (~line 160): *"if admissible slices converge with their
log-speeds g_N uniformly convergent on [0,1], the limit law again belongs to the class
of (i)"* — no hypothesis on the limit's endpoint. `sections/B_proofs.tex` Step 6
(~line 221) proves it only under *"g_∞ continuous and g_∞(1) ≤ log λ̄ < 0"*. The gap:
take g_N → g_∞ uniformly with every g_N admissible but g_∞(1) = 0 (e.g. constant
slices g_N ≡ log(1−1/n)). Step 6 is silent. The proposition survives only *vacuously*
in that branch: I_N → ∞ by Fatou (the limiting integrand ~ e^{b₊} at +∞ is
non-integrable), so m_N = −log I_N → −∞ and every quantile Q_N(u) = m_N + x̄_N(logit u)
→ −∞ — the laws escape to −∞ and "admissible slices converge" fails. That two-line
escape argument appears nowhere, and without it the stated claim is not proved as
stated. Two smaller issues ride along: the proposition never says in *what sense*
"admissible slices converge" (weakly? in the W_p of part (i)?), and the round-2
changelog's "weakened closure claim in §5.3" does not correspond to any change I can
find in the file — the intended edit may not have landed.
**Ask:** either (a) add the endpoint hypothesis to the proposition's closure sentence
("…uniformly convergent on [0,1] *with limiting right-endpoint value strictly
negative*…"), or (b) keep the strong statement and add the Fatou escape paragraph to
Step 6; in both cases name the convergence mode for "slices converge".

**N3. [SOFT] "Next-session NVDA node" is off by one session.**
`sections/09_calibration.tex` (~line 168), `12_computation.tex` (~line 231),
`13_examples.tex` (~line 120: "the next session's expiry"). The reference date is
Monday 2026-08-03 (App. C); the next session is Tuesday 08-04; the expiry is 08-05 —
two calendar days out. After round 1's one-day/2d cleanup this residue stands out.
**Ask:** "nearest-expiry NVDA node" or "the two-calendar-day node" (the macro already
exists).

**N4. [SOFT] The SPY haircut-degeneracy sentence's evidence doesn't support its
quantifier, and its rhetoric presumes the macro's value.**
`sections/09_calibration.tex` (~line 117): *"every SPY spread is far tighter than
$2h$ (the deep-dive node's **median** spread is [x] vol bp against 2h=100), so
[SpyDecBandLivePct]\% of its bands survive the haircut."* A median below 100 does not
evidence "every"; the supporting statistic should be the maximum (or a count). And
after "every … tighter", the surviving share must be exactly 0% — writing "so [X]% of
its bands survive" invites a contradiction if the macro fills with anything else.
**Ask:** quote the max spread (or "all 94 below 2h"), and phrase the consequence as
"none survives ([macro] = 0%)".

**N5. [SOFT] Caption/ledger nits (grouped).**
(a) fig_exact caption still reads "Main panels: … Inset: …" while the figure is a
two-panel layout — panel (b) is not an inset.
(b) The notation ledger's "none is reused with a second meaning" is still not quite
true: h is the butterfly half-width in §2.2 ("long one call at y−h … per h²") and the
haircut half-width in §9/tab. ledger. Local proof substitutions (s = √(1−λ₊),
t = √(1+λ₋) in prop. leeclosed, next to §4.3's scale s) are defensible as bound
variables, but the h collision is two named prose usages.
**Ask:** rename the §2.2 butterfly half-width (it appears twice) or soften the
ledger's boast to "no ledger symbol is reused".

## (a) What I would most want answered before an exam

1. **N2** — the one remaining statement-whose-proof-doesn't-cover-it; the fix is two
   lines either way, but as printed a referee cannot check the closure claim.
2. **N1** — a one-word caption falsehood about the paper's own central coupling
   formula (eq. endpoints), sitting directly under the panel that disproves it.
3. Nothing else rises to exam level; N3–N5 are copyediting.

## (b) Sections that now read perfectly

Everything I praised in round 1 still stands, plus: §2 (the factorization block with
its two checkpoints is now a model of how to state a big-computation result), §4
(receipts, b± bookkeeping, the Legendre justification), §6.4 (the two-sided honesty
clause is *stronger* than the one-sided claim it replaced), §7 (the toy ticket is a
genuinely good pedagogical addition), §8 (the sign-checked digital-mismatch paragraph
is now the best section in the paper), §9 (the reframed order guard and the measured
multi-start are how empirical claims should be reported), §11 (the lemma was the
missing keystone and is correct), §12 (the beyond-grid derivation and the belly
threshold units), §13 (internally consistent signs throughout), App. B (C₂ closed).

## (c) Verdict

**Yes — I would now sign off on this paper as understandable and rigorous for a reader
like me**, with one reservation: the closure claim of prop. universal (ii) must either
gain its endpoint hypothesis or its proof must gain the escape argument (N2), and the
fig_modes caption's e^{0.10} sentence needs its one-word sign fix (N1). The shortest
list to a clean sign-off is exactly: N2, N1, then the three copyedits N3–N5 at leisure.
Every round-1 objection was resolved on the merits — in several places (O7, O9, O14)
by correcting the claim to what the mathematics and the figures actually say, which is
the kind of revision that increases trust rather than merely passing review.

---

*Tally — round-1 resolutions: 23 RESOLVED / 0 PARTIALLY / 0 NOT. New objections:
0 BLOCKING, 1 HARD (N2), 4 SOFT (N1, N3, N4, N5).*
