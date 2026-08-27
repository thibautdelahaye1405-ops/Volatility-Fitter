// Global keyboard shortcuts of the workbench shell (UI SHELL v2, S5). The
// chords are the ones documented in lib/shortcuts.ts. Typing contexts
// (inputs, selects, textareas, contentEditable) are left alone except for
// Esc; the smile-editing keys stay in useSmileShortcuts (Parametric lens).
import { useEffect } from "react";
import { ACTIVITIES, useWorkbench } from "./workbench";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function useShellShortcuts(): void {
  const wb = useWorkbench();
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Esc: close the open dialog (Dialog.tsx handles its own Esc too; this
      // covers the dialog-less popovers via their own backdrops).
      if (e.key === "Escape") {
        if (wb.dialog !== null) {
          wb.closeDialog();
          e.preventDefault();
        }
        return;
      }
      if (isTyping(e.target)) return;

      // Alt+1…5 — lens switch (Ctrl+digits are browser-reserved).
      if (e.altKey && !e.ctrlKey && !e.metaKey && /^Digit[1-5]$/.test(e.code)) {
        const idx = Number(e.code.slice(5)) - 1;
        const a = ACTIVITIES[idx];
        if (a) {
          wb.setActivity(a.id);
          e.preventDefault();
        }
        return;
      }
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        if (e.key === "ArrowLeft") { wb.cycleTab(-1); e.preventDefault(); return; }
        if (e.key === "ArrowRight") { wb.cycleTab(1); e.preventDefault(); return; }
        if (e.code === "KeyW") {
          if (wb.activeTab) wb.closeTab(wb.activeTab.key);
          e.preventDefault();
          return;
        }
      }
      if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        if (e.code === "KeyB" && !e.shiftKey) {
          wb.setLayout({ nodesPane: !wb.layout.nodesPane });
          e.preventDefault();
          return;
        }
        if (e.key === "," && !e.shiftKey) { wb.openDialog("options"); e.preventDefault(); return; }
        if (e.code === "KeyP" && !e.shiftKey) { wb.openDialog("quickopen"); e.preventDefault(); return; }
        if (e.key === "/" && !e.shiftKey) { wb.openDialog("shortcuts"); e.preventDefault(); return; }
        if (e.code === "KeyU" && e.shiftKey) { wb.openDialog("universe"); e.preventDefault(); return; }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [wb]);
}
