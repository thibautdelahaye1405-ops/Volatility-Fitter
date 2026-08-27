// File ▾ menu (UI SHELL v2 wave 3, A1) — top-left, before Options: the
// whole configuration as a FILE. New workspace (two-step confirm) · Open…
// (Ctrl+O; drag-and-drop a .json onto the shell works too) · Save (Ctrl+S,
// last target) · Save as… (Ctrl+Shift+S; Chromium file picker, else a
// download) · Save to server… (inline name, VOLFIT_DB) · Open from server ▸ ·
// Recent ▸ (last 8; Chromium reopens files after a permission re-prompt,
// other browsers re-prompt the picker). State + verbs: state/workspaceFile.
import { useState } from "react";
import { Clock, Download, FilePlus, FolderOpen, Save, Server, Trash2 } from "lucide-react";
import MenuButton from "./MenuButton";
import { MenuDivider, MenuItem, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkflowContext } from "../../../state/workflowContext";
import { useWorkspaceFile } from "../../../state/workspaceFile";

const inputClass =
  "min-w-0 flex-1 rounded-md border border-slate-700 bg-surface-900 px-2 py-1 text-xs " +
  "text-slate-100 outline-none placeholder:text-slate-600 hover:border-slate-600 focus:border-accent-500";
const smallBtn =
  "flex shrink-0 items-center gap-1 rounded-md border border-slate-700 bg-surface-900 px-2 py-1 " +
  "text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

function fmtStamp(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" });
}

export default function FileMenu() {
  const [open, setOpen] = useState(false);
  const [confirmNew, setConfirmNew] = useState(false);
  const [serverName, setServerName] = useState("");
  const { live } = useWorkflowContext();
  const ws = useWorkspaceFile();
  const close = () => { setOpen(false); setConfirmNew(false); };
  const storeOn = live && ws.server.storeEnabled;
  const disabled = !live || ws.busy;

  const submitServer = () => {
    const n = serverName.trim();
    if (n === "" || disabled) return;
    void ws.saveToServer(n);
    setServerName("");
  };

  return (
    <div className="relative">
      <MenuButton label="File" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-72">
        {confirmNew ? (
          <div className="px-3 py-2">
            <p className="mb-2 text-[11px] text-slate-300">
              Reset the workspace? Options return to their defaults; quote edits, priors, overrides and the
              open tabs are cleared. The universe keeps its tickers.
            </p>
            <div className="flex gap-1.5">
              <button className={`${smallBtn} border-rose-500/50 text-rose-300`} disabled={disabled}
                onClick={() => { close(); void ws.newWorkspace(); }}>
                Reset
              </button>
              <button className={smallBtn} onClick={() => setConfirmNew(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          <MenuItem icon={FilePlus} label="New workspace" detail="defaults" disabled={disabled}
            onClick={() => setConfirmNew(true)} />
        )}
        <MenuItem icon={FolderOpen} label="Open…" shortcut="Ctrl+O" detail="or drop a .json"
          disabled={disabled} onClick={() => { close(); void ws.openPicker(); }} />
        <MenuDivider />
        <MenuItem icon={Save} label="Save" shortcut="Ctrl+S"
          detail={ws.target ? `${ws.target.name}${ws.dirty ? " · unsaved" : ""}` : "untitled"}
          disabled={disabled} onClick={() => { close(); void ws.save(); }} />
        <MenuItem icon={Download} label="Save as…" shortcut="Ctrl+Shift+S"
          detail={ws.canPickFiles ? "file picker" : "download"}
          disabled={disabled} onClick={() => { close(); void ws.saveAs(); }} />

        <MenuDivider />
        <MenuSection label="Save to server…" />
        {storeOn ? (
          <form className="flex items-center gap-1.5 px-3 pb-2" onSubmit={(e) => { e.preventDefault(); submitServer(); }}>
            <input className={inputClass} placeholder="name…" value={serverName} aria-label="Workspace name"
              onChange={(e) => setServerName(e.target.value)} />
            <button type="submit" className={smallBtn} disabled={serverName.trim() === "" || disabled}>
              <Server size={11} strokeWidth={1.75} className="opacity-80" />
              Save
            </button>
          </form>
        ) : (
          <p className="px-3 pb-2 text-[10px] text-slate-500">
            {live ? <>Set <span className="font-mono">VOLFIT_DB</span> on the server to store named workspaces.</>
              : "Requires the live backend."}
          </p>
        )}
        {storeOn && (
          <>
            <MenuSection label="Open from server" />
            {ws.server.entries.length === 0 ? (
              <p className="px-3 pb-2 text-[10px] text-slate-500">No saved workspaces yet.</p>
            ) : (
              ws.server.entries.map((e) => (
                <div key={e.name} className="group flex items-center">
                  <div className="min-w-0 flex-1">
                    <MenuItem icon={Server} label={e.name} detail={fmtStamp(e.savedTs)} disabled={disabled}
                      active={ws.target?.kind === "server" && ws.target.name === e.name}
                      onClick={() => { close(); void ws.openFromServer(e.name); }} />
                  </div>
                  <button className="mr-2 rounded p-1 text-slate-600 opacity-0 transition-opacity hover:text-rose-300 group-hover:opacity-100"
                    title={`Delete "${e.name}" from the server`} aria-label={`Delete workspace ${e.name}`}
                    disabled={disabled} onClick={() => void ws.deleteFromServer(e.name)}>
                    <Trash2 size={12} strokeWidth={1.75} />
                  </button>
                </div>
              ))
            )}
          </>
        )}

        <MenuDivider />
        <MenuSection label="Recent" />
        {ws.recent.length === 0 ? (
          <p className="px-3 pb-2 text-[10px] text-slate-500">No recent workspaces.</p>
        ) : (
          ws.recent.map((r) => (
            <MenuItem key={`${r.kind}:${r.name}`} icon={r.kind === "server" ? Server : Clock} label={r.name}
              detail={r.kind === "server" ? "server" : ws.canPickFiles ? "file" : "file · re-pick"}
              disabled={disabled} onClick={() => { close(); void ws.openRecent(r); }} />
          ))
        )}
      </MenuPanel>
    </div>
  );
}
