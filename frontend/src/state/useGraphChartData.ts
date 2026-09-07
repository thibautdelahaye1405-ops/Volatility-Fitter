// Chart-data derivation of the Graph lens (GRAPH ERGONOMICS ARC, E6 —
// extracted from GraphViewer at the file-size cap). With the calibrations
// source the chart is driven by the production solve: the full SELECTED
// lit+dark universe (prior handles as the baseline), the calibrated nodes lit
// (amber ring = an observation) and the posterior field. Before the first
// Run it falls back to the baseline universe so the chart is never blank.
// In the manual what-if the lit set stays the EDITABLE pulse set.
import { useMemo } from "react";
import { nodeKey, type GraphNodeBase, type GraphSolveNode, type UseGraphResult } from "./useGraph";
import type { UseGraphExtrapolationResult } from "./useGraphExtrapolation";
import type { RunSummary } from "../components/graphshell/GraphTopBar";

export interface GraphChartData {
  chartNodes: GraphNodeBase[] | null;
  chartLit: Record<string, number>;
  chartResults: Record<string, GraphSolveNode> | null;
  /** A production field is on screen. */
  extrapolating: boolean;
  summary: RunSummary | null;
  litCount: number;
  darkCount: number;
}

export function useGraphChartData(
  graph: UseGraphResult,
  extra: UseGraphExtrapolationResult,
  manual: boolean,
): GraphChartData {
  const extraChartNodes = useMemo<GraphNodeBase[] | null>(
    () =>
      extra.nodes === null
        ? null
        : extra.nodes.map((n) => ({
            ticker: n.ticker,
            expiry: n.expiry,
            t: n.t,
            atmVol: n.priorAtmVol,
            skew: n.priorSkew,
            curvature: n.priorCurv,
            lit: n.lit,
          })),
    [extra.nodes],
  );
  const extraChartLit = useMemo<Record<string, number>>(
    () =>
      extra.nodes === null
        ? {}
        : Object.fromEntries(
            extra.nodes.filter((n) => n.calibrated).map((n) => [nodeKey(n.ticker, n.expiry), 0]),
          ),
    [extra.nodes],
  );
  const extrapolating = extraChartNodes !== null;
  const chartNodes = extrapolating ? extraChartNodes : graph.nodes;
  const chartLit = manual ? graph.lit : extrapolating ? extraChartLit : {};
  const chartResults = extra.results;

  const summary = useMemo<RunSummary | null>(() => {
    if (chartResults === null) return null;
    const all = Object.values(chartResults);
    const observed = all.filter((n) => n.observed).length;
    const maxAbs = all.reduce((m, n) => Math.max(m, Math.abs(n.shiftBp)), 0);
    return { observed, extrapolated: all.length - observed, maxAbs };
  }, [chartResults]);

  const litCount =
    extrapolating || manual
      ? Object.keys(chartLit).length
      : (chartNodes ?? []).filter((n) => n.lit).length;
  const darkCount = Math.max(0, (chartNodes ?? []).length - litCount);

  return { chartNodes, chartLit, chartResults, extrapolating, summary, litCount, darkCount };
}
