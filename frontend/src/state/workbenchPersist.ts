// Persistence of the workbench shell state (UI SHELL v2, S1 / wave 3 C3):
// activity, editor groups (tabs), layout and per-tab view memory in
// localStorage ("volfit.workbench.v1"), validated on load — a legacy blob
// with a single `tabs` field migrates to one editor group. Split out of
// state/workbench.tsx for the file-size policy.
import { EMPTY_VIEW_MEMORY, pruneViewMemory, restoreViewMemory } from "../lib/workbenchTabs";
import type { ViewMemory } from "../lib/workbenchTabs";
import { EMPTY_GROUPS, allTabs, restoreGroups } from "../lib/editorGroups";
import type { GroupsState } from "../lib/editorGroups";

/** The five activity-bar lenses, in bar order (user spec 2026-08-26). */
export type Activity = "graph" | "forwards" | "parametric" | "localvol" | "quality";

export const ACTIVITIES: { id: Activity; label: string; hint: string }[] = [
  { id: "graph", label: "Graph", hint: "Smile universe — propagate observations through the graph" },
  { id: "forwards", label: "Forwards", hint: "Forwards, dividends & borrow per ticker" },
  { id: "parametric", label: "Parametric", hint: "Per-node parametric smile fit (LQD / SVI-JW / MCS)" },
  { id: "localvol", label: "Local Vol", hint: "Direct local-volatility surface per ticker" },
  { id: "quality", label: "Quality", hint: "Fit-quality dashboard & publish readiness" },
];

export const ACTIVITY_IDS: readonly Activity[] = ACTIVITIES.map((a) => a.id);
export const isActivity = (a: unknown): a is Activity => ACTIVITY_IDS.includes(a as Activity);

/** Lenses that render the whole universe (no tab needed; single group). */
export const UNIVERSE_ACTIVITIES: ReadonlySet<Activity> = new Set(["graph", "quality"]);

export interface LayoutState {
  /** Nodes pane visible (Ctrl+B). */
  nodesPane: boolean;
  /** Nodes pane width in px (resizer; default = 1/5 of the viewport). */
  nodesWidth: number;
  /** Bottom status bar visible. */
  statusBar: boolean;
  /** Diagnostics / config asides inside the lenses. */
  aside: boolean;
  /** Per-tab view memory (wave 3, C2); false = one view state per lens. */
  rememberView: boolean;
}

export const NODES_WIDTH = { min: 200, max: 640 } as const;

/** 1/5 of the viewport (the spec), clamped; SSR-safe fallback. */
export function defaultNodesWidth(): number {
  const w = typeof window !== "undefined" ? window.innerWidth : 1400;
  return Math.max(NODES_WIDTH.min, Math.min(NODES_WIDTH.max, Math.round(w / 5)));
}

export const DEFAULT_LAYOUT: LayoutState = {
  nodesPane: true,
  nodesWidth: defaultNodesWidth(),
  statusBar: true,
  aside: true,
  rememberView: true,
};

const STORAGE_KEY = "volfit.workbench.v1";

export interface Persisted {
  activity: Activity;
  groups: GroupsState;
  layout: LayoutState;
  viewMemory: ViewMemory;
}

/** Lenient layout restore: unknown / malformed fields keep `base`. */
export function restoreLayout(raw: unknown, base: LayoutState): LayoutState {
  const l = (raw ?? {}) as Partial<LayoutState>;
  return {
    nodesPane: typeof l.nodesPane === "boolean" ? l.nodesPane : base.nodesPane,
    nodesWidth: Number.isFinite(l.nodesWidth)
      ? Math.max(NODES_WIDTH.min, Math.min(NODES_WIDTH.max, Number(l.nodesWidth)))
      : base.nodesWidth,
    statusBar: typeof l.statusBar === "boolean" ? l.statusBar : base.statusBar,
    aside: typeof l.aside === "boolean" ? l.aside : base.aside,
    rememberView: typeof l.rememberView === "boolean" ? l.rememberView : base.rememberView,
  };
}

/** Validate any blob (localStorage or a workspace file's shell part). */
export function restorePersisted(raw: unknown, base: Persisted): Persisted {
  const p = (typeof raw === "object" && raw !== null ? raw : {}) as Partial<Persisted> & { tabs?: unknown };
  const groups = p.groups !== undefined || p.tabs !== undefined
    ? restoreGroups(p.groups !== undefined ? { groups: p.groups, focused: (p as { focused?: unknown }).focused } : { tabs: p.tabs }, isActivity)
    : base.groups;
  return {
    activity: isActivity(p.activity) ? p.activity : base.activity,
    groups,
    layout: restoreLayout(p.layout, base.layout),
    viewMemory: pruneViewMemory(restoreViewMemory(p.viewMemory), { tabs: allTabs(groups), activeKey: null }),
  };
}

export function loadPersisted(): Persisted {
  const fallback: Persisted = {
    activity: "parametric", groups: EMPTY_GROUPS, layout: DEFAULT_LAYOUT, viewMemory: EMPTY_VIEW_MEMORY,
  };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? restorePersisted(JSON.parse(raw), fallback) : fallback;
  } catch {
    return fallback;
  }
}

export function persist(p: Persisted): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* best-effort */
  }
}
