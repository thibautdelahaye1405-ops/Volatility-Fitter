// Attribution particles for the graph solve cinematics. HONEST numbers only:
// each particle is one real (lit source -> extrapolated target) attribution
// entry — gain × innovation, the exact per-lit-node decomposition the backend
// already serves on GET /graph/extrapolate/nodes/{ticker}/{expiry} — sized by
// its share of the largest kept |contribution|. Advisory garnish: any fetch
// failure simply yields no particles, never an error.
import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { nodeKey } from "./useGraph";
import type { GraphNodeSmile } from "./useGraphNodeSmile";

/** Candidate target node for a particle fan-in (caller pre-sorts by |shift|). */
export interface ParticleCandidate {
  ticker: string;
  expiry: string;
  shiftBp: number;
}

/** One particle: a real contribution path from a lit source to a target. */
export interface ParticleSpec {
  fromKey: string; // lit source node key `${ticker}|${expiry}`
  toKey: string; // extrapolated target node key
  weight: number; // |contributionBp| / max kept |contributionBp|, in (0, 1]
  positive: boolean; // sign of the contribution (vols marked up vs down)
}

/** Targets per show / attribution entries kept per target / kept-entry floor. */
const MAX_TARGETS = 5;
const TOP_PER_TARGET = 3;
const MIN_ABS_BP = 0.1;

/**
 * When `active`, fetch the attribution of up to MAX_TARGETS candidate nodes
 * (same endpoint + query-param knobs as useGraphNodeSmile) and distil the top
 * contribution paths into particle specs. Inactive or failed -> [].
 */
export function useAttributionParticles(
  active: boolean,
  candidates: ParticleCandidate[],
  body: Record<string, string | number | boolean>,
): ParticleSpec[] {
  const [particles, setParticles] = useState<ParticleSpec[]>([]);

  // Stable keys so unchanged inputs don't refetch every render (same pattern
  // as useGraphNodeSmile); refs carry the live values into the effect.
  const bodyKey = JSON.stringify(body);
  const candKey = JSON.stringify(candidates);
  const bodyRef = useRef(body);
  bodyRef.current = body;
  const candRef = useRef(candidates);
  candRef.current = candidates;

  useEffect(() => {
    if (!active || candRef.current.length === 0) {
      setParticles([]);
      return;
    }
    const picked = candRef.current.slice(0, MAX_TARGETS);
    const controller = new AbortController();
    Promise.all(
      picked.map((c) =>
        api.get<GraphNodeSmile>(
          `/graph/extrapolate/nodes/${c.ticker}/${encodeURIComponent(c.expiry)}`,
          { params: bodyRef.current, signal: controller.signal },
        ),
      ),
    )
      .then((nodes) => {
        // Keep each target's strongest attribution entries above the floor.
        const kept: { fromKey: string; toKey: string; bp: number }[] = [];
        for (const node of nodes) {
          const top = [...node.attribution]
            .filter((a) => Math.abs(a.contributionBp) >= MIN_ABS_BP)
            .sort((a, b) => Math.abs(b.contributionBp) - Math.abs(a.contributionBp))
            .slice(0, TOP_PER_TARGET);
          for (const a of top) {
            kept.push({
              fromKey: nodeKey(a.ticker, a.expiry),
              toKey: nodeKey(node.ticker, node.expiry),
              bp: a.contributionBp,
            });
          }
        }
        const maxAbs = kept.reduce((m, k) => Math.max(m, Math.abs(k.bp)), 0);
        setParticles(
          maxAbs > 0
            ? kept.map((k) => ({
                fromKey: k.fromKey,
                toKey: k.toKey,
                weight: Math.abs(k.bp) / maxAbs,
                positive: k.bp >= 0,
              }))
            : [],
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setParticles([]);
      });
    return () => controller.abort();
  }, [active, bodyKey, candKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return particles;
}
