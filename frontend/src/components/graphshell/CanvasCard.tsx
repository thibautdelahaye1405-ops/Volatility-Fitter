// Graph shell CENTER card: the smile-universe canvas (ticker pods, calendar
// spines, solve cinematics) plus its loading/empty states and the
// interaction-hint + legend strip. Pure presentation — extracted from
// GraphViewer to keep the shell orchestrator under the file-size policy.
// Drop target (wave 3, C5): a node dragged from the Nodes pane shows a halo
// while over the card and hands the node to `onNodeDrop` (the viewer lights
// it, or pulses it in manual what-if).
import { useState } from "react";
import type { DragEvent } from "react";
import GraphNetworkChart, { type GraphEdgeSelection } from "../GraphNetworkChart";
import { decodeNodeDrag, isNodeDrag, NODE_MIME } from "../../lib/nodeDnd";
import type { DragNode } from "../../lib/nodeDnd";
import type { WaveState } from "../GraphNetworkChart.helpers";
import type { GraphNodeBase, GraphSolveNode } from "../../state/useGraph";
import type { ParticleSpec } from "../../state/useAttributionParticles";
import type { LayoutEdgeIn } from "../../lib/graphLayout";

interface CanvasCardProps {
  /** Baseline still loading (and no production field to show instead). */
  loading: boolean;
  nodes: GraphNodeBase[];
  edges: LayoutEdgeIn[];
  lit: Record<string, number>;
  results: Record<string, GraphSolveNode> | null;
  onToggle: (key: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  wave: WaveState;
  particles: ParticleSpec[];
  waveEpoch: number;
  manual: boolean;
  /** Edge click (U4): select a relation for the inspector. */
  onEdgeClick?: (sel: GraphEdgeSelection) => void;
  /** A node dropped onto the canvas (wave 3, C5). */
  onNodeDrop?: (node: DragNode) => void;
}

export default function CanvasCard({
  loading,
  nodes,
  edges,
  lit,
  results,
  onToggle,
  onOpenSmile,
  wave,
  particles,
  waveEpoch,
  manual,
  onEdgeClick,
  onNodeDrop,
}: CanvasCardProps) {
  const [dropHalo, setDropHalo] = useState(false);
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!onNodeDrop || !isNodeDrag(e.dataTransfer.types)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "link";
    if (!dropHalo) setDropHalo(true);
  };
  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    setDropHalo(false);
    const node = decodeNodeDrag(e.dataTransfer.getData(NODE_MIME));
    if (!node || !onNodeDrop) return;
    e.preventDefault();
    onNodeDrop(node);
  };
  return (
    <div
      data-drop-zone="graph-canvas"
      onDragOver={onDragOver}
      onDragLeave={() => setDropHalo(false)}
      onDrop={onDrop}
      className={[
        "relative flex min-w-0 flex-1 flex-col rounded-xl border bg-surface-900 p-4 shadow-xl shadow-black/30 transition-colors",
        dropHalo ? "border-accent-400 ring-2 ring-accent-400/40" : "border-slate-800",
      ].join(" ")}
    >
      {dropHalo && (
        <span className="pointer-events-none absolute top-3 right-4 z-10 rounded-md border border-accent-500/50 bg-accent-500/15 px-2 py-0.5 text-[10px] font-medium text-accent-300">
          {manual ? "Drop to pulse (+1 vol pt)" : "Drop to light the node"}
        </span>
      )}
      <div className="mb-2 flex shrink-0 items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-100">Smile universe</h2>
      </div>

      <div className="min-h-0 flex-1" data-chart-card="">
        {loading ? (
          <div className="flex h-full items-center justify-center text-xs text-slate-500">
            Fitting baseline nodes… (first load can take a second)
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-xs text-slate-500">
            No calibrated nodes yet — calibrate from the Parametric tab, or
            press Run to spread the transported priors across the selected
            universe.
          </div>
        ) : (
          <GraphNetworkChart
            nodes={nodes}
            edges={edges}
            lit={lit}
            results={results}
            onToggle={onToggle}
            onOpenSmile={onOpenSmile}
            onEdgeClick={onEdgeClick}
            wave={wave}
            particles={particles}
            waveEpoch={waveEpoch}
          />
        )}
      </div>

      {/* Interaction hint + visual legend (next to the canvas it explains) */}
      <div className="mt-1 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-600">
        <span>
          {manual
            ? "Click to pulse/unpulse · click an edge to inspect the relation · double-click to open smile · drop a node from the Nodes pane to pulse it"
            : "Click a node or edge to inspect · double-click to open smile · drag to pan, wheel to zoom · drop a node from the Nodes pane to light it"}
        </span>
        {/* The post-Run reveal is an INFLUENCE visualization (real BFS hops
            from the observations) — never solver chronology. */}
        <span
          className="cursor-help text-slate-600"
          title="The post-Run reveal stages nodes by their real graph distance (BFS hops) from the observations — an influence/attribution visualization. The posterior itself is solved jointly; the reveal is never solver chronology."
        >
          reveal = influence distance ⓘ
        </span>
        <span className="ml-auto flex items-center gap-3 text-slate-500">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-full border-2 border-amber-400/90" /> observed
          </span>
          <span className="flex items-center gap-1">
            <span
              className="h-2 w-8 rounded-sm"
              style={{ background: "linear-gradient(90deg, rgb(56 189 248), rgb(100 116 139), rgb(248 113 113))" }}
            />
            posterior shift
          </span>
          <span className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-full bg-slate-400/25" /> halo = uncertainty (sd)
          </span>
        </span>
      </div>
    </div>
  );
}
