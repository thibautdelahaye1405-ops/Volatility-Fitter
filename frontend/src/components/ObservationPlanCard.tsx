// "Where to quote next" (R3 item 13): POST /graph/observation-plan ranks the
// non-observed nodes by closed-form exposure-weighted posterior-variance
// reduction on the SOLVED posterior (rank-one Schur, no refit). The card is
// fetch-on-demand — the ranking rides the same request body as Propagate, so
// it always answers for the knobs currently on screen.
import { useState } from "react";
import { Crosshair } from "lucide-react";
import { api } from "../state/api";

interface Beneficiary {
  ticker: string;
  expiry: string;
  sdBeforeBp: number;
  sdAfterBp: number;
}

interface PlanCandidate {
  ticker: string;
  expiry: string;
  lit: boolean;
  selfSdBeforeBp: number;
  selfSdAfterBp: number;
  totalVarReductionPct: number;
  assumedPrecision: number;
  beneficiaries: Beneficiary[];
}

interface PlanResponse {
  candidates: PlanCandidate[];
  nCandidates: number;
}

interface ObservationPlanCardProps {
  /** The /graph/extrapolate request body (same knobs as Propagate). */
  body: Record<string, string | number | boolean>;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

export default function ObservationPlanCard({ body, onOpenSmile }: ObservationPlanCardProps) {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPlan = async () => {
    setLoading(true);
    setError(null);
    try {
      setPlan(
        await api.post<PlanResponse>("/graph/observation-plan", {
          body: { ...body, topN: 5 },
        }),
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setPlan(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/60 p-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-medium text-slate-300">Where to quote next</span>
        <button
          onClick={() => void fetchPlan()}
          disabled={loading}
          title="Rank the dark nodes by how much of the universe's remaining uncertainty one quote would remove (closed form on the current posterior)"
          className="flex items-center gap-1 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[10px] text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:opacity-40"
        >
          <Crosshair size={11} strokeWidth={1.75} className="opacity-80" />
          {loading ? "Ranking…" : plan !== null ? "Re-rank" : "Rank"}
        </button>
      </div>
      {error !== null && <p className="mt-1 text-[10px] text-amber-400/80">{error}</p>}
      {plan !== null && plan.candidates.length === 0 && (
        <p className="mt-1 text-[10px] text-slate-500">
          Every selected node already feeds an observation — nothing to rank.
        </p>
      )}
      {plan !== null && plan.candidates.length > 0 && (
        <div className="mt-1 divide-y divide-slate-800/60">
          {plan.candidates.map((c, rank) => (
            <div key={`${c.ticker}|${c.expiry}`} className="flex items-center gap-2 py-1">
              <span className="w-3 shrink-0 text-right font-mono text-[9px] text-slate-600">
                {rank + 1}
              </span>
              <button
                onClick={() => onOpenSmile(c.ticker, c.expiry)}
                title={
                  `Quoting pins this node: sd ${c.selfSdBeforeBp.toFixed(0)} → ` +
                  `${c.selfSdAfterBp.toFixed(0)} bp.` +
                  (c.beneficiaries.length > 0
                    ? ` Also shrinks: ${c.beneficiaries
                        .map(
                          (b) =>
                            `${b.ticker} ${b.expiry} (${b.sdBeforeBp.toFixed(0)}→${b.sdAfterBp.toFixed(0)}bp)`,
                        )
                        .join(", ")}`
                    : "")
                }
                className="min-w-0 flex-1 truncate text-left text-[11px] text-slate-300 hover:text-slate-100"
              >
                <span className="font-medium text-slate-100">{c.ticker}</span>{" "}
                <span className="font-mono text-[10px] text-slate-500">{c.expiry}</span>
              </button>
              <span
                className="shrink-0 font-mono text-[10px] text-emerald-400"
                title="Share of the universe's remaining weighted ATM variance this one quote removes"
              >
                −{c.totalVarReductionPct.toFixed(1)}% σ²
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
