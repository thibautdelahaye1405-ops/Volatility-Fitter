// U7 side-by-side current-day LOO: the SAME mode-aware backtest endpoint run
// once per operator (sequentially — each LOO is a full solve per held-out
// node), plus the TRANSPORTED-PRIOR comparator derived client-side from the
// rows' priorAtmVol (no propagation: residual = calibrated − prior; it has no
// calibrated uncertainty, so ζ/coverage are honestly n/a). Coverage 80/95 is
// computed client-side from the standardized residuals.
import { useCallback, useState } from "react";
import { api } from "./api";
import type { BacktestResult, ExtrapolateBody } from "./useGraphExtrapolation";

/** One comparison column (null metrics = not defined for that comparator). */
export interface LooColumn {
  label: string;
  n: number;
  rmseBp: number;
  zetaMean: number | null;
  zetaStd: number | null;
  cov80: number | null;
  cov95: number | null;
}

const Z80 = 1.2816; // two-sided 80% normal quantile
const Z95 = 1.96;

/** Column for a solved operator: wire aggregates + client-side coverage. */
export function operatorColumn(label: string, resp: BacktestResult): LooColumn {
  const zetas = resp.nodes.map((n) => Math.abs(n.standardizedResidual));
  const frac = (z: number) =>
    zetas.length === 0 ? null : zetas.filter((v) => v <= z).length / zetas.length;
  return {
    label,
    n: resp.nScored,
    rmseBp: resp.rmseBp,
    zetaMean: resp.zetaMean,
    zetaStd: resp.zetaStd,
    cov80: frac(Z80),
    cov95: frac(Z95),
  };
}

/** The no-propagation comparator from the rows' transported priors. */
export function priorColumn(resp: BacktestResult): LooColumn {
  const residuals = resp.nodes
    .filter((n) => n.priorAtmVol !== null && n.priorAtmVol !== undefined)
    .map((n) => (n.calibratedAtmVol - (n.priorAtmVol as number)) * 1e4);
  const rmse =
    residuals.length === 0
      ? 0
      : Math.sqrt(residuals.reduce((s, r) => s + r * r, 0) / residuals.length);
  return {
    label: "Transported prior",
    n: residuals.length,
    rmseBp: rmse,
    zetaMean: null,
    zetaStd: null,
    cov80: null,
    cov95: null,
  };
}

export interface UseLooComparisonResult {
  /** [transported prior, smooth field, messages] once a run completed. */
  columns: LooColumn[] | null;
  /** The operator currently being scored, or null when idle. */
  running: string | null;
  error: string | null;
  run: (smoothBody: ExtrapolateBody, messagesBody: ExtrapolateBody) => Promise<void>;
}

export function useLooComparison(): UseLooComparisonResult {
  const [columns, setColumns] = useState<LooColumn[] | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (smoothBody: ExtrapolateBody, messagesBody: ExtrapolateBody) => {
      setError(null);
      try {
        // Sequential by design: each LOO is heavy; two at once would thrash.
        setRunning("smooth field");
        const smooth = await api.post<BacktestResult>("/graph/backtest", {
          body: smoothBody,
          timeoutMs: 300_000,
        });
        setRunning("messages");
        const messages = await api.post<BacktestResult>("/graph/backtest", {
          body: messagesBody,
          timeoutMs: 300_000,
        });
        setColumns([
          priorColumn(smooth),
          operatorColumn("Smooth field", smooth),
          operatorColumn("Messages", messages),
        ]);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRunning(null);
      }
    },
    [],
  );

  return { columns, running, error, run };
}
