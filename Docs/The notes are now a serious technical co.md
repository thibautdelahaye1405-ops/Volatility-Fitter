The notes are now a serious technical corpus. I would like to refine them further though. The improvement should be an editorial and mathematical hardening pass, using [01_lqd_model.tex](C:/Users/thiba/Vol-Fitter/Docs/notes/01_lqd_model.tex) as the gold-standard template and [05_deamericanization.tex](C:/Users/thiba/Vol-Fitter/Docs/notes/05_deamericanization.tex) as the best narrative model.

**Diagnosis**

The set is strong but uneven. Some notes read like polished chapters; others read like compressed implementation memos with good equations. The biggest opportunity is to turn the notes into a coherent “Vol-Fitter book”: each note should explain the problem, the invariant being protected, the mathematical mechanism, the implementation trick, and one concrete failure case where the method matters.

The visual layer is the weakest relative to the math. The generated figures are correct, but many are still “scientific default Matplotlib”: small labels, cramped two-panel layouts, legends inside plots, few annotations, and captions that do not always carry the story. [14_graph_extrapolation.tex](C:/Users/thiba/Vol-Fitter/Docs/notes/14_graph_extrapolation.tex) in particular deserves much stronger full-width visuals because it is one of the project’s signature ideas.

**What I Propose**

1. Create a house style pass.

Add a short `Docs/notes/STYLE_GUIDE.md` and refine [volfit_preamble.sty](C:/Users/thiba/Vol-Fitter/Docs/notes/volfit_preamble.sty). Each note should open with the same compact structure:

- Problem: what can go wrong in production?
- Invariant: what must remain true?
- Mechanism: what mathematical object enforces it?
- Implementation: where this lives in code.
- Example: one small reproducible case.

The boxes are useful, but visually heavy. I would soften the `heuristic`, `caution`, `example`, and `perfbox` colors, make them less dominant, and reserve big colored boxes for genuinely important ideas.

2. Make the derivations more theorem-shaped.

Several derivations are right but under-justified. I would add explicit assumptions, propositions, proof sketches, and edge-case remarks where the current text jumps too quickly.

Priority upgrades:

- `02_svi_jw`: stronger JW admissibility conditions, conversion domains, and no-arbitrage implications.
- `04_local_volatility`: rigorous discrete Dupire/M-matrix discussion, adjoint sensitivity derivation, and solver stability notes.
- `08_variance_swaps`: cleaner normalized log-contract derivation from strike space to log-moneyness space.
- `10_calendar_arbitrage`: clearer convex-order assumptions, especially fixed-forward normalization and deterministic carry.
- `12_spot_vol_dynamics`: careful sign conventions for SSR/Hagan transport and local-vol grid relabeling.
- `13_bayesian_prior_persistence`: formal precision/gating definitions and diagnostic tables.
- `14_graph_extrapolation`: prove the graph prior precision construction, explain positive definiteness, beta trust semantics, and conditioning geometry.

3. Upgrade the pictures into explanatory figures.

I would create a shared plotting helper in `Docs/notes/figures/style.py` so every generated figure has consistent typography, palette, sizing, labels, legends, and export settings. Then revise the key figures to be more narrative:

- Full-width graph propagation figure for Note 14.
- Before/after de-Americanization wing repair figure for Note 05.
- Local-vol grid and short-dated rescue diagram for Note 04.
- Phantom-calendar before/after figure for Note 09/10.
- Prior activation diagnostic figure for Note 13.
- Event-clock timeline showing calendar time, working time, event jumps, and price preservation for Note 11.

The figures should use fewer tiny subplots, larger labels, callouts, and captions that state the lesson, not just describe the axes.

4. Replace toy examples with “case files”.

The best examples should feel like small production incidents:

- “The Wednesday short-dated smile that made Dupire explode.”
- “The American put wing that looked convex until the de-Americanization map touched it.”
- “The graph prior that helped one sparse tenor but hurt another until beta was damped.”
- “The SIV fit that improved RMS while inventing a fake weekend wing.”
- “The forward regression that looked harmless but shifted every delta bucket.”

Each case file should have setup, failure mode, mathematical diagnosis, fix, and numeric verdict. Where possible, each should point to the code module and test that protects the claim.

5. Add traceability.

This is the serious long-term improvement. Add a small appendix/table per note:

| Claim | Equation/Figure | Code | Test |
|---|---|---|---|
| LQD slice is butterfly-free | Prop. X | `backend/volfit/models/lqd/...` | `tests/test_lqd_...` |
| Graph prior propagates increments | Eq. X | `backend/volfit/graph/...` | `tests/test_graph_...` |

That would make the notes much harder to rot as the code evolves.

**Priority Order**

I would start with:

1. Note 14, graph extrapolation: highest conceptual leverage, biggest visual gap.
2. Note 04, local volatility: most compressed and mathematically dense.
3. Note 13, Bayesian prior persistence: important production workflow, could become much clearer.
4. Notes 09 and 10 together: wings, Lee bounds, and calendar confinement form one conceptual arc.
5. Notes 02 and 03: improve SVI/SIV rigor and cautionary examples.
6. Notes 06, 07, 08, 11, 12: polish, examples, and cross-links.
7. Note 00 last: rewrite the overview after the individual notes settle.
8. Note 01 lightly: preserve it as the house template.

**Concrete First Deliverable**

My proposed first move is a pilot improvement on `14_graph_extrapolation`: rewrite the narrative spine, add the missing derivation rigor, create one worked 6-node example, regenerate the graph figures with a shared plotting style, and compile/render the PDF for visual QA. Once that lands, the same pattern can be applied across the whole note series cleanly.