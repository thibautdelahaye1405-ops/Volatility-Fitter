// The Lanes stage's filter panel (SERIES ARC S5): the Kalman ring a filter
// lane kept while the series calibrated, charted by the live Filter view's
// own FilterTimeline (bands · ζ · gain · Q). A lane select limited to the
// lanes whose ring index is non-empty (the panel is absent when no lane
// filters), an expiry select from that index (the stage's expiry when the
// ring has it), a handle select (ATM σ / skew / curvature = handles 0/1/2)
// and the playhead as a cursor — the step committed on the playhead frame,
// matched by FRAME INDEX (lib/seriesEvidence.cursorStepIndex), never by clock.
import { useEffect, useMemo, useState } from "react";
import { FilterTimeline } from "../FilterTimeline";
import { cursorStepIndex } from "../../lib/seriesEvidence";
import { laneLabel } from "../../lib/seriesLanes";
import type { LaneSpec } from "../../lib/seriesTypes";
import { useSeriesLaneFilter, useSeriesLaneFilterIndexes } from "../../state/useSeriesLaneFilter";
import { selectClass } from "../../lib/ui";

interface LanesFilterPanelProps {
  seriesId: string;
  lanes: LaneSpec[];
  /** The stage's expiry: the default ring when the lane keeps one for it. */
  expiry: string | null;
  /** The playhead (frame position). */
  index: number;
  epoch: string;
}

const HANDLES = ["ATM σ", "skew", "curvature"] as const;

/** The lane to chart: the current pick when it still filters, else the
 *  production lane when it does, else the first filtering lane. */
export function pickFilterLane(current: string | null, filtering: readonly LaneSpec[]): string | null {
  if (current !== null && filtering.some((l) => l.id === current)) return current;
  return (filtering.find((l) => l.production) ?? filtering[0])?.id ?? null;
}

/** The ring's expiry: the current pick when the lane keeps it, else the
 *  stage's expiry when it does, else the lane's first ring. */
export function pickFilterExpiry(current: string | null, wanted: string | null, expiries: readonly string[]): string | null {
  if (current !== null && expiries.includes(current)) return current;
  if (wanted !== null && expiries.includes(wanted)) return wanted;
  return expiries[0] ?? null;
}

export default function LanesFilterPanel({ seriesId, lanes, expiry, index, epoch }: LanesFilterPanelProps) {
  const laneIds = useMemo(() => lanes.map((l) => l.id), [lanes]);
  const { index: ringIndex, loaded } = useSeriesLaneFilterIndexes(seriesId, laneIds, epoch);
  const filtering = useMemo(() => lanes.filter((l) => (ringIndex[l.id]?.length ?? 0) > 0), [lanes, ringIndex]);

  const [laneChoice, setLaneChoice] = useState<string | null>(null);
  const [expiryChoice, setExpiryChoice] = useState<string | null>(null);
  const [handle, setHandle] = useState(0);
  const laneId = pickFilterLane(laneChoice, filtering);
  const expiries = laneId !== null ? (ringIndex[laneId] ?? []) : [];
  const ringExpiry = pickFilterExpiry(expiryChoice, expiry, expiries);

  // A stage expiry change re-targets the ring unless the user picked one.
  useEffect(() => {
    setExpiryChoice(null);
  }, [expiry]);

  const { steps, frameIdx } = useSeriesLaneFilter(seriesId, laneId, ringExpiry, epoch);
  const cursor = useMemo(() => cursorStepIndex(frameIdx, index), [frameIdx, index]);

  if (!loaded || filtering.length === 0) return null;
  return (
    <div className="rounded-md border border-slate-800 bg-surface-800/40 p-2" data-testid="lanes-filter-panel">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">Filter ring</span>
        <span className="flex flex-wrap items-center gap-1.5">
          <select
            aria-label="Filter lane"
            className={selectClass}
            value={laneId ?? ""}
            onChange={(e) => { setLaneChoice(e.target.value || null); setExpiryChoice(null); }}
            title="The filter lane whose ring is charted"
          >
            {filtering.map((l) => <option key={l.id} value={l.id}>{laneLabel(l)}</option>)}
          </select>
          <select
            aria-label="Ring expiry"
            className={selectClass}
            value={ringExpiry ?? ""}
            onChange={(e) => setExpiryChoice(e.target.value || null)}
            title="The expiry whose ring is charted"
          >
            {expiries.map((e) => <option key={e} value={e}>{e}</option>)}
          </select>
          <select
            aria-label="Filter handle"
            className={selectClass}
            value={handle}
            onChange={(e) => setHandle(Number(e.target.value))}
            title="Which filtered handle to chart"
          >
            {HANDLES.map((h, i) => <option key={h} value={i}>{h}</option>)}
          </select>
        </span>
      </div>
      {steps.length === 0 ? (
        <p className="text-[10px] text-slate-600">No committed filter steps for this ring yet.</p>
      ) : (
        <FilterTimeline steps={steps} handle={handle} cursor={cursor} />
      )}
    </div>
  );
}
