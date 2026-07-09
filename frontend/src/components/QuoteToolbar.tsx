// Compact quote-editing toolbar for the Smile Viewer chart header.
// Icon + label chips mirroring the keyboard shortcuts (Del exclude,
// Ctrl+Z/Y undo/redo); all disabled in mock mode, where there is no fit
// session to edit.
import { Ban, RotateCcw, Undo2, Redo2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { QuoteBand } from "../lib/mockData";

interface QuoteToolbarProps {
  /** Currently selected quote (resolved by stable index), or null. */
  selectedQuote: QuoteBand | null;
  canUndo: boolean;
  canRedo: boolean;
  /** True when at least one quote is excluded or amended. */
  canReset: boolean;
  /** Editing requires the live backend. */
  live: boolean;
  onToggleExclude: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onReset: () => void;
}

/** Small bordered chips, matching the top-bar action buttons.
 *  Exported so siblings of this toolbar (e.g. Save prior) match exactly. */
export const toolbarButtonClass =
  "flex items-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2 py-1 " +
  "text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** One icon + label toolbar chip. */
function Chip({
  icon: Icon,
  label,
  disabled,
  title,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  disabled: boolean;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button className={toolbarButtonClass} disabled={disabled} title={title} onClick={onClick}>
      <Icon size={12} strokeWidth={1.75} className="opacity-80" />
      {label}
    </button>
  );
}

export default function QuoteToolbar({
  selectedQuote,
  canUndo,
  canRedo,
  canReset,
  live,
  onToggleExclude,
  onUndo,
  onRedo,
  onReset,
}: QuoteToolbarProps) {
  // One shared tooltip explains why everything is greyed out on mock data.
  const offlineTitle = live ? undefined : "requires live backend";
  return (
    <div className="flex items-center gap-1.5">
      <Chip
        icon={Ban}
        label={selectedQuote?.excluded ? "Restore" : "Exclude"}
        disabled={!live || selectedQuote === null}
        title={offlineTitle ?? "Exclude / restore the selected quote (Del)"}
        onClick={onToggleExclude}
      />
      <Chip
        icon={Undo2}
        label="Undo"
        disabled={!live || !canUndo}
        title={offlineTitle ?? "Undo (Ctrl+Z)"}
        onClick={onUndo}
      />
      <Chip
        icon={Redo2}
        label="Redo"
        disabled={!live || !canRedo}
        title={offlineTitle ?? "Redo (Ctrl+Y)"}
        onClick={onRedo}
      />
      <Chip
        icon={RotateCcw}
        label="Reset edits"
        disabled={!live || !canReset}
        title={offlineTitle ?? "Drop every exclusion / amendment"}
        onClick={onReset}
      />
    </div>
  );
}
