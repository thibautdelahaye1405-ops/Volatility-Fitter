// Precision-message edge rules (message arc P5): the message editor's data
// layer. Schema v2 with UNAMBIGUOUS direction — the SOURCE (informer)
// predicts the TARGET (receiver); note this inverts the legacy GraphEdge
// reading, where the engine treats `to` as informing `from`.
// GET /graph/edges/messages (persisted), GET /graph/edges/messages/auto (the
// auto relations to seed from), PUT /graph/edges/messages (replace; empty ⇒
// back to auto).
import { useCallback } from "react";
import { api } from "./api";

export type RelationClass =
  | "calendar"
  | "broad_index"
  | "sector_etf"
  | "sector_peer"
  | "custom";

export type PrecisionRule = "explicit" | "calendar_distance";

export const RELATION_CLASSES: RelationClass[] = [
  "calendar",
  "broad_index",
  "sector_etf",
  "sector_peer",
  "custom",
];

/** One relation factor: source (informer) → target (receiver). */
export interface MessageEdgeRow {
  sourceTicker: string;
  sourceExpiry: string;
  targetTicker: string;
  targetExpiry: string;
  /** Conditional relation precision p, receiver ATM-vol units (1/vol²). */
  messagePrecision: number;
  betaAtmVol: number;
  betaSkew: number;
  betaCurv: number;
  relationClass: RelationClass;
  /** "calendar_distance" = precision derives from the §9.2 maturity-gap rule
   *  at solve time (inherited); "explicit" locks the entered number. */
  precisionRule: PrecisionRule;
}

interface MessageEdgesResponse {
  edges: MessageEdgeRow[];
}

export interface UseMessageEdgesResult {
  fetchEdges: () => Promise<MessageEdgeRow[]>;
  fetchAuto: () => Promise<MessageEdgeRow[]>;
  putEdges: (edges: MessageEdgeRow[]) => Promise<MessageEdgeRow[]>;
}

export function useMessageEdges(): UseMessageEdgesResult {
  const fetchEdges = useCallback(
    () =>
      api.get<MessageEdgesResponse>("/graph/edges/messages").then((r) => r.edges),
    [],
  );
  const fetchAuto = useCallback(
    () =>
      api
        .get<MessageEdgesResponse>("/graph/edges/messages/auto")
        .then((r) => r.edges),
    [],
  );
  const putEdges = useCallback(
    (edges: MessageEdgeRow[]) =>
      api
        .put<MessageEdgesResponse>("/graph/edges/messages", { body: { edges } })
        .then((r) => r.edges),
    [],
  );
  return { fetchEdges, fetchAuto, putEdges };
}
