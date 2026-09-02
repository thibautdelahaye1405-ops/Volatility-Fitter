// Spot move card (Parametric + Local Vol asides).
//
// Three spot levels, one dial, one re-anchor:
//   Calibrated   the spot the ticker's fits were calibrated at (the anchor);
//   Market       the latest known provider spot — streamed off the live book
//                (~1 Hz while it streams), else the last probe or the fetched
//                chain's own spot — with its return vs the anchor;
//   Scenario     anchor × (1 + dial): the spot EVERY lens lives at right now.
// The dial is a hypothetical move (no recalibration): the backend transports
// the calibrated smile / term / LV grid under the Options dynamics regime
// (skew-stickiness ratio R) and the node's live tick stream follows it too.
// ± buttons fine-tune by 0.1 % (Shift: 1 %); Sync to market jumps the dial to
// the live return. In real-time spot mode the scheduler drives the dial.
// Re-anchor clears the dial, refetches the ticker's chain and calibrates ITS
// lit nodes (+ LV surface) as the background job; the previous fit stays on
// screen (stale) until the new one lands.
import type { ReactNode } from "react";
import type { SpotNote, SpotState } from "../state/useSpot";
import type { CalibrationStatus } from "../state/workflowTypes";

/** Dial range and steps (percent). */
export const DIAL_MAX_PCT = 15;
export const DIAL_STEP_PCT = 0.1;
export const DIAL_COARSE_STEP_PCT = 1;

/** The bits of the calibration status the card narrates. */
export type SpotCalibStatus = Pick<CalibrationStatus, "running" | "current" | "phase" | "done" | "total">;

interface SpotPanelProps {
  /** Active proportional spot shift (0 = anchored). */
  spotReturn: number;
  /** Backend spot state (anchor / market / scenario spot, regime, SSR). */
  spotState: SpotState | null;
  /** Options spot mode: "static" (manual dial) or "realtime" (scheduler-driven). */
  spotMode: "static" | "realtime";
  onSpotReturn: (r: number) => void;
  onCalibrate: () => void;
  onSyncLive: () => void;
  onProbeLive: () => void;
  /** The background calibration job (Re-anchor progress), null when unknown. */
  calib: SpotCalibStatus | null;
  /** Outcome line of the last Re-anchor / Sync. */
  note: SpotNote | null;
  disabled: boolean;
  disabledReason?: string;
}

const signedPct = (r: number, digits = 2): string => `${r > 0 ? "+" : ""}${(r * 100).toFixed(digits)}%`;

/** Local HH:MM of an ISO stamp (naive stamps are UTC, the backend convention). */
export function clockOf(iso: string | null): string {
  if (!iso) return "";
  const utc = /(Z|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
  const d = new Date(utc);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** Snap a dial value to the fine step and clamp to the range (percent units). */
export function snapDialPct(pct: number): number {
  const snapped = Math.round(pct / DIAL_STEP_PCT) * DIAL_STEP_PCT;
  return Math.max(-DIAL_MAX_PCT, Math.min(DIAL_MAX_PCT, Math.round(snapped * 1000) / 1000));
}

function Row({ label, sub, value, accent, action }: {
  label: string; sub?: string; value: string; accent?: boolean; action?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-1">
      <span className="min-w-0 text-[11px] text-slate-500">
        {label}
        {sub && <span className="ml-1 text-[10px] text-slate-600">{sub}</span>}
      </span>
      <span className="flex items-center gap-1.5">
        <span className={["font-mono text-[11px]", accent ? "font-semibold text-accent-400" : "text-slate-300"].join(" ")}>
          {value}
        </span>
        {action}
      </span>
    </div>
  );
}

const stepButton =
  "flex h-6 w-6 shrink-0 items-center justify-center rounded border border-slate-700 bg-surface-800 " +
  "font-mono text-xs text-slate-300 transition enabled:hover:border-slate-500 enabled:hover:text-slate-100 " +
  "disabled:cursor-not-allowed disabled:opacity-40";
const linkButton = "text-[10px] font-medium text-slate-500 transition enabled:hover:text-accent-300 disabled:opacity-40";

export default function SpotPanel({
  spotReturn, spotState, spotMode, onSpotReturn, onCalibrate, onSyncLive, onProbeLive,
  calib, note, disabled, disabledReason,
}: SpotPanelProps) {
  const pct = snapDialPct(spotReturn * 100);
  const realtime = spotMode === "realtime";
  const moved = Math.abs(pct) > 1e-9;
  const dialLocked = disabled || realtime;
  const s = spotState;
  const live = s?.liveSpot ?? null;
  const liveRet = s?.liveReturn ?? null;
  // Sync is worth offering when the market sits away from the scenario (>5 bp).
  const canSync = !dialLocked && liveRet !== null && Math.abs(liveRet - spotReturn) > 5e-4;
  const running = calib?.running ?? false;
  const ticker = s?.ticker ?? "";
  const scope = s ? `${s.litNodes} node${s.litNodes === 1 ? "" : "s"}${s.lvEnabled ? " + LV" : ""}` : "";

  const step = (dir: 1 | -1, coarse: boolean) => {
    const size = coarse ? DIAL_COARSE_STEP_PCT : DIAL_STEP_PCT;
    onSpotReturn(snapDialPct(pct + dir * size) / 100);
  };

  const marketSub = !s || live === null
    ? undefined
    : s.liveSource === "stream"
      ? `${s.sourceLabel} · streaming`
      : `${s.liveSource === "probe" ? "probe" : "chain"}${s.liveAt ? ` ${clockOf(s.liveAt)}` : ""}`;

  return (
    <section className={disabled ? "opacity-40" : ""} title={disabled ? disabledReason : undefined}>
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Spot move</h3>
        <span className="flex items-center gap-1.5">
          {s?.streaming && (
            <span className="flex items-center gap-1 text-[10px] font-semibold tracking-wider text-emerald-300" title={`${s.sourceLabel} live book streaming`}>
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
              STREAM
            </span>
          )}
          {realtime && (
            <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-emerald-300" title="Real-time spot mode: the scheduler drives the dial (Options ▸ spotMode)">
              LIVE
            </span>
          )}
        </span>
      </div>
      <p className="mb-2 text-[11px] text-slate-500">
        Transports the smile · term · LV grid — no recalibration
      </p>

      {/* Spot levels: calibrated -> market -> scenario */}
      <div className="mb-2 divide-y divide-slate-800/80 rounded-md border border-slate-800 bg-surface-800/60 px-2">
        <Row label="Calibrated" value={s ? s.anchorSpot.toFixed(2) : "—"} />
        <Row
          label="Market"
          sub={marketSub}
          value={live !== null && liveRet !== null ? `${live.toFixed(2)}  ${signedPct(liveRet)}` : "—"}
          action={
            !s?.streaming ? (
              <button
                type="button"
                onClick={onProbeLive}
                disabled={disabled}
                className={linkButton}
                title="Probe the provider spot now (one request)"
                aria-label="Probe market spot"
              >
                ↻
              </button>
            ) : undefined
          }
        />
        <Row
          label="Scenario"
          sub={moved ? (s?.shiftSource === "live" ? "live poll" : "dial") : undefined}
          value={s ? `${(s.anchorSpot * (1 + spotReturn)).toFixed(2)}  ${signedPct(spotReturn, 1)}` : "—"}
          accent={moved}
        />
        <Row
          label="Regime · R"
          value={s ? `${s.regime} · ${s.regimeSsr.toFixed(1)}` : "—"}
        />
      </div>

      {/* The dial: ± fine-tune (0.1 %; Shift = 1 %) around the slider */}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-400">Spot return</span>
        <span className={["font-mono font-medium", moved ? "text-accent-400" : "text-slate-500"].join(" ")}>
          {signedPct(spotReturn, 1)}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className={stepButton}
          disabled={dialLocked || pct <= -DIAL_MAX_PCT}
          onClick={(e) => step(-1, e.shiftKey)}
          title="−0.1 % (Shift: −1 %)"
          aria-label="Spot down 0.1 percent"
        >
          −
        </button>
        <input
          type="range"
          min={-DIAL_MAX_PCT}
          max={DIAL_MAX_PCT}
          step={DIAL_STEP_PCT}
          value={pct}
          disabled={dialLocked}
          onChange={(e) => onSpotReturn(snapDialPct(Number(e.target.value)) / 100)}
          className="w-full min-w-0 cursor-pointer disabled:cursor-not-allowed"
          style={{ accentColor: "var(--color-accent-500)" }}
          aria-label="Spot return"
        />
        <button
          type="button"
          className={stepButton}
          disabled={dialLocked || pct >= DIAL_MAX_PCT}
          onClick={(e) => step(1, e.shiftKey)}
          title="+0.1 % (Shift: +1 %)"
          aria-label="Spot up 0.1 percent"
        >
          +
        </button>
      </div>
      <div className="flex justify-between px-7 font-mono text-[10px] text-slate-600">
        <span>−{DIAL_MAX_PCT}%</span>
        <span>0</span>
        <span>+{DIAL_MAX_PCT}%</span>
      </div>
      <div className="mt-1 flex items-center justify-end gap-3">
        {realtime ? (
          <span className="text-[10px] text-slate-500">Dial driven by the real-time spot poll</span>
        ) : (
          <>
            <button type="button" className={linkButton} disabled={dialLocked || !moved} onClick={() => onSpotReturn(0)}>
              Reset
            </button>
            <button
              type="button"
              className={linkButton}
              disabled={!canSync}
              onClick={onSyncLive}
              title="Move the dial to the market spot (the live tick stream keeps its own spot)"
            >
              Sync to market
            </button>
          </>
        )}
      </div>

      {/* Re-anchor: refetch + recalibrate THIS ticker's lit nodes at the market spot */}
      <button
        type="button"
        onClick={onCalibrate}
        disabled={disabled || running}
        className="mt-3 w-full rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1.5 text-xs font-semibold text-accent-300 transition enabled:hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        title={`Clear the spot move, refetch ${ticker || "the ticker"}'s quotes and recalibrate its lit nodes at the market spot (background job; the current fit stays until the new one lands)`}
      >
        {running && calib
          ? `Calibrating${calib.current ? ` · ${calib.current}` : ""}${calib.phase ? ` · ${calib.phase}` : ""} ${calib.done}/${calib.total}`
          : `Re-anchor${ticker ? ` ${ticker}` : ""}`}
      </button>
      <p className="mt-1 text-[10px] text-slate-500">
        {running ? "Background job running — the previous fit stays until it lands." : `Refetch quotes · calibrate ${scope || "the lit nodes"} at the market spot`}
      </p>
      {note && (
        <p className={["mt-1 text-[10px]", note.ok ? "text-emerald-300" : "text-amber-300"].join(" ")} role="status">
          {note.text}
        </p>
      )}
    </section>
  );
}
