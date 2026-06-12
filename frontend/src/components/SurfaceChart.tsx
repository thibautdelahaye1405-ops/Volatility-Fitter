// 3D implied-volatility surface view (k × T × σ). Pure SVG, no chart deps.
//
// Fetches GET /surface/{ticker} lazily — the component only mounts while the
// Surface view is open — and renders the (k, sqrt(T), vol) mesh through a
// simple orthographic projection: free yaw rotation around the vertical axis
// (drag horizontally) at a fixed camera pitch. Cells are painter-sorted
// back-to-front and filled with a blue→cyan→amber→red vol colormap at ~55%
// opacity with a same-hue stroke, so the surface reads as a clean
// wireframe-shaded sheet. Live backend only (the parent gates mock mode).
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { api } from "../state/api";
import type { FitMode } from "../state/useSmile";
import { formatPct } from "../lib/chartScale";

/** Response of GET /surface/{ticker}. */
interface SurfaceResponse {
  ticker: string;
  expiries: string[];
  t: number[];
  k: number[];
  /** Implied-vol grid: one row per expiry over the shared k grid. */
  vol: number[][];
  atmVol: number[];
  forward: number[];
}

interface SurfaceChartProps {
  ticker: string;
  fitMode: FitMode;
}

/** Camera elevation above the k-T plane (pitch fixed ≈60° from vertical). */
const ELEV = (30 * Math.PI) / 180;
const SIN_E = Math.sin(ELEV);
const COS_E = Math.cos(ELEV);
/** Height of the vol axis in normalized scene units (x, y span [-1, 1]). */
const Z_HEIGHT = 0.85;
/** Cap on rendered mesh columns: dense k grids are strided down to this. */
const MAX_COLS = 48;

/** Colormap stops: blue → cyan → amber → red over the vol range. */
const STOPS: { u: number; rgb: [number, number, number] }[] = [
  { u: 0, rgb: [59, 130, 246] },
  { u: 0.34, rgb: [34, 211, 238] },
  { u: 0.67, rgb: [251, 191, 36] },
  { u: 1, rgb: [239, 68, 68] },
];

/** Piecewise-linear colormap lookup, u in [0, 1]. */
function volColor(u: number): string {
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

/** Track the pixel size of a container element (same as SmileChart's). */
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

/** Centered placeholder for loading / error states. */
const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function SurfaceChart({ ticker, fitMode }: SurfaceChartProps) {
  const { ref, size } = useElementSize();
  const [data, setData] = useState<SurfaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /** Yaw around the vertical (vol) axis, radians; drag to rotate. */
  const [yaw, setYaw] = useState(-0.55);
  const drag = useRef<{ startX: number; startYaw: number } | null>(null);

  // Fetch (and refetch on ticker / fit-mode change) while the view is open.
  useEffect(() => {
    if (ticker === "") return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    api
      .get<SurfaceResponse>(`/surface/${ticker}`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setData(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [ticker, fitMode]);

  // Normalize the grid into scene coordinates: x = k in [-1, 1],
  // y = sqrt(T) in [-1, 1] (natural maturity spacing), z = vol in [0, Z_HEIGHT].
  const mesh = useMemo(() => {
    if (data === null) return null;
    const { k, t, vol } = data;
    if (k.length < 2 || t.length < 2 || vol.length !== t.length) return null;
    const stride = Math.max(1, Math.ceil(k.length / MAX_COLS));
    const cols: number[] = [];
    for (let j = 0; j < k.length; j += stride) cols.push(j);
    if (cols[cols.length - 1] !== k.length - 1) cols.push(k.length - 1);
    const kMin = k[0];
    const kMax = k[k.length - 1];
    const sMin = Math.sqrt(t[0]);
    const sMax = Math.sqrt(t[t.length - 1]);
    let vMin = Infinity;
    let vMax = -Infinity;
    for (const row of vol)
      for (const v of row) { vMin = Math.min(vMin, v); vMax = Math.max(vMax, v); }
    const vSpan = vMax - vMin || 1;
    const rows = t.map((ti, i) =>
      cols.map((j) => ({
        x: kMax > kMin ? (2 * (k[j] - kMin)) / (kMax - kMin) - 1 : 0,
        y: sMax > sMin ? (2 * (Math.sqrt(ti) - sMin)) / (sMax - sMin) - 1 : 0,
        z: ((vol[i][j] - vMin) / vSpan) * Z_HEIGHT,
        vol: vol[i][j],
      })),
    );
    return { rows, vMin, vMax, kMin, kMax, tMin: t[0], tMax: t[t.length - 1] };
  }, [data]);

  // Project the mesh: yaw rotation in the (x, y) plane, then orthographic
  // tilt. screenY = -(y'·sinE + z·cosE); depth = y'·cosE - z·sinE, so larger
  // depth means farther from the camera (painter sort draws those first).
  const scene = useMemo(() => {
    const plotW = size.width;
    const plotH = size.height;
    if (mesh === null || plotW <= 0 || plotH <= 0) return null;
    const ca = Math.cos(yaw);
    const sa = Math.sin(yaw);
    const project = (p: { x: number; y: number; z: number }) => {
      const x1 = p.x * ca - p.y * sa;
      const y1 = p.x * sa + p.y * ca;
      return {
        sx: x1,
        sy: -(y1 * SIN_E + p.z * COS_E),
        depth: y1 * COS_E - p.z * SIN_E,
      };
    };
    const pts = mesh.rows.map((row) => row.map(project));
    // Base-plane corners (z = 0): frame outline + axis label anchors.
    const corners = [
      { x: -1, y: -1, z: 0 }, // k min, T min
      { x: 1, y: -1, z: 0 }, //  k max, T min
      { x: 1, y: 1, z: 0 }, //   k max, T max
      { x: -1, y: 1, z: 0 }, //  k min, T max
    ].map(project);
    // Fit the projected cloud into the viewport with a small margin.
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
    const scale = 0.88 * Math.min(plotW / (xMax - xMin || 1), plotH / (yMax - yMin || 1));
    const ox = plotW / 2 - (scale * (xMin + xMax)) / 2;
    const oy = plotH / 2 - (scale * (yMin + yMax)) / 2;
    const X = (p: { sx: number }) => ox + p.sx * scale;
    const Y = (p: { sy: number }) => oy + p.sy * scale;

    // Quads, painter-sorted back-to-front by mean projected depth.
    const vSpan = mesh.vMax - mesh.vMin || 1;
    const quads: { d: string; depth: number; color: string }[] = [];
    for (let i = 0; i < pts.length - 1; i++) {
      for (let j = 0; j < pts[i].length - 1; j++) {
        const c4 = [pts[i][j], pts[i][j + 1], pts[i + 1][j + 1], pts[i + 1][j]];
        const vAvg =
          (mesh.rows[i][j].vol + mesh.rows[i][j + 1].vol +
            mesh.rows[i + 1][j + 1].vol + mesh.rows[i + 1][j].vol) / 4;
        quads.push({
          d: `M${c4.map((p) => `${X(p).toFixed(1)},${Y(p).toFixed(1)}`).join("L")}Z`,
          depth: (c4[0].depth + c4[1].depth + c4[2].depth + c4[3].depth) / 4,
          color: volColor((vAvg - mesh.vMin) / vSpan),
        });
      }
    }
    quads.sort((a, b) => b.depth - a.depth);

    const frame = corners.map((c) => `${X(c).toFixed(1)},${Y(c).toFixed(1)}`).join(" ");
    const labels = [
      { x: X(corners[0]), y: Y(corners[0]) + 14, text: `k ${mesh.kMin.toFixed(2)}` },
      { x: X(corners[1]), y: Y(corners[1]) + 14, text: `k ${mesh.kMax.toFixed(2)}` },
      { x: X(corners[0]), y: Y(corners[0]) + 26, text: `T ${mesh.tMin.toFixed(2)}y` },
      { x: X(corners[3]), y: Y(corners[3]) + 14, text: `T ${mesh.tMax.toFixed(2)}y` },
    ];
    return { quads, frame, labels };
  }, [mesh, yaw, size]);

  /* ---------------- drag-to-rotate (yaw only; pitch is fixed) ------------ */

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

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend: colormap + grid info */}
      <div className="mb-1 flex shrink-0 items-center gap-3 px-1 text-[11px] text-slate-400">
        <span className="font-mono text-slate-500">σ(k, T)</span>
        {mesh !== null && (
          <span className="flex items-center gap-1.5 font-mono text-[10px] text-slate-500">
            {formatPct(mesh.vMin)}
            <span
              className="h-2 w-24 rounded"
              style={{
                background:
                  "linear-gradient(90deg, rgb(59 130 246), rgb(34 211 238), rgb(251 191 36), rgb(239 68 68))",
              }}
            />
            {formatPct(mesh.vMax)}
          </span>
        )}
        {data !== null && (
          <span className="text-[10px] text-slate-500">
            {data.expiries.length} expiries · {data.k.length} strikes
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-600">drag to rotate</span>
      </div>

      {/* Plot area */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {loading && data === null ? (
          message("Loading surface…")
        ) : error !== null ? (
          message(`Surface unavailable (${error})`)
        ) : mesh === null ? (
          message("Surface needs at least two expiries.")
        ) : scene === null ? null : ( /* container not measured yet */
          <svg
            width={size.width}
            height={size.height}
            className={[
              "absolute inset-0 cursor-grab active:cursor-grabbing transition-opacity",
              loading ? "opacity-60" : "opacity-100",
            ].join(" ")}
            style={{ touchAction: "none" }}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          >
            {/* Base-plane frame (z = 0) for grounding */}
            <polygon points={scene.frame} fill="none"
              stroke="rgb(148 163 184 / 0.25)" strokeDasharray="3 4" />
            {/* Surface cells, back-to-front */}
            {scene.quads.map((q, i) => (
              <path key={i} d={q.d} fill={q.color} fillOpacity={0.55}
                stroke={q.color} strokeOpacity={0.9} strokeWidth={0.6}
                strokeLinejoin="round" />
            ))}
            {/* Axis cue labels at the base corners */}
            {scene.labels.map((l) => (
              <text key={l.text} x={l.x} y={l.y} textAnchor="middle"
                className="fill-slate-500 font-mono text-[10px]">
                {l.text}
              </text>
            ))}
          </svg>
        )}
      </div>
    </div>
  );
}
