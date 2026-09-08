// Chart-card body of the Local Vol Compare tab (LV Dupire-twin arc, D3): the
// parametric surface's Dupire twin beside the affine sheet, in both spaces.
//
//   Sheets      the two σ²_loc meshes side by side on ONE lattice (the affine
//               vertex grid), sharing a camera (rotate one, both turn) and the
//               linked crosshair; the affine panel shows a Calibrate cue when
//               no LV fit is displayed.
//   Difference  the signed sheet twin − affine (vol) as a heatmap on the
//               diverging ramp, symmetric about zero.
//   Smiles      the node's expiry on the LV smile chart — the affine
//               reconstruction (sky) with the parametric source (lime) and
//               the twin (orange, dashed) overlaid on the quotes — and the
//               per-expiry score table below it (click a row: that expiry).
//
// Cues, not crashes: the endpoint's 404 (fewer than two parametric expiries)
// reads as a "Calibrate first" card; a stale or differently gridded LV fit
// leaves the difference empty with the payload's own message. Pure
// presentation — state lives in LocalVolViewer.
import LocalVolHeatmap from "../LocalVolHeatmap";
import LocalVolSmile from "../LocalVolSmile";
import type { SmileOverlay } from "../LocalVolSmile";
import SurfaceMesh from "../SurfaceMesh";
import LvCompareTable from "./LvCompareTable";
import type { AutoScaleToggles } from "../../lib/autoScaleY";
import type { AxisMode } from "../../lib/axisModes";
import {
  AFFINE_COLOR, PARAMETRIC_COLOR, TWIN_COLOR, TWIN_DASH,
  compareSmileFor, diffSheet, formatSignedPts, sheetMesh,
} from "../../lib/lvCompare";
import type { LvCompareMode } from "../../lib/lvCompare";
import { buttonClass, cardClass, chartMessageClass } from "../../lib/ui";
import type { AffineFitResponse, AffineSmile } from "../../state/useAffine";
import type { LvCompareResponse } from "../../state/useLvCompare";

export interface LvCompareViewProps {
  ticker: string;
  compare: LvCompareResponse | null;
  loading: boolean;
  error: string | null;
  /** The displayed LV payload (its per-expiry smiles feed the smile panel). */
  affine: AffineFitResponse | null;
  mode: LvCompareMode;
  /** The node's expiry (the smile panel and the table selection follow it). */
  expiry: string | null;
  onSelectExpiry: (iso: string) => void;
  axisMode: AxisMode;
  autoScaleY: AutoScaleToggles;
  onToggleAutoScale: (key: keyof AutoScaleToggles) => void;
  formatExpiry: (iso: string, t: number) => string;
  /** Opens the Calibrate flow (the 404 cue's button); optional off-shell. */
  onCalibrate?: () => void;
}

const message = (text: string) => <div className={chartMessageClass}>{text}</div>;

/** A sheet panel's caption (mono, muted) above its chart. */
function Caption({ text, color }: { text: string; color: string }) {
  return (
    <div className="mb-1 flex shrink-0 items-center gap-1.5 px-1 font-mono text-[10px] text-slate-500">
      <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {text}
    </div>
  );
}

/** A disabled var-swap block for a synthetic base smile (no LV fit shown). */
const NO_VARSWAP: AffineSmile["varSwap"] = {
  level: null, excluded: false, modelVol: 0, enabled: false, canUndo: false, canRedo: false,
};

export default function LvCompareView({
  ticker, compare, loading, error, affine, mode, expiry, onSelectExpiry,
  axisMode, autoScaleY, onToggleAutoScale, formatExpiry, onCalibrate,
}: LvCompareViewProps) {
  if (error !== null && compare === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className={`${cardClass} max-w-md p-6 text-center`}>
          <h3 className="mb-1 text-sm font-semibold text-slate-100">The Dupire twin needs a parametric fit</h3>
          <p className="mb-3 text-xs text-slate-500">
            It is read off the calibrated parametric surface — calibrate the ticker first, then come back.
          </p>
          <p className="mb-4 truncate text-[10px] text-amber-400/80" title={error}>{error}</p>
          {onCalibrate && <button className={buttonClass} onClick={onCalibrate}>Calibrate</button>}
        </div>
      </div>
    );
  }
  if (loading || compare === null) return message("Building the Dupire twin…");

  if (mode === "sheets") {
    const twin = sheetMesh(compare, "twin");
    const aff = sheetMesh(compare, "affine");
    const caption = `${compare.tNodes.length}×${compare.xNodes.length} vertices`;
    return (
      <div className="flex h-full min-h-0 gap-3">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <Caption text={`σ²_loc Dupire twin · ${compare.tInterp} · ${caption}`} color={TWIN_COLOR} />
          {twin
            ? (
              <SurfaceMesh
                data={twin}
                legendLabel="σ²_loc twin"
                formatValue={(v) => Number(v.toPrecision(3)).toString()}
                triangulate
                cellDiagMain={affine?.cellDiagMain}
                cameraKey="localvol:compare"
                ticker={ticker}
                chartId="localvol:compare:twin"
                linkK={Math.log}
                formatExpiry={() => ""}
                compact
              />
            )
            : message("The twin needs at least two vertices in each direction.")}
        </div>
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <Caption text={`σ²_loc affine sheet (the LV fit) · ${caption}`} color={AFFINE_COLOR} />
          {aff
            ? (
              <SurfaceMesh
                data={aff}
                legendLabel="σ²_loc affine"
                formatValue={(v) => Number(v.toPrecision(3)).toString()}
                triangulate
                cellDiagMain={affine?.cellDiagMain}
                cameraKey="localvol:compare"
                ticker={ticker}
                chartId="localvol:compare:affine"
                linkK={Math.log}
                formatExpiry={() => ""}
                compact
              />
            )
            : message(
              compare.hasAffine
                ? "The displayed LV fit sits on another lattice — press Calibrate to rebuild it on this one."
                : "No local-vol surface yet — press Calibrate to draw the affine sheet beside the twin.",
            )}
        </div>
      </div>
    );
  }

  if (mode === "diff") {
    const diff = diffSheet(compare);
    if (!diff) {
      return message(
        compare.hasAffine
          ? "The displayed LV fit sits on another lattice — press Calibrate to compare on this one."
          : "The difference needs the LV fit — press Calibrate.",
      );
    }
    return (
      <LocalVolHeatmap
        tNodes={compare.tNodes}
        xNodes={compare.xNodes}
        localVol={diff}
        legendLabel="σ_loc twin − affine"
        diverging
        formatValue={(v) => formatSignedPts(v)}
        ticker={ticker}
        chartId="localvol:compare:diff"
      />
    );
  }

  // Smiles: the node's expiry with the three curves on the quotes, the table
  // below. Every curve comes from the compare payload itself — the affine
  // reconstruction at the ANCHOR spot beside the twin and its parametric
  // source — so the panel never mixes the displayed (spot-transported) LV
  // smile with an anchored twin. The base smile carries the quotes and the
  // var-swap level of the displayed payload when the spot has not moved.
  const cs = compareSmileFor(compare, expiry);
  if (cs === null) return message("No expiry to compare.");
  const hasAffineCurve = (cs.affine?.length ?? 0) > 1;
  const twinPoints = cs.twinExt && cs.twinExt.length > 1 ? cs.twinExt : cs.twin;
  const anchored = (compare.spotShift ?? 0) === 0;
  const shown = anchored && affine?.hasFit !== false ? affine?.smiles.find((s) => s.expiry === cs.expiry) : undefined;
  const smile: AffineSmile = {
    expiry: cs.expiry, t: cs.t, tau: cs.tau, forward: cs.forward,
    model: hasAffineCurve ? cs.affine! : twinPoints,
    quotes: cs.quotes,
    varSwap: shown?.varSwap ?? NO_VARSWAP,
    maxIvErrorBp: hasAffineCurve ? (shown?.maxIvErrorBp ?? 0) : cs.twinScore.maxBp,
  };
  const base = hasAffineCurve;
  const overlays: SmileOverlay[] = [
    { label: "parametric source", points: cs.parametric, color: PARAMETRIC_COLOR, width: 1.4 },
  ];
  if (base) overlays.push({ label: "Dupire twin", points: twinPoints, color: TWIN_COLOR, dash: TWIN_DASH, width: 1.6 });
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-1 flex shrink-0 flex-wrap items-center gap-3 px-1 font-mono text-[10px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ backgroundColor: base ? AFFINE_COLOR : TWIN_COLOR }} />
          {base ? "affine sheet" : "Dupire twin (no LV fit to draw)"}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4" style={{ backgroundColor: PARAMETRIC_COLOR }} />
          parametric source
        </span>
        {base && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 border-t border-dashed" style={{ borderColor: TWIN_COLOR }} />
            Dupire twin
          </span>
        )}
        <span className="ml-auto" title="Twin vs its parametric source at the quoted strikes on the converged operator (in-operator in brackets)">
          round trip {cs.roundTripBp.toFixed(1)} bp ({cs.roundTripInOpBp.toFixed(1)} in-op)
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <LocalVolSmile
          smile={smile}
          axisMode={axisMode}
          autoScaleY={autoScaleY}
          onToggleAutoScale={onToggleAutoScale}
          overlays={overlays}
        />
      </div>
      <div className="mt-2 max-h-44 shrink-0 overflow-y-auto">
        <LvCompareTable
          data={compare}
          selectedExpiry={cs.expiry}
          onSelectExpiry={onSelectExpiry}
          formatExpiry={formatExpiry}
        />
      </div>
    </div>
  );
}
