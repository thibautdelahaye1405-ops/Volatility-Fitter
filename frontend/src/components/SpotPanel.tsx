// Fast spot-move panel for the Parametric aside.
//
// The slider drives a LIVE spot move (no recalibration): dragging it PUTs a
// per-ticker spot shift that the backend transports the calibrated smile / term
// / LV-grid by (volfit.dynamics.transport, per the note
// Docs/spot_move_vol_surface_note_updated.tex). The whole surface refreshes
// across every workspace. "Calibrate" re-anchors: it clears the shift and
// recalibrates at the live spot. The active vol-spot dynamics regime (set in
// Options) determines the skew-stickiness ratio R used by the transport; in
// real-time spot mode the live provider spot drives the slider automatically.
import type { SpotState } from "../state/useSpot";

interface SpotPanelProps {
  /** Active proportional spot shift (0 = anchored). */
  spotReturn: number;
  /** Backend spot state (anchor / shifted spot, regime, SSR). */
  spotState: SpotState | null;
  /** Options spot mode: "static" (manual) or "realtime" (polled live). */
  spotMode: "static" | "realtime";
  onSpotReturn: (r: number) => void;
  onCalibrate: () => void;
  disabled: boolean;
  disabledReason?: string;
}

export default function SpotPanel({
  spotReturn,
  spotState,
  spotMode,
  onSpotReturn,
  onCalibrate,
  disabled,
  disabledReason,
}: SpotPanelProps) {
  // Slider works in whole/half percent; snap so 0 compares exactly.
  const pct = Math.round(spotReturn * 1000) / 10;
  const realtime = spotMode === "realtime";
  const moved = Math.abs(pct) > 1e-9;

  return (
    <section
      className={disabled ? "opacity-40" : ""}
      title={disabled ? disabledReason : undefined}
    >
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-100">Spot move</h3>
        {realtime && (
          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold tracking-wider text-emerald-300">
            LIVE
          </span>
        )}
      </div>
      <p className="mb-3 text-[11px] text-slate-500">
        Transports the smile · term · LV grid — no recalibration
      </p>

      {/* Active dynamics regime — read-only; change it in the Options tab. */}
      <div className="mb-3 flex items-center justify-between rounded-md border border-slate-800 bg-surface-800/60 px-2 py-1">
        <span className="text-[11px] text-slate-500">Regime · R</span>
        <span
          className="font-mono text-[11px] text-slate-300"
          title="Skew-stickiness ratio — set the regime in the Options workspace"
        >
          {spotState ? `${spotState.regime} · ${spotState.regimeSsr.toFixed(1)}` : "—"}
        </span>
      </div>

      {/* Spot-return slider with a live % readout (accent when moved) */}
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-slate-400">Spot return</span>
        <span
          className={[
            "font-mono font-medium",
            moved ? "text-accent-400" : "text-slate-500",
          ].join(" ")}
        >
          {pct > 0 ? "+" : ""}
          {pct.toFixed(1)}%
        </span>
      </div>
      <input
        type="range"
        min={-15}
        max={15}
        step={0.5}
        value={pct}
        disabled={disabled || realtime}
        onChange={(e) => onSpotReturn(Number(e.target.value) / 100)}
        className="w-full cursor-pointer disabled:cursor-not-allowed"
        style={{ accentColor: "var(--color-accent-500)" }}
      />
      <div className="flex justify-between font-mono text-[10px] text-slate-600">
        <span>-15%</span>
        <span>0</span>
        <span>+15%</span>
      </div>

      {/* Spot level readout: anchor -> shifted */}
      {spotState && (
        <p className="mt-2 font-mono text-[11px] text-slate-400">
          Spot {spotState.anchorSpot.toFixed(2)}
          {moved && (
            <>
              {" "}
              →{" "}
              <span className="text-accent-400">{spotState.shiftedSpot.toFixed(2)}</span>
            </>
          )}
        </p>
      )}

      {/* Calibrate: re-anchor at the live spot (full recalibration) */}
      <button
        type="button"
        onClick={onCalibrate}
        disabled={disabled}
        className="mt-3 w-full rounded-md border border-accent-500/40 bg-accent-500/10 px-2 py-1.5 text-xs font-semibold text-accent-300 transition hover:bg-accent-500/20 disabled:cursor-not-allowed disabled:opacity-50"
        title="Clear the spot move and recalibrate at the live spot"
      >
        Calibrate (re-anchor)
      </button>
    </section>
  );
}
