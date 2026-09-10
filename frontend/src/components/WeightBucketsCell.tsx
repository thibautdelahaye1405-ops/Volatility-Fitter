// Quality lens · "Wgt" cell (quote-weighting arc rider, 2026-09-10): the fit's
// summed quote weight by standardized-moneyness band — deep put · put · ATM ·
// call · deep call (z = k / σ_atm√τ, ATM = ±0.5, deep beyond ±2) — as five
// bars whose heights are the shares of the total. The hover lists the shares,
// so a wing-heavy or ATM-only slice reads at a glance beside its RMS. The
// numbers come from the backend (QualityNode.weightBuckets: the same weights
// the Weights strip draws per quote, pooled).

const LABELS = ["deep put", "put", "ATM", "call", "deep call"] as const;

/** Five shares → "deep put 12% · put 30% · ATM 35% · call 18% · deep call 5%". */
export function weightBucketsTitle(shares: number[]): string {
  return shares.map((s, i) => `${LABELS[i]} ${Math.round(s * 100)}%`).join(" · ");
}

export default function WeightBucketsCell({ shares }: { shares: number[] | null | undefined }) {
  if (!shares || shares.length !== LABELS.length) return <span className="text-slate-600">—</span>;
  const peak = Math.max(...shares, 1e-9);
  return (
    <span
      className="inline-flex h-3 items-end gap-px align-middle"
      data-testid="weight-buckets"
      title={`Fit weight by moneyness band — ${weightBucketsTitle(shares)}`}
    >
      {shares.map((s, i) => (
        <span
          key={LABELS[i]}
          className={i === 2 ? "w-1.5 rounded-sm bg-accent-400/80" : "w-1.5 rounded-sm bg-slate-500/70"}
          style={{ height: `${Math.max(8, Math.round((s / peak) * 100))}%` }}
        />
      ))}
    </span>
  );
}
