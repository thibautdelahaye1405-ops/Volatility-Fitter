// Node scope of an editor group (UI SHELL v2 wave 3, C3).
//
// Wraps a group's lens and presents the smile session FOR THAT GROUP'S
// ACTIVE TAB: the universe-level parts come from the root session, the node
// parts from useNodeSmile on (ticker, expiry). The FOCUSED group is the root
// selection itself, so its scope delegates (the node hook stays inert — no
// second fetch of the same node). Selection verbs made inside the group
// (setTicker / setExpiry from a lens) open tabs in THIS group. Also exposes
// the group index + tab key (useNodeScope) for per-tab view memory and the
// drop / keyboard routing.
import { createContext, useContext, useMemo } from "react";
import type { ReactNode } from "react";
import { NodeScopeContext, useRootSmileSession } from "./smileSession";
import { useNodeSmile } from "./useNodeSmile";
import { midLadderExpiry } from "./useSmile";
import type { UseSmileResult } from "./useSmile";
import type { NodeRef } from "../lib/workbenchTabs";
import { tabKey } from "../lib/workbenchTabs";

export interface NodeScopeInfo {
  /** Editor group index (0 = left). */
  group: number;
  /** Tab key of the group's active node, or null when the group is empty. */
  key: string | null;
  focused: boolean;
  /** Two groups are showing (lenses hide their asides to keep charts wide). */
  split: boolean;
}

const InfoCtx = createContext<NodeScopeInfo | null>(null);

export function NodeScopeProvider({
  group,
  node,
  focused,
  split,
  openHere,
  children,
}: {
  group: number;
  /** The group's active node (null = empty group: the root session shows). */
  node: NodeRef | null;
  focused: boolean;
  split: boolean;
  /** Open a node as a preview tab in THIS group (lens-side selections). */
  openHere: (node: NodeRef) => void;
  children: ReactNode;
}) {
  const root = useRootSmileSession();
  const ticker = node?.ticker ?? "";
  const expiry = node?.expiry ?? "";
  // The focused group IS the root selection — read it, do not refetch it.
  const own = !focused && node !== null;
  const scoped = useNodeSmile({
    enabled: own,
    source: root.source, ticker, expiry, fitMode: root.fitMode,
    spotVersion: root.spotVersion, refreshViews: root.refreshViews,
    reloadSignal: root.reloadSignal, regime: root.regime,
    mock: root.source === "mock" ? root.smile : null,
  });

  const value = useMemo<UseSmileResult>(() => {
    if (!own) return root;
    return {
      ...root,
      ...scoped,
      error: root.universe === null ? root.error : scoped.error,
      ticker,
      expiry,
      setTicker: (t: string) => openHere({ ticker: t, expiry: midLadderExpiry(root.universe?.expiries[t] ?? []) }),
      setExpiry: (e: string) => openHere({ ticker, expiry: e }),
    };
  }, [own, root, scoped, ticker, expiry, openHere]);

  const info = useMemo<NodeScopeInfo>(
    () => ({ group, key: node ? tabKey(node.ticker, node.expiry) : null, focused, split }),
    [group, node, focused, split],
  );

  return (
    <InfoCtx.Provider value={info}>
      <NodeScopeContext.Provider value={value}>{children}</NodeScopeContext.Provider>
    </InfoCtx.Provider>
  );
}

/** The enclosing group's identity, or null outside any group. */
export function useNodeScope(): NodeScopeInfo | null {
  return useContext(InfoCtx);
}
