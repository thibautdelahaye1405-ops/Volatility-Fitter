// Small segmented button group, shared by the Smile workspace header
// controls (fit-mode selector, chart-view toggle). Generic over the
// option-id union so onChange stays fully typed at the call site.
interface SegmentedControlProps<T extends string> {
  options: readonly { id: T; label: string }[];
  value: T;
  onChange: (id: T) => void;
  /** "sm" = header height (text-xs), "xs" = compact (text-[11px]). */
  size?: "sm" | "xs";
}

export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  size = "sm",
}: SegmentedControlProps<T>) {
  const pad = size === "sm" ? "px-3 py-1.5 text-xs" : "px-2.5 py-1 text-[11px]";
  return (
    <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
      {options.map((opt) => {
        const active = opt.id === value;
        return (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={[
              pad,
              "font-medium transition-colors",
              active
                ? "bg-accent-600/25 text-accent-400"
                : "text-slate-400 hover:text-slate-200",
            ].join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
