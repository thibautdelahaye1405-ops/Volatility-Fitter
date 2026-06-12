// Universe header of the Smile workspace: underlying / expiry selectors,
// expiry-class filter chips (daily / weekly / monthly / quarterly / LEAPS)
// and the fit-mode segmented control. Reads the shared smile session
// directly so SmileViewer only handles chart-card concerns.
//
// The class filter is multi-select: chips toggle, "All" resets. It only
// narrows the Expiry dropdown options; when the current expiry is filtered
// out, the first surviving rung is auto-selected.
import { useEffect, useMemo, useState } from "react";
import SegmentedControl from "./SegmentedControl";
import { useSmileSession } from "../state/smileSession";
import type { ExpiryClass, FitMode } from "../state/useSmile";

const FIT_MODES: { id: FitMode; label: string }[] = [
  { id: "mid", label: "Mid" },
  { id: "bidask", label: "Bid-Ask" },
  { id: "haircut", label: "Haircut" },
];

/** Chip definitions in display order; only classes present are rendered. */
const CLASS_CHIPS: { id: ExpiryClass; label: string }[] = [
  { id: "daily", label: "D" },
  { id: "weekly", label: "W" },
  { id: "monthly", label: "M" },
  { id: "quarterly", label: "Q" },
  { id: "leaps", label: "LEAPS" },
];

/** Shared styling for the header selects (also used by the axis-mode one). */
export const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

/** Filter-chip styling, active vs idle. */
const chipClass = (active: boolean) =>
  [
    "rounded border px-1.5 py-0.5 text-[10px] font-semibold tracking-wider transition-colors",
    active
      ? "border-accent-500/60 bg-accent-500/15 text-accent-400"
      : "border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-200",
  ].join(" ");

export default function UniverseHeader() {
  const { universe, ticker, expiry, fitMode, setTicker, setExpiry, setFitMode } =
    useSmileSession();

  // Selected expiry classes; empty = no filter ("All").
  const [classFilter, setClassFilter] = useState<ExpiryClass[]>([]);

  const ladder = useMemo(
    () => universe?.expiries[ticker] ?? [],
    [universe, ticker],
  );

  // Chips for the classes actually present in this ticker's ladder.
  const presentChips = useMemo(
    () => CLASS_CHIPS.filter((c) => ladder.some((r) => r.expiryType === c.id)),
    [ladder],
  );

  // Effective filter: drop selections that vanished on a ticker switch.
  const active = useMemo(
    () => classFilter.filter((c) => presentChips.some((p) => p.id === c)),
    [classFilter, presentChips],
  );

  const filteredLadder = useMemo(
    () =>
      active.length === 0
        ? ladder
        : ladder.filter(
            (r) => r.expiryType !== undefined && active.includes(r.expiryType),
          ),
    [ladder, active],
  );

  // Auto-select the first surviving rung when the current expiry is filtered out.
  useEffect(() => {
    if (expiry === "" || filteredLadder.length === 0) return;
    if (!filteredLadder.some((r) => r.expiry === expiry)) {
      setExpiry(filteredLadder[0].expiry);
    }
  }, [filteredLadder, expiry, setExpiry]);

  const toggleClass = (id: ExpiryClass) =>
    setClassFilter((prev) =>
      prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id],
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
          {filteredLadder.map((rung) => (
            <option key={rung.expiry} value={rung.expiry}>
              {rung.expiry} (T={rung.t.toFixed(2)}y)
            </option>
          ))}
        </select>
      </label>

      {/* Expiry-class bulk filter (only when the backend tags classes) */}
      {presentChips.length > 0 && (
        <div className="flex items-center gap-1" title="Filter the expiry ladder by listing class">
          <button className={chipClass(active.length === 0)} onClick={() => setClassFilter([])}>
            All
          </button>
          {presentChips.map((c) => (
            <button
              key={c.id}
              className={chipClass(active.includes(c.id))}
              title={c.id}
              onClick={() => toggleClass(c.id)}
            >
              {c.label}
            </button>
          ))}
        </div>
      )}

      {/* Fit-mode segmented control */}
      <div className="ml-auto flex items-center gap-2">
        <span className="text-xs text-slate-500">Fit to</span>
        <SegmentedControl options={FIT_MODES} value={fitMode} onChange={setFitMode} />
      </div>
    </div>
  );
}
