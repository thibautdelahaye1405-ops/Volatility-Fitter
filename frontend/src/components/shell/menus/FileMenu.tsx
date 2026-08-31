// File ▾ menu (UI SHELL v2 wave 3, A1 + C4) — top-left, before Options: the
// whole configuration as a FILE. Every row is a registry command rendered
// through CommandRow (so Ctrl+K lists the same verbs): New workspace
// (two-step confirm) · Open… (Ctrl+O; drag-and-drop a .json works too) ·
// Save (Ctrl+S, last target) · Save as… (Ctrl+Shift+S; Chromium file picker,
// else a download) · Save to server… (inline name, VOLFIT_DB) · Open from
// server ▸ (dynamic commands) · Recent ▸ (last 8) · Snapshots: Save snapshot…
// (Ctrl+Alt+S; quotes + prevailing calibrations) / Open snapshot… (becomes the
// File data source; A2) · Export: surfaces JSON / CSV, quality report HTML,
// the active chart as PNG (A3). State + verbs: state/workspaceFile,
// state/snapshotFile, state/commands.
import { useState } from "react";
import { Camera, Clock, Download, FileImage, FilePlus, FileSpreadsheet, FileText, FolderOpen, Save, Server, Trash2 } from "lucide-react";
import MenuButton from "./MenuButton";
import CommandRow from "../CommandRow";
import { MenuDivider, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkflowContext } from "../../../state/workflowContext";
import { useWorkspaceFile } from "../../../state/workspaceFile";
import { useCommands } from "../../../state/commands";
import { DYNAMIC } from "../../../lib/commands";

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
  const { commands, run } = useCommands();
  const close = () => { setOpen(false); setConfirmNew(false); };
  const storeOn = live && ws.server.storeEnabled;
  const disabled = !live || ws.busy;
  const serverRows = commands.filter((c) => c.id.startsWith(DYNAMIC.workspaceServer));
  const recentRows = commands.filter((c) => c.id.startsWith(DYNAMIC.workspaceRecent));

  const submitServer = () => {
    const n = serverName.trim();
    if (n === "" || disabled) return;
    run("file.saveToServer", n);
    setServerName("");
  };

  return (
    <div className="relative" data-tour="menu.file">
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
                onClick={() => { close(); run("file.new"); }}>
                Reset
              </button>
              <button className={smallBtn} onClick={() => setConfirmNew(false)}>Cancel</button>
            </div>
          </div>
        ) : (
          // New is the one row that confirms before running (the registry
          // command resets straight away — the palette is an expert path).
          <CommandRow id="file.new" icon={FilePlus} intercept={() => setConfirmNew(true)} />
        )}
        <CommandRow id="file.open" icon={FolderOpen} after={close} />
        <MenuDivider />
        <CommandRow id="file.save" icon={Save} after={close}
          detail={ws.target ? `${ws.target.name}${ws.dirty ? " · unsaved" : ""}` : "untitled"} />
        <CommandRow id="file.saveAs" icon={Download} after={close} detail={ws.canPickFiles ? "file picker" : "download"} />

        <MenuDivider />
        <MenuSection label="Snapshots — quotes + calibrations" />
        <CommandRow id="file.saveSnapshot" icon={Camera} after={close} />
        <CommandRow id="file.openSnapshot" icon={FolderOpen} after={close} />

        <MenuDivider />
        <MenuSection label="Export" />
        <CommandRow id="export.surfacesJson" icon={FileText} after={close} />
        <CommandRow id="export.surfacesCsv" icon={FileSpreadsheet} after={close} />
        <CommandRow id="export.report" icon={FileText} after={close} />
        <CommandRow id="export.chartPng" icon={FileImage} after={close} />

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
            {serverRows.length === 0 ? (
              <p className="px-3 pb-2 text-[10px] text-slate-500">No saved workspaces yet.</p>
            ) : (
              serverRows.map((c) => {
                const name = c.id.slice(DYNAMIC.workspaceServer.length);
                return (
                  <div key={c.id} className="group flex items-center">
                    <div className="min-w-0 flex-1">
                      <CommandRow id={c.id} icon={Server} label={name} detail={fmtStamp(c.detail ?? "")} after={close} />
                    </div>
                    <button className="mr-2 rounded p-1 text-slate-600 opacity-0 transition-opacity hover:text-rose-300 group-hover:opacity-100"
                      title={`Delete "${name}" from the server`} aria-label={`Delete workspace ${name}`}
                      disabled={disabled} onClick={() => run(`${DYNAMIC.workspaceDelete}${name}`)}>
                      <Trash2 size={12} strokeWidth={1.75} />
                    </button>
                  </div>
                );
              })
            )}
          </>
        )}

        <MenuDivider />
        <MenuSection label="Recent" />
        {recentRows.length === 0 ? (
          <p className="px-3 pb-2 text-[10px] text-slate-500">No recent workspaces.</p>
        ) : (
          recentRows.map((c) => (
            <CommandRow key={c.id} id={c.id} icon={c.detail === "server" ? Server : Clock}
              label={c.label.replace(/^Open recent: /, "")}
              detail={c.detail === "server" ? "server" : ws.canPickFiles ? "file" : "file · re-pick"} after={close} />
          ))
        )}
      </MenuPanel>
    </div>
  );
}
