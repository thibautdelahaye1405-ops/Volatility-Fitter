// Spot move card (Parametric + Local Vol asides).
//
// What the ticker's spot FOLLOWS is the card's selector:
//   Market     the prevailing spot — streamed off the live book (~1 Hz while it
//              streams), else the last probe or the fetched chain's own — the
//              backend keeps the shift synced to it (the dial is dimmed);
//   Scenario   the dial: a hypothetical move the whole app, live tick stream
//              included, lives at (the market row is dimmed).
// Neither recalibrates: the backend transports the calibrated smile / term /
// LV grid under the Options dynamics regime (skew-stickiness ratio R). The
// dial moves in 0.1 % steps (± buttons; Shift = 1 %), Reset returns it to 0,
// Sync to market copies the market return into it. Real-time spot mode pins
// Market (the scheduler owns the shift).
// Recalibrate = the top-bar Calibrate for THIS ticker: the same scope (Param +
// LV / Param only / LV only — read live from the top bar's choice) and the
// same snapshot rule (a synchronous quotes + spot snapshot off the streaming
// book, else the last fetched chain), as the background job; the previous fit
// stays on screen (stale) until the new one lands.
// Sizes (lib/asideSizes, the column's shared focus): compact = one row naming
// the followed spot; standard = Follow, the spot rows, the dial, Recalibrate;
// expanded = everything (regime row, dial scale, Reset / Sync, the snapshot
// rule). Rendered outside the column (tests) the card is expanded.
import type { ReactNode } from "react";
import { RotateCcw } from "lucide-react";
import { AsideBody, AsideHeader } from "./AsideCard";
import SegmentedControl from "./SegmentedControl";
import type { AsideSize } from "../lib/asideSizes";
import { SCOPE_SHORT } from "../lib/calibScope";
import type { CalibScope } from "../lib/calibScope";
import { useCalibScope } from "../state/useCalibScope";
import type { SpotFollow, SpotNote, SpotState } from "../state/useSpot";
import type { CalibrationStatus } from "../state/workflowTypes";

/** Dial range and steps (percent). */
export const DIAL_MAX_PCT = 15;
export const DIAL_STEP_PCT = 0.1;
export const DIAL_COARSE_STEP_PCT = 1;

/** The bits of the calibration status the card narrates. */
export type SpotCalibStatus = Pick<CalibrationStatus, "running" | "current" | "phase" | "done" | "total">;

const FOLLOW_OPTIONS = [
  { id: "market", label: "Market spot" },
  { id: "scenario", label: "Scenario" },
] as const;

interface SpotPanelProps {
  /** Active proportional spot shift (0 = anchored). */
  spotReturn: number;
  /** Backend spot state (anchor / market / scenario spot, follow, regime). */
  spotState: SpotState | null;
  onSpotReturn: (r: number) => void;
  onFollow: (follow: SpotFollow) => void;
  /** Recalibrate this ticker with the given scope (the top bar's current one). */
  onCalibrate: (scope: CalibScope) => void;
  onProbeLive: () => void;
  /** The background calibration job (Recalibrate progress), null when unknown. */
  calib: SpotCalibStatus | null;
  /** Outcome line of the last Recalibrate / selector action. */
  note: SpotNote | null;
  disabled: boolean;
  disabledReason?: string;
  /** Card size in the column (default: expanded, the full card). */
  size?: AsideSize;
  /** Expand / fold the card (the column's shared focus). */
  onToggleSize?: () => void;
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

/** A spot-level row; `emphasis` lights the followed level and dims the other. */
function Row({ label, sub, value, emphasis, action }: {
  label: string; sub?: string; value: string; emphasis?: "on" | "off"; action?: ReactNode;
}) {
  return (
    <div
      className={["flex items-center justify-between gap-2 py-1", emphasis === "off" ? "opacity-45" : ""].join(" ")}
      data-emphasis={emphasis ?? "none"}
    >
      <span className={["min-w-0 text-[11px]", emphasis === "on" ? "font-semibold text-slate-200" : "text-slate-500"].join(" ")}>
        {label}
        {sub && <span className="ml-1 text-[10px] font-normal text-slate-600">{sub}</span>}
      </span>
      <span className="flex items-center gap-1.5">
        <span className={["font-mono text-[11px]", emphasis === "on" ? "font-semibold text-accent-400" : "text-slate-300"].join(" ")}>
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
const smallButton =
  "flex items-center gap-1 rounded border border-slate-700 bg-surface-800 px-2 py-0.5 text-[10px] font-medium " +
  "text-slate-300 transition enabled:hover:border-slate-500 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";
const linkButton = "text-[10px] font-medium text-slate-500 transition enabled:hover:text-accent-300 disabled:opacity-40";

export default function SpotPanel({
  spotReturn, spotState, onSpotReturn, onFollow, onCalibrate, onProbeLive,
  calib, note, disabled, disabledReason, size = "L", onToggleSize,
}: SpotPanelProps) {
  const full = size === "L";
  const scope = useCalibScope(); // the top bar's current Calibrate scope
  const pct = snapDialPct(spotReturn * 100);
  const moved = Math.abs(pct) > 1e-9;
  const s = spotState;
  const follow: SpotFollow = s?.follow ?? "market";
  const scenario = follow === "scenario";
  const dialLocked = disabled || !scenario;
  const live = s?.liveSpot ?? null;
  const liveRet = s?.liveReturn ?? null;
  // Sync is worth offering when the scenario sits away from the market (>5 bp).
  const canSync = scenario && !disabled && liveRet !== null && Math.abs(liveRet - spotReturn) > 5e-4;
  const running = calib?.running ?? false;
  const ticker = s?.ticker ?? "";
  const nodes = s ? `${s.litNodes} node${s.litNodes === 1 ? "" : "s"}` : "";
  const what = scope === "lv" ? "LV surface" : scope === "parametric" ? nodes : `${nodes}${s?.lvEnabled ? " + LV" : ""}`;

  const step = (dir: 1 | -1, coarse: boolean) => {
    const stepSize = coarse ? DIAL_COARSE_STEP_PCT : DIAL_STEP_PCT;
    onSpotReturn(snapDialPct(pct + dir * stepSize) / 100);
  };

  const marketSub = !s || live === null
    ? undefined
    : s.liveSource === "stream"
      ? `${s.sourceLabel} · streaming`
      : `${s.liveSource === "probe" ? "probe" : "chain"}${s.liveAt ? ` ${clockOf(s.liveAt)}` : ""}`;

  // Compact row: the followed level (or the running job).
  const followedValue = scenario
    ? s ? `${(s.anchorSpot * (1 + spotReturn)).toFixed(2)} ${signedPct(spotReturn, 1)}` : "—"
    : live !== null && liveRet !== null ? `${live.toFixed(2)} ${signedPct(liveRet)}` : "—";
  const summary = running && calib
    ? `Calibrating ${calib.done}/${calib.total}`
    : `${scenario ? "Scenario" : "Market"} ${followedValue}`;

  const streamingBadge = s?.streaming && (
    <span
      className="flex items-center gap-1 text-[10px] font-semibold tracking-wider text-emerald-300"
      title={`${s.sourceLabel} live book streaming — spot and quotes flow continuously`}
    >
      {/* The book streams: spot and quotes flow continuously (a market-
          following ticker tracks the book; a scenario keeps its dial). */}
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
      {size !== "S" && "STREAMING"}
    </span>
  );

  return (
    <section className={["flex min-h-0 flex-col", disabled ? "opacity-40" : ""].join(" ")} title={disabled ? disabledReason : undefined}>
      <AsideHeader
        title="Spot move"
        size={size}
        onToggle={onToggleSize}
        badge={size === "S" ? streamingBadge : undefined}
        right={streamingBadge}
        summary={summary}
        expandTip="regime, dial scale, Reset / Sync, the snapshot rule"
      />
      {size !== "S" && (
        <AsideBody>
          {full && (
            <p className="mb-2 text-[11px] text-slate-500">
              Transports the smile · term · LV grid — no recalibration
            </p>
          )}

          {/* What the spot follows */}
          <div
            className="mb-2 flex items-center justify-between gap-2"
            title={s?.followForced ? "The market spot is pinned by the backend" : "Follow the prevailing market spot, or the scenario dial"}
          >
            <span className="text-[11px] text-slate-400">Follow</span>
            <div className={s?.followForced || disabled ? "pointer-events-none opacity-50" : ""}>
              <SegmentedControl options={FOLLOW_OPTIONS} value={follow} onChange={onFollow} size="xs" />
            </div>
          </div>

          {/* Spot levels: calibrated -> market -> scenario (the followed one lit) */}
          <div className="mb-2 divide-y divide-slate-800/80 rounded-md border border-slate-800 bg-surface-800/60 px-2">
            <Row label="Calibrated" value={s ? s.anchorSpot.toFixed(2) : "—"} />
            <Row
              label="Market"
              sub={marketSub}
              value={live !== null && liveRet !== null ? `${live.toFixed(2)}  ${signedPct(liveRet)}` : "—"}
              emphasis={scenario ? "off" : "on"}
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
              sub={scenario && moved ? "dial" : undefined}
              value={s ? `${(s.anchorSpot * (1 + spotReturn)).toFixed(2)}  ${signedPct(spotReturn, 1)}` : "—"}
              emphasis={scenario ? "on" : "off"}
            />
            {full && <Row label="Regime · R" value={s ? `${s.regime} · ${s.regimeSsr.toFixed(1)}` : "—"} />}
          </div>

          {/* The dial (lit in scenario mode, dimmed while following the market) */}
          <div className={scenario ? "" : "opacity-45"} data-testid="spot-dial" data-active={scenario}>
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
            {full && (
              <div className="flex justify-between px-7 font-mono text-[10px] text-slate-600">
                <span>−{DIAL_MAX_PCT}%</span>
                <span>0</span>
                <span>+{DIAL_MAX_PCT}%</span>
              </div>
            )}
            {full && (
            <div className="mt-1.5 flex items-center justify-between gap-2">
              <button
                type="button"
                className={smallButton}
                disabled={dialLocked || !moved}
                onClick={() => onSpotReturn(0)}
                title="Reset the scenario to the calibrated spot (0.0 %)"
              >
                <RotateCcw size={11} strokeWidth={1.75} /> Reset to 0.0%
              </button>
              <button
                type="button"
                className={linkButton}
                disabled={!canSync}
                onClick={() => liveRet !== null && onSpotReturn(snapDialPct(liveRet * 100) / 100)}
                title="Copy the market return into the dial"
              >
                Sync to market
              </button>
            </div>
            )}
          </div>

          {/* Recalibrate THIS ticker — the top-bar Calibrate, same scope + snapshot rule */}
          <button
            type="button"
            onClick={() => onCalibrate(scope)}
            disabled={disabled || running}
            className="mt-3 w-full rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1.5 text-xs font-semibold text-accent-300 transition enabled:hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
            title={`The top-bar Calibrate for ${ticker || "this ticker"} only — ${SCOPE_SHORT[scope]} (change the scope in the top bar). Snapshot: streamed quotes + spot when a book streams, else the last fetched chain. Background job; the current fit stays until the new one lands.`}
          >
            {running && calib
              ? `Calibrating${calib.current ? ` · ${calib.current}` : ""}${calib.phase ? ` · ${calib.phase}` : ""} ${calib.done}/${calib.total}`
              : `Recalibrate${ticker ? ` ${ticker}` : ""} (${SCOPE_SHORT[scope]})`}
          </button>
          {full && (
            <p className="mt-1 text-[10px] text-slate-500">
              {running
                ? "Background job running — the previous fit stays until it lands."
                : `Calibrate, this ticker only · ${s?.streaming ? "streamed quotes + spot snapshot" : "last fetched quotes + spot"} · ${what || "the lit nodes"}`}
            </p>
          )}
          {note && (
            <p className={["mt-1 text-[10px]", note.ok ? "text-emerald-300" : "text-amber-300"].join(" ")} role="status">
              {note.text}
            </p>
          )}
        </AsideBody>
      )}
    </section>
  );
}
