// Smile workspace: per-expiry implied volatility smile fitting and editing.
// Data comes from the shared smile session (FastAPI backend with a built-in
// mock fallback). Quotes can be selected on the chart and edited — exclude /
// amend mid / undo / redo — via the toolbar or keyboard; each edit posts to
// the backend fit session and the returned refit replaces the smile.
// The chart card also offers fitted Density / Quantile views, and the
// diagnostics aside hosts the SSR "Spot scenario" overlay panel.
import { useEffect, useRef, useState } from "react";
import SmileChart from "../components/SmileChart";
import QuoteToolbar, { toolbarButtonClass } from "../components/QuoteToolbar";
import DistributionChart from "../components/DistributionChart";
import ScenarioPanel from "../components/ScenarioPanel";
import HyperparamPanel from "../components/HyperparamPanel";
import SegmentedControl from "../components/SegmentedControl";
import { useSmileSession } from "../state/smileSession";
import type { FitMode } from "../state/useSmile";
import { formatPct } from "../lib/chartScale";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

/** Chart-card content: the smile itself or a fitted-distribution view. */
type ChartView = "smile" | "density" | "quantile";

const CHART_VIEWS: { id: ChartView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "density", label: "Density" },
  { id: "quantile", label: "Quantile" },
];

/** Shared styling for the header selectors. */
const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

/** Centered placeholder for the chart-card body states. */
const chartMessage = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function SmileViewer() {
  const {
    smile,
    universe,
    source,
    loading,
    refreshing,
    error,
    editError,
    ticker,
    expiry,
    fitMode,
    setTicker,
    setExpiry,
    setFitMode,
    applyEdit,
    undo,
    redo,
    savePrior,
    reload,
    scenario,
    setScenario,
    scenarioCurve,
    scenarioSsr,
    distribution,
    distributionLoading,
    loadDistribution,
  } = useSmileSession();

  const [kWindow, setKWindow] = useState<[number, number]>([0, 1]);
  // Selected quote, referenced by its stable `index` field (not array
  // position) so the selection keeps its identity across refits.
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  // Chart-card view (smile / density / quantile).
  const [view, setView] = useState<ChartView>("smile");
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

  /** Toggle exclusion of the selected quote (Exclude/Restore button, Del). */
  const toggleExclude = () => {
    if (selectedQuote === null) return;
    void applyEdit(
      selectedQuote.excluded ? "include" : "exclude",
      selectedQuote.index,
    );
  };

  /** Switch the chart-card view; arm the distribution fetcher lazily. */
  const switchView = (next: ChartView) => {
    setView(next);
    if (next !== "smile") loadDistribution();
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

  // Global keyboard shortcuts. Registered on window so the chart needs no
  // focus; events originating from form controls are left alone.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = e.target instanceof HTMLElement ? e.target.tagName : "";
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (e.key === "Escape") {
        setSelectedIndex(null);
        return;
      }
      if (source !== "live") return; // edits require the live backend
      if (e.ctrlKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        if (e.shiftKey) void redo();
        else void undo();
        return;
      }
      if (e.ctrlKey && (e.key === "y" || e.key === "Y")) {
        e.preventDefault();
        void redo();
        return;
      }
      // Remaining shortcuts act on the selected quote of the current smile.
      const quote =
        smile !== null && selectedIndex !== null
          ? smile.quotes.find((q) => q.index === selectedIndex)
          : undefined;
      if (quote === undefined) return;
      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        void applyEdit(quote.excluded ? "include" : "exclude", quote.index);
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        // Nudge the mid IV from its CURRENT value: ±0.1 vol pt, ×5 w/ Shift.
        const step = (e.shiftKey ? 0.005 : 0.001) * (e.key === "ArrowUp" ? 1 : -1);
        void applyEdit("amend", quote.index, quote.mid + step);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [smile, selectedIndex, source, applyEdit, undo, redo]);

  // Expiry ladder of the currently selected ticker (drives the select).
  const ladder = universe?.expiries[ticker] ?? [];

  const diagnostics: { label: string; value: string }[] = smile
    ? [
        { label: "ATM vol", value: formatPct(smile.diagnostics.atmVol) },
        { label: "Skew", value: smile.diagnostics.skew.toFixed(3) },
        { label: "Curvature", value: smile.diagnostics.curvature.toFixed(2) },
        { label: "A_L (left wing)", value: smile.diagnostics.aLeft.toFixed(3) },
        { label: "A_R (right wing)", value: smile.diagnostics.aRight.toFixed(3) },
        { label: "Lee slope L", value: smile.diagnostics.leeLeft.toFixed(3) },
        { label: "Lee slope R", value: smile.diagnostics.leeRight.toFixed(3) },
        { label: "Var-swap vol", value: formatPct(smile.diagnostics.varSwapVol) },
      ]
    : [];

  /** Chart-card body for the Density / Quantile views (live backend only).
   *  A stale distribution keeps showing (dimmed via `refreshing`) while a
   *  replacement is in flight, mirroring how the smile itself behaves. */
  const distributionBody = (kind: "density" | "quantile") => {
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

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: universe selectors + fit-mode control */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Underlying
          <select
            className={selectClass}
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            disabled={universe === null}
          >
            {(universe?.tickers ?? []).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2 text-xs text-slate-500">
          Expiry
          <select
            className={selectClass}
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            disabled={universe === null}
          >
            {ladder.map((rung) => (
              <option key={rung.expiry} value={rung.expiry}>
                {rung.expiry} (T={rung.t.toFixed(2)}y)
              </option>
            ))}
          </select>
        </label>

        {/* Fit-mode segmented control */}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-500">Fit to</span>
          <SegmentedControl options={FIT_MODES} value={fitMode} onChange={setFitMode} />
        </div>
      </div>

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
            {/* View toggle: smile vs fitted-distribution charts */}
            <SegmentedControl
              options={CHART_VIEWS}
              value={view}
              onChange={switchView}
              size="xs"
            />
            {view === "smile" && (
              <span className="font-mono text-[11px] text-slate-500">
                k = ln(K/F)
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
            {loading || smile === null ? (
              chartMessage("Loading universe…")
            ) : view === "smile" ? (
              <SmileChart
                model={smile.model}
                prior={smile.prior}
                quotes={smile.quotes}
                scenario={scenarioCurve}
                kWindow={kWindow}
                onKWindowChange={setKWindow}
                fullRange={[smile.kMin, smile.kMax]}
                axisMode="logmoneyness"
                forward={smile.forward}
                selectedIndex={selectedIndex}
                onQuoteSelect={setSelectedIndex}
              />
            ) : (
              distributionBody(view)
            )}
          </div>
          {/* Interaction hint */}
          <p className="mt-1 shrink-0 text-[10px] text-slate-600">
            {view === "smile"
              ? "Click a quote · Del exclude · ↑↓ amend · Ctrl+Z undo"
              : "Risk-neutral distribution implied by the current fit"}
          </p>
        </div>

        {/* Diagnostics panel */}
        <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <h3 className="mb-1 text-sm font-semibold text-slate-100">
            Fit diagnostics
          </h3>
          <p className="mb-4 text-[11px] text-slate-500">
            {smile
              ? `Current calibration · ${smile.ticker} ${smile.expiry}`
              : "Awaiting data…"}
          </p>
          <dl className="divide-y divide-slate-800">
            {diagnostics.map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between py-2"
              >
                <dt className="text-xs text-slate-400">{row.label}</dt>
                <dd className="font-mono text-xs font-medium text-slate-100">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>

          {/* Spot scenario: drives the SSR overlay on the smile chart */}
          <div className="mt-4 border-t border-slate-800 pt-4">
            <ScenarioPanel
              scenario={scenario}
              onScenarioChange={setScenario}
              scenarioCurve={scenarioCurve}
              ssr={scenarioSsr}
              model={smile?.model ?? null}
              disabled={!live || view !== "smile"}
              disabledReason={
                !live
                  ? "requires live backend"
                  : "scenario overlay applies to the Smile view"
              }
            />
          </div>

          {/* Global fit hyperparameters (model, N, damping) */}
          <div className="mt-4 border-t border-slate-800 pt-4">
            <HyperparamPanel disabled={!live} onApplied={reload} />
          </div>
        </aside>
      </div>
    </div>
  );
}
