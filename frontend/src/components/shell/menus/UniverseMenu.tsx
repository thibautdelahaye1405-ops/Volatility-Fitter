// Universe ▾ menu (UI SHELL v2, top-left main menu): everything that acts on
// the universe as a whole — market-data pulls, the three calibration scopes,
// prior snapshots, the Universe dialog, saved universes and the data source.
// The rows mirror the top-centre command center (same workflow actions), so
// a user who prefers menus never has to hunt for a button.
import { useState } from "react";
import { Database, FolderOpen } from "lucide-react";
import MenuButton from "./MenuButton";
import { MenuDivider, MenuItem, MenuPanel, MenuSection } from "../../topbar/Menu";
import { useWorkflowContext } from "../../../state/workflowContext";
import { useWorkbench } from "../../../state/workbench";
import { useUniverse } from "../../../state/useUniverse";
import { CALIB_SCOPES, SCOPE_LABEL, scopeBadge, scopeDetail } from "../../../lib/calibScope";
import type { SourceStatus } from "../../../state/useDataSources";

const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-rose-500",
};

export default function UniverseMenu() {
  const [open, setOpen] = useState(false);
  const { live, workflow, dataSources } = useWorkflowContext();
  const wb = useWorkbench();
  const { saved, loadUniverse, busy: uniBusy } = useUniverse();
  const { calib, sched, busy, fetchSnapshot, fetchSpots, fetchOptions,
    calibrate, calibrateParametric, calibrateLv, savePriors, fetchPriors, priors } = workflow;
  const running = calib?.running ?? false;
  const stale = calib?.staleNodes ?? 0;
  const lvStale = calib?.lvStaleTickers ?? 0;
  const lvEnabled = sched?.localVolEnabled ?? true;
  const realtimeSpots = sched?.spotMode === "realtime";
  const autoOptions = sched?.optionsFetchMode === "auto";
  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;
  const close = () => setOpen(false);
  const run = (fn: () => Promise<unknown>) => {
    close();
    void fn();
  };

  return (
    <div className="relative">
      <MenuButton label="Universe" chevron active={open} onClick={() => setOpen((v) => !v)} />
      <MenuPanel open={open} onClose={close} width="w-[23rem]">
        <MenuSection label="Market data" />
        <MenuItem
          label="Fetch snapshot"
          detail="quotes + spot in one pull"
          disabled={!live || busy}
          onClick={() => run(fetchSnapshot)}
        />
        <MenuItem
          label={realtimeSpots ? "Fetch spots · real-time" : "Fetch spots"}
          detail={realtimeSpots ? "streaming (Options)" : "refresh live spots"}
          disabled={!live || busy || realtimeSpots}
          onClick={() => run(fetchSpots)}
        />
        <MenuItem
          label={autoOptions ? "Fetch option quotes · auto" : "Fetch option quotes"}
          detail={autoOptions ? "on a timer (status bar)" : "fresh chains now"}
          disabled={!live || busy || autoOptions}
          onClick={() => run(fetchOptions)}
        />

        <MenuDivider />
        <MenuSection label="Calibrate" />
        {CALIB_SCOPES.map((scope) => {
          const n = scopeBadge(scope, stale, lvStale);
          const fn = scope === "both" ? calibrate : scope === "parametric" ? calibrateParametric : calibrateLv;
          return (
            <MenuItem
              key={scope}
              label={n > 0 ? `${SCOPE_LABEL[scope]} (${n})` : SCOPE_LABEL[scope]}
              detail={scopeDetail(scope, stale, lvStale, lvEnabled)}
              disabled={!live || busy || running}
              onClick={() => run(fn)}
            />
          );
        })}

        <MenuDivider />
        <MenuSection label="Priors" />
        <MenuItem
          label="Save priors"
          detail={savedTickers > 0 ? `${savedTickers} ticker(s) saved` : "snapshot all fits"}
          disabled={!live || busy}
          onClick={() => run(savePriors)}
        />
        <MenuItem
          label="Fetch priors"
          detail={savedTickers === 0 ? "save priors first" : "saved → 15m-before-close → close"}
          disabled={!live || busy || savedTickers === 0}
          onClick={() => run(fetchPriors)}
        />

        <MenuDivider />
        <MenuItem
          icon={Database}
          label="Manage universe…"
          detail="tickers · expiries"
          shortcut="Ctrl+Shift+U"
          onClick={() => { close(); wb.openDialog("universe"); }}
        />
        {saved.storeEnabled && saved.names.length > 0 && (
          <>
            <MenuSection label="Load saved universe" />
            {saved.names.map((name) => (
              <MenuItem
                key={name}
                icon={FolderOpen}
                label={name}
                disabled={!live || uniBusy !== null}
                detail={uniBusy === `load:${name}` ? "loading…" : undefined}
                onClick={() => { close(); void loadUniverse(name); }}
              />
            ))}
          </>
        )}

        {dataSources.sources.length > 0 && (
          <>
            <MenuDivider />
            <MenuSection label="Data source" />
            {dataSources.sources.map((s) => {
              const unavailable = s.status === "red";
              return (
                <button
                  key={s.id}
                  disabled={unavailable}
                  onClick={() => { close(); void dataSources.switchSource(s.id); }}
                  title={unavailable ? `${s.label}: ${s.detail}` : undefined}
                  className={[
                    "flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-xs transition-colors",
                    unavailable
                      ? "cursor-not-allowed text-slate-500"
                      : s.id === dataSources.active
                        ? "bg-accent-500/10 text-accent-300"
                        : "text-slate-300 hover:bg-slate-700/40",
                  ].join(" ")}
                >
                  <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} />
                  <span className="flex-1 font-medium">{s.label}</span>
                  <span className="truncate text-[10px] text-slate-500">{s.detail}</span>
                </button>
              );
            })}
          </>
        )}
      </MenuPanel>
    </div>
  );
}
