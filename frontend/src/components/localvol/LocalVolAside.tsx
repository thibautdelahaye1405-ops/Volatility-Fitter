// Local Vol aside (UI SHELL v2 wave 2): the right-hand column of the Local
// Vol lens — three stacked cards, top to bottom, the same column the
// Parametric lens shows so both lenses read identically:
//   Spot move        SpotPanel wired from the shared smile session (the slider
//                    transports the live surface across every lens; Calibrate
//                    re-anchors) — same wiring as SmileAside
//   Variance swap    VarSwapPanel for the selected expiry (Options-gated), on
//                    the AFFINE payload's own varSwap info
//   Fit diagnostics  fit RMS (smile / surface), the per-expiry fit table (a row
//                    click selects that expiry's node, i.e. opens / focuses its
//                    tab) and the LV calibration trace player
// Rendered by LocalVolViewer only while the workbench layout's `aside` toggle
// is on (or always, outside the shell). Owns nothing but the trace player's
// local UI state; every fit datum and var-swap verb comes down through the
// props, the spot-move state through useSmileSession().
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Play } from "lucide-react";
import LvTracePlayer from "../LvTracePlayer";
import SpotPanel from "../SpotPanel";
import VarSwapPanel from "../VarSwapPanel";
import { useExpiryFormat } from "../../state/expiryFormat";
import { useSmileSession } from "../../state/smileSession";
import { useWorkflowContext } from "../../state/workflowContext";
import { formatExpiry } from "../../lib/expiryFormat";
import { formatPct } from "../../lib/chartScale";
import { cardClass } from "../../lib/ui";
import type { AffineFitResponse, AffineSmile, UseAffineResult } from "../../state/useAffine";
import { fmtBp0 } from "./LocalVolToolbar";

export interface LocalVolAsideProps
  extends Pick<UseAffineResult, "applyVarSwap" | "undoVarSwap" | "redoVarSwap"> {
  ticker: string;
  /** Calibrated payload (null while loading / offline). */
  data: AffineFitResponse | null;
  /** The selected expiry's reconstructed smile (undefined before the fit lands). */
  smile: AffineSmile | undefined;
  /** Index of the selected expiry in data.smiles (highlighted table row). */
  expiryIdx: number;
  /** Select an expiry from the per-expiry table (opens / focuses its node tab). */
  onSelectExpiry: (expiry: string) => void;
  /** Live backend? Spot-move and var-swap edits are disabled in mock mode. */
  live: boolean;
  /** Var-swap quoting enabled (OptionsSettings.varSwapEnabled). */
  varSwapEnabled: boolean;
}

/** One stacked card of the column. */
const Card = ({ children }: { children: ReactNode }) => (
  <section className={`${cardClass} p-4`}>{children}</section>
);

export default function LocalVolAside({
  ticker, data, smile, expiryIdx, onSelectExpiry, live, varSwapEnabled,
  applyVarSwap, undoVarSwap, redoVarSwap,
}: LocalVolAsideProps) {
  const { format } = useExpiryFormat();
  // Spot move is session-wide (one shift per ticker, transported by the
  // backend across every lens) — same source as the Parametric aside.
  const {
    spotReturn, spotState, setSpotReturn, setFollow, recalibrate, probeLive, spotNote,
  } = useSmileSession();
  const { workflow } = useWorkflowContext(); // the background job (Re-anchor progress)
  // Fit replay (V3.5 item 13): the ⏵ toggle + an epoch that advances whenever a
  // fresh affine payload lands, so useLvTrace refetches and auto-replays once.
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceEpoch, setTraceEpoch] = useState(0);
  useEffect(() => {
    if (data && data.hasFit !== false) setTraceEpoch((e) => e + 1);
  }, [data]);

  return (
    <aside className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto">
      {/* (a) Spot move — SpotPanel renders its own "Spot move" title: follow the
          market or the scenario dial (no recalibration); Recalibrate = the
          top-bar Calibrate for this ticker. */}
      <Card>
        <SpotPanel
          spotReturn={spotReturn}
          spotState={spotState}
          onSpotReturn={setSpotReturn}
          onFollow={(f) => void setFollow(f)}
          onCalibrate={(scope) => void recalibrate(scope)}
          onProbeLive={() => void probeLive()}
          calib={workflow.calib}
          note={spotNote}
          disabled={!live}
          disabledReason={!live ? "requires live backend" : undefined}
        />
      </Card>

      {/* (b) Variance swap — VarSwapPanel renders its own title. Quote/session
          shared with Parametric, but the info is the AFFINE payload's own
          varSwap — model/basis/stale from the LV fit. */}
      {varSwapEnabled && smile && (
        <Card>
          <VarSwapPanel
            info={smile.varSwap}
            live={live}
            subtitle={`Editing ${formatExpiry(smile.expiry, smile.t, format)} · model = LV surface fit`}
            onSet={(level) => void applyVarSwap(smile.expiry, "set", level)}
            onExclude={() => void applyVarSwap(smile.expiry, "exclude")}
            onInclude={() => void applyVarSwap(smile.expiry, "include")}
            onRemove={() => void applyVarSwap(smile.expiry, "remove")}
            onUndo={() => void undoVarSwap(smile.expiry)}
            onRedo={() => void redoVarSwap(smile.expiry)}
            onReset={() => void applyVarSwap(smile.expiry, "reset")}
          />
        </Card>
      )}

      {/* (c) Fit diagnostics — RMS, per-expiry table, LV trace player */}
      <Card>
        <h3 className="text-sm font-semibold text-slate-100">Fit diagnostics</h3>
        <p
          className="mt-1 text-[11px] text-slate-500"
          title="Grid size, regularizers and solver are global hyperparameters — set them in Options ▸ Local-Vol surface"
        >
          {ticker !== "" ? `Local-vol surface · ${ticker}` : "Awaiting data…"}
        </p>

        {/* Fit RMS — same calibration-consistent basis + format as Parametric */}
        {data && (
          <div className="mt-3 rounded-lg border border-slate-800 bg-surface-800/40 px-3 py-2">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-slate-500">
              RMS vol error
            </div>
            <div className="flex justify-between font-mono text-[11px] text-slate-300">
              <span className="text-slate-500">smile</span>
              <span>{formatPct(smile?.rmsError, 2)}</span>
            </div>
            <div className="flex justify-between font-mono text-[11px] text-slate-300">
              <span className="text-slate-500">surface</span>
              <span>{formatPct(data.surfaceRmsError, 2)}</span>
            </div>
          </div>
        )}

        {/* Per-expiry diagnostics — a row click selects that expiry's node */}
        <div className="mt-3 border-t border-slate-800 pt-3">
          <h4 className="mb-2 text-xs font-semibold text-slate-200">Per-expiry fit</h4>
          <table className="w-full text-right font-mono text-[10px]">
            <thead>
              <tr className="text-slate-600">
                <th className="pb-1 text-left font-normal">expiry</th>
                <th className="pb-1 font-normal">T</th>
                <th className="pb-1 font-normal">err bp</th>
                <th className="pb-1 font-normal">min φ</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {(data?.smiles ?? []).map((s, i) => (
                <tr
                  key={s.expiry}
                  onClick={() => onSelectExpiry(s.expiry)}
                  className={[
                    "cursor-pointer border-t border-slate-800/60",
                    i === expiryIdx ? "text-accent-400" : "hover:text-slate-100",
                  ].join(" ")}
                >
                  <td className="py-1 text-left text-slate-400">
                    {formatExpiry(s.expiry, s.t, format)}
                  </td>
                  <td>{s.t.toFixed(2)}</td>
                  <td>{fmtBp0(s.maxIvErrorBp)}</td>
                  <td>{(data?.minDensity[i] ?? 0).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[10px] text-slate-600">
            min φ &gt; 0 ⇒ no butterfly arbitrage (Breeden–Litzenberger density).
          </p>
        </div>

        {/* LV calibration trace player + solve-count footer */}
        {data && (
          <div className="mt-3 flex shrink-0 flex-col gap-2">
            {traceOpen && <LvTracePlayer ticker={ticker} epoch={traceEpoch} />}
            <p className="flex items-center gap-1.5 text-[10px] text-slate-600">
              <button
                onClick={() => setTraceOpen((v) => !v)}
                title="Replay the LV calibration (accepted solver steps, post-hoc)"
                className={[
                  "rounded border p-0.5 transition-colors",
                  traceOpen
                    ? "border-violet-500/50 bg-violet-500/10 text-violet-300"
                    : "border-slate-700 bg-surface-800 text-slate-400 hover:border-slate-600 hover:text-slate-200",
                ].join(" ")}
              >
                <Play size={9} strokeWidth={1.75} />
              </button>
              {data.nEvals} PDE solves · price rms{" "}
              {Number.isFinite(data.rmsPriceError) ? (data.rmsPriceError * 1e4).toFixed(1) : "—"} bp
            </p>
          </div>
        )}
      </Card>
    </aside>
  );
}
