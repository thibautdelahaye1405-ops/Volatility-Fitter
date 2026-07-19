// Ticker-pod force layout for the smile-universe graph. Pure math — no React,
// no DOM, no chart deps.
//
// Design: each ticker is a "pod" — its expiries stacked as a vertical calendar
// spine (ascending year-fraction t, so term structure reads top → bottom); pod
// centers are positioned by a small deterministic force simulation where
// aggregated cross-ticker edge weights act as springs (heavily-connected
// tickers pull together, e.g. indices end up central). The universe tops out
// around ~30 tickers, i.e. ~30 bodies, so a hand-rolled O(n²·iters) simulation
// is trivial — no d3 dependency.
//
// Determinism: the only randomness is a mulberry32 PRNG seeded by a hash of
// the ticker list (no Math.random, no Date), so identical inputs give
// byte-identical output.

export interface LayoutNode { ticker: string; expiry: string; t: number }
export interface LayoutEdgeIn { fromTicker: string; fromExpiry: string; toTicker: string; toExpiry: string; weight: number }
export interface PlacedNode { ticker: string; expiry: string; t: number; x: number; y: number }
export interface PodLayout { ticker: string; cx: number; cy: number; radius: number; nodes: PlacedNode[] }
export interface BundleEdge {
  fromTicker: string; toTicker: string;   // unordered pair, fromTicker < toTicker lexicographically
  totalWeight: number;                     // sum of |weight| across all individual edges both directions
  count: number;                           // number of individual cross edges in the bundle
  bidirectional: boolean;                  // true when edges exist in both directions
  // Direction flags for honest arrowheads (engine truth: an a→b edge means b
  // INFORMS a, i.e. information flows INTO the a/x1 end of the bundle).
  hasAb: boolean;                          // an edge stored as (a → b) exists
  hasBa: boolean;                          // an edge stored as (b → a) exists
  x1: number; y1: number; x2: number; y2: number;  // pod-boundary anchor points (on the circles, along the center line)
}
export interface CalendarEdge { ticker: string; fromExpiry: string; toExpiry: string; weight: number; x1: number; y1: number; x2: number; y2: number }
export interface PairEdgeDetail { fromTicker: string; fromExpiry: string; toTicker: string; toExpiry: string; weight: number; x1: number; y1: number; x2: number; y2: number }
export interface GraphLayout {
  pods: PodLayout[];
  nodePos: Map<string, { x: number; y: number }>;   // key `${ticker}|${expiry}`
  bundles: BundleEdge[];
  calendar: CalendarEdge[];
  width: number;
  height: number;
  pairDetails: (tickerA: string, tickerB: string) => PairEdgeDetail[];  // individual cross edges between two pods, endpoints at node positions, both directions
}

/* ------------------------------- constants ------------------------------- */

/** Vertical gap between consecutive spine nodes (px). */
const SPINE_DY = 36;
/** Padding from the outermost spine node to the pod circle. */
const POD_PAD = 20;
/** Smallest pod circle (a 1–2 expiry ticker still reads as a pod). */
const POD_MIN_R = 30;
/** Whitespace around the final bounding box. */
const FRAME_MARGIN = 40;
/** Canvas side for the degenerate empty universe. */
const EMPTY_SIZE = 200;

/** Force-sim iteration count; steps shrink linearly to zero over the run. */
const ITERATIONS = 300;
/** Pairwise repulsion magnitude ~ REPULSION/d²: at the typical resting
 *  distance (~250px) this is <1px/step, so it only matters up close. */
const REPULSION = 40000;
/** Per-step repulsion cap so near-coincident pods don't explode. */
const REPULSION_CAP = 60;
/** Spring stiffness of the heaviest bundle (lighter bundles scale down). */
const SPRING_K = 0.02;
/** Comfortable circle-to-circle gap springs relax toward (restLength = rA+rB+slack). */
const SPRING_SLACK = 90;
/** Weak pull toward the origin — keeps disconnected components from drifting apart. */
const CENTER_PULL = 0.002;
/** Hard minimum circle-to-circle gap enforced after the simulation. */
const POD_GAP = 12;
/** Max relaxation passes of the hard overlap resolver (early-exits when clean). */
const SEPARATION_PASSES = 50;
/** Starting ring radius grows with sqrt(nPods) so pod density stays roughly constant. */
const RING_R = 90;

/* ------------------------------ seeded PRNG ------------------------------ */

/** FNV-1a 32-bit string hash: deterministic PRNG seed from the ticker list. */
function hashString(s: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

/** mulberry32: tiny deterministic PRNG, uniform in [0, 1). */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------- geometry -------------------------------- */

/** Unit vector from pod i to pod j plus the distance. Coincident centers get
 *  a deterministic pair-derived direction so ties break identically every run. */
function separationDir(
  px: Float64Array, py: Float64Array, i: number, j: number,
): readonly [number, number, number] {
  const ex = px[j] - px[i];
  const ey = py[j] - py[i];
  const d = Math.hypot(ex, ey);
  if (d < 1e-9) {
    const a = ((i * 37 + j * 101) % 360) * (Math.PI / 180);
    return [Math.cos(a), Math.sin(a), 1e-9];
  }
  return [ex / d, ey / d, d];
}

/* ----------------------------- main algorithm ---------------------------- */

/** Internal per-pair aggregate of the cross-ticker edges. */
interface PairAgg {
  a: string; b: string;            // a < b lexicographically
  totalWeight: number;
  count: number;
  ab: boolean; ba: boolean;        // direction flags (a→b seen / b→a seen)
  details: LayoutEdgeIn[];         // individual edges, input order
}

export function computeGraphLayout(nodes: LayoutNode[], edges: LayoutEdgeIn[]): GraphLayout {
  // Degenerate empty universe: a fixed small canvas, nothing to place.
  if (nodes.length === 0) {
    return {
      pods: [], nodePos: new Map(), bundles: [], calendar: [],
      width: EMPTY_SIZE, height: EMPTY_SIZE,
      pairDetails: () => [],
    };
  }

  // ---- pods: group by ticker (first-appearance order), spine sorted by t --
  const tickers: string[] = [];
  const byTicker = new Map<string, LayoutNode[]>();
  for (const n of nodes) {
    let list = byTicker.get(n.ticker);
    if (list === undefined) {
      list = [];
      byTicker.set(n.ticker, list);
      tickers.push(n.ticker);
    }
    list.push(n);
  }
  const spines = tickers.map((t) => [...(byTicker.get(t) ?? [])].sort((a, b) => a.t - b.t));
  const radii = spines.map((s) => Math.max(POD_MIN_R, ((s.length - 1) * SPINE_DY) / 2 + POD_PAD));
  const podIndex = new Map<string, number>(tickers.map((t, i) => [t, i]));

  // Drop edges whose endpoints aren't in the node universe (defensive: the
  // edge store and node list can momentarily disagree during a universe edit).
  const nodeSet = new Set(nodes.map((n) => `${n.ticker}|${n.expiry}`));
  const valid = edges.filter(
    (e) => nodeSet.has(`${e.fromTicker}|${e.fromExpiry}`) && nodeSet.has(`${e.toTicker}|${e.toExpiry}`),
  );

  // ---- cross-ticker aggregation: one bundle per unordered ticker pair -----
  const pairs = new Map<string, PairAgg>();
  for (const e of valid) {
    if (e.fromTicker === e.toTicker) continue;
    const flip = e.fromTicker > e.toTicker;
    const a = flip ? e.toTicker : e.fromTicker;
    const b = flip ? e.fromTicker : e.toTicker;
    const key = `${a}|${b}`;
    let agg = pairs.get(key);
    if (agg === undefined) {
      agg = { a, b, totalWeight: 0, count: 0, ab: false, ba: false, details: [] };
      pairs.set(key, agg);
    }
    agg.totalWeight += Math.abs(e.weight);
    agg.count += 1;
    if (flip) agg.ba = true; else agg.ab = true;
    agg.details.push(e);
  }

  // ---- calendar aggregation: per adjacent-expiry hop of each spine --------
  // Weight per hop = max |weight| across the (up to two) directed input edges
  // on that hop; hops with no input edge keep 0 so the spine still renders as
  // a connected chain. Same-ticker edges that skip expiries don't map to a
  // spine segment and are ignored here.
  const spinePos = spines.map((s) => new Map<string, number>(s.map((n, j) => [n.expiry, j])));
  const calW = spines.map((s) => new Array<number>(Math.max(0, s.length - 1)).fill(0));
  for (const e of valid) {
    if (e.fromTicker !== e.toTicker) continue;
    const i = podIndex.get(e.fromTicker) ?? -1;
    const pf = spinePos[i].get(e.fromExpiry) ?? -1;
    const pt = spinePos[i].get(e.toExpiry) ?? -1;
    if (Math.abs(pf - pt) !== 1) continue; // adjacent hops only (incl. self-loops out)
    const seg = Math.min(pf, pt);
    calW[i][seg] = Math.max(calW[i][seg], Math.abs(e.weight));
  }

  // ---- force simulation on pod centers only -------------------------------
  const nP = tickers.length;
  const rng = mulberry32(hashString(tickers.join("|")));
  const ringR = RING_R * Math.sqrt(nP);
  const px = new Float64Array(nP);
  const py = new Float64Array(nP);
  for (let i = 0; i < nP; i++) {
    // Seeded start on a ring: even slot spacing + a seeded jitter within each
    // slot (a raw random angle could drop two pods on top of each other and
    // waste iterations separating them; this stays seeded but collision-free).
    const angle = ((i + rng()) / nP) * 2 * Math.PI;
    px[i] = ringR * Math.cos(angle);
    py[i] = ringR * Math.sin(angle);
  }

  // Spring stiffness ∝ log1p(bundled weight), normalized so the heaviest
  // bundle gets the full SPRING_K (log damps the huge index-pair weights).
  const maxTw = Math.max(0, ...[...pairs.values()].map((p) => p.totalWeight));
  const springs = [...pairs.values()].map((p) => ({
    i: podIndex.get(p.a) ?? 0,
    j: podIndex.get(p.b) ?? 0,
    k: maxTw > 0 ? SPRING_K * (Math.log1p(p.totalWeight) / Math.log1p(maxTw)) : 0,
  }));

  for (let iter = 0; iter < ITERATIONS; iter++) {
    const cool = 1 - iter / ITERATIONS; // linear cooling: full steps → zero
    const fx = new Float64Array(nP);
    const fy = new Float64Array(nP);
    // Pairwise repulsion ~ REPULSION/d² (capped): keeps unrelated pods apart.
    for (let i = 0; i < nP; i++) {
      for (let j = i + 1; j < nP; j++) {
        const [ux, uy, d] = separationDir(px, py, i, j);
        const f = Math.min(REPULSION / (d * d), REPULSION_CAP);
        fx[i] -= ux * f; fy[i] -= uy * f;
        fx[j] += ux * f; fy[j] += uy * f;
      }
    }
    // Springs relax connected pods toward a comfortable circle-to-circle gap.
    for (const s of springs) {
      const [ux, uy, d] = separationDir(px, py, s.i, s.j);
      const f = s.k * (d - (radii[s.i] + radii[s.j] + SPRING_SLACK));
      fx[s.i] += ux * f; fy[s.i] += uy * f;
      fx[s.j] -= ux * f; fy[s.j] -= uy * f;
    }
    // Weak centering + apply the cooled step.
    for (let i = 0; i < nP; i++) {
      fx[i] += CENTER_PULL * (0 - px[i]);
      fy[i] += CENTER_PULL * (0 - py[i]);
      px[i] += fx[i] * cool;
      py[i] += fy[i] * cool;
    }
  }

  // Hard-resolve residual circle overlaps: push offending pairs apart
  // symmetrically along their center line until every gap is >= POD_GAP.
  for (let pass = 0; pass < SEPARATION_PASSES; pass++) {
    let moved = false;
    for (let i = 0; i < nP; i++) {
      for (let j = i + 1; j < nP; j++) {
        const minD = radii[i] + radii[j] + POD_GAP;
        const [ux, uy, d] = separationDir(px, py, i, j);
        if (d >= minD) continue;
        const push = (minD - d) / 2;
        px[i] -= ux * push; py[i] -= uy * push;
        px[j] += ux * push; py[j] += uy * push;
        moved = true;
      }
    }
    if (!moved) break;
  }

  // ---- final framing: translate the pod bounding box to margin ------------
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < nP; i++) {
    minX = Math.min(minX, px[i] - radii[i]);
    maxX = Math.max(maxX, px[i] + radii[i]);
    minY = Math.min(minY, py[i] - radii[i]);
    maxY = Math.max(maxY, py[i] + radii[i]);
  }
  const shiftX = FRAME_MARGIN - minX;
  const shiftY = FRAME_MARGIN - minY;
  const width = maxX - minX + 2 * FRAME_MARGIN;
  const height = maxY - minY + 2 * FRAME_MARGIN;

  // ---- outputs in the final coordinate space ------------------------------
  const pods: PodLayout[] = [];
  const nodePos = new Map<string, { x: number; y: number }>();
  for (let i = 0; i < nP; i++) {
    const cx = px[i] + shiftX;
    const cy = py[i] + shiftY;
    const spine = spines[i];
    const halfH = ((spine.length - 1) * SPINE_DY) / 2;
    const placed: PlacedNode[] = spine.map((node, j) => {
      const x = cx; // spine is a vertical line through the pod center
      const y = cy - halfH + j * SPINE_DY;
      nodePos.set(`${node.ticker}|${node.expiry}`, { x, y });
      return { ticker: node.ticker, expiry: node.expiry, t: node.t, x, y };
    });
    pods.push({ ticker: tickers[i], cx, cy, radius: radii[i], nodes: placed });
  }

  /** Node position lookup; the valid-edge filter guarantees presence. */
  const posOf = (ticker: string, expiry: string): { x: number; y: number } =>
    nodePos.get(`${ticker}|${expiry}`) ?? { x: 0, y: 0 };

  // Bundles: anchor each end on the pod circle, along the center line.
  const bundles: BundleEdge[] = [...pairs.values()].map((p) => {
    const pa = pods[podIndex.get(p.a) ?? 0];
    const pb = pods[podIndex.get(p.b) ?? 0];
    const ex = pb.cx - pa.cx;
    const ey = pb.cy - pa.cy;
    const d = Math.hypot(ex, ey);
    const ux = d > 1e-9 ? ex / d : 1;
    const uy = d > 1e-9 ? ey / d : 0;
    return {
      fromTicker: p.a, toTicker: p.b,
      totalWeight: p.totalWeight, count: p.count,
      bidirectional: p.ab && p.ba,
      hasAb: p.ab, hasBa: p.ba,
      x1: pa.cx + ux * pa.radius, y1: pa.cy + uy * pa.radius,
      x2: pb.cx - ux * pb.radius, y2: pb.cy - uy * pb.radius,
    };
  });

  // Calendar: one segment per adjacent spine hop (0-weight fillers included),
  // earlier expiry first, endpoints at the node positions.
  const calendar: CalendarEdge[] = [];
  for (let i = 0; i < nP; i++) {
    const spine = spines[i];
    for (let j = 0; j + 1 < spine.length; j++) {
      const a = posOf(spine[j].ticker, spine[j].expiry);
      const b = posOf(spine[j + 1].ticker, spine[j + 1].expiry);
      calendar.push({
        ticker: tickers[i],
        fromExpiry: spine[j].expiry, toExpiry: spine[j + 1].expiry,
        weight: calW[i][j],
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      });
    }
  }

  // Drill-down: the individual cross edges of a bundle (argument order-free),
  // endpoints at node positions, both directions, input order.
  const pairDetails = (tickerA: string, tickerB: string): PairEdgeDetail[] => {
    const flip = tickerA > tickerB;
    const key = flip ? `${tickerB}|${tickerA}` : `${tickerA}|${tickerB}`;
    const agg = pairs.get(key);
    if (agg === undefined) return [];
    return agg.details.map((e) => {
      const from = posOf(e.fromTicker, e.fromExpiry);
      const to = posOf(e.toTicker, e.toExpiry);
      return {
        fromTicker: e.fromTicker, fromExpiry: e.fromExpiry,
        toTicker: e.toTicker, toExpiry: e.toExpiry,
        weight: e.weight,
        x1: from.x, y1: from.y, x2: to.x, y2: to.y,
      };
    });
  };

  return { pods, nodePos, bundles, calendar, width, height, pairDetails };
}
