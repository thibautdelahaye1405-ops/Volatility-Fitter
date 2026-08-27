// Presentational 3D surface (k × T × value) — pure SVG, no chart deps.
//
// Renders a (k, √T | T, value) mesh through an orthographic camera
// (lib/surfaceCamera): drag = yaw · Shift+drag / middle-drag / two-finger =
// pan · Ctrl+drag = pitch (10–80°) · wheel = zoom AT THE CURSOR · dbl-click =
// reset (a ⌂ chip shows while moved). The camera persists per `cameraKey`
// (state/surfaceCameras — survives tab switches, rides workspace files).
// Cells are painter-sorted back to front and shaded with the shared vol
// colormap (optionally split into their two triangular facets, see
// `triangulate`). Shared by the Parametric vol surface (fetched) and the
// Local Vol meshes (built client-side).
//
// Crosshair (wave 3, B2): the pointer is inverse-projected onto the floor,
// snapped (with hysteresis) to the nearest grid vertex; the SMILE at T_i and
// the TERM curve at k_j are lifted onto the surface with their floor
// projections + a marker, and a badge reads `T · expiry · x · value`. The hit
// is published on the linked hover store, so every other visible chart of the
// same ticker shows the matching point (and this chart shows a muted
// crosshair when another chart publishes).
import { useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { Home } from "lucide-react";
import { formatPct } from "../lib/chartScale";
import { formatYears } from "../lib/timeAxis";
import type { TimeAxisMode } from "../lib/timeAxis";
import { axisTickLabel, formatHoverValue } from "../lib/axisModes";
import type { AxisMode } from "../lib/axisModes";
import { useElementSize } from "../lib/useElementSize";
import { VOL_GRADIENT_CSS } from "../lib/volColormap";
import { buildFacets, buildSceneMesh } from "../lib/surfaceMesh";
import type { SurfaceMeshData } from "../lib/surfaceMesh";
import {
  DEFAULT_CAMERA, fitViewport, isCameraMoved, nearestVertex, panBy, pitchBy, project,
  snapHysteresis, toPixel, unprojectFloor, yawBy, zoomAt,
} from "../lib/surfaceCamera";
import type { GridHit } from "../lib/surfaceCamera";
import { useSurfaceCamera } from "../state/surfaceCameras";
import { nearestGridPoint, useSurfaceHover } from "../state/surfaceHover";
import RangeBrush from "./RangeBrush";
import SurfaceCrosshair, { CrosshairBadge, surfaceReadout } from "./charts/SurfaceCrosshair";

export type { SurfaceMeshData } from "../lib/surfaceMesh";

const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

interface SurfaceMeshProps {
  data: SurfaceMeshData;
  /** Legend caption, e.g. "σ(k, T)" or "σ_IV(k, T)". */
  legendLabel?: string;
  /** Strike-axis display mode (shared with the Smile view). The brushed window
   *  still selects columns in the grid's k; only the displayed x changes. */
  axisMode?: AxisMode;
  /** Legend / badge value formatter (default percent — right for vols). */
  formatValue?: (v: number) => string;
  /** Corner x-axis / badge x formatter (default the axis-mode tick label). */
  formatX?: (v: number) => string;
  /** Grid-size caption (default "N expiries · M strikes"). */
  countCaption?: string;
  /** Per-row display-x override for grids not in log-moneyness (the LV nodal
   *  surface is in x = K/F). Memoize at the call site. */
  rowXTransform?: (x: number, row: number) => number;
  /** Paint each cell as its TWO triangular facets (the LV surface). */
  triangulate?: boolean;
  /** With `triangulate`: the model's per-cell diagonal orientation [tRow][kCol]. */
  cellDiagMain?: boolean[][];
  /** Persist the camera under this key (state/surfaceCameras). */
  cameraKey?: string;
  /** Linked hover: the ticker this surface belongs to + the chart id. */
  ticker?: string;
  chartId?: string;
  /** Grid column → log-moneyness (linking LV grids in x = K/F); default = k. */
  linkK?: (k: number) => number;
  /** Expiry label for the badge (default the raw expiry string). */
  formatExpiry?: (iso: string, t: number) => string;
}

export default function SurfaceMesh({
  data, legendLabel = "σ(k, T)", axisMode = "logmoneyness", formatValue, formatX, countCaption,
  rowXTransform, triangulate = false, cellDiagMain, cameraKey, ticker = "", chartId = "surface",
  linkK, formatExpiry,
}: SurfaceMeshProps) {
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [cam, setCam] = useSurfaceCamera(cameraKey);
  const [timeMode, setTimeMode] = useState<TimeAxisMode>("sqrt");
  const [kWindow, setKWindow] = useState<[number, number] | null>(null);
  const [hit, setHit] = useState<GridHit | null>(null);
  const { hover, publish } = useSurfaceHover(chartId);
  // Active pointers (two-finger pan / pinch) + the drag gesture in flight.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const drag = useRef<{ mode: "yaw" | "pan" | "pitch"; x: number; y: number; moved: boolean } | null>(null);
  const camRef = useRef(cam);
  camRef.current = cam;

  const fullK: [number, number] = data.k.length ? [data.k[0], data.k[data.k.length - 1]] : [-1, 1];
  const [kLo, kHi] = kWindow ?? fullK;

  const mesh = useMemo(
    () => buildSceneMesh(data, kLo, kHi, timeMode, axisMode, rowXTransform),
    [data, kLo, kHi, timeMode, axisMode, rowXTransform],
  );

  // Projection: bounds of the frame + every vertex, fitted with zoom / pan.
  const scene = useMemo(() => {
    if (mesh === null || size.width <= 0 || size.height <= 0) return null;
    const corners = [{ x: -1, y: -1, z: 0 }, { x: 1, y: -1, z: 0 }, { x: 1, y: 1, z: 0 }, { x: -1, y: 1, z: 0 }]
      .map((c) => project(cam, c));
    const proj = mesh.rows.map((row) => row.map((v) => project(cam, v)));
    let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
    for (const p of [...corners, ...proj.flat()]) {
      xMin = Math.min(xMin, p.sx); xMax = Math.max(xMax, p.sx); yMin = Math.min(yMin, p.sy); yMax = Math.max(yMax, p.sy);
    }
    const vp = fitViewport({ xMin, xMax, yMin, yMax }, cam, size.width, size.height);
    const pts = proj.map((row) => row.map((p) => ({ ...toPixel(vp, p), depth: p.depth })));
    const facets = buildFacets(mesh, pts, triangulate, cellDiagMain);
    const anchors = corners.map((c) => toPixel(vp, c));
    return { vp, pts, facets, frame: anchors.map((a) => `${a.x.toFixed(1)},${a.y.toFixed(1)}`).join(" "), anchors };
  }, [mesh, cam, size, triangulate, cellDiagMain]);

  // Wheel: zoom about the cursor (native, non-passive so preventDefault works).
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || scene === null) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      setCam(zoomAt(camRef.current, scene.vp, e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.1 : 1 / 1.1));
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [scene, setCam]);

  // ---- crosshair: own pointer → floor → nearest vertex (hysteresis) --------
  const floorRows = useMemo(() => mesh?.rows.map((r) => r.map((v) => ({ x: v.x, y: v.y }))) ?? [], [mesh]);
  const hoverAt = (px: number, py: number) => {
    if (mesh === null || scene === null) return;
    const f = unprojectFloor(cam, scene.vp, px, py);
    if (f === null) return;
    const next = snapHysteresis(hit, nearestVertex(floorRows, f.x, f.y), floorRows, f.x, f.y);
    if (next !== null && (hit === null || next.i !== hit.i || next.j !== hit.j)) {
      setHit(next);
      const j0 = mesh.cols[next.j];
      publish({ ticker, k: linkK ? linkK(data.k[j0]) : data.k[j0], t: data.t[next.i] });
    }
  };
  const clearHover = () => { setHit(null); publish(null); };
  // Linked hit from another chart of the same ticker (muted crosshair).
  const linkedHit = useMemo<GridHit | null>(() => {
    if (hit !== null || hover === null || hover.source === chartId || hover.ticker !== ticker || mesh === null) return null;
    const ks = mesh.cols.map((j) => (linkK ? linkK(data.k[j]) : data.k[j]));
    const g = nearestGridPoint(ks, data.t, hover.k, hover.t);
    return g === null ? null : { ...g, d2: 0 };
  }, [hit, hover, chartId, ticker, mesh, data, linkK]);
  const shown = hit ?? linkedHit;

  // ---- pointer gestures ------------------------------------------------------
  const local = (e: ReactPointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = local(e);
    pointers.current.set(e.pointerId, p);
    if (pointers.current.size > 1) { drag.current = null; return; }
    const mode = e.button === 1 || e.shiftKey ? "pan" : e.ctrlKey || e.metaKey ? "pitch" : "yaw";
    drag.current = { mode, x: p.x, y: p.y, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const p = local(e);
    if (pointers.current.size >= 2 && pointers.current.has(e.pointerId)) {
      // Two fingers: pan by the midpoint delta + pinch zoom about the midpoint.
      const ids = [...pointers.current.keys()];
      const a0 = pointers.current.get(ids[0])!, b0 = pointers.current.get(ids[1])!;
      const a1 = ids[0] === e.pointerId ? p : a0, b1 = ids[1] === e.pointerId ? p : b0;
      const mid0 = { x: (a0.x + b0.x) / 2, y: (a0.y + b0.y) / 2 }, mid1 = { x: (a1.x + b1.x) / 2, y: (a1.y + b1.y) / 2 };
      const d0 = Math.hypot(a0.x - b0.x, a0.y - b0.y) || 1, d1 = Math.hypot(a1.x - b1.x, a1.y - b1.y) || 1;
      let next = panBy(cam, mid1.x - mid0.x, mid1.y - mid0.y);
      if (scene !== null) next = zoomAt(next, scene.vp, mid1.x, mid1.y, d1 / d0);
      setCam(next);
      pointers.current.set(e.pointerId, p);
      return;
    }
    const d = drag.current;
    if (d === null) { hoverAt(p.x, p.y); return; }
    const dx = p.x - d.x, dy = p.y - d.y;
    if (!d.moved && Math.hypot(dx, dy) < 2) return;
    d.moved = true;
    if (d.mode === "yaw") setCam(yawBy(cam, dx * 0.01));
    else if (d.mode === "pan") setCam(panBy(cam, dx, dy));
    else setCam(pitchBy(cam, dy * 0.006));
    drag.current = { ...d, x: p.x, y: p.y };
    if (hit !== null) clearHover();
  };
  const onPointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    pointers.current.delete(e.pointerId);
    drag.current = null;
  };
  const onPointerLeave = (e: ReactPointerEvent<SVGSVGElement>) => { onPointerUp(e); clearHover(); };
  useEffect(() => () => publish(null), [publish]); // unmount clears our echo

  const fmtV = formatValue ?? formatPct;
  const fmtX = formatX ?? ((v: number) => axisTickLabel(axisMode, v));
  const labels = mesh !== null && scene !== null
    ? [
        { x: scene.anchors[0].x, y: scene.anchors[0].y + 14, text: fmtX(mesh.xMin) },
        { x: scene.anchors[1].x, y: scene.anchors[1].y + 14, text: fmtX(mesh.xMax) },
        { x: scene.anchors[0].x, y: scene.anchors[0].y + 26, text: `T ${mesh.tMin.toFixed(2)}y` },
        { x: scene.anchors[3].x, y: scene.anchors[3].y + 14, text: `T ${mesh.tMax.toFixed(2)}y` },
      ]
    : [];
  // Crosshair geometry + badge for the shown hit.
  const cross = shown !== null && mesh !== null && scene !== null
    ? {
        floorRow: mesh.rows[shown.i].map((v) => toPixel(scene.vp, project(cam, { x: v.x, y: v.y, z: 0 }))),
        floorCol: mesh.rows.map((r) => r[shown.j]).map((v) => toPixel(scene.vp, project(cam, { x: v.x, y: v.y, z: 0 }))),
        badge: surfaceReadout(
          `T ${formatYears(data.t[shown.i])}`,
          formatExpiry ? formatExpiry(data.expiries[shown.i] ?? "", data.t[shown.i]) : (data.expiries[shown.i] ?? null),
          (formatX ?? ((v: number) => formatHoverValue(axisMode, v)))(mesh.displayX[shown.i][shown.j]),
          fmtV(mesh.rows[shown.i][shown.j].vol),
        ),
      }
    : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend: colormap + grid info + camera controls */}
      <div className="mb-1 flex shrink-0 items-center gap-3 px-1 text-[11px] text-slate-400">
        <span className="font-mono text-slate-500">{legendLabel}</span>
        {mesh !== null && (
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
            {fmtV(mesh.vMin)}
            <span className="h-2 w-24 rounded" style={{ background: VOL_GRADIENT_CSS }} />
            {fmtV(mesh.vMax)}
          </span>
        )}
        <span className="text-[10px] text-slate-500">
          {countCaption ?? `${data.expiries.length} expiries · ${data.k.length} strikes`}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {isCameraMoved(cam) && (
            <button
              onClick={() => setCam(DEFAULT_CAMERA)}
              title="Reset the view (yaw · pitch · zoom · pan) — or double-click the chart"
              aria-label="Reset view"
              className="flex items-center gap-1 rounded border border-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300 hover:border-slate-500 hover:text-slate-100"
            >
              <Home size={11} strokeWidth={1.75} /> reset
            </button>
          )}
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
          <span className="hidden text-[10px] text-slate-600 xl:inline" title="Two-finger drag pans, pinch zooms">
            drag: rotate · shift+drag: pan · ctrl+drag: pitch · scroll: zoom · dbl-click: reset
          </span>
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
            onPointerCancel={onPointerUp}
            onPointerLeave={onPointerLeave}
            onDoubleClick={() => setCam(DEFAULT_CAMERA)}
          >
            <polygon points={scene.frame} fill="none" stroke="rgb(148 163 184 / 0.25)" strokeDasharray="3 4" />
            {scene.facets.map((q, i) => (
              <path key={i} d={q.d} fill={q.color} fillOpacity={0.55} stroke={q.color}
                strokeOpacity={0.9} strokeWidth={0.6} strokeLinejoin="round" />
            ))}
            {labels.map((l, i) => (
              <text key={i} x={l.x} y={l.y} textAnchor="middle" className="fill-slate-500 font-mono text-[10px]">
                {l.text}
              </text>
            ))}
            {shown !== null && cross !== null && (
              <SurfaceCrosshair pts={scene.pts} floorRow={cross.floorRow} floorCol={cross.floorCol}
                i={shown.i} j={shown.j} linked={hit === null} />
            )}
          </svg>
        )}
        {cross !== null && <CrosshairBadge label={cross.badge} />}
      </div>

      {/* Coarse strike (k) window — shrink the displayed strike axis. */}
      {data.k.length > 1 && (
        <div className="mt-2 shrink-0 px-1">
          <RangeBrush min={fullK[0]} max={fullK[1]} value={[kLo, kHi]} onChange={setKWindow}
            format={(v) => v.toFixed(2)} />
        </div>
      )}
    </div>
  );
}
