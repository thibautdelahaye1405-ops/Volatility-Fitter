// Graph shell RIGHT pane (P5b U0): the inspector for the selected node.
//
// Selection comes from the shell (canvas click under the calibrations source,
// or a Diagnostics-table row). Shows the node's baseline facts, its
// prior → posterior move once a production run landed, and the exact
// attribution card (gain × innovation terms — why it moved). The full message
// inspector (incoming-messages table, local consensus vs global posterior) is
// the U4 increment; edge-click inspection arrives with it.
import GraphAttributionCard from "../GraphAttributionCard";
import type { GraphNodeBase } from "../../state/useGraph";
import type {
  ExtrapolateBody,
  ExtrapolateNode,
} from "../../state/useGraphExtrapolation";

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
  onClose,
  onOpenSmile,
}: InspectorPaneProps) {
  return (
    <aside className="flex w-80 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Inspector</h3>

      {selected === null ? (
        <p className="mt-1 text-[11px] text-slate-500">
          {manual
            ? "Manual what-if: click nodes on the canvas to light/dim them; the inspector reads production runs (From calibrations)."
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
