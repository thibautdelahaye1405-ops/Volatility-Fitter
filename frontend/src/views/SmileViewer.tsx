// Smile workspace: per-expiry implied volatility smile fitting and editing.
// Data comes from the FastAPI backend via the useSmile hook, which falls
// back to the built-in mock payload whenever the backend is unreachable.
import { useState } from "react";
import SmileChart from "../components/SmileChart";
import { useSmile } from "../state/useSmile";
import type { FitMode } from "../state/useSmile";
import { formatPct } from "../lib/chartScale";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

/** Shared styling for the header selectors. */
const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function SmileViewer() {
  const {
    smile,
    universe,
    source,
    loading,
    refreshing,
    error,
    ticker,
    expiry,
    fitMode,
    setTicker,
    setExpiry,
    setFitMode,
  } = useSmile();

  const [kWindow, setKWindow] = useState<[number, number]>([0, 1]);

  // Reset the brush to the full extent whenever a *different* node loads
  // (ticker/expiry change). Refits of the same node keep the user's window.
  // State is adjusted during render (not in an effect) so the chart never
  // paints a frame with the previous node's window.
  const smileKey = smile ? `${smile.ticker}|${smile.expiry}` : "";
  const [prevSmileKey, setPrevSmileKey] = useState("");
  if (smile && smileKey !== prevSmileKey) {
    setPrevSmileKey(smileKey);
    setKWindow([smile.kMin, smile.kMax]);
  }

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
          <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
            {FIT_MODES.map((mode) => {
              const active = mode.id === fitMode;
              return (
                <button
                  key={mode.id}
                  onClick={() => setFitMode(mode.id)}
                  className={[
                    "px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-accent-600/25 text-accent-400"
                      : "text-slate-400 hover:text-slate-200",
                  ].join(" ")}
                >
                  {mode.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Body: chart card + diagnostics panel */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Chart card */}
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <div className="mb-2 flex shrink-0 items-baseline gap-2">
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
            <span className="font-mono text-[11px] text-slate-500">
              log-moneyness k = ln(K/F)
            </span>
            {/* Surface refetch errors without unmounting the chart */}
            {error !== null && source === "live" && (
              <span className="truncate text-[10px] text-amber-400/80">
                {error}
              </span>
            )}
          </div>
          <div
            className={[
              "min-h-0 flex-1 transition-opacity duration-200",
              refreshing ? "opacity-60" : "opacity-100",
            ].join(" ")}
          >
            {loading || smile === null ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-500">
                Loading universe…
              </div>
            ) : (
              <SmileChart
                model={smile.model}
                prior={smile.prior}
                quotes={smile.quotes}
                kWindow={kWindow}
                onKWindowChange={setKWindow}
                fullRange={[smile.kMin, smile.kMax]}
                axisMode="logmoneyness"
                forward={smile.forward}
              />
            )}
          </div>
        </div>

        {/* Diagnostics panel */}
        <aside className="w-72 shrink-0 rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
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
        </aside>
      </div>
    </div>
  );
}
