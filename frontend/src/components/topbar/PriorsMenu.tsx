// Priors ▾ — surface snapshots. Three save scopes, narrow to wide:
//   · the VISIBLE tab      POST /smiles/{ticker}/{expiry}/prior (one node)
//   · every OPEN tab       the same endpoint, sequentially per tab
//   · every calibrated fit POST /priors/save-all (useWorkflow.savePriors)
// plus Fetch priors (the freshness ladder, useWorkflow.fetchPriors).
//
// Per-node saves go straight through `api` (they are not workflow verbs);
// individual failures are counted, never fatal, and the session smile is
// reloaded afterwards so the chart's dashed prior refreshes. Every action
// acknowledges on the button face with a transient "… ✓" flash (no toast
// system); the workflow verbs also show the indeterminate WORKING bar.
import { useRef, useState } from "react";
import { Bookmark, ChevronDown } from "lucide-react";
import { api } from "../../state/api";
import { useSmileSession } from "../../state/smileSession";
import { useOptionalWorkbench } from "../../state/workbench";
import type { UseWorkflowResult } from "../../state/useWorkflow";
import { MenuDivider, MenuItem, MenuPanel } from "./Menu";

const BTN =
  "relative flex items-center gap-1.5 overflow-hidden rounded-md border px-2.5 py-1 " +
  "font-medium transition-colors disabled:cursor-not-allowed";
const ACTIVE = "border-slate-700 bg-surface-800 text-slate-200 hover:border-slate-600";
const WORKING = "border-accent-500/50 bg-accent-500/10 text-accent-300";
const FLASH = "border-emerald-500/50 bg-emerald-500/10 text-emerald-300";

/** Subtle indeterminate "working" cue overlaid on the in-flight button. */
function WorkingBar() {
  return (
    <span className="pointer-events-none absolute inset-x-0 bottom-0 h-0.5 overflow-hidden bg-accent-500/15">
      <span className="volfit-indeterminate-fill bg-accent-400" />
    </span>
  );
}

interface NodeRef {
  ticker: string;
  expiry: string;
}

/** Save each node's current fit as its prior, one POST after another.
 *  Resolves to the (saved, failed) tally — a failure never aborts the run. */
async function saveNodePriors(nodes: NodeRef[]): Promise<{ saved: number; failed: number }> {
  let saved = 0;
  let failed = 0;
  for (const { ticker, expiry } of nodes) {
    try {
      await api.post<{ saved: boolean }>(`/smiles/${ticker}/${encodeURIComponent(expiry)}/prior`);
      saved++;
    } catch {
      failed++;
    }
  }
  return { saved, failed };
}

export default function PriorsMenu({
  workflow,
  live,
}: {
  workflow: UseWorkflowResult;
  /** Live backend (per-node saves need a fit session; mock has none). */
  live: boolean;
}) {
  const { pending, busy, priors, savePriors, fetchPriors } = workflow;
  const { reload } = useSmileSession();
  const wb = useOptionalWorkbench();
  const activeTab = wb?.activeTab ?? null;
  const tabs = wb?.tabs ?? [];

  const savedTickers = priors?.tickers.filter((t) => t.nodeCount > 0).length ?? 0;
  const activePriors = priors?.tickers.filter((t) => t.activeSource).length ?? 0;
  const priorsBusy = pending === "savePriors" || pending === "fetchPriors";

  const [open, setOpen] = useState(false);
  // Per-node saves in flight (not a workflow verb, so not in `pending`).
  const [saving, setSaving] = useState(false);
  const working = priorsBusy || saving;

  // Transient "✓" acknowledgments on the face: tells the user the action ran.
  const [flash, setFlash] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const showFlash = (text: string) => {
    setFlash(text);
    timers.current.push(window.setTimeout(() => setFlash(null), 2400));
  };

  const onSaveNodes = (nodes: NodeRef[]) => {
    setOpen(false);
    if (nodes.length === 0) return;
    setSaving(true);
    void saveNodePriors(nodes)
      .then(({ saved, failed }) => {
        reload(); // the chart's dashed prior follows the new snapshot
        showFlash(
          saved > 0
            ? `Saved ${saved} ✓${failed > 0 ? ` · ${failed} failed` : ""}`
            : "Save failed",
        );
      })
      .finally(() => setSaving(false));
  };
  const onSaveAll = () => {
    setOpen(false);
    void savePriors().then((r) => {
      if (r) showFlash(r.nodes > 0 ? `Saved ${r.nodes} ✓` : "Nothing to save");
    });
  };
  const onFetchPriors = () => {
    setOpen(false);
    void fetchPriors().then((r) => {
      if (r) {
        const active = r.tickers.filter((t) => t.source !== "none").length;
        showFlash(active > 0 ? `Activated ${active} ✓` : "No prior found");
      }
    });
  };

  const itemsDisabled = busy || saving;
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={busy && !priorsBusy}
        title="Prior surfaces (save / fetch)"
        className={`${BTN} ${flash ? FLASH : working ? WORKING : ACTIVE}`}
      >
        <Bookmark size={13} strokeWidth={1.75} className="opacity-80" />
        {flash ?? "Priors"}
        <ChevronDown size={11} className="text-slate-500" />
        {working && <WorkingBar />}
      </button>
      <MenuPanel open={open} onClose={() => setOpen(false)} width="w-72">
        <MenuItem
          label="Save prior — visible tab"
          detail={activeTab ? `${activeTab.ticker} ${activeTab.expiry}` : "no tab open"}
          disabled={itemsDisabled || !live || activeTab === null}
          onClick={() => onSaveNodes(activeTab ? [activeTab] : [])}
        />
        <MenuItem
          label="Save priors — all open tabs"
          detail={`${tabs.length} tab${tabs.length === 1 ? "" : "s"}`}
          disabled={itemsDisabled || !live || tabs.length === 0}
          onClick={() => onSaveNodes(tabs)}
        />
        <MenuItem
          label="Save priors — all calibrated"
          detail={savedTickers > 0 ? `${savedTickers} ticker(s) saved` : "snapshot all fits"}
          disabled={itemsDisabled}
          onClick={onSaveAll}
        />
        <MenuDivider />
        <MenuItem
          label="Fetch priors"
          detail={
            savedTickers === 0
              ? "save priors first"
              : activePriors > 0
                ? `${activePriors} active`
                : "saved → 15m-before-close → close"
          }
          disabled={itemsDisabled || savedTickers === 0}
          onClick={onFetchPriors}
        />
      </MenuPanel>
    </div>
  );
}
