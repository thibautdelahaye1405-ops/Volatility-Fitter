# Final status — LQD paper, round 3 close (2026-08-04)

**Deliverable**: `Papers/lqd_paper/lqd_paper.pdf` — 52 pages, "The
Log-Quantile-Density Model of the Volatility Smile: Validity, Information,
and Convention", Thibaut Delahaye. Builds with pdflatex ×2 + bibtex, zero
undefined references/citations, exactly one boxed display, 14 figures
(floor was 12), 220 generated macros with 118 used and full parity (no
hand-typed data numbers).

## Process (writer / challenger / arbiter, per the commissioning brief)

- Grounding: three explorer reports (Note 01 four editions map; LQD
  implementation map; headless data path) → briefs in this folder.
- Data: fresh SPY+NVDA Massive snapshot frozen 2026-08-04 02:08 UTC
  (`../data/`), 16/16 nodes, haircut LQD-16; wing-projection publish
  blocker forensically traced to the numerically-empty extrapolated wing
  (k=+0.98 between the 2d/4d SPY expiries) — used in §11 as a live
  illustration, documented in `../data/README.md`.
- Figures: one deterministic pipeline (`../scripts/gen_figures.py` +
  figlib), ~10 s cold, startup gate proves frozen-curve rebuild to
  0.0000 bp; all numbers emitted as macros incl. the reproduced
  phantom-drag experiment (10.6→1095 bp), the 27-slice certification
  battery, interleaved timing (analytic 1.38–1.74× FD), the multi-start
  audit (1 basin), and the NVDA over-parameterization probe (no cliff on
  this book — reported as book-dependent).
- Round 1: student (Black–Scholes-only persona) filed 23 objections
  (0 BLOCKING / 6 HARD / 17 SOFT); the lead's independent review filed 7
  more (ARBITER_ROUND1). Highlight: the student caught a genuine sign
  error (Δ-mismatch direction), confirmed by the lead's own derivation
  and by the measured macro (SPY Dec u* = 41.31%).
- Round 2: all 23 + 7 accepted and applied; figure notation unified to
  the paper's ledger; engineer measurements arbitrated into the text
  (SPY band degeneracy, two-sided Lee wings, N=6 distortion-not-erasure,
  real 800-strike ticket, book-dependent latency cliff).
- Round 3: student verified 23/23 resolved by re-derivation and signed
  off conditional on one HARD (universality closure branch) + 4
  copyedits; the author proved the missing g_infty(1)=0 branch as a
  dichotomy (escape via the solvable slice's normalizer divergence;
  conditional boundary sub-case pinned by tightness), lead verified the
  proof line by line. Statement and proof now match exactly.

## Student's closing verdict (round 2 report, conditions since met)

"Yes — I would now sign off on this paper as understandable and rigorous
for a reader like me."

## Residual items (deliberate, disclosed)

- Benaim–Friz cited without a theorem number (verified against MF 19(1)
  1–12, 2009: the tail-wing formula's regular-variation hypothesis is
  satisfied by inspection for LQD's exact power tails); add the number
  only if a journal demands it.
- Bibliography items marked "verify before print" in AUTHOR_NOTES
  (Carr–Madan chapter pages, Gatheral 2004 talk vs 2006 book, SciPy
  author list) — pre-submission polish, not content.
- The boundary sub-case of the closure dichotomy deliberately leaves
  unclaimed whether tight wall sequences are attained.

## Regeneration

- Figures + macros: `.venv\Scripts\python.exe Papers\lqd_paper\scripts\gen_figures.py`
- Paper: `pdflatex lqd_paper` ×2 (+ bibtex) in `Papers/lqd_paper/`
- Data snapshot: frozen; a refetch produces a NEW book (see data/README.md)
