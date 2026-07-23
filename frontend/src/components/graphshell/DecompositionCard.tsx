// Node decomposition card (P6 V2): the four-part explanation of a layered
// dynamic-harmonic mark —
//
//   mark == baseline (transported prior) + systematic (directed parents β·m)
//         + residual (the node's OWN persistent dislocation u)
//         + harmonic (reciprocal completion)
//
// — the V0 exit-gate identity, rendered as signed contribution rows with a
// proportional diverging bar each. Header chips: the boundary class (§4.2/
// §7.4) and, when today's certified print measured the residual, the §12.2
// residual-surprise χ. The residual row carries the memory's age. Renders
// ONLY when the run's wire carried the V0 fields (layered mode); the parent
// mounts it unconditionally and this component self-hides otherwise.
import type { ExtrapolateNode } from "../../state/useGraphExtrapolation";

/** Boundary-class chip copy (framework §4.2 classes + the unobserved case). */
const BOUNDARY: Record<string, { label: string; cls: string; title: string }> = {
  fresh_certified: {
    label: "clamped boundary",
    cls: "bg-emerald-500/15 text-emerald-300",
    title:
      "Fresh certified observation (age ≤ clampMaxAgeDays): the node is a " +
      "Dirichlet boundary — its mark is pinned to the observation and " +
      "information flows outward only (framework §7.4).",
  },
  soft_stale: {
    label: "stale · soft anchor",
    cls: "bg-amber-500/15 text-amber-300",
    title:
      "Stale observation: demoted to a soft aged anchor that COMPETES with " +
      "the parent-side prediction instead of clamping (framework §4.2).",
  },
  unobserved: {
    label: "unobserved",
    cls: "bg-surface-800 text-slate-500",
    title:
      "No observation today: the mark is completed from the directed " +
      "parents and the reciprocal harmonic layer.",
  },
};

/** χ chip tone: |χ|>2 loud dislocation, |χ|>1 notable, else quiet. */
function chiTone(chi: number): string {
  const a = Math.abs(chi);
  if (a > 2) return "bg-rose-500/15 text-rose-300";
  if (a > 1) return "bg-amber-500/15 text-amber-300";
  return "bg-surface-800 text-slate-400";
}

const fmtBp = (bp: number) => `${bp >= 0 ? "+" : ""}${bp.toFixed(1)} bp`;

/** One signed contribution row: label, diverging bar (width ∝ |bp|), value. */
function PartRow({
  label,
  title,
  bp,
  maxAbs,
  note,
}: {
  label: string;
  title: string;
  bp: number;
  maxAbs: number;
  note?: string;
}) {
  const width = maxAbs > 0 ? Math.max(4, Math.round((Math.abs(bp) / maxAbs) * 56)) : 4;
  return (
    <div className="flex items-center gap-2 py-0.5 text-[11px]" title={title}>
      <span className="w-24 shrink-0 text-slate-500">
        {label}
        {note !== undefined && <span className="ml-1 text-[9px] text-slate-600">{note}</span>}
      </span>
      <span
        className={`h-1.5 shrink-0 rounded-sm ${bp >= 0 ? "bg-emerald-500/60" : "bg-rose-500/60"}`}
        style={{ width }}
      />
      <span className="ml-auto text-right font-mono text-slate-200">{fmtBp(bp)}</span>
    </div>
  );
}

export default function DecompositionCard({ node }: { node: ExtrapolateNode }) {
  const s = node.systematicAtmVol;
  const u = node.residualAtmVol;
  const h = node.harmonicAtmVol;
  if (s == null || u == null || h == null) return null;
  const [sBp, uBp, hBp] = [s * 1e4, u * 1e4, h * 1e4];
  const maxAbs = Math.max(Math.abs(sBp), Math.abs(uBp), Math.abs(hBp));
  const sumBp = sBp + uBp + hBp;
  const boundary =
    node.boundaryClass != null ? BOUNDARY[node.boundaryClass] : undefined;
  const chi = node.residualSurpriseAtm;

  return (
    <div
      data-testid="decomposition"
      className="mb-3 rounded-md border border-slate-800 bg-surface-800/50 p-2"
    >
      <div className="mb-1 flex items-center gap-1.5">
        <span
          className="text-[10px] font-semibold uppercase tracking-wide text-slate-500"
          title="Layered dynamic-harmonic decomposition — the V0 exit-gate identity: mark = baseline + systematic + residual + harmonic"
        >
          Decomposition
        </span>
        {boundary !== undefined && (
          <span
            className={`rounded px-1.5 py-0.5 text-[9px] uppercase tracking-wide ${boundary.cls}`}
            title={boundary.title}
          >
            {boundary.label}
          </span>
        )}
        {chi != null && (
          <span
            className={`ml-auto rounded px-1.5 py-0.5 font-mono text-[9px] ${chiTone(chi)}`}
            title="Residual surprise χ = (e − u)/√(Var e + Var u) (framework §12.2): how far today's cut measurement sits from the stored residual memory, in σ. |χ| > 2 = loud dislocation."
          >
            χ {chi >= 0 ? "+" : ""}
            {chi.toFixed(1)}
          </span>
        )}
      </div>

      <div
        className="flex items-baseline justify-between gap-2 py-0.5 text-[11px]"
        title="Baseline: the transported prior this node starts from — the increments below are relative to it"
      >
        <span className="text-slate-500">baseline (prior)</span>
        <span className="text-right font-mono text-slate-200">
          {(node.priorAtmVol * 100).toFixed(1)}%
        </span>
      </div>
      <PartRow
        label="systematic"
        title="Systematic: the directed parents' prediction β·m — what this node should mark GIVEN its informers (framework §6.3)"
        bp={sBp}
        maxAbs={maxAbs}
      />
      <PartRow
        label="residual"
        note={
          node.residualAgeDays != null
            ? `· ${node.residualAgeDays.toFixed(1)}d`
            : undefined
        }
        title="Residual: the node's OWN persistent dislocation u carried through time (half-life decay) — memory of where it last printed vs its parents (framework §6.3/D2)"
        bp={uBp}
        maxAbs={maxAbs}
      />
      <PartRow
        label="harmonic"
        title="Harmonic: the reciprocal completion layer's adjustment on top of the directed prediction (framework §7)"
        bp={hBp}
        maxAbs={maxAbs}
      />

      <div
        className="mt-1 flex items-baseline justify-between gap-2 border-t border-slate-800 pt-1 text-[11px]"
        title="The identity locked at the V0 exit gate: mark = baseline + systematic + residual + harmonic"
      >
        <span className="text-slate-500">mark</span>
        <span className="text-right font-mono text-slate-200">
          {(node.postAtmVol * 100).toFixed(1)}%{" "}
          <span className="text-slate-500">(Σ {fmtBp(sumBp)})</span>
        </span>
      </div>
    </div>
  );
}
