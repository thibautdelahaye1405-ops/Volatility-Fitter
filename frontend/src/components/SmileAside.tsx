// Diagnostics aside of the Parametric workspace, extracted from SmileViewer:
// headline fit diagnostics plus the SSR spot-scenario slider. The model
// selector, forward/dividend editor and full hyperparameters all moved to the
// Options / Forwards workspaces (ROADMAP Phase 10 + follow-up), leaving the
// aside to diagnostics + the live spot scenario. Reads the shared smile
// session directly; the only prop is whether the Smile chart view is active
// (the scenario overlay is only drawn there).
import ScenarioPanel from "./ScenarioPanel";
import VarSwapPanel from "./VarSwapPanel";
import { useSmileSession } from "../state/smileSession";
import { formatPct } from "../lib/chartScale";

interface SmileAsideProps {
  /** True while the chart card shows the Smile view (scenario overlay host). */
  smileViewActive: boolean;
}

export default function SmileAside({ smileViewActive }: SmileAsideProps) {
  const {
    smile,
    source,
    scenario,
    setScenario,
    scenarioCurve,
    scenarioSsr,
    applyVarSwap,
    undoVarSwap,
    redoVarSwap,
  } = useSmileSession();
  const live = source === "live";

  const diagnostics: { label: string; value: string }[] = smile
    ? [
        { label: "ATM vol", value: formatPct(smile.diagnostics.atmVol) },
        { label: "Skew", value: smile.diagnostics.skew.toFixed(3) },
        { label: "Curvature", value: smile.diagnostics.curvature.toFixed(2) },
        { label: "A_L (left wing)", value: smile.diagnostics.aLeft.toFixed(3) },
        { label: "A_R (right wing)", value: smile.diagnostics.aRight.toFixed(3) },
        { label: "Lee slope L", value: smile.diagnostics.leeLeft.toFixed(3) },
        { label: "Lee slope R", value: smile.diagnostics.leeRight.toFixed(3) },
        { label: "Var-swap vol", value: formatPct(smile.diagnostics.varSwapVol) },
        { label: "RMS error", value: formatPct(smile.diagnostics.rmsError, 2) },
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

      {/* Spot scenario: drives the SSR overlay on the smile chart */}
      <div className="mt-4 border-t border-slate-800 pt-4">
        <ScenarioPanel
          scenario={scenario}
          onScenarioChange={setScenario}
          scenarioCurve={scenarioCurve}
          ssr={scenarioSsr}
          model={smile?.model ?? null}
          disabled={!live || !smileViewActive}
          disabledReason={
            !live
              ? "requires live backend"
              : "scenario overlay applies to the Smile view"
          }
        />
      </div>
    </aside>
  );
}
