// Data-sources card of the Manage-universe dialog (the multi-source engine,
// 2026-09-02h): the UNIVERSE source (the default every ticker follows unless
// pinned — a radio list with a status light and the count of tickers each
// source serves now), *Open a snapshot file*, and the per-ticker pins summary
// (the pins themselves are edited on each ticker row of the matrix,
// state/tickerSources.ts).
import type { DataSourceInfo, SourceStatus } from "../../state/useDataSources";
import type { useOptionalSnapshotFile } from "../../state/snapshotFile";

const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-yellow-400", // degraded-but-usable: yellow, never mistaken for red
  red: "bg-rose-500",
};

interface Props {
  sources: DataSourceInfo[];
  active: string;
  switching: boolean;
  switchSource: (id: string) => Promise<void>;
  snapshot: ReturnType<typeof useOptionalSnapshotFile>;
  /** Explicit per-ticker pins (ticker → source id). */
  pins: Record<string, string>;
  labelOf: (id: string) => string;
  /** Unpin every pinned ticker (each goes back to the universe source). */
  clearPins: () => void;
  pinBusy: string | null;
}

export default function DataSourcesCard({
  sources, active, switching, switchSource, snapshot, pins, labelOf, clearPins, pinBusy,
}: Props) {
  const pinned = Object.entries(pins).filter(([, sid]) => sid !== active);
  return (
    <section className="flex min-h-0 shrink-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
      <h2 className="mb-1 text-sm font-semibold text-slate-100">Data sources</h2>
      <p className="mb-2 text-[11px] text-slate-500">
        <span className="font-medium text-slate-400">Universe source (default)</span> — every ticker
        not pinned elsewhere fetches from it; switching refetches those.
      </p>
      {sources.length === 0 ? (
        <p className="text-[11px] text-slate-500">No data sources registered.</p>
      ) : (
        <div
          role="radiogroup"
          aria-label="Active data source"
          className={`flex flex-col gap-0.5 ${switching ? "animate-pulse" : ""}`}
        >
          {sources.map((s) => {
            // A red light WARNS (the probe failed / timed out / the feed is
            // down) but never locks the choice: the user must always be able
            // to leave a hung source for another one.
            const unavailable = s.status === "red";
            const isActive = s.id === active;
            const served = s.tickers ?? [];
            const title = [
              unavailable ? `${s.detail} — switching is still allowed` : s.detail,
              served.length ? `serves ${served.join(", ")}` : "serves no ticker right now",
            ].filter(Boolean).join("\n");
            return (
              <button
                key={s.id}
                role="radio"
                aria-checked={isActive}
                disabled={switching}
                title={title}
                onClick={() => void switchSource(s.id)}
                className={[
                  "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                  isActive
                    ? "bg-accent-500/10 text-accent-300"
                    : unavailable
                      ? "text-slate-500 hover:bg-slate-700/40 hover:text-slate-200"
                      : "text-slate-300 hover:bg-slate-700/40 hover:text-slate-100",
                ].join(" ")}
              >
                <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} />
                <span className="min-w-0 flex-1 truncate font-medium">{s.label}</span>
                {served.length > 0 && (
                  <span className="shrink-0 font-mono text-[10px] text-slate-500" data-testid={`source-count-${s.id}`}>
                    · {served.length}
                  </span>
                )}
                <span className="max-w-[9rem] truncate text-[10px] text-slate-500" title={s.detail}>
                  {s.detail}
                </span>
              </button>
            );
          })}
        </div>
      )}

      {snapshot !== null && (
        <button
          className="mt-2 w-full rounded-md border border-dashed border-slate-700 px-2 py-1.5 text-left text-[11px] text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200"
          title="Open a snapshot file (quotes + calibrations): it becomes the File data source"
          disabled={snapshot.busy}
          onClick={() => void snapshot.openPicker()}
        >
          + Open snapshot file… <span className="text-slate-600">(File source)</span>
        </button>
      )}

      {/* Per-ticker pins: edited on each ticker row; summarized here. */}
      <div className="mt-3 border-t border-slate-800/60 pt-2" data-testid="per-ticker-sources">
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-slate-300">Per-ticker sources</span>
          {pinned.length > 0 && (
            <span className="text-[10px] text-slate-500">
              {pinned.length} pinned ·{" "}
              <button
                className="text-slate-400 underline hover:text-slate-200 disabled:opacity-50"
                disabled={pinBusy !== null}
                onClick={clearPins}
                title="Every pinned ticker goes back to the universe source"
              >
                clear
              </button>
            </span>
          )}
        </div>
        <p className="text-[10px] text-slate-500">
          A ticker pinned to another source fetches, streams and captures from it; the rest
          follow the universe source. Pick a source on the ticker's row, or add a name from
          another source's catalogue with the search's source selector.
          {pinned.length > 0 && (
            <span className="mt-1 block text-slate-400">
              {pinned.map(([t, sid]) => `${t} → ${labelOf(sid)}`).join(" · ")}
            </span>
          )}
        </p>
      </div>
    </section>
  );
}
