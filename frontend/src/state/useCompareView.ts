// Compare wiring of the Parametric lens (extracted from SmileViewer so the
// view stays under the file-size policy): which families the Compare view
// fits, the tail-matching toggles, the anchoring-axis cells, the lazy fetch
// and the chart's x-coordinate.
//
// The prevailing calibrated family (the smile's modelInfo) shows at once;
// the others are fitted lazily when their chip is clicked. The selections
// live in the lens's view state (remembered per tab) — the extra families
// reset when the SAME node's prevailing model changes (a recalibration under
// another family); the tail and anchoring toggles are family-agnostic and
// survive it. Tail matching (lib/tailMatch) makes LQD the reference, so it
// joins the comparison whenever a toggle is lit. Anchoring cells
// (lib/anchoring) are sent in wire order whatever the click order.
import { useEffect, useMemo, useRef } from "react";
import { prevailingModelId } from "../components/parametric/CompareChips";
import { ANCHORING_ORDER } from "../lib/anchoring";
import { axisTransform, makeVolAt } from "../lib/axisModes";
import type { AxisContext, AxisMode } from "../lib/axisModes";
import { MODEL_ORDER } from "../lib/modelColor";
import type { AnchoringCell, CompareModelId, CompareTailFlag, SmileData } from "../lib/mockData";
import { useModelComparison } from "./useModelComparison";
import type { UseModelComparisonResult } from "./useModelComparison";
import type { FitMode } from "./useSmile";

/** The slice of the lens view state the Compare view owns. */
export interface CompareViewState {
  /** Extra Compare families beyond the prevailing one (chips clicked). */
  compareExtra: CompareModelId[];
  /** Tail-matching toggles lit (lib/tailMatch): the SVI-JW / MCS rows refit
   *  with their tails pulled onto LQD's. */
  compareTails: CompareTailFlag[];
  /** Anchoring cells lit (lib/anchoring): the prevailing family refit with
   *  the prior / filter removed or added, as extra shadow rows. */
  compareAnchoring: AnchoringCell[];
}

export interface UseCompareViewOptions {
  vs: CompareViewState;
  patchView: (patch: Partial<CompareViewState>) => void;
  smile: SmileData | null;
  /** "ticker|expiry" of the displayed smile ("" while none). */
  smileKey: string;
  live: boolean;
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** The session's view version (spot transports / recalibrations refetch). */
  spotVersion: number;
  axisMode: AxisMode;
  /** True while the Compare view is open (the fetch is lazy). */
  enabled: boolean;
}

export interface CompareView {
  prevailing: CompareModelId;
  /** The families asked of the endpoint, in wire order. */
  compareModels: CompareModelId[];
  compareTails: CompareTailFlag[];
  compareAnchoring: AnchoringCell[];
  toggleModel: (id: CompareModelId) => void;
  toggleTail: (flag: CompareTailFlag) => void;
  toggleAnchoring: (cell: AnchoringCell) => void;
  comparison: UseModelComparisonResult;
  /** Log-moneyness k -> the chart's x coordinate under the axis mode. */
  compareTx: (k: number) => number;
}

/** Toggle one entry of a list, order of first selection kept. */
function toggled<T>(list: readonly T[], item: T): T[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export function useCompareView(o: UseCompareViewOptions): CompareView {
  const { vs, patchView, smile, smileKey, axisMode } = o;
  const prevailing = prevailingModelId(smile?.modelInfo?.id, smile?.modelInfo?.label);
  // The extra selection resets when the SAME node's prevailing model changes.
  const prevailingRef = useRef<{ key: string; model: CompareModelId | null }>({ key: "", model: null });
  useEffect(() => {
    const prev = prevailingRef.current;
    prevailingRef.current = { key: smileKey, model: prevailing };
    if (prev.key === smileKey && prev.model !== prevailing && vs.compareExtra.length > 0) {
      patchView({ compareExtra: [] });
    }
  }, [smileKey, prevailing]); // eslint-disable-line react-hooks/exhaustive-deps

  // Older remembered view states predate the toggle fields.
  const compareTails = vs.compareTails ?? [];
  const compareAnchoring = vs.compareAnchoring ?? [];
  const compareModels = useMemo(
    () => MODEL_ORDER.filter(
      (m) => m === prevailing || vs.compareExtra.includes(m) || (m === "lqd" && compareTails.length > 0),
    ),
    [prevailing, vs.compareExtra, compareTails],
  );
  const anchoringWire = useMemo(
    () => ANCHORING_ORDER.filter((c) => compareAnchoring.includes(c)),
    [compareAnchoring],
  );
  const toggleModel = (id: CompareModelId) => patchView({ compareExtra: toggled(vs.compareExtra, id) });
  const toggleTail = (flag: CompareTailFlag) => patchView({ compareTails: toggled(compareTails, flag) });
  const toggleAnchoring = (cell: AnchoringCell) => patchView({ compareAnchoring: toggled(compareAnchoring, cell) });

  const comparison = useModelComparison(
    o.enabled, o.live, o.ticker, o.expiry, o.fitMode, o.spotVersion, compareModels, compareTails, anchoringWire,
  );

  // Compare chart x-axis: the smile's own context (forward, T, ATM vol, the
  // prevailing fit's vol at k for the delta mode) — ONE coordinate for every
  // family, so the curves stay comparable; identity in log-moneyness.
  const compareTx = useMemo(() => {
    if (smile === null || axisMode === "logmoneyness") return (k: number) => k;
    const ctx: AxisContext = {
      forward: smile.forward, t: smile.T, atmVol: smile.diagnostics.atmVol,
      volAt: makeVolAt(smile.model), kRange: [smile.kMin, smile.kMax],
    };
    return (k: number) => axisTransform(axisMode, k, ctx);
  }, [smile, axisMode]);

  return {
    prevailing, compareModels, compareTails, compareAnchoring,
    toggleModel, toggleTail, toggleAnchoring, comparison, compareTx,
  };
}
