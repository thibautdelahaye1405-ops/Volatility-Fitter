// Attribution-particle overlay for the graph solve cinematics: small dots
// travelling the top REAL contribution paths (gain × innovation entries the
// backend attributes per node) from their lit source to the extrapolated
// target — emerald for a positive contribution, rose for a negative one.
// Rendered in WORLD coordinates inside the chart's pan/zoom group; a state
// timer hides the whole show ~2.8 s after mount / a new propagation epoch.
import { useEffect, useState } from "react";
import type { ParticleSpec } from "../state/useAttributionParticles";

const EMERALD_400 = "#34d399";
const ROSE_400 = "#fb7185";
/** Show length: the last particle starts 4·120 ms in and runs two 0.9 s legs. */
const SHOW_MS = 2800;

interface GraphWaveOverlayProps {
  particles: ParticleSpec[];
  /** World-coordinate node positions (the chart layout's nodePos). */
  nodePos: Map<string, { x: number; y: number }>;
  /** Propagation counter — a new epoch restarts the show from scratch. */
  epoch: number;
}

export default function GraphWaveOverlay({
  particles,
  nodePos,
  epoch,
}: GraphWaveOverlayProps) {
  // Self-hiding: visible from mount / each new epoch until the show ends.
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    setVisible(true);
    const timer = setTimeout(() => setVisible(false), SHOW_MS);
    return () => clearTimeout(timer);
  }, [epoch]);

  if (!visible || particles.length === 0) return null;
  return (
    <g pointerEvents="none">
      {particles.map((p, i) => {
        const from = nodePos.get(p.fromKey);
        const to = nodePos.get(p.toKey);
        if (from === undefined || to === undefined) return null;
        const color = p.positive ? EMERALD_400 : ROSE_400;
        return (
          // Keyed by epoch: recreating the elements restarts the SMIL clocks.
          <g key={`${epoch}-${i}`}>
            {/* Faint guiding line while the show is visible */}
            <line
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke={color} strokeWidth={1} opacity={0.12}
            />
            {/* The particle sits at its source until its staggered start,
                then travels the relative straight path source -> target. */}
            <circle
              cx={from.x} cy={from.y}
              r={2.5 + 3 * p.weight}
              fill={color}
              opacity={0.9}
            >
              <animateMotion
                path={`M 0 0 L ${to.x - from.x} ${to.y - from.y}`}
                dur="0.9s"
                begin={`${(i * 0.12).toFixed(2)}s`}
                repeatCount={2}
              />
            </circle>
          </g>
        );
      })}
    </g>
  );
}
