// Persisted per-edge graph overrides (plan Phase 7): the edge editor's data layer.
// GET /graph/edges (persisted overrides), GET /graph/edges/lattice (the auto-lattice
// to seed from), PUT /graph/edges (replace; empty ⇒ back to the lattice).
import { useCallback } from "react";
import { api } from "./api";

/** One directed edge: weight (trust) + per-handle beta (amplitude). */
export interface GraphEdge {
  fromTicker: string;
  fromExpiry: string;
  toTicker: string;
  toExpiry: string;
  weight: number;
  betaAtmVol: number;
  betaSkew: number;
  betaCurv: number;
}

interface GraphEdgesResponse {
  edges: GraphEdge[];
}

export interface UseGraphEdgesResult {
  fetchEdges: () => Promise<GraphEdge[]>;
  fetchLattice: () => Promise<GraphEdge[]>;
  putEdges: (edges: GraphEdge[]) => Promise<GraphEdge[]>;
}

export function useGraphEdges(): UseGraphEdgesResult {
  const fetchEdges = useCallback(
    () => api.get<GraphEdgesResponse>("/graph/edges").then((r) => r.edges),
    [],
  );
  const fetchLattice = useCallback(
    () => api.get<GraphEdgesResponse>("/graph/edges/lattice").then((r) => r.edges),
    [],
  );
  const putEdges = useCallback(
    (edges: GraphEdge[]) =>
      api.put<GraphEdgesResponse>("/graph/edges", { body: { edges } }).then((r) => r.edges),
    [],
  );
  return { fetchEdges, fetchLattice, putEdges };
}
