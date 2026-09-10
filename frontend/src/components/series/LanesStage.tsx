// The Series lens's LANES stage (SERIES ARC S5 — the evidence): what each
// model lane did across the whole series, side by side. Three blocks, top to
// bottom: (a) a metric chip row (rms · max err · pull ATM · ζ ATM · fit ms ·
// ATM σ · skew · curvature) over an overlay chart of that metric per visible
// lane across the frames, the playhead as a violet line + one marker per
// lane (the chart owns no click-to-x, so scrubbing stays with the filmstrip
// and the worst-frame cells); (b) the evidence table (LanesTable) from
// /series/{id}/evidence; (c) the filter ring of a filter lane
// (LanesFilterPanel), absent when no lane filters. The stage keeps its
// metric choice while mounted; everything else comes from the lens.
import { useMemo, useState } from "react";
import OverlayCurvesChart from "../OverlayCurvesChart";
import LanesFilterPanel from "./LanesFilterPanel";
import LanesTable from "./LanesTable";
import {
  EVIDENCE_METRICS,
  formatMetric,
  metricLabel,
  playheadLine,
  playheadMarker,
  stripSeries,
} from "../../lib/seriesEvidence";
import type { EvidenceMetric } from "../../lib/seriesEvidence";
import { productionLane, visibleLanes } from "../../lib/seriesLanes";
import type { FrameDoc, FramePayload, LaneSpec, StripPayload } from "../../lib/seriesTypes";
import { chipClass } from "../../lib/ui";
import { useSeriesEvidence } from "../../state/useSeriesEvidence";

interface LanesStageProps {
  seriesId: string;
  frame: FramePayload | null;
  frames: FrameDoc[];
  /** The playhead (frame position). */
  index: number;
  strip: StripPayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  /** The stage's expiry (the tab's, rolled forward). */
  expiry: string | null;
  epoch: string;
  onScrub: (idx: number) => void;
}

export default function LanesStage({ seriesId, frames, index, strip, lanes, hidden, expiry, epoch, onScrub }: LanesStageProps) {
  const [metric, setMetric] = useState<EvidenceMetric>("rmsBp");
  const shown = useMemo(() => visibleLanes(lanes, hidden), [lanes, hidden]);
  const laneIds = useMemo(() => lanes.map((l) => l.id), [lanes]);
  const production = productionLane(lanes);
  const { evidence } = useSeriesEvidence(seriesId, laneIds, expiry, epoch);

  // The chart: one series per visible lane + the playhead line and markers.
  const laneSeries = useMemo(() => (strip === null ? [] : stripSeries(strip, metric, shown)), [strip, metric, shown]);
  const series = useMemo(() => {
    const line = playheadLine(index, laneSeries);
    return line === null ? laneSeries : [...laneSeries, line];
  }, [laneSeries, index]);
  const markers = useMemo(() => playheadMarker(index, laneSeries, (v) => formatMetric(metric, v)), [laneSeries, index, metric]);
  const fmtY = (v: number) => formatMetric(metric, v);
  const nFrames = strip?.idx.length ?? frames.length;

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 overflow-auto" data-testid="series-lanes-stage">
      {/* (a) metric chips + the chart across frames */}
      <div className="flex shrink-0 flex-wrap items-center gap-1" role="group" aria-label="Metric">
        {EVIDENCE_METRICS.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={metric === m}
            className={chipClass(metric === m)}
            onClick={() => setMetric(m)}
            data-metric={m}
          >
            {metricLabel(m)}
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] text-slate-500">
          frame {Math.min(index, Math.max(0, nFrames - 1)) + 1}{nFrames > 0 ? ` / ${nFrames}` : ""}
        </span>
      </div>
      <div className="relative min-h-[220px] shrink-0 basis-[38%]" data-testid="lanes-chart">
        {strip === null || laneSeries.length === 0 ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">
            {strip === null ? "no filmstrip yet" : "every lane is hidden"}
          </div>
        ) : (
          <OverlayCurvesChart
            series={series}
            xLabel="frame"
            yLabel={metricLabel(metric)}
            formatX={(v) => String(Math.round(v))}
            formatY={fmtY}
            markers={markers}
            xBrush={false}
          />
        )}
      </div>
      {/* (b) the evidence table */}
      <div className="shrink-0">
        <LanesTable evidence={evidence} lanes={shown} production={production} onScrub={onScrub} />
      </div>
      {/* (c) the filter ring of a filter lane */}
      <div className="shrink-0">
        <LanesFilterPanel seriesId={seriesId} lanes={lanes} expiry={expiry} index={index} epoch={epoch} />
      </div>
    </div>
  );
}
