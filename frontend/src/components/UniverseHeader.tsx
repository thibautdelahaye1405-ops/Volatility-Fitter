// Workspace header of the Parametric screen: Underlying / Expiry selectors,
// then the caller's view controls (sub-tabs, axis mode, overlays) via
// `children`, with status badges right-aligned via `right` — the same header
// grammar as the Local Vol workspace, so the two screens read identically.
// The fit target and the expiry-label format are settings (Options ▸
// Calibration and brand menu ▸ View), not per-screen toggles.
import { useMemo } from "react";
import type { ReactNode } from "react";
import { useSmileSession } from "../state/smileSession";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";

/** Shared styling for the header selects (also used by the axis-mode one). */
export const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function UniverseHeader({
  children,
  right,
}: {
  /** View controls rendered after the selectors (sub-tabs, axis mode, …). */
  children?: ReactNode;
  /** Right-aligned status badges. */
  right?: ReactNode;
}) {
  const { universe, ticker, expiry, setTicker, setExpiry } = useSmileSession();
  const { format } = useExpiryFormat();

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
              {formatExpiry(rung.expiry, rung.t, format)}
            </option>
          ))}
        </select>
      </label>

      {children}

      {right !== undefined && (
        <div className="ml-auto flex items-center gap-2">{right}</div>
      )}
    </div>
  );
}
