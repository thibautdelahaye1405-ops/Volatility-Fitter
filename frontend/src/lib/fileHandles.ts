// File-System-Access plumbing for workspace files (UI SHELL v2 wave 3, A1).
//
// Chromium exposes showSaveFilePicker / showOpenFilePicker: a saved file's
// FileSystemFileHandle lets "Save" overwrite in place and "Recent" reopen the
// file after a permission re-prompt. Handles are structured-cloneable, so they
// persist in IndexedDB (store "handles", keyed by workspace name). Other
// browsers get the download / <input type=file> fallbacks; every helper here
// degrades to null / false instead of throwing.

const DB_NAME = "volfit.workspaceHandles";
const STORE = "handles";

type SaveOpts = { suggestedName?: string; types?: { description: string; accept: Record<string, string[]> }[] };
type PickerWindow = Window & {
  showSaveFilePicker?: (o?: SaveOpts) => Promise<FileSystemFileHandle>;
  showOpenFilePicker?: (o?: SaveOpts & { multiple?: boolean }) => Promise<FileSystemFileHandle[]>;
};
type PermissionHandle = FileSystemFileHandle & {
  queryPermission?: (d: { mode: "read" | "readwrite" }) => Promise<PermissionState>;
  requestPermission?: (d: { mode: "read" | "readwrite" }) => Promise<PermissionState>;
};

const JSON_TYPE = [{ description: "VolFit workspace", accept: { "application/json": [".json"] } }];

/** Chromium with the File System Access API. */
export function supportsFilePicker(): boolean {
  return typeof window !== "undefined" && typeof (window as PickerWindow).showSaveFilePicker === "function";
}

/** Save picker → handle, or null when unsupported / cancelled. */
export async function pickSaveHandle(suggestedName: string): Promise<FileSystemFileHandle | null> {
  const w = window as PickerWindow;
  if (typeof w.showSaveFilePicker !== "function") return null;
  try {
    return await w.showSaveFilePicker({ suggestedName, types: JSON_TYPE });
  } catch {
    return null; // AbortError (user cancelled) or a sandboxed context
  }
}

/** Open picker → handle, or null when unsupported / cancelled. */
export async function pickOpenHandle(): Promise<FileSystemFileHandle | null> {
  const w = window as PickerWindow;
  if (typeof w.showOpenFilePicker !== "function") return null;
  try {
    const [h] = await w.showOpenFilePicker({ types: JSON_TYPE, multiple: false });
    return h ?? null;
  } catch {
    return null;
  }
}

/** Write text into a handle; false when the write failed (permission, IO). */
export async function writeHandle(handle: FileSystemFileHandle, text: string): Promise<boolean> {
  try {
    if (!(await ensurePermission(handle, "readwrite"))) return false;
    const w = await handle.createWritable();
    await w.write(text);
    await w.close();
    return true;
  } catch {
    return false;
  }
}

/** Read a handle's file text; null when permission was refused. */
export async function readHandle(handle: FileSystemFileHandle): Promise<string | null> {
  try {
    if (!(await ensurePermission(handle, "read"))) return null;
    return await (await handle.getFile()).text();
  } catch {
    return null;
  }
}

async function ensurePermission(handle: FileSystemFileHandle, mode: "read" | "readwrite"): Promise<boolean> {
  const h = handle as PermissionHandle;
  if (typeof h.queryPermission !== "function") return true;
  if ((await h.queryPermission({ mode })) === "granted") return true;
  if (typeof h.requestPermission !== "function") return false;
  return (await h.requestPermission({ mode })) === "granted";
}

/** Browser download of a text blob (the non-Chromium Save-as path). */
export function downloadText(filename: string, text: string, type = "application/json"): void {
  downloadBlob(filename, new Blob([text], { type }));
}

/** Browser download of any blob (PNG exports, …). */
export function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** <input type=file> prompt → the chosen File (null when cancelled). */
export function promptFile(accept = ".json,application/json"): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = accept;
    input.style.display = "none";
    input.onchange = () => {
      resolve(input.files?.[0] ?? null);
      input.remove();
    };
    // No "cancel" event on every browser: resolve null when focus returns
    // without a change (a short grace period after the dialog closes).
    window.addEventListener(
      "focus",
      () => window.setTimeout(() => { if (document.body.contains(input)) { resolve(null); input.remove(); } }, 600),
      { once: true },
    );
    document.body.appendChild(input);
    input.click();
  });
}

// ---- IndexedDB handle persistence -----------------------------------------
function openDb(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    if (typeof indexedDB === "undefined") return resolve(null);
    try {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

function tx<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T | null> {
  return openDb().then(
    (db) =>
      new Promise((resolve) => {
        if (db === null) return resolve(null);
        try {
          const req = run(db.transaction(STORE, mode).objectStore(STORE));
          req.onsuccess = () => resolve(req.result ?? null);
          req.onerror = () => resolve(null);
        } catch {
          resolve(null);
        }
      }),
  );
}

export function putHandle(name: string, handle: FileSystemFileHandle): Promise<unknown> {
  return tx("readwrite", (s) => s.put(handle, name));
}
export function getHandle(name: string): Promise<FileSystemFileHandle | null> {
  return tx<FileSystemFileHandle>("readonly", (s) => s.get(name));
}
export function deleteHandle(name: string): Promise<unknown> {
  return tx("readwrite", (s) => s.delete(name));
}
