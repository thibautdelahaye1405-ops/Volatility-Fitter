// Workspace FILE bundle (UI SHELL v2 wave 3, A1) — pure helpers, vitest-locked.
//
// A workspace file is one JSON document:
//   { schema: "volfit-workspace/1", savedAt, app: { version },
//     backend: <the server's workspace doc>,      // opaque here (server-validated)
//     shell:   { activity, tabs, layout, viewSettings, expiryFormat, nodeSources } }
// The backend part is authored + validated server-side (GET /workspace/export,
// POST /workspace/import); this module owns the ENVELOPE and the shell part:
// validation of a file the user opens (drag-drop / picker / server), the
// shell blob hash used for dirty tracking, filenames, and the recent list.

export const WORKSPACE_SCHEMA = "volfit-workspace/1";
const SCHEMA_FAMILY = "volfit-workspace";
const SCHEMA_MAJOR = "1";

/** The shell's share of the file (validated leniently on load — every field
 *  is optional; the consumers apply what they recognise). */
export interface ShellBlob {
  activity?: string;
  tabs?: unknown;
  viewMemory?: unknown;
  layout?: Partial<{ nodesPane: boolean; nodesWidth: number; statusBar: boolean; aside: boolean; rememberView: boolean }>;
  viewSettings?: { scheme?: string; contrast?: number; brightness?: number };
  expiryFormat?: string;
  nodeSources?: unknown;
}

export interface WorkspaceBundle {
  schema: string;
  savedAt: string;
  app: { version: string };
  backend: Record<string, unknown>;
  shell: ShellBlob | null;
}

export type ParseResult =
  | { ok: true; bundle: WorkspaceBundle }
  | { ok: false; error: string };

/** Validate an opened file (parsed JSON) into a bundle; every failure names
 *  what was wrong (the status bar shows it). The backend doc's own version
 *  is checked server-side — here only its presence and shape. */
export function parseWorkspaceBundle(raw: unknown): ParseResult {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { ok: false, error: "not a JSON object" };
  }
  const r = raw as Record<string, unknown>;
  const tag = r.schema;
  if (typeof tag !== "string" || !tag.includes("/")) {
    return { ok: false, error: `missing "schema" tag (expected ${WORKSPACE_SCHEMA})` };
  }
  const [family, major] = tag.split("/");
  if (family !== SCHEMA_FAMILY) {
    return { ok: false, error: `not a workspace file (schema ${tag})` };
  }
  if (major !== SCHEMA_MAJOR) {
    return { ok: false, error: `unsupported workspace schema ${tag} (this app reads ${WORKSPACE_SCHEMA})` };
  }
  const backend = r.backend;
  if (typeof backend !== "object" || backend === null || Array.isArray(backend)) {
    return { ok: false, error: "workspace file carries no backend document" };
  }
  if (typeof (backend as { v?: unknown }).v !== "number") {
    return { ok: false, error: "backend document has no version" };
  }
  const shellRaw = r.shell;
  const shell =
    typeof shellRaw === "object" && shellRaw !== null && !Array.isArray(shellRaw)
      ? (shellRaw as ShellBlob)
      : null;
  const app = r.app;
  const version =
    typeof app === "object" && app !== null && typeof (app as { version?: unknown }).version === "string"
      ? (app as { version: string }).version
      : "";
  return {
    ok: true,
    bundle: {
      schema: tag,
      savedAt: typeof r.savedAt === "string" ? r.savedAt : "",
      app: { version },
      backend: backend as Record<string, unknown>,
      shell,
    },
  };
}

/** Assemble the file from the server's export (backend part) + the shell. */
export function buildWorkspaceBundle(
  serverBundle: { schema?: string; app?: { version?: string }; backend: Record<string, unknown> },
  shell: ShellBlob,
  now: Date = new Date(),
): WorkspaceBundle {
  return {
    schema: serverBundle.schema ?? WORKSPACE_SCHEMA,
    savedAt: now.toISOString().replace(/\.\d{3}Z$/, "Z"),
    app: { version: serverBundle.app?.version ?? "" },
    backend: serverBundle.backend,
    shell,
  };
}

/** FNV-1a 32-bit over a string — a cheap, stable content hash for the shell
 *  blob (dirty tracking; NOT a security primitive). Hex, 8 chars. */
export function hashString(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

/** Canonical hash of a shell blob (key order independent). */
export function hashShell(shell: ShellBlob): string {
  return hashString(canonicalJson(shell));
}

/** JSON with sorted object keys (deterministic for hashing). */
export function canonicalJson(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(canonicalJson).join(",")}]`;
  if (typeof v === "object" && v !== null) {
    const keys = Object.keys(v as Record<string, unknown>).sort();
    return `{${keys
      .map((k) => `${JSON.stringify(k)}:${canonicalJson((v as Record<string, unknown>)[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(v) ?? "null";
}

/** "My desk (SPY)" -> "my-desk-spy.volfit.json"; empty -> a dated name. */
export function workspaceFilename(name: string, now: Date = new Date()): string {
  const slug = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  const base = slug !== "" ? slug : `workspace-${now.toISOString().slice(0, 10)}`;
  return `${base}.volfit.json`;
}

/** Display name of a file target from its filename ("desk-a.volfit.json" -> "desk-a"). */
export function workspaceNameOf(filename: string): string {
  return filename.replace(/\.volfit\.json$/i, "").replace(/\.json$/i, "");
}

/** Where the workspace lives (the Save target). */
export type WorkspaceTarget =
  | { kind: "file"; name: string; handle: FileSystemFileHandle | null }
  | { kind: "server"; name: string };

export interface RecentEntry {
  kind: "file" | "server";
  name: string;
  /** Epoch ms of the last open / save. */
  at: number;
}

export const RECENT_MAX = 8;

/** Move-or-insert an entry at the head; capped at RECENT_MAX; dedup by (kind, name). */
export function pushRecent(list: RecentEntry[], entry: RecentEntry, max = RECENT_MAX): RecentEntry[] {
  const rest = list.filter((e) => !(e.kind === entry.kind && e.name === entry.name));
  return [entry, ...rest].slice(0, max);
}

/** Validate a persisted recent list (drops malformed rows). */
export function restoreRecent(raw: unknown): RecentEntry[] {
  if (!Array.isArray(raw)) return [];
  const out: RecentEntry[] = [];
  for (const e of raw as unknown[]) {
    if (typeof e !== "object" || e === null) continue;
    const { kind, name, at } = e as Partial<RecentEntry>;
    if ((kind !== "file" && kind !== "server") || typeof name !== "string" || name === "") continue;
    out.push({ kind, name, at: typeof at === "number" ? at : 0 });
  }
  return out.slice(0, RECENT_MAX);
}
