// Smile workspace: per-expiry implied volatility smile fitting and editing.
// Data comes from the shared smile session (FastAPI backend with a built-in
// mock fallback). The header (UniverseHeader) owns universe selection, the
// sub-tabs and view controls, with status badges right-aligned — the same
// grammar as the Local Vol workspace; the aside (SmileAside) hosts
// diagnostics plus the scenario panels. The chart card offers seven
// views — the editable Smile (with six strike-axis display modes), fitted
// Density / Log-Q-density, the 3D vol Surface and the quote Table (the last four
// require the live backend). Quote edits post to the backend fit session and
// the returned refit replaces the smile; shortcuts live in useSmileShortcuts.
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
import UniverseHeader, { selectClass } from "../components/UniverseHeader";
import SmileAside from "../components/SmileAside";
import SegmentedControl from "../components/SegmentedControl";
import { useSmileSession } from "../state/smileSession";
import { useGraphFocus } from "../state/graphFocus";
import { useGraphNodeSmile } from "../state/useGraphNodeSmile";
import { useObservationFilter } from "../state/useObservationFilter";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import { useSmileShortcuts } from "../state/useSmileShortcuts";
import { useLiveTicks } from "../state/useLiveTicks";
import { composeFrames } from "../lib/smileLayers";
import { useModelComparison } from "../state/useModelComparison";
import { compareSeries } from "../lib/modelCompare";
import { AXIS_MODE_OPTIONS } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";
import { readSmileAutoScale, writeSmileAutoScale } from "../lib/autoScaleY";
import type { AutoScaleToggles } from "../lib/autoScaleY";

/** Chart-card content. "Stacked densities" overlays every expiry's density
 *  (no butterfly arb ⇔ all ≥ 0); "Stacked IV" overlays total variance w=σ²T
 *  (no calendar arb ⇔ curves don't cross). ROADMAP Phase 10. */
type ChartView =
  | "smile"
  | "compare"
  | "stackeddensity"
  | "logqd"
  | "term"
  | "surface"
  | "stackedvar"
  | "table";

const CHART_VIEWS: { id: ChartView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "compare", label: "Compare" },
  { id: "stackeddensity", label: "Densities" },
  { id: "logqd", label: "Log Q-density" },
  { id: "term", label: "Term" },
  { id: "surface", label: "Surface" },
  { id: "stackedvar", label: "Stacked IV" },
  { id: "table", label: "Table" },
];

/** Views whose x-axis can switch coordinate (ln(K/F) / strike / %ATM / Δ / …),
 *  exactly like the Smile: the smile, the density overlay, the 3D surface and
 *  the stacked total-variance overlay. */
const AXIS_MODE_VIEWS = new Set<ChartView>(["smile", "stackeddensity", "surface", "stackedvar"]);

/** Interaction hint shown under the chart card, per view. */
const VIEW_HINTS: Record<ChartView, string> = {
  smile: "Click a quote · Del exclude · ↑↓ amend · Ctrl+Z undo",
  compare: "LQD / SVI-JW / MCS fitted to the same quotes · validity = each family's analytic no-arb signal",
  stackeddensity: "All expiries' densities overlaid · ≥ 0 is structural for LQD only — SVI/MCS dips draw signed in red (clipped otherwise)",
  logqd: "Log quantile density ℓ(u) = log q(u) of the current fit",
  term: "ATM term structure across the expiry ladder · real / event-dilated clock",
  surface: "Drag to rotate · σ(k, T) across the expiry ladder",
  stackedvar: "Total variance w=σ²·T per expiry · non-crossing ⇒ no calendar arbitrage",
  table: "Market frame (prevailing quotes, target, fit @ market spot) · Calib. quotes toggles the calibration columns · Copy / CSV in the footer",
};

/** Centered placeholder for the chart-card body states. */
const chartMessage = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function SmileViewer() {
  const {
    smile,
    source,
    loading,
    refreshing,
    error,
    editError,
    ticker,
    expiry,
    fitMode,
    applyEdit,
    undo,
    redo,
    savePrior,
    scenarioCurve,
    distribution,
    distributionLoading,
    loadDistribution,
    spotVersion,
  } = useSmileSession();
  const { format } = useExpiryFormat();
  const { focus, setFocus } = useGraphFocus();

  const [kWindow, setKWindow] = useState<[number, number]>([0, 1]);
  // Selected quote, referenced by its stable `index` field (not array
  // position) so the selection keeps its identity across refits.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  // Chart-card view (smile / density / quantile / surface / table).
  const [view, setView] = useState<ChartView>("smile");
  // Strike-axis display mode of the smile chart (labels only).
  const [axisMode, setAxisMode] = useState<AxisMode>("logmoneyness");
  // Fit-target overlay (V3.4 item 4): mid polyline + bid-ask/haircut ribbons.
  const [showTarget, setShowTarget] = useState(true);
  // Calibration frame toggles: the quotes + target the last fit used (off by
  // default — the prevailing market is the primary layer) and the fit on its
  // calibration spot (on — the "how far has the market moved" reference).
  const [showCalibQuotes, setShowCalibQuotes] = useState(false);
  const [showCalibFit, setShowCalibFit] = useState(true);
  // Calibration weight strip under the chart (V3.4 item 5), default off.
  const [showWeights, setShowWeights] = useState(false);
  // Smile-chart y-axis auto-scale chips (lib/autoScaleY): after any x-view
  // change, "Y fit" snaps the y window to the data in view and "Y center"
  // recenters the user's y zoom on it. Default both ON; persisted like the
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
  // calibration just brought it up to date (so a model/setting change that refits
  // is visibly confirmed). Keyed per node so switching expiries never flashes.
  const [updatedFlash, setUpdatedFlash] = useState(false);
  const updatedTimer = useRef<number | null>(null);
  const staleRef = useRef<{ key: string; stale: boolean } | null>(null);

  // Reset the brush and selection whenever a *different* node loads
  // (ticker/expiry change). Refits of the same node keep both.
  // State is adjusted during render (not in an effect) so the chart never
  // paints a frame with the previous node's window.
  const smileKey = smile ? `${smile.ticker}|${smile.expiry}` : "";
  const [prevSmileKey, setPrevSmileKey] = useState("");
  if (smile && smileKey !== prevSmileKey) {
    setPrevSmileKey(smileKey);
    setKWindow([smile.kMin, smile.kMax]);
    setSelectedIndex(null);
  }

  // Flash "UPDATED" only on a same-node stale -> fresh edge (a completed refit),
  // never on initial load or an expiry switch.
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

  // Resolve the selection against the current quote list; a refit that
  // drops the quote simply yields no selection.
  const selectedQuote =
    smile !== null && selectedIndex !== null
      ? (smile.quotes.find((q) => q.index === selectedIndex) ?? null)
      : null;
  const hasEdits =
    smile !== null && smile.quotes.some((q) => q.excluded || q.amended);
  const live = source === "live";
  // The node's live market ticks (ONE SSE connection per viewed node, off the
  // active source's streaming book): shared by the chart's live beams and the
  // quote table's overlay; empty when the source is not streaming.
  const liveTicks = useLiveTicks(ticker, expiry, live, fitMode);
  // The chart's two frames (market = prevailing/live, calib = last calibration).
  const frames = useMemo(() => (smile ? composeFrames(smile, liveTicks) : null), [smile, liveTicks]);

  // Side-by-side model comparison (V3.2 item 12): fetched LAZILY — only while
  // the Compare view is open (up to 2 extra fits per node, server-cached).
  const comparison = useModelComparison(
    view === "compare",
    live,
    ticker,
    expiry,
    fitMode,
    spotVersion,
  );

  // Graph-extrapolation live overlay (plan Phase 5): when the user drilled into
  // THIS node from the Graph Extrapolate mode, fetch its reconstructed smile and
  // overlay the posterior curve + credible band on the quotes.
  const graphActive =
    live &&
    view === "smile" &&
    focus !== null &&
    focus.ticker === ticker &&
    focus.expiry === expiry;
  const graphNode = useGraphNodeSmile(graphActive, ticker, expiry, focus?.body ?? {});
  // Guard against a stale frame: only overlay when the response matches the node.
  const graphOverlay =
    graphActive && graphNode.node?.ticker === ticker && graphNode.node?.expiry === expiry
      ? graphNode.node
      : null;

  // Observation-filter overlay (Note 15 Phase 4): the filtered handle posterior
  // for the viewed node. Advisory + cheap; the hook yields null while the filter
  // is off or unseeded, so the overlay and badge simply don't render.
  const { data: filterDiag } = useObservationFilter(
    live && view === "smile",
    ticker,
    expiry,
    fitMode,
    spotVersion,
  );
  // The measurement breakdown is an open Record — the rho key may be absent.
  const filterRho: number | undefined = filterDiag?.measurementBreakdown["rho"];

  // Global keyboard shortcuts (Esc, Del, ↑↓ amend, Ctrl+Z/Y).
  useSmileShortcuts({ smile, source, selectedIndex, setSelectedIndex, applyEdit, undo, redo });

  /** Toggle exclusion of the selected quote (Exclude/Restore button, Del). */
  const toggleExclude = () => {
    if (selectedQuote === null) return;
    void applyEdit(
      selectedQuote.excluded ? "include" : "exclude",
      selectedQuote.index,
    );
  };

  /** Switch the chart-card view; arm the single-node distribution fetcher
   *  lazily (only the Log-Q-density view uses it now). */
  const switchView = (next: ChartView) => {
    setView(next);
    if (next === "logqd") loadDistribution();
  };

  /** Persist the current fit as the prior; flash a brief confirmation. */
  const onSavePrior = () => {
    void savePrior()
      .then(() => {
        setSavedFlash(true);
        if (flashTimer.current !== null) window.clearTimeout(flashTimer.current);
        flashTimer.current = window.setTimeout(() => setSavedFlash(false), 1500);
      })
      .catch(() => {
        // Failure is already surfaced through the session's editError.
      });
  };

  /** Chart-card body for the Density / Log-Q-density views (live backend only).
   *  A stale distribution keeps showing (dimmed via `refreshing`) while a
   *  replacement is in flight, mirroring how the smile itself behaves. */
  const distributionBody = (kind: "density" | "logqd") => {
    if (!live) return chartMessage("Distribution views require the live backend.");
    if (distribution !== null) {
      return (
        <DistributionChart
          kind={kind}
          current={distribution.current}
          prior={distribution.prior}
        />
      );
    }
    if (distributionLoading) return chartMessage("Loading distribution…");
    return chartMessage("Distribution unavailable for this node.");
  };

  /** Chart-card body for the active view. */
  const chartBody = () => {
    if (smile === null) {
      // Reachable backend, no smile yet: still loading -> "connecting"; retries
      // exhausted with an error -> surface it (we stay live, never mock).
      if (!loading && error !== null) return chartMessage(`Couldn't load this smile: ${error}`);
      return chartMessage("Loading market data…");
    }
    switch (view) {
      case "smile":
        return (
          <SmileChart
            market={(frames ?? composeFrames(smile, liveTicks)).market}
            calib={(frames ?? composeFrames(smile, liveTicks)).calib}
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
            varSwapLevel={
              smile.varSwap.enabled && !smile.varSwap.excluded ? smile.varSwap.level : null
            }
            graphPost={graphOverlay?.post ?? null}
            graphBandLo={graphOverlay?.postBandLo ?? null}
            graphBandHi={graphOverlay?.postBandHi ?? null}
            filterPost={filterDiag?.post ?? null}
            filterBandLo={filterDiag?.postBandLo ?? null}
            filterBandHi={filterDiag?.postBandHi ?? null}
            filterPred={filterDiag?.predCurve ?? null}
            fitBandHalf={
              smile.diagnostics.atmVolStd != null ? 1.96 * smile.diagnostics.atmVolStd : null
            }
            degraded={smile.degraded ?? null}
            fitMode={fitMode}
            showTarget={showTarget}
            autoScaleY={autoScaleY}
            footer={
              showWeights ? (
                <WeightStrip
                  live={live}
                  ticker={ticker}
                  expiry={expiry}
                  fitMode={fitMode}
                  smile={smile}
                  kWindow={kWindow}
                  axisMode={axisMode}
                />
              ) : null
            }
          />
        );
      case "compare": {
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
              <OverlayCurvesChart
                series={compareSeries(comparison.data)}
                xLabel="log-moneyness k"
                yLabel="implied vol"
                zoomY
              />
            </div>
            <ModelCompareTable data={comparison.data} />
          </div>
        );
      }
      case "stackeddensity":
        return live
          ? <StackedDensityChart ticker={ticker} fitMode={fitMode} smile={smile} axisMode={axisMode} />
          : chartMessage("Densities require the live backend.");
      case "logqd":
        return distributionBody("logqd");
      case "term":
        return live
          ? <TermPanel />
          : chartMessage("Term-structure view requires the live backend.");
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
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: universe selectors · sub-tabs · view controls · status badges
          (same grammar as the Local Vol workspace). */}
      <UniverseHeader
        right={
          <>
            {/* Data-source badge: live backend vs built-in mock fallback */}
            <span
              title={error ?? undefined}
              className={[
                "rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider",
                source === "live"
                  ? "border-accent-500/40 bg-accent-500/10 text-accent-400"
                  : "border-amber-500/40 bg-amber-500/10 text-amber-400",
              ].join(" ")}
            >
              {source === "live" ? "LIVE" : "MOCK"}
            </span>
            {/* Stale badge: inputs changed since the last calibration */}
            {smile?.stale && (
              <span
                title="Inputs changed since the last calibration — press Calibrate (top bar) to refit"
                className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-amber-400"
              >
                STALE
              </span>
            )}
            {/* Transient confirmation that a completed refit refreshed the fit */}
            {updatedFlash && (
              <span className="volfit-fade-in rounded border border-accent-500/50 bg-accent-500/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-accent-300">
                UPDATED
              </span>
            )}
          </>
        }
      >
        {/* View toggle: smile / distributions / surface / table */}
        <SegmentedControl options={CHART_VIEWS} value={view} onChange={switchView} size="xs" />
        {/* Strike-axis display mode (smile / densities / surface / stacked IV) */}
        {AXIS_MODE_VIEWS.has(view) && (
          <select
            className={selectClass}
            value={axisMode}
            title="Strike-axis display mode"
            onChange={(e) => setAxisMode(e.target.value as AxisMode)}
          >
            {AXIS_MODE_OPTIONS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        )}
        {/* Fit-target overlay toggle: mid polyline + bid-ask/haircut ribbons
            (which band is emphasized follows the live fit target). */}
        {view === "smile" && (
          <button
            className={[
              "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
              showTarget
                ? "border-red-500/50 bg-red-500/10 text-red-300"
                : "border-slate-700 text-slate-400 hover:text-slate-200",
            ].join(" ")}
            title="Overlay the fit target (mid line + bid-ask / haircut band)"
            onClick={() => setShowTarget((v) => !v)}
          >
            Target
          </button>
        )}
        {/* Calibration frame toggles: the quotes + target the last fit used
            (muted, with your edits; the table's calibration columns) and the
            fit on its calibration spot. */}
        {(view === "smile" || view === "table") && (
          <button
            className={[
              "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
              showCalibQuotes
                ? "border-slate-400/60 bg-slate-500/15 text-slate-200"
                : "border-slate-700 text-slate-400 hover:text-slate-200",
            ].join(" ")}
            title="Show the quotes + target the last calibration used (with your exclusions / amended mids) next to the prevailing market — chart layer and table columns"
            onClick={() => setShowCalibQuotes((v) => !v)}
          >
            Calib. quotes
          </button>
        )}
        {view === "smile" && (
          <button
            className={[
              "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
              showCalibFit
                ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
                : "border-slate-700 text-slate-400 hover:text-slate-200",
            ].join(" ")}
            title="Show the fitted smile on its calibration spot (dashed) next to the fit rolled to the prevailing spot"
            onClick={() => setShowCalibFit((v) => !v)}
          >
            Calib. fit
          </button>
        )}
        {/* Calibration weight strip toggle (density vs effective weights). */}
        {view === "smile" && (
          <button
            className={[
              "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
              showWeights
                ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
                : "border-slate-700 text-slate-400 hover:text-slate-200",
            ].join(" ")}
            title="Show per-quote calibration weights under the chart (quote density vs the effective mean-1 weights)"
            onClick={() => setShowWeights((v) => !v)}
          >
            Weights
          </button>
        )}
        {/* Y-axis auto-scale chips: after any x zoom / pan / brush / axis-mode
            change, "Y fit" snaps the y window to everything in the visible
            x-range; "Y center" keeps the y zoom but recenters it on the data
            (fit wins when both are lit). Alt+wheel still zooms y manually. */}
        {view === "smile" && (
          <>
            <button
              className={[
                "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
                autoScaleY.center
                  ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
                  : "border-slate-700 text-slate-400 hover:text-slate-200",
              ].join(" ")}
              title="After any x-view change, keep the y window centered on the data in view (preserves your y zoom; alt+wheel still zooms y)"
              onClick={() => toggleAutoScale("center")}
            >
              Y center
            </button>
            <button
              className={[
                "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
                autoScaleY.fit
                  ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
                  : "border-slate-700 text-slate-400 hover:text-slate-200",
              ].join(" ")}
              title="After any x-view change, auto-fit the y-axis to every curve and quote in the visible x-range"
              onClick={() => toggleAutoScale("fit")}
            >
              Y fit
            </button>
          </>
        )}
      </UniverseHeader>

      {/* Body: chart card + diagnostics panel */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Chart card (briefly ringed when a refit lands) */}
        <div
          className={[
            "flex min-w-0 flex-1 flex-col rounded-xl border bg-surface-900 p-4 shadow-xl shadow-black/30",
            "transition-colors duration-500",
            updatedFlash ? "border-accent-500/70" : "border-slate-800",
          ].join(" ")}
        >
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {smile ? `${smile.ticker} · ${formatExpiry(smile.expiry, smile.T, format)}` : "Smile"}
            </h2>
            {/* Graph-extrapolation overlay badge: provenance + quote metrics,
                with a ✕ to dismiss the overlay (clears the drill-in focus). */}
            {graphOverlay !== null && (
              <span className="flex items-center gap-1.5 rounded border border-violet-500/40 bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
                <span className="font-semibold tracking-wider">GRAPH</span>
                <span className="uppercase text-violet-400/90">{graphOverlay.model}</span>
                <span className="text-violet-400/90">{graphOverlay.priorSource}</span>
                {graphOverlay.metrics !== null && (
                  <span className="font-mono text-violet-200/90">
                    RMS {(graphOverlay.metrics.rmsVol * 100).toFixed(2)}% · in-band{" "}
                    {(graphOverlay.metrics.insideSpreadHitRate * 100).toFixed(0)}%
                    {graphOverlay.metrics.standardizedResidual !== null &&
                      ` · ζ ${graphOverlay.metrics.standardizedResidual.toFixed(2)}`}
                  </span>
                )}
                {/* Functional posterior (R3 item 12): var-swap vol ± 1σ from the
                    delta-method pushforward; tail masses ride the tooltip. */}
                {graphOverlay.varSwapVol !== null && graphOverlay.varSwapVolSd !== null && (
                  <span
                    className="font-mono text-violet-200/90"
                    title={
                      `Posterior var-swap vol ± 1σ (functional band)` +
                      (graphOverlay.tailMassLeft !== null && graphOverlay.tailMassRight !== null
                        ? ` · tail mass beyond chart: left ${(graphOverlay.tailMassLeft * 100).toFixed(2)}%` +
                          (graphOverlay.tailMassLeftSd !== null
                            ? `±${(graphOverlay.tailMassLeftSd * 100).toFixed(2)}`
                            : "") +
                          `, right ${(graphOverlay.tailMassRight * 100).toFixed(2)}%` +
                          (graphOverlay.tailMassRightSd !== null
                            ? `±${(graphOverlay.tailMassRightSd * 100).toFixed(2)}`
                            : "")
                        : "")
                    }
                  >
                    · VS {(graphOverlay.varSwapVol * 100).toFixed(1)}±
                    {(graphOverlay.varSwapVolSd * 100).toFixed(1)}%
                  </span>
                )}
                <button
                  title="Dismiss the graph-extrapolation overlay"
                  className="ml-0.5 text-violet-400 hover:text-violet-200"
                  onClick={() => setFocus(null)}
                >
                  ✕
                </button>
              </span>
            )}
            {/* Observation-filter badge (Note 15): per-handle Kalman gains +
                measurement rho + provenance; amber-tinted when the measurement
                was flagged contaminated. Renders only while the filter is on. */}
            {filterDiag !== null && (
              <span
                title={`Observation filter (${filterDiag.mode}) — gains per handle (${filterDiag.handleNames.join(", ")})${filterDiag.resetReason !== null ? ` · reset: ${filterDiag.resetReason}` : ""}`}
                className={[
                  "flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] font-medium",
                  filterDiag.contaminated
                    ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
                    : "border-teal-500/40 bg-teal-500/10 text-teal-300",
                ].join(" ")}
              >
                <span className="font-semibold tracking-wider">FILTER</span>
                <span className="font-mono">
                  K {filterDiag.gain.map((g) => g.toFixed(2)).join("/")}
                </span>
                {filterRho !== undefined && (
                  <span className="font-mono">ρ {filterRho.toFixed(2)}</span>
                )}
                {filterDiag.provenance !== null && (
                  <span className={filterDiag.contaminated ? "text-amber-400/90" : "text-teal-400/90"}>
                    {filterDiag.provenance}
                  </span>
                )}
                {filterDiag.contaminated && <span className="font-semibold">cont.</span>}
              </span>
            )}
            {/* Surface refetch errors without unmounting the chart */}
            {error !== null && source === "live" && (
              <span className="truncate text-[10px] text-amber-400/80">
                {error}
              </span>
            )}
            {/* Quote-editing toolbar (+ last rejected-edit message) */}
            <div className="ml-auto flex items-center gap-2">
              {editError !== null && (
                <span className="max-w-56 truncate text-[10px] text-amber-400">
                  {editError}
                </span>
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
                title={
                  live
                    ? "Persist the current fit as the prior curve"
                    : "requires live backend"
                }
                onClick={onSavePrior}
              >
                <Bookmark size={12} strokeWidth={1.75} className="opacity-80" />
                {savedFlash ? "Saved ✓" : "Save prior"}
              </button>
            </div>
          </div>
          <div
            className={[
              "min-h-0 flex-1 transition-opacity duration-200",
              refreshing ? "opacity-60" : "opacity-100",
            ].join(" ")}
          >
            {chartBody()}
          </div>
          {/* Interaction hint */}
          <p className="mt-1 shrink-0 text-[10px] text-slate-600">
            {VIEW_HINTS[view]}
          </p>
        </div>

        {/* Diagnostics aside: model / scenario panels. Hidden on the Term
            sub-tab, which carries its own events / ladder controls column. */}
        {view !== "term" && <SmileAside />}
      </div>
    </div>
  );
}
