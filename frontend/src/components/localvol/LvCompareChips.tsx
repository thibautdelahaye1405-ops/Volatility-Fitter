// Chip row of the Local Vol Compare tab (LV Dupire-twin arc, D3), on the
// Parametric CompareChips grammar: the t-interpolation group (Smooth ·
// Buckets — how the parametric total-variance surface is carried between
// expiries before it is differentiated), the tail-target group (v1: the
// displayed model's own wings, lit and pinned; the rider targets show muted
// with their reason), the display-mode switch (Sheets · Difference · Smiles)
// and, right-aligned, the pooled score strip: the converged-operator RMS of
// the twin and of the affine sheet, the parametric source's RMS, the round
// trip, the repair summary and a STALE badge when the displayed LV fit is
// frozen behind drifted inputs. Pure presentation — state is the viewer's.
import SegmentedControl from "../SegmentedControl";
import { badgeClass } from "../../lib/ui";
import {
  LV_COMPARE_MODES, LV_TAIL_OPTIONS, LV_T_INTERP_OPTIONS, formatBp, repairDetail, repairSummary,
} from "../../lib/lvCompare";
import type { LvCompareMode, LvTailTarget } from "../../lib/lvCompare";
import type { LvCompareResponse, LvTInterp } from "../../state/useLvCompare";

export interface LvCompareChipsProps {
  tInterp: LvTInterp;
  onTInterpChange: (v: LvTInterp) => void;
  /** The tail target (2026-09-10: Model wings · Quoted range · Affine wings
   *  are live; Match LQD stays a muted rider). */
  tails: LvTailTarget;
  onTailsChange: (v: LvTailTarget) => void;
  mode: LvCompareMode;
  onModeChange: (m: LvCompareMode) => void;
  /** The last payload (score strip); null before the first lands. */
  data: LvCompareResponse | null;
  /** A HARD build in flight (spinner on the lit interpolation chip). A silent
   *  refresh never spins — on a live feed that spinner ran on every tick. */
  loading: boolean;
}

// The Parametric CompareChips palette, verbatim: a lit model-style chip is
// slate on the surface ground, a lit tail chip teal — both proven readable
// on the dark surface (the first cut's orange tint was not).
const CHIP_BASE = "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium transition-colors";
const CHIP_ON = "border-slate-600 bg-surface-800 text-slate-100";
const CHIP_TAIL_ON = "border-teal-500/50 bg-teal-500/10 text-teal-100";
const CHIP_OFF = "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-200";
const CHIP_MUTED = "border-slate-800/70 text-slate-600 opacity-60 cursor-default";
const GROUP_LABEL = "text-[9px] font-semibold uppercase tracking-wider text-slate-600";
const SPINNER = "h-2.5 w-2.5 animate-spin rounded-full border border-slate-500 border-t-transparent";
const DIVIDER = <span className="mx-0.5 h-3 w-px bg-slate-800" aria-hidden />;

export default function LvCompareChips({
  tInterp, onTInterpChange, tails, onTailsChange, mode, onModeChange, data, loading,
}: LvCompareChipsProps) {
  const twin = data?.twinScore;
  const affine = data?.affineScore ?? null;
  const param = data?.parametricScore;
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
      <span className={GROUP_LABEL} title="How the parametric total-variance surface is carried between listed expiries before it is differentiated">
        time
      </span>
      {LV_T_INTERP_OPTIONS.map((o) => {
        const on = o.id === tInterp;
        return (
          <button
            key={o.id}
            aria-pressed={on}
            onClick={() => onTInterpChange(o.id)}
            title={o.title}
            className={[CHIP_BASE, on ? CHIP_ON : CHIP_OFF].join(" ")}
          >
            {o.label}
            {on && loading && <span className={SPINNER} />}
          </button>
        );
      })}
      {DIVIDER}
      <span className={GROUP_LABEL} title="What the parametric surface is beyond the quoted range before it is differentiated">
        tails
      </span>
      {LV_TAIL_OPTIONS.map((o) => {
        const on = o.available && o.id === tails;
        return (
          <button
            key={o.id}
            aria-pressed={on}
            disabled={!o.available}
            onClick={() => o.available && onTailsChange(o.id)}
            title={o.title}
            className={[CHIP_BASE, !o.available ? CHIP_MUTED : on ? CHIP_TAIL_ON : CHIP_OFF].join(" ")}
          >
            {o.label}
            {!o.available && <span className="text-[9px] uppercase text-slate-600">rider</span>}
            {on && loading && <span className={SPINNER} />}
          </button>
        );
      })}
      {DIVIDER}
      <SegmentedControl options={LV_COMPARE_MODES} value={mode} onChange={onModeChange} size="xs" />

      {data && twin && param && (
        <span className="ml-auto flex items-center gap-3 font-mono text-[11px] text-slate-500">
          {data.affineStale && (
            <span title="Inputs changed since the last LV calibration — the affine sheet is frozen; press Calibrate" className={badgeClass("amber")}>
              STALE
            </span>
          )}
          {(data.spotShift ?? 0) !== 0 && (
            <span
              title={`Spot moved ${((data.spotShift ?? 0) * 100).toFixed(2)}% since the calibration — the comparison is built at the calibration spot (the twin is not transported)`}
              className={badgeClass("amber")}
            >
              ANCHOR
            </span>
          )}
          <span title="RMS vs the fit target (bp): the Dupire twin on its display operator · the affine sheet on the converged operator · the parametric source's closed form">
            twin {formatBp(twin.rmsBp)}
            {affine ? ` · affine conv ${formatBp(affine.convergedBp)}` : ""}
            {` · param ${formatBp(param.rmsBp)} bp`}
          </span>
          <span title="Round trip: the smooth twin repriced back against its own parametric source at the quoted strikes — rms · max, then the operator's floor (a flat surface's error on the same operator; no round trip reads below it) and the nodal sheet's own round trip (what the coarse lattice loses)">
            round trip {formatBp(data.roundTripBp, 1)} · {formatBp(data.roundTripMaxBp, 1)} bp
            {data.operatorBp != null ? ` · floor ${formatBp(data.operatorBp, 1)}` : ""}
            {data.sheetRoundTripBp != null ? ` · sheet ${formatBp(data.sheetRoundTripBp)}` : ""}
          </span>
          <span
            title={`${repairDetail(data.counters, data.tNodes)}

butterfly = the implied surface carries strike arbitrage there (filled from the nearest strike) · calendar = its variance decreases in time (floored) · floored = below the fit's floor · capped = ABOVE the fit's variance cap: reported, not clipped (only the 400 % ceiling clips) — where the twin's wings leave the box the affine sheet lives in`}
            className={data.counters.clean ? "text-emerald-400/90" : "text-amber-400/90"}
          >
            {repairSummary(data.counters)}
          </span>
        </span>
      )}
    </div>
  );
}
