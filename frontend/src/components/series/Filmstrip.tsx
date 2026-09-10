// The Series filmstrip (roadmap §3.4): three stacked sparklines over ALL
// frames — spot, the shown expiry's ATM vol per visible lane, rms bp per
// visible lane — the playhead line crossing them; click / drag scrubs,
// hover badges the instant and its values. Frame-index-linear x (like the
// scrubber); a lane's missing fits break its line (lib/filmstrip is pure
// and vitest-locked). The rows share one measured SVG so the playhead is a
// single line; the labels sit in a gutter to the left.
import { useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useElementSize } from "../../lib/useElementSize";
import { nearestIndex, sparkPath, valueAt, xOf, yScale } from "../../lib/filmstrip";
import { laneLabel, laneStyle, visibleLanes } from "../../lib/seriesLanes";
import { formatFrameInstant } from "../../lib/seriesPlayback";
import { formatPct } from "../../lib/chartScale";
import type { LaneSpec, StripPayload } from "../../lib/seriesTypes";

interface FilmstripProps {
  strip: StripPayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  index: number;
  onScrub: (idx: number) => void;
}

export const ROW_H = 28;
const ROWS = 3;
const GUTTER_W = 44;
export const FILMSTRIP_H = ROW_H * ROWS;
const ROW_LABELS = ["spot", "ATM σ", "rms bp"] as const;

export default function Filmstrip({ strip, lanes, hidden, index, onScrub }: FilmstripProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const dragging = useRef(false);
  const shown = useMemo(() => visibleLanes(lanes, hidden), [lanes, hidden]);
  const n = strip?.idx.length ?? 0;
  const width = size.width;

  // Row scales: pooled across the visible lanes so the lanes are comparable.
  const spotScale = useMemo(() => yScale(strip?.spot ?? []), [strip]);
  const atmScale = useMemo(
    () => yScale(shown.flatMap(({ lane }) => strip?.atmVol[lane.id] ?? [])),
    [strip, shown],
  );
  const rmsScale = useMemo(
    () => yScale(shown.flatMap(({ lane }) => strip?.lanes[lane.id]?.rmsBp ?? [])),
    [strip, shown],
  );

  const idxAt = (e: ReactPointerEvent<SVGSVGElement>): number | null => {
    const svg = svgRef.current;
    if (!svg || n === 0) return null;
    const rect = svg.getBoundingClientRect();
    return nearestIndex(e.clientX - rect.left, n, rect.width);
  };
  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    const i = idxAt(e);
    if (i === null) return;
    dragging.current = true;
    e.currentTarget.setPointerCapture?.(e.pointerId);
    onScrub(i);
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const i = idxAt(e);
    setHover(i);
    if (dragging.current && i !== null) onScrub(i);
  };
  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    dragging.current = false;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
  };
  const onPointerLeave = () => {
    dragging.current = false;
    setHover(null);
  };

  const badge = hover !== null && strip !== null ? badgeText(strip, shown, hover) : null;
  const playX = n > 0 ? xOf(Math.min(n - 1, Math.max(0, index)), n, width) : null;

  return (
    <div className="flex w-full items-stretch" style={{ height: FILMSTRIP_H }} data-testid="series-filmstrip">
      <div className="flex shrink-0 flex-col" style={{ width: GUTTER_W }}>
        {ROW_LABELS.map((label) => (
          <span key={label} className="flex items-center font-mono text-[9px] text-slate-600" style={{ height: ROW_H }}>
            {label}
          </span>
        ))}
      </div>
      <div ref={ref} className="relative min-w-0 flex-1">
        {strip === null || n === 0 ? (
          <div className="flex h-full items-center justify-center text-[10px] text-slate-600">
            {strip === null ? "no filmstrip" : "no frames"}
          </div>
        ) : (
          width > 0 && (
            <svg
              ref={svgRef}
              width={width}
              height={FILMSTRIP_H}
              className="block cursor-crosshair touch-none select-none"
              role="img"
              aria-label="Filmstrip — spot, ATM vol and rms across the frames"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerLeave={onPointerLeave}
            >
              {/* Row separators */}
              {[1, 2].map((r) => (
                <line key={r} x1={0} x2={width} y1={r * ROW_H} y2={r * ROW_H} stroke="rgb(255 255 255 / 0.06)" />
              ))}
              {/* Row 1: spot */}
              <path d={sparkPath(strip.spot, spotScale, width, ROW_H - 4)} transform="translate(0,2)" fill="none" stroke="rgb(148 163 184 / 0.9)" strokeWidth={1.25} data-row="spot" />
              {/* Row 2: ATM vol per visible lane */}
              <g transform={`translate(0,${ROW_H + 2})`}>
                {shown.map(({ lane, ordinal }) => {
                  const st = laneStyle(lane, ordinal);
                  return (
                    <path key={lane.id} d={sparkPath(strip.atmVol[lane.id] ?? [], atmScale, width, ROW_H - 4)} fill="none" stroke={st.colour} strokeWidth={1.25} strokeDasharray={st.dash || undefined} data-row="atm" data-lane={lane.id} />
                  );
                })}
              </g>
              {/* Row 3: rms bp per visible lane */}
              <g transform={`translate(0,${2 * ROW_H + 2})`}>
                {shown.map(({ lane, ordinal }) => {
                  const st = laneStyle(lane, ordinal);
                  return (
                    <path key={lane.id} d={sparkPath(strip.lanes[lane.id]?.rmsBp ?? [], rmsScale, width, ROW_H - 4)} fill="none" stroke={st.colour} strokeWidth={1.25} strokeDasharray={st.dash || undefined} data-row="rms" data-lane={lane.id} />
                  );
                })}
              </g>
              {/* Hover guide + the playhead */}
              {hover !== null && (
                <line x1={xOf(hover, n, width)} x2={xOf(hover, n, width)} y1={0} y2={FILMSTRIP_H} stroke="rgb(148 163 184 / 0.35)" strokeDasharray="3 3" pointerEvents="none" />
              )}
              {playX !== null && (
                <line x1={playX} x2={playX} y1={0} y2={FILMSTRIP_H} stroke="rgb(167 139 250 / 0.95)" strokeWidth={1.5} pointerEvents="none" data-testid="filmstrip-playhead" />
              )}
            </svg>
          )
        )}
        {badge !== null && (
          <div className="pointer-events-none absolute top-0.5 right-1 rounded border border-slate-700 bg-surface-800/95 px-1.5 py-0.5 font-mono text-[9px] text-slate-200 shadow" data-testid="filmstrip-badge">
            {badge}
          </div>
        )}
      </div>
    </div>
  );
}

/** "2026-09-08 15:45 UTC · S 512.30 · LQD σ 18.2% · 4.1 bp · SVI …" */
export function badgeText(strip: StripPayload, shown: { lane: LaneSpec }[], i: number): string {
  const parts = [formatFrameInstant(strip.ts[i])];
  const spot = valueAt(strip.spot, i);
  if (spot !== null) parts.push(`S ${spot.toFixed(2)}`);
  for (const { lane } of shown) {
    const atm = valueAt(strip.atmVol[lane.id], i);
    const rms = valueAt(strip.lanes[lane.id]?.rmsBp, i);
    if (atm === null && rms === null) continue;
    const bits = [laneLabel(lane)];
    if (atm !== null) bits.push(`σ ${formatPct(atm, 1)}`);
    if (rms !== null) bits.push(`${rms.toFixed(1)} bp`);
    parts.push(bits.join(" "));
  }
  return parts.join(" · ");
}
