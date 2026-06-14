// Options workspace (ROADMAP Phase 10): global meta-parameters & defaults.
//
// Hybrid design — this page holds the app-wide toggles, engine defaults and
// the penalty catalogue; the live per-node controls (model / fit-mode /
// scenario) stay in the Parametric aside. Two concerns, two Apply buttons:
//   * Calibration defaults  -> FitSettings   (HyperparamPanel, /settings/fit)
//   * Everything else        -> OptionsSettings (/settings/options, useOptions)
// Some toggles are wired to real engine behaviour (arb-fix, events, var-swap,
// dynamics, calendar penalty); two are stubbed this phase (auto-calibrate,
// spot mode) and labelled as such.
import HyperparamPanel from "../components/HyperparamPanel";
import { useOptions } from "../state/useOptions";
import type { DynamicsRegime } from "../state/useOptions";
import { useSmileSession } from "../state/smileSession";
import { useExpiryFormat } from "../state/expiryFormat";
import { EXPIRY_FORMATS, formatExpiry } from "../lib/expiryFormat";
import type { FitMode } from "../state/useSmile";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

const REGIMES: { id: DynamicsRegime; label: string; title: string }[] = [
  { id: "sticky_moneyness", label: "Mny", title: "Sticky moneyness / delta" },
  { id: "sticky_strike", label: "Strike", title: "Sticky strike (smile fixed in absolute strike)" },
  { id: "sticky_local_vol", label: "LV", title: "Sticky local-vol (SSR = 2 short-end rule)" },
  { id: "sticky_local_vol_grid", label: "LV grid", title: "Sticky local-vol grid (exact Dupire reprice)" },
  { id: "custom", label: "SSR", title: "Custom skew-stickiness ratio (set below)" },
];

/** Penalty catalogue: description + formula + which knob sets its strength. */
const PENALTIES: { name: string; formula: string; strength: string }[] = [
  { name: "LQD high-order damping", formula: "λ · n^(2r) · aₙ²  (n ≥ 4)", strength: "Calibration: Damping λ · r" },
  { name: "Calendar slack (arb-fix)", formula: "w · Σ max(floor − Gᵢ(α), 0)²", strength: "Calendar weight (below)" },
  { name: "SVI min-variance", formula: "P · max(−(a + bσ√(1−ρ²)), 0)²", strength: "fixed" },
  { name: "SVI Lee wing", formula: "P · max(b(1+|ρ|) − 2, 0)²", strength: "fixed" },
  { name: "Band hinge + mid anchor", formula: "max(m−ask,0)² + max(bid−m,0)² + 0.05(m−mid)²", strength: "Calibration: Haircut" },
  { name: "Affine LV roughness", formula: "√λ · L(θ − θ_ref),  L = 2nd diff in (t, x)", strength: "Grid: Roughness λ (below)" },
  { name: "Sigmoid amplitude ridge", formula: "ridge · Σ αᵣ²  (hat amplitudes)", strength: "fixed" },
];

const card =
  "rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30";
const segWrap = "flex overflow-hidden rounded-md border border-slate-700 bg-surface-800";
const numInput =
  "w-24 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";

/** A labelled checkbox toggle row. */
function Toggle({
  label, hint, checked, disabled, onChange,
}: {
  label: string; hint: string; checked: boolean; disabled?: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 py-1.5">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 accent-accent-500"
      />
      <span>
        <span className="text-xs font-medium text-slate-200">{label}</span>
        <span className="block text-[10px] text-slate-500">{hint}</span>
      </span>
    </label>
  );
}

/** A segmented control bound to one of a small set of string values. */
function Segmented<T extends string>({
  options, value, onChange, disabled,
}: {
  options: { id: T; label: string; title?: string }[];
  value: T; onChange: (v: T) => void; disabled?: boolean;
}) {
  return (
    <div className={segWrap}>
      {options.map((o) => (
        <button
          key={o.id}
          title={o.title}
          disabled={disabled}
          onClick={() => onChange(o.id)}
          className={[
            "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
            o.id === value ? "bg-accent-600/25 text-accent-400" : "text-slate-400 enabled:hover:text-slate-200",
          ].join(" ")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export default function OptionsViewer() {
  const { source, reload, fitMode, setFitMode } = useSmileSession();
  const live = source === "live";
  const { draft, patch, dirty, busy, flash, apply } = useOptions(live, reload);
  const { format: expiryFormat, setFormat: setExpiryFormat } = useExpiryFormat();

  const sectionTitle = "mb-3 text-sm font-semibold text-slate-100";
  const rowLabel = "text-xs text-slate-400";

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-4 overflow-y-auto p-4">
      {!live && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
          Settings live on the backend — start the FastAPI server to edit them.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Calibration defaults (FitSettings) */}
        <div className={card}>
          <h3 className={sectionTitle}>Calibration defaults</h3>
          <HyperparamPanel disabled={!live} onApplied={reload} />
          <div className="mt-4 border-t border-slate-800 pt-3">
            <span className={`${rowLabel} mb-1 block`}>Fit target</span>
            <Segmented options={FIT_MODES} value={fitMode} onChange={setFitMode} disabled={!live} />
            <p className="mt-1 text-[10px] text-slate-600">
              Mid · Bid-Ask band · Haircut band (shrink set by Haircut above).
            </p>
          </div>
        </div>

        {/* Engine toggles + prior + dynamics + grid (OptionsSettings) */}
        <div className={`${card} flex flex-col gap-4`}>
          <div>
            <h3 className={sectionTitle}>Engine toggles</h3>
            <Toggle
              label="Arbitrage fix" hint="Enforce the calendar (convex-order) constraint on surface fits"
              checked={draft.enforceCalendar} disabled={!live}
              onChange={(v) => patch({ enforceCalendar: v })}
            />
            <Toggle
              label="Events" hint="Event-time dilation default for the term structure"
              checked={draft.eventsEnabled} disabled={!live}
              onChange={(v) => patch({ eventsEnabled: v })}
            />
            <Toggle
              label="Variance-swaps" hint="Compute & surface the var-swap fair-variance level"
              checked={draft.varSwapEnabled} disabled={!live}
              onChange={(v) => patch({ varSwapEnabled: v })}
            />
            <Toggle
              label="Auto-load prior" hint="Seed the saved prior as the fit prior when a node loads"
              checked={draft.autoLoadPrior} disabled={!live}
              onChange={(v) => patch({ autoLoadPrior: v })}
            />
          </div>

          <div className="border-t border-slate-800 pt-3">
            <h3 className={sectionTitle}>Spot-vol dynamics</h3>
            <Segmented
              options={REGIMES} value={draft.dynamicsRegime} disabled={!live}
              onChange={(v) => patch({ dynamicsRegime: v })}
            />
            <div className="mt-2 flex items-center justify-between">
              <span
                className={`${rowLabel} ${draft.dynamicsRegime === "custom" ? "" : "opacity-40"}`}
                title="Custom skew-stickiness ratio (used when the regime is SSR)"
              >
                SSR value
              </span>
              <input
                type="number" step={0.1} min={0} value={draft.ssr}
                disabled={!live || draft.dynamicsRegime !== "custom"}
                onChange={(e) => patch({ ssr: Number(e.target.value) })}
                className={numInput}
              />
            </div>
            <p className="mt-1 text-[10px] text-slate-600">
              Drives the Parametric spot-scenario overlay (its aside has the spot
              slider only).
            </p>
          </div>

          <div className="border-t border-slate-800 pt-3">
            <h3 className={sectionTitle}>Local-vol grid defaults</h3>
            <div className="space-y-2">
              <NumberRow label="Strike nodes" value={draft.gridXNodes} step={1} disabled={!live}
                onChange={(v) => patch({ gridXNodes: v })} />
              <NumberRow label="Time nodes" value={draft.gridTNodes} step={1} disabled={!live}
                onChange={(v) => patch({ gridTNodes: v })} />
              <NumberRow label="Roughness λ" value={draft.gridRegLambda} step={0.001} disabled={!live}
                onChange={(v) => patch({ gridRegLambda: v })} />
              <NumberRow label="Roughness ρ (t vs x)" value={draft.gridRegRho} step={0.1} disabled={!live}
                onChange={(v) => patch({ gridRegRho: v })} />
            </div>
          </div>

          <div className="border-t border-slate-800 pt-3">
            <h3 className={sectionTitle}>Graph prior (defaults)</h3>
            <div className="space-y-2">
              <NumberRow label="κ prior strength" value={draft.graphKappaScale} step={0.1} disabled={!live}
                onChange={(v) => patch({ graphKappaScale: v })} />
              <NumberRow label="η reach" value={draft.graphEtaScale} step={0.1} disabled={!live}
                onChange={(v) => patch({ graphEtaScale: v })} />
              <NumberRow label="λ OT flux (0 = off)" value={draft.graphLambdaScale} step={0.1} disabled={!live}
                onChange={(v) => patch({ graphLambdaScale: v })} />
              <NumberRow label="ν OT source" value={draft.graphNu} step={0.05} disabled={!live}
                onChange={(v) => patch({ graphNu: v })} />
            </div>
            <p className="mt-1 text-[10px] text-slate-600">
              Seed the Graph Viewer's solver panel (κ = stiffness toward the baseline).
            </p>
          </div>
        </div>
      </div>

      {/* Display: expiry-format default (instant-apply, persisted locally) */}
      <div className={card}>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Display</h3>
          <span className="text-[11px] text-slate-500">
            Expiry format · applied across every view (also a ↻ toggle in the headers)
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {EXPIRY_FORMATS.map((f) => (
            <button
              key={f.id}
              onClick={() => setExpiryFormat(f.id)}
              className={[
                "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors",
                f.id === expiryFormat
                  ? "border-accent-600/60 bg-accent-600/15 text-accent-400"
                  : "border-slate-700 bg-surface-800 text-slate-400 hover:text-slate-200",
              ].join(" ")}
            >
              {f.label}
            </button>
          ))}
          <span className="ml-2 font-mono text-[11px] text-slate-500">
            e.g. {formatExpiry("2026-12-18", 1.25, expiryFormat)}
          </span>
        </div>
      </div>

      {/* Penalty catalogue */}
      <div className={card}>
        <h3 className={sectionTitle}>Penalty catalogue</h3>
        <div className="overflow-x-auto rounded-md border border-slate-800">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead className="bg-surface-800 text-slate-400">
              <tr>
                <th className="px-3 py-1.5 font-medium">Penalty</th>
                <th className="px-3 py-1.5 font-medium">Term</th>
                <th className="px-3 py-1.5 font-medium">Strength</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-slate-300">
              {PENALTIES.map((p) => (
                <tr key={p.name}>
                  <td className="px-3 py-1.5 font-medium text-slate-200">{p.name}</td>
                  <td className="px-3 py-1.5 font-mono text-slate-400">{p.formula}</td>
                  <td className="px-3 py-1.5 text-slate-500">{p.strength}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex items-center justify-between">
          <span className={rowLabel} title="Quadratic calendar-slack penalty weight (surface fits)">
            Calendar weight
          </span>
          <input
            type="number" step={1e5} min={0} value={draft.calendarWeight} disabled={!live}
            onChange={(e) => patch({ calendarWeight: Number(e.target.value) })}
            className={numInput}
          />
        </div>
      </div>

      {/* Workflow (stubbed this phase) */}
      <div className={card}>
        <div className="mb-2 flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Workflow</h3>
          <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-slate-500">
            preview · not yet wired
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Toggle
            label="Auto-on-demand calibration"
            hint="On: refit on every quote edit. Off: refit only on a manual Calibrate button (TODO)."
            checked={draft.autoCalibrate} disabled={!live}
            onChange={(v) => patch({ autoCalibrate: v })}
          />
          <div>
            <span className={`${rowLabel} mb-1 block`}>Spot prices</span>
            <Segmented
              options={[
                { id: "static", label: "Static", title: "Freeze spot at load (pairs with As-of)" },
                { id: "realtime", label: "Real-time", title: "Stream live spot & re-price (TODO)" },
              ]}
              value={draft.spotMode} disabled={!live}
              onChange={(v) => patch({ spotMode: v })}
            />
          </div>
        </div>
      </div>

      {/* Sticky Apply bar for the OptionsSettings draft */}
      <div className="sticky bottom-0 flex items-center gap-3 border-t border-slate-800 bg-surface-950/80 py-3 backdrop-blur">
        <span className="text-[11px] text-slate-500">
          {dirty ? "Unsaved Options changes" : "Options saved"}
        </span>
        <button
          onClick={apply}
          disabled={!live || !dirty || busy}
          className={[
            "ml-auto rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            flash
              ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
              : dirty && live
                ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
                : "cursor-not-allowed border-slate-700 text-slate-600",
          ].join(" ")}
        >
          {flash ? "Applied ✓" : busy ? "Saving…" : "Apply Options"}
        </button>
      </div>
    </div>
  );
}

/** A labelled numeric input row for the grid defaults. */
function NumberRow({
  label, value, step, disabled, onChange,
}: {
  label: string; value: number; step: number; disabled?: boolean; onChange: (v: number) => void;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number" step={step} min={0} value={value} disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-24 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500"
      />
    </div>
  );
}
