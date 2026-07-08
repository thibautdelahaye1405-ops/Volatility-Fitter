// True node-link graph of the smile universe. Hand-rolled SVG, no chart deps.
//
// Pod-spine design: each ticker is a "pod" — a faint circle enclosing that
// ticker's expiry nodes, which sit on a calendar spine (adjacent maturities
// joined by straight segments). Cross-ticker coupling is bundled into one
// quadratic Bézier per ticker pair (width ~ log Σweight); hovering a bundle
// expands it into its individual directed edges. The scene pans (background
// drag) and zooms (wheel, toward the cursor); "Fit" restores the framing.
//
// Node states (same visual language as the lattice GraphChart):
//   dark            slate fill, subtle border (no information yet)
//   lit (observed)  amber ring + glow, carries a user dAtmVol observation
//   solved          fill on a diverging blue -> slate -> red scale from the
//                   posterior shift (bp), plus an outer halo whose radius /
//                   fade encode the posterior sd (bigger + fainter = more
//                   uncertain). Lit nodes keep the amber ring on top.
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { nodeKey } from "../state/useGraph";
import { clamp } from "../lib/chartScale";
import { shiftColor } from "../lib/graphColor";
import { computeGraphLayout } from "../lib/graphLayout";
import type { GraphLayout, LayoutEdgeIn, PairEdgeDetail } from "../lib/graphLayout";
import {
  ArrowMarker,
  BundleTooltip,
  NodeTooltip,
  HALO_MAX,
  K_MAX,
  K_MIN,
  NODE_R,
  SLATE_400,
  buildAdjacency,
  bundleGeometry,
  fitTransform,
  type BundleGeo,
  type Size,
  type Transform,
} from "./GraphNetworkChart.helpers";

interface GraphNetworkChartProps {
  /** Baseline nodes incl. t + lit designation. */
  nodes: GraphNodeBase[];
  /** The REAL solver topology (persisted overrides or the auto-lattice). */
  edges: LayoutEdgeIn[];
  /** Lit nodes: key -> dAtmVol observation (decimal vol). */
  lit: Record<string, number>;
  /** Posterior nodes keyed like `lit`, or null before the first solve. */
  results: Record<string, GraphSolveNode> | null;
  /** Single click: light/dim a node. */
  onToggle: (key: string) => void;
  /** Double click: drill into the node's smile. */
  onOpenSmile: (ticker: string, expiry: string) => void;
}

export default function GraphNetworkChart({
  nodes,
  edges,
  lit,
  results,
  onToggle,
  onOpenSmile,
}: GraphNetworkChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [transform, setTransform] = useState<Transform>({ k: 1, tx: 0, ty: 0 });
  const [dragging, setDragging] = useState(false);
  /** Key of the hovered node (drives focus-dimming + the tooltip). */
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  /** Hovered cross-ticker bundle (its precomputed geometry), or null. */
  const [hoverBundle, setHoverBundle] = useState<BundleGeo | null>(null);
  /** Live pan: pointer + transform at drag start (no per-move allocations
   *  beyond the transform state itself). */
  const dragRef = useRef<{ sx: number; sy: number; tx: number; ty: number } | null>(null);
  /** Layout identity last auto-fitted — a container resize never re-fits. */
  const fittedRef = useRef<GraphLayout | null>(null);

  const layout = useMemo(
    () =>
      computeGraphLayout(
        nodes.map((n) => ({ ticker: n.ticker, expiry: n.expiry, t: n.t })),
        edges,
      ),
    [nodes, edges],
  );

  // Track the container size (the SVG fills it; tooltips are absolute in it).
  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;
    const ro = new ResizeObserver(() => setSize({ w: el.clientWidth, h: el.clientHeight }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Initial fit: once per layout identity, as soon as the size is known.
  useEffect(() => {
    if (size === null || fittedRef.current === layout) return;
    fittedRef.current = layout;
    setTransform(fitTransform(size, layout));
  }, [size, layout]);

  // Wheel zoom toward the cursor. Native non-passive listener — React's
  // synthetic onWheel can't preventDefault the page scroll.
  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      setTransform((prev) => {
        const k = clamp(prev.k * Math.exp(-e.deltaY * 0.0015), K_MIN, K_MAX);
        const s = k / prev.k; // keep the scene point under the cursor fixed
        return { k, tx: cx - (cx - prev.tx) * s, ty: cy - (cy - prev.ty) * s };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Solve-wide normalisers: colours clamp at max |shift|, halos at max sd.
  const { maxAbsShift, maxSd } = useMemo(() => {
    let shift = 0;
    let sd = 0;
    for (const r of Object.values(results ?? {})) {
      shift = Math.max(shift, Math.abs(r.shiftBp));
      sd = Math.max(sd, r.sd);
    }
    return { maxAbsShift: shift, maxSd: sd };
  }, [results]);

  // Per-bundle geometry (paths, widths, midpoints), once per layout.
  const bundleGeos = useMemo(() => {
    const maxLogW = layout.bundles.reduce(
      (m, b) => Math.max(m, Math.log1p(b.totalWeight)),
      0,
    );
    return layout.bundles.map((b) => bundleGeometry(b, maxLogW));
  }, [layout]);

  // Adjacency for hover focus (individual edges + own-pod spine neighbours).
  const { adj, nodeBundles } = useMemo(
    () => buildAdjacency(edges, layout.calendar),
    [edges, layout],
  );

  // Hover focus: the hovered node + everything adjacent stays full-opacity;
  // every other element dims to 0.15 (group opacity, multiplicative).
  const focus = useMemo(() => {
    if (hoverKey === null) return null;
    const keep = new Set<string>([hoverKey]);
    for (const k of adj.get(hoverKey) ?? []) keep.add(k);
    const tickers = new Set<string>();
    for (const k of keep) tickers.add(k.split("|")[0] ?? "");
    return { keep, tickers, bundles: nodeBundles.get(hoverKey) ?? new Set<string>() };
  }, [hoverKey, adj, nodeBundles]);
  const [hovTicker = "", hovExpiry = ""] = hoverKey?.split("|") ?? [];

  // Individual edges of the hovered bundle, overlaid with direction arrows.
  const bundleDetails = useMemo<PairEdgeDetail[]>(
    () =>
      hoverBundle === null
        ? []
        : layout.pairDetails(hoverBundle.b.fromTicker, hoverBundle.b.toTicker),
    [hoverBundle, layout],
  );

  const hoverNode =
    hoverKey !== null
      ? nodes.find((n) => nodeKey(n.ticker, n.expiry) === hoverKey)
      : undefined;
  const hoverPos = hoverKey !== null ? layout.nodePos.get(hoverKey) : undefined;
  const hoverResult = hoverKey !== null ? results?.[hoverKey] : undefined;

  /* --------------------------- pan handlers --------------------------- */
  const startPan = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // left button only; nodes stop propagation
    dragRef.current = { sx: e.clientX, sy: e.clientY, tx: transform.tx, ty: transform.ty };
    setDragging(true);
  };
  const movePan = (e: React.MouseEvent) => {
    const d = dragRef.current;
    if (d === null) return;
    setTransform((prev) => ({
      k: prev.k,
      tx: d.tx + (e.clientX - d.sx),
      ty: d.ty + (e.clientY - d.sy),
    }));
  };
  const endPan = () => {
    dragRef.current = null;
    setDragging(false);
  };

  const { k, tx, ty } = transform;

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden">
      <svg
        width="100%"
        height="100%"
        className={dragging ? "cursor-grabbing select-none" : "cursor-grab"}
        onMouseDown={startPan}
        onMouseMove={movePan}
        onMouseUp={endPan}
        onMouseLeave={endPan}
      >
        <defs>
          <ArrowMarker id="gnc-arrow" px={7} />
          <ArrowMarker id="gnc-arrow-sm" px={5} />
        </defs>
        <g transform={`translate(${tx} ${ty}) scale(${k})`}>
          {/* Cross-ticker bundles: one Bézier per ticker pair, log-weight width */}
          {bundleGeos.map((g) => {
            const hovered = hoverBundle?.key === g.key;
            const dimmed = focus !== null && !focus.bundles.has(g.key);
            return (
              <g key={g.key} opacity={dimmed ? 0.15 : 1}>
                <path
                  d={g.d}
                  fill="none"
                  stroke={SLATE_400}
                  strokeWidth={g.width}
                  opacity={hovered ? 0.5 : 0.16}
                  markerEnd={hovered ? "url(#gnc-arrow)" : undefined}
                  markerStart={hovered && g.b.bidirectional ? "url(#gnc-arrow)" : undefined}
                />
                {/* Wide invisible twin so the thin bundle is hoverable */}
                <path
                  d={g.d}
                  fill="none"
                  stroke="transparent"
                  strokeWidth={g.width + 10}
                  pointerEvents="stroke"
                  onMouseEnter={() => setHoverBundle(g)}
                  onMouseLeave={() => setHoverBundle(null)}
                />
              </g>
            );
          })}

          {/* Hovered bundle expanded: its individual directed edges */}
          {bundleDetails.map((d, i) => (
            <line
              key={`pd-${i}`}
              x1={d.x1} y1={d.y1} x2={d.x2} y2={d.y2}
              stroke={SLATE_400}
              strokeWidth={1}
              opacity={0.35}
              pointerEvents="none"
              markerEnd="url(#gnc-arrow-sm)"
            />
          ))}

          {/* Calendar spines: adjacent maturities within a pod */}
          {layout.calendar.map((c) => {
            const touches =
              focus === null ||
              (c.ticker === hovTicker &&
                (c.fromExpiry === hovExpiry || c.toExpiry === hovExpiry));
            const filler = c.weight === 0; // topology filler, no solver weight
            return (
              <line
                key={`cal-${c.ticker}-${c.fromExpiry}-${c.toExpiry}`}
                x1={c.x1} y1={c.y1} x2={c.x2} y2={c.y2}
                stroke={SLATE_400}
                strokeWidth={1.5}
                strokeDasharray={filler ? "3 3" : undefined}
                opacity={(filler ? 0.15 : 0.3) * (touches ? 1 : 0.15)}
              />
            );
          })}

          {/* Pods: faint enclosing circle + ticker label above */}
          {layout.pods.map((pod) => (
            <g
              key={pod.ticker}
              opacity={focus === null || focus.tickers.has(pod.ticker) ? 1 : 0.15}
            >
              <circle cx={pod.cx} cy={pod.cy} r={pod.radius} fill="none" stroke="rgb(51 65 85)" />
              <text
                x={pod.cx}
                y={pod.cy - pod.radius - 8}
                textAnchor="middle"
                className="fill-slate-300 text-[11px] font-semibold tracking-wide"
              >
                {pod.ticker}
              </text>
            </g>
          ))}

          {/* Nodes */}
          {nodes.map((n) => {
            const key = nodeKey(n.ticker, n.expiry);
            const p = layout.nodePos.get(key);
            if (!p) return null;
            const isLit = key in lit;
            const result = results?.[key];
            const fill = result
              ? shiftColor(result.shiftBp, maxAbsShift)
              : "var(--color-surface-700)";
            // Uncertainty halo: radius grows and fades with the posterior sd
            // (normalised by the solve's max sd, extra radius <= HALO_MAX).
            const sdFrac = result && maxSd > 0 ? clamp(result.sd / maxSd, 0, 1) : 0;
            // Centre label: lit pre-solve -> observation in vol pts;
            // post-solve -> posterior shift in whole bp.
            const label = result
              ? `${result.shiftBp >= 0 ? "+" : ""}${Math.round(result.shiftBp)}`
              : isLit
                ? `${(lit[key] ?? 0) >= 0 ? "+" : ""}${((lit[key] ?? 0) * 100).toFixed(1)}`
                : null;
            return (
              // Click toggles lit/dark; double-click opens the smile (the two
              // single clicks of a dblclick toggle twice, i.e. net no-op).
              <g
                key={key}
                className="cursor-pointer"
                opacity={focus === null || focus.keep.has(key) ? 1 : 0.15}
                // Stop the press from starting a background pan so a plain
                // click still toggles this node.
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => onToggle(key)}
                onDoubleClick={() => onOpenSmile(n.ticker, n.expiry)}
                onMouseEnter={() => setHoverKey(key)}
                onMouseLeave={() => setHoverKey(null)}
              >
                {result && sdFrac > 0 && (
                  <circle
                    cx={p.x} cy={p.y}
                    r={NODE_R + sdFrac * HALO_MAX}
                    fill={fill}
                    opacity={0.3 - 0.18 * sdFrac}
                  />
                )}
                <circle
                  cx={p.x} cy={p.y} r={NODE_R}
                  fill={fill}
                  stroke={isLit ? "#fbbf24" : "rgb(148 163 184 / 0.35)"}
                  strokeWidth={isLit ? 2 : 1}
                  style={
                    isLit
                      ? { filter: "drop-shadow(0 0 6px rgb(251 191 36 / 0.55))" }
                      : undefined
                  }
                />
                {label !== null && (
                  <text
                    x={p.x} y={p.y} dy="0.34em" textAnchor="middle"
                    pointerEvents="none"
                    className={[
                      "font-mono text-[9px] font-medium",
                      result ? "fill-slate-100" : "fill-amber-300",
                    ].join(" ")}
                  >
                    {label}
                  </text>
                )}
                {/* Expiry shorthand beside the node (MM-DD of an ISO date) */}
                <text
                  x={p.x + 17} y={p.y} dy="0.32em"
                  pointerEvents="none"
                  className="fill-slate-500 font-mono text-[8px]"
                >
                  {n.expiry.slice(5)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {/* Fit-to-view (resets the pan/zoom to the initial framing) */}
      <button
        onClick={() => size !== null && setTransform(fitTransform(size, layout))}
        title="Fit graph to view"
        className="absolute right-3 top-3 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100"
      >
        ⤢ Fit
      </button>

      {hoverNode && hoverPos && (
        <NodeTooltip
          node={hoverNode}
          result={hoverResult}
          pos={hoverPos}
          t={transform}
          maxAbsShift={maxAbsShift}
        />
      )}
      {hoverBundle && <BundleTooltip geo={hoverBundle} t={transform} />}
    </div>
  );
}
