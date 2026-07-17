// Presentational 3D surface (k × T × value) — pure SVG, no chart deps.
//
// Renders a (k, sqrt(T), value) mesh through an orthographic projection with
// free yaw rotation (drag) at a fixed pitch; cells are painter-sorted back to
// front and shaded with a blue→cyan→amber→red colormap (optionally split into
// their two triangular facets — see `triangulate`). Extracted from
// SurfaceChart so both the Parametric vol surface (fetched) and the Local Vol
// reconstructed-IV surface (built client-side) share one renderer.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { clamp, formatPct } from "../lib/chartScale";
import { timeAxisValue } from "../lib/timeAxis";
import type { TimeAxisMode } from "../lib/timeAxis";
import { axisTickLabel, axisTransform, makeVolAt } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";
import RangeBrush from "./RangeBrush";

/** Mesh data: one vol row per expiry over a shared log-moneyness grid k.
 *  ``forward`` / ``atmVol`` (per expiry) are optional context the strike / %ATM /
 *  Δ / normalized x-axis modes need; absent ⇒ only the log-moneyness axis. */
export interface SurfaceMeshData {
  expiries: string[];
  t: number[];
  k: number[];
  vol: number[][];
  forward?: number[];
  atmVol?: number[];
}

/** Camera elevation above the k-T plane (pitch fixed ≈60° from vertical). */
const ELEV = (30 * Math.PI) / 180;
const SIN_E = Math.sin(ELEV);
const COS_E = Math.cos(ELEV);
/** Height of the value axis in normalized scene units (x, y span [-1, 1]). */
const Z_HEIGHT = 0.85;
/** Cap on rendered mesh columns: dense k grids are strided down to this. */
const MAX_COLS = 48;

/** Colormap stops: blue → cyan → amber → red over the value range. */
const STOPS: { u: number; rgb: [number, number, number] }[] = [
  { u: 0, rgb: [59, 130, 246] },
  { u: 0.34, rgb: [34, 211, 238] },
  { u: 0.67, rgb: [251, 191, 36] },
  { u: 1, rgb: [239, 68, 68] },
];

/** Piecewise-linear colormap lookup, u in [0, 1]. */
function valColor(u: number): string {
  const x = Math.min(1, Math.max(0, u));
  for (let i = 1; i < STOPS.length; i++) {
    if (x <= STOPS[i].u) {
      const a = STOPS[i - 1];
      const b = STOPS[i];
      const f = (x - a.u) / (b.u - a.u);
      const c = a.rgb.map((v, j) => Math.round(v + f * (b.rgb[j] - v)));
      return `rgb(${c[0]} ${c[1]} ${c[2]})`;
    }
  }
  return "rgb(239 68 68)";
}

/** Track the pixel size of a container element. */
function useElementSize() {
  const ref = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const rect = entries[0]?.contentRect;
      if (rect) setSize({ width: rect.width, height: rect.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return { ref, size };
}

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

interface SurfaceMeshProps {
  data: SurfaceMeshData;
  /** Legend caption, e.g. "σ(k, T)" or "σ_IV(k, T)". */
  legendLabel?: string;
  /** Strike-axis display mode (shared with the Smile view). The brushed window
   *  still selects columns in log-moneyness; only the displayed x changes. */
  axisMode?: AxisMode;
  /** Legend value formatter (default percent — right for vols; the local-
   *  variance surface passes a plain-number formatter). */
  formatValue?: (v: number) => string;
  /** Corner x-axis label formatter (default the axis-mode tick label). */
  formatX?: (v: number) => string;
  /** Grid-size caption (default "N expiries · M strikes"). */
  countCaption?: string;
  /** Per-row display-x override: maps a grid x (data.k, row index) straight to
   *  the display coordinate, bypassing the axis-mode machinery — for grids not
   *  in log-moneyness (the LV nodal surface is in x = K/F). Memoize at the call
   *  site; the brush still windows in data.k units. */
  rowXTransform?: (x: number, row: number) => number;
  /** Paint each cell as its TWO triangular facets (the true piecewise-affine
   *  geometry of a nodal grid — the LV surface) instead of one quad (default,
   *  the smoother look the IV surfaces keep). */
  triangulate?: boolean;
  /** With `triangulate`: the model's own per-cell diagonal orientation
   *  (true = split along (i,j)→(i+1,j+1)), indexed by ORIGINAL grid cell
   *  [tRow][kCol] — the qhull triangulation the pricing basis uses (Note 04).
   *  Absent, or where brushing makes mesh columns non-adjacent, cells fall
   *  back to the main diagonal. */
  cellDiagMain?: boolean[][];
}

export default function SurfaceMesh({
  data,
  legendLabel = "σ(k, T)",
  axisMode = "logmoneyness",
  formatValue,
  formatX,
  countCaption,
  rowXTransform,
  triangulate = false,
  cellDiagMain,
}: SurfaceMeshProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  /** Yaw around the vertical (value) axis, radians; drag to rotate. */
  const [yaw, setYaw] = useState(-0.55);
  /** Scene zoom factor (scroll to zoom the projected surface). */
  const [zoomF, setZoomF] = useState(1);
  /** Maturity-axis scaling: √T (default, the natural diffusive scale) or T. */
  const [timeMode, setTimeMode] = useState<TimeAxisMode>("sqrt");
  /** Coarse strike (k) window; null = full extent. */
  const [kWindow, setKWindow] = useState<[number, number] | null>(null);
  const drag = useRef<{ startX: number; startYaw: number } | null>(null);

  // Wheel zoom (native, non-passive so preventDefault works).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      setZoomF((f) => clamp(f * (e.deltaY < 0 ? 1.1 : 1 / 1.1), 0.3, 6));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, []);

  const fullK: [number, number] = data.k.length
    ? [data.k[0], data.k[data.k.length - 1]]
    : [-1, 1];
  const [kLo, kHi] = kWindow ?? fullK;

  // Normalize the grid into scene coordinates: x = the display coordinate (the
  // chosen axis mode) within the brushed window in [-1, 1], y = T or √T in
  // [-1, 1], z = value in [0, Z_HEIGHT]. The window still selects COLUMNS in
  // log-moneyness; each expiry's display-x is its own monotone transform of k
  // (forward / ATM vol differ per expiry), so e.g. strike shears the sheet.
  const mesh = useMemo(() => {
    const { k, t, vol, forward, atmVol } = data;
    if (k.length < 2 || t.length < 2 || vol.length !== t.length) return null;
    // Columns inside the brushed k-window, strided down for rendering.
    const inWin: number[] = [];
    for (let j = 0; j < k.length; j++) if (k[j] >= kLo && k[j] <= kHi) inWin.push(j);
    if (inWin.length < 2) return null;
    const stride = Math.max(1, Math.ceil(inWin.length / MAX_COLS));
    const cols: number[] = [];
    for (let c = 0; c < inWin.length; c += stride) cols.push(inWin[c]);
    if (cols[cols.length - 1] !== inWin[inWin.length - 1]) cols.push(inWin[inWin.length - 1]);
    const kRange: readonly [number, number] = [k[0], k[k.length - 1]];

    // Per-row display-x for each windowed column. An explicit rowXTransform
    // wins; else log-moneyness (or missing forward context) keeps the shared
    // k, and any other axis mode transforms per expiry.
    const useTransform = axisMode !== "logmoneyness" && forward !== undefined;
    const rowsX: number[][] = t.map((ti, i) => {
      if (rowXTransform) return cols.map((j) => rowXTransform(k[j], i));
      if (!useTransform) return cols.map((j) => k[j]);
      const volAt = makeVolAt(k.map((kk, idx) => ({ k: kk, vol: vol[i][idx] })));
      const ctx = {
        forward: forward[i],
        t: ti,
        atmVol: atmVol?.[i] ?? volAt(0) ?? 0,
        volAt,
        kRange,
      };
      return cols.map((j) => axisTransform(axisMode, k[j], ctx));
    });
    // Global display-domain across every visible vertex (curves can span
    // different ranges per expiry, e.g. strike).
    let dMin = Infinity;
    let dMax = -Infinity;
    for (const row of rowsX)
      for (const x of row) { if (Number.isFinite(x)) { dMin = Math.min(dMin, x); dMax = Math.max(dMax, x); } }
    const dSpan = dMax - dMin || 1;
    const sval = (tt: number) => timeAxisValue(tt, timeMode);
    const sMin = sval(t[0]);
    const sMax = sval(t[t.length - 1]);
    // Colour scale adapts to the visible (windowed) cells.
    let vMin = Infinity;
    let vMax = -Infinity;
    for (let i = 0; i < t.length; i++)
      for (const j of cols) { vMin = Math.min(vMin, vol[i][j]); vMax = Math.max(vMax, vol[i][j]); }
    const vSpan = vMax - vMin || 1;
    const rows = t.map((ti, i) =>
      cols.map((j, c) => ({
        x: (2 * (rowsX[i][c] - dMin)) / dSpan - 1,
        y: sMax > sMin ? (2 * (sval(ti) - sMin)) / (sMax - sMin) - 1 : 0,
        z: ((vol[i][j] - vMin) / vSpan) * Z_HEIGHT,
        vol: vol[i][j],
      })),
    );
    return { rows, cols, vMin, vMax, xMin: dMin, xMax: dMax, tMin: t[0], tMax: t[t.length - 1] };
  }, [data, kLo, kHi, timeMode, axisMode, rowXTransform]);

  const scene = useMemo(() => {
    const plotW = size.width;
    const plotH = size.height;
    if (mesh === null || plotW <= 0 || plotH <= 0) return null;
    const ca = Math.cos(yaw);
    const sa = Math.sin(yaw);
    const project = (p: { x: number; y: number; z: number }) => {
      const x1 = p.x * ca - p.y * sa;
      const y1 = p.x * sa + p.y * ca;
      return { sx: x1, sy: -(y1 * SIN_E + p.z * COS_E), depth: y1 * COS_E - p.z * SIN_E };
    };
    const pts = mesh.rows.map((row) => row.map(project));
    const corners = [
      { x: -1, y: -1, z: 0 },
      { x: 1, y: -1, z: 0 },
      { x: 1, y: 1, z: 0 },
      { x: -1, y: 1, z: 0 },
    ].map(project);
    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    for (const row of pts)
      for (const p of row) {
        xMin = Math.min(xMin, p.sx); xMax = Math.max(xMax, p.sx);
        yMin = Math.min(yMin, p.sy); yMax = Math.max(yMax, p.sy);
      }
    for (const c of corners) {
      xMin = Math.min(xMin, c.sx); xMax = Math.max(xMax, c.sx);
      yMin = Math.min(yMin, c.sy); yMax = Math.max(yMax, c.sy);
    }
    const scale = 0.88 * zoomF * Math.min(plotW / (xMax - xMin || 1), plotH / (yMax - yMin || 1));
    const ox = plotW / 2 - (scale * (xMin + xMax)) / 2;
    const oy = plotH / 2 - (scale * (yMin + yMax)) / 2;
    const X = (p: { sx: number }) => ox + p.sx * scale;
    const Y = (p: { sy: number }) => oy + p.sy * scale;

    const vSpan = mesh.vMax - mesh.vMin || 1;
    // One facet per cell (quad), or — when triangulated — the cell's TWO
    // triangular facets, split along the diagonal the MODEL's own (qhull)
    // triangulation chose for that cell when `cellDiagMain` is provided
    // (falling back to the (i,j) → (i+1,j+1) diagonal otherwise, or when
    // brushing leaves mesh columns non-adjacent), each with its own colour
    // and paint depth.
    const quads: { d: string; depth: number; color: string }[] = [];
    const pushFacet = (
      cs: { sx: number; sy: number; depth: number }[],
      vols: number[],
    ) => {
      const vAvg = vols.reduce((a, v) => a + v, 0) / vols.length;
      quads.push({
        d: `M${cs.map((p) => `${X(p).toFixed(1)},${Y(p).toFixed(1)}`).join("L")}Z`,
        depth: cs.reduce((a, p) => a + p.depth, 0) / cs.length,
        color: valColor((vAvg - mesh.vMin) / vSpan),
      });
    };
    for (let i = 0; i < pts.length - 1; i++) {
      for (let j = 0; j < pts[i].length - 1; j++) {
        const [p00, p01, p11, p10] = [pts[i][j], pts[i][j + 1], pts[i + 1][j + 1], pts[i + 1][j]];
        const [v00, v01, v11, v10] = [
          mesh.rows[i][j].vol, mesh.rows[i][j + 1].vol,
          mesh.rows[i + 1][j + 1].vol, mesh.rows[i + 1][j].vol,
        ];
        if (triangulate) {
          const j0 = mesh.cols[j];
          const mainDiag =
            cellDiagMain === undefined || mesh.cols[j + 1] !== j0 + 1
              ? true
              : (cellDiagMain[i]?.[j0] ?? true);
          if (mainDiag) {
            pushFacet([p00, p01, p11], [v00, v01, v11]);
            pushFacet([p00, p11, p10], [v00, v11, v10]);
          } else {
            pushFacet([p00, p01, p10], [v00, v01, v10]);
            pushFacet([p01, p11, p10], [v01, v11, v10]);
          }
        } else {
          pushFacet([p00, p01, p11, p10], [v00, v01, v11, v10]);
        }
      }
    }
    quads.sort((a, b) => b.depth - a.depth);

    const frame = corners.map((c) => `${X(c).toFixed(1)},${Y(c).toFixed(1)}`).join(" ");
    // Corner pixel anchors; label text is built at render time so custom
    // formatters don't have to be memo dependencies.
    const anchors = corners.map((c) => ({ x: X(c), y: Y(c) }));
    return { quads, frame, anchors };
  }, [mesh, yaw, size, zoomF, triangulate, cellDiagMain]);

  const fmtV = formatValue ?? formatPct;
  const fmtX = formatX ?? ((v: number) => axisTickLabel(axisMode, v));
  const labels =
    mesh !== null && scene !== null
      ? [
          { x: scene.anchors[0].x, y: scene.anchors[0].y + 14, text: fmtX(mesh.xMin) },
          { x: scene.anchors[1].x, y: scene.anchors[1].y + 14, text: fmtX(mesh.xMax) },
          { x: scene.anchors[0].x, y: scene.anchors[0].y + 26, text: `T ${mesh.tMin.toFixed(2)}y` },
          { x: scene.anchors[3].x, y: scene.anchors[3].y + 14, text: `T ${mesh.tMax.toFixed(2)}y` },
        ]
      : [];

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { startX: e.clientX, startYaw: yaw };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (drag.current === null) return;
    setYaw(drag.current.startYaw + (e.clientX - drag.current.startX) * 0.01);
  };
  const onPointerUp = () => {
    drag.current = null;
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend: colormap + grid info */}
      <div className="mb-1 flex shrink-0 items-center gap-3 px-1 text-[11px] text-slate-400">
        <span className="font-mono text-slate-500">{legendLabel}</span>
        {mesh !== null && (
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
            {fmtV(mesh.vMin)}
            <span
              className="h-2 w-24 rounded"
              style={{
                background:
                  "linear-gradient(90deg, rgb(59 130 246), rgb(34 211 238), rgb(251 191 36), rgb(239 68 68))",
              }}
            />
            {fmtV(mesh.vMax)}
          </span>
        )}
        <span className="text-[10px] text-slate-500">
          {countCaption ?? `${data.expiries.length} expiries · ${data.k.length} strikes`}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {/* Maturity-axis scaling toggle */}
          <div className="flex overflow-hidden rounded border border-slate-700">
            {(["linear", "sqrt"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setTimeMode(m)}
                title={m === "sqrt" ? "√T axis" : "Linear T axis"}
                className={[
                  "px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                  timeMode === m ? "bg-accent-600/25 text-accent-400" : "text-slate-400 hover:text-slate-200",
                ].join(" ")}
              >
                {m === "sqrt" ? "√T" : "T"}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-600">drag · scroll · dbl-click</span>
        </div>
      </div>

      {/* Plot area */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {mesh === null ? (
          message("Surface needs at least two expiries.")
        ) : scene === null ? null : (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className="absolute inset-0 cursor-grab active:cursor-grabbing"
            style={{ touchAction: "none" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
            onDoubleClick={() => { setZoomF(1); setYaw(-0.55); }}
          >
            <polygon points={scene.frame} fill="none" stroke="rgb(148 163 184 / 0.25)" strokeDasharray="3 4" />
            {scene.quads.map((q, i) => (
              <path key={i} d={q.d} fill={q.color} fillOpacity={0.55} stroke={q.color}
                strokeOpacity={0.9} strokeWidth={0.6} strokeLinejoin="round" />
            ))}
            {labels.map((l, i) => (
              <text key={i} x={l.x} y={l.y} textAnchor="middle" className="fill-slate-500 font-mono text-[10px]">
                {l.text}
              </text>
            ))}
          </svg>
        )}
      </div>

      {/* Coarse strike (k) window — shrink the displayed strike axis. */}
      {data.k.length > 1 && (
        <div className="mt-2 shrink-0 px-1">
          <RangeBrush
            min={fullK[0]}
            max={fullK[1]}
            value={[kLo, kHi]}
            onChange={setKWindow}
            format={(v) => v.toFixed(2)}
          />
        </div>
      )}
    </div>
  );
}
