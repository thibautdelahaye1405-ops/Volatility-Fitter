// The ANCHORING AXIS (2026-09-07) — pure helpers, no React: a production fit
// may carry two anchoring blocks, the persistence PRIOR (yesterday's smile,
// transported) and the observation FILTER's prediction (Note 15). The axis
// compares shadow fits of the prevailing family that differ from production
// in those blocks alone:
//   free   — no prior, no filter (the pure market fit)
//   prior  — the persistence prior with the filter off
//   filter — the filter's prediction block from the kept state (a PREVIEW of
//            active mode while the filter runs in overlay mode; production
//            itself once it is active)
// The backend derives the axis from the live Options (AnchoringInfo): each
// cell exists only when its input exists, one cell coincides with production
// and is tagged. Two surfaces read these helpers — the Compare chip group +
// table (shadow rows, Pull column) and the Fit switch of the Smile / Density
// views (draw a shadow instead of production). Mirrors lib/tailMatch.
import type { AnchoringCell, AnchoringInfo, CompareModelFit } from "./mockData";

/** Wire order of the cells (the order the chips show and the query sends). */
export const ANCHORING_ORDER: readonly AnchoringCell[] = ["free", "prior", "filter"];

/** Chip / switch labels. */
export const ANCHORING_LABELS: Record<AnchoringCell, string> = {
  free: "Free",
  prior: "+ Prior",
  filter: "+ Filter",
};

/** Short names for the table pill, the chart legend and the SHADOW tag. */
export const ANCHORING_SHORT: Record<AnchoringCell, string> = {
  free: "free",
  prior: "+prior",
  filter: "+filter",
};

/** Hover text of each cell, in user language. */
export const ANCHORING_TITLES: Record<AnchoringCell, string> = {
  free:
    "Free — the pure market fit of the prevailing model: no persistence prior, no observation filter. " +
    "The yardstick the other cells are measured against (its pull reads 0).",
  prior:
    "+ Prior — the prevailing model refit with the persistence prior alone (yesterday's smile, transported) " +
    "and the filter off: what the prior bought on this node.",
  filter:
    "+ Filter — the prevailing model refit with the filter's prediction block forced from the kept state, " +
    "with the persistence resolved as production does. A preview of active mode while the filter runs in " +
    "overlay mode; production itself when the filter is active.",
};

/** SVG stroke dashes of the shadow curves (the plain row stays solid). */
export const ANCHORING_DASH: Record<AnchoringCell, string> = {
  free: "2 3",
  prior: "7 3",
  filter: "9 3 2 3",
};

/** The Fit switch value: production, or one shadow cell drawn instead. */
export type FitAnchoring = "production" | AnchoringCell;

export interface AnchoringChipState {
  /** Lit: selected, or the production cell (always lit). */
  on: boolean;
  /** The backend reports the cell's input exists (unknown ⇒ true). */
  available: boolean;
  /** The production fit coincides with this cell. */
  production: boolean;
  /** What a PREVIEW cell assumes beyond the live Options (null = none). */
  preview: string | null;
  title: string;
}

/** The chip's state from the selection and the node's last axis report. */
export function anchoringChipState(
  cell: AnchoringCell,
  selected: ReadonlySet<AnchoringCell>,
  info: AnchoringInfo | null | undefined,
): AnchoringChipState {
  const production = info?.production === cell;
  const available = info == null || info.available.includes(cell);
  // A remembered selection of a cell THIS node lacks never reads as lit.
  const on = production || (available && selected.has(cell));
  const preview = available && !production ? (info?.preview?.[cell] ?? null) : null;
  let title = ANCHORING_TITLES[cell];
  if (production) title += "\nProduction fit — the prevailing row";
  else if (!available) {
    const note = info?.notes?.[cell];
    title += `\nUnavailable on this node${note ? `: ${note}` : ""}`;
  } else if (preview !== null) title += `\nPreview: ${preview}`;
  return { on, available, production, preview, title };
}

/** The inline hints of the cells this node lacks: "+ Prior: no saved prior —
 *  …" in wire order, so the strip says what to do without a hover. */
export function unavailableHints(info: AnchoringInfo | null | undefined): string[] {
  if (info == null) return [];
  return ANCHORING_ORDER.filter((c) => !info.available.includes(c)).map(
    (c) => `${ANCHORING_LABELS[c]}: ${info.notes?.[c] ?? "unavailable on this node"}`,
  );
}

/** A SHADOW row: carries a cell that is not the production one (the plain
 *  displayed-family row also names its cell — that one IS production). */
export function isShadowRow(
  row: Pick<CompareModelFit, "anchoring">,
  info: AnchoringInfo | null | undefined,
): boolean {
  const cell = row.anchoring ?? null;
  return cell !== null && cell !== (info?.production ?? null);
}

export interface AnchoringPill {
  label: string;
  title: string;
}

/** The table pill of a row: "prod" on the plain displayed-family row (it
 *  coincides with a cell), the cell's short name on a shadow row, none on
 *  the other families' rows. */
export function anchoringPill(
  row: Pick<CompareModelFit, "anchoring">,
  info: AnchoringInfo | null | undefined,
): AnchoringPill | null {
  const cell = row.anchoring ?? null;
  if (cell === null) return null;
  if (cell === (info?.production ?? null)) {
    return {
      label: "prod",
      title: `Production fit — coincides with the ${ANCHORING_LABELS[cell]} cell of the anchoring axis`,
    };
  }
  return { label: ANCHORING_SHORT[cell], title: `Shadow fit — ${ANCHORING_TITLES[cell]}` };
}

/** Signed one-decimal number ("+12.3", "-4.0", "0.0"), em-dash when absent. */
function signed(v: number | null | undefined, digits: number): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const text = Math.abs(v).toFixed(digits);
  if (Number(text) === 0) return (0).toFixed(digits);
  return `${v > 0 ? "+" : "-"}${text}`;
}

export interface PullText {
  /** The ATM pull in vol bp ("+12.3"), or "—" when the row carries none. */
  text: string;
  /** Hover text listing ATM bp, skew and curve RMS bp. */
  title: string;
}

/** The Pull column: the row's distance to the free cell (no prior, no
 *  filter) — ATM vol in bp as the cell text; skew and the RMS curve
 *  distance over the quoted range in the hover. */
export function formatPull(
  row: Pick<CompareModelFit, "pullAtmBp" | "pullSkew" | "pullCurveBp">,
): PullText {
  const atm = row.pullAtmBp ?? null;
  if (atm === null || !Number.isFinite(atm)) {
    return { text: "—", title: "No pull measured — request an anchoring cell to compare against the free fit" };
  }
  const skew = signed(row.pullSkew, 3);
  const curve = row.pullCurveBp ?? null;
  const curveText = curve === null || !Number.isFinite(curve) ? "—" : curve.toFixed(1);
  return {
    text: signed(atm, 1),
    title: `Pull vs the free fit — ATM ${signed(atm, 1)} bp · skew ${skew} · curve RMS ${curveText} bp over the quoted range`,
  };
}

/** Stable React key of a table row / series: a family may now answer twice
 *  (its plain row and its shadow cells). */
export function compareRowKey(row: Pick<CompareModelFit, "model" | "anchoring">): string {
  return `${row.model}:${row.anchoring ?? "plain"}`;
}

/** The Fit switch options: Production first, then every available cell that
 *  is not production (a switch with Production alone has nothing to draw). */
export function fitSwitchOptions(
  info: AnchoringInfo | null | undefined,
): { id: FitAnchoring; label: string }[] {
  const cells = info == null ? [] : ANCHORING_ORDER.filter((c) => info.available.includes(c) && c !== info.production);
  return [{ id: "production", label: "Production" }, ...cells.map((c) => ({ id: c, label: ANCHORING_LABELS[c] }))];
}
