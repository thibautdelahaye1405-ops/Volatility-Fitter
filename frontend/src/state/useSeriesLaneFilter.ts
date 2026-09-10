// A lane's filter ring in a series (SERIES ARC S5): GET /series/{id}/lanes/
// {lane}/filter — the expiries the lane keeps a ring for (empty when the
// lane runs no filter) — and /filter/{expiry} — the ring's steps oldest →
// newest in the FilterStepWire shape the live /filter/history serves, with
// `frameIdx[i]` = the series frame the i-th step committed on (the Lanes
// stage's cursor matches by that, never by clock). The index hook reads
// every lane at once so the stage can hide the panel when no lane filters;
// both hooks re-read on the epoch (a ring grows as fits land) and never
// serve another (series, lane, expiry)'s payload under the current one.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { FilterStepWire } from "../lib/filterTimeline";
import type { LaneFilterIndex, LaneFilterPayload } from "../lib/seriesTypes";

const FILTER_TIMEOUT_MS = 30_000;
const EMPTY_STEPS: FilterStepWire[] = [];
const EMPTY_IDX: (number | null)[] = [];
const EMPTY_STRINGS: string[] = [];

const lanePath = (seriesId: string, laneId: string) =>
  `/series/${encodeURIComponent(seriesId)}/lanes/${encodeURIComponent(laneId)}/filter`;

/** The filter-ring expiries of every lane, keyed by lane id (a lane that
 *  runs no filter, or whose read failed, maps to []); `loaded` once the
 *  current lane set has been read. */
export function useSeriesLaneFilterIndexes(
  seriesId: string | null,
  laneIds: readonly string[],
  epoch: string,
): { index: Record<string, string[]>; loaded: boolean } {
  const lanesKey = laneIds.join(",");
  const [state, setState] = useState<{ key: string; index: Record<string, string[]> } | null>(null);

  useEffect(() => {
    if (seriesId === null || lanesKey === "") {
      setState(null);
      return;
    }
    const controller = new AbortController();
    const ids = lanesKey.split(",");
    Promise.all(
      ids.map((laneId) =>
        api
          .get<LaneFilterIndex>(lanePath(seriesId, laneId), { signal: controller.signal, timeoutMs: FILTER_TIMEOUT_MS })
          .then((r) => r.expiries)
          .catch(() => EMPTY_STRINGS),
      ),
    ).then((lists) => {
      if (controller.signal.aborted) return;
      const index: Record<string, string[]> = {};
      ids.forEach((id, i) => {
        index[id] = lists[i];
      });
      setState({ key: `${seriesId}|${lanesKey}`, index });
    });
    return () => controller.abort();
  }, [seriesId, lanesKey, epoch]);

  const current = state !== null && state.key === `${seriesId}|${lanesKey}` ? state : null;
  return { index: current?.index ?? {}, loaded: current !== null };
}

/** One lane's filter-ring expiries (the single-lane reading of the index). */
export function useSeriesLaneFilterIndex(
  seriesId: string | null,
  laneId: string | null,
  epoch = "",
): { expiries: string[] } {
  const { index } = useSeriesLaneFilterIndexes(seriesId, laneId === null ? EMPTY_STRINGS : [laneId], epoch);
  return { expiries: laneId !== null ? (index[laneId] ?? EMPTY_STRINGS) : EMPTY_STRINGS };
}

/** The ring of one (lane, expiry): its steps (oldest first) and, per step,
 *  the series frame index it committed on. Empty until loaded; the previous
 *  ring stays while the SAME (series, lane, expiry) re-reads on the epoch. */
export function useSeriesLaneFilter(
  seriesId: string | null,
  laneId: string | null,
  expiry: string | null,
  epoch: string,
): { steps: FilterStepWire[]; frameIdx: (number | null)[] } {
  const key = seriesId !== null && laneId !== null && expiry !== null ? `${seriesId}|${laneId}|${expiry}` : null;
  const [state, setState] = useState<{ key: string; steps: FilterStepWire[]; frameIdx: (number | null)[] } | null>(null);

  useEffect(() => {
    if (key === null || seriesId === null || laneId === null || expiry === null) {
      setState(null);
      return;
    }
    const controller = new AbortController();
    api
      .get<LaneFilterPayload>(`${lanePath(seriesId, laneId)}/${encodeURIComponent(expiry)}`, {
        signal: controller.signal,
        timeoutMs: FILTER_TIMEOUT_MS,
      })
      .then((p) => {
        // The wire carries the live filter's step shape; the type is the chart's.
        const steps = (p.steps ?? []) as unknown as FilterStepWire[];
        setState({ key, steps, frameIdx: p.frameIdx ?? steps.map(() => null) });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        setState((prev) => (prev !== null && prev.key === key ? prev : null));
      });
    return () => controller.abort();
  }, [key, seriesId, laneId, expiry, epoch]);

  const current = state !== null && state.key === key ? state : null;
  return { steps: current?.steps ?? EMPTY_STEPS, frameIdx: current?.frameIdx ?? EMPTY_IDX };
}
