// Graph workspace shell (P5b U0 → GRAPH ERGONOMICS ARC, E6): configuring
// relationships between markets, not tuning a numerical solver. TOP = source,
// operator (Layered | Precision), config pill (Apply / Discard), preflight,
// Live, RUN; LEFT = the three-level PolicyPane; CENTER = the canvas (arrows:
// width = confidence, colour = β; click / Connect / collapse / Focus); RIGHT =
// the inspector (relation sliders or node); BOTTOM = the drawer (Relations |
// Preview | Diagnostics | Validation | Plan).
// "What you see is what runs": edits stage the DRAFT at once (useRelationDraft)
// and Run solves it while it differs from the active config; Live re-solves
// as a non-persisting preview. Live backend only. Workbench: the inspected
// node IS the active tab; the pane follows Layout ▸ Diagnostics aside.
import { useCallback, useMemo, useState } from "react";
import MessageEdgeEditor from "../components/MessageEdgeEditor";
import type { GraphEdgeSelection } from "../components/GraphNetworkChart";
import CanvasCard from "../components/graphshell/CanvasCard";
import GraphDrawer, { type DrawerTab } from "../components/graphshell/GraphDrawer";
import GraphTopBar, { type ObservationSource } from "../components/graphshell/GraphTopBar";
import InspectorPane from "../components/graphshell/InspectorPane";
import PolicyPane from "../components/graphshell/PolicyPane";
import OfflineCard from "../components/shell/OfflineCard";
import { newRelationRow, relationKey, rowsToLayoutEdges, type NodeRef } from "../lib/relationRows";
import { useGraph, type GraphNodeBase } from "../state/useGraph";
import { useGraphChartData } from "../state/useGraphChartData";
import { useGraphCinematics } from "../state/useGraphCinematics";
import { buildExtrapolateBody, useGraphExtrapolation } from "../state/useGraphExtrapolation";
import { useGraphFocus } from "../state/graphFocus";
import { useGraphHotkeys } from "../state/useGraphHotkeys";
import { useGraphTopology } from "../state/useGraphTopology";
import { useLivePreview } from "../state/useLivePreview";
import { useLooComparison } from "../state/useLooComparison";
import { activateMessageConfig, configDirty, revertMessageConfig } from "../state/useMessageConfig";
import { useNodeDrop } from "../state/useNodeDrop";
import { usePreflight } from "../state/usePreflight";
import { useRelationDraft } from "../state/useRelationDraft";
import { useSmileSession } from "../state/smileSession";
import { useOptionalWorkbench } from "../state/workbench";

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
  const manual = source === "manual";
  const mode = graph.params.propagationMode;
  const messagesMode = mode !== "smooth_field";
  const layered = mode === "layered_dynamic_harmonic";

  // Calibrations-only solver flags + the units lens (shared by pane + inspector).
  const [flatAtm, setFlatAtm] = useState(false);
  const [crossBeta, setCrossBeta] = useState(1);
  const [raw, setRaw] = useState(false);
  const [live, setLive] = useState(false);
  const [focused, setFocused] = useState(false);

  // Topology (config pair + legacy lattice) and the relation DRAFT on screen.
  const topology = useGraphTopology(messagesMode, false);
  const draft = useRelationDraft({ enabled: messagesMode, onPersisted: topology.refresh });
  const runDraft = messagesMode && configDirty(topology.config); // what you see is what runs
  const edges = useMemo(
    () => (messagesMode ? rowsToLayoutEdges(draft.rows) : topology.edges),
    [messagesMode, draft.rows, topology.edges],
  );
  const msgRows = messagesMode ? draft.rows : [];
  const extrapolateBody = useMemo(
    () => buildExtrapolateBody(graph.params, flatAtm, crossBeta, runDraft),
    [graph.params, flatAtm, crossBeta, runDraft],
  );
  const [configBusy, setConfigBusy] = useState(false);
  const [fullEditor, setFullEditor] = useState(false);

  // Shell selection: the inspected node (workbench: the active tab) and the
  // selected relation / pair (canvas arrow, Relations row, bundle).
  const wb = useOptionalWorkbench();
  const [localSelected, setLocalSelected] = useState<{ ticker: string; expiry: string } | null>(null);
  const [hiddenKey, setHiddenKey] = useState<string | null>(null);
  const selected = useMemo<{ ticker: string; expiry: string } | null>(() => {
    if (wb === null) return localSelected;
    const t = wb.activeTab;
    if (t === null || t.key === hiddenKey) return null;
    return { ticker: t.ticker, expiry: t.expiry };
  }, [wb, localSelected, hiddenKey]);
  const showPane = (wb === null || wb.layout.aside) && !focused;
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeSelection | null>(null);
  const selectedRelationKey = selectedEdge?.kind === "relation" ? selectedEdge.key : null;
  const selectedRow = selectedRelationKey !== null ? (draft.byKey(selectedRelationKey) ?? null) : null;
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("preview");
  const [drawerOpen, setDrawerOpen] = useState(true);
  const openRelations = () => {
    setDrawerTab("relations");
    setDrawerOpen(true);
  };
  const selectRelation = useCallback((key: string) => setSelectedEdge({ kind: "relation", key }), []);

  // Chart data + cinematics.
  const chart = useGraphChartData(graph, extra, manual);
  const { chartNodes, chartLit, chartResults } = chart;
  const cine = useGraphCinematics(chartNodes, edges, chartLit, extra.nodes, manual, extrapolateBody);
  const tOf = useCallback(
    (ticker: string, expiry: string) =>
      (chartNodes ?? []).find((n) => n.ticker === ticker && n.expiry === expiry)?.t,
    [chartNodes],
  );
  const universeNodes = useMemo<NodeRef[]>(
    () => (graph.nodes ?? []).map((n) => ({ ticker: n.ticker, expiry: n.expiry })),
    [graph.nodes],
  );

  /** Drill into a node's smile (pinned Parametric tab + GRAPH overlay focus). */
  const openSmile = (ticker: string, expiry: string) => {
    if (wb !== null) wb.openNode({ ticker, expiry }, { activity: "parametric" });
    else {
      setTicker(ticker);
      setExpiry(expiry);
    }
    setFocus(manual ? null : { ticker, expiry, body: extrapolateBody });
    onNavigateToSmile();
  };
  /** Row / canvas selection for the Inspector (workbench: a preview tab). */
  const selectNode = (ticker: string, expiry: string) => {
    if (wb !== null) {
      setHiddenKey(null);
      wb.openNode({ ticker, expiry }, { preview: true });
      return;
    }
    setLocalSelected((prev) =>
      prev !== null && prev.ticker === ticker && prev.expiry === expiry ? null : { ticker, expiry },
    );
  };
  const closeInspector = () => {
    if (wb !== null) setHiddenKey(wb.activeTab?.key ?? null);
    else setLocalSelected(null);
  };
  const onNodeDrop = useNodeDrop(graph, manual);
  const onChartToggle = (key: string) => {
    if (manual) {
      graph.toggleLit(key);
      return;
    }
    const [ticker = "", expiry = ""] = key.split("|");
    if (ticker !== "" && expiry !== "") selectNode(ticker, expiry);
  };
  /** Connect gesture: informer → receiver becomes a draft row, then selected. */
  const onConnect = useCallback(
    (sourceRef: NodeRef, target: NodeRef) => {
      const row = newRelationRow(sourceRef, target, {
        calPrecision: graph.params.calPrecision,
        crossPrecision: graph.params.crossPrecision,
      });
      if (row === null) return;
      draft.add(row);
      selectRelation(relationKey(row));
    },
    [draft, graph.params.calPrecision, graph.params.crossPrecision, selectRelation],
  );

  // The effective run body (U3): the what-if ships typed pulses as
  // syntheticObservations on the production request (non-persisting).
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
  const preflight = usePreflight(runBody);
  const loo = useLooComparison();
  const looBodies = useMemo(
    () => ({
      smooth: buildExtrapolateBody({ ...graph.params, propagationMode: "smooth_field" }, flatAtm, crossBeta),
      messages: buildExtrapolateBody({ ...graph.params, propagationMode: "precision_messages" }, flatAtm, crossBeta, runDraft),
    }),
    [graph.params, flatAtm, crossBeta, runDraft],
  );

  const litCount0 = Object.keys(graph.lit).length;
  const canRun = (manual ? litCount0 > 0 : true) && preflight.report?.ok !== false;
  const run = async () => {
    if (manual && litCount0 === 0) return;
    await extra.run(runBody);
    setDrawerTab("diagnostics");
    setDrawerOpen(true);
  };
  const rerun = () => {
    if (!manual) void extra.run(live ? { ...runBody, preview: true } : runBody);
  };
  useLivePreview({ live, enabled: canRun && !extra.running, body: runBody, run: extra.run });

  /** Legacy-matrix / policy save: refresh topology + draft, re-solve. */
  const onEdgesSaved = () => {
    topology.refresh();
    draft.reload();
    rerun();
  };
  /** Apply / Discard: activate or revert, then refresh + re-solve. */
  const lifecycle = async (fn: () => Promise<unknown>) => {
    setConfigBusy(true);
    try {
      await fn();
    } catch {
      /* the pill re-renders from the refresh either way */
    } finally {
      setConfigBusy(false);
      topology.refresh();
      draft.reload();
      rerun();
    }
  };

  // Keyboard: Delete removes the selected relation, Esc clears / unfocuses,
  // Ctrl+Z / Ctrl+Y undo / redo the draft.
  useGraphHotkeys({
    enabled: messagesMode,
    onDelete: useCallback(() => {
      if (selectedRelationKey === null) return;
      draft.remove(selectedRelationKey);
      setSelectedEdge(null);
    }, [draft, selectedRelationKey]),
    onEscape: useCallback(() => {
      if (selectedEdge !== null) setSelectedEdge(null);
      else if (focused) setFocused(false);
    }, [selectedEdge, focused]),
    onUndo: draft.undo,
    onRedo: draft.redo,
  });

  const isSel = (n: { ticker: string; expiry: string }) =>
    selected !== null && n.ticker === selected.ticker && n.expiry === selected.expiry;
  const inspectorBase = useMemo<GraphNodeBase | null>(
    () => (chartNodes ?? []).find(isSel) ?? null,
    [selected, chartNodes], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const inspectorPost = useMemo(
    () => (extra.nodes ?? []).find(isSel) ?? null,
    [selected, extra.nodes], // eslint-disable-line react-hooks/exhaustive-deps
  );

  if (graph.error !== null && graph.nodes === null) {
    return <OfflineCard title="Graph solver requires the live backend" error={graph.error} onRetry={graph.reload} />;
  }

  return (
    <div className="flex h-full flex-col gap-3 p-3">
      <GraphTopBar
        source={source}
        setSource={setSource}
        mode={mode}
        setMode={(m) => graph.setParam("propagationMode", m)}
        litCount={chart.litCount}
        darkCount={chart.darkCount}
        preflight={preflight}
        config={{
          config: topology.config,
          saving: draft.saving,
          onActivate: (notes) => void lifecycle(() => activateMessageConfig(notes)),
          onRevert: () => void lifecycle(revertMessageConfig),
          busy: configBusy,
        }}
        summary={chart.summary}
        previewField={extra.preview}
        live={live}
        setLive={setLive}
        error={extra.error}
        canRun={canRun}
        busy={extra.running}
        onRun={() => void run()}
        hasResults={extra.nodes !== null}
        onClear={extra.clear}
      />

      <div className="flex min-h-0 flex-1 gap-3">
        {showPane && (
          <PolicyPane
            graph={graph}
            mode={mode}
            setMode={(m) => graph.setParam("propagationMode", m)}
            config={topology.config}
            onSaved={onEdgesSaved}
            crossBeta={crossBeta}
            setCrossBeta={setCrossBeta}
            rows={msgRows}
            onOpenRelations={openRelations}
            raw={raw}
            setRaw={setRaw}
          />
        )}

        <CanvasCard
          loading={(graph.loading || graph.nodes === null) && !chart.extrapolating}
          nodes={chartNodes ?? []}
          edges={edges}
          lit={chartLit}
          results={chartResults}
          onToggle={onChartToggle}
          onOpenSmile={openSmile}
          wave={cine.wave}
          particles={cine.particles}
          waveEpoch={cine.waveEpoch}
          manual={manual}
          onEdgeClick={setSelectedEdge}
          onNodeDrop={onNodeDrop}
          selectedRelationKey={selectedRelationKey}
          onConnect={messagesMode ? onConnect : undefined}
          focused={focused}
          onToggleFocus={() => setFocused((v) => !v)}
          editable={messagesMode}
        />

        {!focused && (
          <InspectorPane
            selected={selected}
            base={inspectorBase}
            post={inspectorPost}
            body={extrapolateBody}
            showAttribution={!manual && extra.nodes !== null}
            manual={manual}
            messages={messagesMode}
            layered={layered}
            raw={raw}
            msgRows={msgRows}
            allNodes={extra.nodes}
            params={graph.params}
            selectedEdge={selectedEdge}
            relation={selectedRow}
            tOf={tOf}
            onRelationChange={(patch) => selectedRelationKey !== null && draft.update(selectedRelationKey, patch)}
            onRelationFlip={() => {
              if (selectedRelationKey === null) return;
              const nk = draft.flip(selectedRelationKey);
              if (nk !== null) selectRelation(nk);
            }}
            onRelationDelete={() => {
              if (selectedRelationKey === null) return;
              draft.remove(selectedRelationKey);
              setSelectedEdge(null);
            }}
            onSelectRelation={selectRelation}
            onCloseEdge={() => setSelectedEdge(null)}
            onEditRelations={openRelations}
            onClose={closeInspector}
            onOpenSmile={openSmile}
          />
        )}
      </div>

      {!focused && (
        <GraphDrawer
          source={source}
          graph={graph}
          extra={extra}
          body={runBody}
          nodes={graph.nodes}
          loo={loo}
          looBodies={looBodies}
          msgRows={msgRows}
          draft={draft}
          raw={raw}
          selectedRelationKey={selectedRelationKey}
          onSelectRelation={selectRelation}
          universeNodes={universeNodes}
          onOpenFullEditor={() => setFullEditor(true)}
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
      )}

      {/* The §20 full grid (per-handle β + the golden scenario preview);
          its save stages the draft like any other edit. */}
      {fullEditor && (
        <MessageEdgeEditor
          nodes={universeNodes}
          params={graph.params}
          onSaved={onEdgesSaved}
          onClose={() => setFullEditor(false)}
        />
      )}
    </div>
  );
}
