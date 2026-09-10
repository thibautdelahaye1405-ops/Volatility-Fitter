// Pure selectors of the Series lens (SERIES ARC S4): the expiry a frame
// shows for a tab, the ghost trail of the production lane, the production
// lane itself and the epoch key of a job's progress. No React — vitest-friendly.
import type { FramePayload, LaneSpec, SeriesProgress } from "../../lib/seriesTypes";

export interface ShownExpiry {
  expiry: string | null;
  /** The tab's expiry is not in the frame: the nearest later one is shown. */
  rolled: boolean;
}

/** The tab's expiry when the frame carries it; else the nearest LATER expiry
 *  the frame carries (the tab's has rolled off), else the frame's last. */
export function pickExpiry(expiries: readonly string[], tabExpiry: string | null): ShownExpiry {
  if (expiries.length === 0) return { expiry: null, rolled: false };
  if (tabExpiry !== null && expiries.includes(tabExpiry)) return { expiry: tabExpiry, rolled: false };
  const sorted = [...expiries].sort();
  const later = tabExpiry === null ? undefined : sorted.find((e) => e > tabExpiry);
  return { expiry: later ?? sorted[sorted.length - 1] ?? null, rolled: true };
}

export type GhostCurve = { k: number; vol: number }[];

/** The production lane's smile of the `depth` previous frames (nearest
 *  first), read through the frame cache's peek; missing frames / fits skip. */
export function ghostTrail(
  peek: (idx: number) => FramePayload | null,
  index: number,
  depth: number,
  laneId: string | null,
  expiry: string | null,
): GhostCurve[] {
  if (laneId === null || expiry === null || depth <= 0) return [];
  const out: GhostCurve[] = [];
  for (let i = 1; i <= depth && index - i >= 0; i++) {
    const slice = peek(index - i)?.lanes[laneId]?.slices.find((s) => s.expiry === expiry);
    if (!slice) continue;
    out.push(slice.k.map((k, j) => ({ k, vol: slice.iv[j] ?? Number.NaN })));
  }
  return out;
}

/** The lane the ghost trail and differences follow (starred, else the first). */
export function productionLane(lanes: readonly LaneSpec[]): LaneSpec | null {
  return lanes.find((l) => l.production) ?? lanes[0] ?? null;
}

/** Changes whenever a job's counters move: the document and the payload
 *  caches re-read on it. */
export function progressKey(p: SeriesProgress | null): string {
  return p === null ? "" : `${p.status}|${p.framesReady}|${p.fitsDone}`;
}
