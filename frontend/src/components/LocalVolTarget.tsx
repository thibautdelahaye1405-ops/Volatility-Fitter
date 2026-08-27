// Fit-target overlay of the Local-Vol smile chart (V3.4 rider) and its chip.
//
// The LV payload's quotes carry the same targetLo/targetHi the Parametric
// smile payload does (backend affine_fit._quote_bands, resolved by the fit's
// own band rule), so the overlay mirrors QuoteLayer's "market" variant one for
// one: the faint bid-ask ribbon, the haircut ribbon in "haircut" mode, and the
// thin mid polyline (the target in "mid", the soft anchor in the band modes).
// Excluded strikes leave a gap in the ribbons, exactly as on the Parametric
// chart (lib/smileTarget builds both). Kept out of LocalVolSmile.tsx (the
// file-size policy) and geometry-only, so it is testable with plain toX/toY.
import { useCallback, useState } from "react";
import type { QuoteBand } from "../state/useAffine";
import type { FitMode } from "../state/useSmile";
import { midLinePath, ribbonPath } from "../lib/smileTarget";

/** localStorage key of the chip state (per browser; absent = ON). */
export const LV_SHOW_TARGET_KEY = "volfit.lvShowTarget";

function readStored(): boolean {
  try {
    const v = window.localStorage.getItem(LV_SHOW_TARGET_KEY);
    return v === null ? true : v === "1";
  } catch {
    return true; // storage blocked (private window / sandbox): the default
  }
}

/** The "Target" chip state, persisted under LV_SHOW_TARGET_KEY. Storage
 *  failures are swallowed so the chart always renders (session-only then). */
export function useLvShowTarget(): [boolean, (on: boolean) => void] {
  const [on, setOn] = useState<boolean>(readStored);
  const set = useCallback((next: boolean) => {
    setOn(next);
    try {
      window.localStorage.setItem(LV_SHOW_TARGET_KEY, next ? "1" : "0");
    } catch {
      /* storage unavailable: keep the in-memory state only */
    }
  }, []);
  return [on, set];
}

/** QuoteLayer's "market" palette — the LV chart's quotes are the same red. */
const STYLE = {
  ribbon: "rgb(248 113 113 / 0.10)",
  haircut: "rgb(248 113 113 / 0.35)",
  midLine: "rgb(248 113 113 / 0.6)",
};

interface LayerProps {
  quotes: readonly QuoteBand[];
  fitMode: FitMode;
  /** The chip: off ⇒ nothing is rendered. */
  show: boolean;
  /** k (the quote's log-moneyness) -> pixel x: the chart's axis-mode transform
   *  composed with its x scale, so the overlay follows the strike / %ATM axes. */
  toX: (k: number) => number;
  toY: (vol: number) => number;
}

/** The overlay itself — render UNDER the quote beams, inside the clip group. */
export function LocalVolTargetLayer({ quotes, fitMode, show, toX, toY }: LayerProps) {
  if (!show) return null;
  // Same rule as QuoteLayer: the bid-ask ribbon is always the faint context,
  // the haircut ribbon only in "haircut" mode (in "bidask" the target IS the
  // raw band — drawing it twice would just double the opacity).
  const bidAsk = ribbonPath(quotes, (q) => q.bid, (q) => q.ask, toX, toY);
  const haircut =
    fitMode === "haircut"
      ? ribbonPath(quotes, (q) => q.targetLo, (q) => q.targetHi, toX, toY)
      : "";
  const midLine = midLinePath(quotes, toX, toY);
  return (
    <g data-testid="lv-target-layer">
      {bidAsk !== "" && (
        <path data-testid="lv-target-bidask" d={bidAsk} fill={STYLE.ribbon} stroke="none"
          pointerEvents="none" />
      )}
      {haircut !== "" && (
        <path data-testid="lv-target-haircut" d={haircut} fill={STYLE.haircut} stroke="none"
          pointerEvents="none" />
      )}
      {midLine !== "" && (
        <path data-testid="lv-target-mid" d={midLine} fill="none" stroke={STYLE.midLine}
          strokeWidth={1} pointerEvents="none" />
      )}
    </g>
  );
}

const MODE_LABEL: Record<FitMode, string> = { mid: "mid", bidask: "bid-ask", haircut: "haircut" };

/** The "Target" chip (top-right of the chart): toggles the overlay; its label
 *  names the active fit target so the ribbon's meaning is never ambiguous. */
export function LocalVolTargetChip({
  on, fitMode, onToggle,
}: {
  on: boolean;
  fitMode: FitMode;
  onToggle: (on: boolean) => void;
}) {
  const mode = MODE_LABEL[fitMode];
  return (
    <button
      type="button"
      data-testid="lv-target-chip"
      aria-pressed={on}
      onClick={() => onToggle(!on)}
      title={`Fit target overlay (${mode} mode) — ${on ? "shown; click to hide" : "hidden; click to show"}`}
      className={
        "absolute right-2 top-1 rounded-md border px-2 py-0.5 text-[10px] shadow transition " +
        (on
          ? "border-accent-500/50 bg-accent-500/10 text-accent-300 hover:bg-accent-500/20"
          : "border-slate-700 bg-surface-800/95 text-slate-400 hover:text-slate-200")
      }
    >
      Target · {mode}
    </button>
  );
}
