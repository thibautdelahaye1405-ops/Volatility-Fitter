// Grouped view switch shared by the Parametric and Local Vol lenses (UI SHELL
// v2 wave 2): the chart-card views split into NODE views (about the active
// tab's expiry — smile, density, compare, table) and TICKER views (the whole
// ladder — term, densities, stacked IV, surfaces). One segmented control per
// group with a tiny uppercase label, so both lenses read identically.
import SegmentedControl from "../SegmentedControl";

export interface ViewGroup<T extends string> {
  /** Tiny uppercase label before the group ("node" / "ticker"). */
  label: string;
  options: readonly { id: T; label: string }[];
}

export default function LensViewSwitch<T extends string>({
  groups,
  value,
  onChange,
}: {
  groups: ViewGroup<T>[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      {groups.map((g) => (
        <span key={g.label} className="flex items-center gap-1.5">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-600">
            {g.label}
          </span>
          <SegmentedControl options={g.options} value={value} onChange={onChange} size="xs" />
        </span>
      ))}
    </div>
  );
}
