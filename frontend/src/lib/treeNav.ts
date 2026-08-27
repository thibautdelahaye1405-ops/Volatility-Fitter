// Keyboard navigation of the Nodes tree (UI SHELL v2 wave 3, C1) — pure.
//
// The pane flattens its VISIBLE rows (ticker groups, then the expiry rows of
// expanded groups) into a list; this module turns a key press on the focused
// row into ONE action the pane applies: move the focus, expand / collapse a
// ticker, open a node (preview · pinned · in the other split), toggle its
// lit/dark designation, or hand the focus to the filter box. Type-ahead
// (letters typed in quick succession) jumps to the next ticker whose symbol
// starts with the buffer. Vitest-locked in treeNav.test.ts.

export interface TreeRow {
  /** Row id: "g:TICKER" for a group, the tab key "TICKER|expiry" for a node. */
  id: string;
  kind: "group" | "node";
  ticker: string;
  expiry?: string;
  /** Groups only. */
  expanded?: boolean;
}

export type TreeAction =
  | { type: "focus"; id: string }
  | { type: "expand"; ticker: string; expanded: boolean }
  | { type: "open"; ticker: string; expiry: string; mode: "preview" | "pin" | "split" }
  | { type: "lit"; ticker: string; expiry: string }
  | { type: "filter" };

export interface KeyLike {
  key: string;
  shiftKey?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
}

/** Type-ahead buffer: letters typed within this window chain into a prefix. */
export const TYPEAHEAD_MS = 700;

export interface TypeAhead {
  buffer: string;
  at: number;
}

export const EMPTY_TYPEAHEAD: TypeAhead = { buffer: "", at: 0 };

export function groupId(ticker: string): string {
  return `g:${ticker}`;
}

/** Next group whose ticker starts with `prefix`, searching after `fromId`
 *  (wrapping); the focused group itself matches only when nothing else does. */
export function typeAheadTarget(rows: TreeRow[], fromId: string | null, prefix: string): string | null {
  const p = prefix.toUpperCase();
  if (p === "") return null;
  const groups = rows.filter((r) => r.kind === "group");
  if (groups.length === 0) return null;
  const from = fromId === null ? -1 : groups.findIndex((g) => g.id === fromId || fromId.startsWith(`${g.ticker}|`));
  for (let step = 1; step <= groups.length; step++) {
    const g = groups[(from + step + groups.length) % groups.length];
    if (g.ticker.toUpperCase().startsWith(p)) return g.id;
  }
  return null;
}

/**
 * Resolve a key press. Returns the action (or null when the key is not ours)
 * and the updated type-ahead state. `now` is epoch ms (injected for tests).
 */
export function treeKeyAction(
  rows: TreeRow[],
  focusedId: string | null,
  e: KeyLike,
  typeahead: TypeAhead = EMPTY_TYPEAHEAD,
  now = 0,
): { action: TreeAction | null; typeahead: TypeAhead } {
  const idx = focusedId === null ? -1 : rows.findIndex((r) => r.id === focusedId);
  const row = idx >= 0 ? rows[idx] : null;
  const none = { action: null, typeahead: EMPTY_TYPEAHEAD };
  const focus = (i: number): { action: TreeAction | null; typeahead: TypeAhead } => ({
    action: rows[i] ? { type: "focus", id: rows[i].id } : null,
    typeahead: EMPTY_TYPEAHEAD,
  });
  if (e.altKey) return none;

  switch (e.key) {
    case "ArrowDown":
      return focus(Math.min(rows.length - 1, idx + 1));
    case "ArrowUp":
      return focus(Math.max(0, idx < 0 ? 0 : idx - 1));
    case "Home":
      return focus(0);
    case "End":
      return focus(rows.length - 1);
    case "ArrowRight":
      if (row === null) return focus(0);
      if (row.kind === "group") {
        if (!row.expanded) return { action: { type: "expand", ticker: row.ticker, expanded: true }, typeahead: EMPTY_TYPEAHEAD };
        return rows[idx + 1]?.kind === "node" ? focus(idx + 1) : none;
      }
      return none;
    case "ArrowLeft":
      if (row === null) return none;
      if (row.kind === "group") {
        return row.expanded
          ? { action: { type: "expand", ticker: row.ticker, expanded: false }, typeahead: EMPTY_TYPEAHEAD }
          : none;
      }
      return { action: { type: "focus", id: groupId(row.ticker) }, typeahead: EMPTY_TYPEAHEAD };
    case "Enter":
    case " ": {
      if (row === null) return none;
      if (row.kind === "group") return { action: { type: "expand", ticker: row.ticker, expanded: !row.expanded }, typeahead: EMPTY_TYPEAHEAD };
      const mode = e.ctrlKey || e.metaKey ? "split" : e.shiftKey || e.key === " " ? "pin" : "preview";
      return { action: { type: "open", ticker: row.ticker, expiry: row.expiry ?? "", mode }, typeahead: EMPTY_TYPEAHEAD };
    }
    case "Tab":
      if (e.shiftKey) return none;
      return { action: { type: "filter" }, typeahead: EMPTY_TYPEAHEAD };
    default:
      break;
  }
  if (e.ctrlKey || e.metaKey || e.key.length !== 1) return none;
  // L toggles lit/dark on a node row (unless it extends a type-ahead prefix).
  const chained = typeahead.buffer !== "" && now - typeahead.at <= TYPEAHEAD_MS;
  if (!chained && /^[lL]$/.test(e.key) && row?.kind === "node") {
    return { action: { type: "lit", ticker: row.ticker, expiry: row.expiry ?? "" }, typeahead: EMPTY_TYPEAHEAD };
  }
  if (!/^[a-zA-Z0-9.^=-]$/.test(e.key)) return none;
  const buffer = (chained ? typeahead.buffer : "") + e.key;
  const target = typeAheadTarget(rows, focusedId, buffer);
  return {
    action: target !== null ? { type: "focus", id: target } : null,
    typeahead: { buffer, at: now },
  };
}
