// "Replay evidence" block of the Prior Evidence tab (V3.9 rider): the LATEST
// offline filter-replay part for the ticker — replayed day, instants driven
// through the production commit path, filter/fit mode, node count — and the
// link to the served HTML evidence page (the ValidationTab artifact-link
// pattern). Static-file reads only; mock / backendless / no part yet all
// render the run hint, never invented evidence.
import { SquareArrowOutUpRight } from "lucide-react";

import { newestPart, REPLAY_RUN_HINT } from "../lib/filterReplay";
import { API_BASE_URL } from "../state/api";
import { useFilterReplayParts } from "../state/useFilterReplay";

const label = "text-xs text-slate-400";
const mono = "text-right font-mono text-slate-200";

export default function ReplayEvidenceBlock({
  live,
  ticker,
  refreshKey,
}: {
  live: boolean;
  ticker: string;
  refreshKey: unknown;
}) {
  const { parts, loading, available } = useFilterReplayParts(live, ticker, refreshKey);
  const newest = newestPart(parts);
  const olderDays = parts.filter((p) => p !== newest).map((p) => p.day);

  return (
    <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span
          className="text-[10px] font-semibold uppercase tracking-wider text-slate-500"
          title="The offline observation-filter replay: stored intraday chains driven through the PRODUCTION commit path (python -m backtest.filter_replay); its steps are the same wire shape as the live /filter/history ring"
        >
          Replay evidence
          {loading && <span className="ml-2 normal-case tracking-normal text-slate-600">refreshing…</span>}
        </span>
        {live && (
          <a
            href={`${API_BASE_URL}/filter/replay/artifact`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-[10px] text-slate-500 underline decoration-slate-700 transition-colors hover:text-slate-300"
            title="The newest offline filter-replay HTML page (404 until a replay has run)"
          >
            <SquareArrowOutUpRight size={10} strokeWidth={1.75} />
            replay artifact
          </a>
        )}
      </div>
      {!available || newest === null ? (
        <p className="text-[10px] text-slate-600">
          {REPLAY_RUN_HINT}
          {available && ticker !== "" ? ` (no part for ${ticker})` : ""}
        </p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[10px]">
            <span className={label}>Latest replayed day</span>
            <span className={mono}>{newest.day}</span>
            <span className={label}>Instants · nodes</span>
            <span className={mono}>
              {newest.nInstants} · {newest.expiries.length}
            </span>
            <span className={label}>Filter · fit mode</span>
            <span className={mono}>
              {newest.filterMode} · {newest.fitMode}
            </span>
          </div>
          {olderDays.length > 0 && (
            <p className="mt-1 border-t border-slate-800 pt-1 font-mono text-[9px] text-slate-500">
              older: {olderDays.slice(0, 4).join(", ")}
              {olderDays.length > 4 ? ` +${olderDays.length - 4}` : ""}
            </p>
          )}
        </>
      )}
    </div>
  );
}
