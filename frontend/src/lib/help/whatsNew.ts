// What's new (HELP CENTER ARC, H2): release notes in USER language, newest
// first, derived from the ROADMAP session wraps of 2026-08-20 … 2026-08-31.
// Bullets name UI surfaces and behaviour, never code identifiers (except
// where the identifier IS the UI name). Rendered by WhatsNewPage.tsx.
import type { WhatsNewEntry } from "./types";

export const WHATS_NEW: WhatsNewEntry[] = [
  {
    date: "2026-09-09",
    title: "Drive the desk from a Claude chat: the MCP connector, the routine in one call, four inline charts",
    items: [
      "The app is now a connector for Claude Desktop (and, over HTTPS, claude.ai): about twenty curated tools wrap the running backend — universe, fetch, settings, calibrate with streamed progress, report, views, charts — so a chat edits the same universe, settings and fits the workbench shows. Setup and the tool list are in Help ▸ Guides ▸ *Drive the desk from a Claude chat*.",
      "Two macros: `run_desk_workflow` runs the desk routine in one call (universe → fetch → settings → calibrate → report, the Local Vol compare chart in the same reply) as a background job that no chat time budget can cut short; `compare_settings` calibrates under two settings and tabulates the differences per ticker and per expiry in vol bp. A ticker just added is not quoted twice.",
      "Four charts render inside the conversation as MCP Apps — Local Vol compare (affine sheet, Dupire twin, difference), the smile with bands and prev / next expiry, the vol surface (3D / heatmap, k / K/F / strike axis, quoted-range crop, ATM ridge) and the term structure (calendar or event-dilated clock, events, dividends, calendar violations). Every card has a **Workbench** button that opens the node in the app.",
      "Bloomberg: a bare non-US index root (SX5E, SXXP, DAX, UKX, CAC, SMI, NKY, HSI…) now resolves to the index security, so EuroStoxx quotes on the first try. A tool called without a fit target uses the Options' target, so a run, its report and its charts always name one target.",
    ],
  },
  {
    date: "2026-09-09",
    title: "Local Vol: the fast solver now runs the Bid-Ask and Haircut targets — a haircut calibration is 2.5–4× faster",
    items: [
      "The Local Vol calibration's matrix-free solver used to hand the Bid-Ask and Haircut fit targets to the legacy trust-region solver, whose dense factorisation made a haircut fit on a SPY ladder the slowest calibration in the app. Its step is now refined until the variance box and the band edges it will meet are part of the step it takes, and a step is accepted whenever the objective truly falls — so the band targets run on the fast solver too.",
      "On the desk fixtures (SPY weeklies, Bloomberg SPY and NVDA; haircut, 20 nodes, convex wing) a cold Bid-Ask or Haircut Local Vol fit takes 1.4–4.6 s instead of 5–14 s, at the same or a better fit to the target (band error within 0.03 bp, converged-operator error within 1 bp). Mid fits are unchanged.",
      "A Haircut or Bid-Ask recalibration that starts from a Mid surface now relaxes it toward the smoother in-band solution instead of returning it unchanged.",
      "Options ▸ Local Vol ▸ LV solver: `trf` remains available as the legacy solver and is byte-identical to before; `gn` is the default for every fit target.",
    ],
  },
  {
    date: "2026-09-09",
    title: "Quote weighting: a Uniform target, and a weight strip that shows the target beside the weight — on the smile's own axis",
    items: [
      "Options ▸ Calibration ▸ Quote weighting gained **Uniform**: the flat target. Like the time-value, vega and delta schemes it multiplies its target shape by each quote's strike-density correction, so strikes listed every 5 points weigh like 1/K and the summed weight is uniform in log-strike whatever the exchange lists. **Equal** stays the default and is unchanged: one vote per quote, no correction, the aggregate weight follows the listing grid.",
      "The **Weights** strip under the smile now draws what the scheme asks for beside what the fit does: the grey bars are the scheme's target shape at each quote (flat for Equal and Uniform, the time-value / vega / |delta| profile otherwise), the accent bars the mean-1 weight the least squares actually sums. The old \"density 1/sᵢ\" bars — the quote crowding, the inverse of the correction — are gone; hovering a bar reads the target, the multiplier applied and the weight.",
      "The strip sits on the smile chart's own x axis: every axis mode, the brush window, and now the wheel-zoom and the pan too, so a bar is always under its quote.",
    ],
  },
  {
    date: "2026-09-08",
    title: "Local Vol: a second-order march on graded grids — the operator error the fit used to absorb is gone, and a surface with dailies marches a fraction of the nodes",
    items: [
      "The Local Vol calibration's time stepping is now second-order (BDF2) on a time grid graded from the payoff kink, with every vertex row of the sheet a grid point. On every test surface the march's own error is a few basis points per expiry, where the old first-order march left tens to a hundred-plus basis points that the calibration bent the fitted sheet to cancel — and it gets there in two to three times fewer steps.",
      "The strike lattice is graded per expiry: each expiry is resolved at its own step over its own range, the wings coarse, and the at-the-money row is always a node. A same-day or two-day expiry no longer forces ~1700 strike nodes on the whole surface (~400 now, the same near-money resolution), so Calibrate on a universe with dailies is several times faster.",
      "Options ▸ Local Vol shows a **Time stepping** selector — BDF2 (default), Rannacher (opt-in: a few bp finer on the reprice, ~1.5× per step, not monotone) and Implicit Euler (legacy) — and a **Graded strike lattice** toggle. The legacy pair reproduces every historical fit exactly; both knobs touch the Local Vol cache only, never a parametric fit.",
      "The **converged** figure beside each expiry's RMS and the Compare tab's **floor** now read the fit's own scheme and lattice. A large gap between the in-operator and converged figures points at the lattice or the data, not the time stepping.",
    ],
  },
  {
    date: "2026-09-08",
    title: "Local Vol: a Compare tab — the fitted sheet beside the parametric surface's Dupire twin; 3D surfaces crop and stay centred",
    items: [
      "The Local Vol lens gained a **Compare** view. It differentiates the calibrated parametric surface the classical way (Dupire's formula on the displayed model, its total variance carried between expiries by a smooth interpolation or the market's bucket staircase) and draws that **Dupire twin** beside the fitted local-vol sheet on the same lattice: **Sheets** side by side under one camera and one crop, their **Difference** on a diverging ramp, and the **Smiles** of both against the quotes with a per-expiry score table.",
      "The twin is drawn smooth — the surface sampled between the vertices, the vertices themselves exact — while the fitted sheet keeps its triangles, because that is what each one is. Its smile and scores come from the smooth surface on a second-order operator; the strip reads the **round trip** (the twin against its own source) beside the operator's **floor** and the coarse sample's own figure, then the repairs the extraction needed.",
      "The comparison is built at the calibration spot and never rebuilds on a live spot tick; a moved spot shows an **ANCHOR** badge. The twin is a reference only — never a fit, a prior or the calibration's seed.",
      "Every 3D surface — the Parametric surface, the LV mesh, the IV surface and the Compare sheets — now has a second slider beside the plot: together with the strike slider it crops a strike × maturity rectangle that fills and re-centres the view. The wheel zooms about the sheet's centre and pans are bounded, so a zoomed sheet never leaves the window. The two Compare sheets crop and rescale as one.",
    ],
  },
  {
    date: "2026-09-08",
    title: "Graph lens: first-use fixes — Focus that keeps editing, drag to connect, bundles that fold back, + reverse",
    items: [
      "**Focus** now re-fits the graph to the whole lens and keeps editing: a selected arrow or pair floats its card over the canvas, below the toolbar; Esc closes the card first, a second Esc leaves Focus, and **F** toggles it from the keyboard. The canvas toolbar is one row at the top-right with Focus first, so a short pane never clips it; the gesture list moved behind a **gestures ⓘ** chip.",
      "A plain **drag from node to node** draws a relation — no tool or modifier needed (the Connect tool and Shift still work). Dragging onto an arrow that already exists selects it instead of overwriting it, and a new cross relation expands its bundle so you can see it.",
      "Curved ticker-pair arrows fold back: one click expands the bundle into its node-to-node arrows and opens the pair inventory, the next click collapses both at once. Each curve carries a midpoint **handle** (the relation count, or − while expanded) that stays on top of everything, and an expanded curve bows out clear of its arrows, so the pair can always be clicked or unclicked.",
      "The relation card gained **+ reverse**: an arrow is one factor, informer → receiver, whose reverse is already implied under reciprocal semantics (the ⇐ readout); the button adds the explicit opposite arrow when you want one (two facing directed arcs form a cycle the Layered solve rejects, and preflight says so).",
      "Hover readouts flip to the left of their anchor near the right edge, so they never cover the toolbar.",
    ],
  },
  {
    date: "2026-09-07",
    title: "The Graph lens, rebuilt for the desk: sliders, arrows you can edit, Layered by default",
    items: [
      "Operator order flipped: **Layered** leads, **Precision** is next, and **Smooth field** moved under the Coupling pane's Advanced section as the labelled legacy rollback — its η κ λ ν dials and the per-edge weight matrix are still there, one click away, but no longer compete for attention on the top bar.",
      "The left pane (now called **Coupling**) is three levels, not one flat list: Level 0 is what you touch every day — the Desk | Learned preset, a Calendar relations switch with its confidence slider, a Cross-asset confidence slider (both σ in vol points, right = more confident) and a live +1 pt example; **Fine-tune** opens shape, decay, per-ticker overrides, the cross-asset matrix and the Layered Dynamics card; **Advanced** holds the units toggle and the door to the legacy operator.",
      "Every relation is now an arrow drawn on the canvas, informer → receiver: thickness reads its confidence, colour its β (cool below 1, slate at 1, warm above, rose negative). Click an arrow to edit it, a drag from node to node draws a new one (plain, Connect tool or Shift), Delete removes the selected relation, a ticker's pod label collapses it, and Focus clears the side panes for a big universe.",
      "The relation card (Inspector) puts sliders on everything: Confidence (with an **auto** badge and ↺ for calendar rows still on the maturity-distance rule), a linked β handle (unlink for β skew / β curvature), class, semantics and a flip. The drawer's new **Relations** tab lists every arrow with search, class filters, sort, undo / redo, Seed auto / Reset to auto, and **Templates ▾** (Hub → names, Peers ⇄, Calendar only) to lay down a whole universe's relations in one click.",
      "**Live** re-solves on every dial or arrow edit as a non-persisting preview (tagged **preview** in the summary strip); **Run** still commits and is still the only thing that records.",
      "The manual run-draft toggle is gone: while an edit is staged, Run solves the draft automatically, and the config pill's **Apply** / **Discard** replace what used to be a three-way choice.",
    ],
  },
  {
    date: "2026-09-07",
    title: "The smile inferred from the graph is drawn on every node of the Run",
    items: [
      "After a Graph **Run**, every node of the solved universe shows its inferred smile on the Smile chart: violet dash-dot, an **INFERRED · GRAPH** badge naming the Run time, the prior tier and the posterior ATM ± sd. On a dark node it is the only curve, so you can read it against the live quotes; on a calibrated node it sits beside the fit.",
      "It is transported with the spot exactly like a calibrated smile — the market frame rolls it to the prevailing spot and the live tick stream re-rolls it on every spot move. It is never a calibration: not committed, not a prior, never calibration input.",
      "The **Graph** entry in the chart's layer rail hides or shows it (per tab); the ✕ on the badge does the same.",
    ],
  },
  {
    date: "2026-09-07",
    title: "One prior per node, active on save — no Fetch step, and the Graph starts from it",
    items: [
      "**Save prior** (visible tab, all open tabs, all calibrated) now makes the saved fit the node's prior at once: the next calibration's persistence rows pull toward it, the Compare **+ Prior** cell reads it, the dotted prior draws on the Smile, and the Graph uses it as the node's starting point. A restart restores the saved priors from the store.",
      "**Fetch priors** keeps its two jobs — re-read the saved priors, and seed the tickers that have nothing saved from the previous close — and is no longer required to activate what you saved.",
      "Every save runs under the fit target on screen (mid, bid-ask or haircut): a haircut session used to snapshot nothing because the save looked under mid. The Graph's fallback baseline also reads today's fit under the target on screen, so a haircut session no longer starts from a flat 20 % surface.",
    ],
  },
  {
    date: "2026-09-07",
    title: "Compare and the node views: the anchoring axis — what the prior and the filter bought",
    items: [
      "A fourth chip group in the Compare strip — **Free**, **+ Prior**, **+ Filter** — refits the prevailing model with its anchoring blocks removed or added: no prior and no filter (the pure market fit), the persistence prior alone, or the filter's prediction from the kept state. Each cell lands as a dashed row of the same family, and the new **Pull** column reads its distance to the free fit in ATM vol bp (skew and curve RMS on hover), so a node tells what each block bought.",
      "A **fit** switch in the Smile and Density header draws one of these shadow fits in place of production — the curve, both frames and the diagnostics read the shadow, while the quotes, the prior overlay and the committed calibration stay the node's. A *SHADOW* tag says which cell is on screen; quote edits refetch the shadow.",
      "Only cells whose input exists are offered (an active prior, a kept filter state — a missing one says why in its tooltip). **+ Filter** under overlay mode is a preview of what active mode would fit; under active mode it is production. The cell production coincides with is tagged *prod* in the strip and in the table, so the axis always says which row is the prevailing one.",
    ],
  },
  {
    date: "2026-09-04",
    title: "Compare: match LQD's tails and compare bellies only",
    items: [
      "Three new toggles in the Compare strip — **= Var-swap**, **= Lee wings**, **= Edge** — refit SVI-JW and MCS with their tails pulled onto LQD's: the fair var-swap level, both asymptotic total-variance slopes, or the value and slope of total variance at the last quoted strike on each side (where extrapolation starts). Fits to the same quotes differ in the wings, so with the tails matched the RMS column reads belly expressiveness alone.",
      "LQD joins the comparison as the pinned *target* while a toggle is lit; constrained rows carry a teal pill naming the constraints, and the Lee / Var-swap columns become a self-check that reads equal across rows. eSSVI is never constrained.",
      "Each match is a stiff row (equality to solver tolerance), so the belly pays: with all three lit SVI-JW is over-determined and meets them in the least-squares sense. **= Lee wings** needs LQD's exponential tails (α = 0) — on a name with generalized tails the chip shows an amber ! and the reason; a reference slope above the Lee cap is matched at the cap (a *cap* tag).",
    ],
  },
  {
    date: "2026-09-04",
    title: "One chart grammar: Compare, Densities, Stacked IV and the Local Vol smile zoom like the Smile",
    items: [
      "Every 2-D chart now carries the Smile chart's full interaction stack: wheel zoom (Shift = x only, Alt = y only), drag to pan, double-click or ⌂ to reset, the **Y center** / **Y fit** buttons at the top-left of the plot, and an x-range slider under the plot.",
      "Compare gains the x-axis unit selector in the chart footer (ln(K/F), strike, % ATM, delta, normalized) and shares the Smile view's strike window: zoom the belly in Smile, switch to Compare, see the same belly. Its y-axis reads in vol percent.",
      "Densities and Stacked IV (Parametric and Local Vol) and the Local Vol smile get the same Y buttons and slider; the y-axis auto-fits the points inside the visible x-range, so a zoom into a wing no longer leaves the curves squashed at the bottom. The Y center / Y fit preference is shared by both lenses.",
      "With Y center or Y fit lit, a drag pans the x-axis only — the policy places y. Alt+wheel still zooms y by hand.",
    ],
  },
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
