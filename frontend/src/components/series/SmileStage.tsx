// The Series lens's SMILE stage (roadmap §3.4): the frame's quotes drawn as
// bands by the fit target, the PRODUCTION lane's curve as the chart's fit
// line, every other visible lane through the chart's new `lanes` slot
// (family colour, ordinal dash) and the production lane's ghost trail —
// real previous frames, fading with age; nothing between frames is
// interpolated. The expiry is the node tab's, rolled forward when it has
// left the ladder (lib/seriesLanes.nearestExpiry); the k-window brush and
// the wheel zoom are the chart's own and persist across frames through the
// controlled `kWindow`. While the next frame loads the LAST drawn frame
// stays under a veil, so fast playback never flashes an empty chart.
import { useMemo, useRef } from "react";
import SmileChart from "../SmileChart";
import type { LaneCurve } from "../SmileChart";
import type { MarketFrame } from "../../lib/smileLayers";
import type { SmilePoint } from "../../lib/mockData";
import {
  laneCurve,
  laneLabel,
  laneSlice,
  laneStyle,
  nearestExpiry,
  productionLane,
  sliceMetric,
  stageAxisMode,
  visibleLanes,
} from "../../lib/seriesLanes";
import type { FitMode, FramePayload, LaneSpec } from "../../lib/seriesTypes";

interface SmileStageProps {
  frame: FramePayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  /** The node tab's expiry (rolled forward when the frame lacks it). */
  expiry: string | null;
  /** The lens's axis word ("k" · "kf" · "strike"; the chart's ids pass). */
  axisMode: string;
  /** The persisted k-window (null = the quotes' range padded 5 %). */
  kWindow: [number, number] | null;
  onKWindowChange: (w: [number, number]) => void;
  /** The production lane's curves at the previous frames, newest first. */
  ghostCurves: SmilePoint[][];
  fitMode: FitMode;
  loading: boolean;
}

/** Ghost opacity by age (0 = the previous frame): 0.35, 0.28, … ≥ 0.07. */
export function ghostOpacity(n: number): number {
  return Math.max(0.07, 0.35 - 0.07 * n);
}

/** [lo, hi] of the finite k's over the quotes and curves (null when none). */
function kExtent(...runs: readonly { k: number }[][]): [number, number] | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const run of runs) for (const p of run) if (Number.isFinite(p.k)) { lo = Math.min(lo, p.k); hi = Math.max(hi, p.k); }
  return Number.isFinite(lo) && hi > lo ? [lo, hi] : null;
}

/** The default k-window: the quotes' range padded 5 % of its span (the
 *  curves' range when there are no quotes; ±0.5 when nothing at all). */
export function defaultKWindow(quotesK: { k: number }[], curves: SmilePoint[][]): [number, number] {
  const q = kExtent(quotesK) ?? kExtent(...curves);
  if (q === null) return [-0.5, 0.5];
  const pad = (q[1] - q[0]) * 0.05;
  return [q[0] - pad, q[1] + pad];
}

/** Keep a persisted window inside the brushable extent; the default when
 *  it does not overlap (another ticker's window). */
export function clampKWindow(win: [number, number] | null, full: [number, number], fallback: [number, number]): [number, number] {
  if (win === null) return fallback;
  const lo = Math.max(full[0], Math.min(win[0], win[1]));
  const hi = Math.min(full[1], Math.max(win[0], win[1]));
  return hi > lo ? [lo, hi] : fallback;
}

export default function SmileStage({
  frame, lanes, hidden, expiry, axisMode, kWindow, onKWindowChange, ghostCurves, fitMode, loading,
}: SmileStageProps) {
  // The last drawn frame stays under the veil while the next one loads.
  const lastRef = useRef<FramePayload | null>(null);
  if (frame !== null) lastRef.current = frame;
  const drawn = frame ?? (loading ? lastRef.current : null);

  const production = productionLane(lanes);
  const shownExpiry = drawn !== null ? nearestExpiry(drawn, expiry) : null;
  const m = drawn !== null && shownExpiry !== null ? (drawn.market[shownExpiry] ?? null) : null;

  const productionCurve = useMemo(
    () => (drawn !== null && shownExpiry !== null && production !== null ? laneCurve(drawn, production.id, shownExpiry) : []),
    [drawn, shownExpiry, production],
  );
  const productionStyle = production !== null ? laneStyle(production, Math.max(0, lanes.indexOf(production))) : null;

  // The chart's lanes slot: ghosts first (faintest), then the other lanes.
  const overlays = useMemo<LaneCurve[]>(() => {
    if (drawn === null || shownExpiry === null) return [];
    const out: LaneCurve[] = ghostCurves.map((points, n) => ({
      id: `ghost-${n}`, label: "", points, colour: productionStyle?.colour ?? "#94a3b8", dash: "", width: 1, opacity: ghostOpacity(n),
    }));
    for (const { lane, ordinal } of visibleLanes(lanes, hidden)) {
      if (production !== null && lane.id === production.id) continue;
      const st = laneStyle(lane, ordinal);
      out.push({ id: lane.id, label: laneLabel(lane), points: laneCurve(drawn, lane.id, shownExpiry), colour: st.colour, dash: st.dash, width: 1.5, opacity: 1 });
    }
    return out;
  }, [drawn, shownExpiry, ghostCurves, lanes, hidden, production, productionStyle?.colour]);

  // Legend rows: every visible lane (production included) with its rms bp.
  const legend = useMemo(() => {
    if (drawn === null || shownExpiry === null) return [];
    return visibleLanes(lanes, hidden).map(({ lane, ordinal }) => ({
      lane, style: laneStyle(lane, ordinal),
      rmsBp: sliceMetric(laneSlice(drawn, lane.id, shownExpiry), "rmsBp"),
      status: drawn.lanes[lane.id]?.status ?? null,
    }));
  }, [drawn, shownExpiry, lanes, hidden]);

  const quotes = m?.quotes ?? [];
  const fallbackWin = useMemo(
    () => defaultKWindow(quotes, [productionCurve, ...overlays.map((o) => o.points)]),
    [quotes, productionCurve, overlays],
  );
  const fullRange = useMemo<[number, number]>(() => {
    const ext = kExtent(quotes, productionCurve, ...overlays.map((o) => o.points));
    const base = ext ?? fallbackWin;
    return [Math.min(base[0], fallbackWin[0]), Math.max(base[1], fallbackWin[1])];
  }, [quotes, productionCurve, overlays, fallbackWin]);
  const win = clampKWindow(kWindow, fullRange, fallbackWin);

  if (drawn === null || m === null || shownExpiry === null) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-500" data-testid="series-stage-empty">
        {loading ? "loading frame…" : "no frame"}
      </div>
    );
  }

  const market: MarketFrame = {
    forward: m.forward, quotes: m.quotes, model: productionCurve, inferred: null,
    live: false, warming: false, spot: m.spot, timestamp: drawn.ts,
  };
  const atmVol = production !== null ? (laneSlice(drawn, production.id, shownExpiry)?.atmVol ?? undefined) : undefined;

  return (
    <div className="relative h-full min-h-0" data-testid="series-smile-stage" data-expiry={shownExpiry}>
      <SmileChart
        market={market}
        calib={null}
        prior={[]}
        quoteKind={drawn.quoteKind === "marks" ? "marks" : "quotes"}
        kWindow={win}
        onKWindowChange={onKWindowChange}
        fullRange={fullRange}
        axisMode={stageAxisMode(axisMode)}
        t={m.t}
        atmVol={atmVol}
        fitMode={fitMode}
        showTarget
        lanes={overlays}
      />
      {/* Lane legend: swatch · name · this expiry's rms bp */}
      {legend.length > 0 && (
        <div className="pointer-events-none absolute right-3 top-9 flex flex-col gap-0.5 rounded border border-slate-800 bg-surface-900/80 px-1.5 py-1 font-mono text-[9px] text-slate-300" data-testid="series-lane-legend">
          {legend.map(({ lane, style, rmsBp, status }) => (
            <span key={lane.id} className="flex items-center gap-1.5">
              <svg width={16} height={6} aria-hidden="true">
                <line x1={0} x2={16} y1={3} y2={3} stroke={style.colour} strokeWidth={2} strokeDasharray={style.dash || undefined} />
              </svg>
              <span className={production !== null && lane.id === production.id ? "text-slate-100" : ""}>{laneLabel(lane)}</span>
              <span className="text-slate-500">{rmsBp !== null ? `${rmsBp.toFixed(1)} bp` : status === "done" ? "—" : (status ?? "—")}</span>
            </span>
          ))}
        </div>
      )}
      {/* Loading veil: the last frame stays visible underneath */}
      {loading && (
        <div className="pointer-events-none absolute inset-0 flex items-start justify-center bg-surface-900/30 pt-8" data-testid="series-stage-loading">
          <span className="rounded border border-slate-700 bg-surface-800/90 px-2 py-0.5 text-[10px] text-slate-400">loading frame…</span>
        </div>
      )}
    </div>
  );
}
