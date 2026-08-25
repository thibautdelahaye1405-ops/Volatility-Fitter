// Series-building + formatting logic for the Compare view (V3.2 item 12).
// Pure functions (no React, no DOM) so the chart series, the validity chip
// and the null-metric handling are unit-testable — SmileViewer stays a thin
// consumer (file-size policy).
import type { OverlaySeries } from "../components/OverlayCurvesChart";
import type { CompareModelFit, CompareResponse } from "./mockData";
import { MODEL_COLORS, MODEL_LABELS } from "./modelColor";

/** One OverlayCurvesChart series per successfully fitted model, in the
 *  response's (book) order, coloured by family. Failed rows and degenerate
 *  curves are skipped — the table still lists them with their error. */
export function compareSeries(data: CompareResponse): OverlaySeries[] {
  return data.models
    .filter((m) => m.ok && m.curve.length > 1)
    .map((m) => ({
      label: MODEL_LABELS[m.model] ?? m.label,
      xs: m.curve.map((p) => p.k),
      ys: m.curve.map((p) => p.vol),
      color: MODEL_COLORS[m.model] ?? "#94a3b8",
    }));
}

/** Validity chip content: certified ⇒ green "clean", breach ⇒ rose with the
 *  minimum value, no analytic signal ⇒ neutral "n/a". */
export interface ValidityChip {
  label: string;
  /** true = certified (green), false = breach (rose), null = no signal. */
  certified: boolean | null;
  /** Hover text naming the per-family analytic quantity. */
  title: string;
}

/** Compact scientific notation for tiny signed magnitudes (−3.1e−4). */
export function formatExp(v: number): string {
  return v.toExponential(1).replace("e-", "e−").replace("-", "−");
}

export function validityChip(fit: CompareModelFit): ValidityChip {
  const v = fit.validity ?? null;
  const quantity =
    v?.kind === "density"
      ? "risk-neutral density minimum (LQD: ≥ 0 by construction)"
      : "minimum Durrleman g over the traded range (< 0 ⇒ butterfly arb)";
  if (!fit.ok) return { label: "fit failed", certified: false, title: fit.error ?? "fit failed" };
  if (v === null || v.certified === null || v.certified === undefined) {
    return { label: "n/a", certified: null, title: "No analytic no-arbitrage signal for this family" };
  }
  const min = v.minValue ?? null;
  const minText = min === null ? "" : ` ${formatExp(min)}`;
  return v.certified
    ? { label: "clean", certified: true, title: `Certified — ${quantity}:${minText || " n/a"}` }
    : { label: `breach${minText}`, certified: false, title: `NOT certified — ${quantity}` };
}

/** Fixed-digit number, em-dash for null / undefined / non-finite. */
export function formatMetric(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

/** Decimal vol as a percentage ("20.62%"), em-dash when absent. */
export function formatVolPct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? "—" : `${(v * 100).toFixed(2)}%`;
}

/** Fit wall time: reused committed record ⇒ "cached", else "12 ms". */
export function formatFitMs(fit: CompareModelFit): string {
  if (fit.reused) return "cached";
  return fit.fitMs === null || fit.fitMs === undefined ? "—" : `${fit.fitMs.toFixed(0)} ms`;
}

const TAIL_ABBREV: Record<string, string> = {
  exponential: "exp",
  intermediate: "int",
  gaussian: "gauss",
};

/** Structural tail contract pair ("exp/exp", "int/gauss"), em-dash when the
 *  family claims no contract. Unknown class names pass through verbatim. */
export function formatTailPair(fit: CompareModelFit): string {
  const left = fit.tailLeft ?? null;
  const right = fit.tailRight ?? null;
  if (left === null && right === null) return "—";
  const short = (c: string | null) => (c === null ? "—" : (TAIL_ABBREV[c] ?? c));
  return `${short(left)}/${short(right)}`;
}
