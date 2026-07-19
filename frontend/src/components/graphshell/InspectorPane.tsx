// Graph shell RIGHT pane (P5b U0; message inspector U4): the inspector for
// the selected node or edge.
//
// Selection comes from the shell (canvas node/edge click, or a Diagnostics-
// table row). Shows the node's baseline facts, its prior → posterior move
// once a production run landed, the U4 message inspector (incoming-messages
// table + local consensus vs global posterior + divergence explainer, message
// mode), and the exact attribution card (gain × innovation terms — why it
// moved). An edge click swaps in the relation card.
import GraphAttributionCard from "../GraphAttributionCard";
import { EdgeInspectorCard, MessageInspector } from "./MessageInspector";
import type { GraphNodeBase, SolverParams } from "../../state/useGraph";
import type {
  ExtrapolateBody,
  ExtrapolateNode,
} from "../../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../../state/useMessageEdges";
import type { GraphEdgeSelection } from "../GraphNetworkChart";

interface InspectorPaneProps {
  /** The inspected node, or null (empty state). */
  selected: { ticker: string; expiry: string } | null;
  /** Baseline facts for the selected node (GET /graph/nodes), if loaded. */
  base: GraphNodeBase | null;
  /** Production posterior for the selected node, once a run landed. */
  post: ExtrapolateNode | null;
  /** The /graph/extrapolate body of the run on screen (attribution knobs). */
  body: ExtrapolateBody;
  /** Attribution rides the production drill-in — calibrations source only. */
  showAttribution: boolean;
  manual: boolean;
  /** Message operator active (drives the U4 inspector sections). */
  messages: boolean;
  /** Effective relation rows (persisted else auto) + the solved nodes. */
  msgRows: MessageEdgeRow[];
  allNodes: ExtrapolateNode[] | null;
  params: SolverParams;
  /** A canvas edge click, or null; shows the relation card when set. */
  selectedEdge: GraphEdgeSelection | null;
  onCloseEdge: () => void;
  onEditRelations: () => void;
  onClose: () => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

/** One label/value fact row (title = the taxonomy long-name, if any). */
function Fact({
  label,
  title,
  children,
}: {
  label: string;
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-0.5 text-[11px]" title={title}>
      <span className="text-slate-500">{label}</span>
      <span className="text-right font-mono text-slate-200">{children}</span>
    </div>
  );
}

export default function InspectorPane({
  selected,
  base,
  post,
  body,
  showAttribution,
  manual,
  messages,
  msgRows,
  allNodes,
  params,
  selectedEdge,
  onCloseEdge,
  onEditRelations,
  onClose,
  onOpenSmile,
}: InspectorPaneProps) {
  return (
    <aside className="flex w-80 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Inspector</h3>

      {/* Edge-click relation card (U4) — shown above/instead of node facts. */}
      {selectedEdge !== null && (
        <EdgeInspectorCard
          edge={selectedEdge}
          rows={msgRows}
          nodes={allNodes}
          params={params}
          messages={messages}
          onClose={onCloseEdge}
          onEditRelations={onEditRelations}
        />
      )}

      {selected === null && selectedEdge !== null ? null : selected === null ? (
        <p className="mt-1 text-[11px] text-slate-500">
          {manual
            ? "What-if: canvas clicks add/remove pulses — select a row in Diagnostics to inspect a node."
            : "Click a node on the canvas — or a row in Diagnostics — to inspect it."}
        </p>
      ) : (
        <>
          {/* Header: identity + lit/dark + drill-in + close */}
          <div className="mb-2 flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-xs text-slate-300">
              <span className="font-medium text-slate-100">{selected.ticker}</span>{" "}
              <span className="font-mono text-[10px] text-slate-500">{selected.expiry}</span>
              {(post?.lit ?? base?.lit) !== undefined && (
                <span
                  className={`ml-1 text-[9px] ${
                    (post?.lit ?? base?.lit) ? "text-amber-400" : "text-slate-600"
                  }`}
                >
                  {(post?.lit ?? base?.lit) ? "lit" : "dark"}
                </span>
              )}
            </span>
            <button
              onClick={() => onOpenSmile(selected.ticker, selected.expiry)}
              title="Open this node's reconstructed smile"
              className="shrink-0 text-[11px] text-slate-600 hover:text-slate-300"
            >
              ↗
            </button>
            <button
              onClick={onClose}
              title="Close inspector"
              className="shrink-0 px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
            >
              ×
            </button>
          </div>

          {/* Posterior facts (once a production run landed), else baseline. */}
          {post !== null ? (
            <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/50 p-2">
              <Fact label="ATM vol">
                {(post.priorAtmVol * 100).toFixed(1)}→{(post.postAtmVol * 100).toFixed(1)}%
              </Fact>
              <Fact label="Skew" title="Prior → posterior skew handle">
                {post.priorSkew.toFixed(3)}→{post.postSkew.toFixed(3)}
              </Fact>
              <Fact label="Curvature" title="Prior → posterior curvature handle">
                {post.priorCurv.toFixed(3)}→{post.postCurv.toFixed(3)}
              </Fact>
              <Fact label="Shift">
                <span className={post.shiftBp >= 0 ? "text-emerald-400" : "text-rose-400"}>
                  {post.shiftBp >= 0 ? "+" : ""}
                  {post.shiftBp.toFixed(1)} bp
                </span>
              </Fact>
              <Fact
                label="Posterior confidence (1σ)"
                title="Final posterior confidence — the solved marginal sd; folds in source uncertainty and shared routes (authoritative)."
              >
                ±{(post.sd * 1e4).toFixed(0)} bp
              </Fact>
              {post.qIncoming !== null && (
                <Fact
                  label="Incoming confidence q"
                  title="Incoming message confidence q = Σp — the receiver conditional (§7.6). The final posterior (marginal) above is authoritative."
                >
                  {post.qIncoming.toFixed(0)}
                </Fact>
              )}
              {post.innovationBp !== null && (
                <Fact label="Innovation">
                  {post.innovationBp >= 0 ? "+" : ""}
                  {post.innovationBp.toFixed(1)} bp
                </Fact>
              )}
              <Fact label="Prior source">{post.priorSource}</Fact>
              {post.priorAsOf !== null && <Fact label="Prior as-of">{post.priorAsOf}</Fact>}
              {post.transportDistance > 0 && (
                <Fact
                  label="Transport"
                  title="Transported-prior comparison: how far the active prior travelled (spot transport distance) to form this node's baseline."
                >
                  {post.transportDistance.toFixed(3)}
                </Fact>
              )}
              {post.noLitPath === true && (
                <p
                  className="mt-1 rounded bg-rose-500/15 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-rose-300"
                  title="No lit path: this node's component has no observation — it stays at its transported prior with explicitly broad uncertainty (spec §14.3)"
                >
                  no lit path
                </p>
              )}
            </div>
          ) : base !== null ? (
            <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/50 p-2">
              <Fact label="ATM vol">{(base.atmVol * 100).toFixed(1)}%</Fact>
              <Fact label="Skew">{base.skew.toFixed(3)}</Fact>
              <Fact label="Curvature">{base.curvature.toFixed(3)}</Fact>
              <Fact label="T">{base.t.toFixed(3)}y</Fact>
              <p className="mt-1 text-[10px] text-slate-600">
                Baseline handles — press Run for the posterior.
              </p>
            </div>
          ) : null}

          {/* U4 message inspector: incoming messages + local consensus vs
              the solved global posterior. */}
          {messages && post !== null && allNodes !== null && (
            <MessageInspector
              receiver={post}
              rows={msgRows}
              nodes={allNodes}
              params={params}
            />
          )}

          {/* Why it moved: exact gain × innovation attribution. */}
          {showAttribution && (
            <GraphAttributionCard
              ticker={selected.ticker}
              expiry={selected.expiry}
              body={body}
              onClose={onClose}
              onOpenSmile={onOpenSmile}
            />
          )}
        </>
      )}
    </aside>
  );
}
