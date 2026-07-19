// Message-operator knobs (message arc P5, spec §18.4 / §20.1): the amplitude
// SHAPE (alphaT) and LEVEL (ρ presets: desk full force / learned day-horizon
// targets / custom), plus the §9.2 calendar precision family and the cross
// precision scale. Rendered only when the propagation mode is
// "precision_messages"; pure presentation — state lives in useGraph params.
import { AMPLITUDE_PRESETS } from "../lib/messagePreview";
import type { CalendarDecay, SolverParams } from "../state/useGraph";

interface MessagePanelProps {
  params: SolverParams;
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
}

const rowLabel = "text-xs text-slate-400";
const numCls =
  "w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right " +
  "font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500";
const selCls =
  "rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 font-mono " +
  "text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500";

type PresetKey = keyof typeof AMPLITUDE_PRESETS | "custom";

/** Which preset the current amplitudes correspond to ("custom" when neither). */
function presetOf(params: SolverParams): PresetKey {
  for (const [key, v] of Object.entries(AMPLITUDE_PRESETS)) {
    if (params.ampCal === v.ampCal && params.ampCross === v.ampCross)
      return key as PresetKey;
  }
  return "custom";
}

function NumberRow({
  label,
  title,
  value,
  step,
  onChange,
}: {
  label: string;
  title: string;
  value: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-2 flex items-center justify-between" title={title}>
      <span className={rowLabel}>{label}</span>
      <input
        type="number"
        step={step}
        value={value}
        onChange={(e) => {
          const v = e.target.valueAsNumber;
          if (Number.isFinite(v)) onChange(v);
        }}
        className={numCls}
      />
    </div>
  );
}

export default function MessagePanel({ params, setParam }: MessagePanelProps) {
  const preset = presetOf(params);
  return (
    <section className="border-t border-slate-800 pt-3">
      <h3 className="mb-2 text-sm font-semibold text-slate-100">Message operator</h3>

      {/* Amplitude LEVEL ρ: desk full force vs the learned day-horizon targets */}
      <div
        className="mb-2 flex items-center justify-between"
        title={
          "Amplitude level ρ per relation class, mechanized via the innovation anchor. " +
          "Desk = full configured force (ρ=1); Learned = the day-horizon single-source " +
          "targets (calendar 0.23, cross 0.39 — corroborating sources lift the transfer)."
        }
      >
        <span className={rowLabel}>Amplitude preset</span>
        <select
          className={selCls}
          value={preset}
          onChange={(e) => {
            const key = e.target.value as PresetKey;
            if (key !== "custom") {
              setParam("ampCal", AMPLITUDE_PRESETS[key].ampCal);
              setParam("ampCross", AMPLITUDE_PRESETS[key].ampCross);
            }
          }}
        >
          <option value="desk">desk (full force)</option>
          <option value="learned">learned</option>
          <option value="custom" disabled={preset !== "custom"}>
            custom
          </option>
        </select>
      </div>
      <NumberRow
        label="ρ calendar"
        title="Calendar amplitude level (1 = full force; learned day-horizon ≈ 0.23)."
        value={params.ampCal}
        step={0.01}
        onChange={(v) => setParam("ampCal", Math.min(Math.max(v, 0.01), 1))}
      />
      <NumberRow
        label="ρ cross-asset"
        title="Cross-class amplitude level (1 = full force; learned single-source ≈ 0.39)."
        value={params.ampCross}
        step={0.01}
        onChange={(v) => setParam("ampCross", Math.min(Math.max(v, 0.01), 1))}
      />

      {/* Amplitude SHAPE alphaT */}
      <NumberRow
        label="Calendar shape αT"
        title="Maturity-shape exponent: β = (T_informer/T_receiver)^αT. 1.0 = constant total-variance injection (locked default)."
        value={params.alphaT}
        step={0.25}
        onChange={(v) => setParam("alphaT", v)}
      />

      {/* §9.2 calendar precision family */}
      <div
        className="mb-2 flex items-center justify-between"
        title="Calendar relation-precision family: p = scale / (ε + √|ΔT|) by default."
      >
        <span className={rowLabel}>Calendar decay</span>
        <select
          className={selCls}
          value={params.calDecay}
          onChange={(e) => setParam("calDecay", e.target.value as CalendarDecay)}
        >
          <option value="inverse_sqrt_gap">inverse √gap</option>
          <option value="constant">constant</option>
          <option value="log_distance">log distance</option>
        </select>
      </div>
      <NumberRow
        label="Calendar precision p₀"
        title="Calendar precision scale (1/vol²; Phase-0 empirical seed 1700)."
        value={params.calPrecision}
        step={100}
        onChange={(v) => setParam("calPrecision", Math.max(v, 1))}
      />
      <NumberRow
        label="Calendar ε (√years)"
        title="Caps the precision of near-identical expiries (Phase-0 seed 0.97)."
        value={params.calEpsilon}
        step={0.05}
        onChange={(v) => setParam("calEpsilon", Math.max(v, 0.01))}
      />
      <NumberRow
        label="Cross precision"
        title="Cross-relation message precision (1/vol²; Phase-0 index seed 13000)."
        value={params.crossPrecision}
        step={1000}
        onChange={(v) => setParam("crossPrecision", Math.max(v, 1))}
      />

      <p className="mt-1 text-[10px] text-slate-600">
        Signals cross edges at the configured amplitude; confidence decays with
        maturity distance. Arrows read informer → receiver.
      </p>
    </section>
  );
}
