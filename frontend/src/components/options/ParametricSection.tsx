// Options ▸ Parametric model: family selector (LQD / SVI / MCS) plus ONLY the
// active family's hyperparameters, penalty coefficients and penalty-table
// rows. The Local-Vol grid is a separate section, not a parametric family.
import HyperparamPanel from "../HyperparamPanel";
import type { FitSettings } from "../HyperparamPanel";
import { PenaltyTable } from "../OptionsControls";
import type { OptionsSettings } from "../../state/useOptions";
import { numInput, rowLabel, sectionTitle, subTitle } from "./shared";

export default function ParametricSection({
  fitDraft,
  fitPatch,
  draft,
  patch,
  live,
}: {
  fitDraft: FitSettings;
  fitPatch: (p: Partial<FitSettings>) => void;
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
}) {
  return (
    <>
      <h3 className={sectionTitle}>Parametric model</h3>
      <HyperparamPanel group="model" draft={fitDraft} patch={fitPatch} disabled={!live} />

      {/* MCS put-wing regularizer (OptionsSettings) — an MCS-only penalty, so
          it lives with the model it applies to. */}
      {fitDraft.model === "sigmoid" && (
        <div className="mt-1 flex items-center justify-between">
          <span
            className={rowLabel}
            title="Multi-Core Sigmoid put-wing no-butterfly regularizer (% of base; 0 = off). Zero on an arb-free slice, so liquid names are untouched."
          >
            MCS wing penalty %
          </span>
          <input
            type="number" step={10} min={0} max={1000} value={draft.sivWingPenaltyPct} disabled={!live}
            onChange={(e) => patch({ sivWingPenaltyPct: Number(e.target.value) })}
            className={numInput}
          />
        </div>
      )}

      <h4 className={subTitle}>Model penalties</h4>
      <PenaltyTable group="model" model={fitDraft.model} />
    </>
  );
}
