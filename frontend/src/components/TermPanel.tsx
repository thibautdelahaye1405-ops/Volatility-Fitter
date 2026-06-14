// Term-Structure sub-tab of the Parametric workspace (ROADMAP Phase 10).
//
// Embeds the ATM-vol / total-variance term structure that used to be a
// top-level workspace, now sitting alongside the Density sub-tab. The
// underlying is the Parametric session's ticker (useTerm shares it), so there
// is no ticker selector here — only the clock toggle, the editable event
// markers and the expiry ladder, laid out as the chart card's body.
//
// Live backend only (POST /term/{ticker}); offline shows a retry message.
import TermChart from "./TermChart";
import { useTerm } from "../state/useTerm";
import type { ClockMode } from "../state/useTerm";
import { formatPct } from "../lib/chartScale";

const CLOCK_MODES: { id: ClockMode; label: string }[] = [
  { id: "real", label: "Real time" },
  { id: "dilated", label: "Event-dilated" },
];

const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

const numInputClass =
  "w-14 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 " +
  "text-right font-mono text-xs text-slate-100 outline-none " +
  "hover:border-slate-600 focus:border-accent-500";

const textInputClass =
  "min-w-0 flex-1 rounded-md border border-slate-700 bg-surface-800 px-1.5 " +
  "py-1 text-xs text-slate-100 outline-none hover:border-slate-600 " +
  "focus:border-accent-500";

export default function TermPanel() {
  const {
    data,
    loading,
    refreshing,
    error,
    reload,
    events,
    addEvent,
    updateEvent,
    removeEvent,
    eventsEnabled,
    setEventsEnabled,
    axisClock,
    setAxisClock,
  } = useTerm();

  // Backend offline (and nothing loaded): centered retry message.
  if (error !== null && data === null) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm font-semibold text-slate-100">
          Term structure requires the live backend
        </p>
        <p className="max-w-sm truncate text-[10px] text-amber-400/80" title={error}>
          {error}
        </p>
        <button className={buttonClass} onClick={reload}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* Chart area */}
      <div className="flex min-w-0 flex-1 flex-col">
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
              dividends={data.dividends}
            />
          )}
        </div>
        <p className="mt-1 shrink-0 text-[10px] text-slate-600">
          ATM vol σ(T) · total variance w(T) = σ²·T · events add diffusion time
        </p>
      </div>

      {/* Controls column: clock + events + ladder */}
      <aside className="flex w-72 shrink-0 flex-col overflow-y-auto rounded-xl border border-slate-800 bg-surface-950/40 p-4">
        {/* Clock toggle */}
        <div className="mb-3">
          <span className="mb-1 block text-xs text-slate-500">Maturity clock</span>
          <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
            {CLOCK_MODES.map((mode) => (
              <button
                key={mode.id}
                onClick={() => setAxisClock(mode.id)}
                className={[
                  "flex-1 px-2 py-1 text-[11px] font-medium transition-colors",
                  mode.id === axisClock
                    ? "bg-accent-600/25 text-accent-400"
                    : "text-slate-400 hover:text-slate-200",
                ].join(" ")}
              >
                {mode.label}
              </button>
            ))}
          </div>
        </div>

        {/* Events editor */}
        <div className="mb-1 flex items-center">
          <h3 className="text-sm font-semibold text-slate-100">Events</h3>
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
          Each event adds its weight (years of diffusion time) at its position.
        </p>
        <div className={eventsEnabled ? "" : "opacity-40"}>
          <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-slate-600">
            <span className="w-14 text-right">t (y)</span>
            <span className="w-14 text-right">weight</span>
            <span className="flex-1">label</span>
            <span className="w-4" />
          </div>
          <div className="max-h-40 overflow-y-auto">
            {events.length === 0 ? (
              <p className="py-2 text-xs text-slate-500">
                No events — the dilated clock equals real time.
              </p>
            ) : (
              <div className="divide-y divide-slate-800">
                {events.map((ev) => (
                  <div key={ev.id} className="flex items-center gap-1.5 py-1.5">
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

        {/* Expiry ladder */}
        <div className="mt-4 flex min-h-0 flex-1 flex-col border-t border-slate-800 pt-3">
          <h3 className="mb-2 text-sm font-semibold text-slate-100">Expiry ladder</h3>
          {data !== null && data.calendarViolations > 0 && (
            <p className="mb-2 text-[10px] text-amber-400">
              {data.calendarViolations} calendar violation
              {data.calendarViolations > 1 ? "s" : ""}: variance decreases between
              expiries
            </p>
          )}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <table className="w-full text-right font-mono text-[10px]">
              <thead>
                <tr className="text-slate-600">
                  <th className="pb-1 text-left font-normal">expiry</th>
                  <th className="pb-1 font-normal">T</th>
                  <th className="pb-1 font-normal">ATM</th>
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
  );
}
