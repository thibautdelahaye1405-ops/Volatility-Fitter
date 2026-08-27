// Strike-axis unit selector (UI SHELL v2 wave 2): a compact select that the
// lenses place in the chart-card FOOTER next to the x-axis, where the unit it
// changes actually lives — instead of in the toolbar. Generic over the option
// list so the Local Vol mesh (grid-native units) reuses it.
import { AXIS_MODE_OPTIONS } from "../../lib/axisModes";
import type { AxisMode } from "../../lib/axisModes";

export function AxisUnitSelect<T extends string>({
  value,
  options,
  onChange,
  title = "x-axis unit",
}: {
  value: T;
  options: readonly { id: T; label: string }[];
  onChange: (v: T) => void;
  title?: string;
}) {
  return (
    <label className="flex items-center gap-1.5 text-[10px] text-slate-600">
      <span className="uppercase tracking-wider">x-axis</span>
      <select
        className="rounded border border-slate-800 bg-surface-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300 outline-none hover:border-slate-600 focus:border-accent-500"
        value={value}
        title={title}
        onChange={(e) => onChange(e.target.value as T)}
      >
        {options.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
      </select>
    </label>
  );
}

/** The standard strike-axis modes (ln(K/F) / strike / %ATM / Δ / …). */
export default function AxisModeSelect({
  value,
  onChange,
}: {
  value: AxisMode;
  onChange: (m: AxisMode) => void;
}) {
  return (
    <AxisUnitSelect
      value={value}
      options={AXIS_MODE_OPTIONS}
      onChange={onChange}
      title="Strike-axis display mode"
    />
  );
}
