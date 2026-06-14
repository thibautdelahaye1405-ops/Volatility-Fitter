// Scenario and distribution side-channels of the smile session.
//
// Two focused hooks composed by useSmile():
//  - useScenarioCurve — debounced POST /scenario/ssr: the smile re-priced
//    under a hypothetical spot return and a vol-spot dynamics regime
//    (sticky moneyness / strike / local-vol), drawn as a chart overlay.
//  - useDistribution — lazy GET /smiles/{ticker}/{expiry}/density: the
//    risk-neutral pdf over log-returns and its (log) quantile density, backing
//    the Density / Log-Q-density chart views.
// Both require the live backend: in mock mode they resolve to null.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { FitMode } from "./useSmile";
import type { SmileData, SmilePoint } from "../lib/mockData";

/** Vol-spot dynamics regime understood by the SSR scenario engine.
 *  "sticky_local_vol_grid" is the exact mode: the extracted local-vol grid is
 *  held fixed in absolute strike and the smile re-priced through the Dupire
 *  PDE (the others are SSR shape rules applied to the fitted slice). */
export type Regime =
  | "sticky_moneyness"
  | "sticky_strike"
  | "sticky_local_vol"
  | "sticky_local_vol_grid";

/** User-controlled scenario inputs (regime control + spot-return slider). */
export interface ScenarioState {
  /** Hypothetical spot return, e.g. -0.02 for a 2% sell-off. 0 = overlay off. */
  spotReturn: number;
  regime: Regime;
}

/** Response of POST /scenario/ssr. */
interface SsrScenarioResponse {
  k: number[];
  baseVol: number[];
  shiftedVol: number[];
  /** Skew-stickiness ratio implied by the regime. */
  ssr: number;
  regime: string;
}

/** Overlay curve + headline SSR exposed to the view (nulls = overlay off). */
export interface ScenarioResult {
  scenarioCurve: SmilePoint[] | null;
  scenarioSsr: number | null;
}

/** Shared "no overlay" value so repeated clears bail out of re-renders. */
const NO_SCENARIO: ScenarioResult = { scenarioCurve: null, scenarioSsr: null };

/** Debounce before hitting /scenario/ssr while the slider is dragged. */
const SCENARIO_DEBOUNCE_MS = 150;

/**
 * Fetch the SSR-shifted smile for the current node whenever the scenario is
 * active (spotReturn != 0). Slider drags are debounced; superseded requests
 * are aborted; any failure simply removes the overlay.
 */
export function useScenarioCurve(
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  scenario: ScenarioState,
): ScenarioResult {
  const [result, setResult] = useState<ScenarioResult>(NO_SCENARIO);

  // A stale overlay is worse than none: drop it the moment the node changes
  // (the fetch effect below then repopulates it for the new node).
  useEffect(() => {
    setResult(NO_SCENARIO);
  }, [ticker, expiry]);

  useEffect(() => {
    if (!live || ticker === "" || expiry === "" || scenario.spotReturn === 0) {
      setResult(NO_SCENARIO);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      api
        .post<SsrScenarioResponse>("/scenario/ssr", {
          body: {
            ticker,
            expiry,
            spotReturn: scenario.spotReturn,
            regime: scenario.regime,
            fitMode,
          },
          signal: controller.signal,
        })
        .then((res) => {
          setResult({
            scenarioCurve: res.k.map((k, i) => ({ k, vol: res.shiftedVol[i] })),
            scenarioSsr: res.ssr,
          });
        })
        .catch(() => {
          // Fetch error (or 4xx): show no overlay rather than a broken one.
          if (!controller.signal.aborted) setResult(NO_SCENARIO);
        });
    }, SCENARIO_DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [live, ticker, expiry, fitMode, scenario.spotReturn, scenario.regime]);

  return result;
}

/* ------------------------------------------------------------------ */
/* Risk-neutral distribution (Density / Log-Q-density views)            */
/* ------------------------------------------------------------------ */

/** One distribution payload: pdf on a log-return grid + quantile function. */
export interface DistributionCurve {
  /** Log-return grid x = ln(S_T / F) for the density. */
  x: number[];
  density: number[];
  /** Probability grid in [0, 1] for the quantile function. */
  u: number[];
  quantile: number[];
}

/** Response of GET /smiles/{ticker}/{expiry}/density. */
export interface DistributionData {
  current: DistributionCurve;
  /** Saved prior's distribution, or null when no prior exists. */
  prior: DistributionCurve | null;
}

/** What useDistribution exposes to the view. */
export interface UseDistributionResult {
  distribution: DistributionData | null;
  distributionLoading: boolean;
  /** Arm the fetcher; called when a distribution view is first opened. */
  loadDistribution: () => void;
}

/**
 * Lazily fetch the fitted distribution of the current node. Nothing is
 * requested until loadDistribution() arms the hook; once armed, it refetches
 * whenever the displayed smile changes identity — node switches and refits
 * both produce a new `smile` object, so that is the whole cache story.
 */
export function useDistribution(
  live: boolean,
  ticker: string,
  expiry: string,
  fitMode: FitMode,
  smile: SmileData | null,
): UseDistributionResult {
  const [active, setActive] = useState(false);
  const [distribution, setDistribution] = useState<DistributionData | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDistribution = useCallback(() => setActive(true), []);

  useEffect(() => {
    if (!active) return;
    if (!live || ticker === "" || expiry === "" || smile === null) {
      setDistribution(null); // mock mode: distribution views need the backend
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    api
      .get<DistributionData>(`/smiles/${ticker}/${expiry}/density`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((d) => {
        setDistribution(d);
        setLoading(false);
      })
      .catch(() => {
        if (controller.signal.aborted) return; // superseded, not a failure
        setDistribution(null);
        setLoading(false);
      });
    return () => controller.abort();
  }, [active, live, ticker, expiry, fitMode, smile]);

  return { distribution, distributionLoading: loading, loadDistribution };
}
