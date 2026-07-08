# Vol-Fitter capabilities deck

`volfitter_deck.html` is a self-contained light-theme HTML slide deck (16:9,
1920x1080 canvas scaled to the window). Open it in any browser; navigate with
arrow keys / PageUp / PageDown / Home / End; print-to-PDF for a handout.

**Current state: full 36-slide deck, rev 5** (also exported as
`volfitter_deck.pdf`, one page per slide) — opening (problem, architecture,
worked dark-smile walkthrough, glossary), models (LQD ×2, backtest evidence,
SVI ×2, MCS ×2, Local Vol ×2), trading realism (de-Am, forwards, objective,
var-swaps, wings, calendar case file, event clock), dynamics (SSR, priors ×2,
Kalman filter ×2), the graph section (concept, hero, edges, LOO validation),
and product close (workstation tour, quality/runbook, performance, discipline,
roadmap, closing statement).

Rev-5 changes (2026-07-08 pm): **graph demo restaged with stronger propagation**
(eta 10 = slider max, cross-ticker weight 100 — dark gain ~0.5 instead of ~0.25;
eta 10 sits on the flat part of the LOO autotune curve, so it is data-consistent,
not hand-favored): lattice now SPY +77…+140 bp lit / +43…+79 bp dark inside a
±195-200 bp 95% band, hero NVDA +57 bp (ζ = −0.56 vs the deliberately-unmoved
synthetic quotes — caption reframed honestly). Slide-4 steps rewritten to define
innovation precisely (change vs transported prior, never levels) and to state
units/band convention; slide-4 shots no longer vertically cropped (lattice
pre-cropped to content + contain on matched bg #EEF2F7, hero pre-cropped wide as
`smile_hero_wide.png`); glossary ζ entry lists where ζ is used; slide-6 A_R
expression added (A_R = exp(R + Σ(−1)^n a_n)); parametric_smile retaken intraday
(cleaner quotes) with the quote-editor button cluster removed at capture; the
same button cluster is PIL-blanked in smile_hero. stage_graph.py is now truly
idempotent (SPY edit sessions reset BEFORE calibration #0 — previously a rerun
saved priors contaminated by the prior run's +150 bp and innovations collapsed).

Rev-4 changes (2026-07-08): **app screenshots retaken in the app's LIGHT theme
from a live Massive session** (was dark theme / Yahoo); tone pass (quant-to-quant,
less sales); titles made fully explicit with technical-note references moved to
slide footers; every equation carries a notation line defining its symbols;
**"Multi-Core SIV" renamed "Multi-Core Sigmoid (MCS)"** deck-wide and in the app
UI labels; new fit-to-mid vs fit-to-band figure (`gen_band_deck_fig.py`, uses the
production calibrator; seed-searched for a visibly noisy mid fit) plus a concrete
haircut explanation; slide-13 piecewise-affine/wings/Lee explanation; MAP spelled
out on the filter-evidence slide.

Perf claims on the performance slide are measured on this machine
(i7-12700H/16GB): the 30-node live Yahoo session recalibrates in **7.6 s warm /
96.6 s cold** (timed 2026-07-06); test count is dated in the deck.

## Layout

- `deck_template.html` — the deck source. Slides reference assets via tokens:
  `{{IMG:name}}` (app screenshot), `{{FIG:name}}` (note figure),
  `{{EQ:name}}` (equation SVG), `{{CHART:name}}` (hand-authored chart).
- `build.py` — inlines all assets (PNGs as base64, SVGs verbatim with equation
  upscaling) and writes `volfitter_deck.html`. Run with any Python.
  NOTE: equation SVG ids are namespaced per equation at build time — dvisvgm
  reuses glyph ids (`g1-67`, ...) across files, and inlining many SVGs into one
  document otherwise makes `<use>` resolve to another equation's glyphs.
- `assets/shots/` — app screenshots (headless Edge, deviceScaleFactor 2,
  light theme via localStorage `volfit.viewSettings`).
- `assets/fig/` — the technical notes' figures (`Docs/notes/figures/fig_*.pdf`
  rasterized via MiKTeX `pdftoppm -png -r 180`) + deck-only figures
  (`gen_band_deck_fig.py` regenerates `fig_obj_band_deck.png`).
- `assets/eq/` — equations rendered from the technical notes' LaTeX
  (MiKTeX `latex` + `dvisvgm --no-fonts`, painted `currentColor`).
- `assets/charts/` — hand-authored data-viz SVGs (palette validated for both
  the light surface and dark: LQD `#059669`, SVI `#D97706`, MCS `#8B5CF6`).

## Recapturing screenshots (scripts now persisted here)

Market-facing shots (Parametric views, quote table, Term, Local Vol, Forwards,
Universe, Quality) come from a **live Massive session**; the graph and filter
shots come from a **staged synthetic session** (so the propagation story is
visible and reproducible offline) and their captions say so.

1. Build the frontend once: `npm --prefix frontend run build`.
2. Serve single-origin on :8001 (leaves dev :8000 untouched); dot-source
   `restart.local.ps1` first for the Massive key:
   `VOLFIT_DESKTOP_MODE=server VOLFIT_DESKTOP_PORT=8001 VOLFIT_PROVIDER=massive`
   (or `synthetic` for the graph session) plus a scratch `VOLFIT_DB`, then
   `python backend/desktop.py`.
3. Market session: `python Docs/deck/stage_market.py` (universe SPY/QQQ/AAPL/
   NVDA/IWM, ~6 expiries/ticker near 30/60/90/180/365/540 d, SPY events,
   calibrate) then from `frontend/`: `node ../Docs/deck/capture_market.mjs`.
4. Graph/filter session (synthetic provider, fresh scratch DB):
   `python Docs/deck/stage_graph.py` — it calibrates, saves **and fetches**
   priors (without the fetch, extrapolation falls back to `today_bootstrap`
   and every innovation is zero), darkens QQQ/AAPL/NVDA/IWM, reprices SPY
   +150 bp via quote-edit amends, stages the observation filter, and runs the
   extrapolation with visible-propagation knobs (eta 10, lambda 0.1,
   cross-ticker weight 100 → dark nodes inherit +43…+79 bp inside a
   ±195-200 bp 95% band). Then `node ../Docs/deck/capture_graph.mjs`.
5. The captions on the graph/filter/hero slides cite the staged session's
   numbers (innovation bp, band width, reconstruction RMS / in-band % / ζ,
   filter gains) — `stage_graph.py` prints them; update the captions if the
   staging changes. `capture_extras.mjs` retakes the edge-editor shot (it
   PUTs a desk-authored block rule first — weights 30, β 0.9–1.3, calendar
   100 — so the matrix isn't the empty auto-lattice state) and the
   options_calibration_crop (bounded clip; crop afterwards with PIL if tall).

NOTE: the `.mjs` scripts import `puppeteer-core`, which Node resolves
relative to the SCRIPT's location — copy them into `frontend\` before running
(`Copy-Item Docs\deck\capture_market.mjs frontend\; cd frontend; node .\capture_market.mjs`).
CAVEAT: the capture scripts also resolve their OUTPUT dir relative to the
script location, so when run from `frontend\` the PNGs land in
`frontend\assets\shots\` — copy them back to `Docs\deck\assets\shots\`, but do
NOT clobber `edge_editor.png` / `options_calibration_crop.png` (those come from
`capture_extras.mjs` + a PIL crop; a plain capture_graph run overwrites them
with the un-staged / un-cropped variants).

## Verifying + exporting

- `verify_deck.mjs` (copy to frontend\, then `node .\verify_deck.mjs`) —
  screenshots every slide of the BUILT deck to a scratch folder and flags
  content past the slide bottom or clipped inside `.cols` (the columns clip
  overflow, so text never overlaps the trading-relevance strip — but clipped
  content must be trimmed instead). Slide 1 always reports a by-design IMG
  overflow (the title shot is intentionally cropped by its container).
- `export_pdf.mjs` (same copy-to-frontend dance) — one 1920x1080 PDF page per
  slide via the print CSS → `volfitter_deck.pdf`.

The deck's palette/typography rules live in `deck_template.html`'s CSS tokens.
Numbers on the evidence slide come from
`backend/backtest/results/spike_aug2024_parametric_tv_density_mid_report.md`
and `FINDINGS_graph_loo.md`.
