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

## Status (2026-08-08)

Content is COMPLETE: Chapters 2–11 are written, the mathematics is
verified, every figure and number regenerates from the frozen data,
and the build is 231 pages.  The chapters are well organized.

The prose is not done.  On 2026-08-08 the author reviewed the full
build and rejected the REGISTER the text drifted into: audit rhetoric,
a defensive stance ("honest", "audit", promises, claims, stacked
caveats, discussions of controls), and vague terminology.  The style
contract below was rewritten to make the target register explicit and
checkable.  Every chapter now gets a style revision pass — mathematics,
figures, macros and labels stand; the prose is re-registered, shortened
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

Working title: *The Volatility Surface as a Field of Probability
Laws* (placeholder — decide at introduction time).  Author: Thibaut
Delahaye.

Thesis (the thread every chapter serves): an implied-volatility
surface is a family of probability laws read through the Black
formula.  Each chapter separates, for its subject, what follows from
probability (validity), what the market determines (information), and
what the modeler must choose and state (convention).

Structure: three parts, eleven chapters.

| Ch | Title (working) | Content | Style pass |
|----|----------------|---------|------------|
| 1  | Introduction | write LAST, after the style arc | — |
| **Part I — Models** | | | |
| 2  | The log-quantile-density model | done | DONE 2026-08-08 |
| 3  | SVI-JW and superposition | done | DONE 2026-08-08 |
| 4  | Local volatility | done | DONE 2026-08-08 |
| 5  | Integrals and wings | done | DONE 2026-08-08 |
| **Part II — The observation** | | | |
| 6  | Forwards, dividends, and carry | done | pending (moderate) |
| 7  | Removing early exercise | done | pending (moderate) |
| 8  | The market's clock | done | pending (moderate) |
| **Part III — Dynamics and inference** | | | |
| 9  | Spot–vol dynamics | done | pending (moderate) |
| 10 | Filtering and priors | done | pending (heavy) |
| 11 | The graph | done | pending (heavy) |

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

## Chapter 1 — Introduction (write after the style arc)

Content: the problem (finitely many noisy prices; a surface of laws
must be published); the separation thesis (validity / information /
convention); what is assumed of the reader; the book's map, one
paragraph per chapter; the notation ledger; the data statement (one
frozen snapshot threads every example).  Must DEFINE the recurring
device "the reference implementation" (used since Chapter 2 as an
unnamed actor).  Chapter 11's closing pages return to the
introduction's opening problem — write Chapter 1 so that it poses
exactly that problem.  Decide the title with the author.  Some of
Chapter 2 §1 (the smile-as-law argument) may migrate here — decide
then, keeping Chapter 2 self-contained.

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
