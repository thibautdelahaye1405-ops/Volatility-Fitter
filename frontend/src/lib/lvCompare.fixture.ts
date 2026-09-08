// A small, self-consistent LvCompareResponse for the Compare tab's unit and
// component tests (lib/lvCompare.test.ts, components/localvol/LvCompare*.test.tsx):
// a 3 × 4 lattice, two expiries, the affine sheet on the same lattice with
// its difference, clean counters. Pure data — no React, no DOM.
import type { LvCompareResponse, LvCompareSmile } from "../state/useLvCompare";

const T_NODES = [0, 0.1, 0.5];
const X_NODES = [0.8, 0.9, 1.0, 1.1];
const TWIN = [
  [0.22, 0.2, 0.18, 0.19],
  [0.24, 0.21, 0.19, 0.2],
  [0.26, 0.23, 0.21, 0.22],
];
const AFFINE = [
  [0.2, 0.2, 0.19, 0.19],
  [0.23, 0.21, 0.2, 0.2],
  [0.25, 0.22, 0.21, 0.21],
];

const pts = (vols: number[]) => vols.map((vol, i) => ({ k: -0.2 + 0.1 * i, vol }));

function smile(expiry: string, t: number, rt: number): LvCompareSmile {
  return {
    expiry, t, tau: t, forward: 100,
    twin: pts([0.21, 0.2, 0.19, 0.2, 0.21]),
    twinExt: pts([0.22, 0.21, 0.2, 0.19, 0.2, 0.21, 0.22]),
    parametric: pts([0.21, 0.2, 0.19, 0.2, 0.21]),
    quotes: [
      { k: -0.1, bid: 0.199, ask: 0.203, mid: 0.201, index: 0, excluded: false, amended: false },
      { k: 0.1, bid: 0.198, ask: 0.202, mid: 0.2, index: 1, excluded: false, amended: false },
    ],
    twinScore: { rmsError: 0.0025, maxBp: 60, rmsBp: 25, convergedBp: 18 },
    parametricScore: { rmsError: 0.0005, maxBp: 12, rmsBp: 5, convergedBp: null },
    affineScore: { rmsError: 0.0001, maxBp: 3, rmsBp: null, convergedBp: 40 },
    roundTripBp: rt, roundTripMaxBp: rt * 3, roundTripInOpBp: rt * 2,
  };
}

export function lvCompareFixture(overrides: Partial<LvCompareResponse> = {}): LvCompareResponse {
  return {
    ticker: "ALPHA",
    tInterp: "smooth",
    tails: "model",
    tNodes: T_NODES,
    xNodes: X_NODES,
    localVolTwin: TWIN,
    rawLocalVariance: TWIN.map((row) => row.map((v) => v * v)),
    differentiated: [true, true, true, true],
    counters: { butterfly: [0, 0, 0], calendar: [0, 0, 0], floored: [0, 0, 0], capped: [0, 0, 0], clean: true },
    varLo: 0.0025,
    varHi: 4,
    localVolAffine: AFFINE,
    diffLocalVol: TWIN.map((row, i) => row.map((v, j) => v - AFFINE[i][j])),
    hasAffine: true,
    affineStale: false,
    affineLatticeMatches: true,
    smiles: [smile("2026-07-10", 0.1, 30), smile("2026-12-10", 0.5, 8)],
    skippedExpiries: [],
    twinScore: { rmsError: 0.0065, maxBp: 276, rmsBp: 65, convergedBp: 25.4 },
    parametricScore: { rmsError: 0.0005, maxBp: 16, rmsBp: 5, convergedBp: null },
    affineScore: { rmsError: 0.00009, maxBp: 2.7, rmsBp: 0.9, convergedBp: 51.7 },
    roundTripBp: 24.4,
    roundTripMaxBp: 96.4,
    message: "smooth twin on 3 x 4 vertices",
    ...overrides,
  };
}
