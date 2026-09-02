// Settings documentation — Workflow & data (HELP CENTER ARC, H1): the
// calibration / fetch trigger model, the scheduler cadences, streaming, and
// the data-freshness policy (data-age thresholds + the as-of mismatch gate).
// Prose only: type / default / range / enum come from settingsSchema.json.
//
// Cache discipline (SETTINGS_REFERENCE §4): the eight trigger / scheduler
// fields are pure workflow gates — they decide WHEN a fit runs, never what it
// computes — and the three freshness fields are display / report policy:
// dataAgeRedMin and asOfMismatchGate fail publish readiness in Quality without
// touching any fit.
//
// Sources: volfit/api/schemas.py (OptionsSettings comments, authoritative),
// Docs/handoff/SETTINGS_REFERENCE.md §2.1 / §2.12, ROADMAP V3.7 (the unified
// snapshot verb), components/options/SmallSections.tsx (labels).
import type { SettingDoc } from "../types";

export const WORKFLOW_DOCS: SettingDoc[] = [
  // ------------------------------------------------------------ triggers
  {
    key: "autoCalibrate",
    model: "options",
    section: "opt-workflow",
    label: "Auto-calibrate",
    summary: "Decide whether lit nodes refit by themselves after a fetch or a change, or wait for Calibrate.",
    details:
      "ON (continuous calibration): every lit node refits in the background whenever a quotes + spot snapshot arrives — a Fetch, the Auto-update snapshot tick, the streaming refit — and a quote edit or parameter change refits at once. A spot-only update (the stream, a spot-only timer, a spot probe) only transports the surface, never recalibrates. OFF (on-demand): those events only mark nodes STALE until you press Calibrate (top bar, or the palette's Calibrate commands), so expensive fitting happens on your trigger. It is also the master switch for unattended refits — the Auto-update snapshot tick and the streaming refit loop both obey it.\n\n" +
      "The code default is ON for the ungated dev/test app; the gated live server (restart.ps1 / serve.py) boots OFF when no saved preference exists, so a Fetch on a real feed never launches a fit you did not ask for. Pure workflow gate: a fit computed after OFF is the same fit, and no cache is invalidated.",
    example:
      "OFF: you fetch SPY at 14:30, the Nodes pane shows 12 STALE badges and the smile keeps the 14:00 fit until you press Calibrate; ON: the badges clear on their own within seconds.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoUpdate", "streamRefitSeconds", "autoRollPriorOnFetch", "localVolEnabled", "help:guides:workflow"],
    docs: ["00_system_overview"],
  },
  {
    key: "autoRollPriorOnFetch",
    model: "options",
    section: "opt-workflow",
    label: "Auto-roll prior on fetch",
    summary: "Roll each ticker's active prior to its latest saved snapshot during a Snapshot fetch, before any auto-calibration.",
    details:
      "The unified Snapshot fetch (Fetch ▸ Snapshot, `POST /fetch/snapshot`) runs chains → spot transport → optional prior roll → optional auto-calibrate. ON: the roll step takes the O(1) saved branch of the freshness ladder only — the newest saved prior snapshot becomes the active prior — never the prev-close recalibration and never an as-of flip, so it is cheap and cannot stall the fetch. No-op detection keeps a repeated fetch from flooding the event log.\n\n" +
      "OFF (the default): the Snapshot verb is byte-identical to the legacy fetch-options + fetch-spots pair, and the active prior changes only through Fetch priors. A roll bumps that ticker's active-prior version (its prior-anchored fits recompute), never the options version.",
    example:
      "You saved a prior at 10:00 and fetch a Snapshot at 14:30 with this ON: the 14:30 calibration anchors on the 10:00 prior instead of yesterday's close, and the Prior Evidence tab's prior age reads hours, not a day.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoCalibrate", "autoUpdate", "autoLoadPrior", "priorPersistenceMode", "help:guides:priors"],
  },
  // ------------------------------------------------------------ auto-update
  {
    key: "autoUpdate",
    model: "options",
    section: "opt-workflow",
    label: "Auto-update",
    summary: "Without a live stream: keep data manual, refresh the spot alone on a timer, or refresh quotes + spot on a timer.",
    details:
      "`off` (the default): quotes and spot refresh only with Fetch ▸ Snapshot (a manual fetch gets both). `spot`: every `autoUpdateSeconds` the scheduler probes the active source's spot and transports the surface under `dynamicsRegime` — never a refit, since a spot move is a read-time view of the cached fit. `snapshot`: every `autoUpdateSeconds` (15 s floor) the scheduler runs the Snapshot sequence — quotes + spot in one pull, an optional prior roll (`autoRollPriorOnFetch`), then a calibration when `autoCalibrate` is on, otherwise the lit nodes go STALE.\n\n" +
      "A calibration always prices spot and quotes from ONE snapshot (a fetch, or a synchronous read of the streaming book); a spot-only update, whatever its origin, only transports. Inert while a live book streams (`autoStream` on a streaming source): spot and quotes then flow continuously and the dialog dims this control — `streamFreezeFit` is the streaming-side switch. Workflow gate.",
    example:
      "Spot only at 5 s on Cboe: the SPY smile slides along the strike axis every 5 s as spot ticks and no node turns STALE; Spot + quotes at 60 s with Auto-calibrate on: once a minute the chains refetch and the 12 nodes refit unattended.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoUpdateSeconds", "autoCalibrate", "autoStream", "streamFreezeFit", "dynamicsRegime", "help:guides:workflow"],
  },
  {
    key: "autoUpdateSeconds",
    model: "options",
    section: "opt-workflow",
    label: "Every (s)",
    unit: "seconds",
    summary: "Set the Auto-update cadence — spot alone, or quotes + spot (15 s floor).",
    details:
      "Seconds between two Auto-update ticks. For `spot` a tick is one spot probe per selected ticker: 5 s is fine on a book that answers in memory, 30–60 s on a REST or delayed source where each probe is a metered call and the number is stale anyway. For `snapshot` a tick downloads a full chain per ticker (a 14 MB Cboe index file, a paginated Massive pull), so the backend floors the value at 15 s and the dialog clamps it; 60 s matches a 15-min-delayed tier with headroom, 300+ s for a desk that wants the book to age quietly.\n\n" +
      "Keep the snapshot cadence below `dataAgeAmberMin`, or the market pill turns amber between ticks.",
    example:
      "Spot + quotes at 60 with dataAgeAmberMin 20: the pill stays green through every cycle; at 1800 it turns amber for the last 10 minutes of each cycle.",
    activation: "Read only while autoUpdate is spot or snapshot, and no book is streaming",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoUpdate", "dataAgeAmberMin", "streamRefitSeconds"],
  },
  // ------------------------------------------------------------ streaming
  {
    key: "streamRefitSeconds",
    model: "options",
    section: "opt-workflow",
    label: "Stream refit every (s)",
    unit: "seconds",
    summary: "Set how often the streaming loop rebuilds the chain from the live book and recalibrates the lit nodes.",
    details:
      "While a real-time push book is open (Massive WebSocket or Bloomberg //blp/mktdata, `autoStream` on) and the fit is not frozen (`streamFreezeFit` off), the scheduler rebuilds the chain from the in-memory book and refits every lit node at this cadence — the stream's own quotes + spot tick, seconds-scale, distinct from the `autoUpdate` timer that only exists without a stream. It obeys `autoCalibrate`: with continuous calibration off the surface still transports to the book spot and nodes refit only on Calibrate.\n\n" +
      "5 s default: an LQD slice fits in tens of milliseconds and the process pool clears a 12-node universe well inside the interval. Lengthen it on a large universe or with Local Vol fits on, or the next tick queues behind the last. The dialog shows it under Stream live book while streaming is on and the fit is not frozen. No effect on Yahoo / Synthetic.",
    example:
      "2 on Massive Live with 12 SPY/QQQ nodes: the smile and the fit-history strip refresh every 2 s; with 40 nodes and Local Vol on, use 15 or the ticks pile up.",
    activation: "Read only while a real-time book is streaming, the fit is not frozen and Auto-calibrate is on",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoStream", "streamFreezeFit", "autoCalibrate", "autoUpdateSeconds", "localVolEnabled"],
  },
  {
    key: "streamFreezeFit",
    model: "options",
    section: "opt-workflow",
    label: "Freeze fit while streaming",
    summary: "Hold the fit at its calibration spot while the live book streams.",
    details:
      "OFF (the default): while a book streams, spot and quotes flow continuously — the book spot transports the surface live for every market-following ticker (a scenario ticker keeps its dial) and, with `autoCalibrate` on, the streaming refit rebuilds the chain and refits the lit nodes every `streamRefitSeconds`. ON: the fit stays where it was calibrated — no live transport, no streaming refit — while Fetch, Calibrate and the live quote layer still read the book, so the chart shows live quotes against a still surface and Calibrate takes a synchronous quotes + spot snapshot when you press it. The Spot card's dial stays free.\n\n" +
      "Only meaningful with `autoStream` on a streaming source (the dialog shows it then); without a stream the `autoUpdate` timer decides what moves. Workflow gate.",
    example:
      "Frozen on Bloomberg while the index sells off: the quotes ribbon drifts away from the fit on screen, the status bar reads 'Stream · frozen', and one Recalibrate re-anchors at the current book.",
    activation: "Read only while a real-time book is streaming",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoStream", "streamRefitSeconds", "autoUpdate", "autoCalibrate"],
  },
  {
    key: "autoStream",
    model: "options",
    section: "opt-workflow",
    label: "Stream live book (Massive / Bloomberg)",
    summary: "Auto-open the real-time push feed on a streaming-capable source so spot and quotes flow continuously from the in-memory book.",
    details:
      "ON (the default): when the active source can stream — Massive's WebSocket options book, or Bloomberg's //blp/mktdata subscriptions (quota-free, unlike the metered bdp path) — the backend opens the feed, and chain Fetch, Calibrate and spot read from the fast in-memory book instead of a slow, paginated or metered snapshot pull. It is the one switch that opens the book: live transport of the surface and the streaming refit (`streamRefitSeconds`, with `autoCalibrate`) follow from the book being open, unless `streamFreezeFit` holds the fit. The `autoUpdate` timer is inert while a book streams, and the dialog dims it.\n\n" +
      "OFF forces the request path — useful when a delayed-tier key's WS URL is unset or the socket misbehaves; `autoUpdate` then decides what refreshes. No effect on Yahoo / Synthetic. Workflow gate.",
    example:
      "ON with a Massive key and VOLFIT_MASSIVE_WS_URL set: the Data Source pill shows the streaming badge and Fetch ▸ Snapshot returns in well under a second; OFF, the same fetch pages the REST chain and takes several seconds.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["streamFreezeFit", "streamRefitSeconds", "autoUpdate", "help:guides:data-sources"],
  },
  // ------------------------------------------------------------ freshness policy
  {
    key: "dataAgeAmberMin",
    model: "options",
    section: "opt-workflow",
    label: "Data age · amber (min)",
    unit: "minutes",
    summary: "Set the live-chain age past which the market pill turns amber.",
    details:
      "The data-age slice measures how old the loaded LIVE chain is (its snapshot timestamp against now) on real feeds; synthetic and as-of close chains are exempt. Past this threshold the market pill turns amber — advisory only: a 15-min delayed tier lands here on every fetch, which is why the default 20 leaves it headroom. Nothing else changes: no readiness issue, no refit, no cache bump.\n\n" +
      "Pair it with `autoUpdateSeconds` (Spot + quotes) so the pill stays green between scheduled ticks.",
    example:
      "10 on a 15-min delayed feed: every fresh fetch is already amber; 20 keeps the pill green for 5 minutes after each fetch.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["dataAgeRedMin", "autoUpdateSeconds", "asOfMismatchGate", "help:guides:quality"],
  },
  {
    key: "dataAgeRedMin",
    model: "options",
    section: "opt-workflow",
    label: "Data age · red (min)",
    unit: "minutes",
    summary: "Set the live-chain age past which the pill turns red and Quality fails the node's publish readiness.",
    details:
      "Past this age the market pill turns red, Calibrate shows a stale-data warning, and the Quality report adds a readiness issue to every node served from that chain — the publish export blocks. The motivating case: a premarket fetch of yesterday's book must not read '13/13 ready'. Default 120 min tolerates a lunch-hour gap on a delayed tier.\n\n" +
      "Report and display policy only: the fit itself is unchanged and no cache is touched, so lowering this number can flip readiness for the whole universe without a single recalibration.",
    example:
      "60 at 09:15 ET with a chain stamped yesterday 16:00: the pill is red, Quality reads 0/12 ready with a 'chain age 17h' issue, and Publish stays disabled until you fetch.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["dataAgeAmberMin", "asOfMismatchGate", "help:guides:quality"],
  },
  {
    key: "asOfMismatchGate",
    model: "options",
    section: "opt-workflow",
    label: "As-of mismatch gate",
    summary: "Turn a node served off the requested as-of session into a Quality readiness failure that blocks publish.",
    details:
      "The per-node effective as-of compares the chain's stamped session with the As-of you requested. A mismatch arises when a live-only source ignores a close request, or a feed stamps another session. ON: such a node gets the readiness issue 'as-of mismatch: chain stamped <ISO> vs the requested <day>', is not ready, and the publish export blocks on it. OFF (the default): advisory only — the Nodes pane still flags '≠ as-of' and the Quality card mentions it, but readiness and publish ignore it.\n\n" +
      "A data-provenance flag, never an arbitrage flag. Display and report policy: the fit is untouched and no cache is bumped.",
    example:
      "You request the 2026-08-28 close on Yahoo (live-only) with the gate ON: every SPY node shows ≠ as-of, Quality reads 0/12 ready, and Publish stays disabled until you switch to a source that serves that close.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["dataAgeRedMin", "dataAgeAmberMin", "help:guides:quality", "help:guides:data-sources"],
  },
];
