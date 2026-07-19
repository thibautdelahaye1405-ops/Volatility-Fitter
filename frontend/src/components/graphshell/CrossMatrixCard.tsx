// Cross-asset matrix card (P5b U2): the messages-mode Cross-asset card grown
// into the RECEIVER-row × INFORMER-column ticker matrix. Each cell shows the
// relation's ATM amplitude β and relationship uncertainty σ (U1 lens):
// persisted cross rows where they exist (averaged over expiries), the implied
// reverse (1/β, σ/|β| — the §7.6/§8.3 one-factor identities, marked ⇐) when
// only the mirror orientation is persisted, else the auto default (β=1 at the
// cross precision scale, dimmed). Hover = the U1 sentence; click = drill into
// the row-level MessageEdgeEditor. |β| beyond the cap renders amber.
import { MessageCrossSection } from "../MessagePanel";
import { BETA_CAP } from "../../lib/calendarPolicy";
import { fmtSigmaPts, relationSentence } from "../../lib/precisionUnits";
import type { SolverParams } from "../../state/useGraph";
import type { MessageEdgeRow } from "../../state/useMessageEdges";

interface CrossMatrixCardProps {
  params: SolverParams;
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
  /** U1 units lens (σ pts default / raw precision). */
  raw: boolean;
  tickers: string[];
  /** Persisted message rows (empty ⇒ the solve builds its auto relations). */
  rows: MessageEdgeRow[];
  /** Open the row-level relation editor (the cell drill-in). */
  onDrillIn: () => void;
}

/** One rendered cell: β + σ with provenance. */
interface CellValue {
  beta: number;
  precision: number;
  provenance: "persisted" | "implied" | "auto";
  /** Number of expiry-level rows behind the aggregate. */
  n: number;
}

/** Aggregate the persisted cross rows for (receiver, informer) — mean β and
 *  mean precision over the expiry-level rows of that orientation. */
function persistedCell(
  rows: MessageEdgeRow[],
  receiver: string,
  informer: string,
): { beta: number; precision: number; n: number } | null {
  const hits = rows.filter(
    (r) =>
      r.relationClass !== "calendar" &&
      r.targetTicker === receiver &&
      r.sourceTicker === informer &&
      r.targetTicker !== r.sourceTicker,
  );
  if (hits.length === 0) return null;
  const beta = hits.reduce((s, r) => s + r.betaAtmVol, 0) / hits.length;
  const precision = hits.reduce((s, r) => s + r.messagePrecision, 0) / hits.length;
  return { beta, precision, n: hits.length };
}

/** Resolve what a matrix cell displays (see the module comment). */
export function crossCell(
  rows: MessageEdgeRow[],
  receiver: string,
  informer: string,
  crossPrecision: number,
): CellValue {
  const direct = persistedCell(rows, receiver, informer);
  if (direct !== null) return { ...direct, provenance: "persisted" };
  const mirror = persistedCell(rows, informer, receiver);
  if (mirror !== null && mirror.beta !== 0) {
    // §7.6/§8.3 one-factor reverse identities: amplitude 1/β, precision p·β²
    // (σ/|β| under the σ lens).
    return {
      beta: 1 / mirror.beta,
      precision: mirror.precision * mirror.beta * mirror.beta,
      provenance: "implied",
      n: mirror.n,
    };
  }
  return { beta: 1, precision: crossPrecision, provenance: "auto", n: 0 };
}

export default function CrossMatrixCard({
  params,
  setParam,
  raw,
  tickers,
  rows,
  onDrillIn,
}: CrossMatrixCardProps) {
  return (
    <div>
      <MessageCrossSection params={params} setParam={setParam} raw={raw} />

      {tickers.length >= 2 && (
        <div className="mt-2">
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Receiver × informer
          </p>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse font-mono text-[9px]">
              <thead>
                <tr>
                  <th className="p-0.5 text-left font-normal text-slate-600" title="rows = receiver (informed) · columns = informer (source)">
                    ⇣ recv
                  </th>
                  {tickers.map((informer) => (
                    <th key={informer} className="p-0.5 text-right font-medium text-slate-400">
                      {informer}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickers.map((receiver) => (
                  <tr key={receiver}>
                    <td className="p-0.5 font-medium text-slate-400">{receiver}</td>
                    {tickers.map((informer) => {
                      if (informer === receiver) {
                        return (
                          <td key={informer} className="p-0.5 text-right text-slate-700">
                            —
                          </td>
                        );
                      }
                      const cell = crossCell(rows, receiver, informer, params.crossPrecision);
                      const sigma = raw
                        ? `p ${Math.round(cell.precision)}`
                        : `${fmtSigmaPts(cell.precision)}pt`;
                      const sentence =
                        relationSentence({
                          sourceLabel: informer,
                          targetLabel: receiver,
                          beta: cell.beta,
                          precision: cell.precision,
                          rho: params.ampCross,
                        }) +
                        (cell.provenance === "persisted"
                          ? ` · ${cell.n} persisted row${cell.n > 1 ? "s" : ""} (mean)`
                          : cell.provenance === "implied"
                            ? " · implied reverse of the persisted mirror factor (1/β, p·β²)"
                            : " · auto relation at solve time") +
                        " · click to edit relations";
                      const capped = Math.abs(cell.beta) > BETA_CAP;
                      return (
                        <td key={informer} className="p-0">
                          <button
                            onClick={onDrillIn}
                            title={sentence}
                            className={
                              "w-full p-0.5 text-right transition-colors hover:bg-surface-800/60 " +
                              (cell.provenance === "auto"
                                ? "text-slate-600"
                                : capped
                                  ? "text-amber-300"
                                  : "text-slate-300")
                            }
                          >
                            {cell.provenance === "implied" && "⇐"}
                            {cell.beta.toFixed(2)}
                            <span className="text-slate-600">/{sigma}</span>
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-1 text-[9px] text-slate-600">
            β/σ per relation · rows receive, columns inform · dim = auto ·
            ⇐ = implied reverse · click a cell to edit.
          </p>
        </div>
      )}
    </div>
  );
}
