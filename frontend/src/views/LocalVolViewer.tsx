// Local Vol workspace: direct piecewise-affine local-variance surface fit.
//
// Calibrates the local-vol surface straight to the ticker's option quotes
// (POST /fit/affine/{ticker}) and presents Parametric-style sub-tabs, every
// view DERIVED from that calibrated surface (ROADMAP Phase 10):
//   Smile      reconstructed arbitrage-free smile vs quotes (per expiry)
//   Densities  every expiry's Breeden-Litzenberger density overlaid (≥ 0 ⇔ no
//              butterfly arb), mirroring the Parametric "Densities" view
//   Term       ATM / var-swap term structure across the ladder
//   LV surface the nodal local-vol grid — 3D local-variance mesh (default,
//              same renderer as the IV surface) or the flat vertex heatmap
//   IV surface reconstructed implied-vol mesh over t × strike
//   Stacked IV total variance w=σ²·τ per expiry (non-crossing ⇔ no calendar arb)
//   Table      per-strike reconstructed IVs + prices (per expiry)
// Densities / Stacked IV / IV surface are built client-side from the cached fit's
// per-expiry data; Term / Table fetch sibling endpoints that reuse the cached
// affine fit (useAffineView). Live backend only (no mock fallback).
//
// UI SHELL v2: the lens follows the workbench's active node tab — the ticker
// comes from the shared smile session (via useAffine) and the per-expiry
// views show the SESSION expiry (index derived, fallback 0 when the session
// expiry is not in the LV ladder). Any expiry pick made here (Term chart
// click, per-expiry table row) goes through selectExpiry(), which opens a
// preview tab; outside the shell it falls back to a local override.
// Header controls live in LocalVolToolbar; the diagnostics column in
// LocalVolAside.
import { useMemo, useState } from "react";
import LocalVolHeatmap from "../components/LocalVolHeatmap";
import LocalVolSmile from "../components/LocalVolSmile";
import LocalVolTable from "../components/LocalVolTable";
import type { AffineTableData } from "../components/LocalVolTable";
import SurfaceMesh from "../components/SurfaceMesh";
import type { SurfaceMeshData } from "../components/SurfaceMesh";
import OverlayCurvesChart, { maturityColor } from "../components/OverlayCurvesChart";
import type { OverlayMarker, OverlaySeries } from "../components/OverlayCurvesChart";
import TermChart from "../components/TermChart";
import LocalVolToolbar, { PER_EXPIRY, fmtBp0 } from "../components/localvol/LocalVolToolbar";
import type { LvAxis, LvRender, LvView } from "../components/localvol/LocalVolToolbar";
import LocalVolAside from "../components/localvol/LocalVolAside";
import { lvCalendarMarker } from "../lib/stackedVariance";
import { useSmileSession } from "../state/smileSession";
import { useOptionalWorkbench } from "../state/workbench";
import { useAffine } from "../state/useAffine";
import { useAffineView } from "../state/useAffineView";
import { useEvents } from "../state/useTerm";
import type { ClockMode, TermResponse } from "../state/useTerm";
import { useExpiryFormat } from "../state/expiryFormat";
import { buildIvSurface, smileAxisContext } from "../lib/affineSurface";
import { formatExpiry } from "../lib/expiryFormat";
import { axisModeLabel, axisTickLabel, axisTransform } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";
import { buttonClass, cardClass, chartMessageClass } from "../lib/ui";

const chartMessage = (text: string) => (
  <div className={chartMessageClass}>{text}</div>
);

export default function LocalVolViewer() {
  const {
    data, loading, refreshing, error, reload, ticker,
    varSwapEnabled, varSwapNonce, graphSource, setGraphSource,
    applyVarSwap, undoVarSwap, redoVarSwap,
  } = useAffine();

  const { source, spotVersion, fitMode, expiry: sessionExpiry } = useSmileSession();
  // Null outside the shell (tests / legacy mounts): fall back to local state.
  const wb = useOptionalWorkbench();
  const live = source === "live";
  // Spot moves transport the cached surface; fold into the derived-view key so
  // density / term / table refetch alongside the surface (which depends on it
  // via useAffine). Combined with varSwapNonce into one reloadKey.
  const lvReloadKey = varSwapNonce + spotVersion;
  const { format } = useExpiryFormat();
  const [view, setView] = useState<LvView>("smile");
  // Strike-axis display mode for the density / IV-surface / stacked-IV views.
  const [axisMode, setAxisMode] = useState<AxisMode>("logmoneyness");
  // LV-surface render mode: 3D local-variance mesh (default) or vertex heatmap.
  const [lvRender, setLvRender] = useState<LvRender>("mesh");
  // X-axis scale for the 3D LV mesh (the heatmap stays in x = K/F).
  const [lvAxis, setLvAxis] = useState<LvAxis>("moneyness");
  // Shared per-ticker event calendar (read-only here; edited in Parametric Term)
  // + maturity-clock toggle, so event-time dilation is consistent in LV's Term.
  const events = useEvents(ticker);
  const [axisClock, setAxisClock] = useState<ClockMode>("real");

  // Selected expiry for the per-expiry views = the session's (the active tab
  // drives it inside the shell). Without a workbench a local override stands
  // in for the tab strip. Index falls back to 0 when the expiry is not in the
  // LV ladder (findIndex → -1) or before the fit lands.
  const [localExpiry, setLocalExpiry] = useState<string | null>(null);
  const wantedExpiry = wb !== null ? sessionExpiry : (localExpiry ?? sessionExpiry);
  const expiryIdx = Math.max(0, data?.smiles.findIndex((s) => s.expiry === wantedExpiry) ?? 0);
  /** Select an expiry from inside the lens: open / focus its node's preview tab
   *  (the tab pushes it into the session), or the local fallback off-shell. */
  const selectExpiry = (e: string) => {
    if (wb !== null) wb.openNode({ ticker, expiry: e }, { preview: true });
    else setLocalExpiry(e);
  };

  const expiry = data?.smiles[expiryIdx]?.expiry ?? null;

  // Derived views reuse the cached affine fit; only the active one fetches.
  const term = useAffineView<TermResponse>("term", ticker, null, view === "term", lvReloadKey, fitMode);
  const table = useAffineView<AffineTableData>(
    "table", ticker, expiry, view === "table", lvReloadKey, fitMode,
  );

  const smile = data?.smiles[expiryIdx];

  // Reconstructed IV surface: resample every expiry's smile onto a shared
  // log-moneyness grid (intersection range, no extrapolation) → 3D σ_IV mesh
  // (the chosen x-axis mode is applied per-row inside SurfaceMesh).
  const ivSurface = useMemo(() => (data ? buildIvSurface(data.smiles) : null), [data]);

  // Nodal LV surface as a 3D mesh in LOCAL VARIANCE σ²_loc (the quantity the
  // pricing PDE actually consumes): rows = vertex maturities t, columns =
  // vertex strikes x = K/F. Same renderer as the IV surface.
  const lvMesh = useMemo<SurfaceMeshData | null>(() => {
    if (!data || data.tNodes.length < 2 || data.xNodes.length < 2) return null;
    return {
      expiries: data.tNodes.map((t) => t.toFixed(2)),
      t: data.tNodes,
      k: data.xNodes,
      vol: data.localVol.map((row) => row.map((v) => v * v)),
    };
  }, [data]);

  // Display-x transform for the 3D LV mesh (grid x = K/F, per t-row). Strike
  // interpolates ln F(t) across the expiry ladder (flat-extrapolated); the
  // brush and heatmap stay in x. Memoized so SurfaceMesh's mesh memo is stable.
  const lvXTransform = useMemo<((x: number, row: number) => number) | undefined>(() => {
    if (lvAxis === "moneyness" || !data) return undefined;
    if (lvAxis === "logmoneyness") return (x) => Math.log(x);
    const fwd = data.smiles
      .filter((s) => (s.forward ?? 0) > 0)
      .map((s) => ({ t: s.t, lf: Math.log(s.forward as number) }));
    if (fwd.length === 0) return undefined; // no forwards: fall back to x
    const { tNodes } = data;
    const fAt = (t: number): number => {
      if (t <= fwd[0].t) return Math.exp(fwd[0].lf);
      const last = fwd[fwd.length - 1];
      if (t >= last.t) return Math.exp(last.lf);
      for (let i = 1; i < fwd.length; i++) {
        if (t <= fwd[i].t) {
          const a = fwd[i - 1];
          const f = (t - a.t) / (fwd[i].t - a.t);
          return Math.exp(a.lf + f * (fwd[i].lf - a.lf));
        }
      }
      return Math.exp(last.lf);
    };
    const rowF = tNodes.map(fAt);
    return (x, row) => x * (rowF[row] ?? 1);
  }, [lvAxis, data]);

  /** Corner-label formatter matching the chosen LV x-axis scale (falls back to
   *  x when the strike transform is unavailable, mirroring lvXTransform). */
  const lvFormatX = (v: number): string => {
    if (lvXTransform === undefined) return `x ${v.toFixed(2)}`;
    if (lvAxis === "strike") return `K ${v >= 100 ? v.toFixed(0) : v.toFixed(2)}`;
    return `k ${v.toFixed(2)}`;
  };

  // Stacked IV: every reconstructed expiry's total variance w(k) = σ(k)²·τ on
  // shared axes (mirrors the Parametric workspace). σ is quoted in the event-
  // variance clock τ, so this is the price total variance — non-crossing across
  // expiries ⟺ no calendar arbitrage in the local-vol surface. Each expiry
  // re-coordinates k by its own forward / smile for the chosen axis mode.
  const stackedIv = useMemo<OverlaySeries[] | null>(() => {
    if (!data || data.smiles.length === 0) return null;
    const n = data.smiles.length;
    return data.smiles.map((s, i) => {
      const tau = s.tau && s.tau > 0 ? s.tau : s.t;
      const ctx = smileAxisContext(s);
      // Prefer the untruncated modelExt (shared display grid, V3.3 item 3) so
      // short expiries are no longer stubs — same pattern as densityExt below.
      const pts = s.modelExt && s.modelExt.length > 1 ? s.modelExt : s.model;
      return {
        label: formatExpiry(s.expiry, s.t, format),
        xs: pts.map((p) =>
          axisMode === "logmoneyness" ? p.k : axisTransform(axisMode, p.k, ctx),
        ),
        ys: pts.map((p) => p.vol * p.vol * tau),
        color: maturityColor(n > 1 ? i / (n - 1) : 0),
      };
    });
  }, [data, format, axisMode]);

  // Worst calendar crossing on the PDE lattice (V3.3 item 10): a circle at
  // (k*, curve midpoint) on the stacked-IV axes; empty when arb-free.
  const lvCalMarkers = useMemo<OverlayMarker[]>(() => {
    if (!data) return [];
    const m = lvCalendarMarker(data.smiles, data.calendarWorstPair, data.calendarWorstK);
    if (m === null) return [];
    const far = data.smiles[(data.calendarWorstPair ?? 0) + 1];
    const x =
      axisMode === "logmoneyness" || !far
        ? m.k
        : axisTransform(axisMode, m.k, smileAxisContext(far));
    return [{ x, y: m.y, label: m.label }];
  }, [data, axisMode]);

  // Densities: every reconstructed expiry's risk-neutral pdf (Breeden-
  // Litzenberger, carried on each smile) overlaid on shared axes — mirrors the
  // Parametric "Densities" view. All curves staying ≥ 0 ⟺ no butterfly arbitrage.
  const stackedDensities = useMemo<OverlaySeries[] | null>(() => {
    if (!data || data.smiles.length === 0) return null;
    const n = data.smiles.length;
    // Prefer the left-extended density (reaches k_min = -1.4) over the
    // central-mass PDE density, so the overlay spans the full smile range.
    const series = data.smiles
      .map((s, i) => ({ d: s.densityExt ?? s.density, s, i }))
      .filter(({ d }) => d && d.x.length > 0)
      .map(({ d, s, i }) => {
        const ctx = smileAxisContext(s);
        return {
          label: formatExpiry(s.expiry, s.t, format),
          xs: d!.x.map((k) => (axisMode === "logmoneyness" ? k : axisTransform(axisMode, k, ctx))),
          ys: d!.density,
          color: maturityColor(n > 1 ? i / (n - 1) : 0),
        };
      });
    return series.length > 0 ? series : null;
  }, [data, format, axisMode]);

  // Offline card AFTER every hook: an early return between hooks changes the
  // hook count when the session flips live→mock after mount (React #300 — the
  // UI smoke caught exactly this on the offline Local Vol tab).
  if (error !== null && data === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className={`${cardClass} max-w-sm p-8 text-center`}>
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

  /** Chart-card body for the active sub-tab. */
  const chartBody = () => {
    if (loading || data === null) return chartMessage("Calibrating local-vol surface…");
    if (data.hasFit === false)
      return chartMessage("No local-vol surface yet — press Calibrate.");
    switch (view) {
      case "lvsurface":
        return lvRender === "mesh" && lvMesh
          ? (
            <SurfaceMesh
              data={lvMesh}
              legendLabel="σ²_loc(x, t)"
              formatValue={(v) => Number(v.toPrecision(3)).toString()}
              formatX={lvFormatX}
              countCaption={`${data.tNodes.length}×${data.xNodes.length} vertices`}
              rowXTransform={lvXTransform}
              triangulate
              cellDiagMain={data.cellDiagMain}
            />
          )
          : <LocalVolHeatmap tNodes={data.tNodes} xNodes={data.xNodes} localVol={data.localVol} />;
      case "ivsurface":
        return ivSurface
          ? <SurfaceMesh data={ivSurface} legendLabel="σ_IV(k, T)" axisMode={axisMode} />
          : chartMessage("IV surface needs at least two overlapping expiries.");
      case "stackedvar":
        return stackedIv
          ? (
            <OverlayCurvesChart
              series={stackedIv}
              xLabel={axisMode === "logmoneyness" ? "k = log(K / F)" : axisModeLabel(axisMode)}
              yLabel="total variance w = σ²·τ"
              zeroBaseline
              zoomY
              formatX={(v) => axisTickLabel(axisMode, v)}
              markers={lvCalMarkers}
            />
          )
          : chartMessage("Stacked IV needs at least one fitted expiry.");
      case "smile":
        return smile ? <LocalVolSmile smile={smile} axisMode={axisMode} /> : chartMessage("No smile");
      case "densities":
        return stackedDensities
          ? (
            <OverlayCurvesChart
              series={stackedDensities}
              xLabel={axisMode === "logmoneyness" ? "x = log(Sₜ / F)" : axisModeLabel(axisMode)}
              yLabel="density"
              zeroBaseline
              formatX={(v) => axisTickLabel(axisMode, v)}
            />
          )
          : chartMessage("Densities need at least one fitted expiry.");
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
                // Only ladder expiries the LV fit carries can be selected.
                if (data.smiles.some((s) => s.expiry === e)) selectExpiry(e);
              }}
            />
          )
          : chartMessage(term.error ?? "Loading term structure…");
      case "table":
        return table.data ? <LocalVolTable data={table.data} /> : chartMessage(table.error ?? "Loading table…");
    }
  };

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      {/* Header: sub-tabs · view controls · source toggle, status badges
          right-aligned. The node identity is in the workbench tab strip. */}
      <LocalVolToolbar
        view={view}
        onViewChange={setView}
        axisMode={axisMode}
        onAxisModeChange={setAxisMode}
        lvRender={lvRender}
        onLvRenderChange={setLvRender}
        lvAxis={lvAxis}
        onLvAxisChange={setLvAxis}
        axisClock={axisClock}
        onAxisClockChange={setAxisClock}
        graphSource={graphSource}
        onGraphSourceChange={setGraphSource}
        data={data}
        calendarWorstLabel={lvCalMarkers[0]?.label}
      />

      {/* Body: chart card + diagnostics aside (aside follows the shell's layout toggle) */}
      <div className="flex min-h-0 flex-1 gap-3">
        <div className={`${cardClass} flex min-w-0 flex-1 flex-col p-4`}>
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {ticker !== "" ? `${ticker} local vol` : "Local vol"}
              {PER_EXPIRY[view] && smile ? ` · ${formatExpiry(smile.expiry, smile.t, format)}` : ""}
            </h2>
            {smile && PER_EXPIRY[view] && (
              <span className="font-mono text-[11px] text-slate-500">
                arbitrage-free · max err {fmtBp0(smile.maxIvErrorBp)} bp
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

        {(wb === null || wb.layout.aside) && (
          <LocalVolAside
            ticker={ticker}
            data={data}
            smile={smile}
            expiryIdx={expiryIdx}
            onSelectExpiry={selectExpiry}
            live={live}
            varSwapEnabled={varSwapEnabled}
            applyVarSwap={applyVarSwap}
            undoVarSwap={undoVarSwap}
            redoVarSwap={redoVarSwap}
          />
        )}
      </div>
    </div>
  );
}
