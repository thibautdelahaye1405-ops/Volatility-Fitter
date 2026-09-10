// The Series lens's client frame cache (roadmap §3.4): frame payloads are
// fetched per (series, frame, lane set) and kept in a small LRU so playback
// never waits at 8× — the hook prefetches ±24 frames around the playhead
// through `planPrefetch`, at most two requests in flight. Pure (no React,
// no fetch): state/useSeriesFrames owns the requests.

/** Default capacity: the prefetch window (24 ahead + 24 behind) fits. */
export const DEFAULT_CAPACITY = 48;

/** Cache key of one frame payload under one lane set. */
export function frameKey(seriesId: string, idx: number, lanes: string): string {
  return `${seriesId}|${idx}|${lanes}`;
}

/** A least-recently-used map: `get` touches (bumps) an entry, `peek` does
 *  not; `set` evicts the oldest entry past `capacity`. */
export class FrameCache<T> {
  private readonly map = new Map<string, T>();

  constructor(readonly capacity: number = DEFAULT_CAPACITY) {}

  get size(): number {
    return this.map.size;
  }

  has(key: string): boolean {
    return this.map.has(key);
  }

  /** The entry, promoted to most-recently-used; undefined when absent. */
  get(key: string): T | undefined {
    const v = this.map.get(key);
    if (v === undefined) return undefined;
    this.map.delete(key);
    this.map.set(key, v);
    return v;
  }

  /** The entry WITHOUT touching its recency (hover previews, ghost trails). */
  peek(key: string): T | undefined {
    return this.map.get(key);
  }

  set(key: string, value: T): void {
    if (this.map.has(key)) this.map.delete(key);
    this.map.set(key, value);
    while (this.map.size > Math.max(1, this.capacity)) {
      const oldest = this.map.keys().next().value;
      if (oldest === undefined) break;
      this.map.delete(oldest);
    }
  }

  clear(): void {
    this.map.clear();
  }
}

/** The next frame indices to request NOW: walk `indices` in priority order,
 *  skip the ones the cache holds or that are already in flight, and take at
 *  most `maxInFlight − inFlight.size` of them (nothing when the pipe is full). */
export function planPrefetch(
  cache: { has(key: string): boolean },
  keyOf: (idx: number) => string,
  indices: readonly number[],
  inFlight: ReadonlySet<string>,
  maxInFlight = 2,
): number[] {
  const room = maxInFlight - inFlight.size;
  const out: number[] = [];
  if (room <= 0) return out;
  const seen = new Set<string>();
  for (const idx of indices) {
    const key = keyOf(idx);
    if (seen.has(key) || cache.has(key) || inFlight.has(key)) continue;
    seen.add(key);
    out.push(idx);
    if (out.length >= room) break;
  }
  return out;
}
