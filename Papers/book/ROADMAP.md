# The Volatility Book — roadmap

This file is the ONLY entry point for book sessions. A session that works on
a chapter reads: (1) this file, (2) the pedagogy contract below, (3) the
source notes listed in its chapter brief, (4) chapters 3-4 as the tone exemplar 
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

## Status (2026-08-07)

The pedagogy contract governs (rewritten 2026-08-05 after the author
rejected Chapters 3–4's original register; both were fully revised).
Chapters 5–10 were written under the contract from the start (newcomer
fresh-reader pass run on each, all findings resolved).  Chapter 10
(2026-08-07) is the most recent chapter held to the contract;
Chapters 3–4 serve as TONE EXEMPLAR.  Parts I–II are COMPLETE;
Part III has Chapters 9–10 done and Chapter 11 remaining (211-page
build).
Next:

1. Chapter 11 (the graph: one surface from a sparse universe) —
   sources: the three Note 14 editions (brief below).  Chapter 10
   planted the hook (its closing paragraph: per-node inference,
   with the universe's coupling — precision flowing across a graph
   — left to the final chapter), and its §10.7 division of labour
   already names the "dark-node baseline" Chapter 11 must build.
   Data: synthetic universe built FROM the frozen snapshot's two
   names plus synthetic neighbors — no refetching.
2. Then Chapter 1 (introduction, written LAST) + the title decision
   and the Chapter-2 register question (see below).

NOTE (Ch. 8 data decision, 2026-08-07): the anticipated NVDA
earnings-week supplement was NOT needed and was not fetched — the
frozen snapshot's own NVDA board carries the earnings signature (the
18-day expiry dips 429 vol bp below the 4-day; the (Aug 21, Sep 18]
interval runs 1.40× the lull's accrual), and the chapter reads the
clock off that board plus deterministic synthetics.  The data policy's
supplement allowance rolls forward unused.

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
| 5  | Integrals and wings: variance swaps beyond the last quote | 08 + 09 (+ cross-expiry statics remainder of 10) | **DONE** (written under the pedagogy contract 2026-08-06; tone exemplar with revised Ch. 4) |
| **Part II — The observation** | | | |
| 6  | Forwards, dividends, and carry | 06 | **DONE** (written under the pedagogy contract 2026-08-06; tone exemplar with Chs. 4–5) |
| 7  | Removing early exercise | 05 | **DONE** (written under the pedagogy contract 2026-08-07; tone exemplar with Chs. 4–6) |
| 8  | The market's clock | 11 | **DONE** (written under the pedagogy contract 2026-08-07; tone exemplar with Chs. 4–7) |
| **Part III — Dynamics and inference** | | | |
| 9  | Spot–vol dynamics: the missing derivative | 12 | **DONE** (written under the pedagogy contract 2026-08-07; opens Part III) |
| 10 | Inference under weak information: filtering and priors | 15 + 13 | **DONE** (written under the pedagogy contract 2026-08-07) |
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
- 2026-08-06 (later): Chapter 5 WRITTEN under the pedagogy contract
  from the start (`chapters/05_integrals_wings/`, 7 sections +
  appendix 5.A, ~17 pp, book pages 89–105 of the 112-page build).
  Spine: the instrument and the log-contract identity w_vs = −2E[X]
  (Itô derived slowly; flat-smile w_vs = w(0) computed by hand) →
  three integrals for one number (spanning proved; Ch. 2's rank
  integral referenced; the field route by Fubini + backward source
  equation, Feynman–Kac proof in 5.A) → the accrual share (18.4% of
  the running node's integral beyond the quotes; gallery 3–23%) →
  the model-free ceiling β ≤ 2 proved from "the far call must die"
  (both wings displayed; the boundary ray inadmissible; the decay
  exponent recovering Ch. 3's moment budget) → the envelope of
  admissible completions (price-space cone from the last two quotes;
  Black-chart fan; closed-form top edge √w⁺ = q + √(q²+2k) with
  slope → 2 — the ceiling as the fan's top edge) → the wing as a
  stated choice (three family contracts, the hat counterexample:
  slope change exactly 0.0, g_D −0.30 at finite strike; one-curve
  checks extend, two-curve confined) → the ordered term structure
  (calendar order integrates via the same spanning identity; frozen
  gallery monotone, min increment +1.1 var bp) + the contract table.
  7 figures + 46 macros from `scripts/ch05/gen_figures.py` (reuses
  Ch. 3's fit protocol and Ch. 4's LV protocol verbatim via shared
  figlib imports; field-side audit on a widened lattice at dt and
  dt/8 — 23.2 → 2.9 vol bp, first-order convergence shown; ceiling
  panel evaluated in log space).  Notation added to NOTATION.md
  before writing (w_vs, σ_vs, v_τ, 𝒲, 𝒮, bars-at-the-last-quote,
  w±).  Newcomer fresh-reader pass run (sub-agent persona): all 9
  files summarizable, ~35 findings (terms, symbols, skipped steps,
  re-read sentences, one genuine directional error in the
  convex-floor figure walk) ALL resolved; math verified line by
  line by the lead.  Full book builds clean at 112 pp, no undefined
  refs, no ch5 overfulls.  Next: Chapter 6 (forwards, dividends,
  and carry), opening Part II.
- 2026-08-06 (later): Chapter 6 WRITTEN under the pedagogy contract
  from the start (`chapters/06_forwards/`, 8 sections + appendix
  6.A, ~15 pp main text, book pages 109–125 of the 132-page build;
  opens Part II with the \part{The Observation} heading).  Spine:
  parity derived from a static portfolio + a two-strike hand solve
  (D=0.98, F=101.50 exact by construction) → the line fitted on the
  REAL frozen SPY Dec-2026 raw chain (first chapter to read the
  snapshot's embedded chains at quote level: 158 pairs, straight to
  0.35% of an $850 range, residuals a dollar-scale early-exercise
  bow = the Ch. 7 hook; naive root 68 bp under the stored resolved
  forward) → the identifiability proposition (OLS level/slope sds,
  uncorrelated, error decomposition with the F−K̄ lever; MC audit
  6.3 vs 6.4 bp rate / 0.57 vs 0.57 bp forward; 1/t amplification,
  63 bp at t=0.05) → the trim + the MASKING experiment (5-strike
  coherent stale wing: 0 trimmed, rate plausible-but-wrong at
  1.7%, forward moves 13 bp) → the rate band as a prior + the
  lever-arm identity (naive 50 / uniform 5.4 / spot-kernel 0.31 bp
  per % of rate error) → dividends (escrow + proportional
  reinvestment bookkeeping displayed; the sawtooth vs the honest
  discriminator, spot elasticity S/(S−PV)=1.053 at 2y) → the
  dσ/dlogF derivation at fixed price (numerator collapses to
  Φ(d+); put side sign-flips; ATM gap ≈ 2.5δ/√τ = 41 vol bp per
  10 bp on the node; the naive forward would imprint 278 vol bp)
  → borrow as the residual carry (two-sided fee argument;
  materiality 65/136 vol bp per 100 bp at 3m/1y vs the
  identifiability floor 13/3.2 bp, 164 bp at one week; report
  unidentified, never zero) + the contract table.  7 figures + 67
  macros from `scripts/ch06/gen_figures.py` (frozen snapshot raw
  chains + stored LQD fit via ch03 figlib; deterministic synthetic
  boards; the single seeded MC is the chapter's only randomness).
  Notation added BEFORE writing (S, K, t, sans-serif 𝖢/𝖯 raw-quote
  convention, Π, ε, n, K̄_μ, S_KK, hats, r, q_d, d_i/t_i, f_i, PV,
  b/b_min); references +Hull2018, Stoll1969, SeberLee2003,
  RousseeuwLeroy1987.  Newcomer fresh-reader pass run (sub-agent
  persona): all 10 files summarizable, 30 findings (term-of-art
  discipline, hand-typed number echoes → macros, one muddled
  identifiability parenthetical rewritten as a like-with-like
  relative comparison, the §6.4→6.5 transition overpromise, the
  borrow equality earned from both sides, silent signs made
  explicit) ALL resolved; math verified line by line by the lead
  (incl. reproducing every generated number from the closed
  forms).  Full book builds clean at 132 pp, no undefined refs, no
  ch6 overfulls.  Next: Chapter 7 (removing early exercise).
- 2026-08-07: Chapter 7 WRITTEN under the pedagogy contract from the
  start (`chapters/07_early_exercise/`, 7 sections + appendix 7.A,
  ~15 pp main text, book pages 127–143 of the 150-page build).
  Spine: the observation is an American price (A ≥ E; the premium
  A − E deliberately has NO symbol — rule 6) → where the premium
  lives (Merton proved slowly via Jensen + martingale spot; the
  deep-put threshold S < K(1−e^{−rt}) as a corrected
  strictly-beats-the-European-plan proposition; the premium MAP with
  measured intrinsic-plateau boundaries 129%/78% of spot at t=½ and
  the Merton check EXACTLY zero) → a two-step CRR tree hand-solved
  (moment-matched p displayed with explicit exponentials — u, d never
  become symbols; obstacle binds at the down node, premium 0.75;
  even-N convergence panel shows the difference A−E converging 3×
  cleaner: the control-variate seed) → the subtraction (boxed root
  find A(σ*)=𝖢(K); the add-and-subtract identity; monotonicity cited
  with honest scope; the intrinsic-plateau NO-ROOT refusal drawn;
  worked strike +219 bp naive vs exact 25.00% root; budget with
  measured depth sensitivity 2.0/8 bp for 256→128) → dividends as
  dates (recombination-breakage display, escrowed lattice,
  forward-consistent rescale; the premium is EXACTLY zero pre-ex-date
  and JUMPS across it ≈ dividend × P(ITM) — a $6 heavy-payer board;
  the flat smear invents $0.65 where the truth is zero, 3.1× at a
  matched forward) → the Chapter-6 loop closed as a two-pass fixed
  point on the running node (rate pinned 4.3% by convention since the
  board's own slope says −0.24%; 123/158 pairs invert, 35 on the
  floor; the fig 6.1(b) BOW REPRODUCED by the tree to $0.17 rms = the
  leftover noise; line straightens $2.97→$0.17; fitted forward
  762.71→768.20, 4 bp from the stored 767.92 vs 68 bp naive — the
  residual read as the dividend-convention gap) → how much it matters
  (fitted vs discarded populations: SPY gallery medians 1.32→6.8 bp
  across 8 expiries, worst fitted quote 221 bp in the spot–forward
  put band — the fit-coordinate-vs-exercise-right disagreement made
  explicit — against 161 bp median / 448 max on discarded ITM puts;
  wing butterfly disclosure; contract table).  7 figures + 75 macros
  from `scripts/ch07/gen_figures.py` (self-contained CRR engine —
  scalar, batch with per-lane σ bisection, escrowed; frozen snapshot
  raw chains via ch03/ch06 figlib loaders; NO randomness anywhere).
  Notation added BEFORE writing (A(σ), E(σ), σ*, p, N_t, Δt, ϑ, 𝒯;
  italic E = price vs blackboard 𝔼 noted); references +CRR, Merton,
  Peskir–Shiryaev, El Karoui–Jeanblanc–Shreve, Burkovska et al.
  Newcomer fresh-reader pass run (sub-agent persona): all sections
  summarizable, ~25 findings (one GENUINE math defect — Prop 7.3
  claimed "beats every waiting plan" while the proof gives
  beats-the-European-plan — fixed; "control variate"/"batch
  depth"/"time value"/"butterfly violation" glossed; the §7.6
  root-vs-forward word collision renamed throughout incl. the figure
  callout; the inverted 41-bp exchange-rate phrasing replaced by
  Ch. 6's own macros; the OTM-side vega rationale corrected to
  same-vega-tighter-package; six multi-clause sentences split) ALL
  resolved; math verified line by line by the lead (vega identity,
  Jensen chain, drift floor, every hand-tree number recomputed
  independently, CV identity, recombination display, escrow rescale).
  Full book builds clean at 150 pp, no undefined refs, no ch7
  overfulls.  Next: Chapter 8 (the market's clock).
- 2026-08-07 (later): Chapter 8 WRITTEN under the pedagogy contract
  from the start (`chapters/08_clock/`, 7 sections + appendix 8.A,
  ~15 pp main text, book pages 145–161 of the 169-page build; closes
  Part II).  The anticipated NVDA supplement was NOT needed: the
  frozen snapshot's own NVDA board carries the earnings kink (18-day
  expiry 429 vol bp under the 4-day; the earnings-bearing interval
  accrues 1.40× the pre-report lull, 5.39 vs 3.86 var bp/day —
  hand-walked in §8.1).  Spine: the real-board puzzle (three
  readings, accrual rates per interval) → the discrete
  budget-not-schedule computation (independent normal days; one
  seeded walk on two rulers, envelope kink 1.08%) + DDS stated with
  accumulated variance 𝒞(s) defined before the theorem →
  the day-weighted clock (boxed τ_days = 365t + ΣN_e; hand example
  14+4; relabeling proposition: prices/butterfly/calendar-order
  invariant, readings covariant √(t/τ); crush factor + binomial
  expansion N_e/(2·365t); normalization 365/369) → the synthetic
  earnings week (term hump peak 35.5%; fixed-expiry ramp
  34.0→42.4% then −1243 bp overnight, "no unscheduled price move"
  language harmonized everywhere) → interpolate-in-τ (three quotes,
  event between them; calendar rule smears +33/−97 vol bp; jump-at-
  event-date guarantee derived in two lines) → the inverse problem
  (𝓕_i = Δw_i/Δτ_i; J(N) four terms each explained; events can only
  pull their own interval down; within-interval date
  non-identifiability proposition; shrinkage derivation with the
  N≥0 clipping stated; λ_sparse·Δτ²/σ⁴ law; planted-event audit —
  shrink 0.03/0.40 d at 40/20%, quarterly board blind to 2.5 d,
  materiality walls 12%/22%, flat ladder → exactly 0) → the frozen
  boards (year-end horizon: +7.3 d on NVDA's earnings interval,
  in-horizon spread 560→299 var bp, live ℓ1 shrinkage visible;
  no-horizon overreach: 250 d installed, ladder forced flat 1444→44
  — "the horizon and the review are the method"; SPY control: 0.9 d,
  median forward-vol 15%, rising ladder left standing) + below-one-
  day/French–Roll + Clark/Ané–Geman/Bergomi lineage + contract
  table.  7 figures + 59 macros from `scripts/ch08/gen_figures.py`
  (frozen ATM ladders — NO smile refits; self-contained clock +
  solver in figlib implementing exactly the displayed J(N); the
  seeded walk is the chapter's only randomness).  Notation added
  BEFORE writing (t_e/N_e, τ_days, σ_cal, 𝒞(s), Z, 𝓕_i, J,
  λ_mono/sparse/ridge); references +Dambis, Dubins–Schwarz,
  Revuz–Yor, Clark 1973, Ané–Geman, French–Roll, Bergomi.  Newcomer
  fresh-reader pass run (sub-agent persona): all 9 files
  summarizable, ~40 findings (headliners: "prices unmoved" vs
  scheduled-decay contradiction harmonized; the 5-units-vs-4-extra
  event bookkeeping bridged explicitly in §8.3; the crush factor's
  direction pinned on the hand example; 𝒞 defined before the DDS
  statement + growth condition explained; Black-inversion
  time-blindness justified via eq:black's d±(w); shrinkage
  derivation's flat-at-truth assumption argued and the clipping
  paragraph added; "weekly board" renamed dense; appendix's wrong
  "1-day node" → 2-day + full expiry list added; 94=90+4 derived;
  SPY "15%" now macro-backed) ALL resolved; math verified line by
  line by the lead (accrual arithmetic, √-ratios, interpolation
  walk, ∂𝓕/∂N, shrinkage calculus, every macro recomputed).  Full
  book builds clean at 169 pp, no undefined refs, no ch8 overfulls.
  Next: Chapter 9 (spot–vol dynamics: the missing derivative).
- 2026-08-07 (later): Chapter 9 WRITTEN under the pedagogy contract
  from the start (`chapters/09_spotvol/`, 7 sections + appendix 9.A,
  ~15 pp main text, book pages 165–182 of the 191-page build; OPENS
  Part III with the \part{Dynamics and Inference} heading).  Spine:
  the missing derivative (a snapshot does not identify dynamics —
  every strike derivative known, no spot derivative; the fan of
  tomorrows on the frozen hero node, 344 vol bp at one strike for a
  4% move) → the sign discipline (quote rule k−H vs curve rule k+H,
  both hand-derived at F=100→104.08; the log-move wording convention
  stated once) → the one-dial transport (shape preservation ⇒
  re-index + one level; boxed σ_new(k)=σ_old(k+H)+(ℛ−1)s₀H; ATM
  response ℛs₀H proved; Derman regimes at ℛ=0/1/2; six-number toy
  table on a straight smile; the common second-order bend 54 bp at
  −6% = the smile's own curvature) → the delta stakes (fixed-strike
  response (ℛ−1)s₀ EXACT by rule composition; Δ_tot =
  Φ(d₊)+φ(d₊)√τ(ℛ−1)s₀ derived with the σ-cancellation displayed;
  gap 2φ(d₊)√τ|s₀| = 14.4 delta pts at the 19-delta put, 21.0 ATM on
  the hero node s₀=−0.430) → the frozen field (half-rule derived by
  chord average and MEASURED: implied/local slope ratio 0.499 at
  τ=0.10 on a synthetic straight field priced through ch4's marcher;
  frozen-move ATM +140 bp = 2s₀H to the bp; the midpoint relabeling
  ℓ(k,H)=log(e^H(1+e^k)−1) derived from shared dollar midpoints,
  expansion (1+e^{−k})H, put wing reads 2.35H vs call 1.74H) → the
  wings belong to the field (the chapter's DEEPEST payoff, a
  deliberate refinement of the note's story: two fields sharing ATM
  value+slope — log-affine vs dollar-affine — produce near-twin
  todays and visibly different tomorrows; repriced responses flat vs
  tilted ∝(1+e^k), separations 26/36 bp at ±0.30 under −5%; the
  displacement-times-fading-slope trace DISPLAYED so eq (ssrellexp)
  cannot mislead; grid rule x→x−(ℛ/2)H generating the whole dial;
  realized ratio ℛ̂(τ) measured: 2.00 FLAT at every maturity for the
  straight field (spread 0.001 — first-order maturity-independence,
  with the averages-cancel reason given), bent field lifts to
  2+2cH/b: 2.06/2.11 measured vs 2.06/2.11 predicted at −2%/−4%; the
  note's "hugging the short-maturity limit" story corrected to the
  measurable statement) → the board scenario (−5% across all eight
  SPY expiries by the exact per-node transport: two-day ATM 9.6% →
  15.2/25.7/36.2% under ℛ=0/1/2, s₀=−2.10; sticky-moneyness moves
  short ATMs too — the curvature term grown large; 2d/4d reads
  disclosed as published-wing consumption per ch5; 25-delta-put gap
  9.9→21.6 pts, GROWING in maturity since the skew decays slower
  than 1/√τ — macro-backed 0.25-vs-0.430 comparison; validity
  paragraph with Rogers–Tehranchi; contract table) + the ch10 hook
  (weighing new evidence against a moving prior = filtering).  7
  figures + 51 macros from `scripts/ch09/gen_figures.py` (stored
  haircut LQD fits only — NOTHING refitted; ch4's pde1d marcher
  imported for the synthetic frozen-field worlds; NO randomness
  anywhere; dt-audit 0.00%).  Notation added BEFORE writing (H move
  — lowercase h stays haircut; calligraphic ℛ — roman R stays LQD's;
  s₀/s₀(T); ℓ(k,H); ℛ̂ hat-estimate; Δ_tot composite; σ_old/new word
  subscripts); references +Derman 1999, Hagan et al 2002,
  Berestycki–Busca–Florent 2002, Rogers–Tehranchi 2010.  Newcomer
  fresh-reader pass run (sub-agent persona): all 9 files
  summarizable, 45 findings (headliners: the (1+e^k)-tilt trace was
  missing and eq (ssrellexp) actively misled — now displayed; the
  36-bp call-side separation unreachable by first-order logic — now
  honestly attributed to second order; midpoint rule used before
  stated — bridge added; "to first order" moved INSIDE the ℛ=0
  bullet; log-move wording convention stated once; vega attribution
  harmonized ch2-appendix/ch6; macro meaning of the 21-pt spread
  corrected; fan ordering, arrow placement, readout strikes, |H|
  signs, harmonic gloss, haircut gloss ALL fixed) ALL resolved; math
  verified line by line by the lead (toy table, delta chain, ℓ
  expansion constants, gap arithmetic at both strikes, b(e^H−1) vs
  bH, 2+2cH/b at both moves, √τ-scaling of the board skews).  Full
  book builds clean at 191 pp, no undefined refs, no ch9 overfulls.
  Next: Chapter 10 (filtering and priors, Notes 15+13 merged).
- 2026-08-07 (later): Chapter 10 WRITTEN under the pedagogy contract
  from the start (`chapters/10_inference/`, 7 sections + appendix
  10.A, ~17 pp main text, book pages 183–199 of the 211-page build;
  Notes 15+13 merged per the brief: two instruments for one
  predicament — the data underdetermines the state).  Spine: the
  flat directions MEASURED on the frozen SPY node (band-thinned to
  31/94 quotes; pinned-wing profile likelihood: rms moves 0.02 bp
  across a 12-point imposed-wing sweep vs the full chain's sharp V
  half-width 0.5 pts at +5 bp; the ensemble garnish — eight
  reference fits agree within 0.3 pts: "agreement between
  conventions is not information"; quote support Q(k) as the cheap
  proxy) → yesterday as pseudo-observation rows + the activation
  gate (precision-weighted average derived by minimizing the convex
  combination's variance, worked 20.0±0.30 vs 20.4±0.15 → 20.32;
  ridge disqualified by its everywhere-positive posterior share —
  33% at twice the requirement — vs the gate's dead zone; no-damp
  proposition with the 3-line structural proof) → the information
  price (harmonic law + proof, dead-leg 1/(1/6+1/0.1)=0.10, RR/BF
  factor of four derived; the kernel-bleed blind spot stated where
  it bites — BF crosses at half-width 0.09, RR at 0.17 with legs at
  0.18) → coordinates (baskets annihilate the level direction,
  proof; the 4-point overnight jump experiment with ALL FIVE
  candidate rows gated by the chapter's own budget-split rule —
  gates 0.00/0.68/0.00/1.00/0.99, the moderate BF closed by its own
  factor-of-four; basket wing error 0.28 pts vs anchor 4.5 (clings
  to yesterday) vs data-only 6.4; ATM gap 26.9 bp against a 400 bp
  jump; the coverage-deficit test defined for the deep-tail
  anchors) → the filter (state = ATM handles; predict via ch9's
  transport; the boxed scalar update derived from §10.2 with the
  posterior-variance algebra displayed; "the dial nobody may own";
  the stale-strike vignette computed: gains 0.80/0.72/0.027,
  posterior 20.32%/−0.364/0.112, ±13 bp; per-handle-vs-matrix
  remark) → two honest budgets (information matrix with the
  one-parameter covariance derivation displayed; delta method;
  quadratic contract slope 1.000; realized-misfit multiple —
  curvature gain 0.85→0.33 while level 0.97→0.77 with the
  one-multiple honesty stated; prediction budget on ch8's clock;
  surprise WIDENING — renamed from "gate" to avoid the collision)
  → counting once + the audit (joint-fit-equals-filter proposition;
  yesterday-enters-once inventory reconciling the basket rows with
  the filter state; std(Z) audit on the seeded 500-day world: 3.0
  starved / 1.14 honest / 1.01 widened; jump-day error
  3.8/2.0/0.49 pts — "overconfident and slow at once"; contract
  table; hook to ch11).  7 figures + 54 macros from
  `scripts/ch10/gen_figures.py` (frozen snapshot via ch03's
  loader/fit protocol; self-contained spline/least-squares/gate/
  filter machinery in figlib implementing exactly the displayed
  equations; the seeded audit walk is the chapter's only
  randomness).  Notation added BEFORE writing (O, Ô⁻/Ô_obs/Ô⁺ with
  calligraphic-V variances, gain 𝒦, support 𝒬, basket ω_a,
  information ℐ at two scales, gate(·)/γ, row weights λ_j, audit 𝒵
  — MCS owns ζ, q_walk, Δt_days; handles named in words, curvature
  symbol-free per rule 6); references +Kalman 1960, Anderson–Moore,
  Gelman et al., Lehmann–Casella, Tikhonov–Arsenin.  Newcomer
  fresh-reader pass run (sub-agent persona): all 9 files
  summarizable, 19 findings ALL resolved (headliners: the §10.7 row
  inventory omitted the shape baskets' fate — now "yesterday enters
  once" reconciles them; the jump experiment's flat per-row prior
  weights contradicted §10.2's budget-split rule — the SCRIPT was
  changed to implement the displayed rule, which closed the
  moderate BF gate by the factor of four and improved the exhibit;
  the coverage test was undefined — now defined as a deficit vs
  desired coverage; the information-matrix inverse asserted — now
  derived in the one-parameter case; the 60-bp prediction-budget
  arithmetic fixed to a four-day state; "surprise gate" renamed
  widening; spline/knots/kernel/likelihood/ill-posed glossed;
  "barely moves" honesty; process→prediction budget unified) plus
  every per-section stumble; math verified line by line by the lead
  (combination algebra, gate shares, harmonic worked numbers,
  nullspace proof, update/posterior-variance algebra, vignette
  gains and posteriors, covariance slope, MAP identity).  Full book
  builds clean at 211 pp, no undefined refs, no ch10 overfulls.
  Next: Chapter 11 (the graph: one surface from a sparse universe)
  — the book's final content chapter, then Chapter 1.
