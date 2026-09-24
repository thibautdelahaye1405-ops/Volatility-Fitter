// Per-ticker data sources (the multi-source engine, 2026-09-02h).
//
// The universe fetches from ONE default source (the Data Source selector —
// `defaultSource` of GET /universe) unless a ticker is PINNED to another
// registered source: `tickerSources` carries the explicit pins only (ticker →
// source id), so a ticker absent there follows the default. A pin is server
// state: PUT /universe/{ticker}/source {source | null} (null = follow the
// default) drops that ticker's chain caches, refetches it from the new feed
// and bumps its data version (its nodes read STALE). Pins are saved in the
// backend workspace doc and with named universes — nothing is persisted here.
//
// The pin value AUTO_SOURCE ("auto", 2026-09-24) is a POLICY, not a source:
// the backend resolves it per ticker to the fastest green source that can
// serve the name (volfit.api.source_policy) and reports the pick beside the
// pin (`resolvedSources` of GET /universe) — re-ranked at Fetch time only, so
// a ticker never hops between feeds between two Fetches. The row's select
// shows "Auto → Cboe" so the pick is never silent.
import { useCallback, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";

/** The pin value that means "the fastest green source for this ticker". */
export const AUTO_SOURCE = "auto";

/** Effective source of a ticker: its pin when set — an auto pin reads the
 *  backend's resolution (`resolved`), the default until it is known — else
 *  the universe source. */
export function resolveTickerSource(
  pins: Record<string, string> | undefined,
  defaultSource: string,
  ticker: string,
  resolved?: Record<string, string>,
): string {
  const pin = pins?.[ticker];
  if (pin === AUTO_SOURCE) return resolved?.[ticker] ?? defaultSource;
  return pin ?? defaultSource;
}

/** The select's label for the auto option: "Auto → Cboe" once the backend
 *  resolved the ticker's pin, the plain policy name before / on other pins. */
export function autoPinLabel(resolvedId: string | undefined, labelOf: (id: string) => string): string {
  return resolvedId ? `Auto → ${labelOf(resolvedId)}` : "Auto (fastest green source)";
}

/** Short badge text for a source id (the Nodes-pane pill on a pinned ticker). */
export function shortSourceLabel(id: string): string {
  const known: Record<string, string> = {
    bloomberg: "BBG", massive: "MSV", yahoo: "YHOO", cboe: "CBOE", synthetic: "SYN", file: "FILE",
    nasdaq: "NDAQ", asx: "ASX", hkex: "HKEX", sgx: "SGX", eurex: "EURX", [AUTO_SOURCE]: "AUTO",
  };
  return known[id] ?? id.slice(0, 4).toUpperCase();
}

/** Human label for a source id when the data-sources list is not at hand. */
export function sourceLabel(id: string): string {
  const known: Record<string, string> = {
    bloomberg: "Bloomberg", massive: "Massive", yahoo: "Yahoo", cboe: "Cboe", synthetic: "Synthetic",
    file: "File", nasdaq: "Nasdaq", asx: "ASX", hkex: "HKEX", sgx: "SGX", eurex: "Eurex",
    [AUTO_SOURCE]: "Auto",
  };
  return known[id] ?? id;
}

/** FastAPI `detail` when present, else the thrown message. */
function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(err.body);
      const detail = (parsed as { detail?: unknown } | null)?.detail;
      if (typeof detail === "string") return detail;
    } catch {
      /* non-JSON body */
    }
  }
  return err instanceof Error ? err.message : String(err);
}

export interface UseTickerSourcesResult {
  /** The universe's default source id (the Data Source selector). */
  defaultSource: string;
  /** Explicit pins only: ticker → source id (or AUTO_SOURCE). */
  pins: Record<string, string>;
  /** ticker → the source it fetches from NOW per the backend (an auto pin's
   *  resolution made visible; the pin or the default for the others). */
  resolved: Record<string, string>;
  /** Effective source of a ticker (pin — an auto pin's resolution — else the default). */
  sourceOf: (ticker: string) => string;
  /** Pin a ticker to a source; null = follow the universe source. */
  setTickerSource: (ticker: string, sourceId: string | null) => Promise<void>;
  /** The ticker whose pin is being changed, or null. */
  busy: string | null;
  /** The last failed pin change (never silent), or null. */
  error: string | null;
}

export function useTickerSources(): UseTickerSourcesResult {
  const { universe, refreshUniverse } = useSmileSession();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const defaultSource = universe?.defaultSource ?? "";
  const pins = universe?.tickerSources ?? {};
  const resolved = universe?.resolvedSources ?? {};

  const sourceOf = useCallback(
    (ticker: string) => resolveTickerSource(pins, defaultSource, ticker, resolved),
    [pins, defaultSource, resolved],
  );

  const setTickerSource = useCallback(
    async (ticker: string, sourceId: string | null) => {
      setBusy(ticker);
      setError(null);
      try {
        // The pinned ticker refetches lazily on its new feed — a chain pull.
        await api.put(`/universe/${encodeURIComponent(ticker)}/source`, {
          body: { source: sourceId },
          timeoutMs: 300_000,
        });
        await refreshUniverse();
      } catch (err: unknown) {
        setError(`${ticker}: ${messageOf(err)}`);
      } finally {
        setBusy(null);
      }
    },
    [refreshUniverse],
  );

  return { defaultSource, pins, resolved, sourceOf, setTickerSource, busy, error };
}
