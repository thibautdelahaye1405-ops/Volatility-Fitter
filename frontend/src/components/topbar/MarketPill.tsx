// Market-context pill — a PASSIVE readout of "what data am I looking at":
// the active source (Yahoo / Bloomberg / Massive / Synthetic, with a status
// light) and the as-of timestamp (Live / Prev close / historical moment),
// plus a quote-age staleness cue. Face reads "● Massive · Live" and turns
// yellow whenever the view is historical or the live quotes are ageing, rose
// when the "live" chain is really the previous session (the "amber" level
// keeps its backend name but is drawn yellow — amber sat too close to red at
// a glance). No dropdown: the
// click hands off to the shell (the Universe dialog's Data-sources card);
// the as-of picker lives under Fetch ▾ (AsOfRows).
import type { SourceStatus, UseDataSourcesResult } from "../../state/useDataSources";
import type { UseAsOfResult } from "../../state/useAsOf";
import { asofLabel } from "./AsOfRows";

/** Tailwind dot colour for each status level ("amber" = a degraded-but-usable
 *  source, drawn YELLOW so it is never mistaken for the red "unavailable"). */
export const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-yellow-400",
  red: "bg-rose-500",
};

const TITLE =
  "Data source & as-of — click to manage data sources (as-of lives under Fetch ▾)";

export default function MarketPill({
  dataSources,
  asof: asofHook,
  onClick,
}: {
  dataSources: UseDataSourcesResult;
  asof: UseAsOfResult;
  onClick: () => void;
}) {
  const { sources, active, switching, dataAge } = dataSources;
  const { asof, busy: asofBusy } = asofHook;

  const activeSource = sources.find((s) => s.id === active);
  const historical = asof !== null && asof.mode !== "live";
  // Data-age staleness of the LIVE view (backend data_age; null off-live).
  // Red-stale live data means "live" is really the previous session — say so.
  const staleLive = !historical && dataAge !== null && dataAge.level !== "fresh";
  const redStale = staleLive && dataAge!.level === "red";

  return (
    <button
      onClick={onClick}
      title={
        staleLive
          ? `Live view is pricing quotes ${dataAge!.label} old (worst: ${dataAge!.worstTicker})\n${TITLE}`
          : TITLE
      }
      className={[
        "flex items-center gap-2 rounded-md border px-2.5 py-1 hover:border-slate-600",
        redStale
          ? "border-rose-500/40 bg-rose-500/10 text-rose-300"
          : historical || staleLive
            ? "border-yellow-500/40 bg-yellow-500/10 text-yellow-300"
            : "border-slate-700 bg-surface-800 text-slate-200",
      ].join(" ")}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          STATUS_DOT[activeSource?.status ?? "green"]
        } ${switching ? "animate-pulse" : ""}`}
      />
      <span className="font-medium">{activeSource?.label ?? (active || "Source")}</span>
      {asof && (
        <span className={`text-slate-400 ${asofBusy ? "animate-pulse" : ""}`}>
          · {redStale ? "prev session" : asofLabel(asof)}
        </span>
      )}
      {staleLive && (
        <span className={redStale ? "text-rose-300" : "text-yellow-300"}>
          · quotes {dataAge!.label}
        </span>
      )}
    </button>
  );
}
