// Fetch coverage preview (GET /fetch/preview): what the NEXT Fetch would
// serve per active ticker under the current as-of selection and the active
// source — the Fetch menu's "14:30 · 9/12 nodes exact · 3 fall back to
// close" line, read when the menu opens. Read-only on the backend (cached
// state + the provider's advertised capabilities, never a feed call). Mock
// fallback (no live backend) = null, and the row stays hidden.
import { useEffect, useState } from "react";
import { api } from "./api";

/** One active ticker's coverage under the current as-of selection. */
export interface FetchPreviewTicker {
  ticker: string;
  /** Ladder rungs (a ticker's nodes share one chain: exact or fallback whole). */
  nodes: number;
  requestedMode: string;
  requestedDay: string | null;
  /** The source serves the requested moment (advertised, overridden by the
   *  evidence of a loaded chain stamped off the requested session). */
  providerHonors: boolean;
  /** What it serves instead: its live chain, or another session's close. */
  fallback: "live" | "close" | null;
  /** Exactness of the chain currently loaded; null before any fetch. */
  currentlyExact: boolean | null;
  effectiveAsOf: string | null;
}

export interface FetchPreview {
  mode: string;
  requestedDay: string | null;
  dataSource: string;
  /** The one-line menu row. */
  summary: string;
  totals: { nodes: number; exact: number; fallback: number };
  tickers: FetchPreviewTicker[];
}

/** The preview, refetched each time `open` turns true (the menu opening);
 *  null until it answers, off-live, or on a failed read. */
export function useFetchPreview(open: boolean, live: boolean): FetchPreview | null {
  const [preview, setPreview] = useState<FetchPreview | null>(null);

  useEffect(() => {
    if (!live) {
      setPreview(null);
      return;
    }
    if (!open) return;
    const controller = new AbortController();
    api
      .get<FetchPreview>("/fetch/preview", { signal: controller.signal })
      .then(setPreview)
      .catch(() => {
        if (!controller.signal.aborted) setPreview(null);
      });
    return () => controller.abort();
  }, [open, live]);

  return preview;
}
