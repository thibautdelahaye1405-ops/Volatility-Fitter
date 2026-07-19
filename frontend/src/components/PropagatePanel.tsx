// The Graph workspace's single control panel: one workflow, one verb.
//
// The old Sandbox / Extrapolate mode fork collapses into an OBSERVATION SOURCE
// radio: "From calibrations" (production — transported priors + the lit nodes'
// calibration innovations, POST /graph/extrapolate) or "Manual what-if" (typed
// ATM-vol shifts on lit nodes, POST /graph/solve). Same graph, same solver
// knobs, same posterior visuals either way; PROPAGATE is the only primary
// action. Backtest (calibrations) lives under Validate; auto-tune η sits with
// the solver knobs it tunes.
import { useEffect, useMemo, useState } from "react";
import { Eraser, FlaskConical, Grid3x3 } from "lucide-react";
import EdgeMatrixEditor from "./EdgeMatrixEditor";
import ExtrapolateResults from "./ExtrapolateResults";
import MessageEdgeEditor from "./MessageEdgeEditor";
import MessagePanel from "./MessagePanel";
import SegmentedControl from "./SegmentedControl";
import SolverPanel from "./SolverPanel";
import { api } from "../state/api";
import type { PropagationMode, UseGraphResult } from "../state/useGraph";
import type { UseGraphExtrapolationResult } from "../state/useGraphExtrapolation";
import type { UniverseResponse } from "../state/useSmile";

/** Where the propagated observations come from. */
export type ObservationSource = "calibrations" | "manual";

interface PropagatePanelProps {
  /** Selected in the workspace header; the panel adapts its content. */
  source: ObservationSource;
  graph: UseGraphResult;
  extra: UseGraphExtrapolationResult;
  /** The /graph/extrapolate body (built in the parent; shared with drill-ins). */
  body: Record<string, string | number | boolean>;
  flatAtm: boolean;
  setFlatAtm: (v: boolean) => void;
  crossBeta: number;
  setCrossBeta: (v: number) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  onEdgesSaved?: () => void;
}

const buttonClass =
  "flex items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 " +
  "px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors " +
  "enabled:hover:border-slate-600 enabled:hover:text-slate-100 " +
  "disabled:cursor-not-allowed disabled:opacity-40";

const SOURCES: { key: ObservationSource; label: string; blurb: string }[] = [
  {
    key: "calibrations",
    label: "From calibrations",
    blurb: "Lit nodes' calibrated moves vs their transported priors drive the field.",
  },
  {
    key: "manual",
    label: "Manual what-if",
    blurb: "Type ATM-vol shifts on lit nodes and see them spread.",
  },
];

export default function PropagatePanel({
  source,
  graph,
  extra,
  body,
  flatAtm,
  setFlatAtm,
  crossBeta,
  setCrossBeta,
  onOpenSmile,
  onEdgesSaved,
}: PropagatePanelProps) {
  const [editingEdges, setEditingEdges] = useState(false);

  const manual = source === "manual";
  // Message operator active (production source only — the manual sandbox is
  // smooth-field by construction).
  const messages = !manual && graph.params.propagationMode === "precision_messages";
  const litEntries = useMemo(
    () => Object.entries(graph.lit).sort(([a], [b]) => a.localeCompare(b)),
    [graph.lit],
  );

  // Edge-editor universe: the SELECTED universe (GET /universe — what the
  // production solve propagates over), fetched fresh each time the editor
  // opens. The sandbox lattice (graph.nodes) is only a fallback — on the
  // gated live server it is empty until nodes are calibrated in mid mode,
  // which used to leave the matrix without a single row.
  const [universeNodes, setUniverseNodes] = useState<
    { ticker: string; expiry: string }[] | null
  >(null);
  useEffect(() => {
    if (!editingEdges) return;
    let alive = true;
    api
      .get<UniverseResponse>("/universe")
      .then((u) => {
        if (!alive) return;
        setUniverseNodes(
          u.tickers.flatMap((t) =>
            (u.expiries[t] ?? []).map((e) => ({ ticker: t, expiry: e.expiry })),
          ),
        );
      })
      .catch(() => {
        /* keep the sandbox fallback */
      });
    return () => {
      alive = false;
    };
  }, [editingEdges]);

  const editorNodes = useMemo(
    () =>
      universeNodes !== null && universeNodes.length > 0
        ? universeNodes
        : (graph.nodes ?? []).map((n) => ({ ticker: n.ticker, expiry: n.expiry })),
    [universeNodes, graph.nodes],
  );
  const tickers = useMemo(() => {
    const seen: string[] = [];
    for (const n of editorNodes) if (!seen.includes(n.ticker)) seen.push(n.ticker);
    return seen;
  }, [editorNodes]);

  const busy = manual ? graph.solving : extra.running;
  const canPropagate = manual ? litEntries.length > 0 : true;
  const hasResults = manual ? graph.results !== null : extra.nodes !== null;
  const propagate = () => {
    if (manual) void graph.solve();
    else void extra.run(body);
  };
  const clear = () => {
    if (manual) graph.clear();
    else extra.clear();
  };
  const error = manual ? graph.solveError : extra.error;

  return (
    <aside className="flex w-80 shrink-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
      {/* Observations (the source selector lives in the workspace header) */}
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Observations</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        {SOURCES.find((s) => s.key === source)?.blurb}
      </p>

      {/* Calibrations-only knobs */}
      {!manual && (
        <div className="mb-3 space-y-2 text-[11px] text-slate-400">
          {/* Propagation operator (message arc): smooth field = legacy,
              byte-identical; messages = the precision-message operator.
              Hybrid is config-only until validated (spec §20.1). */}
          <label className="flex items-center justify-between gap-2">
            <span title="Propagation operator — seeded from Options ▸ Graph">
              Propagation
            </span>
            <SegmentedControl
              options={[
                { id: "smooth_field" as PropagationMode, label: "Smooth field" },
                { id: "precision_messages" as PropagationMode, label: "Messages" },
              ]}
              value={graph.params.propagationMode}
              onChange={(m) => graph.setParam("propagationMode", m)}
              size="xs"
            />
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={flatAtm}
              onChange={(e) => setFlatAtm(e.target.checked)}
              className="accent-accent-500"
            />
            Flat baselines (diagnostic)
          </label>
          {!messages && (
            <label className="flex items-center justify-between gap-2">
              <span>Cross-ticker β</span>
              <input
                type="number"
                step={0.1}
                value={crossBeta}
                onChange={(e) => {
                  const v = e.target.valueAsNumber;
                  if (Number.isFinite(v)) setCrossBeta(v);
                }}
                className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
              />
            </label>
          )}
        </div>
      )}

      {/* §16.4 inconsistent-cycle warning (message mode) */}
      {!manual && extra.cycles.length > 0 && (
        <p
          className="mb-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300"
          title="Cycles whose beta product differs from 1 — an internally inconsistent edge configuration (spec §16.4)"
        >
          ⚠ {extra.cycles.length} inconsistent beta cycle
          {extra.cycles.length > 1 ? "s" : ""} · worst product{" "}
          {extra.cycles
            .reduce((m, c) => Math.max(m, Math.abs(c.betaProduct)), 0)
            .toFixed(2)}
        </p>
      )}

      {error !== null && (
        <p className="mb-2 truncate text-[10px] text-amber-400/80" title={error}>
          {error}
        </p>
      )}

      {/* Edge editors (modal — the aside is too narrow for a grid). The
          message operator gets its own relation editor (schema v2, one factor
          per relation); the legacy weight/beta matrix stays the smooth-field
          surface. */}
      {editingEdges &&
        (messages ? (
          <MessageEdgeEditor
            nodes={editorNodes}
            params={graph.params}
            onSaved={() => {
              onEdgesSaved?.();
              void extra.run(body);
            }}
            onClose={() => setEditingEdges(false)}
          />
        ) : (
          <EdgeMatrixEditor
            tickers={tickers}
            nodes={editorNodes}
            onSaved={() => {
              onEdgesSaved?.();
              if (!manual) void extra.run(body);
            }}
            onClose={() => setEditingEdges(false)}
          />
        ))}
      {
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
          {manual ? (
            /* One row per lit node: shift input (vol pts) + unlight */
            litEntries.length === 0 ? (
              <p className="py-2 text-xs text-slate-500">
                No lit nodes — click nodes in the graph to add observations.
              </p>
            ) : (
              <div className="divide-y divide-slate-800">
                {litEntries.map(([key, dAtmVol]) => {
                  const [ticker = "", expiry = ""] = key.split("|");
                  return (
                    <div key={key} className="flex items-center gap-2 py-1.5">
                      <span className="min-w-0 flex-1 truncate text-xs text-slate-300">
                        <span className="font-medium text-slate-100">{ticker}</span>{" "}
                        <span className="font-mono text-[10px] text-slate-500">{expiry}</span>
                      </span>
                      {/* Vol points: +2.0 means dAtmVol = +0.02. Uncontrolled so
                          partial entries like "-" don't snap back while typing. */}
                      <input
                        type="number"
                        step={0.5}
                        defaultValue={Number((dAtmVol * 100).toFixed(1))}
                        onChange={(e) => {
                          const pts = e.target.valueAsNumber;
                          if (Number.isFinite(pts)) graph.setShift(key, pts / 100);
                        }}
                        className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
                      />
                      <span className="text-[10px] text-slate-500">pts</span>
                      <button
                        onClick={() => graph.unlight(key)}
                        title="Remove observation"
                        className="px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
                      >
                        ×
                      </button>
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            <ExtrapolateResults extra={extra} body={body} onOpenSmile={onOpenSmile} />
          )}

          {/* Solver knobs (shared by both sources; auto-tune η lives here).
              Under the message operator the smooth-field knobs are inert, so
              the message panel replaces them. */}
          <details className="mt-3">
            <summary
              className="cursor-pointer text-[11px] text-slate-500 transition-colors hover:text-slate-300"
              title="Defaults are seeded from Options ▸ Graph; edits here apply to this session"
            >
              Solver settings <span className="text-slate-600">· seeded from Options ▸ Graph</span>
            </summary>
            {messages ? (
              <MessagePanel params={graph.params} setParam={graph.setParam} />
            ) : (
              <SolverPanel
                params={graph.params}
                setParam={graph.setParam}
                resetParams={graph.resetParams}
                litCount={litEntries.length}
                autotune={() => void graph.autotune()}
                autotuning={graph.autotuning}
                autotuneResult={graph.autotuneResult}
                autotuneError={graph.autotuneError}
              />
            )}
          </details>
        </div>
      }

      {/* Propagate / Clear / Validate (pinned below the scroll area) */}
      <div className="mt-3 border-t border-slate-800 pt-3">
        <div className="flex items-center gap-2">
          <button
            disabled={!canPropagate || busy}
            onClick={propagate}
            title={
              manual && litEntries.length === 0
                ? "Light at least one node first"
                : "Propagate the observations through the graph"
            }
            className="flex flex-1 items-center justify-center gap-2 rounded-md bg-accent-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            )}
            {busy ? "Propagating…" : "Propagate"}
          </button>
          <button
            disabled={!hasResults}
            onClick={clear}
            title="Reset the posterior field (observations are kept)"
            className={buttonClass}
          >
            <Eraser size={12} strokeWidth={1.75} className="opacity-80" />
            Clear field
          </button>
        </div>

        <div className="mt-2 flex items-center gap-2">
          {!manual && (
            <button
              className={buttonClass + " flex-1"}
              disabled={extra.backtesting}
              onClick={() => void extra.runBacktest(body)}
              title="Leave-one-node-out validation of the current knobs"
            >
              <FlaskConical size={12} strokeWidth={1.75} className="opacity-80" />
              {extra.backtesting ? "Backtesting…" : "Validate (LOO)"}
            </button>
          )}
          <button
            className={buttonClass + (manual ? " flex-1" : "")}
            onClick={() => setEditingEdges((v) => !v)}
            title={
              messages
                ? "Edit the message relations (precision + per-handle β + class)"
                : "Edit the per-edge graph weights + beta"
            }
          >
            <Grid3x3 size={12} strokeWidth={1.75} className="opacity-80" />
            {editingEdges ? "Done" : "Edges"}
          </button>
        </div>
        {!manual && extra.backtestError !== null && (
          <p className="mt-2 text-[10px] text-amber-400">{extra.backtestError}</p>
        )}
      </div>
    </aside>
  );
}
