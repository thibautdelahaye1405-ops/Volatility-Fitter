// Prior-persistence evidence: pure shaping + formatting helpers (V3.9 item 8).
//
// Backs the Prior Evidence tab: the /priors age readout, the saved-snapshot
// history, the per-(day, expiry) ATM innovation series ("prior vs market
// distance over time") and the GRAPH residual decay curve phi(dt) = 2^(-dt/H).
//
// THE DOCTRINE (backend volfit/api/filter_mode.py §6.3 split): the Kalman
// filter is a temporal prior on the OBSERVED latent state; the graph residual
// store is memory of the UNOBSERVED functional gap. The decay curve here is
// the GRAPH residual's — the two must never read as one thing in the UI.

/** One ticker row of GET /priors (the saved/active prior status). */
export interface PriorEvidenceStatus {
  ticker: string;
  dataTs: string | null;
  savedTs: string | null;
  asOfLabel: string | null;
  nodeCount: number;
  hasLvSurface: boolean;
  activeSource: string | null;
  activeDataTs: string | null;
  /** Day-resolution ages beside the timestamps (backend _prior_age_days
   *  convention); optional so older backends still type-check. */
  ageDays?: number | null;
  activeAgeDays?: number | null;
}

/** One saved snapshot's metadata (GET /priors/history/{ticker}). */
export interface PriorHistoryEntry {
  dataTs: string;
  savedTs: string;
  nodeCount: number;
  asOfLabel: string;
}

/** One persisted ATM innovation (GET /graph/innovations/{ticker}). */
export interface InnovationPoint {
  day: string; // as-of ISO date it was recorded on
  expiry: string;
  innovationBp: number; // (calibrated − transported prior) ATM vol, bp (signed)
}

/** One per-expiry |innovation| series aligned to the shared day axis. */
export interface InnovationSeries {
  expiry: string;
  /** |innovationBp| per day index; null where the expiry has no record. */
  values: (number | null)[];
}

export interface ShapedInnovations {
  /** Sorted unique as-of days (the shared x axis). */
  days: string[];
  /** One series per expiry, expiry-sorted. */
  series: InnovationSeries[];
  /** Largest |innovationBp| across every point (0 when empty). */
  maxAbsBp: number;
}

/** Group the flat (day, expiry, bp) rows into per-expiry |bp| series over the
 *  sorted day axis — the chart's "does the prior persist?" shape. */
export function shapeInnovationSeries(points: InnovationPoint[]): ShapedInnovations {
  const days = Array.from(new Set(points.map((p) => p.day))).sort();
  const dayIndex = new Map(days.map((d, i) => [d, i]));
  const expiries = Array.from(new Set(points.map((p) => p.expiry))).sort();
  const series = expiries.map((expiry) => ({
    expiry,
    values: days.map<number | null>(() => null),
  }));
  const byExpiry = new Map(series.map((s) => [s.expiry, s]));
  let maxAbsBp = 0;
  for (const p of points) {
    const abs = Math.abs(p.innovationBp);
    byExpiry.get(p.expiry)!.values[dayIndex.get(p.day)!] = abs;
    if (abs > maxAbsBp) maxAbsBp = abs;
  }
  return { days, series, maxAbsBp };
}

/** phi(dt) = 2^(−dt/H); H = null is the random walk (fully persistent, phi ≡ 1) —
 *  the same semantics as the layered solve / dynamicTimeline.replayAB. */
export function decayAt(halfLifeDays: number | null, dt: number): number {
  if (halfLifeDays === null || halfLifeDays <= 0) return 1;
  return Math.pow(2, -dt / halfLifeDays);
}

export interface DecayPoint {
  dt: number; // days since the residual was learned
  phi: number; // surviving fraction of the stored residual
}

/** Sample the residual decay curve on [0, horizon]. The default horizon shows
 *  four half-lives (φ down to 1/16), or 10 days for the random walk. */
export function decayCurve(
  halfLifeDays: number | null,
  horizonDays?: number,
  n = 65,
): DecayPoint[] {
  const horizon =
    horizonDays ??
    (halfLifeDays === null || halfLifeDays <= 0 ? 10 : Math.max(4 * halfLifeDays, 1));
  const count = Math.max(2, Math.floor(n));
  const out: DecayPoint[] = [];
  for (let i = 0; i < count; i++) {
    const dt = (horizon * i) / (count - 1);
    out.push({ dt, phi: decayAt(halfLifeDays, dt) });
  }
  return out;
}

/** Fractional age in days of a backend UTC-naive ISO timestamp; null when
 *  missing/unparseable. Backend timestamps carry no zone marker but ARE UTC,
 *  so a bare stamp is parsed as UTC (never the browser's local zone). */
export function ageDaysFromTs(
  ts: string | null | undefined,
  nowMs: number,
): number | null {
  if (!ts) return null;
  const iso = /(Z|[+-]\d\d:?\d\d)$/.test(ts) ? ts : `${ts}Z`;
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return null;
  return Math.max(0, (nowMs - ms) / 86_400_000);
}

/** Human age: days when ≥ 1 day, hours below that, "—" when unknown. */
export function formatAge(days: number | null | undefined): string {
  if (days === null || days === undefined || !Number.isFinite(days)) return "—";
  if (days >= 1) return `${days.toFixed(1)} d`;
  return `${(days * 24).toFixed(1)} h`;
}

/** Short source-tier label for the provenance chips/columns. */
export function sourceLabel(source: string | null | undefined): string {
  switch (source) {
    case "active_transported": return "active";
    case "nearest_expiry_transported": return "nearest";
    case "today_bootstrap": return "bootstrap";
    case "flat_atm": return "flat";
    case "saved": return "saved";
    case "15min": return "15min";
    case "close": return "close";
    case "none": case null: case undefined: return "none";
    default: return source;
  }
}
