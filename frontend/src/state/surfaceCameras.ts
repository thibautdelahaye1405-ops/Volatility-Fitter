// Persisted 3D cameras per lens view (UI SHELL v2 wave 3, B1): the IV
// surface (Parametric), the LV mesh and the reconstructed IV mesh (Local
// Vol) each keep their yaw / pitch / zoom / pan under a key, so the view
// survives tab switches and reloads (localStorage) and rides workspace files
// (the shell blob reads / writes the whole map). Module store +
// useSyncExternalStore; a chart without a key keeps a local camera.
import { useCallback, useState, useSyncExternalStore } from "react";
import { DEFAULT_CAMERA, clampCamera } from "../lib/surfaceCamera";
import type { Camera } from "../lib/surfaceCamera";

const STORAGE_KEY = "volfit.surfaceCameras.v1";

let cameras: Record<string, Camera> = load();
const listeners = new Set<() => void>();

function load(): Record<string, Camera> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? restoreCameras(JSON.parse(raw)) : {};
  } catch {
    return {};
  }
}
function persist(): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(cameras)); } catch { /* best-effort */ }
}
function commit(next: Record<string, Camera>): void {
  cameras = next;
  persist();
  listeners.forEach((l) => l());
}
function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
const getSnapshot = () => cameras;
const getServerSnapshot = () => ({}) as Record<string, Camera>;

/** Validate a persisted / imported map (each entry clamped; junk dropped). */
export function restoreCameras(raw: unknown): Record<string, Camera> {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return {};
  const out: Record<string, Camera> = {};
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v !== "object" || v === null) continue;
    const c = v as Partial<Camera>;
    out[k] = clampCamera({
      yaw: Number(c.yaw), pitch: Number(c.pitch), zoom: Number(c.zoom),
      panX: Number(c.panX), panY: Number(c.panY),
    });
  }
  return out;
}

/** Whole-map access for the workspace shell blob. */
export function getSurfaceCameras(): Record<string, Camera> {
  return cameras;
}
export function setSurfaceCameras(raw: unknown): void {
  commit(restoreCameras(raw));
}

/** [camera, setCamera] for a keyed (persisted) or local (key undefined) camera. */
export function useSurfaceCamera(key: string | undefined): [Camera, (c: Camera) => void] {
  const all = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const [local, setLocal] = useState<Camera>(DEFAULT_CAMERA);
  const set = useCallback(
    (c: Camera) => {
      if (key === undefined) setLocal(c);
      else commit({ ...cameras, [key]: c });
    },
    [key],
  );
  return [key === undefined ? local : (all[key] ?? DEFAULT_CAMERA), set];
}
