// Series lens header (SERIES ARC S4 §3.4): the ticker's series picker
// (newest first, "name · mode · n frames"), New series… / Delete, the job
// status pill (status · frames ready/total · fits done/total · the current
// step while running · the error in red) with its verbs by status (draft →
// Start; paused / failed / cancelled → Resume; queued / harvesting /
// calibrating → Pause + Cancel), the lane chips (a colour swatch from the
// lane style, ★ on the production lane, click = visibility) and the stage
// tabs — Smile · Frames · Surface · Term · Lanes (S5 lit the last three).
// Pure presentation: every verb is a prop.
import type { LaneSpec, SeriesDoc, SeriesProgress, SeriesSummary } from "../../lib/seriesTypes";
import { laneStyle } from "../../lib/seriesLanes";
import { statusTone } from "../../lib/seriesFormat";
import { badgeClass, buttonClass, chipClass, primaryButtonClass, selectClass } from "../../lib/ui";

export type SeriesStage = "smile" | "frames" | "surface" | "term" | "lanes";
export const SERIES_STAGES: readonly { id: SeriesStage; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "frames", label: "Frames" },
  { id: "surface", label: "Surface" },
  { id: "term", label: "Term" },
  { id: "lanes", label: "Lanes" },
];

export interface SeriesHeaderProps {
  ticker: string;
  list: SeriesSummary[];
  seriesId: string | null;
  doc: SeriesDoc | null;
  /** The job's progress (the stream's while it carries this series, else the document's). */
  progress: SeriesProgress | null;
  /** A verb is in flight: the verbs are inert. */
  busy: boolean;
  hidden: Set<string>;
  stage: SeriesStage;
  onSelect: (id: string | null) => void;
  onNew: () => void;
  onDelete: () => void;
  onStart: () => void;
  onResume: () => void;
  onPause: () => void;
  onCancel: () => void;
  onToggleLane: (id: string) => void;
  onStage: (stage: SeriesStage) => void;
}

/** The picker's row label. */
export function summaryLabel(s: SeriesSummary): string {
  return `${s.name} · ${s.mode} · ${s.nFrames} frame${s.nFrames === 1 ? "" : "s"}`;
}

function StatusPill({ progress }: { progress: SeriesProgress }) {
  const running = progress.status === "harvesting" || progress.status === "calibrating";
  return (
    <div className="flex min-w-0 items-center gap-2 text-[11px]" data-testid="series-status">
      <span className={badgeClass(statusTone(progress.status))}>{progress.status.toUpperCase()}</span>
      <span className="font-mono text-slate-400" title="frames harvested / total">
        frames {progress.framesReady}/{progress.framesTotal}
      </span>
      <span className="font-mono text-slate-400" title="lane fits done / total">
        fits {progress.fitsDone}/{progress.fitsTotal}
      </span>
      {running && progress.current && (
        <span className="max-w-[16rem] truncate text-slate-500" title={progress.current}>{progress.current}</span>
      )}
      {progress.error && (
        <span className="max-w-[20rem] truncate text-rose-400" title={progress.error}>{progress.error}</span>
      )}
    </div>
  );
}

function JobButtons({ progress, busy, onStart, onResume, onPause, onCancel }: Pick<
  SeriesHeaderProps, "progress" | "busy" | "onStart" | "onResume" | "onPause" | "onCancel"
>) {
  const s = progress?.status ?? null;
  if (s === null) return null;
  const resumable = s === "paused" || s === "failed" || s === "cancelled";
  const moving = s === "queued" || s === "harvesting" || s === "calibrating";
  return (
    <>
      {s === "draft" && <button className={primaryButtonClass} disabled={busy} onClick={onStart}>Start</button>}
      {resumable && (
        <button className={primaryButtonClass} disabled={busy} onClick={onResume} title="continue from the first unfinished frame">
          Resume
        </button>
      )}
      {moving && <button className={buttonClass} disabled={busy} onClick={onPause}>Pause</button>}
      {moving && <button className={buttonClass} disabled={busy} onClick={onCancel}>Cancel</button>}
    </>
  );
}

function LaneChip({ lane, index, hidden, onToggle }: { lane: LaneSpec; index: number; hidden: boolean; onToggle: () => void }) {
  const { colour } = laneStyle(lane, index);
  return (
    <button
      type="button"
      aria-pressed={!hidden}
      title={`${lane.name} — ${lane.family}${lane.production ? " · production lane" : ""} (click to ${hidden ? "show" : "hide"})`}
      onClick={onToggle}
      className={[
        "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
        hidden ? "border-slate-800 text-slate-600 line-through" : "border-slate-700 text-slate-200 hover:border-slate-600",
      ].join(" ")}
    >
      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: colour, opacity: hidden ? 0.35 : 1 }} />
      {lane.name}
      {lane.production && <span className="text-amber-400" aria-label="production lane">★</span>}
    </button>
  );
}

export default function SeriesHeader(props: SeriesHeaderProps) {
  const { ticker, list, seriesId, doc, progress, busy, hidden, stage, onSelect, onNew, onDelete, onToggleLane, onStage } = props;
  const unlisted = seriesId !== null && !list.some((s) => s.id === seriesId);
  return (
    <div className="flex shrink-0 flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Series"
          className={`${selectClass} max-w-[24rem]`}
          value={seriesId ?? ""}
          disabled={list.length === 0 && !unlisted}
          onChange={(e) => onSelect(e.target.value || null)}
        >
          {list.length === 0 && !unlisted && <option value="">No series for {ticker}</option>}
          {unlisted && <option value={seriesId ?? ""}>{doc?.spec.name ?? seriesId}</option>}
          {list.map((s) => (
            <option key={s.id} value={s.id}>{summaryLabel(s)}</option>
          ))}
        </select>
        <button className={buttonClass} onClick={onNew}>New series…</button>
        {seriesId !== null && (
          <button className={buttonClass} disabled={busy} onClick={onDelete} title="delete the series with its frames and fits">
            Delete
          </button>
        )}
        {progress && <StatusPill progress={progress} />}
        <div className="ml-auto flex items-center gap-1.5">
          <JobButtons progress={progress} busy={busy} onStart={props.onStart} onResume={props.onResume} onPause={props.onPause} onCancel={props.onCancel} />
        </div>
      </div>
      {doc && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex flex-wrap items-center gap-1.5" aria-label="Lanes">
            {doc.spec.lanes.map((lane, i) => (
              <LaneChip key={lane.id} lane={lane} index={i} hidden={hidden.has(lane.id)} onToggle={() => onToggleLane(lane.id)} />
            ))}
          </div>
          <div className="ml-auto flex items-center gap-1" role="tablist" aria-label="Stage">
            {SERIES_STAGES.map((s) => (
              <button key={s.id} role="tab" aria-selected={stage === s.id} className={chipClass(stage === s.id)} onClick={() => onStage(s.id)}>
                {s.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
