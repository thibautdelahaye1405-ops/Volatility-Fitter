// Options ▸ Calibration: what all fits target and how residuals are weighted —
// fit target, haircut, quote weighting, band mid anchor, calendar-arbitrage
// enforcement, the extrapolation guard, and the variance-swap feature (its
// knobs render only while the feature is on).
import HyperparamPanel from "../HyperparamPanel";
import type { FitSettings } from "../HyperparamPanel";
import { PenaltyTable, Segmented, Toggle } from "../OptionsControls";
import type { OptionsSettings } from "../../state/useOptions";
import type { FitMode } from "../../state/useSmile";
import { numInput, rowLabel, sectionTitle, subTitle } from "./shared";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

export default function CalibrationSection({
  fitDraft,
  fitPatch,
  draft,
  patch,
  live,
  fitMode,
  setFitMode,
}: {
  fitDraft: FitSettings;
  fitPatch: (p: Partial<FitSettings>) => void;
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
  fitMode: FitMode;
  setFitMode: (m: FitMode) => void;
}) {
  return (
    <>
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
        <HyperparamPanel group="calibration" draft={fitDraft} patch={fitPatch} disabled={!live} />
      </div>

      <h4 className={subTitle}>Arbitrage enforcement</h4>
      <Toggle
        label="Arbitrage fix"
        hint="Calendar-couple the Calibrate job: fit each ticker's expiries in order, enforcing the convex-order (no-calendar-arbitrage) floor"
        checked={draft.enforceCalendar} disabled={!live}
        onChange={(v) => patch({ enforceCalendar: v })}
      />
      <div className="mt-1 flex items-center justify-between">
        <span
          className={rowLabel}
          title="Symmetric (default): fit every expiry independently, screen adjacent pairs for an identified violation on their common quote support, then jointly repair only the violating runs - no front-to-back bias, corrections shared by quote precision. Sequential: the historical nearest-to-farthest pass where each slice inherits the previous one as a hard floor."
        >
          Surface solver
        </span>
        <select
          value={draft.surfaceSolver}
          disabled={!live || !draft.enforceCalendar}
          onChange={(e) => patch({ surfaceSolver: e.target.value as "symmetric" | "sequential" })}
          className={numInput}
        >
          <option value="symmetric">Symmetric (screen + joint repair)</option>
          <option value="sequential">Sequential (front-to-back floor)</option>
        </select>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span className={rowLabel} title="Quadratic calendar-slack penalty weight (surface fits)">
          Calendar weight
        </span>
        <input
          type="number" step={1e5} min={0} value={draft.calendarWeight} disabled={!live}
          onChange={(e) => patch({ calendarWeight: Number(e.target.value) })}
          className={numInput}
        />
      </div>
      <Toggle
        label="Extrapolation guard"
        hint="Tapered no-arb enforcement beyond the quoted strikes (SVI/MCS): butterfly + calendar hinges over the time-value envelope, weighted like a handful of extra quotes - leans, never outvotes the data. The Quality tab measures this region either way."
        checked={draft.extrapEnforce} disabled={!live}
        onChange={(v) => patch({ extrapEnforce: v })}
      />

      <h4 className={subTitle}>Variance swaps</h4>
      <Toggle
        label="Variance-swaps"
        hint="Add var-swap quotes (Smile/Term/Table) with a calibration penalty pulling the model var-swap to the quote"
        checked={draft.varSwapEnabled} disabled={!live}
        onChange={(v) => patch({ varSwapEnabled: v })}
      />
      {draft.varSwapEnabled && (
        <>
          <div className="mt-1 flex items-center justify-between">
            <span
              className={rowLabel}
              title="Var-swap penalty weight as a % of the summed option-quote weights of the same (asset, expiry) node — at 100% the var-swap weighs as much as all option quotes combined"
            >
              Var-swap weight (%)
            </span>
            <input
              type="number" step={1} min={0} value={draft.varSwapWeightPct} disabled={!live}
              onChange={(e) => patch({ varSwapWeightPct: Number(e.target.value) })}
              className={numInput}
            />
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span
              className={rowLabel}
              title="How the Local-Vol fit prices the model variance swap: static log-contract strike replication (k^-2 weighted, grid-sensitive in the wings), or the backward source PDE g(0,1) — a local quantity robust to a coarse/truncated strike grid"
            >
              Var-swap pricing
            </span>
            <select
              value={draft.varSwapMethod}
              disabled={!live}
              onChange={(e) => patch({ varSwapMethod: e.target.value as "static" | "source_pde" })}
              className={numInput}
            >
              <option value="static">Static (replication)</option>
              <option value="source_pde">Source PDE</option>
            </select>
          </div>
        </>
      )}

      <h4 className={subTitle}>Calibration penalties</h4>
      <PenaltyTable group="calibration" />
    </>
  );
}
