// The graph shell's topology + config loader (extracted from GraphViewer at
// the file-size cap; P5b U6 adds the lifecycle awareness).
//
// Smooth field: persisted per-edge overrides, else the auto-lattice the
// solver would build. Message mode: the U6 config pair is fetched and the
// RUN slot's rows (active, or draft under the run-draft toggle) drive the
// display — falling back to the auto relations when the slot is empty —
// mapped into the chart's stored-edge convention (from = receiver, to =
// informer) so the information-flow arrows stay honest.
import { useCallback, useEffect, useState } from "react";
import { useGraphEdges } from "./useGraphEdges";
import {
  fetchMessageConfig as defaultFetchConfig,
  type MessageConfigPair,
} from "./useMessageConfig";
import { useMessageEdges, type MessageEdgeRow } from "./useMessageEdges";
import type { LayoutEdgeIn } from "../lib/graphLayout";

export interface GraphTopologyResult {
  /** Chart topology (display; the solver builds its own). */
  edges: LayoutEdgeIn[];
  /** EFFECTIVE relation rows (run slot else auto) — the message inspector. */
  msgRows: MessageEdgeRow[];
  /** The run slot's rows only (no auto fallback) — matrix provenance. */
  persistedRows: MessageEdgeRow[];
  /** The U6 lifecycle pair (fetched in every mode — the config chip). */
  config: MessageConfigPair | null;
  /** Re-fetch (editor save, activate/revert). */
  refresh: () => void;
}

export function useGraphTopology(
  messagesMode: boolean,
  runDraft: boolean,
): GraphTopologyResult {
  const { fetchEdges, fetchLattice } = useGraphEdges();
  const { fetchAuto: fetchMsgAuto } = useMessageEdges();
  const [edges, setEdges] = useState<LayoutEdgeIn[]>([]);
  const [msgRows, setMsgRows] = useState<MessageEdgeRow[]>([]);
  const [persistedRows, setPersistedRows] = useState<MessageEdgeRow[]>([]);
  const [config, setConfig] = useState<MessageConfigPair | null>(null);
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    let alive = true;
    const load = async (): Promise<LayoutEdgeIn[]> => {
      // The config pair rides every mode: the chip stays live even under
      // the smooth field (older backends 404 → chip degrades, harmless).
      const pair = await defaultFetchConfig().catch(() => null);
      if (alive) setConfig(pair);
      if (messagesMode) {
        const slot = runDraft ? pair?.draft : pair?.active;
        const persisted = slot?.rows ?? [];
        if (alive) setPersistedRows(persisted);
        const rows = persisted.length > 0 ? persisted : await fetchMsgAuto();
        if (alive) setMsgRows(rows);
        return rows.map((r) => ({
          fromTicker: r.targetTicker,
          fromExpiry: r.targetExpiry,
          toTicker: r.sourceTicker,
          toExpiry: r.sourceExpiry,
          weight: r.messagePrecision,
        }));
      }
      if (alive) {
        setPersistedRows([]);
        setMsgRows([]);
      }
      const e = await fetchEdges().then((x) => (x.length > 0 ? x : fetchLattice()));
      return e.map((r) => ({
        fromTicker: r.fromTicker,
        fromExpiry: r.fromExpiry,
        toTicker: r.toTicker,
        toExpiry: r.toExpiry,
        weight: r.weight,
      }));
    };
    load()
      .then((e) => {
        if (alive) setEdges(e);
      })
      .catch(() => {
        /* topology is display-only; the solver builds its own — keep last */
      });
    return () => {
      alive = false;
    };
  }, [fetchEdges, fetchLattice, fetchMsgAuto, messagesMode, runDraft, version]);

  return { edges, msgRows, persistedRows, config, refresh };
}
