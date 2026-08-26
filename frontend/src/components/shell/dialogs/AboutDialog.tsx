// Help ▸ About (UI SHELL v2): what this build is, where the backend lives,
// and the one-paragraph product statement.
import Dialog from "../Dialog";
import { API_BASE_URL } from "../../../state/api";
import { useWorkflowContext } from "../../../state/workflowContext";

const APP_VERSION = "0.1.0";

export default function AboutDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { live, dataSources } = useWorkflowContext();
  const source = dataSources.sources.find((s) => s.id === dataSources.active);
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="About VolFit"
      width="w-[min(96vw,30rem)]"
      height="h-auto"
    >
      <div className="flex flex-col gap-4 p-5 text-xs text-slate-300">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent-600/20 font-mono text-xl font-bold text-accent-400">
            σ
          </span>
          <div>
            <div className="text-sm font-semibold text-slate-100">VolFit workbench</div>
            <div className="text-[11px] text-slate-500">
              v{APP_VERSION} · {import.meta.env.MODE} build
            </div>
          </div>
        </div>
        <p className="leading-relaxed text-slate-400">
          Implied-volatility surface fitter — arbitrage-free parametric smiles (LQD,
          SVI-JW, MCS) and direct local-volatility surfaces — with graph extrapolation of
          sparse observations across expiries and underliers.
        </p>
        <dl className="grid grid-cols-[6rem_1fr] gap-y-1 font-mono text-[11px]">
          <dt className="text-slate-500">Backend</dt>
          <dd className={live ? "text-emerald-400" : "text-amber-400"}>
            {API_BASE_URL} · {live ? "connected" : "offline (mock data)"}
          </dd>
          <dt className="text-slate-500">Data source</dt>
          <dd>{source ? `${source.label} · ${source.status}` : "—"}</dd>
          <dt className="text-slate-500">Front-end</dt>
          <dd>React 19 · Vite · Tailwind v4</dd>
        </dl>
      </div>
    </Dialog>
  );
}
