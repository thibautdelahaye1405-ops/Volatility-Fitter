// Graph shell LEFT pane (P5b U0): configuring relationships between markets.
//
// Cards top-down: Calendar (within-ticker maturity relations), Cross-asset
// (between-ticker relations), Overrides (the per-relation editor — message
// relation rows or the legacy weight/beta matrix), and Advanced (the legacy
// η/κ/λ/ν solver knobs — smooth field only; the message operator has none).
// The U2 increment upgrades Calendar into the full policy card (live example,
// per-ticker overrides, ladder/matrix views); U0 slots today's controls into
// the card grammar.
//
// The relation editors are fed by the SELECTED universe (GET /universe — what
// the production solve propagates over), fetched fresh each time the editor
// opens; the sandbox lattice is only a fallback (regression 2026-07-09: on the
// gated live server it is empty until mid-mode calibrations exist).
import { useEffect, useMemo, useState } from "react";
import { Grid3x3 } from "lucide-react";
import EdgeMatrixEditor from "../EdgeMatrixEditor";
import MessageEdgeEditor from "../MessageEdgeEditor";
import { MessageCalendarSection, MessageCrossSection } from "../MessagePanel";
import SolverPanel, {
  DEFAULT_CALENDAR_WEIGHT,
  DEFAULT_CROSS_WEIGHT,
  EdgeWeightInput,
} from "../SolverPanel";
import { api } from "../../state/api";
import type { UseGraphResult } from "../../state/useGraph";
import type { UniverseResponse } from "../../state/useSmile";
import type { ObservationSource } from "./GraphTopBar";

interface RelationshipsPaneProps {
  source: ObservationSource;
  graph: UseGraphResult;
  /** True when the message operator drives the production solve. */
  messages: boolean;
  /** Smooth-field cross-ticker β (calibrations source only). */
  crossBeta: number;
  setCrossBeta: (v: number) => void;
  /** Fired after a relation-editor save (parent refreshes topology + re-runs). */
  onEdgesSaved: () => void;
}

/** Uniform card chrome for the pane sections. */
function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface-800/40 p-3">
      <h4 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {title}
      </h4>
      {children}
    </section>
  );
}

export default function RelationshipsPane({
  source,
  graph,
  messages,
  crossBeta,
  setCrossBeta,
  onEdgesSaved,
}: RelationshipsPaneProps) {
  const manual = source === "manual";
  const [editingEdges, setEditingEdges] = useState(false);
  // U1 units lens for the message confidence scales: σ pts (default) vs raw p.
  const [rawUnits, setRawUnits] = useState(false);

  // Selected-universe nodes for the relation editors (fallback: sandbox nodes).
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

  const litCount = Object.keys(graph.lit).length;

  return (
    <aside className="flex w-72 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-100">Relationships</h3>
        {messages && (
          <button
            className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[9px] text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
            onClick={() => setRawUnits((v) => !v)}
            title="Confidence units: relationship uncertainty σ = 1/√p in vol points (default) vs the raw conditional precision p (1/vol²)"
          >
            {rawUnits ? "units: raw p" : "units: σ pts"}
          </button>
        )}
      </div>
      <p className="mb-3 text-[11px] text-slate-500">
        {messages
          ? "How each smile informs its neighbors: calendar and cross-asset message relations."
          : "Graph coupling of the smooth field: calendar and cross-ticker edge weights."}
      </p>

      <div className="flex flex-col gap-3">
        <Card title="Calendar">
          {messages ? (
            <MessageCalendarSection
              params={graph.params}
              setParam={graph.setParam}
              raw={rawUnits}
            />
          ) : (
            <EdgeWeightInput
              label="Calendar (same ticker)"
              title="Weight of within-ticker calendar edges."
              value={graph.params.calendarWeight}
              fallback={DEFAULT_CALENDAR_WEIGHT}
              onChange={(v) => graph.setParam("calendarWeight", v)}
            />
          )}
        </Card>

        <Card title="Cross-asset">
          {messages ? (
            <MessageCrossSection
              params={graph.params}
              setParam={graph.setParam}
              raw={rawUnits}
            />
          ) : (
            <>
              <EdgeWeightInput
                label="Cross-ticker"
                title="Weight of equal-expiry edges between tickers."
                value={graph.params.crossWeight}
                fallback={DEFAULT_CROSS_WEIGHT}
                onChange={(v) => graph.setParam("crossWeight", v)}
              />
              {!manual && (
                <label
                  className="flex items-center justify-between gap-2 text-xs text-slate-400"
                  title="Level-transfer slope applied on cross-ticker edges (smooth field)."
                >
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
            </>
          )}
        </Card>

        <Card title="Overrides">
          <p className="mb-2 text-[11px] text-slate-500">
            {messages
              ? "Per-relation rows: precision, per-handle β, relation class."
              : "Per-edge weight and β overrides on the auto lattice."}
          </p>
          <button
            className="flex w-full items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100"
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
        </Card>

        {/* Legacy solver knobs — the message operator has no η/κ/λ/ν. */}
        {!messages && (
          <details>
            <summary
              className="cursor-pointer text-[11px] text-slate-500 transition-colors hover:text-slate-300"
              title="Legacy smooth-field solver knobs. Defaults are seeded from Options ▸ Graph; edits here apply to this session"
            >
              Advanced <span className="text-slate-600">· η/κ/λ/ν · seeded from Options ▸ Graph</span>
            </summary>
            <SolverPanel
              params={graph.params}
              setParam={graph.setParam}
              resetParams={graph.resetParams}
              litCount={litCount}
              autotune={() => void graph.autotune()}
              autotuning={graph.autotuning}
              autotuneResult={graph.autotuneResult}
              autotuneError={graph.autotuneError}
            />
          </details>
        )}
      </div>

      {/* Relation editors (modal — the pane is too narrow for a grid). */}
      {editingEdges &&
        (messages ? (
          <MessageEdgeEditor
            nodes={editorNodes}
            params={graph.params}
            onSaved={onEdgesSaved}
            onClose={() => setEditingEdges(false)}
          />
        ) : (
          <EdgeMatrixEditor
            tickers={tickers}
            nodes={editorNodes}
            onSaved={onEdgesSaved}
            onClose={() => setEditingEdges(false)}
          />
        ))}
    </aside>
  );
}
