// FilterTimelineSection — the self-contained panel section around the pure
// FilterTimeline charts (V3.9 item 7 + the replay rider): expiry + handle
// selectors, the MOCK badge, and the "Live | Replay <day>" SOURCE chip. The
// chip appears only when a served offline replay part (GET
// /filter/replay/parts) carries this ticker AND this expiry ISO; selecting
// Replay fetches that part and charts its steps — the same wire shape as the
// live /filter/history ring, so the charts are untouched. Mounted by
// ObservationFilterPanel behind its "Timeline" toggle; serves the mock ring
// when the backend is unreachable (`live` false — no mock replay exists).
import { useEffect, useMemo, useState } from "react";

import { partForExpiry, replayChipLabel, stepsForExpiry } from "../lib/filterReplay";
import { api } from "../state/api";
import { useFilterHistory } from "../state/useFilterHistory";
import { useFilterReplayPart, useFilterReplayParts } from "../state/useFilterReplay";
import type { FitMode } from "../state/useSmile";
import { FilterTimeline } from "./FilterTimeline";

const HANDLES = ["ATM", "skew", "curv"] as const;

type Source = "live" | "replay";

const selectCls =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

const chipCls = (on: boolean) =>
  [
    "px-1.5 py-px text-[9px] font-medium transition-colors",
    on
      ? "bg-accent-500/15 text-accent-300"
      : "text-slate-500 hover:text-slate-300",
  ].join(" ");

export default function FilterTimelineSection({
  ticker, live, fitMode, refreshKey,
}: { ticker: string; live: boolean; fitMode: FitMode; refreshKey: unknown }) {
  const [expiries, setExpiries] = useState<string[]>([]);
  const [expiry, setExpiry] = useState("");
  const [handle, setHandle] = useState(0);
  const [source, setSource] = useState<Source>("live");

  useEffect(() => {
    if (!live || !ticker) { setExpiries([]); setExpiry(""); return; }
    let cancelled = false;
    api
      .get<{ entries: { expiry: string }[] }>(`/forwards/${ticker}`)
      .then((f) => {
        if (cancelled) return;
        const exps = (f.entries ?? []).map((e) => e.expiry);
        setExpiries(exps);
        setExpiry((cur) => (cur !== "" && exps.includes(cur) ? cur : exps[0] ?? ""));
      })
      .catch(() => !cancelled && setExpiries([]));
    return () => { cancelled = true; };
  }, [live, ticker]);

  // Live ring (or the mock ring backendless).
  const { steps: liveSteps, source: liveSource } = useFilterHistory(
    live, ticker, expiry, fitMode, refreshKey,
  );

  // Replay: the newest served part carrying this node decides whether the
  // chip shows; the part document is fetched only once Replay is selected.
  const { parts } = useFilterReplayParts(live, ticker, refreshKey);
  const replayMeta = useMemo(() => partForExpiry(parts, expiry), [parts, expiry]);
  const replayDay = replayMeta?.day ?? null;
  useEffect(() => {
    if (replayDay === null) setSource("live"); // no part for this node: back to Live
  }, [replayDay]);
  const showReplay = source === "replay" && replayDay !== null;
  const { part, loading: partLoading } = useFilterReplayPart(
    live, ticker, showReplay ? replayDay : null,
  );
  const replaySteps = useMemo(() => stepsForExpiry(part, expiry), [part, expiry]);
  const steps = showReplay ? replaySteps : liveSteps;

  return (
    <div className="mt-2 rounded-md border border-slate-800 bg-surface-800/40 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="flex items-center text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Filter timeline
          {liveSource === "mock" && (
            <span className="ml-2 rounded bg-amber-500/15 px-1 py-px text-[9px] font-medium normal-case tracking-normal text-amber-400">
              MOCK
            </span>
          )}
          {replayMeta !== null && (
            <span
              className="ml-2 flex overflow-hidden rounded border border-slate-700 normal-case tracking-normal"
              role="group"
              title={`An offline replay part carries this node (${replayMeta.nInstants} instants, ${replayMeta.filterMode} mode): chart the live ring or that replay`}
            >
              <button type="button" className={chipCls(!showReplay)} onClick={() => setSource("live")}>
                Live
              </button>
              <button type="button" className={chipCls(showReplay)} onClick={() => setSource("replay")}>
                {replayChipLabel(replayMeta)}
              </button>
            </span>
          )}
        </span>
        <span className="flex items-center gap-1.5">
          <select
            value={handle}
            onChange={(e) => setHandle(Number(e.target.value))}
            className={`${selectCls} w-20`}
            title="Which filtered handle to chart"
          >
            {HANDLES.map((h, i) => (
              <option key={h} value={i}>{h}</option>
            ))}
          </select>
          {live && (
            <select
              value={expiry}
              onChange={(e) => setExpiry(e.target.value)}
              className={`${selectCls} w-28`}
              title="Node expiry"
            >
              {expiries.map((e) => (
                <option key={e} value={e}>{e}</option>
              ))}
            </select>
          )}
        </span>
      </div>
      {steps.length === 0 ? (
        <p className="text-[10px] text-slate-600">
          {showReplay
            ? partLoading
              ? "Loading the replay part…"
              : `No replay steps for this node in the ${replayDay} part.`
            : "No committed filter steps yet — calibrate with the filter on; the ring keeps the last 64 committed updates per node."}
        </p>
      ) : (
        <FilterTimeline steps={steps} handle={handle} />
      )}
    </div>
  );
}
