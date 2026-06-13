// Data + actions for the Universe-management workspace.
//
// Talks to the universe API: search the provider catalogue (GET
// /universe/search), add/remove tickers from the active universe (POST/DELETE
// /universe/tickers), and save/load/delete named universes (GET/POST/DELETE
// /universes, POST /universe/load/{name}). The active universe itself is the
// shared smile session's; after any edit we call its refreshUniverse() so the
// selectors in every workspace pick up the change. Live backend only.
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";

/** One symbol-search hit (mirror of the backend SymbolMatch). */
export interface SymbolMatch {
  symbol: string;
  name: string;
  type: string;
  exchange: string;
}

/** Saved named universes (GET /universes). */
export interface SavedUniverses {
  names: string[];
  storeEnabled: boolean;
}

const SEARCH_DEBOUNCE_MS = 300;

/** Human-readable message from a thrown value (FastAPI `detail` when present). */
function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(err.body);
      if (
        typeof parsed === "object" &&
        parsed !== null &&
        typeof (parsed as { detail?: unknown }).detail === "string"
      ) {
        return (parsed as { detail: string }).detail;
      }
    } catch {
      /* non-JSON body: fall through */
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export function useUniverse() {
  const { universe, source, refreshUniverse } = useSmileSession();

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SymbolMatch[]>([]);
  const [searching, setSearching] = useState(false);
  /** A "verb:target" tag for the in-flight action (disables that row). */
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SavedUniverses>({ names: [], storeEnabled: false });

  // Debounced symbol search.
  useEffect(() => {
    if (query.trim() === "") {
      setResults([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setSearching(true);
      api
        .get<{ matches: SymbolMatch[] }>("/universe/search", {
          params: { q: query, limit: 10 },
          signal: controller.signal,
        })
        .then((r) => {
          setResults(r.matches);
          setSearching(false);
        })
        .catch(() => {
          if (!controller.signal.aborted) {
            setResults([]);
            setSearching(false);
          }
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const refreshSaved = useCallback(() => {
    api.get<SavedUniverses>("/universes").then(setSaved).catch(() => {});
  }, []);
  useEffect(() => {
    if (source === "live") refreshSaved();
  }, [source, refreshSaved]);

  /** Run an action with busy/error bookkeeping, then run `after`. */
  const act = useCallback(
    async (tag: string, run: () => Promise<unknown>, after?: () => Promise<void> | void) => {
      setBusy(tag);
      setError(null);
      try {
        await run();
        if (after) await after();
      } catch (err: unknown) {
        setError(messageOf(err));
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  const addTicker = useCallback(
    (symbol: string) =>
      act(`add:${symbol}`, () => api.post("/universe/tickers", { body: { symbol } }), refreshUniverse),
    [act, refreshUniverse],
  );

  const removeTicker = useCallback(
    (symbol: string) =>
      act(`remove:${symbol}`, () => api.delete(`/universe/tickers/${symbol}`), refreshUniverse),
    [act, refreshUniverse],
  );

  const saveUniverse = useCallback(
    (name: string) =>
      act(`save:${name}`, async () => {
        setSaved(await api.post<SavedUniverses>(`/universes/${encodeURIComponent(name)}`));
      }),
    [act],
  );

  const loadUniverse = useCallback(
    (name: string) =>
      act(`load:${name}`, () => api.post(`/universe/load/${encodeURIComponent(name)}`), refreshUniverse),
    [act, refreshUniverse],
  );

  const deleteUniverse = useCallback(
    (name: string) =>
      act(`del:${name}`, async () => {
        setSaved(await api.delete<SavedUniverses>(`/universes/${encodeURIComponent(name)}`));
      }),
    [act],
  );

  return {
    universe,
    source,
    query,
    setQuery,
    results,
    searching,
    busy,
    error,
    saved,
    addTicker,
    removeTicker,
    saveUniverse,
    loadUniverse,
    deleteUniverse,
    /** Refit the session on a new ladder after a per-ticker expiry change. */
    refreshUniverse,
  };
}
