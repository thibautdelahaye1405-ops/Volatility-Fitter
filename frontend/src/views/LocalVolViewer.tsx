// Local Vol workspace: direct piecewise-affine local-variance surface fit.
//
// Calibrates the local-vol surface straight to the ticker's option quotes
// (POST /fit/affine/{ticker}) and shows three things side by side: the nodal
// local-vol heatmap, the per-expiry reconstructed arbitrage-free smiles vs
// quotes, and the fit / no-arbitrage diagnostics with vertex-grid and
// regularization controls. Live backend only (no mock fallback), like the
// Term and Graph workspaces.
import { useEffect, useState } from "react";
import LocalVolHeatmap from "../components/LocalVolHeatmap";
import LocalVolSmile from "../components/LocalVolSmile";
import { useAffine } from "../state/useAffine";

const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** Log-spaced roughness presets (Off = pure data fit). */
const REG_LAMBDAS = [0, 1e-3, 1e-2, 1e-1, 1];
const regLabel = (v: number) => (v === 0 ? "Off" : `1e${Math.round(Math.log10(v))}`);

export default function LocalVolViewer() {
  const {
    data,
    loading,
    refreshing,
    error,
    reload,
    ticker,
    setTicker,
    tickers,
    params,
    setParams,
  } = useAffine();

  // Selected expiry for the reconstructed-smile chart, clamped to range.
  const [expiryIdx, setExpiryIdx] = useState(0);
  useEffect(() => {
    if (data && expiryIdx >= data.smiles.length) setExpiryIdx(0);
  }, [data, expiryIdx]);

  if (error !== null && data === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Local-vol fit requires the live backend
          </h2>
          <p className="mb-1 text-xs text-slate-500">
            Start the FastAPI server on :8000 and retry.
          </p>
          <p className="mb-5 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </p>
          <button className={buttonClass} onClick={reload}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const smile = data?.smiles[expiryIdx];

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Underlying
          <select
            className={selectClass}
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            disabled={tickers.length === 0}
          >
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
        <span className="text-[11px] text-slate-500">
          direct piecewise-affine local-variance calibration
        </span>
        {data && (
          <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-slate-500">
            <span
              className={
                data.arbitrageFree
                  ? "rounded bg-emerald-600/15 px-1.5 py-0.5 text-emerald-400"
                  : "rounded bg-amber-600/15 px-1.5 py-0.5 text-amber-400"
              }
            >
              {data.arbitrageFree ? "arb-free" : `${data.calendarViolations} cal. viol.`}
            </span>
            rms {data.rmsIvErrorBp.toFixed(0)} · max {data.maxIvErrorBp.toFixed(0)} bp
          </span>
        )}
      </div>

      {/* Body */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Heatmap + smile column */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {/* Heatmap card */}
          <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
            <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-100">
              {ticker !== "" ? `${ticker} local-vol surface` : "Local-vol surface"}
            </h2>
            <div
              className={[
                "min-h-0 flex-1 transition-opacity duration-200",
                refreshing ? "opacity-60" : "opacity-100",
              ].join(" ")}
            >
              {loading || data === null ? (
                <div className="flex h-full items-center justify-center text-xs text-slate-500">
                  Calibrating local-vol surface…
                </div>
              ) : (
                <LocalVolHeatmap
                  tNodes={data.tNodes}
                  xNodes={data.xNodes}
                  localVol={data.localVol}
                />
              )}
            </div>
          </div>

          {/* Reconstructed-smile card */}
          <div className="flex min-h-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
            <div className="mb-2 flex shrink-0 flex-wrap items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-100">Reconstructed smile</h2>
              {smile && (
                <span className="font-mono text-[11px] text-slate-500">
                  arbitrage-free · max err {smile.maxIvErrorBp.toFixed(0)} bp
                </span>
              )}
              {/* Expiry selector */}
              <div className="ml-auto flex max-w-full flex-wrap gap-1">
                {(data?.smiles ?? []).map((s, i) => (
                  <button
                    key={s.expiry}
                    onClick={() => setExpiryIdx(i)}
                    className={[
                      "rounded px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                      i === expiryIdx
                        ? "bg-accent-600/25 text-accent-400"
                        : "text-slate-500 hover:text-slate-300",
                    ].join(" ")}
                    title={s.expiry}
                  >
                    {s.t.toFixed(2)}y
                  </button>
                ))}
              </div>
            </div>
            <div className="min-h-0 flex-1">
              {smile ? (
                <LocalVolSmile smile={smile} />
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-slate-500">
                  {loading ? "Fitting…" : "No smile"}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Controls + diagnostics aside */}
        <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <div>
            <h3 className="mb-2 text-sm font-semibold text-slate-100">Vertex grid</h3>
            <SliderRow
              label="Strike nodes"
              value={params.nXNodes}
              min={3}
              max={13}
              step={1}
              onChange={(v) => setParams({ nXNodes: v })}
            />
            <SliderRow
              label="Time nodes"
              value={params.nTNodes}
              min={2}
              max={8}
              step={1}
              onChange={(v) => setParams({ nTNodes: v })}
            />
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-slate-400" title="Second-difference roughness penalty">
                Roughness λ
              </span>
              <select
                value={params.regLambda}
                onChange={(e) => setParams({ regLambda: Number(e.target.value) })}
                className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500"
              >
                {REG_LAMBDAS.map((v) => (
                  <option key={v} value={v}>
                    {regLabel(v)}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Per-expiry diagnostics */}
          <div className="border-t border-slate-800 pt-3">
            <h3 className="mb-2 text-sm font-semibold text-slate-100">Per-expiry fit</h3>
            <table className="w-full text-right font-mono text-[10px]">
              <thead>
                <tr className="text-slate-600">
                  <th className="pb-1 text-left font-normal">expiry</th>
                  <th className="pb-1 font-normal">T</th>
                  <th className="pb-1 font-normal">err bp</th>
                  <th className="pb-1 font-normal">min φ</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                {(data?.smiles ?? []).map((s, i) => (
                  <tr
                    key={s.expiry}
                    onClick={() => setExpiryIdx(i)}
                    className={[
                      "cursor-pointer border-t border-slate-800/60",
                      i === expiryIdx ? "text-accent-400" : "hover:text-slate-100",
                    ].join(" ")}
                  >
                    <td className="py-1 text-left text-slate-400">{s.expiry}</td>
                    <td>{s.t.toFixed(2)}</td>
                    <td>{s.maxIvErrorBp.toFixed(0)}</td>
                    <td>{(data?.minDensity[i] ?? 0).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-[10px] text-slate-600">
              min φ &gt; 0 ⇒ no butterfly arbitrage (Breeden–Litzenberger density).
            </p>
          </div>

          {data && (
            <p className="mt-auto shrink-0 text-[10px] text-slate-600">
              {data.nEvals} PDE solves · price rms {(data.rmsPriceError * 1e4).toFixed(1)} bp
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}

/** A labelled integer slider row for the vertex-grid controls. */
function SliderRow({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="mb-1">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">{label}</span>
        <span className="font-mono text-xs font-medium text-slate-100">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full cursor-pointer"
        style={{ accentColor: "var(--color-accent-500)" }}
      />
    </div>
  );
}
