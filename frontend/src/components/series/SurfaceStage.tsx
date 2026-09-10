// The Series lens's SURFACE stage (SERIES ARC S5, roadmap §3.4): every
// visible lane's σ(k, τ) sheet at the frame on the hand-rolled 3D mesh —
// one panel per lane in a responsive grid, all under ONE camera and ONE
// crop window (rotate or brush one, every sheet follows) with the linked
// crosshair — or, in the difference mode, the production lane's sheet
// beside a signed lane − production heatmap per other lane, drawn the way
// the Local Vol Compare tab draws its twin − affine difference (the
// diverging ramp symmetric about zero, ± legend in vol bp; its x axis reads
// K/F = e^k, so its hover links to the sheets in k). τ is the frame's own,
// so the sheets shrink frame by frame. While the next frame loads the LAST
// drawn frame stays under a veil, so fast playback never flashes empty.
import { useMemo, useRef } from "react";
import type { ReactNode } from "react";
import LocalVolHeatmap from "../LocalVolHeatmap";
import SurfaceMesh from "../SurfaceMesh";
import type { AxisMode } from "../../lib/axisModes";
import { laneLabel, laneStyle, productionLane, stageAxisMode } from "../../lib/seriesLanes";
import { differenceMeshData, formatSignedVolBp, laneSheets } from "../../lib/seriesSurface";
import type { LaneSheet } from "../../lib/seriesSurface";
import type { FramePayload, LaneSpec } from "../../lib/seriesTypes";
import type { SurfaceMeshData } from "../../lib/surfaceMesh";
import { chartMessageClass } from "../../lib/ui";

export type SurfaceStageMode = "sheets" | "difference";

interface SurfaceStageProps {
  frame: FramePayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  /** Keys the shared camera + crop window (`series:<id>`). */
  seriesId: string;
  /** The linked-hover ticker (every panel is one chart of it). */
  ticker: string;
  mode: SurfaceStageMode;
  /** The lens's axis word ("k" · "kf" · "strike"; the mesh's ids pass). */
  axisMode: string;
  loading: boolean;
}

/** Grid columns for n panels: 1 · 2 (two to four) · 3 (more). */
export function gridColumns(n: number): number {
  return n <= 1 ? 1 : n <= 4 ? 2 : 3;
}

/** A panel's caption: colour dot · text · optional tag. */
function Caption({ colour, text, tag }: { colour: string; text: string; tag?: string }) {
  return (
    <div className="mb-1 flex shrink-0 items-center gap-1.5 px-1 font-mono text-[10px] text-slate-500">
      <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: colour }} />
      <span className="truncate">{text}</span>
      {tag && <span className="rounded border border-slate-700 px-1 text-[9px] text-slate-400">{tag}</span>}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className={chartMessageClass} data-testid="series-stage-empty">{text}</div>;
}

interface SheetPanelProps {
  sheet: LaneSheet;
  /** The camera AND window key (one crop, one camera across the stage). */
  sharedKey: string;
  ticker: string;
  axisMode: AxisMode;
  compact: boolean;
  production: boolean;
}

/** One lane's σ(k, τ) sheet. */
function SheetPanel({ sheet, sharedKey, ticker, axisMode, compact, production }: SheetPanelProps) {
  const { lane, ordinal, mesh } = sheet;
  return (
    <div className="flex min-h-0 min-w-0 flex-col" data-testid="series-surface-sheet" data-lane={lane.id}>
      <Caption
        colour={laneStyle(lane, ordinal).colour}
        text={`${mesh.expiries.length} expiries · ${mesh.k.length} strikes`}
        tag={production ? "production" : undefined}
      />
      <SurfaceMesh
        data={mesh}
        legendLabel={`${laneLabel(lane)} σ(k, τ)`}
        axisMode={axisMode}
        cameraKey={sharedKey}
        windowKey={sharedKey}
        ticker={ticker}
        chartId={`series:${lane.id}`}
        compact={compact}
      />
    </div>
  );
}

interface DiffPanelProps {
  sheet: LaneSheet;
  /** lane − production on the common grid (null = no common grid). */
  diff: SurfaceMeshData | null;
  productionLabel: string;
  ticker: string;
}

/** One lane's signed difference to the production lane, as the Compare
 *  tab's diverging heatmap (x = K/F, so its hover links back in k = ln x). */
function DiffPanel({ sheet, diff, productionLabel, ticker }: DiffPanelProps) {
  const { lane, ordinal } = sheet;
  const xNodes = useMemo(() => diff?.k.map((k) => Math.exp(k)) ?? [], [diff]);
  const label = `${laneLabel(lane)} − ${productionLabel}`;
  return (
    <div className="flex min-h-0 min-w-0 flex-col" data-testid="series-surface-diff" data-lane={lane.id}>
      <Caption colour={laneStyle(lane, ordinal).colour} text={label} tag="signed · vol bp" />
      {diff !== null ? (
        <LocalVolHeatmap
          tNodes={diff.t}
          xNodes={xNodes}
          localVol={diff.vol}
          legendLabel={`σ ${label}`}
          cellLabel="cells"
          diverging
          formatValue={formatSignedVolBp}
          ticker={ticker}
          chartId={`series:${lane.id}:diff`}
        />
      ) : (
        <div className={chartMessageClass}>the two grids share fewer than two expiries or strikes</div>
      )}
    </div>
  );
}

export default function SurfaceStage({
  frame, lanes, hidden, seriesId, ticker, mode, axisMode, loading,
}: SurfaceStageProps) {
  // The last drawn frame stays under the veil while the next one loads.
  const lastRef = useRef<FramePayload | null>(null);
  if (frame !== null) lastRef.current = frame;
  const drawn = frame ?? (loading ? lastRef.current : null);

  const production = productionLane(lanes);
  const sheets = useMemo<LaneSheet[]>(
    () => (drawn === null ? [] : laneSheets(drawn, lanes, hidden)),
    [drawn, lanes, hidden],
  );
  const prodSheet = production !== null ? (sheets.find((s) => s.lane.id === production.id) ?? null) : null;
  // The difference mode's signed sheets, lane − production, on the common grid.
  const diffs = useMemo(() => {
    if (mode !== "difference" || prodSheet === null) return [];
    return sheets
      .filter((s) => s !== prodSheet)
      .map((s) => ({ sheet: s, diff: differenceMeshData(s.mesh, prodSheet.mesh) }));
  }, [mode, sheets, prodSheet]);

  if (drawn === null) return <Empty text={loading ? "loading frame…" : "no frame"} />;

  const sharedKey = `series:${seriesId}`;
  const meshAxis = stageAxisMode(axisMode);
  let panels: ReactNode[] = [];
  let empty: string | null = null;
  if (sheets.length === 0) {
    empty = "no surface at this frame";
  } else if (mode === "sheets") {
    panels = sheets.map((s) => (
      <SheetPanel key={s.lane.id} sheet={s} sharedKey={sharedKey} ticker={ticker} axisMode={meshAxis}
        compact={sheets.length > 1} production={s === prodSheet} />
    ));
  } else if (prodSheet === null) {
    empty = "the production lane has no surface at this frame";
  } else {
    const prodLabel = laneLabel(prodSheet.lane);
    panels = [
      <SheetPanel key={prodSheet.lane.id} sheet={prodSheet} sharedKey={sharedKey} ticker={ticker}
        axisMode={meshAxis} compact={diffs.length > 0} production />,
      ...diffs.map(({ sheet, diff }) => (
        <DiffPanel key={sheet.lane.id} sheet={sheet} diff={diff} productionLabel={prodLabel} ticker={ticker} />
      )),
    ];
    if (diffs.length === 0) {
      panels.push(
        <div key="none" className={chartMessageClass} data-testid="series-surface-nodiff">
          no other visible lane has a surface at this frame
        </div>,
      );
    }
  }
  const cols = gridColumns(panels.length);

  return (
    <div className="relative h-full min-h-0" data-testid="series-surface-stage" data-mode={mode}>
      {empty !== null ? (
        <Empty text={empty} />
      ) : (
        <div
          className="grid h-full min-h-0 gap-3"
          style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gridAutoRows: "minmax(0, 1fr)" }}
        >
          {panels}
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
