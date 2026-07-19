// Per-node attribution card (the graph explainability panel): decomposes a
// selected node's posterior ATM move into per-lit-node contributions —
// contribution = gain × innovation, the exact terms of the linear-Gaussian
// update that produced the displayed posterior (they sum to the shift by
// arithmetic, not by fit). Rides the existing per-node drill-in endpoint.
import { useGraphNodeSmile } from "../state/useGraphNodeSmile";
import type { GraphAttributionEntry } from "../state/useGraphNodeSmile";
import type { ExtrapolateBody } from "../state/useGraphExtrapolation";

interface GraphAttributionCardProps {
  ticker: string;
  expiry: string;
  /** The /graph/extrapolate request body (same knobs as the solve on screen). */
  body: ExtrapolateBody;
  onClose: () => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

function ContributionRow({
  entry,
  maxAbs,
}: {
  entry: GraphAttributionEntry;
  maxAbs: number;
}) {
  const positive = entry.contributionBp >= 0;
  const width = maxAbs > 0 ? Math.max(2, (Math.abs(entry.contributionBp) / maxAbs) * 100) : 0;
  const detail =
    `gain ${entry.gain.toFixed(3)} × innovation ${entry.innovationBp >= 0 ? "+" : ""}` +
    `${entry.innovationBp.toFixed(1)}bp` +
    (entry.edgeBeta !== null ? ` · direct edge β ${entry.edgeBeta.toFixed(2)}` : "");
  return (
    <div className="py-0.5" title={detail}>
      <div className="flex items-baseline justify-between gap-2 text-[10px]">
        <span className="min-w-0 truncate text-slate-300">
          <span className="font-medium text-slate-100">{entry.ticker}</span>{" "}
          <span className="font-mono text-slate-500">{entry.expiry}</span>
          {entry.edgeBeta !== null && (
            <span className="ml-1 text-accent-400">β{entry.edgeBeta.toFixed(2)}</span>
          )}
        </span>
        <span
          className={`shrink-0 font-mono ${positive ? "text-emerald-400" : "text-rose-400"}`}
        >
          {positive ? "+" : ""}
          {entry.contributionBp.toFixed(1)}bp
        </span>
      </div>
      <div className="mt-0.5 h-1 rounded-full bg-surface-800">
        <div
          className={`h-1 rounded-full ${positive ? "bg-emerald-500/70" : "bg-rose-500/70"}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

export default function GraphAttributionCard({
  ticker,
  expiry,
  body,
  onClose,
  onOpenSmile,
}: GraphAttributionCardProps) {
  const { node, loading, error } = useGraphNodeSmile(true, ticker, expiry, body);
  const shiftBp = node !== null ? (node.postAtmVol - node.priorAtmVol) * 1e4 : 0;
  const maxAbs =
    node !== null ? Math.max(...node.attribution.map((e) => Math.abs(e.contributionBp)), 0) : 0;

  return (
    <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/60 p-2">
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="min-w-0 truncate text-[11px] font-medium text-slate-200">
          Why {ticker}{" "}
          <span className="font-mono text-[10px] text-slate-500">{expiry}</span> moved
        </span>
        <span className="flex shrink-0 items-center gap-1.5">
          {node !== null && (
            <span
              className={`font-mono text-[11px] ${shiftBp >= 0 ? "text-emerald-400" : "text-rose-400"}`}
            >
              {shiftBp >= 0 ? "+" : ""}
              {shiftBp.toFixed(1)}bp
            </span>
          )}
          <button
            onClick={() => onOpenSmile(ticker, expiry)}
            title="Open the reconstructed smile"
            className="text-[11px] text-slate-500 hover:text-slate-300"
          >
            ↗
          </button>
          <button
            onClick={onClose}
            title="Close attribution"
            className="text-[11px] text-slate-500 hover:text-slate-300"
          >
            ×
          </button>
        </span>
      </div>

      {loading && <p className="py-1 text-[10px] text-slate-500">Solving attribution…</p>}
      {error !== null && !loading && (
        <p className="py-1 text-[10px] text-amber-400/80">{error}</p>
      )}
      {node !== null && !loading && (
        <>
          {node.attribution.length === 0 ? (
            <p className="py-1 text-[10px] text-slate-500">
              No lit observations in the solve — nothing to attribute.
            </p>
          ) : (
            <div className="max-h-48 overflow-y-auto pr-1">
              {node.attribution.map((e) => (
                <ContributionRow key={`${e.ticker}|${e.expiry}`} entry={e} maxAbs={maxAbs} />
              ))}
              {node.attributionOthersBp !== 0 && (
                <div className="flex items-baseline justify-between py-0.5 text-[10px] text-slate-500">
                  <span>+ {"others"}</span>
                  <span className="font-mono">
                    {node.attributionOthersBp >= 0 ? "+" : ""}
                    {node.attributionOthersBp.toFixed(1)}bp
                  </span>
                </div>
              )}
            </div>
          )}
          <p className="mt-1 text-[9px] text-slate-600">
            contribution = gain × lit-node innovation · sums exactly to the shift
          </p>
        </>
      )}
    </div>
  );
}
