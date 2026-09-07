// Lazy fetch for GET /smiles/{ticker}/{expiry}/compare (V3.2 item 12).
//
// Runs ONLY while the Compare view is open (`enabled`) and ONLY for the
// requested `models` (wave 2: the prevailing calibrated family shows at once,
// the others are fitted lazily when their chip is clicked — the endpoint's
// (fit_key, model) cache makes re-toggles free). `tails` are the tail-matching
// toggles (lib/tailMatch): with any lit, the SVI-JW / MCS rows are refit with
// their tails pulled onto LQD's and the response reports what applied.
// `anchoring` are the anchoring-axis cells (lib/anchoring): each requested
// cell that exists and is not production comes back as an EXTRA row of the
// displayed family, and the response reports the axis. Keyed on the node,
// the fit mode and the smile reload key (spot transports / recalibrations),
// the same refetch triggers as the sibling surface views.
// Backendless mode falls back to the built-in mock comparison (cut to the
// requested models, the tail flags echoed as applied, the shadow rows
// synthesized from the LQD row) so the app keeps working offline.
import { useEffect, useState } from "react";
import { api } from "./api";
import { getMockComparison } from "../lib/mockData";
import type { AnchoringCell, CompareModelFit, CompareResponse, CompareTailFlag } from "../lib/mockData";
import { CHIP_MODELS } from "../lib/modelColor";
import type { FitMode } from "./useSmile";

export interface UseModelComparisonResult {
  data: CompareResponse | null;
  loading: boolean;
  error: string | null;
}

/** Mock shadow rows: a copy of the displayed-family (LQD) row per requested
 *  cell that exists and is not production, its belly eased by ~11 bp at the
 *  money (the pull the plain row reports) — the free row pulls 0. */
function mockShadowRows(plain: CompareModelFit, cells: AnchoringCell[]): CompareModelFit[] {
  return cells.map((cell) => {
    const free = cell === "free";
    const dip = free ? 0.00112 : 0.0006;
    return {
      ...plain,
      anchoring: cell,
      reused: false,
      fitMs: 8.1,
      curve: plain.curve.map((p) => ({ k: p.k, vol: p.vol - dip * Math.max(0, 1 - Math.abs(p.k) / 0.3) })),
      atmVol: (plain.atmVol ?? 0.206) - dip,
      skew: (plain.skew ?? -0.355) + (free ? 0.004 : 0.002),
      rmsBp: (plain.rmsBp ?? 18.4) - (free ? 1.3 : 0.6),
      pullAtmBp: free ? 0 : 6.4,
      pullSkew: free ? 0 : -0.002,
      pullCurveBp: free ? 0 : 5.1,
    };
  });
}

/** The mock comparison as the live endpoint would answer the same request. */
function mockComparison(modelsKey: string, tailsKey: string, anchoringKey: string): CompareResponse {
  const mock = getMockComparison();
  const wanted = new Set(modelsKey.split(","));
  const flags = tailsKey === "" ? [] : (tailsKey.split(",") as CompareTailFlag[]);
  const cells = anchoringKey === "" ? [] : (anchoringKey.split(",") as AnchoringCell[]);
  const constrained = new Set(["svi", "sigmoid"]);
  let models = mock.models
    .filter((m) => wanted.has(m.model))
    .map((m) => (flags.length > 0 && constrained.has(m.model) ? { ...m, tailMatched: flags } : m));
  const tailMatch =
    flags.length > 0
      ? { requested: flags, applied: flags, target: "lqd", leeAvailable: true, leeClamped: false }
      : null;
  const info = mock.anchoring ?? null;
  const plain = models.find((m) => m.model === "lqd");
  if (cells.length > 0 && info !== null && plain !== undefined) {
    // The plain displayed-family row carries pulls once any cell is asked.
    models = models.map((m) => (m === plain ? { ...m, pullAtmBp: 11.2, pullSkew: -0.004, pullCurveBp: 9.7 } : m));
    const extra = cells.filter((c) => info.available.includes(c) && c !== info.production);
    models = [...models, ...mockShadowRows(plain, extra)];
  }
  return { ...mock, models, tailMatch, anchoring: info === null ? null : { ...info, requested: cells } };
}

export function useModelComparison(
  enabled: boolean,
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  reloadKey = 0,
  models: readonly string[] = CHIP_MODELS, // reference families only when asked
  tails: readonly string[] = [],
  anchoring: readonly string[] = [],
): UseModelComparisonResult {
  const modelsKey = models.join(",");
  const tailsKey = tails.join(",");
  const anchoringKey = anchoring.join(",");
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) return; // lazy: fetch nothing until the Compare view opens
    if (!live || ticker === "" || expiry === "") {
      // Backendless: the app must still work — the mock, cut to the
      // requested families so the chips (incl. the reference reveal, the
      // tail toggles and the anchoring cells) behave.
      setData(mockComparison(modelsKey, tailsKey, anchoringKey));
      setLoading(false);
      setError(null);
      return;
    }
    let active = true; // drop results landing after unmount / a newer key
    setLoading(true);
    setError(null);
    api
      .get<CompareResponse>(`/smiles/${ticker}/${expiry}/compare`, {
        params: {
          models: modelsKey,
          fit_mode: fitMode,
          ...(tailsKey === "" ? {} : { tail_match: tailsKey }),
          ...(anchoringKey === "" ? {} : { anchoring: anchoringKey }),
        },
        timeoutMs: 120_000, // up to two extra fits on a cold node
      })
      .then((d) => {
        if (!active) return;
        setData(d);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setData(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      active = false;
    };
  }, [enabled, live, ticker, expiry, fitMode, reloadKey, modelsKey, tailsKey, anchoringKey]);

  return { data, loading, error };
}
