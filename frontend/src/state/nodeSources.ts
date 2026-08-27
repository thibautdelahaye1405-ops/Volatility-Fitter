// Per-node data-source policy (UI-ready, NOT active).
//
// STATUS — only mode "universe" is honoured today. The backend runs ONE active
// data source (POST /datasource/{id}; state/useDataSources.ts) and every node
// of the universe fetches from it. The "per-node" mode and the `overrides` map
// are recorded here for the forthcoming multi-source engine (a node or a whole
// ticker pinned to, say, Bloomberg while the rest of the universe stays on
// Massive); they have NO effect on fetches yet. The Manage-universe dialog
// renders the policy so the affordance is discoverable, with the per-node
// controls disabled until the engine lands.
//
// Shape: `overrides` keys are either "TICKER|expiry" (one node) or "TICKER"
// (every expiry of that ticker); values are data-source ids. Resolution order
// for the engine, when it arrives: node key → ticker key → universe source.
//
// Storage: localStorage "volfit.nodeSources.v1", validated on load (a malformed
// or foreign payload falls back to the default policy). A tiny module store +
// useSyncExternalStore keeps every mounted consumer in sync without a provider.
import { useCallback, useSyncExternalStore } from "react";

export type NodeSourceMode = "universe" | "per-node";

export interface NodeSourcePolicy {
  mode: NodeSourceMode;
  /** "TICKER|expiry" or "TICKER" → data-source id. */
  overrides: Record<string, string>;
}

const STORAGE_KEY = "volfit.nodeSources.v1";
const MODES: readonly NodeSourceMode[] = ["universe", "per-node"];
const DEFAULT_POLICY: NodeSourcePolicy = { mode: "universe", overrides: {} };

/** Tooltip on every disabled per-node control (dialog card + matrix column). */
export const PER_NODE_HINT =
  "UI-ready — one active source today; per-node sources arrive with the multi-source engine";

/** Override-map key for one node (expiry given) or a whole ticker. */
export function nodeSourceKey(ticker: string, expiry?: string): string {
  return expiry ? `${ticker}|${expiry}` : ticker;
}

/** Source id a node would fetch from under `policy` (node → ticker →
 *  universe). Pure; the engine-side contract, exposed so the UI can preview it. */
export function resolveNodeSource(
  policy: NodeSourcePolicy,
  ticker: string,
  expiry: string,
  universeSource: string,
): string {
  if (policy.mode !== "per-node") return universeSource;
  return (
    policy.overrides[nodeSourceKey(ticker, expiry)] ??
    policy.overrides[nodeSourceKey(ticker)] ??
    universeSource
  );
}

function isPolicy(v: unknown): v is NodeSourcePolicy {
  if (typeof v !== "object" || v === null) return false;
  const o = v as { mode?: unknown; overrides?: unknown };
  if (!MODES.includes(o.mode as NodeSourceMode)) return false;
  if (typeof o.overrides !== "object" || o.overrides === null || Array.isArray(o.overrides)) {
    return false;
  }
  return Object.entries(o.overrides as Record<string, unknown>).every(
    ([k, val]) => k.trim() !== "" && typeof val === "string" && val.trim() !== "",
  );
}

function load(): NodeSourcePolicy {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (isPolicy(parsed)) return { mode: parsed.mode, overrides: { ...parsed.overrides } };
    }
  } catch {
    /* localStorage unavailable / malformed: fall through to the default */
  }
  return DEFAULT_POLICY;
}

function persist(p: NodeSourcePolicy): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } catch {
    /* best-effort */
  }
}

// ---- module store -------------------------------------------------------
let current: NodeSourcePolicy = load();
const listeners = new Set<() => void>();

function commit(next: NodeSourcePolicy): void {
  current = next;
  persist(next);
  listeners.forEach((l) => l());
}

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
}

const getSnapshot = () => current;
const getServerSnapshot = () => DEFAULT_POLICY;

export interface UseNodeSourcesResult {
  policy: NodeSourcePolicy;
  setMode: (mode: NodeSourceMode) => void;
  /** Pin a node / ticker key to a source; `null` removes the override. */
  setOverride: (key: string, sourceId: string | null) => void;
  clearOverrides: () => void;
}

export function useNodeSources(): UseNodeSourcesResult {
  const policy = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setMode = useCallback((mode: NodeSourceMode) => {
    if (mode !== current.mode) commit({ ...current, mode });
  }, []);

  const setOverride = useCallback((key: string, sourceId: string | null) => {
    const overrides = { ...current.overrides };
    if (sourceId === null || sourceId.trim() === "") delete overrides[key];
    else overrides[key] = sourceId;
    commit({ ...current, overrides });
  }, []);

  const clearOverrides = useCallback(() => {
    if (Object.keys(current.overrides).length > 0) commit({ ...current, overrides: {} });
  }, []);

  return { policy, setMode, setOverride, clearOverrides };
}
