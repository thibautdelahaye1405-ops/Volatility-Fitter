// Fetches one node's observation-filter history ring (V3.9 item 7):
// GET /smiles/{ticker}/{expiry}/filter/history — the last <= 64 committed
// steps, oldest first, feeding the FilterTimeline charts. Read-only and
// poll-safe on the backend (never fits). Backendless (`live` false) it serves
// the deterministic 8-step mock ring so the timeline renders in mock mode.
import { useEffect, useState } from "react";

import type { FilterStepWire } from "../lib/filterTimeline";
import { getMockFilterHistory } from "../lib/mockData";
import { api } from "./api";

/** GET /smiles/{t}/{e}/filter/history response (backend FilterHistoryResponse). */
export interface FilterHistoryResponse {
  /** False when the filter is off or nothing has committed yet (steps = []). */
  active: boolean;
  steps: FilterStepWire[];
}

interface UseFilterHistoryResult {
  steps: FilterStepWire[];
  loading: boolean;
  /** "mock" when serving the built-in ring (backend unreachable / demo). */
  source: "live" | "mock";
}

/** Fetch the history ring for (ticker, expiry) while `live`; refetches on any
 *  param change (bump `refreshKey` after calibrations). A fetch error yields
 *  an EMPTY ring (honest), never the mock — mock is only for `live === false`. */
export function useFilterHistory(
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: string,
  refreshKey: unknown,
): UseFilterHistoryResult {
  const [steps, setSteps] = useState<FilterStepWire[]>([]);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<"live" | "mock">("live");

  useEffect(() => {
    if (!live) {
      setSteps(getMockFilterHistory().steps);
      setSource("mock");
      setLoading(false);
      return;
    }
    setSource("live");
    if (ticker === "" || expiry === "") {
      setSteps([]);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<FilterHistoryResponse>(
        `/smiles/${ticker}/${encodeURIComponent(expiry)}/filter/history`,
        { params: { fit_mode: fitMode }, signal: controller.signal },
      )
      .then((res) => {
        setSteps(res.active ? res.steps : []);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setSteps([]);
        setLoading(false);
      });
    return () => controller.abort();
  }, [live, ticker, expiry, fitMode, refreshKey]);

  return { steps, loading, source };
}
