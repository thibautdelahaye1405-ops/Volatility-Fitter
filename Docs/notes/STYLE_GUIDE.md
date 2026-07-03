# Vol-Fitter Technical Notes — Style Guide

The notes in `Docs/notes/` are a book, not a folder of memos. Each note is a
standalone chapter; together they must read as one voice, one notation, one
visual system. This guide records the house style established by the
2026-07 editorial-and-mathematical hardening pass.

**Gold standards.** `01_lqd_model.tex` is the structural template (section
architecture, appendices, verified snippets). `05_deamericanization.tex` is the
narrative model (a production problem told as a story, with the reverted-fix
case file). When in doubt, imitate those two.

---

## 1. The opening contract

Every note opens by answering, in order, the same five questions — as prose in
the first section(s), not as a literal checklist:

1. **Problem** — what goes wrong in production without this machinery?
   Concrete symptom first (a biased wing, a phantom arbitrage, a frozen node),
   never "we now describe…".
2. **Invariant** — what must remain true no matter how sparse or noisy the
   data is? State it in an `invariant` box near the top. One box, short items.
3. **Mechanism** — what mathematical object enforces the invariant? Name it
   early; its defining equation is the note's single `\boxed{}` display.
4. **Implementation** — where the mechanism lives in code. A ≤15-line verified
   crux listing beside the central equation; module paths in `\texttt{}`.
5. **Example** — one small reproducible case (a "case file", §5) showing the
   mechanism mattering.

The abstract compresses all five into one paragraph with the headline measured
numbers (generated macros, never hard-coded).

## 2. Section architecture

Body: problem → construction → theory (theorem-shaped) → production spine →
worked example / case file → "What is original here" → limitations.
Appendices, always in this order:

- **Appendix A — Hyperparameter atlas.** Every knob, surfaced *and* hidden,
  with default and role (`longtable`, split Surfaced / Hidden).
- **Appendix B — Performance notes.** Numbered list of the numerical
  optimizations with measured speed-ups; rejected/reverted attempts included.
- **Appendix C — Reference implementation.** ≤50 lines, numpy/scipy only,
  distilled from the production module and **executed against it** before
  committing (state the agreement level in the surrounding prose, e.g.
  "reproduces `build_slice` to 1e-10"). Never pseudo-code.
- Bibliography last, inside the note (`thebibliography`).

No inline `file:line` references in the body — module paths only. A
**traceability table** (claim → equation/proposition → code module → test
file) goes at the end of the body or as its own appendix; anchors must be
real, currently existing paths — verify before committing, wildcards are not
acceptable.

## 3. Theorem-shaping

Derivations carry their load-bearing structure explicitly:

- `assumption` for hypotheses that production can violate (say what happens
  when it does — a `remark` or `caution`).
- `definition` for every object with a name used more than once.
- `proposition` / `theorem` for each claim the implementation relies on;
  a proof or proof sketch follows immediately. If the proof is one line of
  algebra, give the line; if it is classical, cite and sketch.
- Edge cases (reducible graphs, zero weights, empty observation sets,
  boundary parameters) get a `remark` where the reader would first worry.

Numbering is per-note and shared across the series by `volfit_preamble.sty`;
reference with `\cref`.

## 4. Boxes — semantics and restraint

The five aside boxes share one quiet shape (left accent bar, faint wash).
Colour alone carries the meaning:

| Box         | Colour | Use for |
|-------------|--------|---------|
| `heuristic` | blue   | intuition, the "why" behind a construction |
| `perfbox`   | green  | numerical / performance engineering |
| `caution`   | red    | pitfalls, hard constraints, reverted fixes |
| `example`   | grey   | worked examples and case files (breakable) |
| `invariant` | amber  | the production invariants the note protects |

Restraint rules: roughly **one box per page** at most; a box is a change of
voice, not a highlight for ordinary prose. One `\boxed{}` display equation per
note — its central object. Titles can be overridden for case files:
`\begin{example}[title={Case file: the phantom calendar}] … \end{example}`.

## 5. Case files

The best examples read like small production incidents, with this skeleton:
**setup** (what was on screen), **failure mode** (the symptom), **diagnosis**
(the mathematical cause), **fix** (what shipped, or was reverted and why),
**verdict** (the measured number after). Point to the code module and the test
that now locks the behaviour. Real incidents from the repo history beat
invented ones; when an incident was a *reverted* fix, say so — reverts are the
most instructive material in the series (see Note 05's global-convexity-repair
caution).

## 6. Figures

All generated figures go through the shared helper:

```python
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from style import setup, save, PALETTE, label_panel
setup()
```

- Generators are `Docs/notes/figures/gen_<topic>.py`: deterministic (fixed
  seeds, no network), importable, re-runnable with the repo `.venv`, and they
  run the **production code**, not a re-implementation.
- Prefer one full-width figure with annotations over two cramped half-width
  panels. Panels that must share a figure get `label_panel(ax, "A")` tags.
- Legends outside the data or `frameon=False`; callout arrows
  (`ax.annotate`) for the one thing the reader must see.
- **Captions state the lesson, not the axes.** "The far node receives only
  34 % of the lit move and its credible band widens accordingly" — not
  "posterior mean vs node index".
- Numbers that appear in prose are emitted as macros into
  `figures/<topic>_tables.tex` (`% Auto-generated — do not edit.`) and
  `\input` by the note; never retype a generated number.

## 7. Notation and prose

- All shared notation comes from `volfit_preamble.sty` — never redefine `\E`,
  `\T`, `\Black`, etc. per note. New note-local macros go right after
  `\title`.
- Voice: rigorous but readable at advanced-undergraduate level; first person
  plural; contractions avoided; entertaining is allowed, imprecise is not.
- Every note cross-links its neighbours ("Note 12" for transport, "Note 01"
  for handles…) — the series is a graph too.
- Generated quantities in prose always via macros (`\lqdsvimaxerr`), with a
  `\IfFileExists` fallback only when a note must compile before its
  generator has run.

## 8. Build and verification

```powershell
# figures (repo root)
.\.venv\Scripts\python.exe Docs\notes\figures\gen_<topic>.py
# note (from Docs\notes)
latexmk -pdf NN_topic.tex
```

A note lands only when: the generator runs clean from the repo `.venv`; the
PDF compiles with no errors; the Appendix C snippet has been executed against
the production module; and every traceability anchor names an existing file.
Commit note + generator + regenerated PDF together.
