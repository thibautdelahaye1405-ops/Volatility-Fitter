// Shared "graph extrapolation focus": when the user drills into a node from the
// Graph workspace's Extrapolate mode, this records WHICH node (and the solver
// knobs used) so the Smile workspace can overlay that node's reconstructed
// graph-extrapolated smile + uncertainty band on top of the live quotes
// (plan Phase 5 live overlay). Cleared when drilling in from the manual sandbox.
import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { ExtrapolateBody } from "./useGraphExtrapolation";

/** The node + request knobs to reconstruct via GET /graph/extrapolate/nodes. */
export interface GraphFocus {
  ticker: string;
  expiry: string;
  /** Solver knobs forwarded as query params (eta/kappa/.../flatAtm/crossBeta;
   *  nested objects like the U2 policy overrides ride as JSON strings). */
  body: ExtrapolateBody;
}

interface GraphFocusValue {
  focus: GraphFocus | null;
  setFocus: (focus: GraphFocus | null) => void;
}

const GraphFocusContext = createContext<GraphFocusValue | null>(null);

/** Mount near the app root (inside the smile session); both the Graph and Smile
 *  workspaces consume it. */
export function GraphFocusProvider({ children }: { children: ReactNode }) {
  const [focus, setFocus] = useState<GraphFocus | null>(null);
  const value = useMemo(() => ({ focus, setFocus }), [focus]);
  return <GraphFocusContext.Provider value={value}>{children}</GraphFocusContext.Provider>;
}

/** Consume the shared graph-extrapolation focus; throws outside the provider. */
export function useGraphFocus(): GraphFocusValue {
  const ctx = useContext(GraphFocusContext);
  if (ctx === null) {
    throw new Error("useGraphFocus must be used within a GraphFocusProvider");
  }
  return ctx;
}
