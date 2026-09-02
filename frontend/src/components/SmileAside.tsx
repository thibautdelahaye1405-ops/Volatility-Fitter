// Right-hand column of the Parametric lens (UI SHELL v2 wave 2): three
// stacked cards, top to bottom —
//   Spot move        follow the market spot or the scenario dial (transports
//                    every lens live); Recalibrate = the top-bar Calibrate for
//                    this ticker (same scope, same snapshot rule)
//   Variance swap    the var-swap quote editor (adds a calibration penalty;
//                    Options-gated)
//   Fit diagnostics  headline handles (ATM / skew / curvature / RMS) with the
//                    secondary readouts (wings, Lee slopes, var-swap vol)
//                    behind an expander; the displayed model + hyperparameters
//                    as a compact chip (full values in the tooltip)
// Model selection itself lives in Options.
import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import SpotPanel from "./SpotPanel";
import VarSwapPanel from "./VarSwapPanel";
import { useSmileSession } from "../state/smileSession";
import { useWorkflowContext } from "../state/workflowContext";
import { formatPct } from "../lib/chartScale";
import { cardClass } from "../lib/ui";

/** Fixed-decimal string, or "—" for a null/NaN diagnostic (a degenerate or
 *  transported fit can yield a non-finite value, which JSON-serializes to null —
 *  a diagnostic readout must never crash on it). */
function fixed(v: number | null | undefined, digits: number): string {
  return v != null && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

interface DiagRow {
  label: string;
  value: string;
}

const DiagList = ({ rows }: { rows: DiagRow[] }) => (
  <dl className="divide-y divide-slate-800">
    {rows.map((row) => (
      <div key={row.label} className="flex items-center justify-between py-1.5">
        <dt className="text-xs text-slate-400">{row.label}</dt>
        <dd className="font-mono text-xs font-medium text-slate-100">{row.value}</dd>
      </div>
    ))}
  </dl>
);

const card = `${cardClass} p-4`;

export default function SmileAside() {
  const {
    smile, source, spotReturn, spotState, setSpotReturn, setFollow, recalibrate,
    probeLive, spotNote, applyVarSwap, undoVarSwap, redoVarSwap,
  } = useSmileSession();
  const { workflow } = useWorkflowContext(); // the background job (Re-anchor progress)
  const live = source === "live";
  const [showMore, setShowMore] = useState(false);

  const info = smile?.modelInfo;
  const d = smile?.diagnostics;

  const headline: DiagRow[] = d
    ? [
        {
          label: "ATM vol",
          // Quote-derived 1σ error bar (the fit's own Jacobian + bid-ask noise).
          value: d.atmVolStd != null ? `${formatPct(d.atmVol)} ±${formatPct(d.atmVolStd, 2)}` : formatPct(d.atmVol),
        },
        { label: "Skew", value: fixed(d.skew, 3) },
        { label: "Curvature", value: fixed(d.curvature, 2) },
        { label: "RMS — smile", value: formatPct(d.rmsError, 2) },
        { label: "RMS — surface", value: formatPct(smile?.surfaceRmsError, 2) },
      ]
    : [];
  const secondary: DiagRow[] = d
    ? [
        { label: "A_L (left wing)", value: fixed(d.aLeft, 3) },
        { label: "A_R (right wing)", value: fixed(d.aRight, 3) },
        { label: "Lee slope L", value: fixed(d.leeLeft, 3) },
        { label: "Lee slope R", value: fixed(d.leeRight, 3) },
        { label: "Var-swap vol", value: formatPct(d.varSwapVol) },
      ]
    : [];

  return (
    <aside className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto">
      {/* 1. Spot move: follow the market or the scenario (no recalibration);
          Recalibrate = Calibrate for this ticker. Applies across every lens,
          not just Smile. */}
      <section className={card}>
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
      </section>

      {/* 2. Variance-swap quote: adds a calibration penalty (Options-gated). */}
      {smile?.varSwap.enabled && (
        <section className={card}>
          <VarSwapPanel
            info={smile.varSwap}
            live={live}
            onSet={(level) => void applyVarSwap("set", level)}
            onExclude={() => void applyVarSwap("exclude")}
            onInclude={() => void applyVarSwap("include")}
            onRemove={() => void applyVarSwap("remove")}
            onUndo={() => void undoVarSwap()}
            onRedo={() => void redoVarSwap()}
            onReset={() => void applyVarSwap("reset")}
          />
        </section>
      )}

      {/* 3. Fit diagnostics */}
      <section className={card}>
        <div className="mb-1 flex items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Fit diagnostics</h3>
          {info && (
            <span
              title={info.params.map((p) => `${p.label}: ${p.value}`).join(" · ") || info.label}
              className="flex items-center gap-1.5 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-300"
            >
              {smile?.stale && <span className="font-sans font-semibold uppercase text-amber-400">stale</span>}
              {info.provenance === "loaded" && (
                <span className="font-sans font-semibold uppercase text-emerald-400" title="Reinstalled from a snapshot file">loaded</span>
              )}
              {info.label}
              {info.params.length > 0 && (
                <span className="font-medium text-slate-400">
                  {info.params.map((p) => `${p.label} ${p.value}`).join(" · ")}
                </span>
              )}
            </span>
          )}
        </div>
        <p className="mb-3 text-[11px] text-slate-500">
          {smile ? `Current calibration · ${smile.ticker} ${smile.expiry}` : "Awaiting data…"}
        </p>
        <DiagList rows={headline} />
        {secondary.length > 0 && (
          <>
            <button
              onClick={() => setShowMore((v) => !v)}
              className="mt-1 flex w-full items-center gap-1 py-1 text-[11px] font-medium text-slate-500 transition-colors hover:text-slate-300"
            >
              {showMore ? <ChevronDown size={12} strokeWidth={1.75} /> : <ChevronRight size={12} strokeWidth={1.75} />}
              More diagnostics
              {!showMore && <span className="text-slate-600">· wings, Lee, var-swap</span>}
            </button>
            {showMore && <DiagList rows={secondary} />}
          </>
        )}
      </section>
    </aside>
  );
}
