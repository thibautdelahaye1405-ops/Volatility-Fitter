// Series FILE bundle (`volfit-series/1`, SERIES ARC S6) — pure helpers,
// vitest-locked. The bundle is built server-side (POST /series/{id}/export:
// the series document, every frame's chain, every fit, the lanes' carries)
// and read back by POST /series/import, which recreates the series under
// its own id (idempotent). The client validates the envelope only and
// routes a dropped file by its schema family (lib/snapshotFile.classifyBundle).

export const SERIES_FILE_SCHEMA = "volfit-series/1";
const FAMILY = "volfit-series";
const MAJOR = "1";

export interface SeriesFileSummary {
  schema: string;
  id: string;
  name: string;
  ticker: string;
  frames: number;
  lanes: number;
}

export type SeriesFileParse = { ok: true; summary: SeriesFileSummary } | { ok: false; error: string };

/** Envelope check of an opened series file (the server checks the content). */
export function parseSeriesBundle(raw: unknown): SeriesFileParse {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { ok: false, error: "not a JSON object" };
  }
  const r = raw as Record<string, unknown>;
  const tag = r.schema;
  if (typeof tag !== "string" || !tag.includes("/")) {
    return { ok: false, error: `missing "schema" tag (expected ${SERIES_FILE_SCHEMA})` };
  }
  const [family, major] = tag.split("/");
  if (family !== FAMILY) return { ok: false, error: `not a series file (schema ${tag})` };
  if (major !== MAJOR) return { ok: false, error: `unsupported series schema ${tag} (this app reads ${SERIES_FILE_SCHEMA})` };
  const series = r.series;
  if (typeof series !== "object" || series === null) return { ok: false, error: "series file carries no series document" };
  const s = series as { id?: unknown; spec?: { name?: unknown; ticker?: unknown; lanes?: unknown }; frames?: unknown };
  if (typeof s.id !== "string" || !s.id) return { ok: false, error: "series document has no id" };
  const spec = s.spec ?? {};
  return {
    ok: true,
    summary: {
      schema: tag,
      id: s.id,
      name: typeof spec.name === "string" ? spec.name : "",
      ticker: typeof spec.ticker === "string" ? spec.ticker : "",
      frames: Array.isArray(s.frames) ? s.frames.length : 0,
      lanes: Array.isArray(spec.lanes) ? spec.lanes.length : 0,
    },
  };
}

/** "spy_2026-08-19-15-min_20260910_1512.volfit-series.json". */
export function seriesFilename(ticker: string, name: string, savedAt: string): string {
  const t = ticker.toLowerCase().replace(/[^a-z0-9]+/g, "") || "series";
  const n = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  const stamp = savedAt.replace(/[-:]/g, "").replace("T", "_").slice(0, 13) || "series";
  return `${t}${n ? `_${n}` : ""}_${stamp}.volfit-series.json`;
}
