// Smile workspace: per-expiry implied volatility smile fitting and editing.
// Currently runs on built-in mock data; swap `getMockSmile()` for an
// `api.get<SmileData>(...)` call once the backend endpoints are live.
import { useMemo, useState } from "react";
import SmileChart from "../components/SmileChart";
import { getMockSmile } from "../lib/mockData";
import { formatPct } from "../lib/chartScale";

/** Quote-fitting objective (visual stub until the optimizer is wired). */
type FitMode = "mid" | "bidask" | "haircut";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

/** Shared styling for the header selector stubs. */
const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function SmileViewer() {
  // Mock payload is pure and deterministic; memoise once per mount.
  const smile = useMemo(() => getMockSmile(), []);
  const [kWindow, setKWindow] = useState<[number, number]>([
    smile.kMin,
    smile.kMax,
  ]);
  const [fitMode, setFitMode] = useState<FitMode>("mid");

  const d = smile.diagnostics;
  const diagnostics: { label: string; value: string }[] = [
    { label: "ATM vol", value: formatPct(d.atmVol) },
    { label: "Skew", value: d.skew.toFixed(3) },
    { label: "Curvature", value: d.curvature.toFixed(2) },
    { label: "A_L (left wing)", value: d.aLeft.toFixed(3) },
    { label: "A_R (right wing)", value: d.aRight.toFixed(3) },
    { label: "Lee slope L", value: d.leeLeft.toFixed(3) },
    { label: "Lee slope R", value: d.leeRight.toFixed(3) },
    { label: "Var-swap vol", value: formatPct(d.varSwapVol) },
  ];

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: universe selectors + fit-mode control (stubs for now) */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Underlying
          <select className={selectClass} defaultValue={smile.ticker}>
            <option value={smile.ticker}>{smile.ticker}</option>
          </select>
        </label>

        <label className="flex items-center gap-2 text-xs text-slate-500">
          Expiry
          <select className={selectClass} defaultValue={smile.expiry}>
            <option value={smile.expiry}>
              {smile.expiry} (T={smile.T}y)
            </option>
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
              {smile.ticker} · {smile.expiry}
            </h2>
            <span className="font-mono text-[11px] text-slate-500">
              log-moneyness k = ln(K/F)
            </span>
          </div>
          <div className="min-h-0 flex-1">
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
          </div>
        </div>

        {/* Diagnostics panel */}
        <aside className="w-72 shrink-0 rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <h3 className="mb-1 text-sm font-semibold text-slate-100">
            Fit diagnostics
          </h3>
          <p className="mb-4 text-[11px] text-slate-500">
            Current calibration · {smile.ticker} {smile.expiry}
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
