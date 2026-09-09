/**
 * Deep links into the workbench: `/?node=TICKER|YYYY-MM-DD&activity=parametric`.
 *
 * The MCP connector's chart apps (backend/volfit_mcp/ui) carry a "Workbench"
 * button that opens the node the chat is looking at in the app, in the lens
 * that drew it (parametric for a smile / surface / term structure, localvol
 * for the LV compare). The hook reads the query once on mount, opens the node
 * through the workbench (which also switches the activity), then strips the
 * query from the address bar so a refresh does not re-open it.
 */
import { useEffect } from "react";
import { useWorkbench } from "./workbench";
import { ACTIVITIES, type Activity } from "./workbenchPersist";
import type { NodeRef } from "../lib/workbenchTabs";

export interface DeepLink {
  node: NodeRef;
  activity?: Activity;
}

const NODE_RE = /^([A-Za-z0-9^_.:\- ]{1,20})\|(\d{4}-\d{2}-\d{2})$/;

/** Parse a `location.search` string; null when it carries no valid node. */
export function parseDeepLink(search: string): DeepLink | null {
  const params = new URLSearchParams(search);
  const node = params.get("node");
  if (!node) return null;
  const m = NODE_RE.exec(node.trim());
  if (!m) return null;
  const activityRaw = params.get("activity");
  const activity = ACTIVITIES.find((a) => a.id === activityRaw)?.id;
  return { node: { ticker: m[1].trim().toUpperCase(), expiry: m[2] }, activity };
}

/** Strip `node` / `activity` from the address bar (history.replaceState). */
export function stripDeepLink(): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has("node") && !url.searchParams.has("activity")) return;
  url.searchParams.delete("node");
  url.searchParams.delete("activity");
  window.history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
}

export function useDeepLink(): void {
  const { openNode } = useWorkbench();
  useEffect(() => {
    const link = parseDeepLink(window.location.search);
    if (!link) return;
    openNode(link.node, { activity: link.activity });
    stripDeepLink();
    // Mount-only by design: the query is consumed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
