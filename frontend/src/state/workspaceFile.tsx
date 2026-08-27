// Workspace FILES (UI SHELL v2 wave 3, A1): the File menu's state — the
// current save target, dirty tracking, the recent list and the server store.
//
// A workspace file bundles the backend workspace doc (GET /workspace/export —
// settings, universe picks, edits, priors, …) with the shell state (activity,
// tabs, layout, view preferences, expiry format, node-source policy). Saving
// merges the two; opening installs both (POST /workspace/import is a backend
// state RESET, then the shell blob is applied). Targets: a FILE (Chromium
// keeps a FileSystemFileHandle so Save overwrites in place; elsewhere Save
// re-downloads under the same name) or the SERVER store (VOLFIT_DB). Dirty =
// the backend fingerprint (GET /workspace/status, polled while live) or the
// shell blob hash moved since the last save / open; a fresh session baselines
// clean. Every outcome lands in the status bar's "Last" chip (noteAction).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "./api";
import { useWorkbench } from "./workbench";
import { useViewSettings } from "./viewSettings";
import type { ColorScheme } from "./viewSettings";
import { useExpiryFormat } from "./expiryFormat";
import { useNodeSources } from "./nodeSources";
import { useSmileSession } from "./smileSession";
import { useWorkflowContext } from "./workflowContext";
import { EXPIRY_FORMATS } from "../lib/expiryFormat";
import type { ExpiryFormat } from "../lib/expiryFormat";
import {
  buildWorkspaceBundle, hashShell, parseWorkspaceBundle, pushRecent, restoreRecent,
  workspaceFilename, workspaceNameOf,
} from "../lib/workspaceFile";
import type { RecentEntry, ShellBlob, WorkspaceBundle, WorkspaceTarget } from "../lib/workspaceFile";
import {
  deleteHandle, downloadText, getHandle, pickOpenHandle, pickSaveHandle, promptFile, putHandle,
  readHandle, supportsFilePicker, writeHandle,
} from "../lib/fileHandles";

const RECENT_KEY = "volfit.workspace.recent.v1";
const STATUS_POLL_MS = 5000;

interface ServerBundle { schema?: string; app?: { version?: string }; backend: Record<string, unknown> }
interface WorkspaceStatus { fingerprint: string }
interface ServerEntry { name: string; savedTs: string }
interface ServerList { entries: ServerEntry[]; storeEnabled: boolean }

export interface WorkspaceFileValue {
  target: WorkspaceTarget | null;
  /** Display name of the target ("untitled" when none). */
  name: string;
  dirty: boolean;
  busy: boolean;
  recent: RecentEntry[];
  server: ServerList;
  canPickFiles: boolean;
  newWorkspace: () => Promise<void>;
  /** Ctrl+O: the open picker (Chromium) or an <input type=file> prompt. */
  openPicker: () => Promise<void>;
  /** A dropped / chosen File. */
  openFile: (file: File) => Promise<void>;
  openRecent: (entry: RecentEntry) => Promise<void>;
  openFromServer: (name: string) => Promise<void>;
  /** Ctrl+S: re-save to the last target (Save as… when there is none). */
  save: () => Promise<void>;
  /** Ctrl+Shift+S: file picker (Chromium) or a browser download. */
  saveAs: () => Promise<void>;
  saveToServer: (name: string) => Promise<void>;
  deleteFromServer: (name: string) => Promise<void>;
  refreshServer: () => void;
}

const Ctx = createContext<WorkspaceFileValue | null>(null);

function loadRecent(): RecentEntry[] {
  try { return restoreRecent(JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]")); } catch { return []; }
}
function persistRecent(list: RecentEntry[]): void {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list)); } catch { /* best-effort */ }
}
function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const d = (JSON.parse(err.body) as { detail?: unknown }).detail;
      if (typeof d === "string") return d;
    } catch { /* non-JSON */ }
  }
  return err instanceof Error ? err.message : String(err);
}

/** Mount inside WorkbenchProvider (it reads + writes the shell state). */
export function WorkspaceFileProvider({ children }: { children: ReactNode }) {
  const wb = useWorkbench();
  const view = useViewSettings();
  const expiry = useExpiryFormat();
  const nodeSources = useNodeSources();
  const { refreshUniverse, reload, refreshViews } = useSmileSession();
  const { live, workflow } = useWorkflowContext();
  const { noteAction } = workflow;

  const [target, setTarget] = useState<WorkspaceTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [recent, setRecent] = useState<RecentEntry[]>(loadRecent);
  const [server, setServer] = useState<ServerList>({ entries: [], storeEnabled: false });
  const [backendFp, setBackendFp] = useState<string | null>(null);
  // Baseline of the last save / open (null until the first status lands).
  const [saved, setSaved] = useState<{ backend: string; shell: string } | null>(null);

  // ---- shell blob in / out ---------------------------------------------
  const shellBlob = useMemo<ShellBlob>(() => ({
    ...wb.exportShell(),
    viewSettings: { scheme: view.scheme, contrast: view.contrast, brightness: view.brightness },
    expiryFormat: expiry.format,
    nodeSources: nodeSources.policy,
  }), [wb, view.scheme, view.contrast, view.brightness, expiry.format, nodeSources.policy]);
  const shellHash = useMemo(() => hashShell(shellBlob), [shellBlob]);
  const shellRef = useRef(shellBlob);
  shellRef.current = shellBlob;

  const applyShell = useCallback((blob: ShellBlob | null) => {
    if (!blob) return;
    wb.importShell(blob as Parameters<typeof wb.importShell>[0]);
    const vs = blob.viewSettings;
    if (vs) {
      if (typeof vs.scheme === "string") view.setScheme(vs.scheme as ColorScheme);
      if (typeof vs.contrast === "number") view.setContrast(vs.contrast);
      if (typeof vs.brightness === "number") view.setBrightness(vs.brightness);
    }
    if (EXPIRY_FORMATS.some((f) => f.id === blob.expiryFormat)) expiry.setFormat(blob.expiryFormat as ExpiryFormat);
    const ns = blob.nodeSources as { mode?: string; overrides?: Record<string, string> } | undefined;
    if (ns && (ns.mode === "universe" || ns.mode === "per-node")) {
      nodeSources.setMode(ns.mode);
      nodeSources.clearOverrides();
      for (const [k, v] of Object.entries(ns.overrides ?? {})) nodeSources.setOverride(k, v);
    }
  }, [wb, view, expiry, nodeSources]);

  // ---- backend fingerprint (dirty tracking) ---------------------------
  const pollStatus = useCallback(async (): Promise<string | null> => {
    try {
      const s = await api.get<WorkspaceStatus>("/workspace/status");
      setBackendFp(s.fingerprint);
      return s.fingerprint;
    } catch { return null; }
  }, []);
  useEffect(() => {
    if (!live) return;
    void pollStatus();
    const id = window.setInterval(() => { if (!document.hidden) void pollStatus(); }, STATUS_POLL_MS);
    return () => window.clearInterval(id);
  }, [live, pollStatus]);
  // First status = the clean baseline of this session.
  useEffect(() => {
    if (saved === null && backendFp !== null) setSaved({ backend: backendFp, shell: shellHash });
  }, [backendFp, saved, shellHash]);

  const refreshServer = useCallback(() => {
    api.get<ServerList>("/workspaces").then(setServer).catch(() => {});
  }, []);
  useEffect(() => { if (live) refreshServer(); }, [live, refreshServer]);

  const remember = useCallback((entry: RecentEntry) => {
    setRecent((prev) => {
      const next = pushRecent(prev, entry);
      // A file that fell off the list end loses its stored handle (best-effort).
      for (const old of prev) {
        if (old.kind === "file" && !next.some((e) => e.kind === "file" && e.name === old.name)) void deleteHandle(old.name);
      }
      persistRecent(next);
      return next;
    });
  }, []);
  const markClean = useCallback(async () => {
    const fp = (await pollStatus()) ?? backendFp ?? "";
    setSaved({ backend: fp, shell: hashShell(shellRef.current) });
  }, [pollStatus, backendFp]);

  // ---- open ------------------------------------------------------------
  const installBundle = useCallback(async (bundle: WorkspaceBundle, next: WorkspaceTarget) => {
    await api.post("/workspace/import", { body: bundle, timeoutMs: 120_000 });
    applyShell(bundle.shell);
    setTarget(next);
    remember({ kind: next.kind, name: next.name, at: Date.now() });
    await refreshUniverse().catch(() => {});
    reload();
    refreshViews();
    await markClean();
  }, [applyShell, remember, refreshUniverse, reload, refreshViews, markClean]);

  const run = useCallback(async (label: string, fn: () => Promise<string | null>) => {
    if (!live) { noteAction(`${label}: requires the live backend`, false); return; }
    setBusy(true);
    try {
      const done = await fn();
      if (done !== null) noteAction(done);
    } catch (err: unknown) {
      noteAction(`${label} failed: ${messageOf(err)}`, false);
    } finally { setBusy(false); }
  }, [live, noteAction]);

  const openText = useCallback(async (text: string, next: WorkspaceTarget): Promise<string> => {
    let raw: unknown;
    try { raw = JSON.parse(text); } catch { throw new Error("not valid JSON"); }
    const parsed = parseWorkspaceBundle(raw);
    if (!parsed.ok) throw new Error(parsed.error);
    await installBundle(parsed.bundle, next);
    return `Opened workspace ${next.name}`;
  }, [installBundle]);

  const openFile = useCallback((file: File) => run("Open workspace", async () => {
    const name = workspaceNameOf(file.name);
    return openText(await file.text(), { kind: "file", name, handle: null });
  }), [run, openText]);

  const openPicker = useCallback(() => run("Open workspace", async () => {
    if (supportsFilePicker()) {
      const handle = await pickOpenHandle();
      if (handle === null) return null;
      const text = await readHandle(handle);
      if (text === null) throw new Error("permission to read the file was refused");
      const name = workspaceNameOf(handle.name);
      const msg = await openText(text, { kind: "file", name, handle });
      void putHandle(name, handle);
      return msg;
    }
    const file = await promptFile();
    if (file === null) return null;
    return openText(await file.text(), { kind: "file", name: workspaceNameOf(file.name), handle: null });
  }), [run, openText]);

  const openFromServer = useCallback((name: string) => run("Open workspace", async () => {
    const bundle = await api.get<unknown>(`/workspaces/${encodeURIComponent(name)}`);
    const parsed = parseWorkspaceBundle(bundle);
    if (!parsed.ok) throw new Error(parsed.error);
    await installBundle(parsed.bundle, { kind: "server", name });
    return `Opened workspace ${name} (server)`;
  }), [run, installBundle]);

  const openRecent = useCallback(async (entry: RecentEntry) => {
    if (entry.kind === "server") return openFromServer(entry.name);
    const handle = await getHandle(entry.name);
    if (handle === null) return openPicker(); // no stored handle (non-Chromium): pick it
    return run("Open workspace", async () => {
      const text = await readHandle(handle);
      if (text === null) throw new Error("permission to read the file was refused");
      return openText(text, { kind: "file", name: entry.name, handle });
    });
  }, [openFromServer, openPicker, run, openText]);

  // ---- save ------------------------------------------------------------
  const bundleNow = useCallback(async (): Promise<WorkspaceBundle> => {
    const srv = await api.get<ServerBundle>("/workspace/export", { timeoutMs: 120_000 });
    return buildWorkspaceBundle(srv, shellRef.current);
  }, []);

  const saveToServer = useCallback((name: string) => run("Save workspace", async () => {
    const bundle = await bundleNow();
    const res = await api.post<ServerList & { name: string }>(`/workspaces/${encodeURIComponent(name)}`, { body: bundle });
    setServer({ entries: res.entries, storeEnabled: res.storeEnabled });
    setTarget({ kind: "server", name: res.name });
    remember({ kind: "server", name: res.name, at: Date.now() });
    await markClean();
    return `Saved workspace ${res.name} (server)`;
  }), [run, bundleNow, remember, markClean]);

  const saveAs = useCallback(() => run("Save workspace", async () => {
    const bundle = await bundleNow();
    const text = JSON.stringify(bundle, null, 1);
    const suggested = workspaceFilename(target?.name ?? "");
    if (supportsFilePicker()) {
      const handle = await pickSaveHandle(suggested);
      if (handle === null) return null;
      if (!(await writeHandle(handle, text))) throw new Error("could not write the file");
      const name = workspaceNameOf(handle.name);
      setTarget({ kind: "file", name, handle });
      void putHandle(name, handle);
      remember({ kind: "file", name, at: Date.now() });
      await markClean();
      return `Saved workspace ${name}`;
    }
    downloadText(suggested, text);
    const name = workspaceNameOf(suggested);
    setTarget({ kind: "file", name, handle: null });
    remember({ kind: "file", name, at: Date.now() });
    await markClean();
    return `Saved workspace ${name} (download)`;
  }), [run, bundleNow, target, remember, markClean]);

  const save = useCallback(async () => {
    if (target === null) return saveAs();
    if (target.kind === "server") return saveToServer(target.name);
    if (target.handle === null) return saveAs();
    const handle = target.handle;
    return run("Save workspace", async () => {
      const text = JSON.stringify(await bundleNow(), null, 1);
      if (!(await writeHandle(handle, text))) throw new Error("could not write the file");
      remember({ kind: "file", name: target.name, at: Date.now() });
      await markClean();
      return `Saved workspace ${target.name}`;
    });
  }, [target, saveAs, saveToServer, run, bundleNow, remember, markClean]);

  const deleteFromServer = useCallback((name: string) => run("Delete workspace", async () => {
    setServer(await api.delete<ServerList>(`/workspaces/${encodeURIComponent(name)}`));
    setRecent((prev) => { const n = prev.filter((e) => !(e.kind === "server" && e.name === name)); persistRecent(n); return n; });
    if (target?.kind === "server" && target.name === name) setTarget(null);
    return `Deleted workspace ${name} (server)`;
  }), [run, target]);

  const newWorkspace = useCallback(() => run("New workspace", async () => {
    await api.post("/workspace/new", { timeoutMs: 120_000 });
    wb.closeAll();
    setTarget(null);
    await refreshUniverse().catch(() => {});
    reload();
    refreshViews();
    await markClean();
    return "New workspace (defaults)";
  }), [run, wb, refreshUniverse, reload, refreshViews, markClean]);

  const dirty = saved !== null && (backendFp !== saved.backend || shellHash !== saved.shell);
  const value = useMemo<WorkspaceFileValue>(() => ({
    target, name: target?.name ?? "untitled", dirty, busy, recent, server,
    canPickFiles: supportsFilePicker(),
    newWorkspace, openPicker, openFile, openRecent, openFromServer,
    save, saveAs, saveToServer, deleteFromServer, refreshServer,
  }), [target, dirty, busy, recent, server, newWorkspace, openPicker, openFile, openRecent,
    openFromServer, save, saveAs, saveToServer, deleteFromServer, refreshServer]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkspaceFile(): WorkspaceFileValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useWorkspaceFile must be used within WorkspaceFileProvider");
  return ctx;
}

/** Null outside the provider (tests / legacy mounts). */
export function useOptionalWorkspaceFile(): WorkspaceFileValue | null {
  return useContext(Ctx);
}
