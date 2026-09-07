// The TICKER views of the Parametric chart card (UI SHELL v2): Table · Term ·
// Densities · Stacked IV · Surface — every view of the toolbar's TICKER group
// (plus the node Table), each live-only with the same offline card. Split
// out of SmileViewer (file-size policy) — the node views (Smile · Density ·
// Compare) stay there, next to the state they edit.
import QuoteTable from "../QuoteTable";
import TermPanel from "../TermPanel";
import StackedDensityChart from "../StackedDensityChart";
import StackedVarianceChart from "../StackedVarianceChart";
import SurfaceChart from "../SurfaceChart";
import type { ChartView } from "./ParametricToolbar";
import type { LiveTicksState } from "../../state/useLiveTicks";
import type { FitMode } from "../../state/useSmile";
import type { SmileData } from "../../lib/mockData";
import type { AxisMode } from "../../lib/axisModes";
import type { AutoScaleToggles } from "../../lib/autoScaleY";
import { chartMessageClass } from "../../lib/ui";

export interface TickerViewBodyProps {
  view: ChartView;
  live: boolean;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  smile: SmileData;
  liveTicks: LiveTicksState;
  showCalibQuotes: boolean;
  axisMode: AxisMode;
  autoScaleY: AutoScaleToggles;
  onToggleAutoScale: (key: keyof AutoScaleToggles) => void;
  /** The session's view version (spot transports / calibrations reload). */
  spotVersion: number;
}

const OFFLINE: Partial<Record<ChartView, string>> = {
  table: "Table view requires the live backend.",
  term: "Term-structure view requires the live backend.",
  stackeddensity: "Densities require the live backend.",
  stackedvar: "Stacked IV requires the live backend.",
  surface: "Surface view requires the live backend.",
};

/** The chart-card body of a ticker view (or the node Table); null for the
 *  node views, which SmileViewer renders itself. */
export default function TickerViewBody(p: TickerViewBodyProps) {
  const { view, live, ticker, expiry, fitMode, smile, axisMode, autoScaleY, onToggleAutoScale, spotVersion } = p;
  if (!(view in OFFLINE)) return null;
  if (!live) return <div className={chartMessageClass}>{OFFLINE[view]}</div>;
  switch (view) {
    case "table":
      return <QuoteTable ticker={ticker} expiry={expiry} fitMode={fitMode} smile={smile} ticks={p.liveTicks} showCalib={p.showCalibQuotes} />;
    case "term":
      return <TermPanel />;
    case "stackeddensity":
      return (
        <StackedDensityChart ticker={ticker} fitMode={fitMode} smile={smile} axisMode={axisMode}
          autoScaleY={autoScaleY} onToggleAutoScale={onToggleAutoScale} />
      );
    case "stackedvar":
      return (
        <StackedVarianceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode}
          autoScaleY={autoScaleY} onToggleAutoScale={onToggleAutoScale} />
      );
    case "surface":
      return <SurfaceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode} />;
    default:
      return null;
  }
}
