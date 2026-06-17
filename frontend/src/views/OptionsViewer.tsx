// Options workspace (ROADMAP Phase 10): global meta-parameters & defaults,
// organized by theme:
//   1. Model & hyperparameters   — model + N/damping/cores, model penalties,
//                                   the local-vol vertex grid.
//   2. Calibration               — fit target, haircut, quote weighting, band
//                                   mid anchor, var-swap weight, normalize
//                                   events, calendar weight, calibration
//                                   penalties, graph prior.
//   3. Workflow & engine features — engine toggles + calibration/fetch triggers.
//   4. Spot-vol dynamics          — regime + SSR.
// Purely cosmetic display preferences live in the separate View tab.
//
// FitSettings (model/penalties/haircut/weighting) and OptionsSettings (the rest)
// are two backend endpoints but share ONE sticky Apply bar here.
import HyperparamPanel from "../components/HyperparamPanel";
import { NumberRow, PenaltyTable, Segmented, Toggle } from "../components/OptionsControls";
import { api } from "../state/api";
import { useOptions } from "../state/useOptions";
import type { DynamicsRegime } from "../state/useOptions";
import { useFitSettings } from "../state/useFitSettings";
import { useSettingsDefaults } from "../state/useSettingsDefaults";
import { useSmileSession } from "../state/smileSession";
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

const card =
  "rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30";
const numInput =
  "w-24 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-right " +
  "font-mono text-[11px] text-slate-200 outline-none hover:border-slate-600 focus:border-accent-500";
const sectionTitle = "mb-3 text-sm font-semibold text-slate-100";
const subTitle = "mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400";

export default function OptionsViewer() {
  const { source, reload, fitMode, setFitMode, ticker } = useSmileSession();
  const live = source === "live";
  const { draft, patch, dirty, busy, flash, apply, adopt } = useOptions(live, reload);
  const fit = useFitSettings(live, reload);
  const defaults = useSettingsDefaults(live);

  // One Apply commits both backends (each is a no-op when its draft is clean).
  const anyDirty = dirty || fit.dirty;
  const anyBusy = busy || fit.busy || defaults.busy;
  const anyFlash = flash || fit.flash;
  const applyAll = () => Promise.all([fit.apply(), apply()]);

  // "Save as default" first commits any pending edits (so the persisted snapshot
  // matches what's on screen), then writes the live settings to the app store.
  const saveAsDefault = async () => {
    await applyAll();
    await defaults.save();
  };

  // "Reset to defaults" reverts the live settings to the built-in code defaults
  // (and clears the saved blob); adopt the returned values into both drafts.
  const resetToDefaults = async () => {
    const r = await defaults.reset();
    if (r) {
      fit.adopt(r.fit);
      adopt(r.options);
      reload();
    }
  };

  const rowLabel = "text-xs text-slate-400";

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col gap-4 overflow-y-auto p-4">
      {!live && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
          Settings live on the backend — start the FastAPI server to edit them.
        </div>
      )}

      {/* ---- 1. Model & hyperparameters --------------------------------- */}
      <div className={card}>
        <h3 className={sectionTitle}>Model &amp; hyperparameters</h3>
        <HyperparamPanel group="model" draft={fit.draft} patch={fit.patch} disabled={!live} />

        <h4 className={subTitle}>Model penalties</h4>
        <PenaltyTable group="model" />

        <h4 className={subTitle}>Local-vol grid</h4>
        <div className="space-y-2">
          <NumberRow label="Strike nodes" value={draft.gridXNodes} step={1} disabled={!live}
            onChange={(v) => patch({ gridXNodes: v })} />
          <NumberRow label="Time nodes (0 = per expiry)" value={draft.gridTNodes} step={1} disabled={!live}
            onChange={(v) => patch({ gridTNodes: v })} />
          <NumberRow label="Roughness λ" value={draft.gridRegLambda} step={0.001} disabled={!live}
            onChange={(v) => patch({ gridRegLambda: v })} />
          <NumberRow label="Roughness ρ (t vs x)" value={draft.gridRegRho} step={0.1} disabled={!live}
            onChange={(v) => patch({ gridRegRho: v })} />
        </div>
        <button
          type="button"
          disabled={!live || ticker === ""}
          title={`Size the grid to ${ticker || "the ticker"}'s observed quotes`}
          onClick={() => {
            api
              .get<{ gridXNodes: number; gridTNodes: number }>(
                `/fit/affine/${ticker}/optimal-size`,
              )
              .then((o) => patch({ gridXNodes: o.gridXNodes, gridTNodes: o.gridTNodes }))
              .catch(() => {});
          }}
          className="mt-2 w-full rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1 text-[11px] font-semibold text-accent-300 transition hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Optimal size (≈ # quotes)
        </button>
        <p className="mt-1 text-[10px] text-slate-500">
          Time vertices default to the observed expiries; the lowest strike vertex
          sits just above the lowest observed strike. Used by the Local-Vol surface.
        </p>
      </div>

      {/* ---- 2. Calibration --------------------------------------------- */}
      <div className={card}>
        <h3 className={sectionTitle}>Calibration</h3>

        <span className={`${rowLabel} mb-1 block`}>Fit target</span>
        <Segmented
          options={FIT_MODES}
          value={fitMode}
          onChange={(v) => { setFitMode(v); patch({ fitMode: v }); }}
          disabled={!live}
        />
        <p className="mt-1 text-[10px] text-slate-600">
          Mid · Bid-Ask band · Haircut band (shrink set by Haircut below).
          Persisted via Save as default.
        </p>

        {/* Haircut, quote weighting, band mid anchor (FitSettings). */}
        <div className="mt-4">
          <HyperparamPanel group="calibration" draft={fit.draft} patch={fit.patch} disabled={!live} />
        </div>

        {/* Var-swap penalty weight + event-clock normalization (OptionsSettings). */}
        <div className="mt-1 flex items-center justify-between">
          <span
            className={`${rowLabel} ${draft.varSwapEnabled ? "" : "opacity-40"}`}
            title="Var-swap penalty weight as a % of the summed option-quote weights of the same (asset, expiry) node — at 100% the var-swap weighs as much as all option quotes combined"
          >
            Var-swap weight (%)
          </span>
          <input
            type="number" step={1} min={0} value={draft.varSwapWeightPct}
            disabled={!live || !draft.varSwapEnabled}
            onChange={(e) => patch({ varSwapWeightPct: Number(e.target.value) })}
            className={numInput}
          />
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span
            className={`${rowLabel} ${draft.autoLoadPrior ? "" : "opacity-40"}`}
            title="Prior-anchor budget as a % of the summed option-quote weights of the node — distributed across delta-locations by the observed-vs-desired quote-density gap, pulling the fit toward the fetched prior where data is sparse (Auto-load prior)"
          >
            Prior-anchor weight (%)
          </span>
          <input
            type="number" step={1} min={0} value={draft.priorAnchorWeightPct}
            disabled={!live || !draft.autoLoadPrior}
            onChange={(e) => patch({ priorAnchorWeightPct: Number(e.target.value) })}
            className={numInput}
          />
        </div>
        <Toggle
          label="Normalize events"
          hint="Rescale all days so the 1Y weight budget stays 365 (1Y vols unchanged; events redistribute variance within the year)"
          checked={draft.normalizeEvents} disabled={!live || !draft.eventsEnabled}
          onChange={(v) => patch({ normalizeEvents: v })}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className={rowLabel} title="Quadratic calendar-slack penalty weight (surface fits)">
            Calendar weight
          </span>
          <input
            type="number" step={1e5} min={0} value={draft.calendarWeight} disabled={!live}
            onChange={(e) => patch({ calendarWeight: Number(e.target.value) })}
            className={numInput}
          />
        </div>

        <h4 className={subTitle}>Calibration penalties</h4>
        <PenaltyTable group="calibration" />

        <h4 className={subTitle}>Graph prior (defaults)</h4>
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

      {/* ---- 3. Workflow & engine features ------------------------------ */}
      <div className={card}>
        <h3 className={sectionTitle}>Workflow &amp; engine features</h3>

        <h4 className={`${subTitle} mt-0`}>Engine features</h4>
        <Toggle
          label="Arbitrage fix" hint="Calendar-couple the Calibrate job: fit each ticker's expiries in order, enforcing the convex-order (no-calendar-arbitrage) floor"
          checked={draft.enforceCalendar} disabled={!live}
          onChange={(v) => patch({ enforceCalendar: v })}
        />
        <Toggle
          label="Events" hint="Event-weighted variance clock: events add day-weights, so an event before an expiry lowers its IV"
          checked={draft.eventsEnabled} disabled={!live}
          onChange={(v) => patch({ eventsEnabled: v })}
        />
        <Toggle
          label="Variance-swaps" hint="Add var-swap quotes (Smile/Term/Table) with a calibration penalty (weight set in Calibration)"
          checked={draft.varSwapEnabled} disabled={!live}
          onChange={(v) => patch({ varSwapEnabled: v })}
        />
        <Toggle
          label="Auto-load prior" hint="Anchor the fit to the fetched prior at delta-locations, weighted by where quotes are sparse (data-gap); fades where data is dense. Strength = Prior-anchor weight in Calibration"
          checked={draft.autoLoadPrior} disabled={!live}
          onChange={(v) => patch({ autoLoadPrior: v })}
        />

        <div className="mt-4 border-t border-slate-800 pt-3">
          <h4 className={`${subTitle} mt-0`}>Calibration &amp; data triggers</h4>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Toggle
              label="Auto-calibrate"
              hint="On: lit nodes refit automatically after a fetch / on any change. Off: nodes go STALE until you press Calibrate (top bar)."
              checked={draft.autoCalibrate} disabled={!live}
              onChange={(v) => patch({ autoCalibrate: v })}
            />
            <Toggle
              label="Local-Vol calibration"
              hint="On: Calibrate also fits each ticker's Local-Vol surface (slow); the Local Vol tab is available. Off: skip LV for fast test cycles and grey out the Local Vol tab."
              checked={draft.localVolEnabled} disabled={!live}
              onChange={(v) => patch({ localVolEnabled: v })}
            />
            <div>
              <span className={`${rowLabel} mb-1 block`}>Spot prices</span>
              <Segmented
                options={[
                  { id: "static", label: "On-demand", title: "Fetch spots only via the 'Fetch spots' button" },
                  { id: "realtime", label: "Real-time", title: "The scheduler polls live spots and transports the surface" },
                ]}
                value={draft.spotMode} disabled={!live}
                onChange={(v) => patch({ spotMode: v })}
              />
              {draft.spotMode === "realtime" && (
                <div className="mt-2">
                  <NumberRow
                    label="Poll every (s)" value={draft.spotPollSeconds} step={1}
                    disabled={!live} onChange={(v) => patch({ spotPollSeconds: v })}
                  />
                </div>
              )}
            </div>
            <div>
              <span className={`${rowLabel} mb-1 block`}>Options quotes</span>
              <Segmented
                options={[
                  { id: "on_demand", label: "On-demand", title: "Fetch chains only via the 'Fetch Options Quotes' button" },
                  { id: "auto", label: "Auto", title: "The scheduler refetches chains on a timer (then auto-calibrates if enabled)" },
                ]}
                value={draft.optionsFetchMode} disabled={!live}
                onChange={(v) => patch({ optionsFetchMode: v })}
              />
              {draft.optionsFetchMode === "auto" && (
                <div className="mt-2">
                  <NumberRow
                    label="Fetch every (min)" value={draft.optionsFetchMinutes} step={1}
                    disabled={!live} onChange={(v) => patch({ optionsFetchMinutes: v })}
                  />
                </div>
              )}
            </div>
          </div>
          <p className="mt-3 text-[11px] text-slate-500">
            A spot move transports the surface (no recalibration); fetching fresh option
            quotes (or any change with Auto-calibrate off) marks lit nodes STALE until Calibrate.
          </p>
        </div>
      </div>

      {/* ---- 4. Spot-vol dynamics --------------------------------------- */}
      <div className={card}>
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
          Drives the Parametric spot-scenario overlay (its aside has the spot slider only).
        </p>
      </div>

      {/* Sticky action bar — Apply commits the live settings; Save as default
          persists them to the store so they survive a backend restart; Reset
          reverts to the built-in defaults. */}
      <div className="sticky bottom-0 flex items-center gap-3 border-t border-slate-800 bg-surface-950/80 py-3 backdrop-blur">
        <span className="text-[11px] text-slate-500">
          {anyDirty
            ? "Unsaved Options changes"
            : defaults.flash
              ? "Saved as default ✓"
              : defaults.hasSaved
                ? "Persisted default set"
                : "Options saved"}
        </span>

        {/* Reset to the built-in defaults (also clears any saved default). */}
        <button
          onClick={resetToDefaults}
          disabled={!live || anyBusy}
          title="Revert all Options & Fit settings to the built-in defaults (clears any saved default)"
          className={[
            "ml-auto rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            live && !anyBusy
              ? "border-slate-700 bg-surface-800 text-slate-300 hover:border-slate-600 hover:text-slate-100"
              : "cursor-not-allowed border-slate-800 text-slate-600",
          ].join(" ")}
        >
          Reset to defaults
        </button>

        {/* Persist the current settings as the startup default (needs a store). */}
        <button
          onClick={saveAsDefault}
          disabled={!live || anyBusy || !defaults.storeEnabled}
          title={
            defaults.storeEnabled
              ? "Save the current settings so they're restored on the next app restart"
              : "Needs a configured store (VOLFIT_DB) to persist across restart"
          }
          className={[
            "rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            defaults.flash
              ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
              : live && !anyBusy && defaults.storeEnabled
                ? "border-slate-600 bg-surface-800 text-slate-200 hover:border-accent-600/60 hover:text-accent-300"
                : "cursor-not-allowed border-slate-800 text-slate-600",
          ].join(" ")}
        >
          {defaults.flash ? "Saved ✓" : "Save as default"}
        </button>

        {/* Apply the pending edits to the live backend settings. */}
        <button
          onClick={applyAll}
          disabled={!live || !anyDirty || anyBusy}
          className={[
            "rounded-md border px-3 py-1.5 text-[11px] font-medium transition-colors",
            anyFlash
              ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
              : anyDirty && live
                ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
                : "cursor-not-allowed border-slate-700 text-slate-600",
          ].join(" ")}
        >
          {anyFlash ? "Applied ✓" : anyBusy ? "Saving…" : "Apply Options"}
        </button>
      </div>
    </div>
  );
}
