// Per-model optimization / penalty coefficients (ROADMAP: expose every
// calibration coefficient explicitly in Options). Edits the lifted FitSettings
// draft via a partial-patch callback; only the ACTIVE model's coefficients
// render (the others keep their values and reappear when the model is
// selected). Each default equals the historical hardcoded constant.
//
// `group` selects which coefficients render so the Options tab can place the
// model-relevant penalties under "Model & hyperparameters" and the band
// mid-anchor (a calibration choice) under "Calibration".
import type { FitModel, FitSettings } from "./HyperparamPanel";

interface Props {
  group: "model" | "calibration";
  draft: FitSettings;
  onChange: (p: Partial<FitSettings>) => void;
  disabled: boolean;
}

const rowLabel = "text-xs text-slate-400";
const numInput =
  "w-20 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500 disabled:cursor-not-allowed";

export default function PenaltyCoefficients({ group, draft, onChange, disabled }: Props) {
  /** One numeric coefficient row. */
  const Row = (label: string, title: string, field: keyof FitSettings, step: number) => (
    <div className="mb-1.5 flex items-center justify-between">
      <span className={rowLabel} title={title}>
        {label}
      </span>
      <input
        type="number"
        step={step}
        min={0}
        value={draft[field] as number}
        disabled={disabled}
        onChange={(e) => onChange({ [field]: Number(e.target.value) } as Partial<FitSettings>)}
        className={numInput}
      />
    </div>
  );

  if (group === "calibration") {
    // Band mid anchor applies to every model in the band fit modes.
    return (
      <div className="mb-1">
        {Row("Band mid anchor", "Mid-anchor weight in bid-ask / haircut modes (all models)", "midAnchorWeight", 0.01)}
      </div>
    );
  }

  // group === "model": only the ACTIVE family's penalty / barrier coefficients.
  const coordsRow = (
    <div className="mb-1.5 flex items-center justify-between" key="lqdCoords">
      <span
        className={rowLabel}
        title="LQD optimization chart: Logistic (default) solves in (log A_L, logit A_R, body) - body modes are endpoint-neutral AND the A_R < 1 wall is unreachable, so the solve is genuinely unconstrained. Endpoint is the same without the logit; L/R is the historical raw vector. Same fitted smile in all three, to solver tolerance."
      >
        LQD solve coordinates
      </span>
      <select
        value={draft.lqdCoords}
        disabled={disabled}
        onChange={(e) => onChange({ lqdCoords: e.target.value as "lr" | "endpoint" | "logistic" })}
        className={numInput + " w-28"}
      >
        <option value="lr">L / R (raw)</option>
        <option value="endpoint">Endpoint</option>
        <option value="logistic">Logistic</option>
      </select>
    </div>
  );
  const rows: Record<FitModel, ReturnType<typeof Row>[]> = {
    lqd: [
      coordsRow,
      Row("LQD A_R barrier centre", "A_R soft-barrier centre (eq. right_admissible)", "barrierCenter", 0.05),
      Row("LQD A_R barrier scale", "A_R soft-barrier steepness", "barrierScale", 5),
    ],
    svi: [
      (
        <div className="mb-1.5 flex items-center justify-between" key="sviChart">
          <span
            className={rowLabel}
            title="SVI optimization chart (committee R3): Raw is the historical (a, b, ρ, m, s) vector with soft feasibility penalties; Structural solves in (β_L, β_R, k*, w*, κ*) — every iterate has a strictly positive variance floor and strictly Lee-clean wings, so the penalties are inert. Same fitted smile on clean quotes, to solver tolerance."
          >
            SVI solve chart
          </span>
          <select
            value={draft.sviChart}
            disabled={disabled}
            onChange={(e) => onChange({ sviChart: e.target.value as "raw" | "structural" })}
            className={numInput + " w-28"}
          >
            <option value="raw">Raw (a,b,ρ,m,s)</option>
            <option value="structural">Structural</option>
          </select>
        </div>
      ),
      Row("SVI no-arb penalty", "Soft no-arbitrage penalty weight (min-var + Lee wing); inert under the Structural chart", "sviPenaltyWeight", 100),
      Row("SVI Lee slope max", "Lee wing-slope cap b(1+|ρ|) ≤ this — buffered strictly under 2 (the boundary itself admits negative tail density)", "leeSlopeMax", 0.1),
    ],
    sigmoid: [
      (
        <div className="mb-1.5 flex items-center justify-between" key="mcsChart">
          <span
            className={rowLabel}
            title="MCS optimization chart (V3.1 rider): Raw is the historical base + kernels vector with soft feasibility penalties; Structural solves in the wing-admissible chart (the base's Lee wing slopes lifted against the slope cap — Lee-clean wings by construction, the SVI committee-arc precedent) but is ~20× slower at R=2. Default Raw until the benchmark adjudication flips it."
          >
            MCS solve chart
          </span>
          <select
            value={draft.mcsChart}
            disabled={disabled}
            onChange={(e) => onChange({ mcsChart: e.target.value as "raw" | "structural" })}
            className={numInput + " w-28"}
          >
            <option value="raw">Raw (base + kernels)</option>
            <option value="structural">Structural</option>
          </select>
        </div>
      ),
      Row("MCS hat ridge", "Multi-Core Sigmoid hat-amplitude ridge penalty", "sigmoidRidge", 0.01),
    ],
  };

  return (
    <div className="mb-3 border-t border-slate-800 pt-3">
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Penalty &amp; barrier coefficients
      </h4>
      {rows[draft.model]}
    </div>
  );
}
