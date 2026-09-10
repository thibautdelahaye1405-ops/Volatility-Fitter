// The Lanes stage's evidence table (SERIES ARC S5): one row per visible lane
// — swatch + name (★ production), frames n / failed, the numeric evidence
// columns (lib/seriesEvidence.EVIDENCE_COLUMNS) with the best lane per
// column lit, and the worst frame (idx · instant · rms) whose click scrubs
// the transport there. A caption says what roughness measures. Pure
// presentation: the evidence payload comes from the stage.
import { useMemo } from "react";
import { bestLane, EVIDENCE_COLUMNS, fmtEvidence } from "../../lib/seriesEvidence";
import type { LaneOrdinal } from "../../lib/seriesEvidence";
import { formatFrameInstant } from "../../lib/seriesPlayback";
import { laneLabel, laneStyle } from "../../lib/seriesLanes";
import type { EvidencePayload, LaneEvidence, LaneSpec } from "../../lib/seriesTypes";

interface LanesTableProps {
  evidence: EvidencePayload | null;
  lanes: LaneOrdinal[];
  production: LaneSpec | null;
  onScrub: (idx: number) => void;
}

const th = "px-2 py-1 font-medium whitespace-nowrap";
const td = "px-2 py-1 whitespace-nowrap";
const BEST = "text-emerald-300";

export const ROUGHNESS_CAPTION =
  "Roughness = the mean frame-to-frame move of the ATM vol / skew — what a prior or a filter damps, at the rms cost beside it.";

function WorstCell({ worst, onScrub }: { worst: LaneEvidence["worstFrame"]; onScrub: (idx: number) => void }) {
  if (worst === null) return <td className={`${td} text-slate-600`}>—</td>;
  return (
    <td className={td}>
      <button
        type="button"
        className="rounded px-1 text-slate-300 underline decoration-slate-600 decoration-dotted underline-offset-2 hover:bg-slate-800/60 hover:text-slate-100"
        title={`jump to frame ${worst.idx} (${formatFrameInstant(worst.ts)})`}
        onClick={() => onScrub(worst.idx)}
        data-testid={`worst-frame-${worst.idx}`}
      >
        #{worst.idx} · {formatFrameInstant(worst.ts).slice(0, 16)} · {worst.rmsBp.toFixed(1)} bp
      </button>
    </td>
  );
}

export default function LanesTable({ evidence, lanes, production, onScrub }: LanesTableProps) {
  const laneIds = useMemo(() => lanes.map(({ lane }) => lane.id), [lanes]);
  const best = useMemo(() => {
    const out = new Map<string, string | null>();
    if (evidence !== null) for (const col of EVIDENCE_COLUMNS) out.set(col.key, bestLane(evidence.lanes, laneIds, col));
    return out;
  }, [evidence, laneIds]);

  if (lanes.length === 0) {
    return <div className="py-3 text-center text-xs text-slate-500">Every lane is hidden — show one with its chip above.</div>;
  }
  return (
    <div className="overflow-auto" data-testid="lanes-table">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead className="text-[10px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className={th}>Lane</th>
            <th className={th} title="ready frames fitted / failed fits">Frames</th>
            <th className={th} title="mean rms of the fit to the quotes (vol bp)">Mean rms bp</th>
            <th className={th} title="mean of the worst quote error per frame (vol bp)">Mean max bp</th>
            <th className={th} title="the frame with the largest rms — click to jump there">Worst frame</th>
            {EVIDENCE_COLUMNS.filter((c) => c.key !== "meanRmsBp" && c.key !== "meanMaxIvBp").map((c) => (
              <th key={c.key} className={th} title={c.title}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {lanes.map(({ lane, ordinal }) => {
            const ev = evidence?.lanes[lane.id] ?? null;
            const st = laneStyle(lane, ordinal);
            const isProd = production !== null && lane.id === production.id;
            const cell = (key: (typeof EVIDENCE_COLUMNS)[number]["key"], digits: number) => (
              <td key={key} className={`${td} ${best.get(key) === lane.id ? BEST : ""}`} data-col={key}>
                {fmtEvidence(ev?.[key], digits)}
              </td>
            );
            return (
              <tr key={lane.id} className="border-t border-slate-800/60 font-mono text-slate-300" data-lane-row={lane.id}>
                <td className={`${td} font-sans`}>
                  <span className="flex items-center gap-1.5">
                    <svg width={16} height={6} aria-hidden="true">
                      <line x1={0} x2={16} y1={3} y2={3} stroke={st.colour} strokeWidth={2} strokeDasharray={st.dash || undefined} />
                    </svg>
                    <span className={isProd ? "text-slate-100" : ""}>{laneLabel(lane)}</span>
                    {isProd && <span className="text-amber-400" aria-label="production lane">★</span>}
                  </span>
                </td>
                <td className={td}>
                  {ev === null ? "—" : (
                    <>
                      {ev.nFrames}
                      {ev.nFailed > 0 && <span className="text-rose-400"> / {ev.nFailed} failed</span>}
                    </>
                  )}
                </td>
                {cell("meanRmsBp", 1)}
                {cell("meanMaxIvBp", 1)}
                <WorstCell worst={ev?.worstFrame ?? null} onScrub={onScrub} />
                {EVIDENCE_COLUMNS.filter((c) => c.key !== "meanRmsBp" && c.key !== "meanMaxIvBp").map((c) => cell(c.key, c.digits))}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-1.5 px-2 text-[10px] leading-snug text-slate-500" data-testid="roughness-caption">
        {ROUGHNESS_CAPTION}
        {evidence === null && <span className="ml-1 text-slate-600">Reading the evidence…</span>}
      </p>
    </div>
  );
}
