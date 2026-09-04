// What's new (HELP CENTER ARC, H2): release notes in USER language, newest
// first, derived from the ROADMAP session wraps of 2026-08-20 … 2026-08-31.
// Bullets name UI surfaces and behaviour, never code identifiers (except
// where the identifier IS the UI name). Rendered by WhatsNewPage.tsx.
import type { WhatsNewEntry } from "./types";

export const WHATS_NEW: WhatsNewEntry[] = [
  {
    date: "2026-09-04",
    title: "Compare: eSSVI is a reference row, not a fourth model",
    items: [
      "The Compare strip shows the three families you can calibrate — LQD, SVI-JW, MCS. eSSVI, the compare-only SSVI yardstick (three handles, the belly tied to the wings), is no longer a default chip: **+ reference** at the end of the strip reveals it, tagged *ref*; **− reference** hides it and drops it from the comparison.",
      "When it is on, its curve is dashed and its table row sits last under a divider with a *reference* pill, so it never reads as a model you could select in Options. A tab that had eSSVI selected keeps it.",
    ],
  },
  {
    date: "2026-09-04",
    title: "Right-hand column: three cards that always fit, one expanded at a time",
    items: [
      "The Spot move, Variance swap and Fit diagnostics cards of the Parametric and Local Vol lenses now share the column without scrolling it. Each card has three sizes — **compact** (one row: the title and a live readout), **standard** (the working controls, the default) and **expanded** (everything the card knows).",
      "One card gets the room: the ⇕ toggle in a card's header — or a click on a compact row — expands that card and compresses the other two to their one-line readouts; the toggle on the expanded card folds all three back to standard. The choice is shared by both lenses and kept across reloads.",
      "Standard keeps what a session uses: Follow, the calibrated / market / scenario spots, the dial and Recalibrate; the var-swap readout, editor and undo row; the headline handles and RMS. Expanded adds the regime row, the dial scale, Reset / Sync and the snapshot rule; the penalty weight, replication split and hard pin; the wings, Lee slopes and var-swap vol — and, on Local Vol, the per-expiry table runs free instead of scrolling inside a capped height.",
    ],
  },
  {
    date: "2026-09-02",
    title: "Per-ticker data sources",
    items: [
      "The active data source is now a **default**, not a rule: each ticker row in Manage universe has a source select. Pin a ticker to another source — a Eurex index on Bloomberg beside names on Cboe — and it fetches, streams and captures from there while the rest of the universe follows the default. *Default (…)* unpins; a changed pin refetches the ticker and marks its nodes stale.",
      "To add a name only another source lists, choose that source in the search box's **in:** selector: the search reads that catalogue and *Add on Bloomberg* pins the new ticker to it. Pins travel with the workspace and with saved universes, and survive a switch of the universe source.",
      "The Nodes pane shows a small source pill (BBG, MSV, …) on a pinned ticker, the market pill a *+N* count with the pins in its tooltip, the Data-sources card the tickers each source serves, and the Spot card names the ticker's own source. A pinned streaming name streams beside request-path names.",
    ],
  },
  {
    date: "2026-09-02",
    title: "One Auto-update setting: spot only or spot + quotes, and a stream that just flows",
    items: [
      "A calibration always prices spot and option quotes from the same snapshot — a Fetch, or a synchronous read of the streaming book. Calibration is on-demand (the default) or continuous with **Auto-calibrate**, which refits whenever a quotes + spot snapshot arrives and on your edits.",
      "With a live stream (**Stream live book** on a Massive or Bloomberg source) spot and quotes flow continuously: the surface transports live and, in continuous mode, refits every *Stream refit every (s)*. Auto-update is not used while a book streams (the dialog dims it). **Freeze fit while streaming** holds the fit at its calibration spot instead — the live quotes still show against it.",
      "Without a stream, option quotes have to be fetched. A manual Fetch ▸ Snapshot gets both. The new **Auto-update** control (Options ▸ Workflow & data) replaces the separate Spot prices and Options quotes selectors: *Off*, *Spot only* every x s, or *Spot + quotes* every x s (15 s minimum — every tick downloads a full chain).",
      "A spot update — from the stream, a timer or a Fetch — only transports the surface, never recalibrates, even in continuous mode; only fresh quotes trigger a refit. The status bar's scheduler chip reads *Next update* with the countdown, or *Stream · live / refit / frozen* while a book streams; the Spot card's Follow selector is never forced any more.",
      "Saved settings migrate on load: an automatic chain timer becomes *Spot + quotes* at its old minutes cadence, a real-time spot poll becomes *Spot only*, everything else *Off*.",
    ],
  },
  {
    date: "2026-09-02",
    title: "Market data, second pass: Bloomberg index chains, real past bid/ask from Massive, captures that belong to their source",
    items: [
      "Bloomberg chains are complete again, verified on a live Terminal. The ladder is OPT_CHAIN (the monthlies and LEAPS, both sides) plus one CHAIN_TICKERS request per series (weeklies and dailies, quarterlies) with the expiry override set to ALL — without it that field answers a single expiry (the \"SPY has one expiry\" symptom) and calls only, without the yellow key (\"SX5E 09/18/26 C4650\": the quote request refused every row, and a call-only chain has no put-call parity to imply a forward — the \"no usable option expiries\" symptom). Each call now gets its put mirrored and the underlying's asset class appended (\"… C4650 Index\").",
      "Massive's past days are real two-sided bid/ask: a day's close or an instant is rebuilt from each contract's last NBBO at that moment — concurrent per-contract history requests, nearest-the-money first, up to 1,500 contracts per chain, counted in the status bar (*312 / 1500 contracts*). The aggregate closes (bid = ask marks) remain the fallback when the key has no historical-quote entitlement or hits its rate limit, and the picker's **marks** tag says so. VOLFIT_MASSIVE_HIST_NBBO=0 pins the marks path.",
      "Captured snapshots belong to the source that made them. A past day under Cboe lists only Cboe's own captures, as explicit *Latest capture · HH:MM* and *Captured · HH:MM* replay rows; *n min before close* is enabled only for a source that can fetch an arbitrary past instant (it used to serve the nearest capture silently). Captures made before this build carry no source and no longer appear in the picker; a saved selection still replays.",
    ],
  },
  {
    date: "2026-09-02",
    title: "Market data fetching: a real gauge, an honest as-of picker, sources that never lock",
    items: [
      "The status bar shows fetch progress: which chain is downloading (*chain 2 of 4*) with its bytes against the venue's file size, the elapsed time of the step, and elapsed versus the 10-minute client timeout when nothing can be measured. Every venue download is capped at 120 s.",
      "The **As of** picker lists every day and moment but only enables what the active source can serve — today is Live, holidays are gone, Massive offers past instants only with its flat-file store — and tags Massive's history **marks**: its past-day chains are one close per contract (bid = ask), so the Smile chart draws hollow diamonds and says *Close marks · no bid/ask* instead of a zero-width band. Bloomberg history carries real bid/ask.",
      "Tickers carry across sources (\"SPX\" is \"SPX Index\" on Bloomberg, \"^SPX\" on Yahoo, \"I:SPX\" on Massive, \"_SPX\" on Cboe). A name a venue does not list shows a yellow **no data** pill with the reason on its Nodes-pane row, and no longer turns the whole source red — the Cboe \"failure\" was a Eurex index sitting in the universe.",
      "Switching data source never waits on a status probe, a hung probe no longer freezes the lights, a red source can still be switched to, and a failed switch is reported in the status bar.",
      "Bloomberg's daily and weekly expiries list (the mechanism that finally works on a live Terminal is in the second-pass entry above; the old OPT_CHAIN request ignored every override and returned the monthly-biased default). Today's expiry is listed until its session closes; an index file's weeklies settle PM and its 3rd-Friday monthlies AM. The expiry picker gains a **Dailies** chip.",
      "Degraded-but-usable source status is drawn **yellow** (it was amber, too close to red).",
    ],
  },
  {
    date: "2026-09-02",
    title: "Spot move card: market spot or scenario, fine-tune, Recalibrate per ticker",
    items: [
      "The card now shows three spots — **Calibrated** (the anchor), **Market** (streamed off the Bloomberg / Massive book at ~1 Hz when a stream is up, else the last probe or the fetched chain's spot, with a ↻ probe button) and **Scenario** (anchor × the dial) — and a **Market spot / Scenario** selector: the followed level is lit, the other dimmed; following the market keeps every lens at the prevailing spot.",
      "The dial moves in 0.1 % steps with ± fine-tune buttons (Shift: 1 %), **Reset to 0.0%** and **Sync to market**.",
      "A scenario now also moves the Smile chart while the live tick stream is on — previously the streamed market frame ignored the dial and only the strike brush shifted.",
      "**Recalibrate _ticker_ (_scope_)** replaces Re-anchor: it is the top-bar Calibrate for that ticker alone — same scope (Param + LV / Param only / LV only) and the same snapshot rule — and every Calibrate now fits a synchronous quotes + spot snapshot off the streaming book when one is up, else the last fetched chain. The previous fit stays on screen (stale) until the new one lands — it used to blank the chart on the gated server.",
    ],
  },
  {
    date: "2026-08-31",
    title: "Help Center",
    items: [
      "Help ▾ is now a full Help Center: Welcome, Guides per lens, Command reference, Settings reference, Keyboard shortcuts, Glossary, Tips & tricks, Documentation, Ask @Vol-Fitter and What's new — one dialog, searchable, with back / forward.",
      "A 12-step spotlight **Walkthrough** over the live shell (Next / Back / Skip, resumable); the Welcome page opens once on a first run.",
      "**F1** opens the guide of the active lens or dialog. **Ctrl+Shift+/** asks @Vol-Fitter — answered from the help corpus at once, and by Claude when the server has an Anthropic key.",
      "Every command and every Fit / Options / Market field is documented with an example; settings show type, default, range, unit, when they are read and what they invalidate, with an *Open in Options* button.",
      "Documentation in-app: the technical notes in Markdown, PDFs of the notes, the book and the LQD paper, the handoff pack.",
      "About VolFit gains build info and a **Copy diagnostics** button for support requests.",
    ],
  },
  {
    date: "2026-08-31",
    title: "Short-dated smiles draw clean wings",
    items: [
      "2–4 day smiles no longer show a ragged far upside or a flat far downside: the price-to-vol conversion of the display now inverts the out-of-the-money side with a tail-accurate map.",
      "The Local-Vol smile and surface views apply the same fix — deep-left wings no longer show gaps or phantom vols.",
      "Calibrations are unchanged; only what is drawn changed.",
    ],
  },
  {
    date: "2026-08-28",
    title: "Three editor groups, and the app rolls over at midnight",
    items: [
      "Ctrl+\\ now cycles one, two, three editor groups and folds back; Ctrl+Shift+\\ splits down. Each group can run its own lens; the tab menu offers *Move to group 1 / 2 / 3*.",
      "Tabs reopen after a refresh and from workspace files again.",
      "A long-running server now rolls its reference date at the exchange's midnight: tenors, expired rungs, dividends and caches follow the new day; a pinned historical as-of is never rolled.",
      "Deep-wing slope anchors can now stay active under an active Kalman filter (Options ▸ Prior, off by default).",
      "The graph pairs cross-venue nodes with nearby expiries when asked (Cross-expiry tolerance, per block-rule pair too).",
    ],
  },
  {
    date: "2026-08-27",
    title: "Per-node as-of, fetch coverage preview, eSSVI in Compare",
    items: [
      "The Nodes pane shows the HH:MM of the chain serving each node, amber when it is not the as-of you asked for, with a ≠ as-of pill on the ticker.",
      "Fetch ▾ previews coverage before you pull: \"9/12 nodes exact · 3 fall back to Close\". An optional as-of mismatch gate (Options ▸ Calibration) turns an inexact node into a publish blocker.",
      "Compare gains a fourth family, eSSVI, as a lazy chip.",
      "Local Vol: the var-swap hard pin now reaches the quote; a robust loss and an ATM-spread var-swap row are available for LV too.",
      "The status bar labels the auto-fetch countdown \"Next snapshot\" when the unified timer is on.",
    ],
  },
  {
    date: "2026-08-27",
    title: "One fetch verb, tail-order gate, var-swap decomposition",
    items: [
      "Fetch ▾ carries a single **Snapshot (quotes + spot)** verb plus the as-of rows; the split verbs survive in Ctrl+K as \"(legacy)\". The auto timer can run the same unified pull (Options ▸ Workflow).",
      "The Local-Vol smile shows the fit target (bid-ask or haircut ribbon) under its quotes, with a persisted Target chip.",
      "The Var-swap card reads \"replication strip 92 % · tails L 5 % / R 3 %\" for parametric and LV nodes.",
      "A tail-order gate can make a wing-order failure a publish blocker; a band-relaxation diagnostic says how much wider the quote band would have to be for a pair to certify.",
      "Kalman-filter history is kept in workspace files, and the Prior Evidence and Filter Timeline panels can show replay evidence.",
    ],
  },
  {
    date: "2026-08-27",
    title: "Workbench wave 3: files, 3D charts, palette, split editors",
    items: [
      "**File ▾**: New, Open (Ctrl+O or drop a .json), Save (Ctrl+S), Save as…, Save to server…, Open from server, Recent — the whole configuration as a file. **Save / Open snapshot…** keeps quotes and fits and loads back as a File data source.",
      "**Export ▸**: surfaces JSON / CSV, quality report, the active chart as PNG.",
      "3D surfaces: zoom at the cursor, pan, pitch, ⌂ reset, and a crosshair that lifts the smile at T and the term curve at k, linked across the ticker's surface charts.",
      "Keyboard navigation in the Nodes pane, per-tab view memory (Layout ▸ Remember view per tab), split editors (Ctrl+\\), the Ctrl+K command palette over every menu row, drag a node onto the Graph canvas to light it.",
    ],
  },
  {
    date: "2026-08-27",
    title: "Workbench wave 2: lens icons, Compare chips, Priors ▾",
    items: [
      "Custom lens icons; menus reordered to Options · Universe ▾ · Help ▾ with Universe ▾ kept slim (manage / save / load).",
      "The Manage-universe dialog gains a Data-sources card (the market pill is now a passive readout); the as-of rows moved into Fetch ▾.",
      "Compare shows the prevailing model at once and fits the other families lazily from chips.",
      "Parametric and Local Vol read alike: NODE / TICKER view groups, the layer rail at the right of the chart, Y-center / Y-fit as overlay buttons, the x-axis unit in the chart footer, three stacked cards on the right (Spot move · Var-swap · Fit diagnostics).",
      "Priors ▾ with three save scopes; Density view with Density / Log Q-density / CDF; Ctrl+P quick open; middle-click a node for a pinned tab.",
    ],
  },
  {
    date: "2026-08-26",
    title: "The workbench",
    items: [
      "A VS Code-like shell replaces the tabbed top bar: activity bar with five lenses (Alt+1…5), a Nodes pane (Ctrl+B) with lit / dark dots, quality glyphs and RMS, one tab per node with preview / pin semantics, and a status bar that narrates the engine and keeps the last action with its timestamp.",
      "Lenses are tab-driven: the forward ladder, the LV per-expiry table, the term chart, the graph canvas and the Quality rows all open or activate the matching tab.",
      "Options is a dialog with a section rail; View ▾ and Layout ▾ hold display preferences and panes.",
    ],
  },
  {
    date: "2026-08-26",
    title: "Tail persistence and short-dated fits — new opt-in knobs",
    items: [
      "Prior wing-slope anchors (WingL / WingR) with their own scale; the prior var-swap row can carry the tail as a spread over ATM; a hard pin for the market var-swap quote.",
      "Short-dated smiles: winged calendar floors, refits that read their committed neighbours, a tick-size floor on the band width, a maturity-aware mid anchor, a robust loss (Huber / Cauchy), and vega-normalised price residuals for SVI-JW and MCS.",
      "Every new knob defaults to the previous behaviour; the Settings reference explains each.",
    ],
  },
  {
    date: "2026-08-25",
    title: "Auto-scaled smiles, weighting schemes, cross-expiry graph edges",
    items: [
      "Smile chart Y center / Y fit chips keep the y-axis on the visible x-range; crosshairs on the overlay, LV smile and forward-curve charts.",
      "Two new quote-weighting schemes (vega density, delta density) beside the existing ones.",
      "The graph can pair nearby expiries across venues (Cross-expiry tolerance in the Cross-asset card).",
      "Compare shows each family's wing law in a Tails column; stacked-IV and 3D grids densify over the quoted span.",
      "Bloomberg chains can include dailies and weeklies; Eurex live quotes require a two-sided book during session hours.",
    ],
  },
  {
    date: "2026-08-21",
    title: "Two comparable frames, three calibrate scopes, exchange delayed chains",
    items: [
      "The smile chart shows the prevailing quotes and the fit rolled to the prevailing spot; Calib. quotes and Calib. fit add the frame the last calibration used. The Quote Table joins both frames per strike.",
      "Calibrate offers three scopes as peers — Parametric + LV, Parametric only, Local-Vol only — and the face runs the last one chosen.",
      "Every RMS and max error scores the chosen fit target (mid, bid-ask or haircut band), in the tiles, the LV column, Compare and the report.",
      "New data sources with real bid / ask from the exchanges' delayed feeds: Cboe, Nasdaq, ASX, HKEX, SGX and Eurex (with its end-of-day settlement tier).",
      "Live quote beams no longer ghost when zooming the smile in Chrome.",
    ],
  },
  {
    date: "2026-08-20",
    title: "Live streaming: Bloomberg push feed, live table and chart bands",
    items: [
      "Bloomberg streams through its subscription service (no daily quota); a universe edit updates the subscription in place on Bloomberg and Massive.",
      "The Quote Table ticks live between refits from a per-node stream; the smile chart draws live bid / ask beams from the same stream.",
      "The replay-day campaign exposed and fixed two graph-edge defects (hub tickers, weight scaling).",
    ],
  },
];
