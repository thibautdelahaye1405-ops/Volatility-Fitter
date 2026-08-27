// Universe ▾ menu (UI SHELL v2, top-left main menu): the universe as a named
// object — open the Manage-universe dialog, save the active set under a name
// (inline form), reload a saved one. Deliberately slim: market-data pulls,
// the calibration scopes and priors live in the command center, and the data
// source is picked in the dialog's Data-sources card (or the status bar).
// Rows are registry commands (CommandRow; wave 3, C4) — the saved-universe
// list is the DYNAMIC "universe.load:<name>" family.
import { useState } from "react";
import { Database, FolderOpen, Save } from "lucide-react";
import MenuButton from "./MenuButton";
import CommandRow from "../CommandRow";
import { MenuDivider, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkflowContext } from "../../../state/workflowContext";
import { useUniverse } from "../../../state/useUniverse";
import { useCommands } from "../../../state/commands";
import { DYNAMIC } from "../../../lib/commands";

const inputClass =
  "min-w-0 flex-1 rounded-md border border-slate-700 bg-surface-900 px-2 py-1 text-xs " +
  "text-slate-100 outline-none placeholder:text-slate-600 hover:border-slate-600 focus:border-accent-500";
const saveBtn =
  "flex shrink-0 items-center gap-1 rounded-md border border-slate-700 bg-surface-900 px-2 py-1 " +
  "text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

export default function UniverseMenu() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const { live } = useWorkflowContext();
  const { saved, busy } = useUniverse();
  const { commands, run } = useCommands();
  const close = () => setOpen(false);
  const storeOn = live && saved.storeEnabled;
  const saving = busy !== null && busy.startsWith("save:");
  const loadRows = commands.filter((c) => c.id.startsWith(DYNAMIC.universeLoad));

  const submit = () => {
    const n = name.trim();
    if (n === "" || busy !== null) return;
    run("universe.saveAs", n);
    setName("");
  };

  return (
    <div className="relative">
      <MenuButton label="Universe" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-72">
        <CommandRow id="universe.manage" icon={Database} after={close} />

        <MenuDivider />
        <MenuSection label="Save universe as…" />
        {storeOn ? (
          // Inline form: Enter or the Save button persists, the panel stays
          // open so the new name shows up in the list below.
          <form
            className="flex items-center gap-1.5 px-3 pb-2"
            onSubmit={(e) => { e.preventDefault(); submit(); }}
          >
            <input
              className={inputClass}
              placeholder="name…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-label="Universe name"
            />
            <button type="submit" className={saveBtn} disabled={name.trim() === "" || busy !== null}>
              <Save size={11} strokeWidth={1.75} className="opacity-80" />
              {saving ? "Saving…" : "Save"}
            </button>
          </form>
        ) : (
          <p className="px-3 pb-2 text-[10px] text-slate-500">
            {live ? (
              <>
                Set <span className="font-mono">VOLFIT_DB</span> on the server to save and load named
                universes.
              </>
            ) : (
              "Requires the live backend."
            )}
          </p>
        )}

        <MenuDivider />
        <MenuSection label="Load saved universe" />
        {loadRows.length === 0 ? (
          <p className="px-3 pb-2 text-[10px] text-slate-500">No saved universes yet.</p>
        ) : (
          loadRows.map((c) => {
            const n = c.id.slice(DYNAMIC.universeLoad.length);
            return (
              <CommandRow key={c.id} id={c.id} icon={FolderOpen} label={n}
                detail={busy === `load:${n}` ? "loading…" : ""} after={close} />
            );
          })
        )}
      </MenuPanel>
    </div>
  );
}
