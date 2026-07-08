// Pure grid model + TSV/CSV codecs for the ticker×ticker edge-matrix editor
// (no React, no side effects; unit-tested in edgeMatrix.test.ts).
//
// The grid maps "SRC|DST" keys to cells. A diagonal "T|T" cell is the ticker's
// own consecutive-expiry calendar chain; an off-diagonal cell is a same-expiry
// cross-ticker pair rule — stored ONCE under the key as written, ruling both
// directions when symmetric. ruleToGrid/gridToRule convert to the persisted
// GraphBlockRule wire format; parseTsv/toCsv are the clipboard codecs.
import type { GraphEdge } from "../state/useGraphEdges";
import type {
  GraphBlockCalendar,
  GraphBlockPair,
  GraphBlockRule,
} from "../state/useGraphBlocks";

/** One matrix cell: weight (trust) + β (amplitude) + both-directions flag. */
export interface MatrixCell {
  weight: number;
  beta: number;
  symmetric: boolean;
}

/** Grid key for a (source, destination) ticker pair. */
export const cellKey = (src: string, dst: string): string => `${src}|${dst}`;

/** The cell governing src→dst: the direct cell, or the mirrored one when it
 *  is symmetric (a symmetric pair is stored once but rules both directions). */
export function cellAt(
  grid: Map<string, MatrixCell>,
  src: string,
  dst: string,
): MatrixCell | undefined {
  const direct = grid.get(cellKey(src, dst));
  if (direct !== undefined) return direct;
  if (src === dst) return undefined;
  const mirror = grid.get(cellKey(dst, src));
  return mirror !== undefined && mirror.symmetric ? mirror : undefined;
}

/** Wire rule → grid. Calendar entries land on the diagonal (always
 *  symmetric); pairs land off-diagonal keyed exactly as written (a|b). */
export function ruleToGrid(rule: GraphBlockRule): Map<string, MatrixCell> {
  const grid = new Map<string, MatrixCell>();
  for (const c of rule.calendar) {
    grid.set(cellKey(c.ticker, c.ticker), {
      weight: c.weight,
      beta: c.beta,
      symmetric: true,
    });
  }
  for (const p of rule.pairs) {
    grid.set(cellKey(p.a, p.b), {
      weight: p.weight,
      beta: p.beta,
      symmetric: p.symmetric,
    });
  }
  return grid;
}

/** Grid → wire rule, in deterministic (sorted-key) order. Zero-weight cells
 *  are dropped — 0 means "no rule", same as a blank TSV cell. */
export function gridToRule(
  grid: Map<string, MatrixCell>,
  overrides: GraphEdge[],
): GraphBlockRule {
  const pairs: GraphBlockPair[] = [];
  const calendar: GraphBlockCalendar[] = [];
  const entries = [...grid.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  for (const [key, cell] of entries) {
    if (cell.weight === 0) continue;
    const [a = "", b = ""] = key.split("|");
    if (a === b) calendar.push({ ticker: a, weight: cell.weight, beta: cell.beta });
    else pairs.push({ a, b, weight: cell.weight, beta: cell.beta, symmetric: cell.symmetric });
  }
  return { pairs, calendar, overrides };
}

/** Fold equal mirrored cells (same weight AND β both ways) into one symmetric
 *  cell, kept under the lexicographically-first key so the result is
 *  deterministic. Pure — returns a new Map. */
export function collapseSymmetric(grid: Map<string, MatrixCell>): Map<string, MatrixCell> {
  const out = new Map<string, MatrixCell>();
  const consumed = new Set<string>();
  for (const key of [...grid.keys()].sort()) {
    if (consumed.has(key)) continue;
    const cell = grid.get(key);
    if (cell === undefined) continue;
    const [a = "", b = ""] = key.split("|");
    const mirrorKey = cellKey(b, a);
    const mirror = a !== b ? grid.get(mirrorKey) : undefined;
    if (mirror !== undefined && mirror.weight === cell.weight && mirror.beta === cell.beta) {
      out.set(key, { ...cell, symmetric: true });
      consumed.add(mirrorKey);
    } else {
      out.set(key, cell);
    }
  }
  return out;
}

/** Parse a pasted matrix. Format: header row = destination tickers (an
 *  optional blank/label corner cell is tolerated), each body row = source
 *  ticker + numeric weights. Tab- or comma-delimited (tab wins when present,
 *  so spreadsheet pastes and our own CSV exports both work). Blank/0 = no
 *  rule. Unknown tickers and non-numeric cells are reported in `errors` and
 *  skipped, never thrown. Values become {weight, beta: 1, symmetric: false}
 *  except the diagonal (symmetric: true); equal mirrored cells are then
 *  collapsed to one symmetric cell via collapseSymmetric. */
export function parseTsv(
  text: string,
  knownTickers: string[],
): { grid: Map<string, MatrixCell>; errors: string[] } {
  const grid = new Map<string, MatrixCell>();
  const errors: string[] = [];
  const known = new Set(knownTickers);
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  const [headerLine, ...bodyLines] = lines;
  if (headerLine === undefined || bodyLines.length === 0) {
    errors.push("need a header row of tickers and at least one body row");
    return { grid, errors };
  }
  const delim = text.includes("\t") ? "\t" : ",";
  const headerCells = headerLine.split(delim).map((c) => c.trim());
  const hasCorner = !known.has(headerCells[0] ?? "");
  // null marks an unknown destination column: reported once, cells skipped.
  const dests: (string | null)[] = (hasCorner ? headerCells.slice(1) : headerCells).map(
    (t) => {
      if (known.has(t)) return t;
      errors.push(`unknown ticker "${t}" (column skipped)`);
      return null;
    },
  );
  for (const line of bodyLines) {
    const cells = line.split(delim);
    const src = (cells[0] ?? "").trim();
    if (!known.has(src)) {
      errors.push(`unknown ticker "${src}" (row skipped)`);
      continue;
    }
    dests.forEach((dst, j) => {
      if (dst === null) return;
      const raw = (cells[j + 1] ?? "").trim();
      if (raw === "") return;
      const weight = Number(raw);
      if (!Number.isFinite(weight)) {
        errors.push(`${src}→${dst}: not a number "${raw}"`);
        return;
      }
      if (weight === 0) return; // 0 = no rule, same as blank
      grid.set(cellKey(src, dst), { weight, beta: 1, symmetric: src === dst });
    });
  }
  return { grid: collapseSymmetric(grid), errors };
}

/** Square CSV matrix: header row + one row per ticker, empty cells for no
 *  rule. Symmetric pairs render in BOTH mirrored cells (via cellAt), so the
 *  export round-trips through parseTsv + collapseSymmetric. */
export function toCsv(grid: Map<string, MatrixCell>, tickers: string[]): string {
  const lines = ["," + tickers.join(",")];
  for (const src of tickers) {
    const row = tickers.map((dst) => {
      const cell = cellAt(grid, src, dst);
      return cell === undefined ? "" : String(cell.weight);
    });
    lines.push([src, ...row].join(","));
  }
  return lines.join("\n") + "\n";
}
