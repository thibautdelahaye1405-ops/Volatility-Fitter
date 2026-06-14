// "Spot scenario" panel for the Parametric aside. Drives the SSR overlay on
// the smile chart: dial a hypothetical spot return and the shifted smile
// (POST /scenario/ssr) is drawn dotted amber by SmileChart. The dynamics
// regime now lives entirely in the Options workspace (ROADMAP Phase 10
// follow-up); this panel shows it read-only and carries only the slider. The
// readout reports the engine's skew-stickiness ratio and ATM vol shift.
import { useMemo } from "react";
import type { ScenarioState } from "../state/useScenario";
import type { SmilePoint } from "../lib/mockData";

interface ScenarioPanelProps {
  scenario: ScenarioState;
  onScenarioChange: (next: ScenarioState) => void;
  /** Shifted smile from the scenario engine; null while the overlay is off. */
  scenarioCurve: SmilePoint[] | null;
  /** Skew-stickiness ratio reported alongside the curve, or null. */
  ssr: number | null;
  /** Current model curve, for the client-side ATM-shift readout. */
  model: SmilePoint[] | null;
  /** Greyed out in mock mode and on the Density / Log-Q-density views. */
  disabled: boolean;
  /** Tooltip explaining why the panel is greyed out. */
  disabledReason?: string;
}

/** Human label for the active regime (string id or numeric custom SSR). */
function regimeLabel(regime: ScenarioState["regime"]): string {
  if (typeof regime === "number") return `Custom SSR ${regime.toFixed(1)}`;
  return (
    {
      sticky_moneyness: "Sticky moneyness",
      sticky_strike: "Sticky strike",
      sticky_local_vol: "Sticky local-vol",
      sticky_local_vol_grid: "Sticky local-vol grid",
    } as Record<string, string>
  )[regime] ?? regime;
}

/** Linear interpolation of a curve's vol at k (same as SmileChart's). */
function volAt(curve: SmilePoint[], k: number): number | null {
  if (curve.length === 0) return null;
  if (k <= curve[0].k) return curve[0].vol;
  const last = curve[curve.length - 1];
  if (k >= last.k) return last.vol;
  for (let i = 1; i < curve.length; i++) {
    const p1 = curve[i];
    if (k <= p1.k) {
      const p0 = curve[i - 1];
      const t = (k - p0.k) / (p1.k - p0.k);
      return p0.vol + t * (p1.vol - p0.vol);
    }
  }
  return last.vol;
}

export default function ScenarioPanel({
  scenario,
  onScenarioChange,
  scenarioCurve,
  ssr,
  model,
  disabled,
  disabledReason,
}: ScenarioPanelProps) {
  // ATM vol shift in bp: scenario curve minus current model, both at k = 0.
  const atmShiftBp = useMemo(() => {
    if (scenarioCurve === null || model === null) return null;
    const shifted = volAt(scenarioCurve, 0);
    const base = volAt(model, 0);
    if (shifted === null || base === null) return null;
    return (shifted - base) * 1e4; // decimal vol -> basis points
  }, [scenarioCurve, model]);

  // Slider works in whole/half percent; snap so 0 compares exactly.
  const pct = Math.round(scenario.spotReturn * 1000) / 10;

  return (
    <section
      className={disabled ? "opacity-40" : ""}
      title={disabled ? disabledReason : undefined}
    >
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Spot scenario</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        SSR-implied smile under a spot shock
      </p>

      {/* Active dynamics regime — read-only; change it in the Options tab. */}
      <div className="mb-3 flex items-center justify-between rounded-md border border-slate-800 bg-surface-800/60 px-2 py-1">
        <span className="text-[11px] text-slate-500">Regime</span>
        <span className="font-mono text-[11px] text-slate-300" title="Set in the Options workspace">
          {regimeLabel(scenario.regime)}
        </span>
      </div>

      {/* Spot-return slider with a live % readout (accent when active) */}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-400">Spot return</span>
        <span
          className={[
            "font-mono font-medium",
            pct !== 0 ? "text-accent-400" : "text-slate-500",
          ].join(" ")}
        >
          {pct > 0 ? "+" : ""}
          {pct.toFixed(1)}%
        </span>
      </div>
      <input
        type="range"
        min={-5}
        max={5}
        step={0.5}
        value={pct}
        disabled={disabled}
        onChange={(e) =>
          onScenarioChange({ ...scenario, spotReturn: Number(e.target.value) / 100 })
        }
        className="w-full cursor-pointer disabled:cursor-not-allowed"
        style={{ accentColor: "var(--color-accent-500)" }}
      />
      <div className="flex justify-between font-mono text-[10px] text-slate-600">
        <span>-5%</span>
        <span>0</span>
        <span>+5%</span>
      </div>

      {/* Headline readout: engine SSR + resulting ATM vol shift */}
      <p className="mt-2 font-mono text-[11px] text-slate-400">
        {disabled || pct === 0 ? (
          <span className="text-slate-600">Slide to preview a spot shock</span>
        ) : ssr !== null && atmShiftBp !== null ? (
          <>
            SSR = {ssr.toFixed(1)} · ATM shift ≈ {atmShiftBp >= 0 ? "+" : ""}
            {atmShiftBp.toFixed(0)} bp
          </>
        ) : (
          <span className="text-slate-600">Computing scenario…</span>
        )}
      </p>
    </section>
  );
}
