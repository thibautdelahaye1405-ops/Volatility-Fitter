// Chrome of the right-hand column's stacked cards (lib/asideSizes): the card
// shell sized by the shared focus, its header with the expand / fold toggle,
// and the compact-row readout. Every card of the Parametric and Local Vol
// asides — Spot move, Variance swap, Fit diagnostics — is built from these
// three pieces so the column reads as one instrument:
//   S   <AsideHeader> alone: title · badge · the readout as the expand button
//   M   header (toggle = expand) + <AsideBody> with the working controls
//   L   header (toggle = fold back) + <AsideBody> with everything; the body
//       scrolls if the column is short, the two compact rows never leave.
import type { ReactNode } from "react";
import { ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { asideCardShrinks } from "../lib/asideSizes";
import type { AsidePanelId, AsideSize } from "../lib/asideSizes";
import { cardClass } from "../lib/ui";

/** One card of the column. Compact / standard cards keep their natural
 *  height; the expanded card (and the standard diagnostics card, last in the
 *  column) may shrink so nothing above it is pushed off screen. */
export function AsideCard({ id, size, children }: {
  id: AsidePanelId; size: AsideSize; children: ReactNode;
}) {
  return (
    <section
      data-aside-panel={id}
      data-aside-size={size}
      className={[
        cardClass,
        "flex flex-col",
        size === "S" ? "px-4 py-2" : "p-4",
        asideCardShrinks(size, id) ? "min-h-24 shrink" : "shrink-0",
      ].join(" ")}
    >
      {children}
    </section>
  );
}

/** The scrolling body under the header (standard and expanded sizes). */
export function AsideBody({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`min-h-0 flex-1 overflow-y-auto ${className}`}>{children}</div>;
}

const toggleButton =
  "flex h-5 w-5 shrink-0 items-center justify-center rounded text-slate-500 transition-colors " +
  "hover:bg-surface-800 hover:text-slate-200";

interface AsideHeaderProps {
  /** Card title (the <h3>). */
  title: string;
  size: AsideSize;
  /** Expand / fold; absent when the card is rendered outside the column. */
  onToggle?: () => void;
  /** Inline marker beside the title (stale, streaming dot). */
  badge?: ReactNode;
  /** Right-hand content at the standard / expanded sizes (a chip, a readout). */
  right?: ReactNode;
  /** The compact row's one-line readout — it IS the expand button. */
  summary?: ReactNode;
  /** What expanding reveals, for the toggle's tooltip. */
  expandTip: string;
}

/** Card header: title + badge at the left, the right-hand content and the
 *  size toggle at the right. At the compact size the readout replaces the
 *  right-hand content and doubles as the expand button. */
export function AsideHeader({ title, size, onToggle, badge, right, summary, expandTip }: AsideHeaderProps) {
  const expandTitle = `Expand — ${expandTip} (the other cards compress)`;
  return (
    <div className={["flex min-w-0 items-center justify-between gap-2", size === "S" ? "" : "mb-1"].join(" ")}>
      <h3 className="flex shrink-0 items-center gap-1.5 text-sm font-semibold text-slate-100">
        {title}
        {badge}
      </h3>
      <span className="flex min-w-0 items-center gap-1.5">
        {size === "S" ? (
          <button
            type="button"
            onClick={onToggle}
            disabled={!onToggle}
            title={expandTitle}
            aria-label={`Expand ${title}`}
            className="flex min-w-0 items-center gap-1.5 rounded font-mono text-[10px] text-slate-400 transition-colors enabled:hover:text-slate-100"
          >
            <span className="truncate">{summary}</span>
            <ChevronsUpDown size={12} strokeWidth={1.75} className="shrink-0" />
          </button>
        ) : (
          <>
            {right}
            {onToggle && (
              <button
                type="button"
                onClick={onToggle}
                title={size === "L" ? "Back to the standard size — all three cards" : expandTitle}
                aria-label={size === "L" ? `Shrink ${title}` : `Expand ${title}`}
                className={toggleButton}
              >
                {size === "L"
                  ? <ChevronsDownUp size={12} strokeWidth={1.75} />
                  : <ChevronsUpDown size={12} strokeWidth={1.75} />}
              </button>
            )}
          </>
        )}
      </span>
    </div>
  );
}
