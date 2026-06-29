# Legacy notes → Technical Notes series

The six standalone `.tex` notes that previously lived in `Docs/` are **superseded
for reading** by the `Docs/notes/` Technical Notes series (the "rewrite
comprehensive" decision: each new note fuses the original theory with the
implementation, the hyperparameter atlas, the performance work, and figures
generated fresh from the production code).

The legacy files are **retained in place, not moved or deleted**, for one concrete
reason: ~39 files across the backend, tests, frontend and other docs reference
them *by path* and cite their *equation labels* (e.g. `eq. q_logit`,
`note section 5.2`). Those citations anchor the code's docstrings to a specific
numbered derivation. Moving or removing the legacy files would orphan all of them.
Each legacy file now carries a `% === SUPERSEDED` banner pointing to its
replacement.

| Legacy `Docs/*.tex` (citation source) | Superseded by `Docs/notes/` (read this) |
|---|---|
| `lqd_model_note.tex` | `01_lqd_model.tex` |
| `Multi_Core_SIV_Technical_Note.tex` | `03_multicore_siv.tex` |
| `piecewise_affine_local_variance_calibration.tex` | `04_local_volatility.tex` |
| `iv_time_value_density_weights.tex` | `07_calibration_objective.tex` (absorbed) |
| `spot_move_vol_surface_note_updated.tex` | `12_spot_vol_dynamics.tex` |
| `ot_bayesian_graph_extrapolation_expanded.tex` | `14_graph_extrapolation.tex` |

## Guidance

- **Reading / sharing:** use the `Docs/notes/NN_*.tex` (and their compiled PDFs).
- **Code citations:** when a docstring says `Docs/lqd_model_note.tex, eq. (X)`, that
  still resolves to the legacy file's labels. If a docstring is ever rewritten to
  cite a `notes/` label instead, the corresponding legacy reference can be dropped.
- The other `Docs/*.md` notes (methodology, perf, roadmaps, design records) are
  **not** superseded — they are working/process documents, distinct from the
  formal series.
