// Shared crop windows + time-axis mode of the 3D surfaces (2026-09-08, the
// Compare tab's request: "make the sliders locked in sync so the two sheets
// are directly comparable"). A mesh with a `windowKey` reads and writes its
// strike window, maturity window and √T/T mode HERE, so every mesh under the
// same key crops and rescales together (the two Compare sheets share
// "localvol:compare", the way they already share a camera key). A mesh
// without a key keeps a local copy. Module store + useSyncExternalStore, not
// persisted: a window is tied to the grid it was made for (its extents key)
// and falls back to the full range when the grid changes.
import { useCallback, useState, useSyncExternalStore } from "react";
import type { TimeAxisMode } from "../lib/timeAxis";

/** One axis's brushed window, with the extents key of the grid it was made for. */
export interface AxisWindow {
  range: [number, number];
  key: string;
}

export interface SurfaceWindows {
  k: AxisWindow | null;
  t: AxisWindow | null;
  timeMode: TimeAxisMode;
}

export const DEFAULT_WINDOWS: SurfaceWindows = { k: null, t: null, timeMode: "sqrt" };

let windows: Record<string, SurfaceWindows> = {};
const listeners = new Set<() => void>();

function commit(next: Record<string, SurfaceWindows>): void {
  windows = next;
  listeners.forEach((l) => l());
}
function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
const getSnapshot = () => windows;
const getServerSnapshot = () => ({}) as Record<string, SurfaceWindows>;

/** Drop every shared window (tests). */
export function resetSurfaceWindows(): void {
  commit({});
}

/** [windows, patch] for a keyed (shared) or local (key undefined) window set. */
export function useSurfaceWindows(
  key: string | undefined,
): [SurfaceWindows, (patch: Partial<SurfaceWindows>) => void] {
  const all = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [local, setLocal] = useState<SurfaceWindows>(DEFAULT_WINDOWS);
  const patch = useCallback(
    (p: Partial<SurfaceWindows>) => {
      if (key === undefined) setLocal((prev) => ({ ...prev, ...p }));
      else commit({ ...windows, [key]: { ...(windows[key] ?? DEFAULT_WINDOWS), ...p } });
    },
    [key],
  );
  return [key === undefined ? local : (all[key] ?? DEFAULT_WINDOWS), patch];
}
