// Global keyboard shortcuts of the workbench shell (UI SHELL v2, S5). The
// chords are the ones documented in lib/shortcuts.ts. Typing contexts
// (inputs, selects, textareas, contentEditable) are left alone except for
// Esc; the smile-editing keys stay in useSmileShortcuts (Parametric lens).
import { useEffect } from "react";
import { ACTIVITIES, useWorkbench } from "./workbench";
import { useWorkspaceFile } from "./workspaceFile";
import { useSnapshotFile } from "./snapshotFile";
import { useHelp } from "./help";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function useShellShortcuts(): void {
  const wb = useWorkbench();
  const ws = useWorkspaceFile();
  const snap = useSnapshotFile();
  const help = useHelp();
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // Esc: close the open dialog (Dialog.tsx handles its own Esc too; this
      // covers the dialog-less popovers via their own backdrops) — or end the
      // Walkthrough when it is running.
      if (e.key === "Escape") {
        if (help.tour.active) {
          help.endTour();
          e.preventDefault();
          return;
        }
        if (wb.dialog !== null) {
          wb.closeDialog();
          e.preventDefault();
        }
        return;
      }
      // F1 — Help for this view (HELP CENTER ARC); the browser's own F1 help
      // is suppressed by preventDefault in Chromium. Works while typing too.
      if (e.key === "F1" && !e.ctrlKey && !e.altKey && !e.metaKey) {
        help.openContextHelp();
        e.preventDefault();
        return;
      }
      if (isTyping(e.target)) return;
      // Ctrl+Shift+/ (Ctrl+?) — Ask @Vol-Fitter.
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && !e.altKey && (e.key === "?" || e.code === "Slash")) {
        help.openHelp({ page: "ask" });
        e.preventDefault();
        return;
      }

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
      // Snapshot file (wave 3, A2): Ctrl+Alt+S.
      if ((e.ctrlKey || e.metaKey) && e.altKey && !e.shiftKey && e.code === "KeyS") {
        void snap.saveSnapshot(); e.preventDefault(); return;
      }
      if ((e.ctrlKey || e.metaKey) && !e.altKey) {
        if (e.code === "KeyB" && !e.shiftKey) {
          // Hide when shown; otherwise show AND focus the tree (keyboard nav).
          if (wb.layout.nodesPane) wb.setLayout({ nodesPane: false });
          else wb.focusNodesPane();
          e.preventDefault();
          return;
        }
        if (e.key === "," && !e.shiftKey) { wb.openDialog("options"); e.preventDefault(); return; }
        if (e.code === "KeyP" && !e.shiftKey) { wb.openDialog("quickopen"); e.preventDefault(); return; }
        // Command palette (wave 3, C4): Ctrl+K, or VS Code's Ctrl+Shift+P.
        if ((e.code === "KeyK" && !e.shiftKey) || (e.code === "KeyP" && e.shiftKey)) {
          wb.openDialog("commands"); e.preventDefault(); return;
        }
        if (e.key === "/" && !e.shiftKey) { help.openHelp({ page: "shortcuts" }); e.preventDefault(); return; }
        if (e.code === "KeyU" && e.shiftKey) { wb.openDialog("universe"); e.preventDefault(); return; }
        // Split editors (wave 3, C3 + third group): Ctrl+\ adds a group (at
        // three, folds back to one); Ctrl+Shift+\ splits DOWN from one group.
        if (e.code === "Backslash") { if (e.shiftKey) wb.splitDown(); else wb.toggleSplit(); e.preventDefault(); return; }
        // Workspace files (wave 3, A1): Ctrl+O open · Ctrl+S save · Ctrl+Shift+S save as.
        if (e.code === "KeyO" && !e.shiftKey) { void ws.openPicker(); e.preventDefault(); return; }
        if (e.code === "KeyS") { void (e.shiftKey ? ws.saveAs() : ws.save()); e.preventDefault(); return; }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [wb, ws, snap, help]);
}
