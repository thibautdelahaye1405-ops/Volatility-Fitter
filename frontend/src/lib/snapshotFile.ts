// Snapshot FILE bundle (UI SHELL v2 wave 3, A2) — pure helpers, vitest-locked.
//
// A snapshot file (`volfit-snapshot/1`, built server-side by POST
// /snapshot/export) carries quotes + prevailing calibrations per ticker; the
// client only validates the envelope before handing it to POST
// /snapshot/import (the server validates the content) and routes a dropped
// file to the right opener by its schema family.

export const SNAPSHOT_SCHEMA = "volfit-snapshot/1";
const FAMILY = "volfit-snapshot";
const MAJOR = "1";

export interface SnapshotSummary {
  schema: string;
  asOf: string;
  tickers: string[];
}

export type SnapshotParse = { ok: true; summary: SnapshotSummary } | { ok: false; error: string };

/** Envelope check of an opened snapshot file (the server checks the content). */
export function parseSnapshotBundle(raw: unknown): SnapshotParse {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { ok: false, error: "not a JSON object" };
  }
  const r = raw as Record<string, unknown>;
  const tag = r.schema;
  if (typeof tag !== "string" || !tag.includes("/")) {
    return { ok: false, error: `missing "schema" tag (expected ${SNAPSHOT_SCHEMA})` };
  }
  const [family, major] = tag.split("/");
  if (family !== FAMILY) return { ok: false, error: `not a snapshot file (schema ${tag})` };
  if (major !== MAJOR) return { ok: false, error: `unsupported snapshot schema ${tag} (this app reads ${SNAPSHOT_SCHEMA})` };
  const tickers = r.tickers;
  if (!Array.isArray(tickers) || tickers.length === 0) return { ok: false, error: "snapshot file carries no tickers" };
  const names = tickers
    .map((t) => (typeof t === "object" && t !== null ? (t as { ticker?: unknown }).ticker : undefined))
    .filter((t): t is string => typeof t === "string" && t !== "");
  if (names.length !== tickers.length) return { ok: false, error: "malformed ticker entry" };
  return { ok: true, summary: { schema: tag, asOf: typeof r.asOf === "string" ? r.asOf : "", tickers: names } };
}

/** Which opener a dropped JSON belongs to, by schema family (null = neither). */
export function classifyBundle(raw: unknown): "workspace" | "snapshot" | null {
  if (typeof raw !== "object" || raw === null) return null;
  const tag = (raw as { schema?: unknown }).schema;
  if (typeof tag !== "string") return null;
  if (tag.startsWith("volfit-workspace/")) return "workspace";
  if (tag.startsWith("volfit-snapshot/")) return "snapshot";
  return null;
}

/** "spy-qqq_2026-08-27_1430.volfit-snapshot.json" (tickers capped at 3). */
export function snapshotFilename(tickers: string[], asOf: string): string {
  const names = tickers.slice(0, 3).map((t) => t.toLowerCase().replace(/[^a-z0-9]+/g, "")).filter(Boolean);
  const more = tickers.length > 3 ? `-plus${tickers.length - 3}` : "";
  const stamp = asOf.replace(/[-:]/g, "").replace("T", "_").slice(0, 13) || "snapshot";
  return `${names.join("-") || "snapshot"}${more}_${stamp}.volfit-snapshot.json`;
}

/** Display name of a snapshot target from its filename. */
export function snapshotNameOf(filename: string): string {
  return filename.replace(/\.volfit-snapshot\.json$/i, "").replace(/\.json$/i, "");
}
