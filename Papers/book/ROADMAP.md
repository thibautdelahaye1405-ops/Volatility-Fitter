# The Volatility Book — roadmap

This file is the ONLY entry point for book sessions. A session that works on
a chapter reads: (1) this file, (2) the pedagogy contract below, (3) the
source notes listed in its chapter brief, (4) the most recently REVISED
chapter as the tone exemplar (until one exists, the contract itself
governs — do NOT imitate the density of Chapters 2–4 as they stand).
Nothing else.

## Context hygiene (read this first, every session)

The book must read like a polished textbook. The repository around it is an
application with years of engineering history; that history is poison for
the prose. Therefore:

- Do NOT read: the app `ROADMAP.md`, `backend/backtest/**`, `Docs/notes/
  reviews/**`, `Docs/notes/build_*/`, FINDINGS files, certification/benchmark
  material, or memory entries about campaigns, perf arcs, or UI work.
- Do NOT open the app, fetch live data, or run backtests. The data policy
  below covers every empirical need.
- From the source notes, take mathematics, derivations, worked constants,
  and figures ideas. Leave behind: version history, committee/review
  narrative, production incident stories, test-lock references, app
  vocabulary (endpoints, settings names, store paths).
- The implementation, when mentioned, is always "the reference
  implementation". No product names, no repo paths, no internal note
  citations — public literature only.

## Status (2026-08-05, author feedback)

The author reviewed Chapters 3–4 and rejected their register: too dense,
too clever, not readable for someone meeting the subject for the first
time. The style contract below was rewritten in response — it OVERRIDES
the earlier "monograph" register, and Chapter 2 is NO LONGER the style
exemplar. Both queued revisions are now done: Chapter 3 was revised to
the new contract on 2026-08-05, Chapter 4 on 2026-08-06 (each with a
newcomer fresh-reader pass, all stumble points resolved). Chapter 4 is
the most recently revised chapter and therefore the TONE EXEMPLAR.
Next:

1. Chapter 5 (variance swaps and wings), written under the new
   contract from the start, imitating the revised Chapter 4's tone.

Chapter 2 keeps its monograph register for now (it doubles as the
standalone paper); whether to soften it inside the book is the author's
decision, to be raised at introduction time.

## The book

Working title: *The Volatility Surface as a Field of Probability Laws*
(placeholder — decide at introduction time). Author: Thibaut Delahaye.

Thesis (the thread every chapter serves): an implied-volatility surface is a
family of probability laws read through the Black formula. Each chapter
separates, for its subject, what follows from probability (validity), what
the market determines (information), and what the modeler must choose and
disclose (convention).

## The pedagogy contract (rewritten 2026-08-05 — this governs)

The reader: smart, motivated, but NEW to this. Black–Scholes, calculus and
probability at first-course level; no prior exposure to smile modeling, to
the literature, or to this project. They have read the earlier chapters
once, not memorized them. The standard is a patient lecture in writing:
simple words, concrete examples, every step shown, nothing performed.

A chapter is a LESSON, never a rephrase of the source notes or papers.
The notes are a quarry for facts, derivations, constants and figure ideas
— their structure, sentences and density must not survive into the book.

1. Plan as a lesson. Before drafting, write the 3–5 things the reader
   must be able to explain or do after the chapter (as a comment block at
   the top of chapter.tex). Everything in the chapter serves one of them.
   Whatever serves none is CUT, not compressed.
2. One idea per paragraph. Short declarative sentences. If a sentence
   needs a second reading, split it. At most one aside per paragraph; no
   sentence with three clauses strung on em-dashes.
3. Concrete before abstract. Introduce every new object on the smallest
   example that shows it — three quotes, a 2×3 grid, one worked number —
   before the general definition. The reader should be able to compute
   along on paper.
4. Say why, plainly, before and after. Before a derivation: one or two
   sentences on what is about to be shown and why it matters. After:
   restate the result in words a beginner could repeat to a colleague.
   Signposts are plain ("We now know X. The next question is Y.").
5. Show the algebra. Any step a first-course reader could not reproduce
   is written out. "Integrating by parts twice" is displayed lines, not a
   phrase.
6. Re-introduce terms. Every term of art (convex order, vega, Tikhonov,
   monotone scheme, ...) gets a one-line plain-language reminder at first
   use in EACH chapter, even if defined earlier. Keep the symbol count
   low: a symbol used fewer than three times should be words instead.
7. Plain beats memorable. At most one aphorism per chapter. Cut any
   phrase that performs rather than teaches.
8. Repetition is a feature. Open each section with one sentence of where
   we are; close with one sentence of what we now have. Restate a key
   fact when it is used pages after its proof.
9. A limitation is stated once, in one sentence, where it bites; the
   chapter's contract table collects scope. No stacked caveats, no audit
   rhetoric — and no cleverness about honesty either.
10. Fewer figures, walked slowly. 5–8 per chapter, and the text walks
    each panel ("in panel (a), the orange curve is ...; notice ...").
    A figure the text does not walk is cut.

Page budget: 15–22 pages at the new, roomier prose density — fewer topics
per chapter, not smaller writing.

Mechanics (unchanged): derive, don't assert; proofs ≤ half a page stay in
the text, longer ones go to the chapter appendix. One notation ledger for
the whole book (NOTATION.md); one boxed display per chapter at most;
primes for one-variable derivatives, ∂ for partials. Every empirical
number is a generated macro; figures come from one deterministic
per-chapter script reading frozen data.

## Structure (decided 2026-08-04 with the author)

Three parts, eleven chapters. Mapping to notes: 02+03 merged, 08+09 merged,
13+15 merged, 07 and 10 absorbed, all else 1:1. Concept-first order, with
local volatility placed among the models (author's decision).

| Ch | Title (working) | Source notes | Status |
|----|----------------|--------------|--------|
| 1  | Introduction | replaces Note 00; write LAST | pending (last) |
| **Part I — Models** | | | |
| 2  | The log-quantile-density model | 01 | **DONE** (`Papers/lqd_paper/`, 36 pp) |
| 3  | Families in the volatility chart: SVI-JW and superposition | 02 + 03 (+ objective material from 07 not already in Ch. 2) | **DONE** (revised to the pedagogy contract 2026-08-05; tone exemplar) |
| 4  | Local volatility | 04 | **DONE** (revised to the pedagogy contract 2026-08-06; tone exemplar) |
| 5  | Integrals and wings: variance swaps beyond the last quote | 08 + 09 (+ cross-expiry statics remainder of 10) | pending (next) |
| **Part II — The observation** | | | |
| 6  | Forwards, dividends, and carry | 06 | pending |
| 7  | Removing early exercise | 05 | pending |
| 8  | The market's clock | 11 | pending |
| **Part III — Dynamics and inference** | | | |
| 9  | Spot–vol dynamics: the missing derivative | 12 | pending |
| 10 | Inference under weak information: filtering and priors | 15 + 13 | pending |
| 11 | The graph: one surface from a sparse universe | 14 | pending |

Note 10 (calendar) is absorbed: its theory (convex order ⇔ ledger order,
conjugate duality, Kellerer existence) is in Chapter 2 §8; Chapter 5 picks
up term-structure order for integrals; Chapter 4 states calendar-ordered
input as a hypothesis. Note 07 is absorbed: objective/bands/vega weights are
in Chapter 2 §6; quote-quality and weighting-scheme material goes to Part II
and Chapter 10.

## Book infrastructure (DONE 2026-08-05)

`Papers/book/` is the single master.  Build: `pdflatex book && bibtex book
&& pdflatex book && pdflatex book` from `Papers/book/` (no latexmk on this
machine).  Fast single-chapter builds: uncomment `\includeonly` in
book.tex.  Chapter figures: `scripts/chNN/gen_figures.py` (repo venv)
emits `figures/chNN/*.pdf` + a per-chapter macros file; ch03's store is
`figures/ch03/_macros_store.json` (same `--only` mechanics as ch02).
Per-chapter lettered appendices via the `chapterappendices` environment
(sections number 2.A, 3.A, ...; cref says "Appendix").  Each chapter file
opens with `\renewcommand{\figdir}{figures/chNN}`.  As originally planned:

1. `book.tex`: `\documentclass{book}` (or memoir), the Chapter-2 preamble
   generalized (same macros: \E, \Prob, \dd, \PhiN, \phin, \Black, \expit,
   \logit, \paperfig, theorem environments numbered per chapter), natbib,
   `\includeonly` workflow for fast single-chapter builds.
2. `chapters/02_lqd/`: retrofit of `Papers/lqd_paper/` — sections become the
   chapter's sections (\section→ stays \section under a \chapter heading),
   labels get a `lqd:` or ch-2 prefix ONLY if collisions force it. Keep
   `Papers/lqd_paper/` untouched as the standalone-paper artifact.
3. `data/`: copy the frozen snapshot + its README from
   `Papers/lqd_paper/data/` (the book owns its data).
4. `figures/ch02/`: copy Chapter 2's 14 PDFs + `paper_macros.tex`; the
   generator scripts move to `scripts/ch02/`. Macro names get no prefix —
   the \Mac namespace is book-global; new chapters must not collide
   (prefix new macros by chapter subject, e.g. \MacSviXxx, \MacLvXxx).
5. `NOTATION.md`: transcribe Chapter 2's notation ledger as the book ledger.
   New chapters ADD symbols here before using them; never redefine.
   Reserved so far: X, Y, u, z, k, y, c, P, w, σ, τ, Λ, ρ, Q, q, g, x, m,
   G, L, R, a_n, λ±, u_k, z_k, u*, f*, Δ, β_L, β_R, N, Z_max, Ψ, r±*, ξ,
   g_D, δ (butterfly half-width), h (haircut), η (vega floor), α, ν (ridge).
6. The three-part structure with `\part` headings; Chapter 1 as a stub
   (`\chapter{Introduction}` + a one-line placeholder).

## Data policy

One frozen snapshot threads the book:
`data/lqd_paper_snapshot_20260804_0208.json` (SPY + NVDA, 8 expiries each,
2026-08-03 session, haircut LQD-16 fits, embedded chains and quotes; SPY/NVDA
listed options are American-style, so it also serves Chapter 7). A chapter
may add at most ONE documented supplement, frozen in `data/` with a README
entry, when its phenomenon demands it. Anticipated supplements:

- Ch. 8 (clock): one capture spanning a scheduled earnings date (NVDA), to
  show event-dilated variance time. Small: two or three expiries suffice.
- Ch. 6 (carry): possibly one hard-to-borrow name's chain for a borrow-cost
  example. Optional — synthetic illustration acceptable.
- Ch. 9–11: synthetic constructions preferred (scenarios, simulated paths);
  no live-feed dependencies.

Never refetch to "refresh" an existing example. Figures regenerate from
frozen files only.

## Session protocol (per chapter)

1. Read: this roadmap → the chapter brief below → the source notes (all
   listed editions; they are alternative expositions of the same material —
   mine all, follow none, and let none of their density through).
2. Plan the chapter as a lesson: FIRST the 3–5 lesson goals (recorded as a
   comment block in chapter.tex), then a section spine (5–8 sections +
   optional chapter appendix), the 5–8 figures, the macros needed. The
   briefs' "Keep" lists below are ceilings, not floors — cut freely; what
   serves no lesson goal goes.
3. Draft. Writer may be the lead or one writer sub-agent (brief it with the
   pedagogy contract verbatim; forbid the excluded context explicitly).
4. Figures: one deterministic script `scripts/chNN/gen_figures.py` reading
   frozen data; emits `figures/chNN/` PDFs + a macros file the chapter
   inputs. Match the established visual conventions (restrained palette,
   (a)/(b) panel titles, units on axes, rms annotations where relevant).
5. Review: ONE fresh-reader pass with a NEWCOMER persona — first-course
   Black–Scholes only, no smile-modeling background, has read the previous
   chapters once. Their report must give, per section: (i) a one-sentence
   summary in their own words, (ii) the first place they got lost or had
   to re-read. Plus the lead's own math verification of every derivation.
6. Build the whole book (all chapters), check cross-references and the
   notation ledger, commit.

Definition of done: compiles in the book master; 15–22 pp; the lesson
goals are stated and each is met; every derivation verified by the lead;
every "lost" or "re-read" point from the newcomer pass resolved (rewrite
until the persona can summarize every section in one plain sentence);
zero hand-typed empirical numbers; notation ledger updated; no
excluded-context leakage (grep the chapter for "production", app terms,
note references).

## Revision procedure (Chapters 3 and 4)

Goal: same mathematics, same figures, same macros — new prose, written as
lessons under the pedagogy contract. Per chapter: write the lesson goals
first; re-draft section by section (do not patch sentences — patching
preserves the old density); cut material that serves no goal (move it to
the appendix or drop it; the figure scripts stay untouched either way);
walk every kept figure panel by panel; then run the newcomer pass and the
definition of done above. Expect the revised chapters to carry FEWER
remarks and asides and MORE worked steps than the drafts.

## Chapter briefs

### Ch. 3 — Families in the volatility chart: SVI-JW and superposition

Sources: `Docs/notes/02_svi_jw.tex`, `02_svi_jw_moments.tex`,
`02_svi_jw_rewrite.tex`; `03_multicore_siv.tex`,
`03_multicore_mcs_corrections.tex`; `07_calibration_objective_measure.tex`
(mine only for weighting-scheme material not already in Ch. 2 §6).

Angle suggestion: the deliberate foil to Chapter 2. Working directly in the
volatility chart buys interpretable coordinates (the JW handles ARE the
trader's vocabulary) at the price that validity must now be policed: the
admissible region is bounded by conditions (Durrleman g_D ≥ 0, Lee slope
cap) that the optimizer can violate. The chapter develops SVI/SVI-JW
honestly as the industry standard, the moment map as the dictionary between
JW handles and distributional facts, the wing-slope cap STRICTLY inside
Lee's bound (β at the bound admits negative tail density — state as a
proposition with the two-line proof), and reparameterization
(the structural chart: every iterate valid by construction — the same
constraint-elimination idea as Chapter 2, applied within the volatility
chart). Multi-Core SIV enters as superposition: capacity from summing
simple positive kernels, with its own validity logic and its capacity
limits. Close with a fair comparison on the frozen snapshot: same quotes,
LQD vs SVI-JW vs MCS — fit quality, validity margin (g_D minimum), tail
behavior, parameter interpretability. One table, no advocacy; the book's
point is that chart choice allocates difficulty, not that one family wins.

Keep: JW parameterization and the raw↔JW maps (with domain conditions as
propositions); the moment/handle map; Durrleman function (already defined in
Ch. 2 — REFERENCE it, don't redefine); Lee cap proposition; the structural
chart construction; belly (butterfly) certificate as the numerical check;
MCS kernel construction, superposition validity, capacity discussion;
worked fits on SPY December 2026 (the book's canonical node).

Drop: committee-review history, benchmark/adjudication narratives,
chart-vs-chart production racing, eval-cap statistics, desk-ticket API
material, "R1/R2/…" revision vocabulary, test-lock references.

Notation: JW handles need symbols that do not collide with the ledger
(σ, w taken; the notes' (v_t, ψ, p, c, ṽ_t) collide with Ψ and P — resolve
in NOTATION.md first; suggest w₀-consistent handle names or explicit
subscripted v_JW etc. — decide at writing time, record in the ledger).

Figures sketch (8–10): the SVI shape zoo (one figure, parameters varied);
the JW handle geometry; admissible-region geometry with a violating fit
shown (the failure Chapter 2 §1 promised); moment map; Lee cap at the
boundary (density going negative — the counterexample); structural-chart
mechanics; MCS kernels and superposition; the three-family comparison on
the frozen node; g_D margins across the SPY gallery.

Data: frozen snapshot only. Macros prefix: \MacSvi*, \MacMcs*, \MacCmp*.

### Ch. 4 — Local volatility

Sources: `04_local_volatility.tex`, `04_local_volatility_forward.tex`.
Angle suggestion: the "forward" edition's spine — the forward (Dupire)
equation as the object: one field σ_loc(K,T) consistent with ALL marginals
at once; derivation from the ledger/density objects of Chapter 2;
discretization as an affine field on a strike×maturity grid with positivity
and calendar hypotheses stated as input conditions (referencing Ch. 2 §8).
Keep: Dupire derivation done slowly; the affine-grid representation;
regularization as convention; a fitted SPY field figure. Drop: every perf
stage, Numba/memory-budget engineering, incident history (the numerical
appendix may state the grid and stability facts plainly). Macros: \MacLv*.

### Ch. 5 — Integrals and wings: variance swaps beyond the last quote

Sources: `08_variance_swaps.tex`, `08_varswap_representations.tex`,
`09_wings_lee_bounds.tex`, `09_wings_lastquote.tex`; remainder of
`10_calendar_*` for term-structure order of the integrals.
Angle suggestion: integrals of the smile meet the end of the data. The
log-contract/varswap in its three representations (strip replication,
direct-law rank integral — already eq. (varswap) of Ch. 2, reference it —
and the ledger moment); what fraction of the integral lives beyond the last
quote (compute it on the frozen nodes — a strong figure); Lee bounds as the
model-free envelope of admissible completions; extrapolation policy as
disclosed convention; term structure of the integral and its calendar
monotonicity. Keep: the three-integral equivalences with proofs; tail-share
decomposition; Lee-bound envelope construction. Drop: publish-time
projection engineering, export/audit vocabulary. Macros: \MacVs*, \MacWing*.

### Ch. 6 — Forwards, dividends, and carry

Sources: `06_forwards_dividends.tex`, `06_forwards_dividends_inference.tex`.
Angle suggestion: the forward is a fitted parameter, not an input.
Put–call parity as a regression across strikes; discrete dividends vs yield;
carry/borrow as the residual rate; error propagation — how a forward error
masquerades as skew (derive dIV/dF; a figure). The chapter opens Part II
with the statement that Chapters 2–5 assumed (F, D) known, and now the book
earns them. Keep: parity regression with robust treatment of outliers as
mathematics (not pipeline lore); identifiability of borrow; the
forward-bump-reads-as-skew derivation. Drop: feed/provider material,
zero-carry synthesis incidents, schema versions. Macros: \MacFwd*.

### Ch. 7 — Removing early exercise

Sources: `05_deamericanization.tex`, `05_deamericanization_stopping.tex`.
Angle suggestion: the "stopping" edition — listed equity options carry an
exercise option; the European observation is recovered by pricing the
stopping right under a proxy model and subtracting it, with the fixed-point
subtlety (the proxy needs the surface the observation feeds). Early-exercise
premium behavior (calls vs puts, dividends, rates); where de-Am is material
vs negligible (frozen SPY data: it is American — show the EEP across the
gallery). Keep: optimal-stopping formulation, EEP decomposition, the
fixed-point argument, binomial/CRR as the reference numerical method (facts,
not perf history). Drop: performance staging, Numba, campaign material.
Macros: \MacDeam*.

### Ch. 8 — The market's clock

Sources: `11_event_variance_clock.tex`, `11_event_market_clock.tex`.
Angle suggestion: τ, used since Chapter 2 as "variance time", finally
defined: variance accrues on the market's clock, not the calendar —
weekends, sessions, scheduled events. Event dilation as a measure on time;
the term structure read in event time straightens. Keep: the clock
construction, event weights, the dilated-calendar comparison. Data: the ONE
anticipated supplement (an NVDA earnings-week capture) OR a synthetic event
construction if the supplement is not available at writing time. Macros:
\MacClk*.

### Ch. 9 — Spot–vol dynamics: the missing derivative

Sources: `12_spot_vol_dynamics.tex`, `12_spotvol_missing_derivative.tex`.
Angle suggestion: statics give ∂C/∂K exactly; hedging needs dσ/dS, which
statics cannot supply — the missing derivative. Sticky rules as candidate
completions; SSR as the OUTPUT summarizing a rule; delta stakes (how much
delta the rule choice moves). Scenario figures from the frozen surface.
Macros: \MacSsr*.

### Ch. 10 — Inference under weak information: filtering and priors

Sources: `15_kalman_filtering.tex`, `15_kalman_computed_trust.tex`,
`13_bayesian_prior_persistence.tex`, `13_prior_flat_directions.tex`.
Angle suggestion (the merge's logic): two instruments for the same
predicament — the data underdetermines the state. In TIME: the filter, with
trust computed (gain from innovation statistics, honest covariances), on the
smile handles. In PARAMETER SPACE: the prior, placed along the likelihood's
flat directions (the null space Chapter 2 §6 exposed: tails, inter-quote
detail), persistence as the prior's memory. One chapter because the two
share the Bayesian frame: posterior = data where data speaks, prior/filter
where it is silent — the "information vs convention" thesis made dynamic.
Keep: state-space setup on handles, gain-as-output, ζ (consistency) audit
as mathematics; flat-direction identification; prior anchoring with
data-gap precision. Drop: session-clock plumbing details beyond what Ch. 8
established, campaign/backtest results, mode-flag vocabulary. Synthetic +
frozen-snapshot illustrations. Macros: \MacFilt*, \MacPrior*.

### Ch. 11 — The graph: one surface from a sparse universe

Sources: `14_graph_extrapolation.tex`, `14_graph_messages.tex`,
`14_graph_three_priors.tex`.
Angle suggestion: the book's destination. Nodes are (underlier, expiry)
laws; edges carry precision-weighted messages; a sparse set of observed
smiles completes a universe. Develop as Bayesian propagation (precision
messages), with the prior structure of Chapter 10 as the local ingredient;
the three-priors view (baseline, systematic, residual) as the decomposition
of what an unobserved node believes. Close the book by returning to the
introduction's promise. Keep: operator construction, message algebra,
posterior decomposition, a worked sparse-universe example (synthetic
universe built FROM the frozen snapshot's two names plus synthetic
neighbors). Drop: solver/UI/campaign material entirely. Macros: \MacGr*.

### Ch. 1 — Introduction (write LAST)

Replaces Note 00. Content: the problem (finitely many noisy prices; a
surface of laws must be published); the separation thesis; what is assumed
of the reader (Black–Scholes, calculus, probability at first-course level);
the book's map with one paragraph per chapter; the notation ledger; the data
statement (one frozen snapshot threads every example). Must also DEFINE the
recurring device "the reference implementation" (Ch. 2 and Ch. 3 both use
it as an unnamed actor — the fresh-reader pass flagged the dangling
referent) and, if useful, desk vocabulary the chapters assume sparingly. Some of Chapter 2 §1
(the smile-as-law argument) may migrate here at that point — decide then,
keeping Chapter 2 self-contained.

## Progress log

- 2026-08-04: structure decided with the author (mapping, order, master,
  data policy); Chapter 2 complete as `Papers/lqd_paper/` (36 pp,
  monograph-chapter edition). Next: book infrastructure + Chapter 3.
- 2026-08-05: book master built (`book.tex`, ch2 retrofit verbatim under a
  \chapter heading with the abstract as synopsis, data/figures/scripts
  copied, NOTATION.md ledger, ch1 stub, 2.A-2.C lettered appendices;
  builds clean).  Chapter 3 written: 8 sections + appendix 3.A, ~19 pp,
  10 figures + 69 macros from `scripts/ch03/gen_figures.py` (frozen
  snapshot + deterministic synthetics; three-family comparison refits
  LQD/SVI/MCS on the same mid quotes — protocol in appendix 3.A).
  Notation resolved in NOTATION.md: raw SVI subscript-S, JW handles
  subscript-J, MCS uses ζ/𝒜/𝓑/γ (z, Φ, B, α were taken); moment budget
  reuses Ch.2's r±* = Ψ⁻¹(β).  Fresh-reader pass run; math verified by
  the lead.  Next: Chapter 4 (local volatility).
- 2026-08-05 (later): Chapter 4 written (`chapters/04_localvol/`, 8
  sections + appendix 4.A, ~20 pp, pages 59–78 of the 82-page build).
  Spine: field → forward equation derived from the density with the
  chart identity v = ∂τw/g_D (numerator = calendar, denominator =
  butterfly: the field exists iff the surface is valid, evaluated on the
  frozen SPY surface as fig 4.1) → ill-posedness of extraction (two
  quote densities, one ripple) → P1 sheet with box-bound validity → the
  M-matrix implicit march + CN counterexample → identifiability (two
  sheets one quote set) → objective/tangent/adjoint → examples +
  contract.  10 figures + 46 macros from `scripts/ch04/gen_figures.py`
  (frozen snapshot + deterministic synthetics; REAL whole-surface fits:
  SPY 216 vertices/1026 quotes 2.7 bp in-operator vs 13.6 bp refined,
  NVDA 16.1/46.1 — the operator gap is deliberately part of the story;
  measured butterfly/calendar minima at rounding scale).  Notation: bare
  v (local variance), y reused from Ch. 2, calligraphic 𝓛/𝓜/ℋ/𝒥/𝒪,
  Γ roughness, λ/λ₀ weights, s_ℓ/p adjoint pairs — all ledgered.
  Fresh-reader pass (sub-agent, 18 findings) fully addressed — the one
  real proof gap was the θ-dependent boundary term in the
  tangent/adjoint propositions, now stated boundary-inclusively.  Math
  verified by the lead.  Next: Chapter 5 (variance swaps and wings).
- 2026-08-05 (author review): the author rejected the register of
  Chapters 3–4 — too dense, not pedagogical, unreadable for a newcomer,
  and too close to a rephrase of the source material.  The style
  contract was rewritten as the pedagogy contract above; Chapter 2 is no
  longer the style exemplar; Chapters 3–4 are queued for a full prose
  revision (math/figures/macros stand); Chapter 5 waits until after that
  revision so it can imitate a revised chapter's tone.
- 2026-08-05 (later): Chapter 3 REVISED to the pedagogy contract — full
  prose rewrite as a lesson, all 8 sections + synopsis; mathematics,
  figures (10, every panel now walked in the body text), macros, and
  labels unchanged.  Lesson goals recorded as the comment block in
  chapter.tex.  Additions: worked numeric slice opens §3.2; every proof
  step displayed (wing limits, boundary expansion, Ψ inversion, χ band,
  𝒟 derivatives, structural inversion, kernel curvature); plain-word
  reminders for every term of art; Table 3.1 pre-glossed.  Moved to
  App. 3.A: the Jacobian-layers subsection (labels intact).  Fixed en
  route: the appendix's `R=2` → `M=2` (ledger collision), a corrupted
  `\rm` in §3.8, and a false "seventeen-strike" claim (the node has 94
  prepared quotes — checked against the frozen snapshot).  Newcomer
  fresh-reader pass run (sub-agent persona): all sections summarizable,
  ~20 stumble points ALL resolved; math re-verified by the lead.  Main
  text pp. 39–61 (≈23 pp, one over the guideline — accepted; density,
  not length, was the complaint), appendix 62–64; full book builds
  clean at 88 pp, no undefined refs, ch3 overfulls cleared.  Next:
  Chapter 4 revision, imitating Chapter 3's revised tone.
- 2026-08-06: Chapter 4 REVISED to the pedagogy contract — full prose
  rewrite as a lesson, all 8 sections + synopsis; mathematics, figures
  (10, every panel walked in the body, incl. a per-panel progression
  walk of fig 4.8), macros (all 46 still in use), and labels unchanged.
  Lesson goals recorded as the comment block in chapter.tex.
  Additions: Fokker–Planck derived in full (Itô → test function →
  double integration by parts, each displayed), vega identity and
  chart-ratio cancellation displayed, worked 4ε/Δk² noise computation
  with plugged numbers, g_D recalled with its formula where the noise
  lands, non-uniform stencil derived by Taylor, self-contained Jacobi
  proof of inverse positivity, boundary vector b^n displayed once and
  reused by both proofs that lean on it, tangent product-rule
  derivation displayed, plain-word reminders for every term of art
  (butterfly, Dirichlet, M-matrix, monotone, CFL, Tikhonov, vega,
  Gauss–Newton, adjoint, vanilla, LEAP, variance swap, delta ladder,
  alias, hull, tensor grid, Delaunay).  One aphorism kept (the
  two-sheets experiment); the rest of the performing phrases made
  plain.  Symbol repairs: test function is Ξ (both phi glyphs were in
  service; ledgered), M_* → U_* (vs the step matrix 𝓜), the ones
  vector vs the indicator disambiguated, 𝔏 vs 𝓛 flagged, §4.6
  volatility-vs-variance units made explicit.  Fixed en route: two
  appendix overfulls (long inline formulas displayed).  Newcomer
  fresh-reader pass run (sub-agent persona): all 9 files summarizable
  in one sentence, ~20 stumble points ALL resolved; math re-verified
  by the lead.  Main text pp. 65–86 (≈22 pp), appendix 87–89; full
  book builds clean at 94 pp, no undefined refs, no ch4 overfulls.
  Ch. 4 is now the tone exemplar.  Next: Chapter 5 (variance swaps
  and wings), new contract from the start.
