// Smile workspace: per-expiry implied volatility smile fitting and editing.
// Data comes from the shared smile session (FastAPI backend with a built-in
// mock fallback). The header (UniverseHeader) owns universe selection and
// expiry-class filtering; the aside (SmileAside) hosts diagnostics plus the
// scenario / forward / hyperparameter panels. The chart card offers five
// views — the editable Smile (with six strike-axis display modes), fitted
// Density / Log-Q-density, the 3D vol Surface and the quote Table (the last four
// require the live backend). Quote edits post to the backend fit session and
// the returned refit replaces the smile; shortcuts live in useSmileShortcuts.
import { useRef, useState } from "react";
import SmileChart from "../components/SmileChart";
import QuoteToolbar, { toolbarButtonClass } from "../components/QuoteToolbar";
import DistributionChart from "../components/DistributionChart";
import StackedDensityChart from "../components/StackedDensityChart";
import StackedVarianceChart from "../components/StackedVarianceChart";
import TermPanel from "../components/TermPanel";
import SurfaceChart from "../components/SurfaceChart";
import QuoteTable from "../components/QuoteTable";
import UniverseHeader, { selectClass } from "../components/UniverseHeader";
import SmileAside from "../components/SmileAside";
import SegmentedControl from "../components/SegmentedControl";
import { useSmileSession } from "../state/smileSession";
import { useSmileShortcuts } from "../state/useSmileShortcuts";
import { useMassiveIv } from "../state/useMassiveIv";
import { AXIS_MODE_OPTIONS } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";

/** Chart-card content. "Stacked densities" overlays every expiry's density
 *  (no butterfly arb ⇔ all ≥ 0); "Stacked IV" overlays total variance w=σ²T
 *  (no calendar arb ⇔ curves don't cross). ROADMAP Phase 10. */
type ChartView =
  | "smile"
  | "stackeddensity"
  | "logqd"
  | "term"
  | "surface"
  | "stackedvar"
  | "table";

const CHART_VIEWS: { id: ChartView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "stackeddensity", label: "Stacked densities" },
  { id: "logqd", label: "Log Q-density" },
  { id: "term", label: "Term" },
  { id: "surface", label: "Surface" },
  { id: "stackedvar", label: "Stacked IV" },
  { id: "table", label: "Table" },
];

/** Interaction hint shown under the chart card, per view. */
const VIEW_HINTS: Record<ChartView, string> = {
  smile: "Click a quote · Del exclude · ↑↓ amend · Ctrl+Z undo",
  stackeddensity: "All expiries' densities overlaid · staying ≥ 0 ⇒ no butterfly arbitrage",
  logqd: "Log quantile density ℓ(u) = log q(u) of the current fit",
  term: "ATM term structure across the expiry ladder · real / event-dilated clock",
  surface: "Drag to rotate · σ(k, T) across the expiry ladder",
  stackedvar: "Total variance w=σ²·T per expiry · non-crossing ⇒ no calendar arbitrage",
  table: "Per-strike quotes vs the current fit · Copy / CSV in the footer",
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
  } = useSmileSession();

  const [kWindow, setKWindow] = useState<[number, number]>([0, 1]);
  // Selected quote, referenced by its stable `index` field (not array
  // position) so the selection keeps its identity across refits.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  // Chart-card view (smile / density / quantile / surface / table).
  const [view, setView] = useState<ChartView>("smile");
  // Strike-axis display mode of the smile chart (labels only).
  const [axisMode, setAxisMode] = useState<AxisMode>("logmoneyness");
  // Read-only Massive-IV comparison overlay toggle (Massive provider only).
  const [showMassiveIv, setShowMassiveIv] = useState(false);
  // Transient "Saved ✓" confirmation on the Save-prior button.
  const [savedFlash, setSavedFlash] = useState(false);
  const flashTimer = useRef<number | null>(null);

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

  // Resolve the selection against the current quote list; a refit that
  // drops the quote simply yields no selection.
  const selectedQuote =
    smile !== null && selectedIndex !== null
      ? (smile.quotes.find((q) => q.index === selectedIndex) ?? null)
      : null;
  const hasEdits =
    smile !== null && smile.quotes.some((q) => q.excluded || q.amended);
  const live = source === "live";

  // Read-only Massive-IV comparison overlay for the current node (null unless
  // the toggle is on, the smile view is active, and the provider is Massive).
  const massiveIvCurve = useMassiveIv(
    live,
    ticker,
    expiry,
    smile?.forward ?? 0,
    showMassiveIv && view === "smile",
  );

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
    if (loading || smile === null) return chartMessage("Loading universe…");
    switch (view) {
      case "smile":
        return (
          <SmileChart
            model={smile.model}
            prior={smile.prior}
            quotes={smile.quotes}
            scenario={scenarioCurve}
            massiveIv={massiveIvCurve}
            kWindow={kWindow}
            onKWindowChange={setKWindow}
            fullRange={[smile.kMin, smile.kMax]}
            axisMode={axisMode}
            forward={smile.forward}
            t={smile.T}
            atmVol={smile.diagnostics.atmVol}
            selectedIndex={selectedIndex}
            onQuoteSelect={setSelectedIndex}
          />
        );
      case "stackeddensity":
        return live
          ? <StackedDensityChart ticker={ticker} fitMode={fitMode} smile={smile} />
          : chartMessage("Stacked densities require the live backend.");
      case "logqd":
        return distributionBody("logqd");
      case "term":
        return live
          ? <TermPanel />
          : chartMessage("Term-structure view requires the live backend.");
      case "surface":
        return live
          ? <SurfaceChart ticker={ticker} fitMode={fitMode} />
          : chartMessage("Surface view requires the live backend.");
      case "stackedvar":
        return live
          ? <StackedVarianceChart ticker={ticker} fitMode={fitMode} />
          : chartMessage("Stacked IV requires the live backend.");
      case "table":
        return live
          ? <QuoteTable ticker={ticker} expiry={expiry} fitMode={fitMode} smile={smile} />
          : chartMessage("Table view requires the live backend.");
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: universe selectors, expiry-class filter, fit-mode control */}
      <UniverseHeader />

      {/* Body: chart card + diagnostics panel */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Chart card */}
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {smile ? `${smile.ticker} · ${smile.expiry}` : "Smile"}
            </h2>
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
            {/* View toggle: smile / distributions / surface / table */}
            <SegmentedControl
              options={CHART_VIEWS}
              value={view}
              onChange={switchView}
              size="xs"
            />
            {/* Strike-axis display mode (smile view only) */}
            {view === "smile" && (
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
            {/* Read-only Massive-IV overlay toggle (no-op unless the backend
                runs the Massive provider; the dots simply won't appear). */}
            {view === "smile" && live && (
              <button
                className={[
                  "rounded border px-2 py-0.5 text-[11px] font-medium transition-colors",
                  showMassiveIv
                    ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                    : "border-slate-700 text-slate-400 hover:text-slate-200",
                ].join(" ")}
                title="Overlay Massive's own implied vols (read-only comparison)"
                onClick={() => setShowMassiveIv((v) => !v)}
              >
                Massive IV
              </button>
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
        {view !== "term" && <SmileAside smileViewActive={view === "smile"} />}
      </div>
    </div>
  );
}
