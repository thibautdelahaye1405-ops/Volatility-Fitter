/**
 * Deep links into the workbench: `/?node=TICKER|YYYY-MM-DD&activity=parametric`
 * and, since the SERIES ARC (S4), `&series=<id>&frame=<n>` to open a stored
 * series at a frame on the Series lens.
 *
 * The MCP connector's chart apps (backend/volfit_mcp/ui) carry a "Workbench"
 * button that opens the node the chat is looking at in the app, in the lens
 * that drew it (parametric for a smile / surface / term structure, localvol
 * for the LV compare, series for a replayed frame). The hook reads the query
 * once on mount, parks the series half for the Series lens
 * (state/seriesDeepLink), opens the node through the workbench (which also
 * switches the activity), then strips the query from the address bar so a
 * refresh does not re-open it.
 */
import { useEffect } from "react";
import { useWorkbench } from "./workbench";
import { ACTIVITIES, type Activity } from "./workbenchPersist";
import { setPendingSeriesLink } from "./seriesDeepLink";
import type { SeriesLink } from "./seriesDeepLink";
import type { NodeRef } from "../lib/workbenchTabs";

export interface DeepLink {
  node: NodeRef;
  activity?: Activity;
  /** A stored series to select on the Series lens, optionally at a frame. */
  series?: SeriesLink;
}

const NODE_RE = /^([A-Za-z0-9^_.:\- ]{1,20})\|(\d{4}-\d{2}-\d{2})$/;
const SERIES_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,79}$/;
/** Every query key a deep link may carry (all stripped together). */
const PARAMS = ["node", "activity", "series", "frame"] as const;

function parseSeries(id: string | null, frame: string | null): SeriesLink | undefined {
  const s = id?.trim() ?? "";
  if (!SERIES_ID_RE.test(s)) return undefined;
  const link: SeriesLink = { id: s };
  const f = frame?.trim() ?? "";
  if (/^\d{1,6}$/.test(f)) link.frame = Number(f);
  return link;
}

/** Parse a `location.search` string; null when it carries no valid node.
 *  A series link without an explicit activity lands on the Series lens. */
export function parseDeepLink(search: string): DeepLink | null {
  const params = new URLSearchParams(search);
  const node = params.get("node");
  if (!node) return null;
  const m = NODE_RE.exec(node.trim());
  if (!m) return null;
  const series = parseSeries(params.get("series"), params.get("frame"));
  const activityRaw = params.get("activity");
  const activity = ACTIVITIES.find((a) => a.id === activityRaw)?.id ?? (series ? "series" : undefined);
  const link: DeepLink = { node: { ticker: m[1].trim().toUpperCase(), expiry: m[2] }, activity };
  if (series) link.series = series;
  return link;
}

/** Strip the deep-link params from the address bar (history.replaceState). */
export function stripDeepLink(): void {
  const url = new URL(window.location.href);
  if (!PARAMS.some((p) => url.searchParams.has(p))) return;
  for (const p of PARAMS) url.searchParams.delete(p);
  window.history.replaceState(null, "", url.pathname + (url.search || "") + url.hash);
}

export function useDeepLink(): void {
  const { openNode } = useWorkbench();
  useEffect(() => {
    const link = parseDeepLink(window.location.search);
    if (!link) return;
    if (link.series) setPendingSeriesLink(link.series);
    openNode(link.node, { activity: link.activity });
    stripDeepLink();
    // Mount-only by design: the query is consumed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
