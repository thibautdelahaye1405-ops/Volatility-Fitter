// Model-family palette for the Compare view (V3.2 item 12) — the book's
// convention: LQD green / SVI blue / MCS violet. Tailwind 500 shades so the
// curves sit naturally beside the app's accent colours on the dark surface.
// Pure data — no React, no DOM.
import type { CompareModelId } from "./mockData";

/** Stroke / chip colour per model family (tailwind green/blue/violet 500). */
export const MODEL_COLORS: Record<CompareModelId, string> = {
  lqd: "#22c55e",
  svi: "#3b82f6",
  sigmoid: "#8b5cf6",
};

/** Display names (MCS = the Multi-Core Sigmoid, book ch. 3). */
export const MODEL_LABELS: Record<CompareModelId, string> = {
  lqd: "LQD",
  svi: "SVI-JW",
  sigmoid: "MCS",
};

/** Book ordering of the comparable families. */
export const MODEL_ORDER: readonly CompareModelId[] = ["lqd", "svi", "sigmoid"];
