// Help ▸ About (UI SHELL v2 + HELP CENTER ARC): what this build is, where the
// backend lives, the product statement, and the support actions — Copy
// diagnostics (a plain-text bundle for a support request), What's new,
// Documentation, plus the two chords worth remembering (F1, Ctrl+K).
import { useState } from "react";
import { ClipboardCopy, Library, Megaphone } from "lucide-react";
import Dialog from "../Dialog";
import { API_BASE_URL } from "../../../state/api";
import { useWorkflowContext } from "../../../state/workflowContext";
import { useHelp } from "../../../state/help";
import { useDiagnosticsSnapshot } from "../../../state/useDiagnostics";
import { copyText, formatDiagnostics } from "../../../lib/help/diagnostics";
import { APP_VERSION, BUILD_MODE, STACK } from "../../../lib/appInfo";

export default function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { live, dataSources } = useWorkflowContext();
  const help = useHelp();
  const snapshot = useDiagnosticsSnapshot();
  const [copied, setCopied] = useState<null | boolean>(null);
  const source = dataSources.sources.find((s) => s.id === dataSources.active);

  const copy = () => {
    void copyText(formatDiagnostics(snapshot())).then((ok) => {
      setCopied(ok);
      window.setTimeout(() => setCopied(null), 1800);
    });
  };
  const action = "flex items-center gap-1.5 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 hover:border-slate-600 hover:text-slate-100";

  return (
    <Dialog open={open} onClose={onClose} title="About VolFit" width="w-[min(96vw,32rem)]" height="h-auto">
      <div className="flex flex-col gap-4 p-5 text-xs text-slate-300">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-600/20 font-mono text-xl font-bold text-accent-400">σ</span>
          <div>
            <div className="text-sm font-semibold text-slate-100">VolFit workbench</div>
            <div className="text-[11px] text-slate-500">v{APP_VERSION} · {BUILD_MODE} build · {STACK}</div>
          </div>
        </div>
        <p className="leading-relaxed text-slate-400">
          Implied-volatility surface fitter — arbitrage-free parametric smiles (LQD, SVI-JW, MCS) and direct
          local-volatility surfaces — with graph extrapolation of sparse observations across expiries and underliers.
        </p>
        <dl className="grid grid-cols-[6rem_1fr] gap-y-1 font-mono text-[11px]">
          <dt className="text-slate-500">Backend</dt>
          <dd className={live ? "text-emerald-400" : "text-amber-400"}>{API_BASE_URL} · {live ? "connected" : "offline (mock data)"}</dd>
          <dt className="text-slate-500">Data source</dt>
          <dd>{source ? `${source.label} · ${source.status}` : "—"}</dd>
          <dt className="text-slate-500">Help</dt>
          <dd className="text-slate-400">F1 help for this view · Ctrl+K every command · Ctrl+Shift+/ ask</dd>
        </dl>
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-800 pt-3">
          <button onClick={copy} className={action} title="Copy a plain-text diagnostics bundle for a support request">
            <ClipboardCopy size={13} /> {copied === null ? "Copy diagnostics" : copied ? "Copied ✓" : "Copy failed"}
          </button>
          <button onClick={() => help.openHelp({ page: "whatsnew" })} className={action}><Megaphone size={13} /> What's new</button>
          <button onClick={() => help.openHelp({ page: "docs" })} className={action}><Library size={13} /> Documentation</button>
        </div>
      </div>
    </Dialog>
  );
}
