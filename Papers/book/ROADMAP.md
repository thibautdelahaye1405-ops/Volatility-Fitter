# The Volatility Book — roadmap

This file is the ONLY entry point for book sessions. A session that works on
a chapter reads: (1) this file, (2) the style contract below, (3) the source
notes listed in its chapter brief, (4) Chapter 2 (`Papers/lqd_paper/`) as the
style exemplar. Nothing else.

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

## The book

Working title: *The Volatility Surface as a Field of Probability Laws*
(placeholder — decide at introduction time). Author: Thibaut Delahaye.

Thesis (the thread every chapter serves): an implied-volatility surface is a
family of probability laws read through the Black formula. Each chapter
separates, for its subject, what follows from probability (validity), what
the market determines (information), and what the modeler must choose and
disclose (convention).

Register: self-contained chapters of a polished textbook. Voice: a blend of
Shannon, Einstein, Turing, and Milnor; the pedagogical standard is El
Karoui–Geman–Rochet, "Changes of Numeraire, Changes of Measure, and Option
Pricing". Concretely (learned on Chapter 2, enforce everywhere):

1. Plain declarative prose; every abstraction followed immediately by a
   concrete instance. Derive, don't assert; a proof ≤ half a page stays in
   the text, longer proofs go to the chapter appendix.
2. NO audit rhetoric, NO defensiveness, NO repeated caveats. A limitation is
   stated once, as mathematics, where it arises (the model contract table at
   a chapter's end may collect scope in one place). "Honesty" is shown, not
   discussed.
3. One notation ledger for the whole book (see below). One boxed display per
   chapter at most. Primes for one-variable derivatives, ∂ for partials.
4. Every empirical number is a generated macro; nothing data-derived is
   typed by hand. Figures come from one deterministic per-chapter script
   reading frozen data.
5. Concise and progressive: a chapter should run 15–25 pages, sections
   single-subject, transitions explicit ("we now have X; the next question
   is Y").

## Structure (decided 2026-08-04 with the author)

Three parts, eleven chapters. Mapping to notes: 02+03 merged, 08+09 merged,
13+15 merged, 07 and 10 absorbed, all else 1:1. Concept-first order, with
local volatility placed among the models (author's decision).

| Ch | Title (working) | Source notes | Status |
|----|----------------|--------------|--------|
| 1  | Introduction | replaces Note 00; write LAST | pending (last) |
| **Part I — Models** | | | |
| 2  | The log-quantile-density model | 01 | **DONE** (`Papers/lqd_paper/`, 36 pp) |
| 3  | Families in the volatility chart: SVI-JW and superposition | 02 + 03 (+ objective material from 07 not already in Ch. 2) | **DONE** (2026-08-05, ~19 pp) |
| 4  | Local volatility | 04 | next |
| 5  | Integrals and wings: variance swaps beyond the last quote | 08 + 09 (+ cross-expiry statics remainder of 10) | pending |
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
   mine all, follow none) → skim Chapter 2 for voice and conventions.
2. Plan the chapter: section spine (6–9 sections + optional chapter
   appendix), the 6–12 figures, the macros needed. The spine of the LQD
   chapter (object → validity → structure → computation → examples →
   contract) adapts to most subjects but must not be forced.
3. Draft. Writer may be the lead or one writer sub-agent (brief it with the
   style contract verbatim; forbid the excluded context explicitly).
4. Figures: one deterministic script `scripts/chNN/gen_figures.py` reading
   frozen data; emits `figures/chNN/` PDFs + a macros file the chapter
   inputs. Match Chapter 2's visual conventions (restrained palette, (a)/(b)
   panel titles, units on axes, rms annotations where relevant).
5. Review, lean: ONE fresh-reader pass (student persona: knows Black-Scholes
   and the PREVIOUS chapters only — chapters must be self-contained given
   the book so far) + the lead's own math verification of every derivation.
   The full multi-round machinery of Chapter 2 is not repeated unless the
   chapter's mathematics is genuinely new rather than re-derived.
6. Build the whole book (all chapters), check cross-references and the
   notation ledger, commit.

Definition of done: compiles in the book master; 15–25 pp; every derivation
verified by the lead; zero hand-typed empirical numbers; notation ledger
updated; no excluded-context leakage (grep the chapter for "production",
app terms, note references); one fresh-reader pass addressed.

## Chapter briefs

### Ch. 3 — Families in the volatility chart: SVI-JW and superposition (NEXT)

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
