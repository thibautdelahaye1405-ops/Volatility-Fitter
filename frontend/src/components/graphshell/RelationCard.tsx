// Relation inspector card (GRAPH ERGONOMICS ARC, E5): ONE relation, edited
// with sliders. Sits in the right-hand Inspector when an arrow (or a
// Relations-tab row) is selected.
//
//   header      informer → receiver · class select · ⇄ flip · × close
//   confidence  the SigmaSlider (σ in vol points, raw p behind the units
//               lens); a calendar row on the distance rule shows "auto" and
//               today's derived value — moving the slider locks it explicit,
//               ↺ returns it to the rule (cross rows reset to the pane scale)
//   amplitude   β ATM slider (mark at 1); handles are LINKED by default (one
//               slider drives all three), unlock for β skew / β curvature
//   semantics   Layered only (reciprocal ⇄ / directed →; auto = class default)
//   footer      the implied reverse (1/β, σ/|β|), "+ reverse" (an EXPLICIT
//               opposite arrow — only meaningful for a directed relation;
//               under reciprocal semantics the reverse is already implied,
//               and two directed arcs facing each other form a directed
//               cycle the layered solve rejects) and Delete
// Every change goes straight to the draft (the shell's useRelationDraft);
// nothing here persists on its own.
import { useState } from "react";
import SigmaSlider from "./SigmaSlider";
import Slider from "../Slider";
import { effectiveCalendarPolicy } from "../../lib/calendarPolicy";
import { calendarPrecision, reverseBeta, reversePrecision } from "../../lib/messagePreview";
import { fmtSigmaPts, relationSentence } from "../../lib/precisionUnits";
import type { SolverParams } from "../../state/useGraph";
import {
  CLASS_DEFAULT_SEMANTICS,
  RELATION_CLASSES,
  type MessageEdgeRow,
  type RelationClass,
  type RelationSemantics,
} from "../../state/useMessageEdges";
import { semanticsLabel } from "../MessageEdgeEditor.helpers";

interface RelationCardProps {
  row: MessageEdgeRow;
  params: SolverParams;
  layered: boolean;
  raw: boolean;
  /** Year fraction of a node (for the distance-derived precision), if known. */
  tOf?: (ticker: string, expiry: string) => number | undefined;
  onChange: (patch: Partial<MessageEdgeRow>) => void;
  onFlip: () => void;
  onDelete: () => void;
  /** Create (or select) the explicit opposite arrow. */
  onAddReverse?: () => void;
  /** The opposite arrow already exists in the draft. */
  reverseExists?: boolean;
  onClose: () => void;
}

const short = (ticker: string, expiry: string) => `${ticker} ${expiry.slice(5)}`;
const selCls =
  "rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500";
const smallBtn =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-300 transition-colors hover:border-slate-600 hover:text-slate-100";

/** Exact-entry twin of a β slider (the readout badge). */
function BetaInput({ value, onChange, title }: { value: number; onChange: (v: number) => void; title: string }) {
  return (
    <input
      type="number"
      step={0.05}
      value={Number(value.toFixed(3))}
      title={title}
      onChange={(e) => {
        const v = e.target.valueAsNumber;
        if (Number.isFinite(v)) onChange(v);
      }}
      className="w-14 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500"
    />
  );
}

export default function RelationCard({
  row,
  params,
  layered,
  raw,
  tOf,
  onChange,
  onFlip,
  onDelete,
  onAddReverse,
  reverseExists = false,
  onClose,
}: RelationCardProps) {
  const [linked, setLinked] = useState(
    row.betaSkew === row.betaAtmVol && row.betaCurv === row.betaAtmVol,
  );
  const calendar = row.relationClass === "calendar";
  const derived = row.precisionRule === "calendar_distance";
  const rho = calendar ? params.ampCal : params.ampCross;

  // Distance-derived precision: today's value under the receiver's policy.
  const tR = tOf?.(row.targetTicker, row.targetExpiry);
  const tI = tOf?.(row.sourceTicker, row.sourceExpiry);
  const policy = effectiveCalendarPolicy(params, row.targetTicker);
  const shownPrecision =
    derived && tR !== undefined && tI !== undefined
      ? calendarPrecision(tR, tI, policy.scale, params.calEpsilon, params.calDecay)
      : row.messagePrecision;

  const sentence = relationSentence({
    sourceLabel: short(row.sourceTicker, row.sourceExpiry),
    targetLabel: short(row.targetTicker, row.targetExpiry),
    beta: row.betaAtmVol,
    precision: shownPrecision,
    rho,
  });
  const setBeta = (v: number) =>
    onChange(linked ? { betaAtmVol: v, betaSkew: v, betaCurv: v } : { betaAtmVol: v });
  const semanticsValue = row.relationSemantics ?? "auto";
  const semanticsDefault = CLASS_DEFAULT_SEMANTICS[row.relationClass];

  return (
    <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/60 p-2" data-testid="relation-card">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-200" title={sentence}>
          {short(row.sourceTicker, row.sourceExpiry)}{" "}
          <span className="text-accent-400">→</span>{" "}
          {short(row.targetTicker, row.targetExpiry)}
        </span>
        <button onClick={onFlip} title="Reverse the direction (1/β, σ/|β| — the one-factor identities)" className={smallBtn} data-testid="relation-flip">
          ⇄
        </button>
        <button onClick={onClose} title="Close relation card" className="px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200">
          ×
        </button>
      </div>
      <p className="mb-2 text-[10px] text-slate-500" title={sentence}>
        {sentence}
      </p>

      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs text-slate-400">Class</span>
        <select
          className={selCls}
          value={row.relationClass}
          title="Relation class (drives the amplitude multiplier ρ and the layered-mode semantics default)"
          onChange={(e) => onChange({ relationClass: e.target.value as RelationClass })}
        >
          {RELATION_CLASSES.map((c) => (
            <option key={c} value={c}>
              {c.replace("_", " ")}
            </option>
          ))}
        </select>
      </div>

      <SigmaSlider
        label="Confidence"
        title={
          derived
            ? "Distance-derived relationship uncertainty (today's value under the receiver's calendar policy). Moving the slider locks it explicit; ↺ returns to the rule."
            : "Relationship uncertainty σ = 1/√p of this ONE factor (vol pts) — right = tighter coupling"
        }
        precision={shownPrecision}
        raw={raw}
        onChange={(p) => onChange({ messagePrecision: p, precisionRule: "explicit" })}
        onReset={() =>
          onChange(
            calendar
              ? { precisionRule: "calendar_distance" }
              : { messagePrecision: params.crossPrecision, precisionRule: "explicit" },
          )
        }
        resetTitle={calendar ? "Back to the maturity-distance rule" : "Back to the pane's cross-asset confidence"}
        muted={derived}
        badge={
          derived ? (
            <span className="rounded bg-surface-800 px-1 text-[8px] uppercase tracking-wide text-slate-500" title="Precision follows the §9.2 maturity-gap rule at solve time">
              auto
            </span>
          ) : undefined
        }
        testId="slider-sigma"
      />

      <div className="mt-2">
        <Slider
          label={linked ? "β (all handles)" : "β ATM"}
          title="Amplitude β: what +1 pt of the informer's innovation becomes at the receiver (before the class multiplier ρ). Mark = 1."
          value={row.betaAtmVol}
          min={0}
          max={3}
          step={0.01}
          mark={1}
          format={(v) => v.toFixed(2)}
          onChange={setBeta}
          badge={<BetaInput value={row.betaAtmVol} onChange={setBeta} title="β ATM (exact)" />}
          testId="slider-beta"
        />
        <label className="mt-1 flex items-center gap-1.5 text-[10px] text-slate-500" title="Linked: one slider drives β ATM, β skew and β curvature together">
          <input
            type="checkbox"
            checked={linked}
            onChange={(e) => {
              setLinked(e.target.checked);
              if (e.target.checked) onChange({ betaSkew: row.betaAtmVol, betaCurv: row.betaAtmVol });
            }}
            className="accent-accent-500"
          />
          link handles
        </label>
        {!linked && (
          <>
            <Slider className="mt-1" label="β skew" title="Skew-handle amplitude" value={row.betaSkew} min={0} max={3} step={0.01} mark={1} format={(v) => v.toFixed(2)} onChange={(v) => onChange({ betaSkew: v })} badge={<BetaInput value={row.betaSkew} onChange={(v) => onChange({ betaSkew: v })} title="β skew (exact)" />} testId="slider-beta-skew" />
            <Slider className="mt-1" label="β curvature" title="Curvature-handle amplitude" value={row.betaCurv} min={0} max={3} step={0.01} mark={1} format={(v) => v.toFixed(2)} onChange={(v) => onChange({ betaCurv: v })} badge={<BetaInput value={row.betaCurv} onChange={(v) => onChange({ betaCurv: v })} title="β curvature (exact)" />} testId="slider-beta-curv" />
          </>
        )}
      </div>

      <div className={"mt-2 flex items-center justify-between gap-2" + (layered ? "" : " opacity-50")}>
        <span className="text-xs text-slate-400" title={layered ? "Layered-mode behaviour of the factor" : "Takes effect in Layered mode only"}>
          Semantics
        </span>
        <select
          className={selCls}
          value={semanticsValue}
          title={`recip ⇄: information flows both ways; direct →: one-way informer→receiver state, ZERO reverse influence. auto = the class default (${semanticsLabel(semanticsDefault)}).`}
          onChange={(e) =>
            onChange({ relationSemantics: e.target.value === "auto" ? null : (e.target.value as RelationSemantics) })
          }
        >
          <option value="auto">auto · {semanticsLabel(semanticsDefault)}</option>
          <option value="reciprocal_harmonic">recip ⇄</option>
          <option value="directed_state">direct →</option>
        </select>
      </div>

      <div className="mt-2 flex items-center justify-between gap-2 border-t border-slate-800 pt-2">
        <span className="font-mono text-[9px] text-slate-600" title="Implied reverse identities of this ONE-factor relation: amplitude 1/β, relationship uncertainty σ/|β| (spec §7.6/§8.3). One arrow is one factor; with reciprocal semantics information already flows both ways at these implied values.">
          ⇐ β {reverseBeta(row.betaAtmVol).toFixed(2)} · σ {fmtSigmaPts(reversePrecision(shownPrecision, row.betaAtmVol))} pt
        </span>
        <span className="flex items-center gap-1">
          {onAddReverse !== undefined && (
            <button
              onClick={onAddReverse}
              title={
                reverseExists
                  ? "The opposite arrow already exists — select it"
                  : "Add an EXPLICIT opposite arrow (receiver → informer) as its own factor. Meaningful for a directed relation; under reciprocal semantics the reverse is already implied (⇐), and two directed arcs facing each other form a directed cycle the Layered solve rejects (preflight blocks it)."
              }
              className={smallBtn}
              data-testid="relation-add-reverse"
            >
              {reverseExists ? "⇐ reverse" : "+ reverse"}
            </button>
          )}
          <button onClick={onDelete} title="Remove this relation (Delete)" className={smallBtn + " hover:border-rose-500/50 hover:text-rose-300"} data-testid="relation-delete">
            Delete
          </button>
        </span>
      </div>
    </div>
  );
}
