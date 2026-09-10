// The Series lens's stage switch (SERIES ARC S5): ONE place that maps the
// header's stage tab to the stage component and its props — Smile (S4),
// Frames (S4), Surface + Term (S5, agent C's stages: the prop contracts
// below are theirs) and Lanes (S5, the evidence). The lens hands every
// piece it owns (frame · frames · strip · playback · lanes · view state);
// nothing here fetches.
import FramesTable from "../../components/series/FramesTable";
import LanesStage from "../../components/series/LanesStage";
import SmileStage from "../../components/series/SmileStage";
import SurfaceStage from "../../components/series/SurfaceStage";
import TermStage from "../../components/series/TermStage";
import type { SeriesStage } from "../../components/series/SeriesHeader";
import type { SmilePoint } from "../../lib/mockData";
import type { FitMode, FrameDoc, FramePayload, LaneSpec, StripPayload } from "../../lib/seriesTypes";
import type { SurfaceMode } from "./useSeriesViewState";

export interface StageSwitchProps {
  stage: SeriesStage;
  seriesId: string;
  ticker: string;
  frame: FramePayload | null;
  frames: FrameDoc[];
  /** The playhead (frame position). */
  index: number;
  strip: StripPayload | null;
  lanes: LaneSpec[];
  hidden: Set<string>;
  /** The shown expiry (the tab's, rolled forward). */
  expiry: string | null;
  axisMode: string;
  surfaceMode: SurfaceMode;
  kWindow: [number, number] | null;
  onKWindowChange: (w: [number, number]) => void;
  ghostCurves: SmilePoint[][];
  fitMode: FitMode;
  loading: boolean;
  /** Every payload cache's epoch (series id + the job's counters). */
  epoch: string;
  onScrub: (idx: number) => void;
}

export default function StageSwitch(p: StageSwitchProps) {
  switch (p.stage) {
    case "frames":
      return <FramesTable frames={p.frames} index={p.index} onJump={p.onScrub} />;
    case "surface":
      return (
        <SurfaceStage
          frame={p.frame}
          lanes={p.lanes}
          hidden={p.hidden}
          seriesId={p.seriesId}
          ticker={p.ticker}
          mode={p.surfaceMode}
          axisMode={p.axisMode}
          loading={p.loading}
        />
      );
    case "term":
      return <TermStage frame={p.frame} lanes={p.lanes} hidden={p.hidden} expiry={p.expiry} loading={p.loading} />;
    case "lanes":
      return (
        <LanesStage
          seriesId={p.seriesId}
          frame={p.frame}
          frames={p.frames}
          index={p.index}
          strip={p.strip}
          lanes={p.lanes}
          hidden={p.hidden}
          expiry={p.expiry}
          epoch={p.epoch}
          onScrub={p.onScrub}
        />
      );
    default:
      return (
        <SmileStage
          frame={p.frame}
          lanes={p.lanes}
          hidden={p.hidden}
          expiry={p.expiry}
          axisMode={p.axisMode}
          kWindow={p.kWindow}
          onKWindowChange={p.onKWindowChange}
          ghostCurves={p.ghostCurves}
          fitMode={p.fitMode}
          loading={p.loading}
        />
      );
  }
}
