// Options workspace (ROADMAP Phase 10; reorganized 2026-07): one thematic card
// per concern, with feature-dependent knobs rendered only while their feature /
// model is active:
//   Parametric model · Local-Vol surface · Calibration · Prior persistence ·
//   Kalman filter · Events · Graph · Workflow & data · Spot-vol dynamics
// A sticky chip row scrolls to each section. Purely cosmetic display
// preferences live in the separate View tab.
//
// FitSettings (model/penalties/haircut/weighting) and OptionsSettings (the rest)
// are two backend endpoints but share ONE sticky Apply bar here.
import { useEffect, useState } from "react";

import CalibrationSection from "../components/options/CalibrationSection";
import LocalVolSection from "../components/options/LocalVolSection";
import type { GridInfo } from "../components/options/LocalVolSection";
import ParametricSection from "../components/options/ParametricSection";
import {
  DynamicsSection,
  EventsSection,
  GraphSection,
  WorkflowSection,
} from "../components/options/SmallSections";
import { sectionTitle } from "../components/options/shared";
import ObservationFilterPanel from "../components/ObservationFilterPanel";
import PriorPersistencePanel from "../components/PriorPersistencePanel";
import { api } from "../state/api";
import { useOptions } from "../state/useOptions";
import { useFitSettings } from "../state/useFitSettings";
import { useSettingsDefaults } from "../state/useSettingsDefaults";
import { useSmileSession } from "../state/smileSession";

const card =
  "scroll-mt-12 rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30";

/** Section registry: card ids for the sticky quick-nav chips. */
const SECTIONS: { id: string; label: string }[] = [
  { id: "opt-parametric", label: "Parametric" },
  { id: "opt-localvol", label: "Local Vol" },
  { id: "opt-calibration", label: "Calibration" },
  { id: "opt-prior", label: "Prior" },
  { id: "opt-filter", label: "Kalman filter" },
  { id: "opt-events", label: "Events" },
  { id: "opt-graph", label: "Graph" },
  { id: "opt-workflow", label: "Workflow" },
  { id: "opt-dynamics", label: "Dynamics" },
];

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

  // The ACTUAL resolved vertex grid for the active ticker under the APPLIED
  // settings (so the floor / delta / convex-wing knobs are visible + consistent).
  // Refetched on ticker change and whenever edits are applied (anyDirty -> false).
  const [gridInfo, setGridInfo] = useState<GridInfo | null>(null);
  useEffect(() => {
    if (!live || !ticker || anyDirty) return;
    let cancelled = false;
    api
      .get<GridInfo>(`/fit/affine/${ticker}/grid-info`)
      .then((g) => !cancelled && setGridInfo(g))
      .catch(() => !cancelled && setGridInfo(null));
    return () => {
      cancelled = true;
    };
  }, [live, ticker, anyDirty]);

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

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col overflow-y-auto p-4 pt-0">
      {/* Sticky quick-nav: one chip per section. */}
      <div className="sticky top-0 z-10 -mx-4 mb-4 flex flex-wrap items-center gap-1.5 border-b border-slate-800 bg-surface-950/85 px-4 py-2 backdrop-blur">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() =>
              document.getElementById(s.id)?.scrollIntoView({ behavior: "smooth", block: "start" })
            }
            className="rounded-full border border-slate-700 bg-surface-800 px-2.5 py-0.5 text-[11px] font-medium text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200"
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-4">
        {!live && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
            Settings live on the backend — start the FastAPI server to edit them.
          </div>
        )}

        <div className={card} id="opt-parametric">
          <ParametricSection
            fitDraft={fit.draft} fitPatch={fit.patch} draft={draft} patch={patch} live={live}
          />
        </div>

        <div className={card} id="opt-localvol">
          <LocalVolSection
            draft={draft} patch={patch} live={live} ticker={ticker}
            gridInfo={gridInfo} anyDirty={anyDirty}
          />
        </div>

        <div className={card} id="opt-calibration">
          <CalibrationSection
            fitDraft={fit.draft} fitPatch={fit.patch} draft={draft} patch={patch}
            live={live} fitMode={fitMode} setFitMode={setFitMode}
          />
        </div>

        {/* Prior persistence — first-class section (design note §10/§9.4). */}
        <div className={card} id="opt-prior">
          <h3 className={sectionTitle}>Prior persistence</h3>
          <p className="text-[11px] text-slate-500">
            How a fetched prior surface (Save / Fetch priors, top bar) is persisted
            into the calibration — mode, operators and diagnostics.
          </p>
          <PriorPersistencePanel
            draft={draft} patch={patch} live={live} ticker={ticker}
            fitMode={fitMode} refreshKey={anyDirty}
          />
        </div>

        {/* Observation Kalman filter — first-class section (Note 15 Phase 4). */}
        <div className={card} id="opt-filter">
          <h3 className={sectionTitle}>Observation filter (Kalman)</h3>
          <p className="text-[11px] text-slate-500">
            Kalman-filter the incoming quotes across fetches to denoise the
            calibration input — mode, process noise and the per-expiry gain audit.
          </p>
          <ObservationFilterPanel
            draft={draft} patch={patch} live={live} ticker={ticker}
            fitMode={fitMode} refreshKey={anyDirty}
          />
        </div>

        <div className={card} id="opt-events">
          <EventsSection draft={draft} patch={patch} live={live} />
        </div>

        <div className={card} id="opt-graph">
          <GraphSection draft={draft} patch={patch} live={live} />
        </div>

        <div className={card} id="opt-workflow">
          <WorkflowSection draft={draft} patch={patch} live={live} />
        </div>

        <div className={card} id="opt-dynamics">
          <DynamicsSection draft={draft} patch={patch} live={live} />
        </div>
      </div>

      {/* Sticky action bar — Apply commits the live settings; Save as default
          persists them to the store so they survive a backend restart; Reset
          reverts to the built-in defaults. */}
      <div className="sticky bottom-0 mt-4 flex items-center gap-3 border-t border-slate-800 bg-surface-950/80 py-3 backdrop-blur">
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
