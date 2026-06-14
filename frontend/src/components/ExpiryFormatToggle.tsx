// Compact expiry-format cycle button for the workspace headers (Phase 10
// follow-up). Clicking advances the global format; the face shows the current
// format's sample label. The Options tab hosts the full selector.
import { useExpiryFormat } from "../state/expiryFormat";
import { EXPIRY_FORMATS } from "../lib/expiryFormat";

export default function ExpiryFormatToggle() {
  const { format, cycle } = useExpiryFormat();
  const label = EXPIRY_FORMATS.find((f) => f.id === format)?.label ?? format;
  return (
    <button
      onClick={cycle}
      title="Cycle the expiry date format (set the default in Options)"
      className="flex items-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
    >
      <span className="text-slate-500">↻</span>
      <span className="font-mono">{label}</span>
    </button>
  );
}
