// Lane presentation helpers of the Series lens (roadmap §3.4): a lane is
// one model configuration calibrated on every frame; the Smile stage
// overlays every visible lane's curve, the filmstrip its metrics. Colour =
// the lane's own when set, else its FAMILY colour (lib/modelColor — LQD
// green / SVI blue / MCS violet; Local Vol gets orange here, the family
// the Compare palette does not carry); dash = the lane's ORDINAL among the
// series' lanes (stable when lanes are hidden), on the lib/anchoring dash
// vocabulary. Pure — no React.
import { MODEL_COLORS, MODEL_LABELS } from "./modelColor";
import type { SmilePoint } from "./mockData";
import type { FramePayload, LaneFamily, LaneSpec, SliceCurveDoc } from "./seriesTypes";
import type { AxisMode } from "./axisModes";

/** Local Vol's lane colour (tailwind orange-500) — distinct from the three
 *  parametric families and from the teal filter / violet graph overlays. */
export const LV_COLOUR = "#f97316";

/** Stroke dashes by lane ordinal: solid, dashed, dotted, dash-dot, cycling. */
export const LANE_DASHES: readonly string[] = ["", "6 3", "2 2", "8 3 2 3"];

const FAMILY_LABELS: Record<LaneFamily, string> = {
  lqd: MODEL_LABELS.lqd,
  svi: MODEL_LABELS.svi,
  sigmoid: MODEL_LABELS.sigmoid,
  lv: "Local Vol",
};

/** The family's colour (the Compare palette, plus orange for Local Vol). */
export function familyColour(family: LaneFamily): string {
  return family === "lv" ? LV_COLOUR : MODEL_COLORS[family];
}

/** Stroke colour + dash of a lane drawn at ordinal `index` among the lanes. */
export function laneStyle(lane: LaneSpec, index: number): { colour: string; dash: string } {
  const own = lane.colour?.trim() ?? "";
  const n = LANE_DASHES.length;
  const ordinal = Number.isFinite(index) ? ((Math.trunc(index) % n) + n) % n : 0;
  return { colour: own !== "" ? own : familyColour(lane.family), dash: LANE_DASHES[ordinal] };
}

/** The lane's display name: its name, else "<family> · <id>". */
export function laneLabel(lane: LaneSpec): string {
  const name = lane.name.trim();
  return name !== "" ? name : `${FAMILY_LABELS[lane.family]} · ${lane.id}`;
}

/** The lane's slice at an expiry in a frame, or null. */
export function laneSlice(frame: FramePayload, laneId: string, expiry: string): SliceCurveDoc | null {
  const lane = frame.lanes[laneId];
  if (!lane) return null;
  return lane.slices.find((s) => s.expiry === expiry) ?? null;
}

/** The lane's curve at an expiry as chart points ({k, vol}); empty when the
 *  lane, the slice or a finite pair is absent. */
export function laneCurve(frame: FramePayload, laneId: string, expiry: string): SmilePoint[] {
  const slice = laneSlice(frame, laneId, expiry);
  if (!slice) return [];
  const n = Math.min(slice.k.length, slice.iv.length);
  const out: SmilePoint[] = [];
  for (let i = 0; i < n; i++) {
    const k = slice.k[i];
    const vol = slice.iv[i];
    if (Number.isFinite(k) && Number.isFinite(vol)) out.push({ k, vol });
  }
  return out;
}

/** A slice metric as a finite number, else null. */
export function sliceMetric(slice: SliceCurveDoc | null, name: string): number | null {
  const v = slice?.metrics[name];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** The expiry the stage shows: `wanted` when the frame carries it, else the
 *  nearest LATER expiry (the node's expiry has rolled off — roll forward),
 *  else the last; the FIRST expiry when nothing is wanted; null when the
 *  frame has none. */
export function nearestExpiry(frame: FramePayload, wanted: string | null): string | null {
  const expiries = [...frame.expiries].sort();
  if (expiries.length === 0) return null;
  if (wanted === null || wanted === "") return expiries[0];
  if (expiries.includes(wanted)) return wanted;
  const later = expiries.find((e) => e > wanted);
  return later ?? expiries[expiries.length - 1];
}

/** The production lane (the starred one), else the first lane, else null. */
export function productionLane(lanes: readonly LaneSpec[]): LaneSpec | null {
  return lanes.find((l) => l.production) ?? lanes[0] ?? null;
}

/** The lanes to draw: the ones not hidden, each with its ordinal among ALL
 *  lanes (so a lane keeps its dash when its neighbours are hidden). */
export function visibleLanes(
  lanes: readonly LaneSpec[],
  hidden: ReadonlySet<string>,
): { lane: LaneSpec; ordinal: number }[] {
  const out: { lane: LaneSpec; ordinal: number }[] = [];
  lanes.forEach((lane, ordinal) => {
    if (!hidden.has(lane.id)) out.push({ lane, ordinal });
  });
  return out;
}

/** The Series lens's axis vocabulary → the chart's AxisMode: "k" (log-
 *  moneyness), "kf" / "K/F" (% of forward) and "strike" (the FIXED-strike
 *  reading through time); the chart's own ids pass through; anything else
 *  reads as log-moneyness. */
export function stageAxisMode(mode: string | null | undefined): AxisMode {
  switch ((mode ?? "").trim().toLowerCase()) {
    case "strike":
    case "fixed":
    case "fixedstrike":
    case "fixed_strike":
    case "fixed-strike":
      return "strike";
    case "kf":
    case "k/f":
    case "pctatm":
      return "pctatm";
    case "delta":
      return "delta";
    case "normalized":
      return "normalized";
    case "lognormalized":
      return "lognormalized";
    default:
      return "logmoneyness";
  }
}
