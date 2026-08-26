// Parametric lens (UI SHELL v2): per-expiry implied-volatility smile fitting
// and editing for the ACTIVE TAB's node. Data comes from the shared smile
// session (the workbench points it at the tab; FastAPI backend with a
// built-in mock fallback). The toolbar (ParametricToolbar) owns the sub-views,
// axis mode and overlay toggles with status badges right-aligned; the aside
// (SmileAside) hosts diagnostics plus the scenario panels and follows the
// Layout ▸ "Diagnostics aside" toggle. The chart card offers eight views —
// the editable Smile (with six strike-axis display modes), model Compare,
// stacked Densities, Log-Q-density, Term, the 3D Surface, Stacked IV and the
// quote Table (all but Smile/Compare need the live backend). Quote edits post
// to the backend fit session and the returned refit replaces the smile;
// shortcuts live in useSmileShortcuts.
import { useEffect, useMemo, useRef, useState } from "react";
import { Bookmark } from "lucide-react";
import SmileChart from "../components/SmileChart";
import QuoteToolbar, { toolbarButtonClass } from "../components/QuoteToolbar";
import DistributionChart from "../components/DistributionChart";
import StackedDensityChart from "../components/StackedDensityChart";
import StackedVarianceChart from "../components/StackedVarianceChart";
import OverlayCurvesChart from "../components/OverlayCurvesChart";
import ModelCompareTable from "../components/ModelCompareTable";
import TermPanel from "../components/TermPanel";
import SurfaceChart from "../components/SurfaceChart";
import QuoteTable from "../components/QuoteTable";
import WeightStrip from "../components/WeightStrip";
import SmileAside from "../components/SmileAside";
import ParametricToolbar, { VIEW_HINTS } from "../components/parametric/ParametricToolbar";
import type { ChartView } from "../components/parametric/ParametricToolbar";
import { FilterBadge, GraphOverlayBadge } from "../components/parametric/SmileOverlayBadges";
import { useSmileSession } from "../state/smileSession";
import { useGraphFocus } from "../state/graphFocus";
import { useGraphNodeSmile } from "../state/useGraphNodeSmile";
import { useObservationFilter } from "../state/useObservationFilter";
import { useExpiryFormat } from "../state/expiryFormat";
import { useOptionalWorkbench } from "../state/workbench";
import { formatExpiry } from "../lib/expiryFormat";
import { useSmileShortcuts } from "../state/useSmileShortcuts";
import { useLiveTicks } from "../state/useLiveTicks";
import { composeFrames } from "../lib/smileLayers";
import { useModelComparison } from "../state/useModelComparison";
import { compareSeries } from "../lib/modelCompare";
import type { AxisMode } from "../lib/axisModes";
import { readSmileAutoScale, writeSmileAutoScale } from "../lib/autoScaleY";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import { cardClass, chartMessageClass } from "../lib/ui";

/** Centered placeholder for the chart-card body states. */
const chartMessage = (text: string) => <div className={chartMessageClass}>{text}</div>;

export default function SmileViewer() {
  const {
    smile, source, loading, refreshing, error, editError, ticker, expiry, fitMode,
    applyEdit, undo, redo, savePrior, scenarioCurve,
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
  const [view, setView] = useState<ChartView>("smile");
  const [axisMode, setAxisMode] = useState<AxisMode>("logmoneyness");
  // Fit-target overlay (V3.4 item 4): mid polyline + bid-ask/haircut ribbons.
  const [showTarget, setShowTarget] = useState(true);
  // Calibration frame toggles: the quotes + target the last fit used (off by
  // default — the prevailing market is the primary layer) and the fit on its
  // calibration spot (on — the "how far has the market moved" reference).
  const [showCalibQuotes, setShowCalibQuotes] = useState(false);
  const [showCalibFit, setShowCalibFit] = useState(true);
  const [showWeights, setShowWeights] = useState(false);
  // Smile-chart y-axis auto-scale chips (lib/autoScaleY), persisted like the
  // Calibrate scope (localStorage — a UI preference).
  const [autoScaleY, setAutoScaleY] = useState<AutoScaleToggles>(() => readSmileAutoScale());
  const toggleAutoScale = (key: keyof AutoScaleToggles) =>
    setAutoScaleY((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      writeSmileAutoScale(next);
      return next;
    });
  // Transient "Saved ✓" confirmation on the Save-prior button.
  const [savedFlash, setSavedFlash] = useState(false);
  const flashTimer = useRef<number | null>(null);

  // Brief "UPDATED" flash when the viewed node transitions stale -> fresh, i.e. a
  // calibration just brought it up to date. Keyed per node so switching
  // expiries never flashes.
  const [updatedFlash, setUpdatedFlash] = useState(false);
  const updatedTimer = useRef<number | null>(null);
  const staleRef = useRef<{ key: string; stale: boolean } | null>(null);

  // Reset the brush and selection whenever a *different* node loads
  // (ticker/expiry change). Refits of the same node keep both. State is
  // adjusted during render so the chart never paints the previous window.
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

  // Side-by-side model comparison (V3.2 item 12): fetched lazily.
  const comparison = useModelComparison(view === "compare", live, ticker, expiry, fitMode, spotVersion);

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
  const { data: filterDiag } = useObservationFilter(
    live && view === "smile", ticker, expiry, fitMode, spotVersion,
  );

  useSmileShortcuts({ smile, source, selectedIndex, setSelectedIndex, applyEdit, undo, redo });

  const toggleExclude = () => {
    if (selectedQuote === null) return;
    void applyEdit(selectedQuote.excluded ? "include" : "exclude", selectedQuote.index);
  };
  /** Switch the chart-card view; arm the distribution fetcher lazily. */
  const switchView = (next: ChartView) => {
    setView(next);
    if (next === "logqd") loadDistribution();
  };
  const onSavePrior = () => {
    void savePrior()
      .then(() => {
        setSavedFlash(true);
        if (flashTimer.current !== null) window.clearTimeout(flashTimer.current);
        flashTimer.current = window.setTimeout(() => setSavedFlash(false), 1500);
      })
      .catch(() => { /* surfaced through editError */ });
  };

  const distributionBody = (kind: "density" | "logqd") => {
    if (!live) return chartMessage("Distribution views require the live backend.");
    if (distribution !== null) {
      return <DistributionChart kind={kind} current={distribution.current} prior={distribution.prior} />;
    }
    if (distributionLoading) return chartMessage("Loading distribution…");
    return chartMessage("Distribution unavailable for this node.");
  };

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
            market={fr.market}
            calib={fr.calib}
            showCalibQuotes={showCalibQuotes}
            showCalibFit={showCalibFit}
            liveFlash={liveTicks.flash}
            prior={smile.prior}
            priorTransported={smile.priorTransported}
            scenario={scenarioCurve}
            kWindow={kWindow}
            onKWindowChange={setKWindow}
            fullRange={[smile.kMin, smile.kMax]}
            axisMode={axisMode}
            t={smile.T}
            atmVol={smile.diagnostics.atmVol}
            selectedIndex={selectedIndex}
            onQuoteSelect={setSelectedIndex}
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
            fitMode={fitMode}
            showTarget={showTarget}
            autoScaleY={autoScaleY}
            footer={
              showWeights ? (
                <WeightStrip live={live} ticker={ticker} expiry={expiry} fitMode={fitMode}
                  smile={smile} kWindow={kWindow} axisMode={axisMode} />
              ) : null
            }
          />
        );
      case "compare":
        if (comparison.data === null) {
          return chartMessage(
            comparison.loading
              ? "Fitting LQD / SVI-JW / MCS…"
              : `Couldn't load the comparison: ${comparison.error ?? "unavailable"}`,
          );
        }
        return (
          <div className="flex h-full min-h-0 flex-col gap-2">
            <div className={["min-h-0 flex-1", comparison.loading ? "opacity-60" : ""].join(" ")}>
              <OverlayCurvesChart series={compareSeries(comparison.data)} xLabel="log-moneyness k" yLabel="implied vol" zoomY />
            </div>
            <ModelCompareTable data={comparison.data} />
          </div>
        );
      case "stackeddensity":
        return live
          ? <StackedDensityChart ticker={ticker} fitMode={fitMode} smile={smile} axisMode={axisMode} />
          : chartMessage("Densities require the live backend.");
      case "logqd":
        return distributionBody("logqd");
      case "term":
        return live ? <TermPanel /> : chartMessage("Term-structure view requires the live backend.");
      case "surface":
        return live
          ? <SurfaceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode} />
          : chartMessage("Surface view requires the live backend.");
      case "stackedvar":
        return live
          ? <StackedVarianceChart ticker={ticker} fitMode={fitMode} reloadKey={spotVersion} axisMode={axisMode} />
          : chartMessage("Stacked IV requires the live backend.");
      case "table":
        return live
          ? <QuoteTable ticker={ticker} expiry={expiry} fitMode={fitMode} smile={smile} ticks={liveTicks} showCalib={showCalibQuotes} />
          : chartMessage("Table view requires the live backend.");
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <ParametricToolbar
        view={view} onView={switchView}
        axisMode={axisMode} onAxisMode={setAxisMode}
        showTarget={showTarget} onShowTarget={() => setShowTarget((v) => !v)}
        showCalibQuotes={showCalibQuotes} onShowCalibQuotes={() => setShowCalibQuotes((v) => !v)}
        showCalibFit={showCalibFit} onShowCalibFit={() => setShowCalibFit((v) => !v)}
        showWeights={showWeights} onShowWeights={() => setShowWeights((v) => !v)}
        autoScaleY={autoScaleY} onToggleAutoScale={toggleAutoScale}
        live={live} error={error} stale={smile?.stale ?? false} updatedFlash={updatedFlash}
      />

      {/* Body: chart card + diagnostics aside */}
      <div className="flex min-h-0 flex-1 gap-3">
        <div
          className={[
            "flex min-w-0 flex-1 flex-col p-4 transition-colors duration-500",
            cardClass,
            updatedFlash ? "border-accent-500/70" : "",
          ].join(" ")}
        >
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {smile ? `${smile.ticker} · ${formatExpiry(smile.expiry, smile.T, format)}` : "Smile"}
            </h2>
            {graphOverlay !== null && <GraphOverlayBadge overlay={graphOverlay} onDismiss={() => setFocus(null)} />}
            {filterDiag !== null && <FilterBadge diag={filterDiag} />}
            {error !== null && source === "live" && (
              <span className="truncate text-[10px] text-amber-400/80">{error}</span>
            )}
            {/* Quote-editing toolbar (+ last rejected-edit message) */}
            <div className="ml-auto flex items-center gap-2">
              {editError !== null && (
                <span className="max-w-56 truncate text-[10px] text-amber-400">{editError}</span>
              )}
              <QuoteToolbar
                selectedQuote={selectedQuote}
                canUndo={smile?.canUndo ?? false}
                canRedo={smile?.canRedo ?? false}
                canReset={hasEdits}
                live={live}
                onToggleExclude={toggleExclude}
                onUndo={() => void undo()}
                onRedo={() => void redo()}
                onReset={() => void applyEdit("reset")}
              />
              <button
                className={toolbarButtonClass}
                disabled={!live}
                title={live ? "Persist the current fit as the prior curve" : "requires live backend"}
                onClick={onSavePrior}
              >
                <Bookmark size={12} strokeWidth={1.75} className="opacity-80" />
                {savedFlash ? "Saved ✓" : "Save prior"}
              </button>
            </div>
          </div>
          <div className={["min-h-0 flex-1 transition-opacity duration-200", refreshing ? "opacity-60" : "opacity-100"].join(" ")}>
            {chartBody()}
          </div>
          <p className="mt-1 shrink-0 text-[10px] text-slate-600">{VIEW_HINTS[view]}</p>
        </div>

        {/* Diagnostics aside: hidden on the Term sub-tab (own controls column)
            and by Layout ▸ Diagnostics aside. */}
        {view !== "term" && showAside && <SmileAside />}
      </div>
    </div>
  );
}
