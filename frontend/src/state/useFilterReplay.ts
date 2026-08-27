// Hooks over the SERVED offline filter-replay artifacts (V3.9 rider):
//
//   GET /filter/replay/parts?ticker=      → part metadata, newest first
//   GET /filter/replay/parts/{t}/{day}    → one part document (wire-shape steps)
//
// Both are static-file reads on the backend (nothing fits). Backendless
// (`live` false) or when the listing fails, `available` is false and the
// consumers render the REPLAY_RUN_HINT — there is deliberately NO mock replay:
// the artifact is evidence, and evidence is never invented.
import { useEffect, useState } from "react";

import type { FilterReplayPart, FilterReplayPartMeta } from "../lib/filterReplay";
import { api } from "./api";

interface PartsResponse {
  parts: FilterReplayPartMeta[];
}

export interface UseFilterReplayPartsResult {
  /** Newest first (the backend order); [] when none / unavailable. */
  parts: FilterReplayPartMeta[];
  loading: boolean;
  /** True once a live listing succeeded (even if it was empty). */
  available: boolean;
}

/** The replay parts for `ticker` (all tickers when ""), refetched on any
 *  param change; bump `refreshKey` after a replay run to re-list. */
export function useFilterReplayParts(
  live: boolean,
  ticker: string,
  refreshKey?: unknown,
): UseFilterReplayPartsResult {
  const [parts, setParts] = useState<FilterReplayPartMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [available, setAvailable] = useState(false);

  useEffect(() => {
    if (!live) {
      setParts([]);
      setAvailable(false);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<PartsResponse>("/filter/replay/parts", {
        params: ticker !== "" ? { ticker } : {},
        signal: controller.signal,
      })
      .then((res) => {
        setParts(res.parts ?? []);
        setAvailable(true);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setParts([]);
        setAvailable(false);
        setLoading(false);
      });
    return () => controller.abort();
  }, [live, ticker, refreshKey]);

  return { parts, loading, available };
}

export interface UseFilterReplayPartResult {
  part: FilterReplayPart | null;
  loading: boolean;
}

/** One part document, fetched only while `day` is non-null (the timeline
 *  fetches it when its Replay chip is selected, never before). */
export function useFilterReplayPart(
  live: boolean,
  ticker: string,
  day: string | null,
): UseFilterReplayPartResult {
  const [part, setPart] = useState<FilterReplayPart | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!live || ticker === "" || day === null) {
      setPart(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<FilterReplayPart>(
        `/filter/replay/parts/${encodeURIComponent(ticker)}/${encodeURIComponent(day)}`,
        { signal: controller.signal },
      )
      .then((doc) => {
        setPart(doc);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setPart(null);
        setLoading(false);
      });
    return () => controller.abort();
  }, [live, ticker, day]);

  return { part, loading };
}
