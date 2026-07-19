// Legacy solver knobs for the Graph shell's Advanced section (smooth field
// only — the message operator has no η/κ/λ/ν).
//
// Exposes the increment-prior knobs of the OT-Bayesian graph solver
// (volfit/graph/prior.py) — directed-smoothness reach η, local stiffness κ,
// optimal-transport flux λ with source allowance ν — and an auto-tune that
// LOO-cross-validates η over the lit observations. The two lattice edge
// weights render in the Relationships pane's Calendar / Cross-asset cards
// (EdgeWeightInput is exported for them). Pure presentation: all state lives
// in useGraph.
import type { AutotuneResult, SolverParams } from "../state/useGraph";

interface SolverPanelProps {
  params: SolverParams;
  setParam: <K extends keyof SolverParams>(key: K, value: SolverParams[K]) => void;
  resetParams: () => void;
  /** Number of lit nodes (auto-tune needs >= 2). */
  litCount: number;
  autotune: () => void;
  autotuning: boolean;
  autotuneResult: AutotuneResult | null;
  autotuneError: string | null;
}

/** Service-default edge weights (volfit/api/service.py); shown as placeholders
 *  and used when the override input is cleared back to the default. */
export const DEFAULT_CALENDAR_WEIGHT = 10;
export const DEFAULT_CROSS_WEIGHT = 2;

const rowLabel = "text-xs text-slate-400";

/** A log-scaled 0.1×–10× slider (η, κ): the value space is multiplicative. */
function LogScaleSlider({
  label,
  title,
  value,
  onChange,
}: {
  label: string;
  title: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="mb-3 block" title={title}>
      <span className="flex items-center justify-between">
        <span className={rowLabel}>{label}</span>
        <span className="font-mono text-xs font-medium text-slate-100">
          {value.toFixed(2)}×
        </span>
      </span>
      <input
        type="range"
        min={-1}
        max={1}
        step={0.05}
        value={Math.log10(value)}
        onChange={(e) => onChange(10 ** Number(e.target.value))}
        className="mt-1.5 w-full cursor-pointer"
        style={{ accentColor: "var(--color-accent-500)" }}
      />
    </label>
  );
}

/** Edge-weight override input: shows the default as a placeholder; clearing or
 *  matching the default stores null so the backend reuses its cached graph. */
export function EdgeWeightInput({
  label,
  title,
  value,
  fallback,
  onChange,
}: {
  label: string;
  title: string;
  value: number | null;
  fallback: number;
  onChange: (v: number | null) => void;
}) {
  return (
    <div className="mb-2 flex items-center justify-between" title={title}>
      <span className={rowLabel}>{label}</span>
      <span className="flex items-center gap-1">
        <input
          type="number"
          min={0.1}
          step={1}
          value={value ?? ""}
          placeholder={String(fallback)}
          onChange={(e) => {
            const v = e.target.valueAsNumber;
            onChange(Number.isFinite(v) && v > 0 ? v : null);
          }}
          className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
        />
        <button
          onClick={() => onChange(null)}
          title="Reset to default"
          className="px-0.5 text-xs leading-none text-slate-600 transition-colors hover:text-slate-300"
        >
          ↺
        </button>
      </span>
    </div>
  );
}

export default function SolverPanel({
  params,
  setParam,
  resetParams,
  litCount,
  autotune,
  autotuning,
  autotuneResult,
  autotuneError,
}: SolverPanelProps) {
  const otOff = params.lambdaScale === 0;
  const maxRmse =
    autotuneResult?.candidates.reduce((m, c) => Math.max(m, c.rmseBp), 0) ?? 0;

  return (
    <section className="border-t border-slate-800 pt-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Solver</h3>
        <button
          onClick={resetParams}
          className="text-[10px] text-slate-500 transition-colors hover:text-slate-300"
          title="Reset all solver hyperparameters"
        >
          reset
        </button>
      </div>

      <LogScaleSlider
        label="Propagation reach η"
        title="Directed-smoothness weight: how far an observation propagates."
        value={params.etaScale}
        onChange={(v) => setParam("etaScale", v)}
      />
      <LogScaleSlider
        label="Local stiffness κ"
        title="Local precision: higher pins nodes to their baseline (less spread)."
        value={params.kappaScale}
        onChange={(v) => setParam("kappaScale", v)}
      />

      {/* OT flux λ (0 disables the transport term) + source allowance ν */}
      <label className="mb-2 block" title="Optimal-transport flux weight; 0 disables the OT term.">
        <span className="flex items-center justify-between">
          <span className={rowLabel}>OT flux λ</span>
          <span className="font-mono text-xs font-medium text-slate-100">
            {otOff ? "off" : params.lambdaScale.toFixed(1)}
          </span>
        </span>
        <input
          type="range"
          min={0}
          max={5}
          step={0.1}
          value={params.lambdaScale}
          onChange={(e) => setParam("lambdaScale", Number(e.target.value))}
          className="mt-1.5 w-full cursor-pointer"
          style={{ accentColor: "var(--color-accent-500)" }}
        />
      </label>
      <div
        className={"mb-3 flex items-center justify-between " + (otOff ? "opacity-40" : "")}
        title="OT source/sink allowance ν (only active when λ > 0)."
      >
        <span className={rowLabel}>Source allowance ν</span>
        <input
          type="number"
          min={0.01}
          step={0.05}
          value={params.nu}
          disabled={otOff}
          onChange={(e) => {
            const v = e.target.valueAsNumber;
            if (Number.isFinite(v) && v > 0) setParam("nu", v);
          }}
          className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500 disabled:cursor-not-allowed"
        />
      </div>

      {/* Auto-tune η by leave-one-out cross-validation */}
      <button
        onClick={autotune}
        disabled={litCount < 2 || autotuning}
        title={
          litCount < 2
            ? "Light at least two nodes to auto-tune η"
            : "Pick η by leave-one-out cross-validation on the lit nodes"
        }
        className="mt-3 flex w-full items-center justify-center gap-2 rounded-md border border-slate-700 bg-surface-800 px-2 py-1.5 text-[11px] font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {autotuning && (
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500/40 border-t-slate-200" />
        )}
        {autotuning ? "Tuning η…" : "Auto-tune η"}
      </button>

      {autotuneError !== null && (
        <p className="mt-2 text-[10px] text-amber-400">{autotuneError}</p>
      )}

      {autotuneResult !== null && (
        <div className="mt-2 rounded-md border border-slate-800 bg-surface-800/50 p-2">
          <p className="mb-1.5 font-mono text-[10px] text-slate-400">
            best η <span className="text-accent-400">{autotuneResult.etaScale}×</span>
            {" · LOO RMSE "}
            <span className="text-slate-200">{autotuneResult.rmseBp.toFixed(1)} bp</span>
          </p>
          {/* LOO error bars across the η grid; chosen bar highlighted. */}
          <div className="flex items-end gap-1" style={{ height: 28 }}>
            {autotuneResult.candidates.map((c) => {
              const h = maxRmse > 0 ? Math.max(2, (c.rmseBp / maxRmse) * 28) : 2;
              const chosen = c.etaScale === autotuneResult.etaScale;
              return (
                <span
                  key={c.etaScale}
                  title={`η ${c.etaScale}× · ${c.rmseBp.toFixed(1)} bp`}
                  className={"flex-1 rounded-sm " + (chosen ? "bg-accent-500" : "bg-slate-700")}
                  style={{ height: h }}
                />
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
