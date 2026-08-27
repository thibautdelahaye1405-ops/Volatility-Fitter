// Per-tab view memory for a lens (UI SHELL v2 wave 3, C2).
//
// A lens keeps ONE local view state (today's per-lens behaviour: sub-view,
// axis mode, layers, …). With Layout ▸ "Remember view per tab" ON, the
// workbench also stores that state per (tab, lens): activating a tab whose
// memory exists restores it; every change writes it back; a tab without
// memory shows the lens's current state (so a restored / inherited tab feels
// continuous). Outside the shell (tests, legacy mounts) the hook is a plain
// useState with a patch setter.
import { useCallback, useState } from "react";
import { useOptionalWorkbench } from "./workbench";
import { useNodeScope } from "./nodeScope";

export function useLensViewMemory<T extends object>(
  lens: "parametric" | "localvol",
  defaults: T | (() => T),
): [T, (patch: Partial<T>) => void] {
  const wb = useOptionalWorkbench();
  const scope = useNodeScope(); // the enclosing editor group's tab (wave 3, C3)
  const [local, setLocal] = useState<T>(defaults);
  const key = scope !== null ? scope.key : (wb?.activeTab?.key ?? null);
  const remember = wb !== null && wb.layout.rememberView && key !== null;
  const stored = remember ? (wb.viewMemory[key]?.[lens] as Partial<T> | undefined) : undefined;
  const value: T = stored !== undefined ? { ...local, ...stored } : local;

  const patch = useCallback(
    (p: Partial<T>) => {
      // Fold the patch onto the DISPLAYED value (memory over local) so a
      // remembered tab never regresses to the lens's stale local state.
      const next = { ...value, ...p };
      setLocal(next);
      if (remember && wb !== null && key !== null) wb.setViewMemory(key, lens, next);
    },
    [remember, wb, key, lens, value],
  );
  return [value, patch];
}
