// Presentation helpers for EdgeMatrixEditor, split out to respect the
// 400-line file policy: shared class strings, the heatmap tint, the CSV blob
// download, the per-cell inline editor popover and the paste-TSV sub-panel.
// The editor owns the grid state; everything here is presentational.
import { useState } from "react";
import type { CSSProperties } from "react";
import type { MatrixCell } from "../lib/edgeMatrix";

export const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

export const numCls =
  "w-16 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-100 outline-none focus:border-accent-500";

/** Heatmap tint: background opacity scales with weight / max weight — accent
 *  off-diagonal, amber for the diagonal (calendar). color-mix keeps the
 *  accent themeable (it is a CSS variable re-skinned per data-theme). */
export function heatStyle(
  cell: MatrixCell | undefined,
  diagonal: boolean,
  maxWeight: number,
): CSSProperties | undefined {
  if (cell === undefined || cell.weight <= 0 || maxWeight <= 0) return undefined;
  const pct = Math.round(6 + 34 * Math.min(1, cell.weight / maxWeight));
  const base = diagonal ? "#f59e0b" : "var(--color-accent-500)";
  return { backgroundColor: `color-mix(in srgb, ${base} ${pct}%, transparent)` };
}

/** Client-side CSV download with a dated filename. */
export function downloadCsv(text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `edge-matrix-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

interface CellPopoverProps {
  /** Current cell value (the caller resolves defaults for empty cells). */
  cell: MatrixCell;
  diagonal: boolean;
  /** Live write-through: every input change updates the grid immediately. */
  onChange: (cell: MatrixCell) => void;
  onClear: () => void;
  onClose: () => void;
}

/** Small inline editor anchored under the clicked cell. A fixed transparent
 *  scrim behind it (TopBar dropdown pattern) closes on click-away; Escape and
 *  focus leaving the popover close it too. */
export function CellPopover({ cell, diagonal, onChange, onClear, onClose }: CellPopoverProps) {
  return (
    <>
      <button
        className="fixed inset-0 z-20 cursor-default"
        tabIndex={-1}
        aria-label="Close cell editor"
        onClick={onClose}
      />
      <div
        className="absolute left-1/2 top-full z-30 w-40 -translate-x-1/2 space-y-1.5 rounded-md border border-slate-700 bg-surface-800 p-2 text-left shadow-lg shadow-black/40"
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.stopPropagation();
            onClose();
          }
        }}
        onBlur={(e) => {
          const next = e.relatedTarget instanceof Node ? e.relatedTarget : null;
          if (!e.currentTarget.contains(next)) onClose();
        }}
      >
        <label className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
          weight
          <input
            autoFocus
            type="number"
            step={0.5}
            value={cell.weight}
            className={numCls}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) onChange({ ...cell, weight: v });
            }}
          />
        </label>
        <label className="flex items-center justify-between gap-2 text-[10px] text-slate-400">
          β
          <input
            type="number"
            step={0.1}
            value={cell.beta}
            className={numCls}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) onChange({ ...cell, beta: v });
            }}
          />
        </label>
        {/* The diagonal (own calendar chain) is symmetric by construction. */}
        {!diagonal && (
          <label className="flex items-center gap-1.5 text-[10px] text-slate-400">
            <input
              type="checkbox"
              checked={cell.symmetric}
              onChange={(e) => onChange({ ...cell, symmetric: e.target.checked })}
              className="accent-accent-500"
            />
            symmetric ⇄
          </label>
        )}
        <div className="flex items-center justify-between pt-0.5">
          <button className="text-[10px] text-rose-400/80 hover:text-rose-300" onClick={onClear}>
            Clear
          </button>
          <button className="text-[10px] text-slate-400 hover:text-slate-200" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </>
  );
}

interface PasteTsvPanelProps {
  errors: string[];
  busy: boolean;
  onApply: (text: string) => void;
  onCancel: () => void;
}

/** Textarea sub-panel for pasting a spreadsheet matrix; parse errors from the
 *  last apply render inline below it. */
export function PasteTsvPanel({ errors, busy, onApply, onCancel }: PasteTsvPanelProps) {
  const [text, setText] = useState("");
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <p className="shrink-0 text-[11px] text-slate-500">
        Header row = destination tickers; each body row = source ticker + weights
        (tab- or comma-separated — a spreadsheet paste works as-is). Blank or 0 = no
        rule; equal mirrored cells collapse to one symmetric pair.
      </p>
      <textarea
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        placeholder={"\tSPY\tQQQ\nSPY\t2\t3\nQQQ\t3\t1"}
        className="min-h-0 flex-1 resize-none rounded-md border border-slate-700 bg-surface-800 p-2 font-mono text-[11px] text-slate-100 outline-none focus:border-accent-500"
      />
      {errors.length > 0 && (
        <ul className="max-h-24 shrink-0 overflow-y-auto text-[10px] text-amber-400/80">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
      <div className="flex shrink-0 items-center gap-1.5">
        <button className={btn} disabled={busy || text.trim() === ""} onClick={() => onApply(text)}>
          Apply
        </button>
        <button className={btn} disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
