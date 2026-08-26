// Solve cinematics of the Graph lens, extracted from GraphViewer (UI SHELL v2
// file-size policy): the post-Run reveal staged by REAL BFS hop from the lit
// set over the real edge topology (honest influence distance, never solver
// chronology), the wave epoch that restarts it when a NEW result set lands,
// and the attribution particles (calibrations source only — the dark nodes
// the propagation moved most).
import { useEffect, useMemo, useState } from "react";
import { nodeKey } from "./useGraph";
import type { GraphNodeBase } from "./useGraph";
import type { ExtrapolateBody, ExtrapolateNode } from "./useGraphExtrapolation";
import { useWaveTimeline } from "./useWaveTimeline";
import { useAttributionParticles } from "./useAttributionParticles";
import type { ParticleSpec } from "./useAttributionParticles";
import { waveHops } from "../lib/graphWave";
import type { LayoutEdgeIn } from "../lib/graphLayout";
import type { WaveState } from "../components/GraphNetworkChart.helpers";

export interface GraphCinematics {
  /** Canvas wave state (hop of each node, revealed hop, animation flag, skip). */
  wave: WaveState;
  /** Bumped on every new result set (restarts the reveal + particle timer). */
  waveEpoch: number;
  particles: ParticleSpec[];
}

export function useGraphCinematics(
  chartNodes: GraphNodeBase[] | null,
  edges: LayoutEdgeIn[],
  chartLit: Record<string, number>,
  /** The solved nodes (state identity — bumps the epoch when it changes). */
  solvedNodes: ExtrapolateNode[] | null,
  manual: boolean,
  body: ExtrapolateBody,
): GraphCinematics {
  const litKeySet = useMemo(() => new Set(Object.keys(chartLit)), [chartLit]);
  const hops = useMemo(
    () => waveHops((chartNodes ?? []).map((n) => nodeKey(n.ticker, n.expiry)), edges, litKeySet),
    [chartNodes, edges, litKeySet],
  );
  // Wave epoch: keyed off the underlying state identity (solvedNodes) —
  // extra.results is rebuilt every render, so watching it would loop.
  const [waveEpoch, setWaveEpoch] = useState(0);
  useEffect(() => {
    if (solvedNodes !== null) setWaveEpoch((v) => v + 1);
  }, [solvedNodes]);
  const timeline = useWaveTimeline(waveEpoch, hops.maxHop);

  // Attribution candidates = the dark nodes the propagation moved most.
  const particleCandidates = useMemo(
    () =>
      manual || solvedNodes === null
        ? []
        : solvedNodes
            .filter((n) => !n.lit)
            .sort((a, b) => Math.abs(b.shiftBp) - Math.abs(a.shiftBp))
            .slice(0, 5)
            .map((n) => ({ ticker: n.ticker, expiry: n.expiry, shiftBp: n.shiftBp })),
    [manual, solvedNodes],
  );
  const particles = useAttributionParticles(!manual && solvedNodes !== null, particleCandidates, body);

  return {
    wave: {
      hopOf: hops.hopOf,
      revealedHop: timeline.revealedHop,
      animating: timeline.animating,
      skip: timeline.skip,
    },
    waveEpoch,
    particles,
  };
}
