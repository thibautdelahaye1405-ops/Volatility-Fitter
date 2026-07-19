// Graph shell BOTTOM drawer (P5b U0; test pulse unified in U3): Preview |
// Diagnostics | Validation | Observation plan.
//
//   Preview      — what the next Run will propagate: the what-if TEST PULSE
//                  rows (editable shifts + canonical scenario shortcuts;
//                  non-persisting, runs the ACTIVE operator on the production
//                  machinery) or the calibrations summary + the
//                  flat-baselines diagnostic toggle.
//   Diagnostics  — the post-run field: §16.4 cycle warnings + the per-node
//                  prior → posterior table (both sources — one solve).
//   Validation   — U7: the side-by-side current-day LOO across operators
//                  (ValidationTab) + the offline benchmark-artifact link.
//   Observation plan — "where to quote next" ranking on the solved posterior
//                  (rides the SAME body as Run — what-if pulses included),
//                  with U7 WHY-annotations per candidate.
//
// The shell owns tab/open state so a landing run can reveal Diagnostics.
import ExtrapolateResults from "../ExtrapolateResults";
import ObservationPlanCard from "../ObservationPlanCard";
import ValidationTab from "./ValidationTab";
import { planAnnotations } from "../../lib/planAnnotations";
import { buildScenario, SCENARIOS } from "../../lib/whatifScenarios";
import type { GraphNodeBase, UseGraphResult } from "../../state/useGraph";
import type {
  ExtrapolateBody,
  UseGraphExtrapolationResult,
} from "../../state/useGraphExtrapolation";
import type { UseLooComparisonResult } from "../../state/useLooComparison";
import type { MessageEdgeRow } from "../../state/useMessageEdges";
import type { ObservationSource } from "./GraphTopBar";

export type DrawerTab = "preview" | "diagnostics" | "validation" | "plan";

const TABS: { id: DrawerTab; label: string }[] = [
  { id: "preview", label: "Preview" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "validation", label: "Validation" },
  { id: "plan", label: "Observation plan" },
];

interface GraphDrawerProps {
  source: ObservationSource;
  graph: UseGraphResult;
  extra: UseGraphExtrapolationResult;
  /** The EFFECTIVE run body (manual = knobs + syntheticObservations) —
   *  backtest + plan ride the same request Run does. */
  body: ExtrapolateBody;
  /** Baseline universe nodes (scenario shortcuts pick their pulse sets). */
  nodes: GraphNodeBase[] | null;
  /** U7 side-by-side LOO state + the mode-forced bodies (shell-built). */
  loo: UseLooComparisonResult;
  looBodies: { smooth: ExtrapolateBody; messages: ExtrapolateBody };
  /** Effective relation rows — the plan's competing-signals annotation. */
  msgRows: MessageEdgeRow[];
  flatAtm: boolean;
  setFlatAtm: (v: boolean) => void;
  selected: { ticker: string; expiry: string } | null;
  onSelect: (ticker: string, expiry: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  tab: DrawerTab;
  setTab: (t: DrawerTab) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
}


export default function GraphDrawer({
  source,
  graph,
  extra,
  body,
  nodes,
  loo,
  looBodies,
  msgRows,
  flatAtm,
  setFlatAtm,
  selected,
  onSelect,
  onOpenSmile,
  tab,
  setTab,
  open,
  setOpen,
}: GraphDrawerProps) {
  const manual = source === "manual";
  const litEntries = Object.entries(graph.lit).sort(([a], [b]) => a.localeCompare(b));

  // Canonical scenario shortcuts (U3): one click replaces the pulse set.
  const scenarioButtons = (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      {SCENARIOS.map((s) => {
        const entries = nodes === null ? null : buildScenario(s.id, nodes);
        return (
          <button
            key={s.id}
            disabled={entries === null}
            onClick={() => {
              if (entries !== null) graph.replaceLit(entries);
            }}
            title={
              s.description +
              (entries === null ? " (the selected universe cannot host this scenario)" : "")
            }
            className="rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[10px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {s.label}
          </button>
        );
      })}
      <span
        className="text-[9px] text-slate-600"
        title="Competing signals resolve by precision-weighted averaging: the receiver's mean can cancel while its incoming confidence ADDS (q = Σp) — disagreement never reads as ignorance (§21.2/§21.3)."
      >
        ⓘ competing signals average · confidences add
      </span>
    </div>
  );

  const preview = manual ? (
    <>
      <p className="mb-2 text-[11px] text-slate-500">
        Test pulse — typed shifts run the ACTIVE operator over the selected
        universe on transported-prior baselines.{" "}
        <span className="text-slate-400">Nothing is persisted.</span>
      </p>
      {scenarioButtons}
      {litEntries.length === 0 ? (
        <p className="py-2 text-xs text-slate-500">
          No pulses — click nodes in the graph or use a scenario shortcut.
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
      )}
    </>
  ) : (
    <div className="space-y-2 text-xs text-slate-400">
      <p className="text-slate-500">
        Lit nodes' calibrated moves vs their transported priors drive the field
        — {litEntries.length} lit observation{litEntries.length === 1 ? "" : "s"}.
      </p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={flatAtm}
          onChange={(e) => setFlatAtm(e.target.checked)}
          className="accent-accent-500"
        />
        Flat baselines (diagnostic)
      </label>
    </div>
  );

  // One solve, one table (U3): both sources read the production field.
  const diagnostics = (
    <div className="flex h-full min-h-0 flex-col">
      {extra.cycles.length > 0 && (
        <p
          className="mb-2 shrink-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300"
          title="Cycles whose beta product differs from 1 — an internally inconsistent edge configuration (spec §16.4)"
        >
          ⚠ {extra.cycles.length} inconsistent beta cycle
          {extra.cycles.length > 1 ? "s" : ""} · worst product{" "}
          {extra.cycles
            .reduce((m, c) => Math.max(m, Math.abs(c.betaProduct)), 0)
            .toFixed(2)}
        </p>
      )}
      <ExtrapolateResults
        extra={extra}
        selected={selected}
        onSelect={onSelect}
        onOpenSmile={onOpenSmile}
      />
    </div>
  );

  const validation = (
    <ValidationTab
      manual={manual}
      loo={loo}
      smoothBody={looBodies.smooth}
      messagesBody={looBodies.messages}
    />
  );

  // The plan rides the same body as Run (what-if pulses included, U3); U7
  // annotates each candidate with WHY it is valuable.
  const messagesOperator = graph.params.propagationMode === "precision_messages";
  const plan =
    extra.nodes === null ? (
      <p className="py-2 text-xs text-slate-500">
        Run first — the ranking reads the solved posterior.
      </p>
    ) : (
      <ObservationPlanCard
        body={body}
        onOpenSmile={onOpenSmile}
        annotate={(ticker, expiry) =>
          planAnnotations(
            { ticker, expiry }, extra.nodes, msgRows, graph.params, messagesOperator,
          )
        }
      />
    );

  const content: Record<DrawerTab, React.ReactNode> = {
    preview,
    diagnostics,
    validation,
    plan,
  };

  return (
    <div className="shrink-0 rounded-xl border border-slate-800 bg-surface-900 shadow-xl shadow-black/30">
      <div className="flex items-center gap-1 px-2 pt-1.5">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              // Re-clicking the active tab collapses the drawer.
              if (tab === t.id && open) setOpen(false);
              else {
                setTab(t.id);
                setOpen(true);
              }
            }}
            className={`rounded-t-md px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.id && open
                ? "bg-surface-800 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t.label}
          </button>
        ))}
        <button
          onClick={() => setOpen(!open)}
          title={open ? "Collapse drawer" : "Expand drawer"}
          className="ml-auto px-2 py-1 text-xs text-slate-500 transition-colors hover:text-slate-300"
        >
          {open ? "▾" : "▴"}
        </button>
      </div>
      {open && <div className="h-52 overflow-y-auto border-t border-slate-800 px-4 py-2">{content[tab]}</div>}
    </div>
  );
}
