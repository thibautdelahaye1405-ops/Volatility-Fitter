# The Volatility Book — roadmap

This file is the ONLY entry point for book sessions.  A session reads:
(1) this file, (2) the style contract below, (3) the chapter(s) it is
revising, (4) where useful, one already-revised chapter as the current
exemplar.  Nothing else.

## Context hygiene (read this first, every session)

The book must read like a polished textbook.  The repository around it
is an application with years of engineering history; that history is
poison for the prose.  Therefore:

- Do NOT read: the app `ROADMAP.md`, `backend/backtest/**`,
  `Docs/notes/reviews/**`, `Docs/notes/build_*/`, FINDINGS files,
  certification/benchmark material, or memory entries about campaigns,
  perf arcs, or UI work.
- Do NOT open the app, fetch live data, or run backtests.  The data
  policy below covers every empirical need.
- The source notes (`Docs/notes/*.tex`) are closed: every content
  chapter is written.  Do not reopen them during the style arc — the
  drift this arc repairs came largely from their vocabulary.
- The implementation, when mentioned, is always "the reference
  implementation".  No product names, no repo paths, no internal note
  citations — public literature only.

## Status (2026-08-08 — THE BOOK IS COMPLETE)

Content AND style are COMPLETE.  Chapters 2–11 are written and
re-registered to the style contract below (the full revision arc ran
2026-08-08, chapters in book order, one commit each); Chapter 1 (the
introduction) was written last, under the contract, on 2026-08-08;
the title is DECIDED with the author: *The Volatility Surface as a
Field of Probability Laws*.  The build is 235 pages (introduction
pp. 1–8, ch. 2 at p. 9), one pre-existing 1.03pt overfull in ch. 3,
no undefined references, banned-grep zero everywhere except
protocol-protected identifiers (labels, macro names, file/function
names — logged per chapter below).  Every figure and number
regenerates from the frozen data.

What remains is OPTIONAL: publication mechanics only (copyright
page, an index if a publisher wants one, print geometry).  Take
these up only if the author asks.  The fresh-reader pass on
Chapter 1 ran 2026-08-08 (eleventh session): a newcomer-persona
sub-agent read the preface + ch. 1 cold (first-course calculus/
probability, Black–Scholes seen once, no other chapters), reported
16 stumbles and a positive verdict (no blockers; the dominant
disease was terms of art arriving before the gloss §1.4 itself
promises).  Fourteen edits were proposed to the author; ELEVEN were
approved and applied (commit 06ad2f3): the preface's December-smile
sentence made factually precise (two smiles, not one — SPY threads
5–10, NVDA is withheld in 11); §1.2's pricing measure defined by
its property (prices are averages under it) and the false "so"
repaired; the butterfly portfolio built in one clause; glosses at
first use for money, wings, total variance, calendar spread,
variance swap, delta, handles, nodes, volatility basis points;
"tenor" dropped; the ch. 2 map blurb rewritten newcomer-readable
(quantile function, not transport-of-logistic vocabulary); the
ch. 4 blurb's "fails no matter how good the data gets" given its
mechanism (noise over squared strike spacing) and
numerator/denominator wording; the harmonic law glossed; "famous"
crush dropped.  THREE were DECLINED by the author — do not re-apply
them: no Black-vs-Black–Scholes bridging clause in §1.2 (P2), no
smile-shape/implied-vol parenthetical at first use in §1.1 (P6), no
European/American gloss in the ch. 7 blurb (P12).  The front-matter
pass ran 2026-08-08 (tenth session): the "A working draft" tag is
dropped from the title page; a one-page Preface
(chapters/00_frontmatter/preface.tex) sits before the Contents at
p. iii — short by design, it defers to Chapter 1 and carries NO
acknowledgements (none invented; the author adds his own); blank
verso pages carry no header/folio (the emptypage idiom inlined in
book.tex — emptypage.sty is not on this machine); ch. 1 §1.2
retitled "Why probability laws" (its ToC line duplicated ch. 2
§2.1's title verbatim).  The INDEX decision: none in this edition —
a subject index means an \index{} pass through finished chapters
and belongs to publication mechanics, not to the draft.  Build: 237
pages (preface iii, Contents v, main matter unmoved: intro p. 1,
ch. 2 p. 9), 1 pre-existing overfull (ch. 3), no undefined refs.

The paragraphs below are kept as the arc's record.  On 2026-08-08
the author reviewed the full
build and rejected the REGISTER the text drifted into: audit rhetoric,
a defensive stance ("honest", "audit", promises, claims, stacked
caveats, discussions of controls), and vague terminology.  The style
contract below was rewritten to make the target register explicit and
checkable.  Every chapter then got a style revision pass — mathematics,
figures, macros and labels stand; the prose was re-registered, shortened
and simplified.

Measured drift (case-insensitive counts over each chapter's .tex
files, 2026-08-08; the trend confirms the author's reading — the
drift grows monotonically through the book):

| Ch | honest* | audit* | promise* | claim* | refuse/convict/disclose | depth of pass |
|----|--------:|-------:|---------:|-------:|------------------------:|---------------|
| 2  | 0 | 10 | 0 | 5 | 0 | light scrub |
| 3  | 2 | 0  | 2 | 2 | 0 | light scrub |
| 4  | 2 | 4  | 4 | 2 | 1 | light |
| 5  | 2 | 7  | 3 | 2 | 6 | light |
| 6  | 6 | 3  | 0 | 4 | 3 | moderate |
| 7  | 14 | 1 | 2 | 0 | 10 | moderate |
| 8  | 11 | 12 | 4 | 2 | 1 | moderate |
| 9  | 9 | 6  | 2 | 1 | 6 | moderate |
| 10 | 28 | 58 | 2 | 5 | 6 | heavy — partial redraft |
| 11 | 19 | 29 | 1 | 10 | 8 | heavy — partial redraft |

Order of work: book order, 2 → 11, one to three chapters per session
(light chapters batch; 10 and 11 take a session each).  Working in
book order lets each freshly revised chapter calibrate the next
session's ear.  Commit per chapter.  THEN Chapter 1 (the
introduction, written last) together with the title decision.

## The style contract (2026-08-08 — this governs)

This contract supersedes the 2026-08-05 pedagogy contract by
extension: the lesson structure (part A) is unchanged; the register
(part B) is new and is what the revision arc enforces.  The style bar
is a mix of Claude Shannon, Albert Einstein, Alan Turing and John
Milnor: simple, concise, precise prose in the indicative mood;
definitions, theorems, proofs, worked numbers, and intuition —
nothing performed, nothing defended.  DEFINE, EXPLAIN, SHORTEN,
SIMPLIFY.  It is a mathematics textbook: not poetry, not a novel, not
a philosophical essay, and not the defense of a thesis under attack.

### A. The lesson (unchanged from 2026-08-05)

The reader: smart, motivated, new to the subject.  Black–Scholes,
calculus and probability at first-course level; has read the earlier
chapters once.

1. Plan as a lesson: 3–5 things the reader can do afterwards,
   recorded as the comment block in chapter.tex; whatever serves none
   of them is cut.
2. One idea per paragraph; short declarative sentences.
3. Concrete before abstract: the smallest example first — three
   quotes, a 2×2 matrix, one worked number the reader can reproduce.
4. Say why before a derivation and restate the result plainly after.
5. Show the algebra: any step a first-course reader could not
   reproduce is written out.
6. Re-introduce terms of art with a one-line plain reminder at first
   use in each chapter.  Keep the symbol count low.
7. Repetition of orientation is a feature: open each section with
   where we are, close with what we now have.
8. 5–8 figures per chapter, each walked panel by panel in the text,
   with clear, explanatory captions.
9. 15–22 pages per chapter; one boxed display at most.

### B. The register (2026-08-08 — the revision arc enforces this)

**Banned outright** (the pass ends with ZERO occurrences in the
chapter's .tex files and in its figures' rendered text — panel
titles, captions, legends):

- "honest", "honesty", "honestly", "dishonest" — methods are correct
  or incorrect, exact or approximate, consistent or inconsistent;
  never honest.
- "audit", "audited", "auditable" — and the audit *posture* with it.
- "promise", "promised" — the text never announces obligations to the
  reader; it states results.
- "claim" (any form) — nothing is claimed; it is stated, derived,
  measured, or assumed.
- "caveat" — and caveat *stacks* with it (see rule 3).

**Replace on sight** (the defensive/moralizing register): refuse,
refusal, convict, disclose, confess, betray, cheat, defensible,
discipline (as a virtue), prudent, modest, "on the record", "earn"
(as in "data must earn the move"), "owns that", "the price of".
Replace each by the mechanism: what equation holds, what quantity is
zero, what the solver returns.

**Vague terminology**: every noun phrase names a defined object.
Replace "the machinery / the apparatus / the construction / the
story" by the specific noun — the solver, the objective, the update,
equation (N).  Delete metaphor-carriers: "wearing X clothes", "grown
up", "in one breath", "load-bearing", "the part that matters",
"conscience", "bookkeeping" (unless the sentence is literally about
accounting identities).

**Sentence-level rules:**

1. Indicative mood throughout.  Never announce that something will be
   proved, is being proved, or has been proved; write "Proposition.
   … Proof. …", then one plain-language restatement of the *fact* —
   not of the achievement.
2. A limitation is stated once, where it binds, as a statement of
   scope ("the ratio assumes a flat volatility term structure") — 
   never repeated, never as a concession, and never gathered into
   defensive lists.  The closing three-column table
   (proved / measured / chosen) is the single home for scope; body
   text does not rehearse it.
3. Delete meta-commentary about the text itself ("worth saying
   plainly", "the chapter's verdict", "hold this against the
   thesis").  If a sentence is about the writing rather than the
   mathematics, cut it.
4. No applause for the results ("remarkably", "beautifully",
   "strikingly"); the number and its meaning suffice.
5. At most one aphorism per chapter; when in doubt, none.

**What the text must KEEP and ADD (the positive list):**

- Heuristics, intuition, and physics analogies, flagged as such.
  Canonical ones for this book: precision as electrical conductance
  (precision-weighted averaging = conductances in parallel; the chain
  variance law = resistors in series; the harmonic combination of
  Chapter 10 = series resistance); diffusion/heat flow for smoothing;
  a measurement in the Gaussian sense as a spring of stiffness 1/σ².
- Examples tied to real market quotes and situations (the frozen
  SPY/NVDA boards are the canonical source).
- Propositions, theorems, formulas, and full derivations.
- Empirical, numerical and experimental statements with their
  measured values (macros), stated plainly.
- Well-commented figures with explanatory captions: a caption says
  what is plotted, how to read it, and what to notice.

### C. Mechanics (unchanged)

Derive, don't assert; proofs ≤ half a page stay in the text, longer
ones go to the chapter appendix.  One notation ledger (NOTATION.md);
new symbols added there before use, never redefined.  Primes for
one-variable derivatives, ∂ for partials; τ is always variance time.
Every empirical number is a generated macro; figures come from the
per-chapter script reading frozen data only.

## Canonical renamings (decided once, applied book-wide)

The recurring devices keep one name each across all chapters:

| Old (banned register) | New (canonical) |
|---|---|
| the audit; the audit statistic | the standardized-error test (the 𝒵 test): std(𝒵) = 1 when stated variances match realized errors |
| honest variance / band / budget | *consistent* variance / band (define at first use per chapter: a stated variance is consistent when std(𝒵) = 1) |
| honest-to-conservative bands | conservative bands (std(𝒵) < 1) |
| overconfident (bars too narrow) | keep — standard forecasting usage, glossed once |
| "the machinery refuses / no-lit-path honesty" | the information matrix is singular on such a component; the solver returns the baseline with the stated default variance and a flag |
| "counting once" (Ch. 10/11 accounting identities) | keep — it names an identity |
| "the chapter's contract" (closing table) | keep the table and the three columns (proved / measured / chosen); rewrite the cells to the register |
| "the reference implementation" | keep — Chapter 1 defines it |
| "the dial nobody may own" (Ch. 10 §) | "The gain is computed, not set" |
| "The accountant: what the joint solve refuses to invent" (Ch. 11 §) | "Silent neighbours, repeated routes, and empty components" |
| "The audit, and one honest repair" (Ch. 11 §) | "The standardized-error test, and the idiosyncratic floor" |
| "Two honest budgets" (Ch. 10 §) | "Two variance budgets" |
| "Counting once, and checking the bars" (Ch. 10 §) | "Counting once, and testing the stated variances" |

Section labels (`\label{...}`) never change; only titles and prose.

## The revision protocol (per chapter)

1. Grep first: the banned list over the chapter's .tex files AND its
   `scripts/chNN/figlib` sources (panel titles, captions, legends,
   macro meaning strings).  This is the work list.
2. Read the chapter start to finish; rewrite sentence by sentence to
   part B.  In Chapters 10–11 some subsections are *structurally*
   defensive (built as pleas) — redraft those paragraphs from their
   mathematics up, don't patch words.  Shorten as you go: the pass
   should leave each chapter the same length or shorter, never
   longer.
3. Untouched: mathematics, derivations, numerical values, macros
   (names and values), figure geometry, labels, cross-references,
   the lesson-goals comment (update its wording if it carries banned
   terms).  Changed where needed: section/subsection titles (per the
   renaming table), figure panel titles/captions/legends (edit the
   script, regenerate the figure — values must not move), synopsis
   blocks (rewrite tight), closing-table cells.
4. Add, where natural (do not force): one heuristic or physics
   analogy per chapter from the positive list; nothing else new.
5. Definition of done: banned-grep zero (chapter .tex + its figlib);
   register read-through passes part B; length ≤ before; figures
   regenerated where their rendered text changed, byte-stable
   values; full book builds clean (no errors, no undefined refs, no
   new overfulls); commit ("style(book): chapter N re-registered").
6. NOTATION.md: entries whose *meaning text* uses banned vocabulary
   (e.g. 𝒵 "the audit statistic") are reworded in the same session
   as their chapter.

No fresh-reader persona pass during this arc (the content was already
reviewed); the register read-through by the lead replaces it.  If a
sentence resists simplification, delete it and check whether anything
is missing — usually nothing is.

## Chapter dossiers (for the pass)

Facts a session needs without re-deriving them.  Pages refer to the
2026-08-07 build (231 pp).

- **Ch. 2 — the LQD model** (pp. 7–38; retrofit of the standalone
  paper).  Light scrub: 10 "audit" hits (mostly §7/appendix
  certificate prose), 5 "claim".  Its denser monograph register is
  acceptable to the author ("not far from the objective") — scrub
  the banned words, shorten where easy, do not re-register wholesale.
- **Ch. 3 — SVI-JW and superposition** (pp. 39–64).  Near target.
  Scrub the isolated hits; tighten the synopsis.
- **Ch. 4 — local volatility** (pp. 65–89).  Light: scattered hits;
  check the "promise/promised" transitions between sections.
- **Ch. 5 — integrals and wings** (pp. 89–105).  Light: "refus*"
  cluster in the envelope/wing-choice sections; "the honest
  surprise" phrasing in the term-structure part.
- **Ch. 6 — forwards, dividends, carry** (pp. 109–125).  Moderate:
  "honest discriminator", masking-experiment prose leans defensive.
- **Ch. 7 — early exercise** (pp. 127–143).  Moderate: 14 "honest"
  + 10 refuse/disclose — concentrated in the subtraction (§7.4
  no-root paragraphs) and §7.7 fitted-vs-discarded prose.
- **Ch. 8 — the market's clock** (pp. 145–161).  Moderate: 12
  "audit" (the planted-event study is *named* an audit — rename per
  the table), "honest" in the inverse-problem and frozen-boards
  sections.
- **Ch. 9 — spot–vol dynamics** (pp. 165–182).  Moderate: "honest"
  in the wings/field sections; audit language around the dt-check.
- **Ch. 10 — filtering and priors** (pp. 183–199).  HEAVY.  The
  chapter's frame ("two honest budgets", "the audit: were the error
  bars true?", "the dial nobody may own") must be re-registered per
  the renaming table; the 𝒵 device becomes the standardized-error
  test everywhere; the audit figure's panel titles and caption
  regenerate; §10.7's accounting prose (quote-counted-twice,
  yesterday-enters-once) is good mathematics wrapped in plea — keep
  the identities, redraft the wrap.  NOTATION.md: 𝒵 meaning text.
- **Ch. 11 — the graph** (pp. 203–221).  HEAVY.  Rename §11.4 and
  the §11.7 subsections per the table; the synopsis, the
  "accountant" frame, "refusals" list, and the closing pages carry
  most of the drift; fig_gr_complete panel (c) title ("the audit")
  regenerates; the invariant-style vocabulary ("no invented signal,
  ever") becomes stated properties of the objective.  The closing
  pages of the book stay — rewritten to the register (they end the
  book; they must read like Milnor's last page, not a summation to
  the jury).

## The book

Title (DECIDED with the author, 2026-08-08): *The Volatility Surface
as a Field of Probability Laws*.  Author: Thibaut Delahaye.

Thesis (the thread every chapter serves): an implied-volatility
surface is a family of probability laws read through the Black
formula.  Each chapter separates, for its subject, what follows from
probability (validity), what the market determines (information), and
what the modeler must choose and state (convention).

Structure: three parts, eleven chapters.

| Ch | Title (working) | Content | Style pass |
|----|----------------|---------|------------|
| 1  | Introduction | DONE 2026-08-08 (written last) | written to the contract |
| **Part I — Models** | | | |
| 2  | The log-quantile-density model | done | DONE 2026-08-08 |
| 3  | SVI-JW and superposition | done | DONE 2026-08-08 |
| 4  | Local volatility | done | DONE 2026-08-08 |
| 5  | Integrals and wings | done | DONE 2026-08-08 |
| **Part II — The observation** | | | |
| 6  | Forwards, dividends, and carry | done | DONE 2026-08-08 |
| 7  | Removing early exercise | done | DONE 2026-08-08 |
| 8  | The market's clock | done | DONE 2026-08-08 |
| **Part III — Dynamics and inference** | | | |
| 9  | Spot–vol dynamics | done | DONE 2026-08-08 |
| 10 | Filtering and priors | done | DONE 2026-08-08 |
| 11 | The graph | done | DONE 2026-08-08 |

## Infrastructure and build

`Papers/book/` is the single master.  Build: `pdflatex book && bibtex
book && pdflatex book && pdflatex book` from `Papers/book/` (no
latexmk on this machine).  If `book.pdf` is locked by a viewer, build
with `-jobname`, swap when the lock clears, then rerun the canonical
jobname so book.aux/bbl stay consistent.  Fast single-chapter builds:
`\includeonly` in book.tex.  Figures: `scripts/chNN/gen_figures.py`
(repo venv) emit `figures/chNN/*.pdf` + a per-chapter macros file;
`--only fig_x` refreshes one figure (the macro store persists).
Never bulk-edit .tex with shell one-liners; use the Edit tool.
Lettered appendices via the `chapterappendices` environment.  Each
chapter file opens with `\renewcommand{\figdir}{figures/chNN}`.
NOTATION.md is the ledger; the \Mac macro namespace is book-global
with per-chapter prefixes.  Under numeric natbib use \citet/\citep,
never \citealp.

## Data policy

One frozen snapshot threads the book:
`data/lqd_paper_snapshot_20260804_0208.json` (SPY + NVDA, 8 expiries
each, 2026-08-03 session, haircut LQD-16 fits, embedded chains and
quotes).  No refetching, ever; figures regenerate from frozen files
only.  The style arc adds NO new data and NO new numbers — if a
rewritten sentence needs a number that is not a macro, the sentence
is wrong, not the macro set.

## Chapter 1 — Introduction (DONE 2026-08-08)

Written to this spec: the problem (§1.1 poses exactly the predicament
ch. 11's closing pages return to, same cadence); the separation
thesis (§1.3); the reader and reading conventions incl. the notation
ledger (§1.4); the reference implementation DEFINED and the frozen-
data statement (§1.5); the map, one paragraph per chapter in three
parts (§1.6, ending "— which is where we begin").  §1.2 states the
smile-as-law reading in one display (Breeden–Litzenberger) and
points to Chapter 2; NOTHING migrated out of Chapter 2 §1 — it stays
self-contained (decision recorded here).  No figures, no macros: the
introduction quotes no measured number (qualitative allusions only).
Labels: sec:intro{problem,law,thesis,reader,impl,map} (ch. 2's
sec:intro was taken).  Title decided the same session.

## Progress log

(The content-writing log, 2026-08-04 → 2026-08-07, lives in git
history — `git log --follow Papers/book/ROADMAP.md`, through commit
6d310e5.  This log restarts with the style arc.)

- 2026-08-08: author review of the full 231-page build: content
  complete and well organized, but the register has drifted —
  audit rhetoric, defensive stance, "honest/honesty", repeated
  caveats, vague terminology.  Style contract rewritten (part B:
  banned list, replacements, sentence rules; positive list:
  heuristics/physics analogies, market examples, proofs, measured
  numbers).  Drift measured per chapter (table above; monotone
  growth 2 → 11 confirms the author's reading).  Roadmap rewritten
  from scratch around the revision arc: chapters 2–11 in book
  order, then Chapter 1.
- 2026-08-08: Chapters 2 and 3 re-registered (light scrubs).
  Banned-grep zero in both chapters' .tex and figure text.  Ch. 2:
  the five \MacAudit* aliases in §7 switched to their canonical
  \MacCert* names (values identical; alias layer untouched);
  fig_exact / fig_jacobian / fig_butterfly / fig_calendar
  regenerated for re-worded panel titles and one annotation —
  every macro value byte-identical, timing block not re-run.
  Ch. 3: synopsis tightened; isolated hits scrubbed ("promised",
  "honest units", "earns the claim", "machinery", "bookkeeping",
  "at the price of").  NOTATION.md: one banned word in the ch. 4
  `v` entry reworded; the 𝒵 entries stay for the ch. 10 session.
  Build: 231 pages, chapter boundaries unchanged, 1 overfull
  (pre-existing), no undefined refs.  Next: Chapter 4 (light).
- 2026-08-08 (second session): Chapters 4 and 5 re-registered (light).
  Banned-grep zero (incl. refuse*/disclose* replace-on-sight) in both
  chapters' .tex.  Ch. 4: the "promise/promised" section transitions
  reworked (validity structural rather than policed; "the promised
  discipline" -> the discrete side); "honest caveat" -> one limit of
  the repair; captions "audited" -> "checked"; the refined "(audit)"
  operator loses the parenthetical (ch. 5's appendix follows).
  Ch. 5: the three-route agreement language moves from audit to
  test/check; "refuses to select" -> bounds without selecting;
  "honesty requires showing it" -> showing it takes that range;
  "disclose/disclosed" -> state/stated throughout; "Part II starts by
  earning them" -> inferring them from the quotes.  NO figure text
  changed in either chapter, so no figures regenerated.  Build: 231
  pages, boundaries unchanged (65/89/109), 1 pre-existing overfull,
  no undefined refs.  Next: Chapter 6 (moderate).
- 2026-08-08 (third session): Chapter 6 re-registered (moderate).
  Banned-grep zero (the one surviving "earns" is literal interest
  accrual — "a dollar earns", kept).  The flagged spots: "the honest
  discriminator" -> the quantity that separates the conventions; the
  masking-experiment close redrafted to mechanism (quotes whose
  residuals expose them / leaves no residual; "builds that defense
  and is honest about its reach" -> builds that safeguard, with a
  stated reach); "the identifiability audit" renamed the
  identifiability experiment (text + appendix + figlib meaning
  string, fig_fwd_ident re-run seeded, values byte-identical);
  borrow section: "noise wearing a suit" -> noise, "guess dressed in
  the estimator's output format" -> a guess in a measurement's
  format, "honest output" -> correct output, "two caveats bound the
  whole enterprise" -> two limits bound the estimator, "declaring
  victory" dropped; "disclosed" -> stated (3 sites); "owed to the
  user" dropped from the contract intro.  Build: 231 pages,
  boundaries unchanged (109/127), 1 pre-existing overfull, no
  undefined refs.  Next: Chapter 7 (moderate — "honest" and
  refuse/disclose concentrated in §7.4 no-root and §7.7
  fitted-vs-discarded).
- 2026-08-08 (fourth session): Chapter 7 re-registered (moderate).
  Banned-grep zero.  The no-root device is now a FLAG throughout
  ("honest output is a refusal" -> the output is a flag; "refuses it
  honestly" -> returns a flag instead of a number; "its honest
  refusal" -> its no-root flag; §7.4 subsection retitled "When the
  root exists, and when it does not").  §7.7 retitled "How much it
  matters, by population" — the population device replaces the
  "honestly" framing; "honest bookkeeping of populations" -> the
  measured split of populations.  "The subtraction is honest" ->
  exact (its precise meaning); escrow "honest label/default" ->
  point of precision / correct default; "promised ... we now pay the
  debt" -> indicative; "clear conscience" -> without loss; "noise
  wearing a suit" -> noise (second occurrence book-wide); "disclosed"
  -> stated (5 sites); literal "a dollar earns interest" instances
  kept.  One contract cell shortened ("a numerical-target dial", the
  "stated" dropped as redundant in the Convention column) to stay at
  the pre-existing single overfull.  No figure text changed, no
  regeneration.  Build: 231 pages, boundaries unchanged (127/145),
  1 pre-existing overfull, no undefined refs.  Next: Chapter 8
  (moderate — the planted-event study is NAMED an audit; rename per
  the table; "honest" in the inverse-problem and frozen-boards
  sections).
- 2026-08-08 (fifth session): Chapter 8 re-registered (moderate).
  Banned-grep zero (the many "earnings" hits are the corporate event,
  untouched).  The planted-event AUDIT is now the planted-event STUDY
  everywhere — caption, derivation prose ("the study's
  configuration/measured pair"), contract cell ("The study", same
  width — no overfull risk), appendix ("the study is the reference"),
  figlib docstrings; "the estimator is audited" -> is measured.
  "This chapter earns the distinction" -> separates them; "the claim
  to be earned" -> the fact to establish; "do the discrete case
  honestly" -> in full; "honest boundary/limits/general statement" ->
  scope words; "the honest price tag" -> the cost; "the audit's
  flat-ladder promise kept" -> the study's flat-ladder result
  repeated; "telling the clock story about everything" ->
  attributing everything to the clock; "bookkeeping(s)" ->
  additivity (walk) / currencies (clock, matching the chapter's own
  "in this currency") / counting choice (normalization); "an honest
  clock" -> the market's clock (the chapter title); "disciplined
  run" -> the run with a horizon.  No figure text changed, no
  regeneration.  Build: 231 pages, boundaries unchanged (145/165),
  1 pre-existing overfull, no undefined refs.  Next: Chapter 9
  (moderate — "honest" in the wings/field sections; audit language
  around the dt-check).
- 2026-08-08 (sixth session): Chapter 9 re-registered (moderate — the
  last moderate chapter; Part I-III up to ch. 9 now done).  Banned-
  grep zero except the protocol-protected macro NAME
  \MacSsrRepAuditPct (no alias layer in ch. 9; prose around it says
  "marching-step check").  Section retitles: §9.2 "Two coordinate
  systems, two sign rules" (was "one discipline"), §9.4 "The stakes
  of the choice: delta" (was "The price of the choice").  The
  dt-check: "audit" -> check in the appendix and the figlib meaning
  string; fig_ssr_reprice re-run (deterministic, values
  byte-identical).  "An honest clock" -> the market's clock (ch. 8
  continuity, 2 sites); "owes the reader a confession" -> the two
  derivations do not share a chart; "note of honesty" -> note of
  precision; "second-order honesty" -> second-order error; "the
  honest arbiter" -> the arbiter; "bookkeeping" -> sign conventions;
  "discipline" -> rule; "load-bearing" -> carries more weight;
  "re-audited" -> re-checked; "no snapshot can audit" -> can test.
  Build: 231 pages, boundaries unchanged (165/183), 1 pre-existing
  overfull, no undefined refs.  Next: Chapter 10 (HEAVY — the frame
  "two honest budgets"/"the audit: were the error bars true?"/"the
  dial nobody may own" re-registers per the renaming table; 𝒵
  becomes the standardized-error test everywhere; the audit figure's
  panel titles and caption regenerate; §10.7 redrafted from the
  identities up; NOTATION.md 𝒵 meaning text in the same session).
- 2026-08-08 (seventh session): Chapter 10 re-registered (the first
  HEAVY pass).  Banned-grep zero except protocol-protected NAMES
  (labels sec:/fig:infaudit, macros \MacFiltAudit*, file/function
  fig_audit/fig_flt_audit, store key "audit" — the ch. 9
  \MacSsrRepAuditPct precedent).  Renaming table applied in full:
  §10.6 "Two variance budgets", §10.7 "Counting once, and testing the
  stated variances", §10.5.2 "The gain is computed, not set", §10.7.2
  "The standardized-error test" — the 𝒵 device is the
  standardized-error test everywhere, and "consistent" is defined at
  its first use (std(𝒵)=1: stated variances match realized errors);
  the audit-run naming became mechanism naming (starved / true-scale
  / widened).  Synopsis rewritten (no promise-kept frame); §10.7
  redrafted from the identities up ("bookkeeping and conscience"
  opener cut; the quote double count stated as mechanism;
  "verdict"/"smuggled" gone); the "dial marked trust" paragraph
  rebuilt around the gain as an output with definitions (§10.6) and
  a test (§10.7).  "Honest budget / honesty points / honest repair /
  convicts / disclosed / claims / admits" all replaced by mechanism;
  "in other clothes" -> in other coordinates; "load-bearing" ->
  decisive; the dangling "flapping" -> the flat directions.  ADDED
  the canonical electrical picture (one analogy, two halves):
  precisions add = conductances in parallel (§10.2.1), the harmonic
  law = resistances in series, a dead leg = a near-infinite resistor
  (§10.3.1).  Four figures regenerated for rendered text only
  (fig_flt_gate "owns" -> carries in callout/ylabel; fig_flt_update
  panel (b) "trust, computed per handle" -> "gains computed, not
  set"; fig_flt_covar "turns the dial itself" -> "lowers the gain";
  fig_flt_audit legends "honest budget" -> "true-scale budget" +
  panel (b) "the audit curve" -> "the standardized-error test" +
  meaning strings) — every macro value byte-identical, seed
  untouched.  NOTATION.md: both 𝒵 meaning texts reworded (ch. 10
  entry + the ch. 11 intro's "same audit statistic").  Build: 231
  pages, boundaries unchanged (183/203), 1 pre-existing overfull
  (ch. 3), no undefined refs.  Next: Chapter 11 (HEAVY, one session
  — rename §11.4 and the §11.7 subsections per the table; the
  synopsis, the "accountant" frame, the "refusals" list and the
  closing pages carry most of the drift; fig_gr_complete panel (c)
  title regenerates; the closing pages re-registered to end the book
  like Milnor's last page, not a summation to the jury).
- 2026-08-08 (eighth session): Chapter 11 re-registered — THE STYLE
  ARC'S CHAPTER PASSES (2–11) ARE COMPLETE.  Banned-grep zero except
  protected NAMES (label sec:infaudit refs, \MacGrAudit* macros,
  universe.audit_std / fig file names).  Renaming table applied:
  §11.4 "Silent neighbours, repeated routes, and empty components"
  (was "The accountant: what the joint solve refuses to invent"),
  §11.7.2 "The standardized-error test, and the idiosyncratic floor"
  (was "The audit, and one honest repair"); "the audit" is the
  standardized-error test everywhere; the no-lit-path REFUSAL became
  the mechanism (objective flat, information matrix singular on the
  component, solver returns baseline + stated default band + flag);
  the closing thesis "list of refusals" became stated properties of
  the objective (no move without a lit innovation, no transfer from
  a silent neighbour, one count per source, marginal confidence, no
  posterior on an unlit component).  Scrubs: "lit data must earn
  every departure" -> every departure is priced by the lit
  innovations (synopsis + goals); "betray/cheat/convicted/
  disclosed/prudent/claim(s)" -> mechanism words; "event logic
  wearing scenario clothes" -> applied to a scenario; "in graph
  clothes" -> at graph scale; "grown up" -> at universe scale;
  "load-bearing sentence" -> the policy is one sentence; "the
  story" (vague-list) -> the example throughout §11.6 (+ NOTATION
  t_1/2 entry); "case file" -> fixture/mechanism; "worth
  saying/stating" meta cut.  The closing pages keep their shape,
  re-registered: "the observation was earned" -> had to be
  inferred; "taught one discipline" -> kept one rule; "a band,
  audited" -> a band, tested; the final sentence ends on "keeping
  those two accounts separate, and adding them up correctly"
  (Gaussian accounting — every assumption stated, every source
  counted once).  ADDED the electrical picture's ch. 11 half (one
  flagged parenthetical at the chain law: hops = resistors in
  series, a receiver's informers = parallel conductances).  Two
  figures regenerated (fig_gr_complete panel (c) "the audit" ->
  "the standardized-error test"; fig_gr_account meaning-string
  sync) — every macro value byte-identical, seed untouched.
  Build: 231 pages, boundaries unchanged (183/203/221), 1
  pre-existing overfull (ch. 3), no undefined refs.  Next (final):
  Chapter 1 — the introduction, written fresh under the contract
  (content spec in "Chapter 1" section above: the problem, the
  separation thesis, the reader, the map, the notation ledger, the
  data statement, DEFINE "the reference implementation"; ch. 11's
  closing pages return to exactly the problem ch. 1 poses) — plus
  the title decision WITH the author.
- 2026-08-08 (ninth session): Chapter 1 WRITTEN and the TITLE
  DECIDED — THE ARC, AND THE BOOK, ARE COMPLETE.  Title (author's
  choice among four candidates, working title confirmed): *The
  Volatility Surface as a Field of Probability Laws*; book.tex
  header comment updated (the \title was already this text; the
  "A working draft" tag stays for now).  Chapter 1 (~7pp, six
  sections, no figures, no macros — no measured number quoted):
  §1.1 the predicament, landing on the title phrase and matching
  ch. 11's closing callback verbatim in cadence; §1.2 the
  Breeden–Litzenberger reading in one display + Black-formula-as-
  chart, ch. 2 pointed to and left self-contained (no migration —
  decision recorded in the Chapter 1 section); §1.3 the three bins
  with one example each from the book's own measurements, the
  proved/measured/chosen tables announced, std(𝒵)=1 named as the
  book's acceptance test; §1.4 reader contract, writing rules,
  notation ledger conventions, and the scope paragraph (no
  stochastic-vol/exotics/hedging-beyond-delta); §1.5 the reference
  implementation DEFINED (conventions live in implementations, not
  theorems; named so a choice can be adopted, replaced, or tested)
  + the frozen-snapshot statement and the compounding argument
  (the December smiles' six reappearances listed); §1.6 the map,
  one paragraph per chapter from the chapters' own synopses,
  closing "— which is where we begin."  One aphorism total ("A
  convention is not a flaw; an unstated one is").  Banned-grep on
  ch. 1: zero (two "earnings" = the corporate event, exempt as in
  ch. 8).  Build: 235 pages (intro pp. 1–8, ch. 2 at p. 9, ch. 11
  ends p. 225), 1 pre-existing overfull (ch. 3, unchanged), no
  undefined refs.  Remaining (optional, only on request): a
  fresh-reader pass over ch. 1; front-matter (drop the draft tag,
  preface, index); publication mechanics.
- 2026-08-08 (tenth session): front-matter pass (record in the
  Status block above).  Draft tag dropped; Preface written (one
  page, no invented acknowledgements, listed in the ToC); blank
  versos cleaned via the inlined emptypage idiom; ch. 1 §1.2
  retitled "Why probability laws"; index deliberately deferred to
  publication.  237 pages, main matter unmoved.
- 2026-08-08 (eleventh session): fresh-reader pass on ch. 1 —
  proposals to the author, eleven approved and applied, three
  declined (full record in the Status block above; declined = P2
  Black-vs-BS bridge, P6 smile parenthetical, P12
  European/American gloss — do not re-apply).  Build: 237 pages,
  intro still pp. 1–8, ch. 2 at p. 9, 1 pre-existing overfull
  (ch. 3), no undefined refs.  The book now has no open items
  beyond publication mechanics.
