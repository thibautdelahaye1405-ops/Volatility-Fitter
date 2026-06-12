// Diagnostics aside of the Smile workspace, extracted from SmileViewer:
// headline fit diagnostics plus the SSR spot-scenario, per-expiry forward
// and global hyperparameter panels. Reads the shared smile session directly;
// the only prop is whether the Smile chart view is active (the scenario
// overlay is only drawn there).
import ScenarioPanel from "./ScenarioPanel";
import ForwardPanel from "./ForwardPanel";
import HyperparamPanel from "./HyperparamPanel";
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
    ticker,
    expiry,
    reload,
    scenario,
    setScenario,
    scenarioCurve,
    scenarioSsr,
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

      {/* Per-expiry forward source: parity / theoretical / manual */}
      <div className="mt-4 border-t border-slate-800 pt-4">
        <ForwardPanel
          disabled={!live}
          ticker={ticker}
          expiry={expiry}
          onApplied={reload}
        />
      </div>

      {/* Global fit hyperparameters (model, N, damping) */}
      <div className="mt-4 border-t border-slate-800 pt-4">
        <HyperparamPanel disabled={!live} onApplied={reload} />
      </div>
    </aside>
  );
}
