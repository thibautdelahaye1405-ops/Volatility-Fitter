// "Spot scenario" panel for the Smile Viewer diagnostics aside. Drives the
// SSR overlay on the smile chart: pick a vol-spot dynamics regime, dial a
// hypothetical spot return, and the shifted smile (POST /scenario/ssr) is
// drawn dotted amber by SmileChart. The readout line reports the engine's
// skew-stickiness ratio and the resulting ATM vol shift.
import { useMemo } from "react";
import type { Regime, ScenarioState } from "../state/useScenario";
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
  /** Greyed out in mock mode and on the Density / Quantile views. */
  disabled: boolean;
  /** Tooltip explaining why the panel is greyed out. */
  disabledReason?: string;
}

/** Compact regime labels; full names live in the hover tooltips. */
const REGIMES: { id: Regime; label: string; title: string }[] = [
  { id: "sticky_moneyness", label: "Mny", title: "Sticky moneyness" },
  { id: "sticky_strike", label: "Strike", title: "Sticky strike" },
  { id: "sticky_local_vol", label: "LV", title: "Sticky local-vol (SSR = 2 rule)" },
  {
    id: "sticky_local_vol_grid",
    label: "LV grid",
    title: "Sticky local-vol grid (exact: fixed-strike grid, Dupire reprice)",
  },
];

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

      {/* Regime segmented control (mirrors the fit-mode control styling) */}
      <div className="mb-3 flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {REGIMES.map((r) => {
          const active = r.id === scenario.regime;
          return (
            <button
              key={r.id}
              title={r.title}
              disabled={disabled}
              onClick={() => onScenarioChange({ ...scenario, regime: r.id })}
              className={[
                "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
                active
                  ? "bg-accent-600/25 text-accent-400"
                  : "text-slate-400 enabled:hover:text-slate-200",
              ].join(" ")}
            >
              {r.label}
            </button>
          );
        })}
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
