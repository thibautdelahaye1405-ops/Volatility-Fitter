// Fit switch of the chart-card header (ANCHORING AXIS, lib/anchoring): on
// the Smile and Density views, draw one SHADOW fit of the axis — Free (no
// prior, no filter), + Prior, + Filter — in place of the production fit.
// The quotes, the prior overlay and the committed calibration stay the
// node's; only the curve and its diagnostics read the shadow. Rendered only
// when the node reports at least one non-production cell (a switch with
// Production alone has nothing to draw). The SHADOW pill appears once the
// payload actually carries a shadow (modelInfo.anchoring), so the header
// never says "shadow" while production is still on screen.
import SegmentedControl from "../SegmentedControl";
import { ANCHORING_SHORT, ANCHORING_TITLES, fitSwitchOptions } from "../../lib/anchoring";
import type { FitAnchoring } from "../../lib/anchoring";
import type { AnchoringCell, AnchoringInfo } from "../../lib/mockData";

const SWITCH_TITLE =
  "Fit switch — draw a shadow fit of the anchoring axis instead of the production fit: " +
  "Free (no prior, no filter), + Prior, + Filter. The committed calibration is untouched.";

export interface FitAnchoringSwitchProps {
  /** The node's axis report (smile.anchoring); nothing renders without it. */
  info: AnchoringInfo | null | undefined;
  /** The view's choice; a cell the node no longer offers reads Production. */
  value: FitAnchoring;
  onChange: (next: FitAnchoring) => void;
  /** The cell the displayed payload was drawn in (modelInfo.anchoring);
   *  null / absent = production. */
  drawn?: AnchoringCell | null;
}

export default function FitAnchoringSwitch({ info, value, onChange, drawn }: FitAnchoringSwitchProps) {
  if (info == null) return null;
  const options = fitSwitchOptions(info);
  if (options.length < 2) return null;
  const current: FitAnchoring = options.some((o) => o.id === value) ? value : "production";
  return (
    <div className="flex shrink-0 items-center gap-1.5" title={SWITCH_TITLE} data-fit-anchoring={current}>
      <span className="text-[9px] font-semibold uppercase tracking-wider text-slate-600">fit</span>
      <SegmentedControl options={options} value={current} onChange={onChange} size="xs" />
      {drawn != null && (
        <span
          className="rounded border border-sky-500/30 bg-sky-500/10 px-1 py-px text-[9px] font-medium tracking-wider text-sky-300"
          title={`Shadow fit drawn instead of production — ${ANCHORING_TITLES[drawn]}`}
        >
          SHADOW · {ANCHORING_SHORT[drawn]}
        </span>
      )}
    </div>
  );
}
