// Keyboard chords of the Graph lens (GRAPH ERGONOMICS ARC, E6): Delete /
// Backspace removes the selected relation, Escape clears the selection (or
// leaves Focus), Ctrl+Z / Ctrl+Y (Ctrl+Shift+Z) undo / redo the relation
// draft. Inert while a text control has the focus, so typing a search or a
// number never fires a chord.
import { useEffect } from "react";

interface GraphHotkeys {
  enabled: boolean;
  onDelete: () => void;
  onEscape: () => void;
  onUndo: () => void;
  onRedo: () => void;
}

/** True when the event target is a text-entry control. */
export function isTextTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return (
    tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable
  );
}

export function useGraphHotkeys({ enabled, onDelete, onEscape, onUndo, onRedo }: GraphHotkeys): void {
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (isTextTarget(e.target)) return;
      const ctrl = e.ctrlKey || e.metaKey;
      if (e.key === "Escape") {
        onEscape();
      } else if ((e.key === "Delete" || e.key === "Backspace") && !ctrl) {
        e.preventDefault();
        onDelete();
      } else if (ctrl && (e.key === "z" || e.key === "Z") && !e.shiftKey) {
        e.preventDefault();
        onUndo();
      } else if (ctrl && (e.key === "y" || e.key === "Y" || ((e.key === "z" || e.key === "Z") && e.shiftKey))) {
        e.preventDefault();
        onRedo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, onDelete, onEscape, onUndo, onRedo]);
}
