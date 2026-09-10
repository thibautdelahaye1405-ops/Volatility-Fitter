// Frames stage of the Series lens (SERIES ARC S4 §3.4): one row per frame —
// index, instant, spot, quote count, quote kind, harvest status (with its
// error) and the warm-up flag; the playhead row is lit and kept in view; a
// click jumps the transport to that frame (the row's POSITION is the
// playback index; the frame's own idx is the label).
import { useEffect, useRef } from "react";
import type { FrameDoc } from "../../lib/seriesTypes";
import { fmtInstant, fmtNum } from "../../lib/seriesFormat";

export interface FramesTableProps {
  frames: FrameDoc[];
  /** The playhead (position in `frames`). */
  index: number;
  onJump: (idx: number) => void;
}

const STATUS_CLASS: Record<FrameDoc["status"], string> = {
  ready: "text-emerald-400",
  pending: "text-slate-500",
  harvesting: "text-accent-300",
  failed: "text-rose-400",
  skipped: "text-amber-400",
};

const th = "px-2 py-1 font-medium";
const td = "px-2 py-1";

export default function FramesTable({ frames, index, onJump }: FramesTableProps) {
  const rowRef = useRef<HTMLTableRowElement | null>(null);
  // Keep the playhead row in view as the transport moves (no-op in jsdom).
  useEffect(() => {
    rowRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [index]);

  if (frames.length === 0) {
    return <div className="flex h-full items-center justify-center text-xs text-slate-500">No frames yet.</div>;
  }
  return (
    <div className="h-full overflow-auto" data-testid="frames-table">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead className="sticky top-0 bg-surface-900 text-[10px] uppercase tracking-wider text-slate-500">
          <tr>
            <th className={th}>#</th>
            <th className={th}>Instant</th>
            <th className={th}>Spot</th>
            <th className={th}>Quotes</th>
            <th className={th}>Kind</th>
            <th className={th}>Status</th>
            <th className={th}>Warm-up</th>
          </tr>
        </thead>
        <tbody>
          {frames.map((f, i) => {
            const on = i === index;
            return (
              <tr
                key={`${f.idx}-${i}`}
                ref={on ? rowRef : undefined}
                data-frame-row={i}
                aria-selected={on}
                onClick={() => onJump(i)}
                className={[
                  "cursor-pointer border-t border-slate-800/60 font-mono",
                  on ? "bg-accent-500/10 text-slate-100" : "text-slate-300 hover:bg-slate-800/40",
                ].join(" ")}
              >
                <td className={`${td} text-slate-500`}>{f.idx}</td>
                <td className={td}>{fmtInstant(f.ts)}</td>
                <td className={td}>{fmtNum(f.spot)}</td>
                <td className={td}>{f.nQuotes}</td>
                <td className={`${td} text-slate-400`}>{f.quoteKind ?? "—"}</td>
                <td className={`${td} ${STATUS_CLASS[f.status]}`} title={f.error ?? undefined}>
                  {f.status}
                  {f.error ? ` · ${f.error}` : ""}
                </td>
                <td className={`${td} text-slate-500`}>{f.warmup ? "warm-up" : ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
