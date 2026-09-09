// Parametric lens (UI SHELL v2, wave 2): per-expiry implied-volatility smile
// fitting and editing for the ACTIVE TAB's node. Data comes from the shared
// smile session (the workbench points it at the tab; FastAPI backend with a
// built-in mock fallback).
//
// Layout of the chart card:
//   toolbar   NODE views (Smile · Density · Compare · Table) · TICKER views
//             (Term · Densities · Stacked IV · Surface) · Density sub-toggle ·
//             status badges (ParametricToolbar)
//   header    node title · GRAPH / FILTER overlay badges · the Fit switch of
//             the anchoring axis (Smile / Density) · quote toolbar
//   body      the chart, with the layer rail (Target · Calib. quotes · Calib.
//             fit · Weights) at its RIGHT and Y-center / Y-fit as overlay
//             buttons on the chart itself
//   footer    interaction hint · the x-axis unit select next to the x-axis
// The right-hand column (SmileAside) stacks Spot move · Var-swap · Fit
// diagnostics and follows Layout ▸ "Diagnostics aside". Save prior lives in
// the top bar's Priors ▾. Quote edits post to the backend fit session and the
// returned refit replaces the smile; shortcuts live in useSmileShortcuts.
// The Compare wiring lives in state/useCompareView. View state (sub-view,
// axis unit, layers, Y auto-scale, Compare selections, the Fit switch) goes
// through useLensViewMemory: per TAB when Layout ▸ "Remember view per tab"
// is on (wave 3, C2), per lens otherwise.
import { useEffect, useMemo, useRef, useState } from "react";
import SmileChart from "../components/SmileChart";
import QuoteToolbar from "../components/QuoteToolbar";
import DistributionChart from "../components/DistributionChart";
import type { DistKind } from "../components/DistributionChart";
import OverlayCurvesChart from "../components/OverlayCurvesChart";
import ModelCompareTable from "../components/ModelCompareTable";
import WeightStrip from "../components/WeightStrip";
import SmileAside from "../components/SmileAside";
import AxisModeSelect from "../components/charts/AxisModeSelect";
import ParametricToolbar, { AXIS_MODE_VIEWS, VIEW_HINTS } from "../components/parametric/ParametricToolbar";
import type { ChartView } from "../components/parametric/ParametricToolbar";
import LayerRail from "../components/parametric/LayerRail";
import TickerViewBody from "../components/parametric/TickerViewBody";
import CompareChips from "../components/parametric/CompareChips";
import FitAnchoringSwitch from "../components/parametric/FitAnchoringSwitch";
import { FilterBadge, GraphInferredBadge, GraphOverlayBadge, runClock } from "../components/parametric/SmileOverlayBadges";
import { useSmileSession } from "../state/smileSession";
import { useGraphFocus } from "../state/graphFocus";
import { useGraphNodeSmile } from "../state/useGraphNodeSmile";
import { useObservationFilter } from "../state/useObservationFilter";
import { useExpiryFormat } from "../state/expiryFormat";
import { useOptionalWorkbench } from "../state/workbench";
import { useNodeScope } from "../state/nodeScope";
import { useLensViewMemory } from "../state/useLensViewMemory";
import { useCompareView } from "../state/useCompareView";
import type { CompareViewState } from "../state/useCompareView";
import { formatExpiry } from "../lib/expiryFormat";
import { useSmileShortcuts } from "../state/useSmileShortcuts";
import { useLiveTicks } from "../state/useLiveTicks";
import { composeFrames } from "../lib/smileLayers";
import { compareSeries } from "../lib/modelCompare";
import type { FitAnchoring } from "../lib/anchoring";
import { axisModeLabel, axisTickLabel } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";
import { formatPct } from "../lib/chartScale";
import { readSmileAutoScale, writeSmileAutoScale } from "../lib/autoScaleY";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import { cardClass, chartMessageClass } from "../lib/ui";

/** Centered placeholder for the chart-card body states. */
const chartMessage = (text: string) => <div className={chartMessageClass}>{text}</div>;

/** The lens's remembered view state (per tab or per lens — see the header);
 *  the Compare selections are the CompareViewState slice. */
interface ParametricView extends CompareViewState {
  view: ChartView;
  densityKind: DistKind;
  axisMode: AxisMode;
  showTarget: boolean;
  showCalibQuotes: boolean;
  showCalibFit: boolean;
  showWeights: boolean;
  autoScaleY: AutoScaleToggles;
  /** The Fit switch (lib/anchoring): production, or a shadow cell drawn
   *  instead on the Smile / Density views. */
  fitAnchoring: FitAnchoring;
  /** The graph-inferred smile layer (the last Run's posterior on the node). */
  showInferred: boolean;
}

export default function SmileViewer() {
  const {
    smile, source, loading, refreshing, error, editError, ticker, expiry, fitMode,
    applyEdit, undo, redo, scenarioCurve, setAnchoring,
    distribution, distributionLoading, loadDistribution, spotVersion,
  } = useSmileSession();
  const { format } = useExpiryFormat();
  const { focus, setFocus } = useGraphFocus();
  const wb = useOptionalWorkbench();
  const scope = useNodeScope();
  // Split editors (wave 3, C3): the right-hand column yields to the charts.
  const showAside = (wb === null || wb.layout.aside) && !(scope?.split ?? false);

  const [kWindow, setKWindow] = useState<[number, number]>([0, 1]);
  // Selected quote, referenced by its stable `index` field (not array
  // position) so the selection keeps its identity across refits.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  // View state — chart layers (the rail): fit-target overlay (V3.4 item 4),
  // calibration frame (quotes off by default — the prevailing market is the
  // primary layer; fit on its calibration spot on) and the weight strip; Y
  // auto-scale chips (lib/autoScaleY) seed from their persisted default.
  const [vs, patchView] = useLensViewMemory<ParametricView>("parametric", () => ({
    view: "smile", densityKind: "density", axisMode: "logmoneyness",
    showTarget: true, showCalibQuotes: false, showCalibFit: true, showWeights: false,
    autoScaleY: readSmileAutoScale(), compareExtra: [], compareTails: [], compareAnchoring: [],
    fitAnchoring: "production", showInferred: true,
  }));
  const { view, densityKind, axisMode, showTarget, showCalibQuotes, showCalibFit, showWeights, autoScaleY } = vs;
  const setDensityKind = (densityKind: DistKind) => patchView({ densityKind });
  const setAxisMode = (axisMode: AxisMode) => patchView({ axisMode });
  const toggleAutoScale = (key: keyof AutoScaleToggles) => {
    const next = { ...autoScaleY, [key]: !autoScaleY[key] };
    writeSmileAutoScale(next);
    patchView({ autoScaleY: next });
  };

  // Brief "UPDATED" flash when the viewed node transitions stale -> fresh, i.e.
  // a calibration just brought it up to date. Keyed per node so switching
  // expiries never flashes.
  const [updatedFlash, setUpdatedFlash] = useState(false);
  const updatedTimer = useRef<number | null>(null);
  const staleRef = useRef<{ key: string; stale: boolean } | null>(null);

  // Reset the brush and selection whenever a *different* node loads; refits of
  // the same node keep both. State is adjusted during render so the chart
  // never paints the previous window.
  const smileKey = smile ? `${smile.ticker}|${smile.expiry}` : "";
  const [prevSmileKey, setPrevSmileKey] = useState("");
  if (smile && smileKey !== prevSmileKey) {
    setPrevSmileKey(smileKey);
    setKWindow([smile.kMin, smile.kMax]);
    setSelectedIndex(null);
  }
  const staleNow = smile?.stale ?? null;
  useEffect(() => {
    if (smile === null) return;
    const prev = staleRef.current;
    if (prev !== null && prev.key === smileKey && prev.stale && !smile.stale) {
      setUpdatedFlash(true);
      if (updatedTimer.current) window.clearTimeout(updatedTimer.current);
      updatedTimer.current = window.setTimeout(() => setUpdatedFlash(false), 1100);
    }
    staleRef.current = { key: smileKey, stale: smile.stale ?? false };
  }, [smileKey, staleNow]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (updatedTimer.current) window.clearTimeout(updatedTimer.current); }, []);

  const selectedQuote =
    smile !== null && selectedIndex !== null
      ? (smile.quotes.find((q) => q.index === selectedIndex) ?? null)
      : null;
  const hasEdits = smile !== null && smile.quotes.some((q) => q.excluded || q.amended);
  const live = source === "live";
  // The node's live market ticks (ONE SSE connection per viewed node).
  const liveTicks = useLiveTicks(ticker, expiry, live, fitMode);
  const frames = useMemo(() => (smile ? composeFrames(smile, liveTicks) : null), [smile, liveTicks]);

  // Compare (wave 2 + tail matching + the anchoring axis): state/useCompareView.
  const cv = useCompareView({
    vs, patchView, smile, smileKey, live, ticker, expiry, fitMode, spotVersion, axisMode,
    enabled: view === "compare",
  });

  // Fit switch (anchoring axis): the view's choice drives the session's smile
  // and density fetches — ONLY on the views that show the switch (a shadow
  // never reaches the Table / Compare payloads unannounced); production
  // again when the view moves on or the lens unmounts.
  const fitAnchoring: FitAnchoring = vs.fitAnchoring ?? "production";
  const shadowView = view === "smile" || view === "density";
  useEffect(() => {
    setAnchoring(shadowView && fitAnchoring !== "production" ? fitAnchoring : null);
    return () => setAnchoring(null);
  }, [fitAnchoring, shadowView, setAnchoring]);

  // Graph-extrapolation live overlay (plan Phase 5): when the user drilled into
  // THIS node from the Graph lens, overlay the posterior curve + credible band.
  const graphActive =
    live && view === "smile" && focus !== null && focus.ticker === ticker && focus.expiry === expiry;
  const graphNode = useGraphNodeSmile(graphActive, ticker, expiry, focus?.body ?? {});
  const graphOverlay =
    graphActive && graphNode.node?.ticker === ticker && graphNode.node?.expiry === expiry
      ? graphNode.node
      : null;
  // Observation-filter overlay (Note 15 Phase 4): null while the filter is off.
  const { data: filterDiag } = useObservationFilter(live && view === "smile", ticker, expiry, fitMode, spotVersion);

  useSmileShortcuts({ smile, source, selectedIndex, setSelectedIndex, applyEdit, undo, redo });

  const toggleExclude = () => {
    if (selectedQuote === null) return;
    void applyEdit(selectedQuote.excluded ? "include" : "exclude", selectedQuote.index);
  };
  /** Switch the chart-card view; arm the distribution fetcher lazily. */
  const switchView = (next: ChartView) => {
    patchView({ view: next });
    if (next === "density") loadDistribution();
  };
  // A remembered tab may land straight on Density: arm the fetcher then too.
  useEffect(() => { if (view === "density") loadDistribution(); }, [view, loadDistribution]);

  /** Chart-card body for the active view. */
  const chartBody = () => {
    if (smile === null) {
      if (!loading && error !== null) return chartMessage(`Couldn't load this smile: ${error}`);
      return chartMessage("Loading market data…");
    }
    const fr = frames ?? composeFrames(smile, liveTicks);
    const inferredInfo = smile.graphInferred ?? null;
    const showInferred = (vs.showInferred ?? true) && inferredInfo !== null;
    switch (view) {
      case "smile":
        return (
          <SmileChart
            market={fr.market} calib={fr.calib}
            inferred={showInferred ? fr.market.inferred : null}
            inferredLabel={inferredInfo ? `run ${runClock(inferredInfo.runTs)}` : null}
            showCalibQuotes={showCalibQuotes} showCalibFit={showCalibFit}
            liveFlash={liveTicks.flash} liveSeq={liveTicks.seq}
            quoteKind={smile.quoteKind ?? "quotes"}
            prior={smile.prior} priorTransported={smile.priorTransported}
            scenario={scenarioCurve}
            kWindow={kWindow} onKWindowChange={setKWindow} fullRange={[smile.kMin, smile.kMax]}
            axisMode={axisMode} t={smile.T} atmVol={smile.diagnostics.atmVol}
            selectedIndex={selectedIndex} onQuoteSelect={setSelectedIndex}
            varSwapLevel={smile.varSwap.enabled && !smile.varSwap.excluded ? smile.varSwap.level : null}
            graphPost={graphOverlay?.post ?? null}
            graphBandLo={graphOverlay?.postBandLo ?? null}
            graphBandHi={graphOverlay?.postBandHi ?? null}
            filterPost={filterDiag?.post ?? null}
            filterBandLo={filterDiag?.postBandLo ?? null}
            filterBandHi={filterDiag?.postBandHi ?? null}
            filterPred={filterDiag?.predCurve ?? null}
            fitBandHalf={smile.diagnostics.atmVolStd != null ? 1.96 * smile.diagnostics.atmVolStd : null}
            degraded={smile.degraded ?? null}
            fitMode={fitMode} showTarget={showTarget}
            autoScaleY={autoScaleY} onToggleAutoScale={toggleAutoScale}
            footer={
              showWeights
                ? ({ xView, tx }) => (
                    <WeightStrip live={live} ticker={ticker} expiry={expiry} fitMode={fitMode}
                      smile={smile} xView={xView} tx={tx} />
                  )
                : null
            }
          />
        );
      case "density":
        if (!live) return chartMessage("Distribution views require the live backend.");
        if (distribution !== null) {
          return <DistributionChart kind={densityKind} current={distribution.current} prior={distribution.prior} />;
        }
        return chartMessage(distributionLoading ? "Loading distribution…" : "Distribution unavailable for this node.");
      case "compare": {
        const { comparison, compareTx } = cv;
        const chips = (
          <CompareChips prevailing={cv.prevailing} selected={new Set(cv.compareModels)} onToggle={cv.toggleModel}
            data={comparison.data} loading={comparison.loading}
            tails={new Set(cv.compareTails)} onToggleTail={cv.toggleTail} tailInfo={comparison.data?.tailMatch ?? null}
            anchoring={new Set(cv.compareAnchoring)} onToggleAnchoring={cv.toggleAnchoring}
            anchoringInfo={comparison.data?.anchoring ?? smile.anchoring ?? null} />
        );
        if (comparison.data === null) {
          return (
            <div className="flex h-full min-h-0 flex-col gap-2">
              {chips}
              {chartMessage(comparison.loading ? "Fitting…" : `Couldn't load the comparison: ${comparison.error ?? "unavailable"}`)}
            </div>
          );
        }
        return (
          <div className="flex h-full min-h-0 flex-col gap-2">
            {chips}
            <div className={["min-h-0 flex-1", comparison.loading ? "opacity-60" : ""].join(" ")}>
              {/* Same grammar as the Smile: strike-axis mode, the SHARED k-window
                  brush (zoom the belly here, see it there), Y center / Y fit. */}
              <OverlayCurvesChart
                series={compareSeries(comparison.data, compareTx)}
                xLabel={axisMode === "logmoneyness" ? "log-moneyness k" : axisModeLabel(axisMode)}
                yLabel="implied vol"
                formatX={(v) => axisTickLabel(axisMode, v)}
                formatY={(v) => formatPct(v)}
                formatHoverY={(v) => `σ ${formatPct(v, 2)}`}
                xBrush={{
                  min: smile.kMin, max: smile.kMax, value: kWindow, onChange: setKWindow,
                  toX: compareTx, format: (v) => v.toFixed(2),
                }}
                autoScaleY={autoScaleY} onToggleAutoScale={toggleAutoScale}
              />
            </div>
            <ModelCompareTable data={comparison.data} />
          </div>
        );
      }
      default:  // the ticker views + the node Table (parametric/TickerViewBody)
        return (
          <TickerViewBody view={view} live={live} ticker={ticker} expiry={expiry} fitMode={fitMode} smile={smile}
            liveTicks={liveTicks} showCalibQuotes={showCalibQuotes} axisMode={axisMode}
            autoScaleY={autoScaleY} onToggleAutoScale={toggleAutoScale} spotVersion={spotVersion} />
        );
    }
  };

  const railView = view === "smile" || view === "table" ? view : null;
  // The Fit switch: live, a fitted node, on the views that draw its own fit.
  const showFitSwitch = live && shadowView && smile !== null && smile.hasFit !== false;

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <ParametricToolbar
        view={view} onView={switchView}
        densityKind={densityKind} onDensityKind={setDensityKind}
        live={live} error={error} stale={smile?.stale ?? false} updatedFlash={updatedFlash}
      />

      {/* Body: chart card + the right-hand column */}
      <div className="flex min-h-0 flex-1 gap-3">
        <div
          className={[
            "flex min-w-0 flex-1 flex-col p-4 transition-colors duration-500",
            cardClass,
            updatedFlash ? "border-accent-500/70" : "",
          ].join(" ")}
        >
          {/* Header: node title · overlay badges · Fit switch · quote-editing toolbar */}
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="whitespace-nowrap text-sm font-semibold text-slate-100">
              {smile ? `${smile.ticker} · ${formatExpiry(smile.expiry, smile.T, format)}` : "Smile"}
            </h2>
            {graphOverlay !== null && <GraphOverlayBadge overlay={graphOverlay} onDismiss={() => setFocus(null)} />}
            {view === "smile" && smile?.graphInferred && (vs.showInferred ?? true) && (
              <GraphInferredBadge info={smile.graphInferred} onHide={() => patchView({ showInferred: false })} />
            )}
            {filterDiag !== null && <FilterBadge diag={filterDiag} />}
            {error !== null && source === "live" && (
              <span className="truncate text-[10px] text-amber-400/80">{error}</span>
            )}
            <div className="ml-auto flex items-center gap-2">
              {showFitSwitch && (
                <FitAnchoringSwitch info={smile.anchoring} value={fitAnchoring}
                  onChange={(fitAnchoring) => patchView({ fitAnchoring })} drawn={smile.modelInfo?.anchoring ?? null} />
              )}
              {editError !== null && (
                <span className="max-w-56 truncate text-[10px] text-amber-400">{editError}</span>
              )}
              <QuoteToolbar
                selectedQuote={selectedQuote}
                canUndo={smile?.canUndo ?? false} canRedo={smile?.canRedo ?? false} canReset={hasEdits}
                live={live}
                onToggleExclude={toggleExclude}
                onUndo={() => void undo()} onRedo={() => void redo()}
                onReset={() => void applyEdit("reset")}
              />
            </div>
          </div>

          {/* Body: chart + layer rail at its right */}
          <div className="flex min-h-0 flex-1 gap-2">
            <div data-chart-card="" className={["min-h-0 min-w-0 flex-1 transition-opacity duration-200", refreshing ? "opacity-60" : "opacity-100"].join(" ")}>
              {chartBody()}
            </div>
            {railView !== null && (
              <LayerRail
                view={railView}
                showTarget={showTarget} onShowTarget={() => patchView({ showTarget: !showTarget })}
                showCalibQuotes={showCalibQuotes} onShowCalibQuotes={() => patchView({ showCalibQuotes: !showCalibQuotes })}
                showCalibFit={showCalibFit} onShowCalibFit={() => patchView({ showCalibFit: !showCalibFit })}
                showWeights={showWeights} onShowWeights={() => patchView({ showWeights: !showWeights })}
                hasInferred={smile?.graphInferred != null} showInferred={vs.showInferred ?? true}
                onShowInferred={() => patchView({ showInferred: !(vs.showInferred ?? true) })}
              />
            )}
          </div>

          {/* Footer: interaction hint · x-axis unit next to the x-axis */}
          <div className="mt-1 flex shrink-0 items-center gap-3 text-[10px] text-slate-600">
            <span className="truncate">{VIEW_HINTS[view]}</span>
            {AXIS_MODE_VIEWS.has(view) && (
              <span className="ml-auto shrink-0">
                <AxisModeSelect value={axisMode} onChange={setAxisMode} />
              </span>
            )}
          </div>
        </div>

        {/* Right-hand column: Spot move · Var-swap · Fit diagnostics. Hidden on
            the Term sub-tab (own controls column) and by Layout ▸ aside. */}
        {view !== "term" && showAside && <SmileAside />}
      </div>
    </div>
  );
}
