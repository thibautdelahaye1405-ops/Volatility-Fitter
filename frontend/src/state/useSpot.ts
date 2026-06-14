// Manual spot-move control for the shared smile session.
//
// The slider drives a hypothetical spot move (no recalibration): dragging it PUTs
// a per-ticker spot shift that the backend transports the calibrated smile / term
// / LV-grid by (volfit.dynamics.transport). Real-time spot polling and timed
// options fetches are owned by the BACKEND scheduler now (Options spotMode /
// optionsFetchMode); this hook only handles the manual slider + per-ticker
// re-anchor, and signals the session to refresh every workspace's views via
// `refreshViews` (which bumps the version those fetchers depend on).
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Response of GET/PUT /spot/{ticker} (and POST /spot/{ticker}/calibrate). */
export interface SpotState {
  ticker: string;
  anchorSpot: number;
  spotReturn: number;
  shiftedSpot: number;
  regime: string;
  regimeSsr: number;
}

/** Slider-drag PUT debounce (ms). */
const PUT_DEBOUNCE_MS = 120;

export interface UseSpotResult {
  /** Active proportional spot shift of the current ticker (0 = anchored). */
  spotReturn: number;
  /** Last spot state from the backend (anchor/shifted spot, regime, SSR). */
  spotState: SpotState | null;
  /** Set the hypothetical shift (debounced PUT; transports every view). */
  setSpotReturn: (r: number) => void;
  /** Re-anchor this ticker: clear the shift and recalibrate at the live spot. */
  recalibrate: () => Promise<void>;
}

export function useSpot(
  live: boolean,
  ticker: string,
  refreshViews: () => void,
): UseSpotResult {
  const [spotReturn, setSpotReturnState] = useState(0);
  const [spotState, setSpotState] = useState<SpotState | null>(null);
  const putTimer = useRef<number | undefined>(undefined);

  // Sync the displayed shift to the backend whenever the ticker changes (each
  // ticker holds its own shift); mock mode shows no spot controls.
  useEffect(() => {
    if (!live || ticker === "") {
      setSpotState(null);
      setSpotReturnState(0);
      return;
    }
    const controller = new AbortController();
    api
      .get<SpotState>(`/spot/${ticker}`, { signal: controller.signal })
      .then((s) => {
        setSpotState(s);
        setSpotReturnState(s.spotReturn);
      })
      .catch(() => {});
    return () => controller.abort();
  }, [live, ticker]);

  const applyShift = useCallback(
    (r: number) => {
      if (!live || ticker === "") return;
      api
        .put<SpotState>(`/spot/${ticker}`, { body: { spotReturn: r } })
        .then((s) => {
          setSpotState(s);
          refreshViews();
        })
        .catch(() => {});
    },
    [live, ticker, refreshViews],
  );

  const setSpotReturn = useCallback(
    (r: number) => {
      setSpotReturnState(r); // immediate slider feedback
      window.clearTimeout(putTimer.current);
      putTimer.current = window.setTimeout(() => applyShift(r), PUT_DEBOUNCE_MS);
    },
    [applyShift],
  );

  const recalibrate = useCallback(async () => {
    if (!live || ticker === "") return;
    const s = await api.post<SpotState>(`/spot/${ticker}/calibrate`);
    setSpotState(s);
    setSpotReturnState(0);
    refreshViews();
  }, [live, ticker, refreshViews]);

  return { spotReturn, spotState, setSpotReturn, recalibrate };
}
