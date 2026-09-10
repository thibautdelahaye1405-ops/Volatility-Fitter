// Pure helpers of the Series lens's LANES stage (SERIES ARC S5): the strip's
// metrics as overlay-chart series (one per visible lane, frame-index x, a
// lane's missing fits break its line), the playhead drawn on that chart (a
// vertical two-point series + one marker per lane at the playhead's value),
// the evidence table's columns with the "best lane" rule, and the filter
// ring's cursor step for the playhead frame. No React — vitest-locked.
import type { OverlayMarker, OverlaySeries } from "../components/OverlayCurvesChart";
import { formatPct } from "./chartScale";
import { laneLabel, laneStyle } from "./seriesLanes";
import type { LaneEvidence, LaneSpec, StripMetric, StripPayload } from "./seriesTypes";

/** A strip metric or the ATM vol (carried beside the metrics on the strip). */
export type EvidenceMetric = StripMetric | "atmVol";

/** The metric chip order of the Lanes stage. */
export const EVIDENCE_METRICS: readonly EvidenceMetric[] = [
  "rmsBp", "maxIvBp", "pullAtmBp", "zetaAtm", "fitMs", "atmVol", "skew", "curvature",
];

const METRIC_LABELS: Record<EvidenceMetric, string> = {
  rmsBp: "rms bp",
  maxIvBp: "max err bp",
  pullAtmBp: "pull ATM bp",
  zetaAtm: "ζ ATM",
  fitMs: "fit ms",
  atmVol: "ATM σ",
  skew: "skew",
  curvature: "curvature",
};

const METRIC_DIGITS: Record<EvidenceMetric, number> = {
  rmsBp: 1, maxIvBp: 1, pullAtmBp: 1, zetaAtm: 2, fitMs: 0, atmVol: 1, skew: 3, curvature: 3,
};

/** The filmstrip's playhead violet (components/series/Filmstrip). */
export const PLAYHEAD_COLOUR = "rgb(167 139 250 / 0.95)";
export const PLAYHEAD_LABEL = "playhead";

/** The chip / axis label of a metric. */
export function metricLabel(metric: EvidenceMetric): string {
  return METRIC_LABELS[metric];
}

/** A metric value for a readout: the ATM vol as a percentage, the rest at
 *  the metric's own precision; "—" when null / non-finite. */
export function formatMetric(metric: EvidenceMetric, v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return metric === "atmVol" ? formatPct(v, METRIC_DIGITS.atmVol) : v.toFixed(METRIC_DIGITS[metric]);
}

/** One lane's per-frame values of a metric off the strip (empty when absent). */
export function metricValues(strip: StripPayload, metric: EvidenceMetric, laneId: string): (number | null)[] {
  return (metric === "atmVol" ? strip.atmVol[laneId] : strip.lanes[laneId]?.[metric]) ?? [];
}

export interface LaneOrdinal {
  lane: LaneSpec;
  ordinal: number;
}

type StyleOf = (lane: LaneSpec, ordinal: number) => { colour: string; dash: string };

/** One overlay series per lane: x = the frame's POSITION in the strip (the
 *  playback index), y = the metric (NaN where the lane has no fit, which
 *  breaks the line). The lane's colour + ordinal dash; a duplicated label
 *  carries the lane id (the chart keys its paths by label). */
export function stripSeries(
  strip: StripPayload,
  metric: EvidenceMetric,
  lanes: readonly LaneOrdinal[],
  style: StyleOf = laneStyle,
): OverlaySeries[] {
  const n = strip.idx.length;
  const labels = lanes.map(({ lane }) => laneLabel(lane));
  return lanes.map(({ lane, ordinal }, j) => {
    const values = metricValues(strip, metric, lane.id);
    const st = style(lane, ordinal);
    const duplicate = labels.some((l, k) => k !== j && l === labels[j]);
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < n; i++) {
      const v = values[i];
      xs.push(i);
      ys.push(v != null && Number.isFinite(v) ? v : Number.NaN);
    }
    return {
      label: duplicate ? `${labels[j]} (${lane.id})` : labels[j],
      xs,
      ys,
      color: st.colour,
      dash: st.dash !== "" ? st.dash : undefined,
    };
  });
}

/** The playhead as a vertical two-point series spanning the lanes' finite
 *  y-extent at `index` (null when nothing is finite — no line to anchor). */
export function playheadLine(index: number, series: readonly OverlaySeries[]): OverlaySeries | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const s of series) {
    for (const y of s.ys) {
      if (!Number.isFinite(y)) continue;
      if (y < lo) lo = y;
      if (y > hi) hi = y;
    }
  }
  if (!(lo <= hi)) return null;
  if (lo === hi) {
    const half = Math.max(Math.abs(lo) * 0.05, 1e-6);
    lo -= half;
    hi += half;
  }
  return { label: PLAYHEAD_LABEL, xs: [index, index], ys: [lo, hi], color: PLAYHEAD_COLOUR, dash: "3 3" };
}

/** One marker per lane series at the playhead: the lane's value at frame
 *  `index` (skipped where the lane has no fit there), titled "lane · value". */
export function playheadMarker(
  index: number,
  series: readonly OverlaySeries[],
  fmt: (v: number) => string = (v) => v.toFixed(2),
): OverlayMarker[] {
  const out: OverlayMarker[] = [];
  for (const s of series) {
    if (s.label === PLAYHEAD_LABEL) continue;
    const i = s.xs.indexOf(index);
    if (i < 0) continue;
    const y = s.ys[i];
    if (!Number.isFinite(y)) continue;
    out.push({ x: index, y, label: `${s.label} · ${fmt(y)}`, color: s.color });
  }
  return out;
}

/** The ring step the playhead sits on, matched by FRAME INDEX — the lane
 *  filter payload's `frameIdx[i]` is the series frame the i-th step was
 *  committed on (a step's `ts` is a local-clock epoch of a naive stamp, so
 *  steps are never matched to frames by clock): the step whose frameIdx is
 *  the playhead index, else the LAST step committed at or before it, else
 *  null (the ring starts after the frame). */
export function cursorStepIndex(frameIdx: readonly (number | null)[], index: number): number | null {
  let before: number | null = null;
  for (let i = 0; i < frameIdx.length; i++) {
    const f = frameIdx[i];
    if (f == null || !Number.isFinite(f)) continue;
    if (f === index) return i;
    if (f < index) before = i;
  }
  return before;
}

/** Fixed-point evidence number; "—" for null / non-finite. */
export function fmtEvidence(v: number | null | undefined, digits: number): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

/** A numeric column of the evidence table. `score` maps a value to "lower is
 *  better" (identity by default — every rms / roughness / cost column). */
export interface EvidenceColumn {
  key: Exclude<keyof LaneEvidence, "nFrames" | "nFailed" | "worstFrame">;
  label: string;
  title: string;
  digits: number;
  score?: (v: number) => number;
}

export const EVIDENCE_COLUMNS: readonly EvidenceColumn[] = [
  { key: "meanRmsBp", label: "mean rms bp", title: "mean rms of the fit to the quotes over the ready frames (vol bp)", digits: 1 },
  { key: "meanMaxIvBp", label: "mean max bp", title: "mean of the worst quote error per frame (vol bp)", digits: 1 },
  { key: "roughnessAtmBp", label: "rough. ATM bp", title: "mean |Δ σ_atm| between consecutive frames (vol bp)", digits: 1 },
  { key: "roughnessSkew", label: "rough. skew", title: "mean |Δ skew| between consecutive frames", digits: 4 },
  { key: "meanAbsPullAtmBp", label: "mean |pull| bp", title: "mean |ATM pull| of the prior / filter (vol bp)", digits: 1 },
  { key: "zetaAtmStd", label: "ζ ATM std", title: "std of the ATM standardized innovation — 1 is a healthy Q", digits: 2, score: (v) => Math.abs(v - 1) },
  { key: "meanFitMs", label: "mean fit ms", title: "mean wall time of one frame's fit", digits: 0 },
];

/** The lane with the best value of a column among `laneIds` — null unless at
 *  least two lanes carry a finite value (one row has nothing to beat). */
export function bestLane(
  evidence: Record<string, LaneEvidence>,
  laneIds: readonly string[],
  col: EvidenceColumn,
): string | null {
  const score = col.score ?? ((v: number) => v);
  let best: string | null = null;
  let bestScore = Infinity;
  let finite = 0;
  for (const id of laneIds) {
    const v = evidence[id]?.[col.key];
    if (v == null || !Number.isFinite(v)) continue;
    finite += 1;
    const s = score(v);
    if (s < bestScore) {
      bestScore = s;
      best = id;
    }
  }
  return finite >= 2 ? best : null;
}
