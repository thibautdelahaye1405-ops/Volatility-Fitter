// Pure helpers over the SERVED offline filter-replay artifacts (V3.9 rider).
// No React, no DOM — vitest-covered; consumed by state/useFilterReplay.ts,
// components/ReplayEvidenceBlock.tsx and components/FilterTimelineSection.tsx.
//
// The backend (routers/filter_replay.py) only serves what
// `python -m backtest.filter_replay` wrote: per (ticker, day) one part
// `{meta, nodes: {iso: FilterStepWire[]}}` whose steps are byte-identical to
// the live /filter/history wire dicts — so the FilterTimeline renders a
// replay part with the same code path as the live ring.
import type { FilterStepWire } from "./filterTimeline";

/** One row of GET /filter/replay/parts (backend FilterReplayPartMeta). */
export interface FilterReplayPartMeta {
  ticker: string;
  /** ISO date the session was replayed over. */
  day: string;
  /** Stored intraday instants driven through the production commit path. */
  nInstants: number;
  fitMode: string;
  /** The replay's observationFilterMode ("overlay"). */
  filterMode: string;
  /** Node ISOs carried by the part's `nodes` (sorted). */
  expiries: string[];
  /** File modification epoch seconds (newest-first tie-breaker). */
  mtime: number;
}

/** GET /filter/replay/parts/{ticker}/{day}: the part document verbatim. */
export interface FilterReplayPart {
  meta: {
    ticker: string;
    day: string;
    fitMode?: string;
    filterMode?: string;
    nInstants?: number;
    appVersion?: string;
  };
  nodes: Record<string, FilterStepWire[]>;
}

/** The empty-state copy (mock / backendless / no part yet). */
export const REPLAY_RUN_HINT =
  "No replay artifact yet — run python -m backtest.filter_replay";

/** Newest part: replayed day DESC, then file mtime DESC (the backend's
 *  listing order, re-derived here so an unsorted list still resolves);
 *  null when the list is empty. */
export function newestPart<T extends { day: string; mtime?: number }>(parts: T[]): T | null {
  let best: T | null = null;
  for (const p of parts) {
    if (best === null) {
      best = p;
      continue;
    }
    if (p.day > best.day) best = p;
    else if (p.day === best.day && (p.mtime ?? 0) > (best.mtime ?? 0)) best = p;
  }
  return best;
}

/** The newest part whose `nodes` carry this expiry ISO — what decides
 *  whether the timeline shows its "Replay <day>" chip at all. */
export function partForExpiry(
  parts: FilterReplayPartMeta[],
  iso: string,
): FilterReplayPartMeta | null {
  if (iso === "") return null;
  return newestPart(parts.filter((p) => p.expiries.includes(iso)));
}

/** A part's steps for `iso`, oldest first; [] when the part/node is absent
 *  or malformed (a non-array node never reaches the charts). */
export function stepsForExpiry(
  part: FilterReplayPart | null | undefined,
  iso: string,
): FilterStepWire[] {
  const node = part?.nodes?.[iso];
  return Array.isArray(node) ? node : [];
}

/** Source-chip label for a replay part. */
export function replayChipLabel(part: { day: string }): string {
  return `Replay ${part.day}`;
}
