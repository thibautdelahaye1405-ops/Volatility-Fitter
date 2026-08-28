// Ticker×ticker block-rule data layer for the sparse edge-matrix editor:
// GET/PUT /graph/edges/blocks. A block rule is the compact spec the matrix
// edits — pair rules expand to same-expiry cross-ticker links (both directions
// when symmetric), calendar rules set a ticker's own consecutive-expiry chain
// (the matrix diagonal), and overrides are explicit per-edge rows layered
// last. An all-empty rule falls back to the auto-lattice. The backend reports
// how many concrete edges the rule expands to (expandedCount).
import { useCallback } from "react";
import { api } from "./api";
import type { GraphEdge } from "./useGraphEdges";

/** Same-expiry directed links between two tickers (both ways if symmetric). */
export interface GraphBlockPair {
  a: string;
  b: string;
  weight: number;
  beta: number;
  symmetric: boolean;
  /** Cross-venue asynchronous ladders: also link each rung without an exact
   *  partner to the other ticker's NEAREST expiry within this many calendar
   *  days, at weight × tol/(tol+gap). Absent/null = inherit the solver-level
   *  tolerance (0 by default); 0 = exact-ISO links only for this pair. Only
   *  sent when set, so an untouched rule round-trips exactly as written. */
  crossExpiryToleranceDays?: number | null;
}

/** A ticker's own consecutive-expiry chain weight (the matrix diagonal). */
export interface GraphBlockCalendar {
  ticker: string;
  weight: number;
  beta: number;
}

/** The full block rule; overrides are explicit per-edge rows layered last. */
export interface GraphBlockRule {
  pairs: GraphBlockPair[];
  calendar: GraphBlockCalendar[];
  overrides: GraphEdge[];
}

export interface GraphBlockRuleResponse {
  rule: GraphBlockRule;
  expandedCount: number;
}

export interface UseGraphBlocksResult {
  fetchRule: () => Promise<GraphBlockRuleResponse>;
  putRule: (rule: GraphBlockRule) => Promise<GraphBlockRuleResponse>;
}

export function useGraphBlocks(): UseGraphBlocksResult {
  const fetchRule = useCallback(
    () => api.get<GraphBlockRuleResponse>("/graph/edges/blocks"),
    [],
  );
  const putRule = useCallback(
    (rule: GraphBlockRule) =>
      api.put<GraphBlockRuleResponse>("/graph/edges/blocks", { body: rule }),
    [],
  );
  return { fetchRule, putRule };
}
