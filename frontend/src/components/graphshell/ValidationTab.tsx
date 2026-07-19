// Validation drawer tab (P5b U7): the SIDE-BY-SIDE current-day LOO across
// operators — transported prior (no propagation) vs smooth field vs precision
// messages, all through the same mode-aware backtest endpoint — plus the link
// to the OFFLINE benchmark artifact (the pre-registered multi-regime story
// runs offline via run_benchmark_pack.ps1; this tab only links its output).
import { FlaskConical, SquareArrowOutUpRight } from "lucide-react";
import { API_BASE_URL } from "../../state/api";
import type { ExtrapolateBody } from "../../state/useGraphExtrapolation";
import type { LooColumn, UseLooComparisonResult } from "../../state/useLooComparison";

interface ValidationTabProps {
  manual: boolean;
  loo: UseLooComparisonResult;
  /** Mode-forced request bodies (built by the shell from the live knobs). */
  smoothBody: ExtrapolateBody;
  messagesBody: ExtrapolateBody;
}

const METRICS: {
  key: keyof Pick<LooColumn, "rmseBp" | "zetaMean" | "zetaStd" | "cov80" | "cov95" | "n">;
  label: string;
  title: string;
  fmt: (v: number) => string;
}[] = [
  { key: "rmseBp", label: "RMSE (bp)", title: "Root-mean-square held-out ATM residual", fmt: (v) => v.toFixed(1) },
  { key: "zetaMean", label: "ζ mean", title: "Standardized-residual mean (0 = unbiased)", fmt: (v) => v.toFixed(2) },
  { key: "zetaStd", label: "ζ std", title: "Standardized-residual std (1 = honest bands)", fmt: (v) => v.toFixed(2) },
  { key: "cov80", label: "cov 80", title: "Fraction of held-out nodes inside the 80% band (client-side from ζ)", fmt: (v) => (v * 100).toFixed(0) + "%" },
  { key: "cov95", label: "cov 95", title: "Fraction inside the 95% band", fmt: (v) => (v * 100).toFixed(0) + "%" },
  { key: "n", label: "n scored", title: "Validation-clean held-out nodes", fmt: (v) => String(v) },
];

export default function ValidationTab({
  manual,
  loo,
  smoothBody,
  messagesBody,
}: ValidationTabProps) {
  if (manual) {
    return (
      <p className="py-2 text-xs text-slate-500">
        Switch Observations to “From calibrations” — validation scores held-out
        CALIBRATIONS; a what-if pulse has nothing held out.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          className="flex items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          disabled={loo.running !== null}
          onClick={() => void loo.run(smoothBody, messagesBody)}
          title="Current-day leave-one-node-out under BOTH operators (sequential — each LOO is one full solve per held-out node) + the transported-prior comparator"
        >
          {loo.running !== null && (
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500/40 border-t-slate-200" />
          )}
          <FlaskConical size={12} strokeWidth={1.75} className="opacity-80" />
          {loo.running !== null ? `Scoring ${loo.running}…` : "Compare operators (LOO)"}
        </button>
        {/* The offline artifact: the pre-registered multi-regime story. */}
        <a
          href={`${API_BASE_URL}/graph/benchmark/artifact`}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1 text-[10px] text-slate-500 underline decoration-slate-700 transition-colors hover:text-slate-300"
          title="The offline benchmark-pack artifact (multi-regime, pre-registered — run backend/backtest/run_benchmark_pack.ps1; 404 until a pack has run)"
        >
          <SquareArrowOutUpRight size={10} strokeWidth={1.75} />
          offline benchmark artifact
        </a>
      </div>

      {loo.error !== null && (
        <p className="text-[10px] text-amber-400">{loo.error}</p>
      )}

      {loo.columns !== null && (
        <div className="overflow-x-auto">
          <table className="border-collapse font-mono text-[10px]">
            <thead>
              <tr>
                <th className="pr-3 text-left font-normal text-slate-600" />
                {loo.columns.map((c) => (
                  <th key={c.label} className="px-2 text-right font-medium text-slate-300">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map((m) => (
                <tr key={m.key} title={m.title}>
                  <td className="pr-3 text-slate-500">{m.label}</td>
                  {loo.columns!.map((c) => {
                    const v = c[m.key];
                    return (
                      <td key={c.label} className="px-2 text-right text-slate-300">
                        {v === null ? "—" : m.fmt(v as number)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-[9px] text-slate-600">
            Same day, same universe, same knobs — only the operator differs.
            The transported-prior column has no calibrated uncertainty (ζ/cov
            n/a). The multi-regime verdict lives in the offline artifact.
          </p>
        </div>
      )}
    </div>
  );
}
