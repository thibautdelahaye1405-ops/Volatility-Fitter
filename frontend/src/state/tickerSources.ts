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
import { useCallback, useState } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";

/** Effective source of a ticker: its pin when set, else the universe source. */
export function resolveTickerSource(
  pins: Record<string, string> | undefined,
  defaultSource: string,
  ticker: string,
): string {
  return pins?.[ticker] ?? defaultSource;
}

/** Short badge text for a source id (the Nodes-pane pill on a pinned ticker). */
export function shortSourceLabel(id: string): string {
  const known: Record<string, string> = {
    bloomberg: "BBG", massive: "MSV", yahoo: "YHOO", cboe: "CBOE", synthetic: "SYN", file: "FILE",
    nasdaq: "NDAQ", asx: "ASX", hkex: "HKEX", sgx: "SGX", eurex: "EURX",
  };
  return known[id] ?? id.slice(0, 4).toUpperCase();
}

/** Human label for a source id when the data-sources list is not at hand. */
export function sourceLabel(id: string): string {
  const known: Record<string, string> = {
    bloomberg: "Bloomberg", massive: "Massive", yahoo: "Yahoo", cboe: "Cboe", synthetic: "Synthetic",
    file: "File", nasdaq: "Nasdaq", asx: "ASX", hkex: "HKEX", sgx: "SGX", eurex: "Eurex",
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
  /** Explicit pins only: ticker → source id. */
  pins: Record<string, string>;
  /** Effective source of a ticker (pin, else the default). */
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

  const sourceOf = useCallback(
    (ticker: string) => resolveTickerSource(pins, defaultSource, ticker),
    [pins, defaultSource],
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

  return { defaultSource, pins, sourceOf, setTickerSource, busy, error };
}
