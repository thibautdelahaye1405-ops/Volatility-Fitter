// Pure builders of the New series… dialog (SERIES ARC S4 §3.1): the form
// state and its defaults, the lane-list edits, and the SeriesSpec /
// SeriesImportRequest the backend receives. Kept apart from the dialog so
// the mapping is unit-testable and the dialog stays under the file-size
// policy. Mirrors backend volfit/api/schemas_series.py defaults.
import type {
  FitMode, ImportSource, LadderPolicy, LaneSpec, SeriesImportRequest, SeriesMode, SeriesSpec, SeriesStep,
} from "../../lib/seriesTypes";
import { STEP_LABELS } from "../../lib/seriesTypes";

/** The clock's zone: the time of day and the session grid are read in New
 *  York (the backend's default; the roadmap's "15:45 ET"). */
export const SERIES_TZ = "America/New_York";
/** schemas_series.MAX_FRAMES. */
export const MAX_FRAMES = 2000;
/** Steps whose instants need a time of day. */
export const DAILY_STEPS: ReadonlySet<SeriesStep> = new Set(["daily", "weekly", "session_close"]);

export interface NewSeriesForm {
  mode: SeriesMode;
  /** "" = the derived default name. */
  name: string;
  step: SeriesStep;
  count: number;
  /** datetime-local value, or "" (live: now; historical: the latest instants). */
  start: string;
  sessionOnly: boolean;
  /** HH:MM in SERIES_TZ. */
  timeOfDay: string;
  warmupFrames: number;
  policy: LadderPolicy;
  /** "" = no cap. */
  maxExpiries: string;
  fitMode: FitMode;
  note: string;
  importKind: ImportSource["kind"];
  importPath: string;
  /** "" = every stored snapshot. */
  importMaxFrames: string;
}

export function defaultForm(fitMode: FitMode): NewSeriesForm {
  return {
    mode: "historical", name: "", step: "15m", count: 20, start: "", sessionOnly: true, timeOfDay: "15:45",
    warmupFrames: 0, policy: "pinned", maxExpiries: "", fitMode, note: "",
    importKind: "captures", importPath: "", importMaxFrames: "",
  };
}

/** "<TICKER> <step> ×<count>" (import: "<TICKER> import · <kind>"). */
export function defaultName(ticker: string, f: NewSeriesForm): string {
  if (f.mode === "import") return `${ticker} import · ${f.importKind}`;
  return `${ticker} ${STEP_LABELS[f.step]} ×${f.count}`;
}

/** datetime-local value → ISO with the browser's offset
 *  ("2026-09-08T15:45" → "2026-09-08T15:45:00-04:00"); null when blank or
 *  unparsable. */
export function localToIso(v: string): string | null {
  const s = v.trim();
  if (s === "") return null;
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return null;
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const p = (n: number) => String(Math.abs(n)).padStart(2, "0");
  const base = s.length === 16 ? `${s}:00` : s;
  return `${base}${sign}${p(Math.trunc(Math.abs(off) / 60))}:${p(Math.abs(off) % 60)}`;
}

function optionalInt(s: string): number | null {
  const t = s.trim();
  const n = Number(t);
  return t !== "" && Number.isInteger(n) && n > 0 ? n : null;
}

export function buildSpec(ticker: string, f: NewSeriesForm, lanes: LaneSpec[]): SeriesSpec {
  return {
    name: f.name.trim() || defaultName(ticker, f),
    ticker,
    tickers: [ticker],
    source: null, // the ticker's pinned source
    mode: f.mode,
    clock: {
      start: localToIso(f.start), end: null, step: f.step, count: f.count, sessionOnly: f.sessionOnly,
      timeOfDay: f.timeOfDay, tz: SERIES_TZ, warmupFrames: f.warmupFrames,
    },
    // pinned + [] = the backend pins the ticker's universe expiries at creation.
    ladder: { policy: f.policy, expiries: [], maxExpiries: optionalInt(f.maxExpiries) },
    fitMode: f.fitMode,
    lanes,
    note: f.note,
  };
}

export function buildImport(ticker: string, f: NewSeriesForm, lanes: LaneSpec[]): SeriesImportRequest {
  return {
    name: f.name.trim() || defaultName(ticker, f),
    ticker,
    source: { kind: f.importKind, path: f.importPath.trim() || null, maxFrames: optionalInt(f.importMaxFrames) },
    lanes,
    fitMode: f.fitMode,
    ladder: { policy: f.policy, expiries: [], maxExpiries: optionalInt(f.maxExpiries) },
    note: f.note,
  };
}

/** What blocks a submit, or null. */
export function validateForm(f: NewSeriesForm, lanes: LaneSpec[]): string | null {
  if (lanes.length === 0) return "Pick at least one lane.";
  if (!lanes.some((l) => l.production)) return "Pick a production lane.";
  if (lanes.some((l) => l.name.trim() === "")) return "Every lane needs a name.";
  if (f.mode !== "import") {
    if (!Number.isInteger(f.count) || f.count < 1 || f.count > MAX_FRAMES) return `Count must be between 1 and ${MAX_FRAMES}.`;
    if (!/^\d{2}:\d{2}$/.test(f.timeOfDay)) return "Time of day must be HH:MM.";
    if (!Number.isInteger(f.warmupFrames) || f.warmupFrames < 0 || f.warmupFrames > 64) return "Warm-up frames must be between 0 and 64.";
  }
  return null;
}

// ------------------------------------------------------------ lane edits

/** Check / uncheck a preset: presets order kept; the production star moves
 *  to the first lane when its holder leaves; a first lane is production. */
export function toggleLane(lanes: LaneSpec[], presets: LaneSpec[], preset: LaneSpec): LaneSpec[] {
  const on = lanes.some((l) => l.id === preset.id);
  const order = new Map(presets.map((p, i) => [p.id, i]));
  let next = on ? lanes.filter((l) => l.id !== preset.id) : [...lanes, { ...preset, production: false }];
  next = [...next].sort((a, b) => (order.get(a.id) ?? 0) - (order.get(b.id) ?? 0));
  if (next.length > 0 && !next.some((l) => l.production)) next = next.map((l, i) => ({ ...l, production: i === 0 }));
  return next;
}

export function setProduction(lanes: LaneSpec[], id: string): LaneSpec[] {
  return lanes.map((l) => ({ ...l, production: l.id === id }));
}

export function patchLane(lanes: LaneSpec[], id: string, patch: Partial<LaneSpec>): LaneSpec[] {
  return lanes.map((l) => (l.id === id ? { ...l, ...patch } : l));
}

/** The dialog's opening pick: the first two presets (the first = production). */
export function defaultLanes(presets: LaneSpec[]): LaneSpec[] {
  return presets.slice(0, 2).map((p, i) => ({ ...p, production: i === 0 }));
}
