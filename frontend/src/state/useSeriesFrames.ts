// Frame payloads of the Series lens (roadmap §3.4): GET /series/{id}/frame/
// {idx}?lanes=… per (series, frame, lane set) — the frame's market plus
// every requested lane's curves, surface grid and metrics in one response
// (~50–200 KB, cached server-side). The hook keeps ONE LRU per instance
// (lib/seriesFrameCache, 48 entries), serves the current frame from it and
// prefetches ±24 frames around the playhead, ahead in the play direction
// first, at most two requests in flight, so playback never waits at 8×.
//
// Staleness: the cache, the in-flight set and the abort controller belong
// to a GENERATION keyed on (series, lane set, epoch); a response landing
// after its generation was retired is dropped, and every request of the old
// generation is aborted. A frame whose request failed is remembered per
// generation so the planner never retries it in a loop; it reads as
// `frame: null, loading: false`.
import { useCallback, useEffect, useReducer, useRef } from "react";
import { api } from "./api";
import { FrameCache, frameKey, planPrefetch } from "../lib/seriesFrameCache";
import { prefetchWindow } from "../lib/seriesPlayback";
import type { FramePayload } from "../lib/seriesTypes";

const FRAME_TIMEOUT_MS = 30_000;
const MAX_IN_FLIGHT = 2;

interface Generation {
  key: string;
  n: number;
  cache: FrameCache<FramePayload>;
  inFlight: Set<string>;
  failed: Set<string>;
  controller: AbortController;
}

function newGeneration(key: string, n: number): Generation {
  return {
    key,
    n,
    cache: new FrameCache<FramePayload>(),
    inFlight: new Set(),
    failed: new Set(),
    controller: new AbortController(),
  };
}

export interface SeriesFramesHandle {
  /** The payload of frame `index`, or null while missing / after a failure. */
  frame: FramePayload | null;
  /** True only while the CURRENT frame's request is outstanding. */
  loading: boolean;
  /** A cached frame without touching its recency (ghost trails, hover). */
  peek: (idx: number) => FramePayload | null;
}

export function useSeriesFrames(
  seriesId: string | null,
  laneIds: readonly string[],
  index: number,
  nFrames: number,
  direction: 1 | -1,
  epoch: string,
): SeriesFramesHandle {
  const lanesKey = laneIds.join(",");
  const genKey = `${seriesId ?? ""}|${lanesKey}|${epoch}`;
  const genRef = useRef<Generation | null>(null);
  // Retire the generation when its key moves (render-time, idempotent):
  // abort what is in flight, drop the cache — the old series' frames never
  // paint under the new one.
  if (genRef.current === null || genRef.current.key !== genKey) {
    genRef.current?.controller.abort();
    genRef.current = newGeneration(genKey, (genRef.current?.n ?? 0) + 1);
  }
  const gen = genRef.current;
  // A landed response bumps this so the planner runs again (next prefetch).
  const [tick, bump] = useReducer((n: number) => n + 1, 0);

  const keyOf = useCallback(
    (idx: number) => frameKey(seriesId ?? "", idx, lanesKey),
    [seriesId, lanesKey],
  );

  useEffect(() => {
    if (seriesId === null || !(nFrames > 0)) return;
    const g = gen;
    const known = { has: (k: string) => g.cache.has(k) || g.failed.has(k) };
    const wanted = [index, ...prefetchWindow(index, nFrames, direction)];
    const plan = planPrefetch(known, keyOf, wanted, g.inFlight, MAX_IN_FLIGHT);
    // The frame under the playhead bypasses the in-flight cap: it is what
    // the user is looking at.
    const cur = keyOf(index);
    if (!known.has(cur) && !g.inFlight.has(cur) && !plan.includes(index)) plan.unshift(index);
    for (const idx of plan) {
      const key = keyOf(idx);
      g.inFlight.add(key);
      api
        .get<FramePayload>(`/series/${encodeURIComponent(seriesId)}/frame/${idx}`, {
          params: lanesKey !== "" ? { lanes: lanesKey } : {},
          signal: g.controller.signal,
          timeoutMs: FRAME_TIMEOUT_MS,
        })
        .then((payload) => {
          if (genRef.current !== g) return; // a retired generation's answer
          g.cache.set(key, payload);
        })
        .catch(() => {
          if (genRef.current !== g || g.controller.signal.aborted) return;
          g.failed.add(key);
        })
        .finally(() => {
          if (genRef.current !== g) return;
          g.inFlight.delete(key);
          bump();
        });
    }
  }, [seriesId, lanesKey, index, nFrames, direction, gen, keyOf, tick]);

  const curKey = keyOf(index);
  const frame = seriesId === null ? null : (gen.cache.get(curKey) ?? null);
  const loading =
    seriesId !== null && nFrames > 0 && frame === null && !gen.failed.has(curKey);

  const peek = useCallback(
    (idx: number) => (seriesId === null ? null : (gen.cache.peek(keyOf(idx)) ?? null)),
    [seriesId, gen, keyOf],
  );

  return { frame, loading, peek };
}
