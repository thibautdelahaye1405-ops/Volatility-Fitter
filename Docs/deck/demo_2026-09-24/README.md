# Demo deck 2026-09-24 — how the assets were made

> The deck and speaker notes were completely rewritten on 28 September 2026 as a
> 48-slide internal technical presentation. The current authoring source and build
> instructions are in [rewrite/README.md](rewrite/README.md). The staging record
> below documents the archived 24 September screenshots used in that presentation.

Deck: `../demo_deck_template.html` → `python ../build.py demo_deck_template.html demo_deck.html`
(tokens `{{SHOT:name}}` = `assets/shots_demo/name.png`, `{{EQD:name}}` = `assets/eq_demo/name.svg`;
`{{FIG:}}` / `{{EQ:}}` / `{{IMG:}}` as in the capabilities deck). Verify / export:
`node ../verify_deck.mjs <deck.html> <outdir>`, `node ../export_pdf.mjs <deck.html> <out.pdf>`.
Speaker notes: `../demo_speaker_notes_2026-09-24.md`. Press **N** in the deck for the presenter notes overlay.

## Staging a private desk (never the user's :8000)

```powershell
$env:VOLFIT_PORT="8011"; $env:VOLFIT_SERVE_FRONTEND="1"; $env:VOLFIT_PROVIDER="nasdaq"
$env:VOLFIT_TICKERS="SPY,NVDA,AAPL,QQQ"; $env:VOLFIT_DB="<scratch copy of backend\data\volfit.sqlite>"
$env:VOLFIT_CALIB_WORKERS="2"; Remove-Item Env:\VOLFIT_MASSIVE_KEY   # no second Massive socket
.\.venv\Scripts\python.exe backend\serve.py     # single-origin: built bundle + API on :8011
```
Needs `frontend\dist` (`npm run build`). Then, from the repo root with the venv python:
`stage1.py` (monthly ladders, first fetch, options, calibrate, priors — written for Cboe, which
served a 36 h-old file that day), `stage2.py` (switch to Nasdaq delayed, re-fetch, calibrate,
save priors, save universe `demo-core`), `stage3.py` (event auto-calibration on AAPL / MSFT / NVDA,
a var-swap quote on QQQ Dec-18, eight dark nodes, a clean recalibration). The last step of the day
was: re-save priors, re-fetch, recalibrate — so lit nodes carry a real intraday innovation and the
dark nodes take `nearest_expiry_transported` priors; then reset the graph relations to auto through
`GET /graph/edges/messages/auto` → `PUT /graph/edges/messages` → `POST /graph/config/messages/activate`.

## Screenshots

`frontend\scripts\demo_shots_parametric.mjs` and `demo_shots_graph.mjs` (puppeteer-core, headless
Edge, light theme via `volfit.viewSettings`, 1600×1000 @2x) write into `assets/shots_demo/`; the
`README_*.md` files there list what each shot shows. `crops.py` cuts the dialog / card crops the deck
uses (display coordinates of the 2000×1250 view of a 3200×2000 shot). `render_eqs.py` renders the
31 equations with `latex` + `dvisvgm -n` (MiKTeX) into `assets/eq_demo/`.

## Findings that day
- The combined Calibrate's LV stage failed once per run on one ticker (SPY, then MSFT) with
  `unsupported operand type(s) for -: 'float' and 'NoneType'`; the direct `POST /fit/affine/{T}`
  succeeded afterwards — intermittent, in the parallel calibration path.
- Cboe's delayed file was 36 h stale (publication stamp 2026-09-23T03:54:59); Nasdaq delayed was ≈ 15 min.
- The Term view's forward-variance ladder includes a dark node's stale fit (a spike near τ ≈ 0.4 on
  AAPL); pick an all-lit ladder for the events beat, or accept and explain it.
- No straddle / collar dial exists; RR / BF / ATM are prior operators read off the fit.
