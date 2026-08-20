# Alternative Chapter 2: The log-quantile-density model

This package contains a standalone alternative version of Chapter 2.

## Contents

- `book_ch02_alternative.tex`: standalone LaTeX master.
- `chapters/02_lqd_alternative/`: chapter text and appendices.
- `figures/ch02/`: inherited and newly generated figures.
- `scripts/generate_new_figures.py`: source for the two new synthetic figures.
- `references.bib`: bibliography used by the standalone master.

## Principal changes

- The exposition begins with the economic object--a mean-one terminal law--and
  introduces each coordinate only when it performs a specific job.
- The original exponential-tail LQD skeleton is derived before the generalized
  tail gauges, making the extension visible as one controlled modification.
- Main formulas are paired with their probability and trading interpretations;
  longer proofs and implementation detail remain in the appendices.
- A two-sided tail family with exponents `alpha_-` and `alpha_+` in `[0,1/2]` interpolates between exponential and Gaussian-rate log-return tails.
- The normalizer, moment domain, and implied-variance wings are derived for the full tail family.
- Calendar order is imposed on the whole real line through ledger inequalities and certified at every quantile-curve crossing, rather than checked only on quoted strikes.
- Calibration, stable evaluation, sensitivities, pseudocode, failure tests, and reference defaults are collected into an implementation contract.

## Build

Run LaTeX, BibTeX, then LaTeX twice on `book_ch02_alternative.tex`. The generated PDF is placed in `build/` by the packaged build used for this delivery.

The frozen empirical fits retain `alpha_- = alpha_+ = 0`. Any comparison of alternative tail exponents should refit each scenario under the same quotes and the same joint calendar constraints.
