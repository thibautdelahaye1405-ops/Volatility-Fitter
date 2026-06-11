// Term-Structure workspace: ATM vol and total variance across the expiry
// ladder of the session's underlying, on a real or event-dilated maturity
// axis. Event markers (time, weight, label) are editable and refit live;
// the dense curve interpolates variance linearly in the dilated clock.
//
// This view requires the live backend (POST /term/{ticker}) — there is
// deliberately no mock fallback, matching the Graph workspace.
import TermChart from "../components/TermChart";
import { useTerm } from "../state/useTerm";
import type { ClockMode } from "../state/useTerm";
import { formatPct } from "../lib/chartScale";

const CLOCK_MODES: { id: ClockMode; label: string }[] = [
  { id: "real", label: "Real time" },
  { id: "dilated", label: "Event-dilated" },
];

/** Shared styling for the header selectors (matches SmileViewer). */
const selectClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-200 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

/** Small bordered button, matching the smile toolbar style. */
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** Numeric event input (time / weight, in years). */
const numInputClass =
  "w-14 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 " +
  "text-right font-mono text-xs text-slate-100 outline-none " +
  "hover:border-slate-600 focus:border-accent-500";

/** Free-text event label input. */
const textInputClass =
  "min-w-0 flex-1 rounded-md border border-slate-700 bg-surface-800 px-1.5 " +
  "py-1 text-xs text-slate-100 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function TermStructureViewer() {
  const {
    data,
    loading,
    refreshing,
    error,
    reload,
    ticker,
    setTicker,
    tickers,
    events,
    addEvent,
    updateEvent,
    removeEvent,
    eventsEnabled,
    setEventsEnabled,
    axisClock,
    setAxisClock,
  } = useTerm();

  // Backend offline (and nothing loaded): centered empty-state card.
  if (error !== null && data === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Term structure requires the live backend
          </h2>
          <p className="mb-1 text-xs text-slate-500">
            Start the FastAPI server on :8000 and retry.
          </p>
          <p className="mb-5 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </p>
          <button className={buttonClass} onClick={reload}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  // Header fit summary: worst per-expiry IV error across the ladder.
  const maxErrBp = data
    ? data.points.reduce((m, p) => Math.max(m, p.maxIvErrorBp), 0)
    : 0;

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: underlying selector + clock toggle + fit info */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-slate-500">
          Underlying
          <select
            className={selectClass}
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            disabled={tickers.length === 0}
          >
            {tickers.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>

        {/* Clock segmented control */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">Clock</span>
          <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
            {CLOCK_MODES.map((mode) => {
              const active = mode.id === axisClock;
              return (
                <button
                  key={mode.id}
                  onClick={() => setAxisClock(mode.id)}
                  className={[
                    "px-3 py-1.5 text-xs font-medium transition-colors",
                    active
                      ? "bg-accent-600/25 text-accent-400"
                      : "text-slate-400 hover:text-slate-200",
                  ].join(" ")}
                >
                  {mode.label}
                </button>
              );
            })}
          </div>
        </div>

        {data && (
          <span className="ml-auto font-mono text-[11px] text-slate-500">
            fit to mid · {data.points.length} expiries · max err{" "}
            {maxErrBp.toFixed(0)} bp
          </span>
        )}
      </div>

      {/* Body: chart card + events / ladder panel */}
      <div className="flex min-h-0 flex-1 gap-4">
        {/* Chart card */}
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">
              {ticker !== "" ? `${ticker} term structure` : "Term structure"}
            </h2>
            <span className="font-mono text-[11px] text-slate-500">
              ATM vol σ(T) · total variance w(T) = σ²·T
            </span>
            {/* Surface refit errors without unmounting the chart */}
            {error !== null && (
              <span className="ml-auto truncate text-[10px] text-amber-400/80" title={error}>
                {error}
              </span>
            )}
          </div>
          <div
            className={[
              "min-h-0 flex-1 transition-opacity duration-200",
              refreshing ? "opacity-60" : "opacity-100",
            ].join(" ")}
          >
            {loading || data === null ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-500">
                Fitting term structure… (first load can take a second)
              </div>
            ) : (
              <TermChart
                points={data.points}
                curve={data.curve}
                events={events}
                eventsEnabled={eventsEnabled}
                axisClock={axisClock}
              />
            )}
          </div>
          {/* Interaction hint */}
          <p className="mt-1 shrink-0 text-[10px] text-slate-600">
            Events add diffusion time · variance interpolates linearly in the
            dilated clock
          </p>
        </div>

        {/* Events + per-expiry panel */}
        <aside className="flex w-80 shrink-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
          <div className="mb-1 flex items-center">
            <h3 className="text-sm font-semibold text-slate-100">Events</h3>
            {/* Master toggle: keep the rows, just stop sending them */}
            <label className="ml-auto flex cursor-pointer items-center gap-1.5 text-[11px] text-slate-400">
              <input
                type="checkbox"
                checked={eventsEnabled}
                onChange={(e) => setEventsEnabled(e.target.checked)}
                className="accent-accent-500"
              />
              Enabled
            </label>
          </div>
          <p className="mb-2 text-[11px] text-slate-500">
            Each event adds its weight (years of diffusion time) at its
            real-time position.
          </p>

          {/* Column captions + event rows (dimmed when disabled) */}
          <div className={eventsEnabled ? "" : "opacity-40"}>
            <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-slate-600">
              <span className="w-14 text-right">t (y)</span>
              <span className="w-14 text-right">weight</span>
              <span className="flex-1">label</span>
              <span className="w-4" />
            </div>
            <div className="max-h-44 overflow-y-auto">
              {events.length === 0 ? (
                <p className="py-2 text-xs text-slate-500">
                  No events — the dilated clock equals real time.
                </p>
              ) : (
                <div className="divide-y divide-slate-800">
                  {events.map((ev) => (
                    <div key={ev.id} className="flex items-center gap-1.5 py-1.5">
                      {/* Uncontrolled (defaultValue) so partial entries like
                          "0." don't snap back while typing. */}
                      <input
                        type="number"
                        step={0.05}
                        min={0}
                        defaultValue={ev.time}
                        title="Event time (years)"
                        onChange={(e) => {
                          const v = e.target.valueAsNumber;
                          if (Number.isFinite(v)) updateEvent(ev.id, { time: v });
                        }}
                        className={numInputClass}
                      />
                      <input
                        type="number"
                        step={0.01}
                        min={0}
                        defaultValue={ev.weight}
                        title="Added diffusion time (years)"
                        onChange={(e) => {
                          const v = e.target.valueAsNumber;
                          if (Number.isFinite(v)) updateEvent(ev.id, { weight: v });
                        }}
                        className={numInputClass}
                      />
                      <input
                        type="text"
                        defaultValue={ev.label}
                        title="Event label"
                        onChange={(e) => updateEvent(ev.id, { label: e.target.value })}
                        className={textInputClass}
                      />
                      <button
                        onClick={() => removeEvent(ev.id)}
                        title="Remove event"
                        className="w-4 px-0 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
          <button onClick={addEvent} className={`${buttonClass} mt-2 shrink-0`}>
            + Add event
          </button>

          {/* Per-expiry handles table */}
          <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-slate-800 pt-3">
            <h3 className="mb-2 text-sm font-semibold text-slate-100">
              Expiry ladder
            </h3>
            {data !== null && data.calendarViolations > 0 && (
              <p className="mb-2 text-[10px] text-amber-400">
                {data.calendarViolations} calendar violation
                {data.calendarViolations > 1 ? "s" : ""}: total variance
                decreases between expiries
              </p>
            )}
            <div className="min-h-0 flex-1 overflow-y-auto">
              <table className="w-full text-right font-mono text-[10px]">
                <thead>
                  <tr className="text-slate-600">
                    <th className="pb-1 text-left font-normal">expiry</th>
                    <th className="pb-1 font-normal">T</th>
                    <th className="pb-1 font-normal">ATM</th>
                    <th className="pb-1 font-normal">w0</th>
                    <th className="pb-1 font-normal">VS</th>
                    <th className="pb-1 font-normal">bp</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300">
                  {(data?.points ?? []).map((p) => (
                    <tr key={p.expiry} className="border-t border-slate-800/60">
                      <td className="py-1 text-left text-slate-400">{p.expiry}</td>
                      <td>{p.t.toFixed(2)}</td>
                      <td>{formatPct(p.atmVol)}</td>
                      <td>{p.w0.toFixed(4)}</td>
                      <td>{formatPct(p.varSwapVol)}</td>
                      <td>{p.maxIvErrorBp.toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
