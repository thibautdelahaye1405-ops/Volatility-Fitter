// Universe header of the Parametric workspace: underlying / expiry selectors
// and the fit-mode segmented control. Reads the shared smile session directly
// so SmileViewer only handles chart-card concerns. The Expiry dropdown lists
// every selected expiry of the ticker (the old D/W/M/Q class-filter chips were
// removed — expiry curation lives in the Universe tab).
import { useMemo } from "react";
import SegmentedControl from "./SegmentedControl";
import { useSmileSession } from "../state/smileSession";
import type { FitMode } from "../state/useSmile";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

/** Shared styling for the header selects (also used by the axis-mode one). */
export const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function UniverseHeader() {
  const { universe, ticker, expiry, fitMode, setTicker, setExpiry, setFitMode } =
    useSmileSession();

  const ladder = useMemo(
    () => universe?.expiries[ticker] ?? [],
    [universe, ticker],
  );

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-3">
      <label className="flex items-center gap-2 text-xs text-slate-500">
        Underlying
        <select
          className={selectClass}
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
          disabled={universe === null}
        >
          {(universe?.tickers ?? []).map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-xs text-slate-500">
        Expiry
        <select
          className={selectClass}
          value={expiry}
          onChange={(e) => setExpiry(e.target.value)}
          disabled={universe === null}
        >
          {ladder.map((rung) => (
            <option key={rung.expiry} value={rung.expiry}>
              {rung.expiry} (T={rung.t.toFixed(2)}y)
            </option>
          ))}
        </select>
      </label>

      {/* Fit-mode segmented control */}
      <div className="ml-auto flex items-center gap-2">
        <span className="text-xs text-slate-500">Fit to</span>
        <SegmentedControl options={FIT_MODES} value={fitMode} onChange={setFitMode} />
      </div>
    </div>
  );
}
