// Local Vol lens · view state (split out of LocalVolViewer.tsx on 2026-09-10,
// the 400-line policy — a pure move): the per-tab remembered sub-view ·
// strike-axis mode · LV-surface render · 3D-mesh x scale · maturity clock ·
// Y chips · the Compare tab's two chips, through useLensViewMemory (Layout ▸
// "Remember view per tab"), plus the setters the toolbar and charts call.
import type { LvAxis, LvRender, LvView } from "../../components/localvol/LocalVolToolbar";
import type { AxisMode } from "../../lib/axisModes";
import { readSmileAutoScale, writeSmileAutoScale } from "../../lib/autoScaleY";
import type { AutoScaleToggles } from "../../lib/autoScaleY";
import type { LvCompareMode, LvTailTarget } from "../../lib/lvCompare";
import { useLensViewMemory } from "../../state/useLensViewMemory";
import type { LvTInterp } from "../../state/useLvCompare";
import type { ClockMode } from "../../state/useTerm";

/** What the lens remembers per tab (older memories lack the Compare chips). */
export interface LocalVolViewState {
  view: LvView; axisMode: AxisMode; lvRender: LvRender; lvAxis: LvAxis; axisClock: ClockMode;
  autoScaleY: AutoScaleToggles; lvTInterp: LvTInterp; lvTails: LvTailTarget; lvCompareMode: LvCompareMode;
}

export function useLocalVolViewState() {
  // View state: sub-view · strike-axis mode · LV-surface render (3D mesh or
  // heatmap) · x-axis scale of the 3D LV mesh · maturity clock (Term sub-tab)
  // · the Y center / Y fit chips of the 2-D charts (seeded from the same
  // persisted preference as the Parametric lens — lib/autoScaleY).
  // The Compare tab adds its two chips (t-interpolation of the twin, the
  // display mode) — remembered per tab like the rest (older memories lack
  // them and fall back to the defaults).
  const [vs, patchView] = useLensViewMemory<LocalVolViewState>("localvol", () => ({
    view: "smile", axisMode: "logmoneyness", lvRender: "mesh", lvAxis: "moneyness", axisClock: "real",
    autoScaleY: readSmileAutoScale(), lvTInterp: "smooth", lvTails: "model", lvCompareMode: "sheets",
  }));
  const { view, axisMode, lvRender, lvAxis, axisClock, autoScaleY } = vs;
  const lvTInterp: LvTInterp = vs.lvTInterp ?? "smooth";
  const lvTails: LvTailTarget = vs.lvTails ?? "model";  // the tail-target chip (2026-09-10)
  const lvCompareMode: LvCompareMode = vs.lvCompareMode ?? "sheets";
  const setView = (view: LvView) => patchView({ view });
  const setAxisMode = (axisMode: AxisMode) => patchView({ axisMode });
  const toggleAutoScale = (key: keyof AutoScaleToggles) => {
    const next = { ...autoScaleY, [key]: !autoScaleY[key] };
    writeSmileAutoScale(next);
    patchView({ autoScaleY: next });
  };
  const setLvRender = (lvRender: LvRender) => patchView({ lvRender });
  const setLvAxis = (lvAxis: LvAxis) => patchView({ lvAxis });
  const setAxisClock = (axisClock: ClockMode) => patchView({ axisClock });
  return {
    view, axisMode, lvRender, lvAxis, axisClock, autoScaleY, lvTInterp, lvTails, lvCompareMode,
    patchView, setView, setAxisMode, toggleAutoScale, setLvRender, setLvAxis, setAxisClock,
  };
}
