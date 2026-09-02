// Settings documentation — Workflow & data (HELP CENTER ARC, H1): the
// calibration / fetch trigger model, the scheduler cadences, streaming, and
// the data-freshness policy (data-age thresholds + the as-of mismatch gate).
// Prose only: type / default / range / enum come from settingsSchema.json.
//
// Cache discipline (SETTINGS_REFERENCE §4): the nine trigger / scheduler
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
      "ON: after option chains are fetched, every lit node calibrates in the background, and a quote edit or parameter change refits at once. OFF: those events only mark nodes STALE until you press Calibrate (top bar, or the palette's Calibrate commands), so expensive fitting happens on your trigger. It is also the master switch for unattended refits — the automatic chain refetch and the streaming refit loop both obey it.\n\n" +
      "The code default is ON for the ungated dev/test app; the gated live server (restart.ps1 / serve.py) boots OFF when no saved preference exists, so a Fetch on a real feed never launches a fit you did not ask for. Pure workflow gate: a fit computed after OFF is the same fit, and no cache is invalidated.",
    example:
      "OFF: you fetch SPY at 14:30, the Nodes pane shows 12 STALE badges and the smile keeps the 14:00 fit until you press Calibrate; ON: the badges clear on their own within seconds.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["optionsFetchMode", "streamRefitSeconds", "autoRollPriorOnFetch", "localVolEnabled", "help:guides:workflow"],
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
    related: ["autoCalibrate", "schedulerUnifiedFetch", "autoLoadPrior", "priorPersistenceMode", "help:guides:priors"],
  },
  // ------------------------------------------------------------ spot
  {
    key: "spotMode",
    model: "options",
    section: "opt-workflow",
    label: "Spot prices",
    summary: "Choose whether spots refresh only on demand or the scheduler polls them and transports the surface live.",
    details:
      "`static` (On-demand, the default): spots refresh only with Fetch ▸ Snapshot or the legacy palette command 'Fetch spots only'. `realtime`: the backend scheduler polls the active source's spot every `spotPollSeconds` and transports the surface under `dynamicsRegime` — no recalibration, since a spot move is a read-time view of the cached fit.\n\n" +
      "Real-time spot is also the gate for live re-pricing and for the streaming refit loop (`streamRefitSeconds`); `autoStream` opens the book regardless. While a book streams the selector keeps its meaning — the book supplies spots either way; `realtime` additionally re-prices the surface live and runs the streaming refit, `static` keeps the fit at its calibration spot while market-following tickers track the book spot at the poll cadence — so the dialog leaves it enabled (unlike the options-quotes timer). Default static because a polled spot on a delayed or metered feed spends quota on a number that moves every 15 minutes. Workflow gate.",
    example:
      "Real-time at 5 s on Massive Live: the SPY smile slides along the strike axis every 5 s as spot ticks, the ATM marker tracks, and no node turns STALE — nothing was recalibrated.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["spotPollSeconds", "dynamicsRegime", "autoStream", "streamRefitSeconds", "help:guides:workflow"],
  },
  {
    key: "spotPollSeconds",
    model: "options",
    section: "opt-workflow",
    label: "Poll every (s)",
    unit: "seconds",
    summary: "Set how often the scheduler polls the spot in real-time spot mode.",
    details:
      "Each tick pulls one spot per selected ticker and transports the surface. 5 s suits a streaming book (Massive WebSocket, Bloomberg mktdata), where the read is in-memory and free. On a REST or delayed source lengthen it to 30–60 s: each poll is a metered call and the number is stale anyway.\n\n" +
      "Under `schedulerUnifiedFetch` a snapshot tick re-arms this timer, so a spot poll due on the same tick is absorbed rather than fired twice.",
    example:
      "60 on Yahoo: spots and the transported surface update once a minute, and the market pill's spot age stays under a minute without burning a request every 5 s.",
    activation: "Read only while spotMode is realtime",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["spotMode", "schedulerUnifiedFetch", "optionsFetchMinutes"],
  },
  // ------------------------------------------------------------ chains
  {
    key: "optionsFetchMode",
    model: "options",
    section: "opt-workflow",
    label: "Options quotes",
    summary: "Choose whether option chains refresh only on demand or on the scheduler's timer.",
    details:
      "`on_demand` (the default): chains refresh only with Fetch ▸ Snapshot or the legacy palette command 'Fetch option quotes only'. `auto`: the scheduler refetches every `optionsFetchMinutes` — the bare chain refetch, or the full Snapshot sequence when `schedulerUnifiedFetch` is on — then auto-calibrates when `autoCalibrate` is on, otherwise marks the lit nodes STALE.\n\n" +
      "Default on-demand so the chain pull — the expensive, metered call on most sources — happens when you ask for it. Distinct from the streaming refit loop, which rebuilds the chain from the in-memory book at a seconds cadence. With `autoStream` on the dialog dims this selector: a streaming source serves every Fetch from the book and the streaming refit replaces the timer (a source without a stream, such as Yahoo or Cboe, still follows the saved value). Workflow gate.",
    example:
      "Auto every 5 min with Auto-calibrate on: at 14:30, 14:35 and 14:40 the 12 SPY nodes refetch and refit unattended, and the fit-history strip gains one entry per tick.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["optionsFetchMinutes", "schedulerUnifiedFetch", "autoCalibrate", "streamRefitSeconds", "help:guides:workflow"],
  },
  {
    key: "optionsFetchMinutes",
    model: "options",
    section: "opt-workflow",
    label: "Fetch every (min)",
    unit: "minutes",
    summary: "Set the chain refetch cadence of the automatic options fetch.",
    details:
      "How often the scheduler pulls fresh chains for the selected universe. Each tick is a full chain call per ticker (paginated REST on Massive, one bulk call on Yahoo), so this is the quota lever. 5 min matches a 15-min-delayed tier's update rhythm with headroom; use 1 min on a real-time REST tier, 60+ min for an end-of-day desk that wants the book to age quietly.\n\n" +
      "Keep it below `dataAgeAmberMin`, or the market pill will turn amber between ticks.",
    example:
      "15 with dataAgeAmberMin 20: the pill stays green through every cycle; set 30 and it turns amber for the last 10 minutes of each cycle.",
    activation: "Read only while optionsFetchMode is auto",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["optionsFetchMode", "dataAgeAmberMin", "spotPollSeconds"],
  },
  {
    key: "schedulerUnifiedFetch",
    model: "options",
    section: "opt-workflow",
    label: "Scheduler uses unified snapshot fetch",
    summary: "Make each automatic fetch tick run the full Snapshot sequence instead of the bare chain refetch.",
    details:
      "ON: every auto tick runs exactly `POST /fetch/snapshot` — chains → spot transport → optional prior roll (`autoRollPriorOnFetch`) → optional auto-calibrate — so the scheduled path and the Fetch ▸ Snapshot button leave the same state behind. The double-fire guard re-arms the real-time spot timer on each snapshot tick, so a spot poll due on the same tick is absorbed, never fired twice.\n\n" +
      "OFF (the default): the legacy split timers — chains and spots on independent clocks — byte-identical to the product before the V3.7 rider. Workflow gate.",
    example:
      "ON with Auto every 5 min, Real-time spot at 5 s and Auto-roll prior on: each 5-minute tick refetches chains, transports spot, rolls the saved prior and refits in one sequence, and the spot timer skips the poll that would have coincided with it.",
    activation: "Read only while optionsFetchMode is auto",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["optionsFetchMode", "autoRollPriorOnFetch", "spotPollSeconds", "autoCalibrate"],
  },
  // ------------------------------------------------------------ streaming
  {
    key: "streamRefitSeconds",
    model: "options",
    section: "opt-workflow",
    label: "Stream refit cadence",
    unit: "seconds",
    summary: "Set how often the streaming loop rebuilds the chain from the live book and recalibrates the lit nodes.",
    details:
      "While a real-time push book is open (Massive WebSocket or Bloomberg //blp/mktdata, with `autoStream` on and `spotMode` realtime), the scheduler rebuilds the chain from the in-memory book and refits every lit node at this cadence — a seconds-scale loop distinct from the minutes-scale REST refetch of `optionsFetchMinutes`. It obeys `autoCalibrate`.\n\n" +
      "5 s default: an LQD slice fits in tens of milliseconds and the process pool clears a 12-node universe well inside the interval. Lengthen it on a large universe or with Local Vol fits on, or the next tick queues behind the last. The dialog shows it as 'Stream refit every (s)' under Spot prices once Stream live book is on and spot is Real-time. No effect on Yahoo / Synthetic.",
    example:
      "2 on Massive Live with 12 SPY/QQQ nodes: the smile and the fit-history strip refresh every 2 s; with 40 nodes and Local Vol on, use 15 or the ticks pile up.",
    activation: "Read only while a real-time book is streaming and spotMode is realtime",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["autoStream", "spotMode", "autoCalibrate", "optionsFetchMinutes", "localVolEnabled"],
  },
  {
    key: "autoStream",
    model: "options",
    section: "opt-workflow",
    label: "Stream live book (Massive / Bloomberg)",
    summary: "Auto-open the real-time push feed on a streaming-capable source so fetches serve from the in-memory book.",
    details:
      "ON (the default): when the active source can stream — Massive's WebSocket options book, or Bloomberg's //blp/mktdata subscriptions (quota-free, unlike the metered bdp path) — the backend opens the feed, and chain Fetch, Calibrate and spot read from the fast in-memory book instead of a slow, paginated or metered snapshot pull. OFF forces the request path — useful when a delayed-tier key's WS URL is unset or the socket misbehaves.\n\n" +
      "Independent of `spotMode`: the book only feeds fetches; live re-pricing and the streaming refit loop still need real-time spot. ON dims the options-quotes timer in the dialog (the book replaces it) and reveals the stream refit cadence under Spot prices once spot is Real-time. No effect on Yahoo / Synthetic. Workflow gate.",
    example:
      "ON with a Massive key and VOLFIT_MASSIVE_WS_URL set: the Data Source pill shows the streaming badge and Fetch ▸ Snapshot returns in well under a second; OFF, the same fetch pages the REST chain and takes several seconds.",
    cacheEffect: "workflow-gate",
    surfaced: true,
    related: ["spotMode", "streamRefitSeconds", "optionsFetchMode", "help:guides:data-sources"],
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
      "Pair it with `optionsFetchMinutes` so the pill stays green between scheduled ticks.",
    example:
      "10 on a 15-min delayed feed: every fresh fetch is already amber; 20 keeps the pill green for 5 minutes after each fetch.",
    cacheEffect: "display-only",
    surfaced: true,
    related: ["dataAgeRedMin", "optionsFetchMinutes", "asOfMismatchGate", "help:guides:quality"],
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
