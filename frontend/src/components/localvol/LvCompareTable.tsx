// Per-expiry score table of the Local Vol Compare tab (LV Dupire-twin arc,
// D3), on the ModelCompareTable grammar: one row per expiry of the ladder,
// three surfaces side by side — the parametric source (closed form: rms ·
// max), the Dupire twin (rms · conv · max) and the affine sheet (rms · conv
// · max) — then the round trip (the twin repriced back against its own
// parametric source: rms · max). "rms" is the WEIGHTED fit-target RMS
// (the AffineSmile.rmsError basis) so the three columns compare like for
// like; "conv" the converged-operator RMS. Clicking a row selects that
// expiry (the smile panel follows). Formatting lives in lib/lvCompare.
import { AFFINE_COLOR, PARAMETRIC_COLOR, TWIN_COLOR, formatBp, scoreBp } from "../../lib/lvCompare";
import type { LvCompareResponse } from "../../state/useLvCompare";

export interface LvCompareTableProps {
  data: LvCompareResponse;
  selectedExpiry: string | null;
  onSelectExpiry: (iso: string) => void;
  formatExpiry: (iso: string, t: number) => string;
}

const GROUPS: { label: string; color: string; title: string; cols: string[] }[] = [
  { label: "Parametric", color: PARAMETRIC_COLOR, title: "The displayed parametric fit (closed form): weighted RMS · worst quote, bp", cols: ["rms", "max"] },
  { label: "Dupire twin", color: TWIN_COLOR, title: "The smooth twin marched on its display operator (second-order, refined): weighted RMS · worst quote, bp", cols: ["rms", "max"] },
  { label: "Affine", color: AFFINE_COLOR, title: "The displayed LV sheet: weighted RMS · converged-operator RMS · worst quote, bp", cols: ["rms", "conv", "max"] },
  {
    label: "Round trip", color: "rgb(148 163 184)",
    title: "Twin vs its own parametric source at the quoted strikes: rms · max · the operator's floor (a flat surface's error on the same operator) · the nodal SHEET's own round trip (what the coarse lattice loses), bp",
    cols: ["rms", "max", "floor", "sheet"],
  },
];

const CELL = "px-2 py-1 font-mono";

export default function LvCompareTable({ data, selectedExpiry, onSelectExpiry, formatExpiry }: LvCompareTableProps) {
  return (
    <div className="shrink-0 overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-slate-800 text-left text-[10px] uppercase tracking-wider text-slate-500">
            <th rowSpan={2} className="px-2 py-1 font-medium">Expiry</th>
            {GROUPS.map((g) => (
              <th key={g.label} colSpan={g.cols.length} className="px-2 pt-1 font-medium" title={g.title}>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: g.color }} />
                  {g.label}
                </span>
              </th>
            ))}
          </tr>
          <tr className="border-b border-slate-800 text-left text-[9px] uppercase tracking-wider text-slate-600">
            {GROUPS.flatMap((g) => g.cols.map((c) => (
              <th key={`${g.label}-${c}`} className="px-2 pb-1 font-medium">{c}</th>
            )))}
          </tr>
        </thead>
        <tbody>
          {data.smiles.map((s) => {
            const p = scoreBp(s.parametricScore);
            const tw = scoreBp(s.twinScore);
            const af = scoreBp(s.affineScore);
            const selected = s.expiry === selectedExpiry;
            return (
              <tr
                key={s.expiry}
                data-selected={selected ? "true" : undefined}
                onClick={() => onSelectExpiry(s.expiry)}
                className={[
                  "cursor-pointer border-b border-slate-800/60 transition-colors hover:bg-surface-800/60",
                  selected ? "bg-surface-800 text-slate-100" : "text-slate-300",
                ].join(" ")}
                title="Click: show this expiry's smiles"
              >
                <td className="px-2 py-1 font-medium">{formatExpiry(s.expiry, s.t)}</td>
                <td className={CELL}>{formatBp(p.rms)}</td>
                <td className={CELL}>{formatBp(p.max)}</td>
                <td className={CELL}>{formatBp(tw.rms)}</td>
                <td className={CELL}>{formatBp(tw.max)}</td>
                <td className={CELL}>{formatBp(af.rms)}</td>
                <td className={CELL}>{formatBp(af.conv)}</td>
                <td className={CELL}>{formatBp(af.max)}</td>
                <td className={CELL}>{formatBp(s.roundTripBp, 1)}</td>
                <td className={CELL}>{formatBp(s.roundTripMaxBp, 1)}</td>
                <td className={CELL}>{formatBp(s.operatorBp, 1)}</td>
                <td className={CELL}>{formatBp(s.sheetRoundTripBp)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
