// Model-family palette for the Compare view (V3.2 item 12) — the book's
// convention: LQD green / SVI blue / MCS violet, plus amber for the
// compare-only eSSVI yardstick. Tailwind 500 shades so the curves sit
// naturally beside the app's accent colours on the dark surface.
// Pure data — no React, no DOM.
import type { CompareModelId } from "./mockData";

/** Stroke / chip colour per model family (tailwind green/blue/violet/amber 500). */
export const MODEL_COLORS: Record<CompareModelId, string> = {
  lqd: "#22c55e",
  svi: "#3b82f6",
  sigmoid: "#8b5cf6",
  essvi: "#f59e0b",
};

/** Display names (MCS = the Multi-Core Sigmoid, book ch. 3; eSSVI = the
 *  Gatheral–Jacquier SSVI slice with a per-expiry ρ, Hendriks–Martini). */
export const MODEL_LABELS: Record<CompareModelId, string> = {
  lqd: "LQD",
  svi: "SVI-JW",
  sigmoid: "MCS",
  essvi: "eSSVI",
};

/** Wire / book ordering of every comparable family (the reference last).
 *  This is the order the compare endpoint is asked in and the chart draws. */
export const MODEL_ORDER: readonly CompareModelId[] = ["lqd", "svi", "sigmoid", "essvi"];

/** REFERENCE families: compare-only yardsticks that are never a displayed
 *  (calibrated) model — FitSettings.model does not know them. They are not
 *  in the default chip set: the Compare strip reveals them behind a
 *  "+ reference" affordance, the table tags their row and the chart dashes
 *  their curve. Today: eSSVI (three handles, the belly tied to the wings),
 *  the yardstick the five-parameter SVI-JW row is measured against. */
export const REFERENCE_MODELS: ReadonlySet<CompareModelId> = new Set<CompareModelId>(["essvi"]);

export function isReferenceModel(id: CompareModelId): boolean {
  return REFERENCE_MODELS.has(id);
}

/** Why a family is a reference row (hover text of the pill and the chip). */
export const REFERENCE_NOTE: Partial<Record<CompareModelId, string>> = {
  essvi:
    "Reference family — the Gatheral–Jacquier SSVI slice with a per-expiry ρ (Hendriks–Martini): " +
    "a three-handle yardstick fitted on the same quotes, never a calibrated / displayed model",
};

/** The DEFAULT chip set: the families a user can calibrate and display. */
export const CHIP_MODELS: readonly CompareModelId[] = MODEL_ORDER.filter((m) => !REFERENCE_MODELS.has(m));

/** The reference families, in wire order (the hidden-by-default chips). */
export const REFERENCE_ORDER: readonly CompareModelId[] = MODEL_ORDER.filter((m) => REFERENCE_MODELS.has(m));
