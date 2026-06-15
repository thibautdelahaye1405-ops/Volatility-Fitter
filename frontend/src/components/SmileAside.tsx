// Diagnostics aside of the Parametric workspace, extracted from SmileViewer:
// headline fit diagnostics plus the SSR spot-scenario slider. The model
// selector, forward/dividend editor and full hyperparameters all moved to the
// Options / Forwards workspaces (ROADMAP Phase 10 + follow-up), leaving the
// aside to diagnostics + the live spot scenario. Reads the shared smile
// session directly; the only prop is whether the Smile chart view is active
// (the scenario overlay is only drawn there).
import SpotPanel from "./SpotPanel";
import VarSwapPanel from "./VarSwapPanel";
import { useSmileSession } from "../state/smileSession";
import { formatPct } from "../lib/chartScale";

/** Fixed-decimal string, or "—" for a null/NaN diagnostic (a degenerate or
 *  transported fit can yield a non-finite value, which JSON-serializes to null —
 *  a diagnostic readout must never crash on it). */
function fixed(v: number | null | undefined, digits: number): string {
  return v != null && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

export default function SmileAside() {
  const {
    smile,
    source,
    spotReturn,
    spotState,
    spotMode,
    setSpotReturn,
    recalibrate,
    applyVarSwap,
    undoVarSwap,
    redoVarSwap,
  } = useSmileSession();
  const live = source === "live";

  const d = smile?.diagnostics;
  const diagnostics: { label: string; value: string }[] = d
    ? [
        { label: "ATM vol", value: formatPct(d.atmVol) },
        { label: "Skew", value: fixed(d.skew, 3) },
        { label: "Curvature", value: fixed(d.curvature, 2) },
        { label: "A_L (left wing)", value: fixed(d.aLeft, 3) },
        { label: "A_R (right wing)", value: fixed(d.aRight, 3) },
        { label: "Lee slope L", value: fixed(d.leeLeft, 3) },
        { label: "Lee slope R", value: fixed(d.leeRight, 3) },
        { label: "Var-swap vol", value: formatPct(d.varSwapVol) },
        { label: "RMS error", value: formatPct(d.rmsError, 2) },
      ]
    : [];

  return (
    <aside className="w-72 shrink-0 overflow-y-auto rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
      <h3 className="mb-1 text-sm font-semibold text-slate-100">
        Fit diagnostics
      </h3>
      <p className="mb-4 text-[11px] text-slate-500">
        {smile
          ? `Current calibration · ${smile.ticker} ${smile.expiry}`
          : "Awaiting data…"}
      </p>
      <dl className="divide-y divide-slate-800">
        {diagnostics.map((row) => (
          <div
            key={row.label}
            className="flex items-center justify-between py-2"
          >
            <dt className="text-xs text-slate-400">{row.label}</dt>
            <dd className="font-mono text-xs font-medium text-slate-100">
              {row.value}
            </dd>
          </div>
        ))}
      </dl>

      {/* Variance-swap quote: adds a calibration penalty (Options-gated) */}
      {smile?.varSwap.enabled && (
        <div className="mt-4 border-t border-slate-800 pt-4">
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
        </div>
      )}

      {/* Spot move: the slider transports the live surface (no recalibration);
          Calibrate re-anchors. Applies across every workspace, not just Smile. */}
      <div className="mt-4 border-t border-slate-800 pt-4">
        <SpotPanel
          spotReturn={spotReturn}
          spotState={spotState}
          spotMode={spotMode}
          onSpotReturn={setSpotReturn}
          onCalibrate={() => void recalibrate()}
          disabled={!live}
          disabledReason={!live ? "requires live backend" : undefined}
        />
      </div>
    </aside>
  );
}
