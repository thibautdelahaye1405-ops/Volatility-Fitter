// Shared smile session: a single useSmile() instance lifted into React
// context so the data (and the backend fit session it mirrors) survives
// workspace tab switches, and so the TopBar can show real connectivity.
//
// Node SCOPES (UI SHELL v2 wave 3, C3): an editor group wraps its lens in a
// NodeScopeProvider (state/nodeScope) that presents the SAME session shape
// for ITS node (the group's active tab). useSmileSession() prefers the
// nearest scope, so every lens and component keeps calling it unchanged and
// two groups can show two nodes at once; the root session follows the
// focused group.
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { useSmile } from "./useSmile";
import type { UseSmileResult } from "./useSmile";

const SmileSessionContext = createContext<UseSmileResult | null>(null);
/** The scoped session of the enclosing editor group (null at the root). */
export const NodeScopeContext = createContext<UseSmileResult | null>(null);

/** Mount once near the app root; provides the shared smile session. */
export function SmileSessionProvider({ children }: { children: ReactNode }) {
  const session = useSmile();
  return (
    <SmileSessionContext.Provider value={session}>
      {children}
    </SmileSessionContext.Provider>
  );
}

/** Consume the session — the enclosing node scope's when inside an editor
 *  group, else the root; throws outside a SmileSessionProvider. */
export function useSmileSession(): UseSmileResult {
  const scoped = useContext(NodeScopeContext);
  const root = useContext(SmileSessionContext);
  if (scoped !== null) return scoped;
  if (root === null) {
    throw new Error("useSmileSession must be used within SmileSessionProvider");
  }
  return root;
}

/** The ROOT session regardless of scopes (the shell chrome, node scopes). */
export function useRootSmileSession(): UseSmileResult {
  const root = useContext(SmileSessionContext);
  if (root === null) throw new Error("useRootSmileSession must be used within SmileSessionProvider");
  return root;
}
