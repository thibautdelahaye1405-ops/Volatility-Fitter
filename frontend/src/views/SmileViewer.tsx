// Parametric lens (UI SHELL v2, wave 2): per-expiry implied-volatility smile
// fitting and editing for the ACTIVE TAB's node. Data comes from the shared
// smile session (the workbench points it at the tab; FastAPI backend with a
// built-in mock fallback).
//
// Layout of the chart card:
//   toolbar   NODE views (Smile · Density · Compare · Table) · TICKER views
//             (Term · Densities · Stacked IV · Surface) · Density sub-toggle ·
//             status badges (ParametricToolbar)
//   header    node title · GRAPH / FILTER overlay badges · quote toolbar
//   body      the chart, with the layer rail (Target · Calib. quotes · Calib.
//             fit · Weights) at its RIGHT and Y-center / Y-fit as overlay
//             buttons on the chart itself
//   footer    interaction hint · the x-axis unit select next to the x-axis
// The right-hand column (SmileAside) stacks Spot move · Var-swap · Fit
// diagnostics and follows Layout ▸ "Diagnostics aside". Save prior lives in
// the top bar's Priors ▾. Quote edits post to the backend fit session and the
// returned refit replaces the smile; shortcuts live in useSmileShortcuts.
// View state (sub-view, density kind, axis unit, layers, Y auto-scale, extra
// Compare families) goes through useLensViewMemory: per TAB when Layout ▸
// "Remember view per tab" is on (wave 3, C2), per lens otherwise.
import { useEffect, useMemo, useRef, useState } from "react";
import SmileChart from "../components/SmileChart";
import QuoteToolbar from "../components/QuoteToolbar";
import DistributionChart from "../components/DistributionChart";
import type { DistKind } from "../components/DistributionChart";
import StackedDensityChart from "../components/StackedDensityChart";
import StackedVarianceChart from "../components/StackedVarianceChart";
import OverlayCurvesChart from "../components/OverlayCurvesChart";
import ModelCompareTable from "../components/ModelCompareTable";
import TermPanel from "../components/TermPanel";
import SurfaceChart from "../components/SurfaceChart";
import QuoteTable from "../components/QuoteTable";
import WeightStrip from "../components/WeightStrip";
import SmileAside from "../components/SmileAside";
import AxisModeSelect from "../components/charts/AxisModeSelect";
import ParametricToolbar, { AXIS_MODE_VIEWS, VIEW_HINTS } from "../components/parametric/ParametricToolbar";
import type { ChartView } from "../components/parametric/ParametricToolbar";
import LayerRail from "../components/parametric/LayerRail";
import CompareChips, { prevailingModelId } from "../components/parametric/CompareChips";
import { FilterBadge, GraphOverlayBadge } from "../components/parametric/SmileOverlayBadges";
import { useSmileSession } from "../state/smileSession";
import { useGraphFocus } from "../state/graphFocus";
import { useGraphNodeSmile } from "../state/useGraphNodeSmile";
import { useObservationFilter } from "../state/useObservationFilter";
import { useExpiryFormat } from "../state/expiryFormat";
import { useOptionalWorkbench } from "../state/workbench";
import { useLensViewMemory } from "../state/useLensViewMemory";
import { formatExpiry } from "../lib/expiryFormat";
import { useSmileShortcuts } from "../state/useSmileShortcuts";
import { useLiveTicks } from "../state/useLiveTicks";
import { composeFrames } from "../lib/smileLayers";
import { useModelComparison } from "../state/useModelComparison";
import { compareSeries } from "../lib/modelCompare";
import { MODEL_ORDER } from "../lib/modelColor";
import type { CompareModelId } from "../lib/mockData";
import type { AxisMode } from "../lib/axisModes";
import { readSmileAutoScale, writeSmileAutoScale } from "../lib/autoScaleY";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import { cardClass, chartMessageClass } from "../lib/ui";

/** Centered placeholder for the chart-card body states. */
const chartMessage = (text: string) => <div className={chartMessageClass}>{text}</div>;

/** The lens's remembered view state (per tab or per lens — see the header). */
interface ParametricView {
  view: ChartView;
  densityKind: DistKind;
  axisMode: AxisMode;
  showTarget: boolean;
  showCalibQuotes: boolean;
  showCalibFit: boolean;
  showWeights: boolean;
  autoScaleY: AutoScaleToggles;
  /** Extra Compare families beyond the prevailing one (chips clicked). */
  compareExtra: CompareModelId[];
}

export default function SmileViewer() {
  const {
    smile, source, loading, refreshing, error, editError, ticker, expiry, fitMode,
    applyEdit, undo, redo, scenarioCurve,
    distribution, distributionLoading, loadDistribution, spotVersion,
  } = useSmileSession();
  const { format } = useExpiryFormat();
  const { focus, setFocus } = useGraphFocus();
  const wb = useOptionalWorkbench();
  const showAside = wb === null || wb.layout.aside;

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
    autoScaleY: readSmileAutoScale(), compareExtra: [],
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

  // Compare (wave 2): the prevailing calibrated family shows at once; the
  // others are fitted lazily when their chip is clicked. The extra selection
  // lives in the view state (remembered per tab) and resets when the SAME
  // node's prevailing model changes (a recalibration under another family).
  const prevailing = prevailingModelId(smile?.modelInfo?.id, smile?.modelInfo?.label);
  const prevailingRef = useRef<{ key: string; model: CompareModelId | null }>({ key: "", model: null });
  useEffect(() => {
    const prev = prevailingRef.current;
    prevailingRef.current = { key: smileKey, model: prevailing };
    if (prev.key === smileKey && prev.model !== prevailing && vs.compareExtra.length > 0) {
      patchView({ compareExtra: [] });
    }
  }, [smileKey, prevailing]); // eslint-disable-line react-hooks/exhaustive-deps
  const compareModels = useMemo(
    () => MODEL_ORDER.filter((m) => m === prevailing || vs.compareExtra.includes(m)),
    [prevailing, vs.compareExtra],
  );
  const toggleModel = (id: CompareModelId) =>
    patchView({
      compareExtra: vs.compareExtra.includes(id)
        ? vs.compareExtra.filter((m) => m !== id)
        : [...vs.compareExtra, id],
    });
  const comparison = useModelComparison(
    view === "compare", live, ticker, expiry, fitMode, spotVersion, compareModels,
  );

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
    switch (view) {
      case "smile":
        return (
          <SmileChart
            market={fr.market} calib={fr.calib}
            showCalibQuotes={showCalibQuotes} showCalibFit={showCalibFit}
            liveFlash={liveTicks.flash}
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
              showWeights ? (
                <WeightStrip live={live} ticker={ticker} expiry={expiry} fitMode={fitMode}
                  smile={smile} kWindow={kWindow} axisMode={axisMode} />
              ) : null
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
        const chips = (
          <CompareChips prevailing={prevailing} selected={new Set(compareModels)} onToggle={toggleModel}
            data={comparison.data} loading={comparison.loading} />
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
              <OverlayCurvesChart series={compareSeries(comparison.data)} xLabel="log-moneyness k" yLabel="implied vol" zoomY />
            </div>
            <ModelCompareTable data={comparison.data} />
          </div>
        );
      }
      case "table":
        return live
          ? <QuoteTable ticker={ticker} expiry={expiry} fitMode={fitMode} smile={smile} ticks={liveTicks} showCalib={showCalibQuotes} />
          : chartMessage("Table view requires the live backend.");
      case "term":
        return live ? <TermPanel /> : chartMessage("Term-structure view requires the live backend.");
      case "stackeddensity":
        return live
          ? <StackedDensityChart ticker={ticker} fitMode={fitMode} smile={smile} axisMode={axisMode} />
          : chartMessage("Densities require the live backend.");
      case "stackedvar":
        return live
          ? <StackedVarianceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode} />
          : chartMessage("Stacked IV requires the live backend.");
      case "surface":
        return live
          ? <SurfaceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode} />
          : chartMessage("Surface view requires the live backend.");
    }
  };

  const railView = view === "smile" || view === "table" ? view : null;

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
          {/* Header: node title · overlay badges · quote-editing toolbar */}
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {smile ? `${smile.ticker} · ${formatExpiry(smile.expiry, smile.T, format)}` : "Smile"}
            </h2>
            {graphOverlay !== null && <GraphOverlayBadge overlay={graphOverlay} onDismiss={() => setFocus(null)} />}
            {filterDiag !== null && <FilterBadge diag={filterDiag} />}
            {error !== null && source === "live" && (
              <span className="truncate text-[10px] text-amber-400/80">{error}</span>
            )}
            <div className="ml-auto flex items-center gap-2">
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
