// Graph workspace shell (P5b U0): configuring relationships between markets,
// not tuning a numerical solver. Workflow spine: Configure → Preview → Run →
// Explain → Validate.
//
//   TOP    — observation source + propagation operator, config / preflight
//            chips, Clear, RUN (the single primary action).
//   LEFT   — Relationships pane: calendar / cross-asset cards, per-relation
//            overrides (Edges editors), advanced legacy solver knobs.
//   CENTER — the smile-universe canvas (ticker pods, calendar spines; solve
//            cinematics by real BFS hop + attribution particles). Unchanged.
//   RIGHT  — Inspector: the selected node (facts + exact attribution).
//   BOTTOM — drawer: Preview | Diagnostics | Validation | Observation plan.
// This view requires the live backend (GET /graph/nodes, POST
// /graph/extrapolate — BOTH observation sources ride the production solve
// since P5b U3; the what-if ships syntheticObservations, non-persisting) —
// there is deliberately no mock fallback.
//
// Workbench integration (UI SHELL v2): inside the shell the inspected node IS
// the active tab — a canvas / diagnostics click opens that node's tab
// (preview), the drill-in opens a pinned tab under the Parametric lens with
// the GRAPH overlay focus, and the Relationships pane follows Layout ▸
// Diagnostics aside. Without a provider (tests) the legacy local selection
// state applies unchanged.
import { useMemo, useState } from "react";
import type { GraphEdgeSelection } from "../components/GraphNetworkChart";
import CanvasCard from "../components/graphshell/CanvasCard";
import GraphDrawer, { type DrawerTab } from "../components/graphshell/GraphDrawer";
import GraphTopBar, { type ObservationSource } from "../components/graphshell/GraphTopBar";
import InspectorPane from "../components/graphshell/InspectorPane";
import RelationshipsPane from "../components/graphshell/RelationshipsPane";
import { useGraph, nodeKey, type GraphNodeBase } from "../state/useGraph";
import { useGraphExtrapolation, buildExtrapolateBody } from "../state/useGraphExtrapolation";
import { useGraphTopology } from "../state/useGraphTopology";
import {
  activateMessageConfig,
  revertMessageConfig,
} from "../state/useMessageConfig";
import { useLooComparison } from "../state/useLooComparison";
import { usePreflight } from "../state/usePreflight";
import { useGraphFocus } from "../state/graphFocus";
import { useSmileSession } from "../state/smileSession";
import { useOptionalWorkbench } from "../state/workbench";
import { useGraphCinematics } from "../state/useGraphCinematics";
import { useNodeDrop } from "../state/useNodeDrop";
import OfflineCard from "../components/shell/OfflineCard";


interface GraphViewerProps {
  /** Switch the app to the Smile tab (after this view sets the node). */
  onNavigateToSmile: () => void;
}

export default function GraphViewer({ onNavigateToSmile }: GraphViewerProps) {
  const graph = useGraph();
  const extra = useGraphExtrapolation();
  const { setTicker, setExpiry } = useSmileSession();
  const { setFocus } = useGraphFocus();
  const [source, setSource] = useState<ObservationSource>("calibrations");

  // Calibrations-only solver flags (owned here so the drill-in focus can
  // rebuild the exact request body the shell ran with). runDraft (U6) rides
  // the body so backtest/plan/preflight/drill-in all read the same slot.
  const [flatAtm, setFlatAtm] = useState(false);
  const [crossBeta, setCrossBeta] = useState(1);
  const [runDraft, setRunDraft] = useState(false);
  const extrapolateBody = useMemo(
    () => buildExtrapolateBody(graph.params, flatAtm, crossBeta, runDraft),
    [graph.params, flatAtm, crossBeta, runDraft],
  );

  // Shell state: the inspected node/edge and the bottom drawer. Inside the
  // workbench the inspected node is the active tab (closable via the
  // inspector's × until the tab changes); standalone it is local state.
  const wb = useOptionalWorkbench();
  const [localSelected, setLocalSelected] = useState<{ ticker: string; expiry: string } | null>(null);
  const [hiddenKey, setHiddenKey] = useState<string | null>(null);
  const selected = useMemo<{ ticker: string; expiry: string } | null>(() => {
    if (wb === null) return localSelected;
    const t = wb.activeTab;
    if (t === null || t.key === hiddenKey) return null;
    return { ticker: t.ticker, expiry: t.expiry };
  }, [wb, localSelected, hiddenKey]);
  const showRelationships = wb === null || wb.layout.aside;
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeSelection | null>(null);
  // Bumped by the inspector's "Edit relations" — RelationshipsPane opens the
  // row editor on change.
  const [editorSignal, setEditorSignal] = useState(0);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("preview");
  const [drawerOpen, setDrawerOpen] = useState(true);

  // Topology + U6 config lifecycle (state/useGraphTopology): the chart edges,
  // the effective relation rows (inspector), the run slot's persisted rows
  // (matrix provenance) and the config pair (chip). Layered mode reuses the
  // message-relation config wholesale (framework §9.3: reciprocal relations
  // ARE message factors), so every message surface treats it as message-family.
  const messagesMode = graph.params.propagationMode !== "smooth_field";
  const topology = useGraphTopology(messagesMode, runDraft);
  const { edges, msgRows } = topology;
  const [configBusy, setConfigBusy] = useState(false);

  // With the calibrations source the chart is driven by the production solve:
  // the full SELECTED lit+dark universe (prior handles as the baseline), the
  // calibrated nodes lit (amber ring = an observation), and the posterior
  // field. Before the first Run (extra.nodes null) it falls back to the
  // baseline universe so the chart is never blank.
  const extraChartNodes = useMemo<GraphNodeBase[] | null>(
    () =>
      extra.nodes === null
        ? null
        : extra.nodes.map((n) => ({
            ticker: n.ticker,
            expiry: n.expiry,
            t: n.t,
            atmVol: n.priorAtmVol,
            skew: n.priorSkew,
            curvature: n.priorCurv,
            lit: n.lit,
          })),
    [extra.nodes],
  );
  const extraChartLit = useMemo<Record<string, number>>(
    () =>
      extra.nodes === null
        ? {}
        : Object.fromEntries(
            extra.nodes
              .filter((n) => n.calibrated)
              .map((n) => [nodeKey(n.ticker, n.expiry), 0]),
          ),
    [extra.nodes],
  );

  const manual = source === "manual";
  // U3 unification: BOTH sources render the production field. In manual the
  // lit set stays the EDITABLE pulse set (rings follow the current edits,
  // which may differ from the last run).
  const extrapolating = extraChartNodes !== null;
  const chartNodes = extrapolating ? extraChartNodes : graph.nodes;
  const chartLit = manual ? graph.lit : extrapolating ? extraChartLit : {};
  const chartResults = extra.results;

  // Solve cinematics (BFS-hop reveal, wave epoch, attribution particles).
  const cine = useGraphCinematics(chartNodes, edges, chartLit, extra.nodes, manual, extrapolateBody);
  const { waveEpoch, particles } = cine;

  /** Drill into a node's smile: point the shared session at it, then jump.
   *  With the calibrations source also set the graph-extrapolation focus so
   *  the Smile viewer overlays this node's reconstructed smile + band. */
  const openSmile = (ticker: string, expiry: string) => {
    if (wb !== null) {
      wb.openNode({ ticker, expiry }, { activity: "parametric" }); // pinned tab
    } else {
      setTicker(ticker); // also picks a default expiry on the ladder…
      setExpiry(expiry); // …which this immediately overrides with the node's
    }
    setFocus(manual ? null : { ticker, expiry, body: extrapolateBody });
    onNavigateToSmile();
  };

  /** Row / canvas selection for the Inspector: opens the node's tab (preview)
   *  in the workbench; standalone, a re-click deselects. */
  const selectNode = (ticker: string, expiry: string) => {
    if (wb !== null) {
      setHiddenKey(null);
      wb.openNode({ ticker, expiry }, { preview: true });
      return;
    }
    setLocalSelected((prev) =>
      prev !== null && prev.ticker === ticker && prev.expiry === expiry
        ? null
        : { ticker, expiry },
    );
  };
  /** Inspector ×: hide the inspection (workbench: until the tab changes). */
  const closeInspector = () => {
    if (wb !== null) setHiddenKey(wb.activeTab?.key ?? null);
    else setLocalSelected(null);
  };
  // Drop from the Nodes pane (wave 3, C5): light / pulse (state/useNodeDrop).
  const onNodeDrop = useNodeDrop(graph, manual);
  /** Canvas single-click: manual lights/dims; calibrations inspects. */
  const onChartToggle = (key: string) => {
    if (manual) {
      graph.toggleLit(key);
      return;
    }
    const [ticker = "", expiry = ""] = key.split("|");
    if (ticker !== "" && expiry !== "") selectNode(ticker, expiry);
  };

  // The effective run body (U3 unification): manual what-if ships the typed
  // pulse set as syntheticObservations on the PRODUCTION request — selected
  // universe, transported-prior baselines, ACTIVE operator, non-persisting.
  const syntheticObservations = useMemo(
    () =>
      Object.entries(graph.lit).map(([key, dAtmVol]) => {
        const [ticker = "", expiry = ""] = key.split("|");
        return { ticker, expiry, dAtmVol };
      }),
    [graph.lit],
  );
  const runBody = useMemo(
    () => (manual ? { ...extrapolateBody, syntheticObservations } : extrapolateBody),
    [manual, extrapolateBody, syntheticObservations],
  );

  // Live pre-run diagnostics (U5) on the SAME body Run ships; blockers gate
  // Run (fail-open when no report — advisory infra, never a hard dependency).
  const preflight = usePreflight(runBody);

  // U7 side-by-side LOO: mode-forced bodies from the SAME live knobs (only
  // the operator differs; run-draft applies to the message column only).
  const loo = useLooComparison();
  const looBodies = useMemo(
    () => ({
      smooth: buildExtrapolateBody(
        { ...graph.params, propagationMode: "smooth_field" }, flatAtm, crossBeta,
      ),
      messages: buildExtrapolateBody(
        { ...graph.params, propagationMode: "precision_messages" },
        flatAtm, crossBeta, runDraft,
      ),
    }),
    [graph.params, flatAtm, crossBeta, runDraft],
  );

  // Run routing: one solve either way. After the attempt, reveal Diagnostics
  // (errors surface in the top bar).
  const litCount0 = Object.keys(graph.lit).length;
  const canRun =
    (manual ? litCount0 > 0 : true) && preflight.report?.ok !== false;
  const busy = extra.running;
  const run = async () => {
    if (manual && litCount0 === 0) return;
    await extra.run(runBody);
    setDrawerTab("diagnostics");
    setDrawerOpen(true);
  };
  const clearField = () => extra.clear();
  const runError = extra.error;
  const hasResults = extra.nodes !== null;

  /** Relation-editor save (stages the DRAFT since U6): refresh the displayed
   *  topology/config and re-run — the field only changes when the run slot
   *  (active, or draft under run-draft) actually moved. */
  const onEdgesSaved = () => {
    topology.refresh();
    if (!manual) void extra.run(runBody);
  };

  /** U6 lifecycle action wrapper: activate/revert, then refresh + re-solve. */
  const lifecycle = async (fn: () => Promise<unknown>) => {
    setConfigBusy(true);
    try {
      await fn();
    } catch {
      /* the chip re-renders from the refresh either way */
    } finally {
      setConfigBusy(false);
      topology.refresh();
      if (!manual) void extra.run(runBody);
    }
  };

  // Inspector data for the selected node (baseline facts + solved posterior).
  const isSel = (n: { ticker: string; expiry: string }) =>
    selected !== null && n.ticker === selected.ticker && n.expiry === selected.expiry;
  const inspectorBase = useMemo(
    () => (chartNodes ?? []).find(isSel) ?? null,
    [selected, chartNodes], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const inspectorPost = useMemo(
    () => (extra.nodes ?? []).find(isSel) ?? null,
    [selected, extra.nodes], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // Summary strip: observed / extrapolated counts + the solve's max |shift|.
  const summary = useMemo(() => {
    if (chartResults === null) return null;
    const all = Object.values(chartResults);
    const observed = all.filter((n) => n.observed).length;
    const maxAbs = all.reduce((m, n) => Math.max(m, Math.abs(n.shiftBp)), 0);
    return { observed, extrapolated: all.length - observed, maxAbs };
  }, [chartResults]);

  // Backend offline (and nothing loaded): centered empty-state card.
  if (graph.error !== null && graph.nodes === null) {
    return (
      <OfflineCard
        title="Graph solver requires the live backend"
        error={graph.error}
        onRetry={graph.reload}
      />
    );
  }

  // Top-bar badges: lit/dark composition of the displayed universe.
  const litCount =
    extrapolating || manual
      ? Object.keys(chartLit).length
      : (chartNodes ?? []).filter((n) => n.lit).length;
  const darkCount = Math.max(0, (chartNodes ?? []).length - litCount);

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <GraphTopBar
        source={source}
        setSource={setSource}
        mode={graph.params.propagationMode}
        setMode={(m) => graph.setParam("propagationMode", m)}
        litCount={litCount}
        darkCount={darkCount}
        preflight={preflight}
        config={{
          config: topology.config,
          runDraft,
          setRunDraft,
          onActivate: (notes) => void lifecycle(() => activateMessageConfig(notes)),
          onRevert: () => void lifecycle(revertMessageConfig),
          busy: configBusy,
        }}
        summary={summary}
        error={runError}
        canRun={canRun}
        busy={busy}
        onRun={() => void run()}
        hasResults={hasResults}
        onClear={clearField}
      />

      <div className="flex min-h-0 flex-1 gap-3">
        {showRelationships && <RelationshipsPane
          graph={graph}
          messages={messagesMode}
          layered={graph.params.propagationMode === "layered_dynamic_harmonic"}
          config={topology.config}
          crossBeta={crossBeta}
          setCrossBeta={setCrossBeta}
          onEdgesSaved={onEdgesSaved}
          openEditorSignal={editorSignal}
          persistedRows={topology.persistedRows}
        />}

        <CanvasCard
          loading={(graph.loading || graph.nodes === null) && !extrapolating}
          nodes={chartNodes ?? []}
          edges={edges}
          lit={chartLit}
          results={chartResults}
          onToggle={onChartToggle}
          onOpenSmile={openSmile}
          wave={cine.wave}
          particles={particles}
          waveEpoch={waveEpoch}
          manual={manual}
          onEdgeClick={setSelectedEdge}
          onNodeDrop={onNodeDrop}
        />

        <InspectorPane
          selected={selected}
          base={inspectorBase}
          post={inspectorPost}
          body={extrapolateBody}
          showAttribution={!manual && extra.nodes !== null}
          manual={manual}
          messages={messagesMode}
          msgRows={msgRows}
          allNodes={extra.nodes}
          params={graph.params}
          selectedEdge={selectedEdge}
          onCloseEdge={() => setSelectedEdge(null)}
          onEditRelations={() => setEditorSignal((v) => v + 1)}
          onClose={closeInspector}
          onOpenSmile={openSmile}
        />
      </div>

      <GraphDrawer
        source={source}
        graph={graph}
        extra={extra}
        body={runBody}
        nodes={graph.nodes}
        loo={loo}
        looBodies={looBodies}
        msgRows={msgRows}
        flatAtm={flatAtm}
        setFlatAtm={setFlatAtm}
        selected={selected}
        onSelect={selectNode}
        onOpenSmile={openSmile}
        tab={drawerTab}
        setTab={setDrawerTab}
        open={drawerOpen}
        setOpen={setDrawerOpen}
      />
    </div>
  );
}
