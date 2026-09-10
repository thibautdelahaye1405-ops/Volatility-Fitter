// Series lens · view state (SERIES ARC S4): what the lens remembers per tab
// through useLensViewMemory (Layout ▸ "Remember view per tab") — the picked
// series, the stage, the hidden lanes, the axis mode, the ghost-trail depth
// and the strike window — plus the derived Set and the lane toggle.
import { useCallback, useMemo } from "react";
import { useLensViewMemory } from "../../state/useLensViewMemory";
import type { SeriesStage } from "../../components/series/SeriesHeader";

export interface SeriesViewState {
  seriesId: string | null;
  stage: SeriesStage;
  hiddenLanes: string[];
  /** "k" (log-moneyness) or "strike" — the Smile stage maps it. */
  axisMode: string;
  /** Previous frames of the production lane drawn fading (0 = off). */
  ghost: number;
  kWindow: [number, number] | null;
}

export const GHOST_OPTIONS = [0, 1, 2, 3, 5] as const;
export const AXIS_OPTIONS: { id: string; label: string }[] = [
  { id: "k", label: "k = ln(K/F)" },
  { id: "strike", label: "Strike K" },
];

const EMPTY: string[] = [];

export function useSeriesViewState() {
  const [vs, patch] = useLensViewMemory<SeriesViewState>("series", () => ({
    seriesId: null, stage: "smile", hiddenLanes: [], axisMode: "k", ghost: 0, kWindow: null,
  }));
  // Older memories may lack a field: fall back per field.
  const hiddenLanes = vs.hiddenLanes ?? EMPTY;
  const hidden = useMemo(() => new Set(hiddenLanes), [hiddenLanes]);
  const toggleLane = useCallback(
    (id: string) => {
      patch({ hiddenLanes: hiddenLanes.includes(id) ? hiddenLanes.filter((x) => x !== id) : [...hiddenLanes, id] });
    },
    [patch, hiddenLanes],
  );
  return {
    seriesId: vs.seriesId ?? null,
    stage: vs.stage ?? "smile",
    axisMode: vs.axisMode ?? "k",
    ghost: vs.ghost ?? 0,
    kWindow: vs.kWindow ?? null,
    hiddenLanes,
    hidden,
    patch,
    toggleLane,
  };
}
