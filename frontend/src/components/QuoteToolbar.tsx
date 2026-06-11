// Compact quote-editing toolbar for the Smile Viewer chart header.
// Buttons mirror the keyboard shortcuts (Del exclude, Ctrl+Z/Y undo/redo)
// and are all disabled in mock mode, where there is no fit session to edit.
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

/** Small bordered buttons, matching the fit-mode segmented control. */
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

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
      <button
        className={buttonClass}
        disabled={!live || selectedQuote === null}
        title={offlineTitle}
        onClick={onToggleExclude}
      >
        {selectedQuote?.excluded ? "Restore" : "Exclude"}
      </button>
      <button
        className={buttonClass}
        disabled={!live || !canUndo}
        title={offlineTitle}
        onClick={onUndo}
      >
        Undo
      </button>
      <button
        className={buttonClass}
        disabled={!live || !canRedo}
        title={offlineTitle}
        onClick={onRedo}
      >
        Redo
      </button>
      <button
        className={buttonClass}
        disabled={!live || !canReset}
        title={offlineTitle}
        onClick={onReset}
      >
        Reset edits
      </button>
    </div>
  );
}
