// Local Vol workspace: direct piecewise-affine local-variance surface fit.
//
// Calibrates the local-vol surface straight to the ticker's option quotes
// (POST /fit/affine/{ticker}) and presents Parametric-style sub-tabs, every
// view DERIVED from that calibrated surface (ROADMAP Phase 10):
//   Smile      reconstructed arbitrage-free smile vs quotes (per expiry)
//   Densities  every expiry's B-L density overlaid (≥ 0 ⇔ no butterfly arb)
//   Term       ATM / var-swap term structure across the ladder
//   LV surface the nodal local-vol grid — 3D local-variance mesh or heatmap
//   IV surface reconstructed implied-vol mesh over t × strike
//   Stacked IV total variance w=σ²·τ per expiry (non-crossing ⇔ no calendar arb)
//   Table      per-strike reconstructed IVs + prices (per expiry)
// Densities / Stacked IV / IV surface are built client-side from the cached
// fit; Term / Table reuse it through sibling endpoints (useAffineView). Live
// backend only (no mock fallback).
//
// UI SHELL v2: the lens follows the workbench's active node tab (ticker from
// the shared session via useAffine; per-expiry views show the SESSION expiry,
// index fallback 0); an expiry pick made here (Term click, table row) goes
// through selectExpiry() → preview tab (local override off-shell). Wave 2
// grammar: LocalVolToolbar (NODE / TICKER view switch, render / clock /
// graph-source controls, badges); chart-card FOOTER (hint + the strike-axis
// unit selector: AxisModeSelect, or AxisUnitSelect for the 3D LV mesh);
// LocalVolAside (Spot move · Variance swap · Fit diagnostics). View state goes
// through useLensViewMemory (per tab with Layout ▸ "Remember view per tab").
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
import LocalVolToolbar, {
  AXIS_MODE_VIEWS, LV_AXIS_OPTIONS, PER_EXPIRY, fmtBp0,
} from "../components/localvol/LocalVolToolbar";
import type { LvAxis, LvRender, LvView } from "../components/localvol/LocalVolToolbar";
import LocalVolAside from "../components/localvol/LocalVolAside";
import { lvMeshFormatX, lvMeshXTransform } from "../components/localvol/lvMeshAxis";
import AxisModeSelect, { AxisUnitSelect } from "../components/charts/AxisModeSelect";
import { lvCalendarMarker } from "../lib/stackedVariance";
import { useSmileSession } from "../state/smileSession";
import { useOptionalWorkbench } from "../state/workbench";
import { useNodeScope } from "../state/nodeScope";
import { useLensViewMemory } from "../state/useLensViewMemory";
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

const chartMessage = (text: string) => <div className={chartMessageClass}>{text}</div>;

export default function LocalVolViewer() {
  const {
    data, loading, refreshing, error, reload, ticker,
    varSwapEnabled, varSwapNonce, graphSource, setGraphSource,
    applyVarSwap, undoVarSwap, redoVarSwap,
  } = useAffine();

  const { source, spotVersion, fitMode, expiry: sessionExpiry } = useSmileSession();
  // Null outside the shell (tests / legacy mounts): fall back to local state.
  const wb = useOptionalWorkbench();
  const scope = useNodeScope(); // split editors hide the aside (wave 3, C3)
  const live = source === "live";
  // Spot moves transport the cached surface: fold them (+ varSwapNonce) into
  // one reloadKey so density / term / table refetch alongside the surface.
  const lvReloadKey = varSwapNonce + spotVersion;
  const { format } = useExpiryFormat();
  // View state: sub-view · strike-axis mode · LV-surface render (3D mesh or
  // heatmap) · x-axis scale of the 3D LV mesh · maturity clock (Term sub-tab).
  const [vs, patchView] = useLensViewMemory<{
    view: LvView; axisMode: AxisMode; lvRender: LvRender; lvAxis: LvAxis; axisClock: ClockMode;
  }>("localvol", { view: "smile", axisMode: "logmoneyness", lvRender: "mesh", lvAxis: "moneyness", axisClock: "real" });
  const { view, axisMode, lvRender, lvAxis, axisClock } = vs;
  const setView = (view: LvView) => patchView({ view });
  const setAxisMode = (axisMode: AxisMode) => patchView({ axisMode });
  const setLvRender = (lvRender: LvRender) => patchView({ lvRender });
  const setLvAxis = (lvAxis: LvAxis) => patchView({ lvAxis });
  const setAxisClock = (axisClock: ClockMode) => patchView({ axisClock });
  // Shared per-ticker event calendar (edited in Parametric Term) for LV's Term.
  const events = useEvents(ticker);

  // Selected expiry for the per-expiry views = the session's (the active tab);
  // a local override stands in off-shell. Index falls back to 0 (not in the
  // LV ladder, or before the fit lands).
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

  // Reconstructed IV surface: every expiry's smile resampled onto a shared
  // log-moneyness grid (intersection range, no extrapolation) → 3D σ_IV mesh.
  const ivSurface = useMemo(() => (data ? buildIvSurface(data.smiles) : null), [data]);

  // Nodal LV surface as a 3D mesh in LOCAL VARIANCE σ²_loc (what the pricing
  // PDE consumes): rows = vertex maturities t, columns = vertex strikes x = K/F.
  const lvMesh = useMemo<SurfaceMeshData | null>(() => {
    if (!data || data.tNodes.length < 2 || data.xNodes.length < 2) return null;
    return {
      expiries: data.tNodes.map((t) => t.toFixed(2)),
      t: data.tNodes,
      k: data.xNodes,
      vol: data.localVol.map((row) => row.map((v) => v * v)),
    };
  }, [data]);

  // Display-x transform + corner-label formatter for the 3D LV mesh (grid
  // x = K/F, per t-row; localvol/lvMeshAxis). Memoized for SurfaceMesh's memo.
  const lvXTransform = useMemo(() => lvMeshXTransform(lvAxis, data), [lvAxis, data]);
  const lvFormatX = lvMeshFormatX(lvAxis, lvXTransform !== undefined);

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
        t: s.t,
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
          t: s.t,
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

  // Footer hint: the 2-D zoomable charts (smile / overlays) share one
  // wheel-drag-double-click grammar; Term is click-to-select; the heatmap and
  // the table are static; SurfaceMesh prints its own hint in its top bar, so
  // the two mesh views get none here (no doubled hint).
  const interactionHint =
    view === "smile" || view === "densities" || view === "stackedvar"
      ? "scroll: zoom · drag: pan · dbl-click: reset"
      : view === "term"
        ? "click a point: select that expiry"
        : "";

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
              cameraKey="localvol:lv"
              ticker={ticker}
              chartId="localvol:lv"
              linkK={Math.log}
              formatExpiry={() => ""}
            />
          )
          : <LocalVolHeatmap tNodes={data.tNodes} xNodes={data.xNodes} localVol={data.localVol} ticker={ticker} />;
      case "ivsurface":
        return ivSurface
          ? (
            <SurfaceMesh data={ivSurface} legendLabel="σ_IV(k, T)" axisMode={axisMode}
              cameraKey="localvol:iv" ticker={ticker} chartId="localvol:iv"
              formatExpiry={(iso, t) => formatExpiry(iso, t, format)} />
          )
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
              link={axisMode === "logmoneyness" ? { ticker, chartId: "localvol:stackedvar" } : undefined}
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
              link={axisMode === "logmoneyness" ? { ticker, chartId: "localvol:densities" } : undefined}
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
        lvRender={lvRender}
        onLvRenderChange={setLvRender}
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
            data-chart-card=""
            className={[
              "min-h-0 flex-1 transition-opacity duration-200",
              refreshing ? "opacity-60" : "opacity-100",
            ].join(" ")}
          >
            {chartBody()}
          </div>

          {/* Footer: interaction hint · strike-axis unit selector next to the
              x-axis it changes (AxisModeSelect for the smile-family views, the
              grid-native AxisUnitSelect for the 3D LV mesh). */}
          <div className="mt-1 flex shrink-0 items-center gap-3 text-[10px] text-slate-600">
            <span>{interactionHint}</span>
            {AXIS_MODE_VIEWS.has(view) && (
              <span className="ml-auto">
                <AxisModeSelect value={axisMode} onChange={setAxisMode} />
              </span>
            )}
            {view === "lvsurface" && lvRender === "mesh" && (
              <span className="ml-auto">
                <AxisUnitSelect
                  value={lvAxis}
                  options={LV_AXIS_OPTIONS}
                  onChange={setLvAxis}
                  title="Strike-axis display scale"
                />
              </span>
            )}
          </div>
        </div>

        {(wb === null || wb.layout.aside) && !(scope?.split ?? false) && (
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
