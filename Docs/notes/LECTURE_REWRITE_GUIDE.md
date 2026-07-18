# Lecture-Edition Rewrite Guide

How to rewrite a technical note as a standalone *lecture edition* — the
process and standards distilled from the Note 01 (LQD → `01_lqd_model_coordinates.tex`)
and Note 04 (Local Vol → `04_local_volatility_forward.tex`) redrafts of 2026-07.
This layers on top of `STYLE_GUIDE.md` (which still governs boxes, macros,
generators, build); where the two disagree for a lecture edition, this file wins.

---

## 1. What a rewrite is

- A **true rewrite from scratch**, not a cosmetic rephrase, in a **new file**
  (`NN_topic_<angle>.tex`); the original note is untouched.
- Each rewrite takes a **genuinely new narrative angle** — a single organizing
  idea the whole document hangs on. Used so far: Note 01 "coordinates on the
  space of smiles: find the chart where no-arbitrage is free"; Note 04 "read
  Dupire backward: from the parameters up". Do not repeat an angle.
- **Content parity**: everything in the original must appear (every result,
  guarantee, caveat, case file, appendix, traceability anchor) — reorganized
  and re-emphasized, never dropped. Build an explicit checklist from the
  original before writing.

## 2. Register — the most important calibration

Write a **mathematics / computational-mathematics lecture** for an audience of
professional quantitative traders plus a few good students. Model the voice on
Steve Shreve (rigor, definitions→theorem→proof rhythm) and David Tong (fluid
narrative, motivation-first, the right rigor/heuristic balance). NOT
engineering documentation of the app.

Concretely:

- **The body carries no product plumbing.** No settings/knob names
  (`gridXNodes`, `FitSettings`…), no gate/byte-identity/test-lock language, no
  "product path" / fixture / schema vocabulary, no commit hashes mid-prose.
  All of it lives in the appendices (atlas, performance notes, traceability).
  A module path in `\texttt{}` may appear in a listing caption or a pointer,
  sparingly. Say "the implementation", "a real SPY chain", "shipped defaults".
- **Derive, don't assert.** Every claim a reader could ask "why?" about gets
  its two-line derivation or a named proof: why an MGF strip is exact, where
  π²s²/3 comes from, why noise at spacing Δk enters a second difference as
  4ε/Δk², why forming JᵀJ squares the condition number. Quantify failures
  (ill-posedness, CFL bounds) rather than describing them.
- **Name the mathematics.** Tikhonov regularization, convex order, Legendre
  duality, M-matrix, envelope theorem, continuation method, Amdahl's law,
  inverse crime. The audience owns this vocabulary; using it is compression.
- **A few short Exercises** (2–3, `\paragraph{Exercise N.}`), Shreve-style:
  small, concrete, answerable in a few lines, each reinforcing a design choice.
- **Case files stay** (the house's best material) but as *lessons in numerical
  pathology*: keep setup→failure→diagnosis→fix→verdict, strip file/knob names,
  and end each with its general principle stated in one italicized sentence.
- **Engineering war stories survive only if the lesson is methodological**
  (e.g. "profile before optimizing; never accept a synthetic-only benchmark").
- A speed/engineering section becomes a **complexity-and-algorithms** section:
  cost accounting in O(·), why levers compose or don't, numerical-linear-algebra
  reasoning. Measured multipliers, machine scopes and shelved-lever ledgers go
  to the performance appendix with their protocol stated in full
  ("machine-dependent numbers belong there").

## 3. Voice rules (hard-won; each was explicit user feedback)

- **The lecture voice must survive the whole document.** The failure mode is
  drift: careful opening, report-like back half. Every section re-earns the
  frame: open with why/where-we-are, close by handing to the next section.
- **Honest and calibrated claims.** If two objects are a bijection, say so and
  frame the issue as units — never "must not be conflated". Scope every
  guarantee (on the hull, under the gate, for the continuous objects). State
  what is control vs theorem, measured vs proved, implemented vs derived.
- **One differentiation convention**, stated once in the notation ledger:
  primes for one-variable functions (C′, w′, σ′), subscripted ∂ for partials
  (∂_k B, ∂G/∂θ). Never mix ∂_k, C′, B_k styles.
- **No near-identical symbol pairs** (ω_i vs w rejected). Prefer deleting a
  symbol over renaming it (per-quote weights became prose). Unify objects that
  are secretly the same (asset share A(z) and calendar curve G_i(α) → one
  ledger G). One time symbol. A **notation ledger table** early in the note
  lists every symbol; nothing is reused with a second meaning.
- **A running example** (one production-fitted object reused across most
  figures) gives the lecture a recurring character.
- Keep the house openers: invariant box near the top (phrased as
  *mathematical* invariants), one `\boxed{}` equation, ~1 aside box per page.

## 4. Figures

- **More figures than the original** (Note 01: 6→12; Note 04: 4→9), every one
  generated by a new per-edition generator (`gen_<topic>_<angle>.py`) running
  **production code** — never a re-implementation. Every quoted number is an
  emitted macro (`<topic>_<angle>_tables.tex`); tiny values in
  `\ensuremath{m\times10^{e}}` form. Reusing figures/macros from a sibling
  edition's suite is allowed; never re-time benchmarks — read the stored
  artifact (e.g. `lv_numbers.json`).
- **Sleekness rules** (each was a rejection once): no in-figure panel titles —
  captions carry the lesson; panel letters via `label_panel`; frameless legends
  placed in *verified-empty* regions, adding ylim headroom if curves peak into
  them; direct annotations with thin leader lines over legend boxes; wide
  content spaced (`wspace`); **render every figure and affected PDF page and
  eyeball for collisions before calling it done**.
- **Explain every figure twice**: a panel-by-panel walk in the prose *and* a
  caption that states the lesson, not the axes. "Figure N is not well
  explained" is a rejection.
- Include a **hero figure of the real object as the app shows it** where one
  exists (e.g. the triangulated 3-D SPY local-vol sheet from the product-path
  response). If drawing it faithfully exposes a code subtlety (the
  degenerate-Delaunay diagonals), put the subtlety in a Remark — the figure is
  evidence, never airbrushed.
- Pedagogically strong figure archetypes to reach for: the *thesis figure*
  (one object in several coordinate systems), the *wrong-way demo* (the naive
  method failing on realistic data), a *mechanism demo* (scheme losing
  monotonicity; shape-vs-handle moves), an *identifiability demo* (two very
  different surfaces, one quote set), and an *audit figure* (analytic vs
  independent finite differences).

## 5. Structure template

Body: problem/motivation (concrete failure first) → construction with
definitions/propositions/proofs → the numerical method and what it inherits →
honesty sections (identifiability; what is measured vs proved) → derivatives →
complexity → case files → worked examples (report quote error and latent-object
error as **two separate numbers**) → what is genuinely original → limitations
("a lecture that sells a model without drawing its boundary is an
advertisement").

Appendices, in order: **A** hyperparameter atlas (all knobs, surfaced+hidden —
the only home for settings names); **B** performance notes (measured
multipliers + protocol + shelved levers + engineering cautions); **C**
traceability table (moved out of the body); **D** reference implementation —
**executed against production before committing**, with the measured agreement
stated in the prose; bibliography last.

## 6. Process

1. Read the original end-to-end; write the content-parity checklist.
2. Choose the new angle; design the notation ledger (fewer symbols, collisions
   resolved by deletion/unification).
3. Write the generator first; run it; iterate on figure sleekness with
   rendered previews. Then write the note in chunks against the macros.
4. Verify the Appendix D listing against production (state the tolerance).
5. Build with `pdflatex` ×2 into `build_<name>/` (latexmk is broken on this
   machine), fix every error/undefined ref/overfull >10pt, copy the PDF up,
   render key pages and eyeball.
6. Expect iterative feedback; apply it globally, not just at the cited spots
   (the comment lists are never exhaustive).

## 7. Status of existing editions

| Note | Edition file | Angle | Generator |
|---|---|---|---|
| 01 LQD | `01_lqd_model_lecture.tex` | distribution-first desk lecture | `gen_lqd_lecture.py` |
| 01 LQD | `01_lqd_model_percentile_ruler.tex` | monotone transport / rubber ruler | `gen_lqd_fresh.py` |
| 01 LQD | `01_lqd_model_coordinates.tex` | coordinates; the chart where no-arb is free | `gen_lqd_geometry.py` |
| 02 SVI | `02_svi_jw_rewrite.tex` | one hyperbola, two languages (raw vs JW charts) | `gen_svi_rewrite.py` |
| 02 SVI | `02_svi_jw_moments.tex` | the wings and the belly; Lee's moment bound is a tail statement | `gen_svi_moments.py` |
| 03 MCS | `03_multicore_mcs_corrections.tex` | base and correction; superposition + a tail-silent local basis; capacity control | `gen_mcs_corrections.py` |
| 04 LV | `04_local_volatility_forward.tex` | read Dupire backward, parameters up | `gen_lv_forward.py` |
| 05 De-Am | `05_deamericanization_stopping.tex` | optimal stopping; subtracting the unobservable premium | `gen_deam_stopping.py` |
| 06 Forwards | `06_forwards_dividends_inference.tex` | statistical inference on one straight line; identifiability ladder | `gen_fwd_inference.py` |
| 07 Objective | `07_calibration_objective_measure.tex` | the objective as units, measure, tolerance | `gen_obj_measure.py` |
| 08 Var swaps | `08_varswap_representations.tex` | one number, three integrals: a pairing evaluated in each model's native chart | `gen_vs_representations.py` |
| 09 Wings | `09_wings_last_quote.tex` | beyond the last quote: prove / choose / police; the limit is not the wing | `gen_wings_lastquote.py` |
| 10 Calendar | `10_calendar_unnamed_martingale.tex` | the unnamed martingale: Kellerer as the organizing theorem; who pays to restore the order | `gen_cal_martingale.py` |
| 11 Event clock | `11_event_market_clock.tex` | the market keeps its own clock: DDS license, the crush as a reading error, the calendar as an inverse problem | `gen_event_market_clock.py` |
| 12 Spot-vol | `12_spotvol_missing_derivative.tex` | the missing derivative: dynamics unidentified by a snapshot; SSR as the one dial; frozen LV derives its own answer | `gen_ssr_derivative.py` |

No edition has been declared the replacement of its original.
