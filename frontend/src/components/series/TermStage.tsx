// The Series lens's TERM stage (SERIES ARC S5, roadmap §3.4): the frame's
// term structure on the live Term chart — the PRODUCTION lane's per-expiry
// ATM / var-swap vols as the chart's points and its dense curve
// (lib/seriesTerm, the live endpoint's own variance rule), every other
// visible lane through the chart's `lanes` slot (family colour, ordinal
// dash: ATM polylines + markers, var-swap thinner and dashed), the node
// tab's expiry highlighted (rolled forward when it has left the ladder). A
// series carries no event calendar: no events, the calendar clock, no
// dividends. The footer legend reads every visible lane's ATM / var-swap
// vol at the shown expiry. While the next frame loads the LAST drawn frame
// stays under a veil.
import { useMemo, useRef } from "react";
import TermChart from "../TermChart";
import type { TermLane } from "../TermChart";
import { formatPct } from "../../lib/chartScale";
import { laneLabel, laneStyle, nearestExpiry, productionLane, visibleLanes } from "../../lib/seriesLanes";
import { laneTermSeries, productionTermChart } from "../../lib/seriesTerm";
import type { FramePayload, LaneSpec } from "../../lib/seriesTypes";
import { chartMessageClass } from "../../lib/ui";

interface TermStageProps {
  frame: FramePayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  /** The node tab's expiry (highlighted; rolled forward when the frame lacks it). */
  expiry: string | null;
  loading: boolean;
}

export default function TermStage({ frame, lanes, hidden, expiry, loading }: TermStageProps) {
  // The last drawn frame stays under the veil while the next one loads.
  const lastRef = useRef<FramePayload | null>(null);
  if (frame !== null) lastRef.current = frame;
  const drawn = frame ?? (loading ? lastRef.current : null);

  const production = productionLane(lanes);
  const shownExpiry = drawn !== null ? nearestExpiry(drawn, expiry) : null;

  const chart = useMemo(
    () => (drawn !== null && production !== null ? productionTermChart(drawn, production.id) : null),
    [drawn, production],
  );
  // The chart's lanes slot: every other visible lane with a term point.
  const termLanes = useMemo<TermLane[]>(() => {
    if (drawn === null) return [];
    const out: TermLane[] = [];
    for (const { lane, ordinal } of visibleLanes(lanes, hidden)) {
      if (production !== null && lane.id === production.id) continue;
      const points = laneTermSeries(drawn, lane.id);
      if (points.length === 0) continue;
      const st = laneStyle(lane, ordinal);
      out.push({ id: lane.id, label: laneLabel(lane), colour: st.colour, dash: st.dash, points });
    }
    return out;
  }, [drawn, lanes, hidden, production]);
  // Footer legend: every visible lane's ATM / var-swap vol at the shown expiry.
  const legend = useMemo(() => {
    if (drawn === null) return [];
    return visibleLanes(lanes, hidden).map(({ lane, ordinal }) => {
      const p = laneTermSeries(drawn, lane.id).find((q) => q.expiry === shownExpiry) ?? null;
      return {
        lane, style: laneStyle(lane, ordinal), atmVol: p?.atmVol ?? null, varSwapVol: p?.varSwapVol ?? null,
        status: drawn.lanes[lane.id]?.status ?? null,
      };
    });
  }, [drawn, lanes, hidden, shownExpiry]);

  if (drawn === null) {
    return (
      <div className={chartMessageClass} data-testid="series-stage-empty">
        {loading ? "loading frame…" : "no frame"}
      </div>
    );
  }

  return (
    <div className="relative flex h-full min-h-0 flex-col" data-testid="series-term-stage" data-expiry={shownExpiry ?? undefined}>
      <div className="min-h-0 flex-1">
        {chart === null ? (
          <div className={chartMessageClass} data-testid="series-stage-empty">no term structure at this frame</div>
        ) : (
          <TermChart
            points={chart.points}
            curve={chart.curve}
            events={[]}
            eventsEnabled={false}
            axisClock="real"
            dividends={[]}
            selectedExpiry={shownExpiry}
            lanes={termLanes}
          />
        )}
      </div>
      {/* Lane legend: swatch · name · ATM / var-swap vol at the shown expiry */}
      {legend.length > 0 && (
        <div className="mt-1 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-0.5 px-1 font-mono text-[9px] text-slate-300" data-testid="series-lane-legend">
          {legend.map(({ lane, style, atmVol, varSwapVol, status }) => (
            <span key={lane.id} className="flex items-center gap-1.5" data-lane-row={lane.id}>
              <svg width={16} height={6} aria-hidden="true">
                <line x1={0} x2={16} y1={3} y2={3} stroke={style.colour} strokeWidth={2} strokeDasharray={style.dash || undefined} />
              </svg>
              <span className={production !== null && lane.id === production.id ? "text-slate-100" : ""}>{laneLabel(lane)}</span>
              <span className="text-slate-500">
                {atmVol !== null ? `ATM ${formatPct(atmVol)}` : status === "done" ? "—" : (status ?? "—")}
                {varSwapVol !== null ? ` · VS ${formatPct(varSwapVol)}` : ""}
              </span>
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
