// Snapshot FILES (UI SHELL v2 wave 3, A2): quotes + prevailing calibrations
// as a file, and the `file` data source that serves them back.
//
//   saveSnapshot   POST /snapshot/export (cached chains + committed fits —
//                  never fetches / refits) → Chromium file picker or download
//   openPicker /   POST /snapshot/import?name= → the backend registers /
//   openFile       extends the `file` data source, switches to it, points
//                  the universe at the file's tickers and reinstalls the
//                  embedded calibrations (provenance "loaded"); the shell
//                  then refreshes the sources, the universe and every view.
// Outcomes land in the status bar's "Last" chip (noteAction). Mounted inside
// WorkspaceFileProvider (App.tsx) — the File menu, the command registry and
// the Data-sources card all read this one context.
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, ApiError } from "./api";
import { useSmileSession } from "./smileSession";
import { useWorkflowContext } from "./workflowContext";
import { parseSnapshotBundle, snapshotFilename, snapshotNameOf } from "../lib/snapshotFile";
import {
  downloadText, pickOpenHandle, pickSaveHandle, promptFile, readHandle, supportsFilePicker, writeHandle,
} from "../lib/fileHandles";

interface ImportResult { source: string; label: string; asOf: string; tickers: string[]; calibrations: number; failed: string[] }

export interface SnapshotFileValue {
  busy: boolean;
  /** Ctrl+Alt+S: the loaded chains + committed fits → a file. */
  saveSnapshot: () => Promise<void>;
  openPicker: () => Promise<void>;
  /** A dropped / chosen snapshot File (already classified by schema). */
  openFile: (file: File) => Promise<void>;
  /** Raw JSON text + a display name (the drop router reads the text first). */
  openText: (text: string, name: string) => Promise<void>;
}

const Ctx = createContext<SnapshotFileValue | null>(null);

function messageOf(err: unknown): string {
  if (err instanceof ApiError) {
    try {
      const d = (JSON.parse(err.body) as { detail?: unknown }).detail;
      if (typeof d === "string") return d;
    } catch { /* non-JSON */ }
  }
  return err instanceof Error ? err.message : String(err);
}

export function SnapshotFileProvider({ children }: { children: ReactNode }) {
  const { refreshUniverse, reload, refreshViews } = useSmileSession();
  const { live, workflow, dataSources } = useWorkflowContext();
  const { noteAction } = workflow;
  const [busy, setBusy] = useState(false);

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

  const importText = useCallback(async (text: string, name: string): Promise<string> => {
    let raw: unknown;
    try { raw = JSON.parse(text); } catch { throw new Error("not valid JSON"); }
    const parsed = parseSnapshotBundle(raw);
    if (!parsed.ok) throw new Error(parsed.error);
    const res = await api.post<ImportResult>("/snapshot/import", { params: { name }, body: raw, timeoutMs: 300_000 });
    dataSources.refresh();
    await refreshUniverse().catch(() => {});
    reload();
    refreshViews();
    const failed = res.failed.length > 0 ? ` · ${res.failed.length} fit${res.failed.length === 1 ? "" : "s"} not reinstalled` : "";
    return `Opened snapshot ${name} (${res.tickers.length} ticker${res.tickers.length === 1 ? "" : "s"}, ${res.calibrations} calibration${res.calibrations === 1 ? "" : "s"}${failed})`;
  }, [dataSources, refreshUniverse, reload, refreshViews]);

  const openText = useCallback((text: string, name: string) => run("Open snapshot", () => importText(text, name)), [run, importText]);
  const openFile = useCallback((file: File) => run("Open snapshot", async () => importText(await file.text(), snapshotNameOf(file.name))), [run, importText]);
  const openPicker = useCallback(() => run("Open snapshot", async () => {
    if (supportsFilePicker()) {
      const handle = await pickOpenHandle();
      if (handle === null) return null;
      const text = await readHandle(handle);
      if (text === null) throw new Error("permission to read the file was refused");
      return importText(text, snapshotNameOf(handle.name));
    }
    const file = await promptFile();
    if (file === null) return null;
    return importText(await file.text(), snapshotNameOf(file.name));
  }), [run, importText]);

  const saveSnapshot = useCallback(() => run("Save snapshot", async () => {
    const bundle = await api.post<{ asOf: string | null; manifest: { tickers: string[] } }>("/snapshot/export", { body: {}, timeoutMs: 120_000 });
    const text = JSON.stringify(bundle);
    const suggested = snapshotFilename(bundle.manifest.tickers, bundle.asOf ?? "");
    if (supportsFilePicker()) {
      const handle = await pickSaveHandle(suggested);
      if (handle === null) return null;
      if (!(await writeHandle(handle, text))) throw new Error("could not write the file");
      return `Saved snapshot ${snapshotNameOf(handle.name)} (${bundle.manifest.tickers.length} tickers)`;
    }
    downloadText(suggested, text);
    return `Saved snapshot ${snapshotNameOf(suggested)} (download)`;
  }), [run]);

  const value = useMemo<SnapshotFileValue>(
    () => ({ busy, saveSnapshot, openPicker, openFile, openText }),
    [busy, saveSnapshot, openPicker, openFile, openText],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSnapshotFile(): SnapshotFileValue {
  const ctx = useContext(Ctx);
  if (ctx === null) throw new Error("useSnapshotFile must be used within SnapshotFileProvider");
  return ctx;
}

/** Null outside the provider (tests / legacy mounts). */
export function useOptionalSnapshotFile(): SnapshotFileValue | null {
  return useContext(Ctx);
}
