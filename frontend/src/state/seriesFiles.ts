// The Series lens's files (2026-09-12): Export remembers the file it saved,
// Open starts in that file's directory and proposes it first, a recent file
// reopens through its stored handle. One external store (useSyncExternalStore,
// no provider) shared by the header, the File menu and the palette rows:
// the recent list (localStorage) plus this session's handles (IndexedDB
// keeps them across reloads, beside the workspace handles). Every verb
// returns what it opened / saved (the viewer shows the note and selects the
// series) and throws a plain Error on failure; null means cancelled.
import { useSyncExternalStore } from "react";
import {
  deleteHandle, downloadText, getHandle, pickOpenHandle, pickSaveHandle, promptFile, putHandle, readHandle,
  supportsFilePicker, writeHandle,
} from "../lib/fileHandles";
import { parseSeriesBundle, seriesFilename } from "../lib/seriesFile";
import {
  SERIES_FILE_DESCRIPTION, SERIES_PICKER_ID, SERIES_RECENT_KEY, pushSeriesRecent, restoreSeriesRecent, seriesHandleKey,
} from "../lib/seriesFiles";
import type { SeriesRecentEntry } from "../lib/seriesFiles";
import type { SeriesDoc } from "../lib/seriesTypes";
import { exportSeriesFile, importSeriesFile, notifySeriesChanged } from "./useSeries";

function load(): SeriesRecentEntry[] {
  try { return restoreSeriesRecent(JSON.parse(localStorage.getItem(SERIES_RECENT_KEY) ?? "[]")); } catch { return []; }
}
function persist(list: SeriesRecentEntry[]): void {
  try { localStorage.setItem(SERIES_RECENT_KEY, JSON.stringify(list)); } catch { /* best-effort */ }
}

let recent: SeriesRecentEntry[] = load();
/** This session's handles by file name (IndexedDB holds them across reloads). */
const handles = new Map<string, FileSystemFileHandle>();
const listeners = new Set<() => void>();
function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
const snapshot = () => recent;

/** The recent series files, the latest first. */
export function useSeriesRecent(): SeriesRecentEntry[] {
  return useSyncExternalStore(subscribe, snapshot, snapshot);
}
export function seriesRecentNow(): SeriesRecentEntry[] {
  return recent;
}

/** Put a file at the head of the list (its handle stored when Chromium gave one). */
export function rememberSeriesFile(entry: SeriesRecentEntry, handle: FileSystemFileHandle | null): void {
  const prev = recent;
  recent = pushSeriesRecent(prev, entry);
  if (handle !== null) {
    handles.set(entry.name, handle);
    void putHandle(seriesHandleKey(entry.name), handle);
  }
  for (const old of prev) {
    if (!recent.some((e) => e.name === old.name)) {
      handles.delete(old.name);
      void deleteHandle(seriesHandleKey(old.name));
    }
  }
  persist(recent);
  listeners.forEach((l) => l());
}

/** Tests / a fresh desk: forget every file. */
export function forgetSeriesFiles(): void {
  recent = [];
  handles.clear();
  persist(recent);
  listeners.forEach((l) => l());
}

async function handleOf(name: string): Promise<FileSystemFileHandle | null> {
  return handles.get(name) ?? (await getHandle(seriesHandleKey(name)));
}

/** The handle the pickers start in: the latest file's, else the most recent
 *  file that has one (a download has none). */
export async function lastSeriesHandle(): Promise<FileSystemFileHandle | null> {
  for (const e of recent) {
    const h = await handleOf(e.name);
    if (h !== null) return h;
  }
  return null;
}

export interface SeriesOpenResult {
  id: string;
  name: string;
  ticker: string;
  frames: number;
}

async function importText(text: string, name: string, handle: FileSystemFileHandle | null): Promise<SeriesOpenResult> {
  let raw: unknown;
  try { raw = JSON.parse(text); } catch { throw new Error("not a JSON file"); }
  const parsed = parseSeriesBundle(raw);
  if (!parsed.ok) throw new Error(parsed.error);
  const doc = await importSeriesFile(raw);
  const entry: SeriesRecentEntry = { name, at: Date.now(), id: doc.id, ticker: doc.spec.ticker, frames: doc.frames.length };
  rememberSeriesFile(entry, handle);
  notifySeriesChanged();
  return { id: doc.id, name, ticker: entry.ticker, frames: entry.frames };
}

/** File ▸ Open series… / the header's Open file…: the picker starts in the
 *  last series file's directory (Chromium also remembers it per picker id).
 *  Null when cancelled. */
export async function openSeriesPicker(): Promise<SeriesOpenResult | null> {
  if (supportsFilePicker()) {
    const handle = await pickOpenHandle({ id: SERIES_PICKER_ID, startIn: await lastSeriesHandle(), description: SERIES_FILE_DESCRIPTION });
    if (handle === null) return null;
    const text = await readHandle(handle);
    if (text === null) throw new Error("permission to read the file was refused");
    return importText(text, handle.name, handle);
  }
  const file = await promptFile();
  if (file === null) return null;
  return importText(await file.text(), file.name, null);
}

/** Reopen a recent file through its stored handle (a permission prompt may
 *  appear); a file without a handle (another browser, a download) goes
 *  through the picker instead. */
export async function openSeriesRecent(entry: SeriesRecentEntry): Promise<SeriesOpenResult | null> {
  const handle = await handleOf(entry.name);
  if (handle === null) return openSeriesPicker();
  const text = await readHandle(handle);
  if (text === null) throw new Error("permission to read the file was refused");
  return importText(text, handle.name, handle);
}

/** A series file dropped on the shell: imported and remembered (with the
 *  drop's handle when the browser hands one over). */
export async function openDroppedSeries(file: File, handle: FileSystemFileHandle | null): Promise<SeriesOpenResult> {
  return importText(await file.text(), file.name, handle);
}

/** The header's Export: save through the picker (Chromium: in the last
 *  file's directory) or as a download, and remember the file so the next
 *  Open proposes it. Returns the file name, null when cancelled. */
export async function exportSeries(seriesId: string, doc: SeriesDoc): Promise<string | null> {
  const bundle = await exportSeriesFile(seriesId);
  const text = JSON.stringify(bundle);
  const suggested = seriesFilename(doc.spec.ticker, doc.spec.name, String(bundle.savedAt ?? ""));
  const entry = (name: string): SeriesRecentEntry => ({
    name, at: Date.now(), id: seriesId, ticker: doc.spec.ticker, frames: doc.frames.length,
  });
  if (supportsFilePicker()) {
    const handle = await pickSaveHandle(suggested, { id: SERIES_PICKER_ID, startIn: await lastSeriesHandle(), description: SERIES_FILE_DESCRIPTION });
    if (handle === null) return null;
    if (!(await writeHandle(handle, text))) throw new Error("could not write the file");
    rememberSeriesFile(entry(handle.name), handle);
    return handle.name;
  }
  downloadText(suggested, text);
  rememberSeriesFile(entry(suggested), null);
  return suggested;
}
