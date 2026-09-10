// Lane composer of the New series… dialog (SERIES ARC S4 §3.1 / §3.3): the
// presets as a checkbox list (name · family badge); a checked lane shows its
// colour swatch (blank = the family colour), a colour field, a rename field
// and the production radio (exactly one). The list of LaneSpec is owned by
// the dialog; the edits are the pure helpers of newSeriesSpec.ts.
import type { LaneSpec } from "../../lib/seriesTypes";
import { laneStyle } from "../../lib/seriesLanes";
import { patchLane, setProduction, toggleLane } from "./newSeriesSpec";

const FAMILY_LABEL: Record<LaneSpec["family"], string> = { lqd: "LQD", svi: "SVI-JW", sigmoid: "MCS", lv: "LV" };
const inputClass =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[11px] text-slate-200 outline-none focus:border-accent-500";

export interface LaneComposerProps {
  presets: LaneSpec[];
  loading: boolean;
  error: string | null;
  lanes: LaneSpec[];
  onChange: (lanes: LaneSpec[]) => void;
}

export default function LaneComposer({ presets, loading, error, lanes, onChange }: LaneComposerProps) {
  if (loading) return <p className="text-[11px] text-slate-500">Loading the lane presets…</p>;
  if (error) return <p className="text-[11px] text-amber-400">{error}</p>;
  if (presets.length === 0) return <p className="text-[11px] text-slate-500">No lane presets.</p>;
  return (
    <div className="flex flex-col gap-1" data-testid="lane-composer">
      {presets.map((p) => {
        const lane = lanes.find((l) => l.id === p.id);
        const index = lane ? lanes.indexOf(lane) : 0;
        return (
          <div
            key={p.id}
            className={[
              "flex flex-wrap items-center gap-2 rounded-md border px-2 py-1",
              lane ? "border-slate-700 bg-surface-800/60" : "border-slate-800",
            ].join(" ")}
          >
            <label className="flex min-w-0 items-center gap-2 text-xs text-slate-200">
              <input type="checkbox" checked={lane !== undefined} onChange={() => onChange(toggleLane(lanes, presets, p))} />
              <span className="truncate">{p.name}</span>
              <span className="rounded border border-slate-700 px-1 text-[10px] uppercase tracking-wider text-slate-400">
                {FAMILY_LABEL[p.family]}
              </span>
              {p.fitMode && <span className="text-[10px] text-slate-500">{p.fitMode}</span>}
            </label>
            {lane && (
              <div className="ml-auto flex items-center gap-2">
                <span className="inline-block h-3 w-3 rounded-sm" style={{ background: laneStyle(lane, index).colour }} aria-hidden />
                <input
                  aria-label={`Colour of ${p.name}`}
                  className={`${inputClass} w-24`}
                  placeholder="family colour"
                  value={lane.colour ?? ""}
                  onChange={(e) => onChange(patchLane(lanes, p.id, { colour: e.target.value.trim() || null }))}
                />
                <input
                  aria-label={`Name of ${p.name}`}
                  className={`${inputClass} w-40`}
                  value={lane.name}
                  onChange={(e) => onChange(patchLane(lanes, p.id, { name: e.target.value }))}
                />
                <label className="flex items-center gap-1 text-[11px] text-slate-400" title="the production lane: the ghost trail and differences follow it">
                  <input type="radio" name="series-production-lane" checked={lane.production} onChange={() => onChange(setProduction(lanes, p.id))} />
                  <span className={lane.production ? "text-amber-400" : ""}>★</span>
                </label>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
