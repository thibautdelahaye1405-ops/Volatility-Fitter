// The series half of a deep link (SERIES ARC S4): `?series=<id>&frame=<n>`
// is parsed by useDeepLink on mount, before any Series lens exists, so the
// hook parks it here and the lens takes it ONCE when it mounts — a plain
// module slot, no context, no persistence (a refresh never re-opens it: the
// address bar is stripped with the node link).

export interface SeriesLink {
  /** The stored series id. */
  id: string;
  /** Frame index to jump to once the document is in (0-based). */
  frame?: number;
}

let pending: SeriesLink | null = null;

/** Park a series link for the next Series lens mount (null clears it). */
export function setPendingSeriesLink(link: SeriesLink | null): void {
  pending = link;
}

/** Take the parked link — consumed once; null when nothing is parked. */
export function takePendingSeriesLink(): SeriesLink | null {
  const link = pending;
  pending = null;
  return link;
}
