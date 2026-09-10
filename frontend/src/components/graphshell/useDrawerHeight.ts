// Resizable graph drawer (GRAPH ERGONOMICS rider, 2026-09-10): the bottom
// drawer used to be a fixed box (16 rem for Relations, 13 rem otherwise), so a
// long Relations list scrolled inside a small window. This hook owns the
// drawer height: the per-tab default until the user drags the TOP edge, then
// the dragged height (clamped) for the rest of the session — remembered in
// localStorage so a reload keeps it; a double-click on the handle resets.
//
// The drag uses mouse events on the handle + window listeners (no pointer
// capture) so it works the same under jsdom and in the browser; dragging UP
// makes the drawer taller because the handle sits on its top edge.
import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";

import type { DrawerTab } from "./GraphDrawer";

/** localStorage key of the dragged height (a JSON number, px). */
export const DRAWER_HEIGHT_KEY = "volfit.graph.drawerHeight.v1";
/** Smallest useful drawer: one toolbar row plus a few list rows. */
export const DRAWER_MIN_PX = 140;
/** The drawer never takes more than this share of the viewport. */
export const DRAWER_MAX_VH = 0.7;

/** Today's defaults: h-64 (16 rem) for Relations, h-52 (13 rem) otherwise. */
export function defaultDrawerHeight(tab: DrawerTab): number {
  return tab === "relations" ? 256 : 208;
}

function maxHeight(): number {
  const vh = typeof window === "undefined" ? 0 : window.innerHeight;
  return Math.max(DRAWER_MIN_PX, Math.floor(vh * DRAWER_MAX_VH));
}

export function clampDrawerHeight(px: number): number {
  return Math.max(DRAWER_MIN_PX, Math.min(maxHeight(), Math.round(px)));
}

function readStored(): number | null {
  try {
    const raw = localStorage.getItem(DRAWER_HEIGHT_KEY);
    const v = raw === null ? NaN : Number(JSON.parse(raw));
    return Number.isFinite(v) && v > 0 ? clampDrawerHeight(v) : null;
  } catch {
    return null;
  }
}

function writeStored(px: number | null): void {
  try {
    if (px === null) localStorage.removeItem(DRAWER_HEIGHT_KEY);
    else localStorage.setItem(DRAWER_HEIGHT_KEY, JSON.stringify(px));
  } catch {
    /* storage unavailable (private window, thumbnail capture) — session-only */
  }
}

export interface DrawerHandleProps {
  onMouseDown: (e: ReactMouseEvent<HTMLElement>) => void;
  onDoubleClick: () => void;
}

export interface UseDrawerHeightResult {
  /** The height to apply to the drawer body, px. */
  height: number;
  /** True while a dragged height overrides the tab default. */
  dragged: boolean;
  /** Spread onto the top-edge handle element. */
  handleProps: DrawerHandleProps;
  /** Back to the tab default (also what the handle's double-click does). */
  reset: () => void;
}

export function useDrawerHeight(tab: DrawerTab): UseDrawerHeightResult {
  const [stored, setStored] = useState<number | null>(readStored);
  const start = useRef<{ y: number; h: number } | null>(null);
  const height = stored ?? defaultDrawerHeight(tab);

  const reset = useCallback(() => {
    setStored(null);
    writeStored(null);
  }, []);

  // The drag: the window listens while the button is down, so a fast pointer
  // leaving the 1 px seam does not drop the drag. Persisted on release.
  const onMouseDown = useCallback((e: ReactMouseEvent<HTMLElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    start.current = { y: e.clientY, h: height };
  }, [height]);

  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (start.current === null) return;
      setStored(clampDrawerHeight(start.current.h - (e.clientY - start.current.y)));
    };
    const up = () => {
      if (start.current === null) return;
      start.current = null;
      setStored((v) => {
        writeStored(v);
        return v;
      });
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  return {
    height,
    dragged: stored !== null,
    handleProps: { onMouseDown, onDoubleClick: reset },
    reset,
  };
}
