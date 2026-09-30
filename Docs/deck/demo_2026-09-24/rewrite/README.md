# Internal technical presentation

This is the authoring source for the 28 September 2026 rewrite of the demo deck.
The audience is internal quants and traders. The 48 slides explain the motivation,
mathematics, computational method and interpretation of each feature.

## Deliverables

- [Self-contained HTML deck](../../demo_deck.html)
- [PDF, one page per slide](../../demo_deck.pdf)
- [Matching speaker notes](../../demo_speaker_notes_2026-09-24.md)

The existing speaker-notes filename is retained so links continue to work.
Arrow keys, Page Up / Page Down, Home / End, the dots and the URL hash navigate.
**N** opens the speaker notes, **O** the contents (grouped by section); Escape closes
either overlay. The HTML uses embedded images and equations, system fonts and plain
JavaScript; it has no external runtime dependencies.

## Presentation layer (restyled 29 September 2026)

The slides use the capabilities deck's design system (`../../deck_template.html`):
the same colour tokens, kicker (section + "k / n" position), claim title, lede,
formula block on the left and evidence on the right, the "illustrative calculation"
as an accent strip (amber when the label says recorded / measured / limitation),
captions with a bold lead, the footer with the reference and the slide count.

- **Equations** are rendered offline by MiKTeX (`latex` + `dvisvgm -n`) into
  `assets/eq_demo/gen/<sha1>.svg`, glyphs as paths, coloured by CSS, inlined by
  `build.py`'s SVG inliner (ids namespaced per formula). The cache is content-keyed,
  so only new or changed formulas are rendered. If LaTeX rejects a formula the build
  prints a warning and falls back to matplotlib mathtext for that one display.
- **Layout rules** (`build_demo.py`): a slide with an image or plot is two columns
  (formulas + bullets + table + example | figure + caption; `layout: "wide-image"`
  widens the figure, `layout: "narrow-image"` narrows it for a portrait capture
  beside a wide table, `layout: "half-image"` gives formulas and figure equal width); a slide with a table and formulas or bullets is two equal columns
  (formulas + bullets | table + example); formulas without a table sit left with the
  bullets right; a table alone spans the slide. `layout: "cover"` is the title slide,
  `layout: "close"` the closing slide (brand, title, lede, bullets); `layout: "compact"`
  shrinks a table. Optional keys `eq_title` and `eq_note` label a formula block, and
  `eq_labels` (aligned with `eq`) puts a step label above each display; `demo`
  renders an "In the app" cue on the slide and in the notes.
- **Inline maths in prose**: every slide-visible text field (lede, bullet labels and
  text, example, table cells, captions, demo cues) may carry `$…$` spans (write `\$` for a literal dollar sign). They go
  through the same LaTeX pipeline in text style, are scaled to the surrounding font and
  sat on its baseline. The convention since 29 September is LaTeX only — no Unicode
  superscripts, subscripts or Greek for mathematical symbols in those fields. Titles
  stay plain text.
- **Screenshots**: a 1600×1000 capture has its status bar hidden; a portrait or
  square crop is framed at its own width in a 640 px panel.
- **Auto-fit**: at load, any slide whose body overflows is zoomed down uniformly in
  steps (0.95 … 0.75) — the whole body, not individual font sizes — so typography
  stays consistent across the deck. `verify_deck.mjs` reports what still overflows.

## Editing and rebuilding

The five numbered JSON files define the slides in order. Each slide has a stable
ID, title, explanation, equations or table where useful, a visual where useful,
speaker notes and source paths. Edit these files rather than the generated HTML
or Markdown. All source paths are checked during the build.

From the repository root, using the venv Python (Matplotlib, Pillow; MiKTeX on PATH):

```powershell
.\.venv\Scripts\python.exe Docs\deck\demo_2026-09-24\rewrite\plots.py
.\.venv\Scripts\python.exe Docs\deck\demo_2026-09-24\rewrite\build_demo.py
```

The first command creates the explanatory plots in `assets/plots_demo/` (deck
palette, Segoe UI). The second renders the mathematical SVGs, generates
`demo_deck_template.html` and the speaker notes, then calls the existing deck builder
to embed the archived app screenshots and reference-note figures into `demo_deck.html`.

Render every slide, check layout and navigation, and refresh the PDF:

```powershell
node Docs\deck\verify_deck.mjs Docs\deck\demo_deck.html <outdir>          # per-slide PNGs + overflow report (Edge)
node Docs\deck\demo_2026-09-24\rewrite\verify_demo.mjs Docs\deck\demo_deck.html <outdir> --pdf   # + navigation checks, previews, PDF (Chrome)
```

Both verifiers produce slide PNGs that need visual inspection as well as the
automated checks. The browser executable paths are specific to this workstation.

## Sources and example conventions

Each slide and notes section identifies its references. The handoff notes provide
the basic mathematics; September roadmaps and current implementation resolve
later changes to calendar certification, local-volatility stepping, filtering and
graph reconstruction. Stored HTML notes contain the same explanatory prose as the
Markdown notes; equations and tables are visible on the slide and repeated in the
Markdown version.

Application captures are archived from 24 September. Their values and stale-state
labels belong to that saved session. Mechanism plots are explicitly illustrative;
the performance chart retains the date, workload and hardware of the recorded
23 September experiment. A same-session dark-node demonstration and a
chronological held-out validation have different information sets, as explained
in the graph notes.

Keep annualisation conventions explicit: calendar time is `t`, the application's
working variance clock is `τ`, and total variance is the clock-independent object
when changing volatility units. Volatility is a decimal; one vol point is `0.01`
and one vol basis point is `0.0001`.
