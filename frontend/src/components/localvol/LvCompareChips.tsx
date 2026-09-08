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
import type { LvCompareMode } from "../../lib/lvCompare";
import type { LvCompareResponse, LvTInterp } from "../../state/useLvCompare";

export interface LvCompareChipsProps {
  tInterp: LvTInterp;
  onTInterpChange: (v: LvTInterp) => void;
  mode: LvCompareMode;
  onModeChange: (m: LvCompareMode) => void;
  /** The last payload (score strip); null before the first lands. */
  data: LvCompareResponse | null;
  /** A build in flight (spinner on the lit interpolation chip). */
  loading: boolean;
}

const CHIP_BASE = "flex items-center gap-1.5 rounded border px-2 py-0.5 text-[11px] font-medium transition-colors";
const CHIP_OFF = "border-slate-800 text-slate-500 hover:border-slate-600 hover:text-slate-200";
const CHIP_MUTED = "border-slate-800/70 text-slate-600 opacity-60 cursor-default";
const GROUP_LABEL = "text-[9px] font-semibold uppercase tracking-wider text-slate-600";
const SPINNER = "h-2.5 w-2.5 animate-spin rounded-full border border-slate-500 border-t-transparent";
const DIVIDER = <span className="mx-0.5 h-3 w-px bg-slate-800" aria-hidden />;

export default function LvCompareChips({
  tInterp, onTInterpChange, mode, onModeChange, data, loading,
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
            className={[CHIP_BASE, on ? "border-orange-500/50 bg-orange-500/10 text-orange-100" : CHIP_OFF].join(" ")}
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
      {LV_TAIL_OPTIONS.map((o) => (
        <button
          key={o.id}
          aria-pressed={o.available}
          disabled
          title={o.title}
          className={[
            CHIP_BASE,
            o.available ? "cursor-default border-orange-500/50 bg-orange-500/10 text-orange-100" : CHIP_MUTED,
          ].join(" ")}
        >
          {o.label}
          {o.available
            ? <span className="text-[9px] uppercase text-slate-500">v1</span>
            : <span className="text-[9px] uppercase text-slate-600">rider</span>}
        </button>
      ))}
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
          <span title="Converged-operator RMS vs the fit target (bp): the Dupire twin · the affine sheet · the parametric source's closed form">
            conv twin {formatBp(twin.convergedBp)}
            {affine ? ` · affine ${formatBp(affine.convergedBp)}` : ""}
            {` · param ${formatBp(param.rmsBp)} bp`}
          </span>
          <span title="Round trip: the twin repriced back against its own parametric source at the quoted strikes (converged operator) — the lattice sampling + discretization, nothing else: rms · max">
            round trip {formatBp(data.roundTripBp)} · {formatBp(data.roundTripMaxBp)} bp
          </span>
          <span
            title={repairDetail(data.counters, data.tNodes)}
            className={data.counters.clean ? "text-emerald-400/90" : "text-amber-400/90"}
          >
            {repairSummary(data.counters)}
          </span>
        </span>
      )}
    </div>
  );
}
