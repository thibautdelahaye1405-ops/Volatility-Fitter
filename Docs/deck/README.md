# Vol-Fitter capabilities deck

`volfitter_deck.html` is a self-contained light-theme HTML slide deck (16:9,
1920x1080 canvas scaled to the window). Open it in any browser; navigate with
arrow keys / PageUp / PageDown / Home / End; print-to-PDF for a handout.

**Current state: full 36-slide deck** (also exported as `volfitter_deck.pdf`,
one page per slide) — opening (problem, architecture, **worked dark-smile
walkthrough**, **glossary**), models (LQD ×2, backtest evidence, SVI ×2,
MC-SIV ×2, Local Vol ×2), trading realism (de-Am, forwards, objective,
var-swaps, wings, calendar case file, event clock), dynamics (SSR, priors ×2,
Kalman filter ×2), the graph section (concept, hero, edges, LOO validation),
and product close (workstation tour, quality/runbook, performance, discipline,
roadmap, closing statement).

Perf claims on the performance slide are measured on this machine
(i7-12700H/16GB): the 30-node live Yahoo session recalibrates in **7.6 s warm /
96.6 s cold** (timed via `scratchpad` script, 2026-07-06); test count is dated
to commit `645bf1e`.

## Layout

- `deck_template.html` — the deck source. Slides reference assets via tokens:
  `{{IMG:name}}` (app screenshot), `{{FIG:name}}` (note figure),
  `{{EQ:name}}` (equation SVG), `{{CHART:name}}` (hand-authored chart).
- `build.py` — inlines all assets (PNGs as base64, SVGs verbatim with equation
  upscaling) and writes `volfitter_deck.html`. Run with any Python.
  NOTE: equation SVG ids are namespaced per equation at build time — dvisvgm
  reuses glyph ids (`g1-67`, ...) across files, and inlining many SVGs into one
  document otherwise makes `<use>` resolve to another equation's glyphs.
- `assets/shots/` — app screenshots (headless Edge, deviceScaleFactor 2).
- `assets/fig/` — the technical notes' figures (`Docs/notes/figures/fig_*.pdf`
  rasterized via MiKTeX `pdftoppm -png -r 180`).
- `assets/eq/` — equations rendered from the technical notes' LaTeX
  (MiKTeX `latex` + `dvisvgm --no-fonts`, painted `currentColor`).
- `assets/charts/` — hand-authored data-viz SVGs (palette validated for both
  the light surface and dark: LQD `#059669`, SVI `#D97706`, SIV `#8B5CF6`).

## Recapturing screenshots

Market-facing shots (Parametric views, quote table, Term, Local Vol, Forwards,
Universe, Quality) come from a **live Yahoo session**: launch with
`VOLFIT_PROVIDER=yahoo`, restrict each ticker to ~6 expiries near
30/60/90/180/365/540 days via `PUT /universe/{ticker}/expiries`, fetch,
add SPY events, calibrate. The graph and filter shots come from a staged
synthetic session (so the propagation story is visible and reproducible
offline) and their captions say so:

1. Serve the app single-origin on :8001 (leaves the dev :8000 untouched):
   `VOLFIT_DESKTOP_MODE=server VOLFIT_DESKTOP_PORT=8001 VOLFIT_PROVIDER=synthetic`
   plus a scratch `VOLFIT_DB`, then `python backend/desktop.py`
   (needs `npm --prefix frontend run build` once).
2. Stage: fetch spots + options -> Calibrate -> Save priors -> **Fetch priors**
   (activates them; otherwise extrapolation falls back to `today_bootstrap` and
   every innovation is zero) -> darken QQQ/AAPL/NVDA/IWM via
   `PUT /universe/lit/{ticker} {"lit": false}` -> reprice SPY by amending every
   quote mid +150 bp (`POST /smiles/SPY/{expiry}/edits`) -> Calibrate.
3. Solver knobs for a visible propagation: eta 3.16x (slider 0.5), lambda 0.1,
   cross-ticker edge weight 30 -> dark nodes inherit ~+37-40 bp of SPY's
   +150 bp with an ~140 bp credible band.
4. Drive headless Edge with puppeteer-core (installed in `frontend/`) and
   screenshot the Parametric smile, the Graph Extrapolate lattice, and a dark
   NVDA node's reconstructed smile (click its row in the Extrapolate panel).
5. Extras staged for the full deck: an SPY event calendar
   (`PUT /events/SPY {"events":[{"time":0.12,"weight":3},{"time":0.37,"weight":3}]}`)
   for the Term shot, and the observation filter
   (`PUT /settings/options` with `observationFilterMode: "active"` + two
   calibrations with a small quote nudge between them) for the FILTER-overlay
   smile, the filter panel, and the Quality dashboard shots.

The deck's palette/typography rules live in `deck_template.html`'s CSS tokens.
Numbers on the evidence slide come from
`backend/backtest/results/spike_aug2024_parametric_tv_density_mid_report.md`
and `FINDINGS_graph_loo.md`.
