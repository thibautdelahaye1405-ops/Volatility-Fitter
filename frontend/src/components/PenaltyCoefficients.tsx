// Per-model optimization / penalty coefficients (ROADMAP: expose every
// calibration coefficient explicitly in Options). Edits the FitSettings draft
// owned by HyperparamPanel; model-specific groups grey out when their family
// isn't the active model (the coefficient still applies once selected). Each
// default equals the historical hardcoded constant.
import type { FitModel, FitSettings } from "./HyperparamPanel";

interface Props {
  draft: FitSettings;
  onChange: (next: FitSettings) => void;
  disabled: boolean;
}

const rowLabel = "text-xs text-slate-400";
const numInput =
  "w-20 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500 disabled:cursor-not-allowed";

export default function PenaltyCoefficients({ draft, onChange, disabled }: Props) {
  const set = (patch: Partial<FitSettings>) => onChange({ ...draft, ...patch });

  /** One numeric coefficient row, greyed when its model isn't active. */
  const Row = (
    label: string,
    title: string,
    field: keyof FitSettings,
    step: number,
    only?: FitModel,
  ) => {
    const off = disabled || (only !== undefined && draft.model !== only);
    return (
      <div className={`mb-1.5 flex items-center justify-between ${off && !disabled ? "opacity-40" : ""}`}>
        <span className={rowLabel} title={title}>
          {label}
        </span>
        <input
          type="number"
          step={step}
          min={0}
          value={draft[field] as number}
          disabled={off}
          onChange={(e) => set({ [field]: Number(e.target.value) } as Partial<FitSettings>)}
          className={numInput}
        />
      </div>
    );
  };

  return (
    <div className="mb-3 border-t border-slate-800 pt-3">
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Penalty &amp; barrier coefficients
      </h4>

      {/* LQD */}
      {Row("LQD A_R barrier centre", "A_R soft-barrier centre (eq. right_admissible)", "barrierCenter", 0.05, "lqd")}
      {Row("LQD A_R barrier scale", "A_R soft-barrier steepness", "barrierScale", 5, "lqd")}

      {/* SVI */}
      {Row("SVI no-arb penalty", "Soft no-arbitrage penalty weight (min-var + Lee wing)", "sviPenaltyWeight", 100, "svi")}
      {Row("SVI Lee slope max", "Lee wing-slope bound b(1+|ρ|) ≤ this", "leeSlopeMax", 0.1, "svi")}

      {/* Sigmoid */}
      {Row("SIV hat ridge", "Multi-Core SIV hat-amplitude ridge penalty", "sigmoidRidge", 0.01, "sigmoid")}

      {/* All models (band modes) */}
      {Row("Band mid anchor", "Mid-anchor weight in bid-ask / haircut modes (all models)", "midAnchorWeight", 0.01)}
    </div>
  );
}
