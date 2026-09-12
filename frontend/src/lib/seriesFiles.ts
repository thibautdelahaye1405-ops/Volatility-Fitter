// The Series lens's file memory (2026-09-12) — pure, vitest-locked. The lens
// remembers the series files it saved or opened (name, when, which series)
// so that the next Open starts where the last file was saved and proposes
// the latest file first: File ▸ Series ▸ the recent rows, the header's
// "Reopen <latest>", the palette's "Open recent series: <name>". The list
// lives in localStorage (this key); the files' handles live beside the
// workspace handles in IndexedDB under `seriesHandleKey(name)` (Chromium
// only — other browsers keep the names and re-pick the file).

export interface SeriesRecentEntry {
  /** The file's name (the picker's / the download's), unique in the list. */
  name: string;
  /** Epoch ms of the last save / open. */
  at: number;
  /** The series the file carries (its own id survives the round trip). */
  id: string;
  ticker: string;
  frames: number;
}

export const SERIES_RECENT_MAX = 8;
export const SERIES_RECENT_KEY = "volfit.series.recent.v1";
/** The picker id: Chromium remembers the last directory per id across sessions. */
export const SERIES_PICKER_ID = "volfit-series";
export const SERIES_FILE_DESCRIPTION = "VolFit series";

/** Move-or-insert at the head (dedup by file name), capped. */
export function pushSeriesRecent(list: SeriesRecentEntry[], entry: SeriesRecentEntry, max = SERIES_RECENT_MAX): SeriesRecentEntry[] {
  const rest = list.filter((e) => e.name !== entry.name);
  return [entry, ...rest].slice(0, max);
}

/** Validate a persisted list (malformed rows dropped). */
export function restoreSeriesRecent(raw: unknown): SeriesRecentEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: SeriesRecentEntry[] = [];
  for (const e of raw as unknown[]) {
    if (typeof e !== "object" || e === null) continue;
    const { name, at, id, ticker, frames } = e as Partial<SeriesRecentEntry>;
    if (typeof name !== "string" || name === "" || typeof id !== "string" || id === "") continue;
    out.push({
      name, id,
      at: typeof at === "number" ? at : 0,
      ticker: typeof ticker === "string" ? ticker : "",
      frames: typeof frames === "number" ? frames : 0,
    });
  }
  return out.slice(0, SERIES_RECENT_MAX);
}

/** The IndexedDB key of a series file's handle (beside the workspace handles). */
export function seriesHandleKey(name: string): string {
  return `series:${name}`;
}

/** The file to propose first: the most recently saved or opened. */
export function latestSeriesFile(list: SeriesRecentEntry[]): SeriesRecentEntry | null {
  return list[0] ?? null;
}

/** "name · NVDA · 10 frames" (the palette / menu detail). */
export function seriesFileLabel(e: SeriesRecentEntry): string {
  return `${e.name} · ${e.ticker || "?"} · ${e.frames} frame${e.frames === 1 ? "" : "s"}`;
}

/** A file name short enough for a button: the series suffix dropped, the
 *  middle elided past ``max`` characters ("nvda_5-min-x10_2026…1452"). */
export function shortFileName(name: string, max = 28): string {
  const base = name.replace(/\.volfit-series\.json$/i, "").replace(/\.json$/i, "");
  if (base.length <= max) return base;
  const head = Math.ceil((max - 1) / 2);
  const tail = Math.floor((max - 1) / 2);
  return `${base.slice(0, head)}…${base.slice(base.length - tail)}`;
}
