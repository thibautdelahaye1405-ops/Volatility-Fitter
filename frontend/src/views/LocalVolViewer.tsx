// Local Vol workspace: direct piecewise-affine local-variance surface fit.
//
// Calibrates the local-vol surface straight to the ticker's option quotes
// (POST /fit/affine/{ticker}) and presents Parametric-style sub-tabs, every
// view DERIVED from that calibrated surface (ROADMAP Phase 10):
//   Smile    reconstructed arbitrage-free smile vs quotes (per expiry)
//   Density  Breeden-Litzenberger density of the reconstructed smile
//   Term     ATM / var-swap term structure across the ladder
//   Surface  the nodal local-vol heatmap
//   Table    per-strike reconstructed IVs + prices (per expiry)
// The derived Density / Term / Table views fetch sibling endpoints that reuse
// the cached affine fit (useAffineView). Live backend only (no mock fallback).
import { useEffect, useMemo, useState } from "react";
import LocalVolHeatmap from "../components/LocalVolHeatmap";
import LocalVolSmile from "../components/LocalVolSmile";
import LocalVolTable from "../components/LocalVolTable";
import type { AffineTableData } from "../components/LocalVolTable";
import SurfaceMesh from "../components/SurfaceMesh";
import type { SurfaceMeshData } from "../components/SurfaceMesh";
import DistributionChart from "../components/DistributionChart";
import TermChart from "../components/TermChart";
import SegmentedControl from "../components/SegmentedControl";
import ExpiryFormatToggle from "../components/ExpiryFormatToggle";
import VarSwapPanel from "../components/VarSwapPanel";
import { useSmileSession } from "../state/smileSession";
import { useAffine } from "../state/useAffine";
import { useAffineView } from "../state/useAffineView";
import { useEvents } from "../state/useTerm";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import type { DistributionData } from "../state/useScenario";
import type { ClockMode, TermResponse } from "../state/useTerm";

const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";


/** Chart-card sub-tabs, mirroring the Parametric workspace. "LV surface" is the
 *  nodal local-vol heatmap; "IV surface" is the reconstructed implied-vol
 *  surface (both heatmaps over t × strike). */
type LvView = "smile" | "density" | "term" | "lvsurface" | "ivsurface" | "table";
const LV_VIEWS: { id: LvView; label: string }[] = [
  { id: "smile", label: "Smile" },
  { id: "density", label: "Density" },
  { id: "term", label: "Term" },
  { id: "lvsurface", label: "LV surface" },
  { id: "ivsurface", label: "IV surface" },
  { id: "table", label: "Table" },
];
/** Which sub-tabs are per-expiry (need the expiry selector). */
const PER_EXPIRY: Record<LvView, boolean> = {
  smile: true, density: true, table: true, term: false, lvsurface: false, ivsurface: false,
};

const chartMessage = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function LocalVolViewer() {
  const {
    data, loading, refreshing, error, reload, ticker, setTicker, tickers,
    varSwapEnabled, varSwapNonce, applyVarSwap, undoVarSwap, redoVarSwap,
  } = useAffine();

  const { source, spotVersion } = useSmileSession();
  const live = source === "live";
  // Spot moves transport the cached surface; fold into the derived-view key so
  // density / term / table refetch alongside the surface (which depends on it
  // via useAffine). Combined with varSwapNonce into one reloadKey.
  const lvReloadKey = varSwapNonce + spotVersion;
  const { format } = useExpiryFormat();
  const [view, setView] = useState<LvView>("smile");
  // Shared per-ticker event calendar (read-only here; edited in Parametric Term)
  // + maturity-clock toggle, so event-time dilation is consistent in LV's Term.
  const events = useEvents(ticker);
  const [axisClock, setAxisClock] = useState<ClockMode>("real");
  // Selected expiry for the per-expiry views, clamped to range.
  const [expiryIdx, setExpiryIdx] = useState(0);
  useEffect(() => {
    if (data && expiryIdx >= data.smiles.length) setExpiryIdx(0);
  }, [data, expiryIdx]);

  const expiry = data?.smiles[expiryIdx]?.expiry ?? null;

  // Derived views reuse the cached affine fit; only the active one fetches.
  const density = useAffineView<DistributionData>(
    "density", ticker, expiry, view === "density", lvReloadKey,
  );
  const term = useAffineView<TermResponse>("term", ticker, null, view === "term", lvReloadKey);
  const table = useAffineView<AffineTableData>(
    "table", ticker, expiry, view === "table", lvReloadKey,
  );

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
          <button className={buttonClass} onClick={reload}>Retry</button>
        </div>
      </div>
    );
  }

  const smile = data?.smiles[expiryIdx];

  // Reconstructed IV surface: resample every expiry's smile onto a shared
  // log-moneyness grid (intersection range, no extrapolation) → 3D σ_IV mesh.
  const ivSurface = useMemo(() => (data ? buildIvSurface(data.smiles) : null), [data]);

  /** Chart-card body for the active sub-tab. */
  const chartBody = () => {
    if (loading || data === null) return chartMessage("Calibrating local-vol surface…");
    switch (view) {
      case "lvsurface":
        return <LocalVolHeatmap tNodes={data.tNodes} xNodes={data.xNodes} localVol={data.localVol} />;
      case "ivsurface":
        return ivSurface
          ? <SurfaceMesh data={ivSurface} legendLabel="σ_IV(k, T)" />
          : chartMessage("IV surface needs at least two overlapping expiries.");
      case "smile":
        return smile ? <LocalVolSmile smile={smile} /> : chartMessage("No smile");
      case "density":
        return density.data
          ? <DistributionChart kind="density" current={density.data.current} prior={density.data.prior} />
          : chartMessage(density.error ?? "Loading density…");
      case "term":
        return term.data
          ? (
            <TermChart
              points={term.data.points}
              curve={term.data.curve}
              events={events}
              eventsEnabled={events.length > 0}
              axisClock={axisClock}
              dividends={term.data.dividends}
              selectedExpiry={smile?.expiry ?? null}
              onSelectExpiry={(e) => {
                const idx = data?.smiles.findIndex((s) => s.expiry === e) ?? -1;
                if (idx >= 0) setExpiryIdx(idx);
              }}
            />
          )
          : chartMessage(term.error ?? "Loading term structure…");
      case "table":
        return table.data ? <LocalVolTable data={table.data} /> : chartMessage(table.error ?? "Loading table…");
    }
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: ticker + sub-tab selector + expiry chips + arb badge */}
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
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>

        <SegmentedControl options={LV_VIEWS} value={view} onChange={setView} size="xs" />
        <ExpiryFormatToggle />

        {/* Maturity clock (Term sub-tab): real vs shared event-dilated time */}
        {view === "term" && (
          <SegmentedControl
            options={[
              { id: "real" as ClockMode, label: "Real time" },
              { id: "dilated" as ClockMode, label: "Event-dilated" },
            ]}
            value={axisClock}
            onChange={setAxisClock}
            size="xs"
          />
        )}

        {/* Per-expiry selector (smile / density / table) */}
        {PER_EXPIRY[view] && (
          <div className="flex max-w-full flex-wrap gap-1">
            {(data?.smiles ?? []).map((s, i) => (
              <button
                key={s.expiry}
                onClick={() => setExpiryIdx(i)}
                className={[
                  "rounded px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                  i === expiryIdx ? "bg-accent-600/25 text-accent-400" : "text-slate-500 hover:text-slate-300",
                ].join(" ")}
                title={s.expiry}
              >
                {formatExpiry(s.expiry, s.t, format)}
              </button>
            ))}
          </div>
        )}

        {data && (
          <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-slate-500">
            {data.stale && (
              <span
                title="Inputs changed since the last LV calibration — press Calibrate (top bar)"
                className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 font-semibold tracking-wider text-amber-400"
              >
                STALE
              </span>
            )}
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

      {/* Body: chart card + controls aside */}
      <div className="flex min-h-0 flex-1 gap-4">
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {ticker !== "" ? `${ticker} local vol` : "Local vol"}
              {PER_EXPIRY[view] && smile ? ` · ${formatExpiry(smile.expiry, smile.t, format)}` : ""}
            </h2>
            {smile && PER_EXPIRY[view] && (
              <span className="font-mono text-[11px] text-slate-500">
                arbitrage-free · max err {smile.maxIvErrorBp.toFixed(0)} bp
              </span>
            )}
          </div>
          <div
            className={[
              "min-h-0 flex-1 transition-opacity duration-200",
              refreshing ? "opacity-60" : "opacity-100",
            ].join(" ")}
          >
            {chartBody()}
          </div>
        </div>

        {/* Controls + diagnostics aside */}
        <aside className="flex w-72 shrink-0 flex-col gap-4 overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <div>
            <h3 className="mb-1 text-sm font-semibold text-slate-100">Vertex grid</h3>
            <p className="text-[11px] text-slate-500">
              Grid size (strike/time nodes) &amp; roughness λ, ρ are global
              hyperparameters — set them in the <span className="text-slate-300">Options</span> tab
              (with an "Optimal size" button). Time vertices default to the observed expiries.
            </p>
          </div>

          {/* Var-swap quote for the selected expiry (Options-gated, shared
              with the Parametric workspace) */}
          {varSwapEnabled && smile && (
            <div className="border-t border-slate-800 pt-3">
              <VarSwapPanel
                info={smile.varSwap}
                live={live}
                subtitle={`Editing ${formatExpiry(smile.expiry, smile.t, format)}`}
                onSet={(level) => void applyVarSwap(smile.expiry, "set", level)}
                onExclude={() => void applyVarSwap(smile.expiry, "exclude")}
                onInclude={() => void applyVarSwap(smile.expiry, "include")}
                onRemove={() => void applyVarSwap(smile.expiry, "remove")}
                onUndo={() => void undoVarSwap(smile.expiry)}
                onRedo={() => void redoVarSwap(smile.expiry)}
                onReset={() => void applyVarSwap(smile.expiry, "reset")}
              />
            </div>
          )}

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
                    <td className="py-1 text-left text-slate-400">
                      {formatExpiry(s.expiry, s.t, format)}
                    </td>
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

/** Linear interpolation of a sorted (k, vol) curve at log-moneyness k. */
function interpVol(model: { k: number; vol: number }[], k: number): number {
  if (model.length === 0) return NaN;
  if (k <= model[0].k) return model[0].vol;
  const last = model[model.length - 1];
  if (k >= last.k) return last.vol;
  for (let i = 1; i < model.length; i++) {
    if (k <= model[i].k) {
      const a = model[i - 1];
      const b = model[i];
      const f = (k - a.k) / (b.k - a.k);
      return a.vol + f * (b.vol - a.vol);
    }
  }
  return last.vol;
}

/** Reconstructed IV surface from the per-expiry affine smiles: resample each on
 *  a shared log-moneyness grid (the intersection range, so no curve is
 *  extrapolated) and return it as a (T × k → σ) mesh for the 3D SurfaceMesh. */
function buildIvSurface(
  smiles: { expiry: string; t: number; model: { k: number; vol: number }[] }[],
): SurfaceMeshData | null {
  const usable = smiles.filter((s) => s.model.length >= 2);
  if (usable.length < 2) return null;
  const kLo = Math.max(...usable.map((s) => s.model[0].k));
  const kHi = Math.min(...usable.map((s) => s.model[s.model.length - 1].k));
  if (!(kHi > kLo)) return null;
  const N = 41;
  const kGrid = Array.from({ length: N }, (_, j) => kLo + ((kHi - kLo) * j) / (N - 1));
  return {
    expiries: usable.map((s) => s.expiry),
    t: usable.map((s) => s.t),
    k: kGrid,
    vol: usable.map((s) => kGrid.map((k) => interpVol(s.model, k))),
  };
}

