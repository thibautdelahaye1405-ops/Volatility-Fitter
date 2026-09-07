// True node-link graph of the smile universe — the Graph lens's canvas AND,
// since the GRAPH ERGONOMICS ARC (E3), its relation editor (hand-rolled SVG).
// Pod-spine design: each ticker is a pod enclosing its expiry nodes on a
// calendar spine; cross-ticker relations bundle into one Bézier per pair and
// expand (hover, or click for a sticky expansion) into individual ARROWS —
// informer → receiver, thickness = confidence, colour = β (GraphEdgeLayer).
// Gestures (handlers optional — absent = read-only): click an arrow / hop
// selects the relation, click a bundle expands it + opens the pair card,
// Connect tool or Shift-drag node → node adds a relation, a ticker label
// collapses its pod, Focus hides the side panes. Node gestures are unchanged
// (click toggles / pulses, double-click drills in, background drag pans,
// wheel zooms). Solve cinematics: the reveal by REAL BFS hop + attribution
// particles — honest staging, never decoration.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import { nodeKey } from "../state/useGraph";
import type { ParticleSpec } from "../state/useAttributionParticles";
import { computeGraphLayout } from "../lib/graphLayout";
import type { CalendarEdge, GraphLayout, LayoutEdgeIn } from "../lib/graphLayout";
import { aggregateLit, aggregateResults, collapseUniverse, isCollapsedKey } from "../lib/graphCollapse";
import { arrowHeadPoints } from "../lib/edgeStyle";
import type { NodeRef } from "../lib/relationRows";
import GraphCanvasToolbar from "./GraphCanvasToolbar";
import GraphEdgeLayer, { calendarKeys, type RelationHover } from "./GraphEdgeLayer";
import GraphNodeLayer from "./GraphNodeLayer";
import GraphWaveOverlay from "./GraphWaveOverlay";
import { BundleTooltip, NodeTooltip, RelationTooltip } from "./GraphNetworkChart.tooltips";
import {
  WavePulseStyle,
  buildAdjacency,
  bundleGeometry,
  fitTransform,
  focusOf,
  toScene,
  zoomAbout,
  type BundleGeo,
  type Size,
  type Transform,
  type WaveState,
} from "./GraphNetworkChart.helpers";

/** Edge-click selection: a cross ticker pair, one calendar adjacent pair, or
 *  (E3) ONE relation by its directed key `source|sExp>target|tExp`. */
export type GraphEdgeSelection =
  | { kind: "cross"; a: string; b: string }
  | { kind: "calendar"; ticker: string; aExpiry: string; bExpiry: string }
  | { kind: "relation"; key: string };

interface GraphNetworkChartProps {
  nodes: GraphNodeBase[];
  /** The REAL solver topology (message rows, persisted overrides or the auto-lattice). */
  edges: LayoutEdgeIn[];
  lit: Record<string, number>;
  results: Record<string, GraphSolveNode> | null;
  onToggle: (key: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  /** Edge click: select a relation / pair for the inspector. */
  onEdgeClick?: (sel: GraphEdgeSelection) => void;
  /** The relation highlighted on the canvas (inspector selection). */
  selectedRelationKey?: string | null;
  /** Connect gesture landed: informer → receiver (E3). Absent = no tool. */
  onConnect?: (source: NodeRef, target: NodeRef) => void;
  focused?: boolean;
  onToggleFocus?: () => void;
  wave?: WaveState;
  particles?: ParticleSpec[];
  waveEpoch?: number;
}

interface ConnectState {
  fromKey: string;
  x: number;
  y: number;
}

export default function GraphNetworkChart({
  nodes,
  edges,
  lit,
  results,
  onToggle,
  onOpenSmile,
  onEdgeClick,
  selectedRelationKey = null,
  onConnect,
  focused,
  onToggleFocus,
  wave,
  particles,
  waveEpoch,
}: GraphNetworkChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [transform, setTransform] = useState<Transform>({ k: 1, tx: 0, ty: 0 });
  const [dragging, setDragging] = useState(false);
  const [hoverKey, setHoverKey] = useState<string | null>(null);
  const [hoverBundle, setHoverBundle] = useState<BundleGeo | null>(null);
  const [hoverRelation, setHoverRelation] = useState<RelationHover | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [connectTool, setConnectTool] = useState(false);
  const [connecting, setConnecting] = useState<ConnectState | null>(null);
  const dragRef = useRef<{ sx: number; sy: number; tx: number; ty: number } | null>(null);
  const fittedRef = useRef<GraphLayout | null>(null);
  /** A just-finished connect gesture must not toggle the node under it. */
  const suppressClickRef = useRef(false);

  // Collapsed-pod universe → layout; results / lit aggregated per pod.
  const cu = useMemo(() => collapseUniverse(nodes, edges, collapsed), [nodes, edges, collapsed]);
  const layout = useMemo(
    () =>
      computeGraphLayout(
        cu.nodes.map((n) => ({ ticker: n.ticker, expiry: n.expiry, t: n.t })),
        cu.edges,
      ),
    [cu],
  );
  const dispResults = useMemo(() => aggregateResults(results, cu.members), [results, cu.members]);
  const dispLit = useMemo(() => aggregateLit(lit, cu.members), [lit, cu.members]);
  const tickers = useMemo(() => [...new Set(nodes.map((n) => n.ticker))], [nodes]);

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

  // Wheel zoom toward the cursor (native non-passive listener).
  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      setTransform((prev) =>
        zoomAbout(prev, Math.exp(-e.deltaY * 0.0015), e.clientX - rect.left, e.clientY - rect.top),
      );
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // Esc cancels a connect gesture / exits the tool.
  useEffect(() => {
    if (!connectTool && connecting === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setConnecting(null);
      setConnectTool(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [connectTool, connecting]);

  // Solve-wide normalisers: colours clamp at max |shift|, halos at max sd.
  const { maxAbsShift, maxSd } = useMemo(() => {
    let shift = 0;
    let sd = 0;
    for (const r of Object.values(dispResults ?? {})) {
      shift = Math.max(shift, Math.abs(r.shiftBp));
      sd = Math.max(sd, r.sd);
    }
    return { maxAbsShift: shift, maxSd: sd };
  }, [dispResults]);

  const bundleGeos = useMemo(() => layout.bundles.map(bundleGeometry), [layout]);
  const { adj, nodeBundles } = useMemo(() => buildAdjacency(cu.edges, layout.calendar), [cu.edges, layout]);
  const focus = useMemo(() => focusOf(hoverKey, adj, nodeBundles), [hoverKey, adj, nodeBundles]);
  const [hovTicker = "", hovExpiry = ""] = hoverKey?.split("|") ?? [];

  const hoverNode = hoverKey !== null ? cu.nodes.find((n) => nodeKey(n.ticker, n.expiry) === hoverKey) : undefined;
  const hoverPos = hoverKey !== null ? layout.nodePos.get(hoverKey) : undefined;

  /* ------------------------- edge click routing ------------------------- */
  const onCalendarClick = useCallback(
    (c: CalendarEdge) => {
      if (onEdgeClick === undefined) return;
      const keys = calendarKeys(c);
      // One stored direction → the relation itself; both → the pair card.
      if (c.toEarlier !== c.toLater)
        onEdgeClick({ kind: "relation", key: c.toEarlier ? keys.toEarlier : keys.toLater });
      else onEdgeClick({ kind: "calendar", ticker: c.ticker, aExpiry: c.fromExpiry, bExpiry: c.toExpiry });
    },
    [onEdgeClick],
  );
  const onBundleClick = useCallback(
    (g: BundleGeo) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(g.key)) next.delete(g.key);
        else next.add(g.key);
        return next;
      });
      onEdgeClick?.({ kind: "cross", a: g.b.fromTicker, b: g.b.toTicker });
    },
    [onEdgeClick],
  );

  /* --------------------------- pan + connect --------------------------- */
  const scenePoint = (e: React.MouseEvent) => {
    const rect = containerRef.current?.getBoundingClientRect();
    return toScene(transform, e.clientX - (rect?.left ?? 0), e.clientY - (rect?.top ?? 0));
  };
  const startPan = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // left button only; nodes stop propagation
    if (wave?.animating) wave.skip(); // a pan gesture fast-forwards the reveal
    dragRef.current = { sx: e.clientX, sy: e.clientY, tx: transform.tx, ty: transform.ty };
    setDragging(true);
  };
  const move = (e: React.MouseEvent) => {
    if (connecting !== null) {
      const p = scenePoint(e);
      setConnecting({ ...connecting, x: p.x, y: p.y });
      return;
    }
    const d = dragRef.current;
    if (d === null) return;
    setTransform((prev) => ({ k: prev.k, tx: d.tx + (e.clientX - d.sx), ty: d.ty + (e.clientY - d.sy) }));
  };
  const end = () => {
    dragRef.current = null;
    setDragging(false);
    if (connecting !== null) setConnecting(null); // released off a node: cancel
  };
  const onNodeMouseDown = (key: string, e: React.MouseEvent) => {
    e.stopPropagation(); // never start a background pan from a node
    if (onConnect === undefined || isCollapsedKey(key)) return;
    if (!(connectTool || e.shiftKey)) return;
    e.preventDefault();
    const p = scenePoint(e);
    setConnecting({ fromKey: key, x: p.x, y: p.y });
  };
  const onNodeMouseUp = (key: string, e: React.MouseEvent) => {
    if (connecting === null) return;
    e.stopPropagation();
    const from = connecting.fromKey;
    setConnecting(null);
    suppressClickRef.current = true;
    if (key === from || isCollapsedKey(key) || onConnect === undefined) return;
    const [st = "", se = ""] = from.split("|");
    const [tt = "", te = ""] = key.split("|");
    onConnect({ ticker: st, expiry: se }, { ticker: tt, expiry: te });
  };
  const onNodeToggle = (key: string) => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    onToggle(key);
  };
  const togglePod = (ticker: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });

  const { k, tx, ty } = transform;
  const connectFromPos = connecting !== null ? layout.nodePos.get(connecting.fromKey) : undefined;

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden" data-testid="graph-canvas">
      <svg
        width="100%"
        height="100%"
        className={dragging ? "cursor-grabbing select-none" : connectTool ? "cursor-crosshair" : "cursor-grab"}
        onMouseDown={startPan}
        onMouseMove={move}
        onMouseUp={end}
        onMouseLeave={end}
      >
        <defs>{wave !== undefined && <WavePulseStyle />}</defs>
        <g transform={`translate(${tx} ${ty}) scale(${k})`}>
          <GraphEdgeLayer
            layout={layout}
            bundleGeos={bundleGeos}
            focus={focus}
            hovTicker={hovTicker}
            hovExpiry={hovExpiry}
            hoverBundleKey={hoverBundle?.key ?? null}
            expanded={expanded}
            selectedKey={selectedRelationKey}
            hoverRelationKey={hoverRelation?.key ?? null}
            interactive={onEdgeClick !== undefined}
            onBundleEnter={setHoverBundle}
            onBundleLeave={() => setHoverBundle(null)}
            onBundleClick={onBundleClick}
            onRelationEnter={setHoverRelation}
            onRelationLeave={() => setHoverRelation(null)}
            onRelationClick={(key) => onEdgeClick?.({ kind: "relation", key })}
            onCalendarClick={onCalendarClick}
          />

          {/* Pods: faint enclosing circle + ticker label (click = collapse) */}
          {layout.pods.map((pod) => (
            <g key={pod.ticker} opacity={focus === null || focus.tickers.has(pod.ticker) ? 1 : 0.15}>
              <circle cx={pod.cx} cy={pod.cy} r={pod.radius} fill="none" stroke="rgb(51 65 85)" />
              <text
                x={pod.cx}
                y={pod.cy - pod.radius - 8}
                textAnchor="middle"
                className="cursor-pointer fill-slate-300 text-[11px] font-semibold tracking-wide hover:fill-slate-100"
                data-pod={pod.ticker}
                onMouseDown={(e) => e.stopPropagation()}
                onClick={() => togglePod(pod.ticker)}
              >
                {pod.ticker}
                {collapsed.has(pod.ticker) ? " ▸" : ""}
                <title>{collapsed.has(pod.ticker) ? "Expand this ticker's expiries" : "Collapse this ticker to one node"}</title>
              </text>
            </g>
          ))}

          <GraphNodeLayer
            nodes={cu.nodes}
            layout={layout}
            lit={dispLit}
            results={dispResults}
            maxAbsShift={maxAbsShift}
            maxSd={maxSd}
            focusKeep={focus === null ? null : focus.keep}
            wave={wave}
            members={cu.members}
            connectFrom={connecting?.fromKey ?? null}
            onToggle={onNodeToggle}
            onOpenSmile={onOpenSmile}
            onHover={setHoverKey}
            onNodeMouseDown={onNodeMouseDown}
            onNodeMouseUp={onNodeMouseUp}
          />

          {/* Connect rubber band: source node → pointer, with a head */}
          {connecting !== null && connectFromPos !== undefined && (
            <g pointerEvents="none" data-testid="connect-band">
              <line
                x1={connectFromPos.x} y1={connectFromPos.y} x2={connecting.x} y2={connecting.y}
                stroke="var(--color-accent-400)" strokeWidth={2} strokeDasharray="5 4" opacity={0.9}
              />
              <polygon
                points={arrowHeadPoints(connectFromPos.x, connectFromPos.y, connecting.x, connecting.y)}
                fill="var(--color-accent-400)"
              />
            </g>
          )}

          {particles !== undefined && particles.length > 0 && (
            <GraphWaveOverlay particles={particles} nodePos={layout.nodePos} epoch={waveEpoch ?? 0} />
          )}
        </g>
      </svg>

      <GraphCanvasToolbar
        onZoomIn={() => size !== null && setTransform((p) => zoomAbout(p, 1.3, size.w / 2, size.h / 2))}
        onZoomOut={() => size !== null && setTransform((p) => zoomAbout(p, 1 / 1.3, size.w / 2, size.h / 2))}
        onFit={() => size !== null && setTransform(fitTransform(size, layout))}
        connectTool={onConnect !== undefined ? connectTool : undefined}
        onToggleConnect={onConnect !== undefined ? () => setConnectTool((v) => !v) : undefined}
        allCollapsed={tickers.length > 1 ? tickers.every((t) => collapsed.has(t)) : undefined}
        onCollapseAll={tickers.length > 1 ? () => setCollapsed(new Set(tickers)) : undefined}
        onExpandAll={tickers.length > 1 ? () => setCollapsed(new Set()) : undefined}
        focused={focused}
        onToggleFocus={onToggleFocus}
      />

      {hoverNode && hoverPos && (
        <NodeTooltip
          node={hoverNode}
          result={dispResults?.[hoverKey ?? ""]}
          pos={hoverPos}
          t={transform}
          maxAbsShift={maxAbsShift}
          memberCount={cu.members.get(hoverKey ?? "")?.length ?? 0}
        />
      )}
      {hoverBundle && hoverRelation === null && <BundleTooltip geo={hoverBundle} t={transform} />}
      {hoverRelation && (
        <RelationTooltip
          label={hoverRelation.label}
          beta={hoverRelation.beta}
          precision={hoverRelation.precision}
          x={hoverRelation.x}
          y={hoverRelation.y}
          t={transform}
        />
      )}
    </div>
  );
}
