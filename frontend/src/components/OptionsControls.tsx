// Small presentational controls + the penalty catalogue used by the Options tab.
// Extracted from OptionsViewer to keep that file under the 400-line policy.

const segWrap = "flex overflow-hidden rounded-md border border-slate-700 bg-surface-800";
const numInput =
  "w-24 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** Penalty catalogue: description + formula + which knob sets its strength.
 *  `group` routes each row to the Model or the Calibration card. */
export const PENALTIES: { name: string; formula: string; strength: string; group: "model" | "calibration" }[] = [
  { name: "LQD high-order damping", formula: "λ · n^(2r) · aₙ²  (n ≥ 4)", strength: "Model: Damping λ · r", group: "model" },
  { name: "SVI min-variance", formula: "P · max(−(a + bσ√(1−ρ²)), 0)²", strength: "Model: SVI no-arb penalty", group: "model" },
  { name: "SVI Lee wing", formula: "P · max(b(1+|ρ|) − 2, 0)²", strength: "Model: SVI Lee slope max", group: "model" },
  { name: "Sigmoid amplitude ridge", formula: "ridge · Σ αᵣ²  (hat amplitudes)", strength: "Model: MCS hat ridge", group: "model" },
  { name: "Affine LV roughness", formula: "√λ · L(θ − θ_ref),  L = 2nd diff in (t, x)", strength: "Model: Grid roughness λ", group: "model" },
  { name: "Calendar slack (arb-fix)", formula: "w · Σ max(floor − Gᵢ(α), 0)²", strength: "Calibration: Calendar weight", group: "calibration" },
  { name: "Band hinge + mid anchor", formula: "max(m−ask,0)² + max(bid−m,0)² + w(m−mid)²", strength: "Calibration: Haircut · Band mid anchor", group: "calibration" },
];

/** Render the penalty catalogue filtered to one themed group. */
export function PenaltyTable({ group }: { group: "model" | "calibration" }) {
  const rows = PENALTIES.filter((p) => p.group === group);
  return (
    <div className="overflow-x-auto rounded-md border border-slate-800">
      <table className="w-full border-collapse text-left text-[11px]">
        <thead className="bg-surface-800 text-slate-400">
          <tr>
            <th className="px-3 py-1.5 font-medium">Penalty</th>
            <th className="px-3 py-1.5 font-medium">Term</th>
            <th className="px-3 py-1.5 font-medium">Strength</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60 text-slate-300">
          {rows.map((p) => (
            <tr key={p.name}>
              <td className="px-3 py-1.5 font-medium text-slate-200">{p.name}</td>
              <td className="px-3 py-1.5 font-mono text-slate-400">{p.formula}</td>
              <td className="px-3 py-1.5 text-slate-500">{p.strength}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A labelled checkbox toggle row. */
export function Toggle({
  label, hint, checked, disabled, onChange,
}: {
  label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 py-1.5">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 accent-accent-500"
      />
      <span>
        <span className="text-xs font-medium text-slate-200">{label}</span>
        <span className="block text-[10px] text-slate-500">{hint}</span>
      </span>
    </label>
  );
}

/** A segmented control bound to one of a small set of string values. */
export function Segmented<T extends string>({
  options, value, onChange, disabled,
}: {
  options: { id: T; label: string; title?: string }[];
  value: T; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <div className={segWrap}>
      {options.map((o) => (
        <button
          key={o.id}
          title={o.title}
          disabled={disabled}
          onClick={() => onChange(o.id)}
          className={[
            "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
            o.id === value ? "bg-accent-600/25 text-accent-400" : "text-slate-400 enabled:hover:text-slate-200",
          ].join(" ")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** A labelled numeric input row. */
export function NumberRow({
  label, value, step, disabled, onChange,
}: {
  label: string; value: number; step: number; disabled?: boolean; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number" step={step} min={0} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className={numInput}
      />
    </div>
  );
}
