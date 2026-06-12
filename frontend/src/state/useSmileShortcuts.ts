// Global keyboard shortcuts of the Smile workspace, extracted from
// SmileViewer so the view stays under the file-size policy. Registered on
// window so the chart needs no focus; events originating from form controls
// are left alone. Esc clears the selection; everything else requires the
// live backend (mock mode has no fit session to edit).
import { useEffect } from "react";
import type { SmileData } from "../lib/mockData";
import type { EditAction, SmileSource } from "./useSmile";

interface ShortcutDeps {
  smile: SmileData | null;
  source: SmileSource;
  /** Stable `index` of the selected quote, or null. */
  selectedIndex: number | null;
  setSelectedIndex: (index: number | null) => void;
  applyEdit: (action: EditAction, index?: number, mid?: number) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

/**
 * Shortcuts: Esc deselect · Del/Backspace exclude-toggle · ↑/↓ amend the
 * selected mid (±0.1 vol pt, ×5 with Shift) · Ctrl+Z / Ctrl+Shift+Z /
 * Ctrl+Y undo & redo.
 */
export function useSmileShortcuts({
  smile,
  source,
  selectedIndex,
  setSelectedIndex,
  applyEdit,
  undo,
  redo,
}: ShortcutDeps): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = e.target instanceof HTMLElement ? e.target.tagName : "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "Escape") {
        setSelectedIndex(null);
        return;
      }
      if (source !== "live") return; // edits require the live backend
      if (e.ctrlKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) void redo();
        else void undo();
        return;
      }
      if (e.ctrlKey && (e.key === "y" || e.key === "Y")) {
        e.preventDefault();
        void redo();
        return;
      }
      // Remaining shortcuts act on the selected quote of the current smile.
      const quote =
        smile !== null && selectedIndex !== null
          ? smile.quotes.find((q) => q.index === selectedIndex)
          : undefined;
      if (quote === undefined) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        void applyEdit(quote.excluded ? "include" : "exclude", quote.index);
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        // Nudge the mid IV from its CURRENT value: ±0.1 vol pt, ×5 w/ Shift.
        const step = (e.shiftKey ? 0.005 : 0.001) * (e.key === "ArrowUp" ? 1 : -1);
        void applyEdit("amend", quote.index, quote.mid + step);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [smile, selectedIndex, setSelectedIndex, source, applyEdit, undo, redo]);
}
