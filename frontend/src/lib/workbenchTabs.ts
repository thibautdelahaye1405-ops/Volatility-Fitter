// Pure tab algebra for the workbench shell (UI SHELL v2, S1).
//
// The main pane shows ONE TAB PER NODE (ticker, expiry). Tabs follow the VS
// Code grammar: a single click on a node opens a PREVIEW tab (italic, reused
// by the next preview); a double click, an edit or an explicit pin turns it
// into a pinned tab that stays until closed. Every function here is pure
// (state in, state out) so the behaviour is unit-locked in workbenchTabs.test
// and the React provider (state/workbench.tsx) stays a thin shell.

/** Identity of a smile node. */
export interface NodeRef {
  ticker: string;
  expiry: string;
}

/** One open tab. `preview` tabs are replaced by the next preview open. */
export interface WorkbenchTab extends NodeRef {
  /** Canonical key "TICKER|YYYY-MM-DD" (the React key + identity). */
  key: string;
  preview: boolean;
}

export interface TabsState {
  tabs: WorkbenchTab[];
  /** Key of the active tab, or null when nothing is open. */
  activeKey: string | null;
}

export const EMPTY_TABS: TabsState = { tabs: [], activeKey: null };

/** Canonical map key for a node (matches useGraph.nodeKey). */
export function tabKey(ticker: string, expiry: string): string {
  return `${ticker}|${expiry}`;
}

/** Parse a tab key back into its node ("" parts on a malformed key). */
export function parseTabKey(key: string): NodeRef {
  const [ticker = "", expiry = ""] = key.split("|");
  return { ticker, expiry };
}

/** The active tab, or null. */
export function activeTab(state: TabsState): WorkbenchTab | null {
  return state.tabs.find((t) => t.key === state.activeKey) ?? null;
}

/**
 * Open (or focus) a node. Preview semantics:
 *  - already open → activate it; opening as pinned also pins it;
 *  - preview open + an existing preview tab → REPLACE that tab in place
 *    (keeps the strip stable, exactly like VS Code);
 *  - otherwise insert right after the active tab (or append).
 */
export function openTab(
  state: TabsState,
  node: NodeRef,
  opts: { preview?: boolean } = {},
): TabsState {
  const preview = opts.preview ?? false;
  const key = tabKey(node.ticker, node.expiry);
  const existing = state.tabs.find((t) => t.key === key);
  if (existing) {
    const tabs = preview
      ? state.tabs
      : state.tabs.map((t) => (t.key === key ? { ...t, preview: false } : t));
    return { tabs, activeKey: key };
  }
  const fresh: WorkbenchTab = { ...node, key, preview };
  if (preview) {
    const idx = state.tabs.findIndex((t) => t.preview);
    if (idx >= 0) {
      const tabs = state.tabs.slice();
      tabs[idx] = fresh;
      return { tabs, activeKey: key };
    }
  }
  const at = state.tabs.findIndex((t) => t.key === state.activeKey);
  const tabs = state.tabs.slice();
  tabs.splice(at >= 0 ? at + 1 : tabs.length, 0, fresh);
  return { tabs, activeKey: key };
}

/** Turn a preview tab into a pinned one (no-op when absent / pinned). */
export function pinTab(state: TabsState, key: string): TabsState {
  if (!state.tabs.some((t) => t.key === key && t.preview)) return state;
  return {
    ...state,
    tabs: state.tabs.map((t) => (t.key === key ? { ...t, preview: false } : t)),
  };
}

/** Close a tab; when it was active, activate its right neighbour (else left). */
export function closeTab(state: TabsState, key: string): TabsState {
  const idx = state.tabs.findIndex((t) => t.key === key);
  if (idx < 0) return state;
  const tabs = state.tabs.filter((t) => t.key !== key);
  if (state.activeKey !== key) return { tabs, activeKey: state.activeKey };
  const next = tabs[idx] ?? tabs[idx - 1] ?? null;
  return { tabs, activeKey: next?.key ?? null };
}

/** Close every tab but `key` (VS Code "Close others"). */
export function closeOtherTabs(state: TabsState, key: string): TabsState {
  const keep = state.tabs.find((t) => t.key === key);
  if (!keep) return state;
  return { tabs: [keep], activeKey: key };
}

export function closeAllTabs(): TabsState {
  return EMPTY_TABS;
}

/** Activate a tab by key (no-op when absent). */
export function activateTab(state: TabsState, key: string): TabsState {
  return state.tabs.some((t) => t.key === key) ? { ...state, activeKey: key } : state;
}

/** Cycle the active tab by `delta` (±1), wrapping around. */
export function cycleTab(state: TabsState, delta: number): TabsState {
  const n = state.tabs.length;
  if (n === 0) return state;
  const cur = state.tabs.findIndex((t) => t.key === state.activeKey);
  const next = (((cur < 0 ? 0 : cur) + delta) % n + n) % n;
  return { ...state, activeKey: state.tabs[next].key };
}

/** Move a tab to a new index (drag-reorder); keeps the active key. */
export function moveTab(state: TabsState, key: string, toIndex: number): TabsState {
  const from = state.tabs.findIndex((t) => t.key === key);
  if (from < 0) return state;
  const tabs = state.tabs.slice();
  const [tab] = tabs.splice(from, 1);
  const to = Math.max(0, Math.min(tabs.length, toIndex));
  tabs.splice(to, 0, tab);
  return { ...state, tabs };
}

/**
 * Drop tabs whose node is no longer in the universe (a removed ticker or a
 * deselected expiry). `has(ticker, expiry)` is the membership test.
 */
export function pruneTabs(
  state: TabsState,
  has: (ticker: string, expiry: string) => boolean,
): TabsState {
  const tabs = state.tabs.filter((t) => has(t.ticker, t.expiry));
  if (tabs.length === state.tabs.length) return state;
  const activeKey =
    state.activeKey !== null && tabs.some((t) => t.key === state.activeKey)
      ? state.activeKey
      : (tabs[0]?.key ?? null);
  return { tabs, activeKey };
}

/** Validate a persisted blob back into a TabsState (drops malformed rows). */
export function restoreTabs(raw: unknown): TabsState {
  if (typeof raw !== "object" || raw === null) return EMPTY_TABS;
  const r = raw as { tabs?: unknown; activeKey?: unknown };
  if (!Array.isArray(r.tabs)) return EMPTY_TABS;
  const seen = new Set<string>();
  const tabs: WorkbenchTab[] = [];
  for (const t of r.tabs as unknown[]) {
    if (typeof t !== "object" || t === null) continue;
    const { ticker, expiry, preview } = t as Partial<WorkbenchTab>;
    if (typeof ticker !== "string" || typeof expiry !== "string") continue;
    if (ticker === "" || expiry === "") continue;
    const key = tabKey(ticker, expiry);
    if (seen.has(key)) continue;
    seen.add(key);
    tabs.push({ ticker, expiry, key, preview: preview === true });
  }
  const activeKey =
    typeof r.activeKey === "string" && seen.has(r.activeKey)
      ? r.activeKey
      : (tabs[0]?.key ?? null);
  return { tabs, activeKey };
}
