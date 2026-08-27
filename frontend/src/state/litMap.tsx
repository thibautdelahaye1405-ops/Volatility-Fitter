// Shared lit/dark designation map (UI SHELL v2, S2).
//
// Every selected (ticker, expiry) node carries a lit/dark designation
// (GET/PUT /universe/lit): lit = an observed source for the graph solver,
// dark = an extrapolation target. Three surfaces edit it — the nodes pane,
// the Universe dialog's matrix and the Graph canvas (manual mode) — so the
// map lives in ONE context with optimistic toggles. Writers that bypass the
// context (useGraph.persistLit) announce themselves on a window event
// (LIT_CHANGED_EVENT) so the map refetches and every surface agrees.
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api";
import { useSmileSession } from "./smileSession";

export interface LitNode {
  ticker: string;
  expiry: string;
  lit: boolean;
}
interface LitMapResponse {
  nodes: LitNode[];
}

/** Dispatched (window) after an out-of-context PUT /universe/lit lands. */
export const LIT_CHANGED_EVENT = "volfit:lit-changed";

export function announceLitChanged(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(LIT_CHANGED_EVENT));
}

export interface LitMapValue {
  nodes: LitNode[];
  /** key "T|expiry" -> lit (fast lookup). */
  litOf: (ticker: string, expiry: string) => boolean | undefined;
  error: string | null;
  /** Optimistic single-node toggle (PUT; reverts on failure). */
  toggleNode: (ticker: string, expiry: string) => void;
  /** Optimistic single-node SET (drag-to-light, wave 3 C5); no-op when equal. */
  setNode: (ticker: string, expiry: string, lit: boolean) => void;
  /** Light / darken every node of a ticker (PUT; server list adopted). */
  setTicker: (ticker: string, lit: boolean) => void;
  refresh: () => void;
}

const Ctx = createContext<LitMapValue | null>(null);

export function LitMapProvider({ children }: { children: ReactNode }) {
  const { universe, source } = useSmileSession();
  const [nodes, setNodes] = useState<LitNode[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Refetch when the universe's ticker set / ladder lengths change, on an
  // explicit refresh, and whenever another writer announces a change.
  const sig = useMemo(
    () =>
      universe
        ? universe.tickers.map((t) => `${t}:${(universe.expiries[t] ?? []).length}`).join(",")
        : "",
    [universe],
  );
  useEffect(() => {
    if (source !== "live") {
      setNodes([]);
      return;
    }
    const controller = new AbortController();
    api
      .get<LitMapResponse>("/universe/lit", { signal: controller.signal })
      .then((d) => {
        setNodes(d.nodes);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [sig, source, attempt]);

  const refresh = useCallback(() => setAttempt((n) => n + 1), []);
  useEffect(() => {
    window.addEventListener(LIT_CHANGED_EVENT, refresh);
    return () => window.removeEventListener(LIT_CHANGED_EVENT, refresh);
  }, [refresh]);

  const index = useMemo(() => {
    const m = new Map<string, boolean>();
    for (const n of nodes) m.set(`${n.ticker}|${n.expiry}`, n.lit);
    return m;
  }, [nodes]);
  const litOf = useCallback(
    (ticker: string, expiry: string) => index.get(`${ticker}|${expiry}`),
    [index],
  );

  const toggleNode = useCallback((ticker: string, expiry: string) => {
    setNodes((prev) => {
      const cur = prev.find((m) => m.ticker === ticker && m.expiry === expiry);
      if (!cur) return prev;
      const lit = !cur.lit;
      void api
        .put(`/universe/lit/${ticker}/${encodeURIComponent(expiry)}`, { body: { lit } })
        .catch(() => {
          setNodes((p) =>
            p.map((m) => (m.ticker === ticker && m.expiry === expiry ? { ...m, lit: cur.lit } : m)),
          );
        });
      return prev.map((m) => (m.ticker === ticker && m.expiry === expiry ? { ...m, lit } : m));
    });
  }, []);

  const setNode = useCallback((ticker: string, expiry: string, lit: boolean) => {
    setNodes((prev) => {
      const cur = prev.find((m) => m.ticker === ticker && m.expiry === expiry);
      if (!cur || cur.lit === lit) return prev;
      void api
        .put(`/universe/lit/${ticker}/${encodeURIComponent(expiry)}`, { body: { lit } })
        .catch(() => {
          setNodes((p) =>
            p.map((m) => (m.ticker === ticker && m.expiry === expiry ? { ...m, lit: cur.lit } : m)),
          );
        });
      return prev.map((m) => (m.ticker === ticker && m.expiry === expiry ? { ...m, lit } : m));
    });
  }, []);

  const setTicker = useCallback((ticker: string, lit: boolean) => {
    setNodes((prev) => prev.map((m) => (m.ticker === ticker ? { ...m, lit } : m)));
    void api
      .put<LitMapResponse>(`/universe/lit/${ticker}`, { body: { lit } })
      .then((d) => setNodes(d.nodes))
      .catch(() => {
        /* leave the optimistic state; the next refresh reconciles */
      });
  }, []);

  const value = useMemo<LitMapValue>(
    () => ({ nodes, litOf, error, toggleNode, setNode, setTicker, refresh }),
    [nodes, litOf, error, toggleNode, setNode, setTicker, refresh],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useLitMap(): LitMapValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useLitMap must be used within LitMapProvider");
  return ctx;
}

/** Null outside the provider (tests / legacy mounts). */
export function useOptionalLitMap(): LitMapValue | null {
  return useContext(Ctx);
}
