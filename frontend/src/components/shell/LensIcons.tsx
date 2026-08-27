// Custom lens icons for the activity bar (UI SHELL v2 wave 2). Drawn to say
// what the lens IS rather than a generic glyph: a real graph (a node with four
// edges, plus outer links), a smile-shaped curve with quote ticks, an
// isometric 3D local-vol surface, and a list of items for the universe.
// Same 24-box / currentColor / 1.6 stroke conventions as lucide so they sit
// next to TrendingUp (Forwards) and Gauge (Quality) without a seam.
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Svg({ size = 21, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      {...rest}
    >
      {children}
    </svg>
  );
}

/** Graph: a centre node joined to four neighbours, two of which also link. */
export function GraphIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <line x1="12" y1="12" x2="5" y2="6" />
      <line x1="12" y1="12" x2="19" y2="6" />
      <line x1="12" y1="12" x2="5.5" y2="18.5" />
      <line x1="12" y1="12" x2="18.5" y2="18.5" />
      <line x1="5" y1="6" x2="19" y2="6" />
      <line x1="5.5" y1="18.5" x2="18.5" y2="18.5" strokeDasharray="2 2" />
      <circle cx="12" cy="12" r="2.3" fill="currentColor" stroke="none" />
      <circle cx="5" cy="6" r="1.8" />
      <circle cx="19" cy="6" r="1.8" />
      <circle cx="5.5" cy="18.5" r="1.8" />
      <circle cx="18.5" cy="18.5" r="1.8" />
    </Svg>
  );
}

/** Parametric smile: a skewed convex curve over a light axis, with quote ticks. */
export function SmileIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <line x1="3" y1="19" x2="21" y2="19" strokeOpacity="0.35" />
      <line x1="12" y1="5" x2="12" y2="19" strokeOpacity="0.2" strokeDasharray="1.5 2" />
      <path d="M3 5.5 C7 12.5, 10.5 15.5, 13.5 15.2 C16.5 14.9, 19 12.5, 21 9" strokeWidth={1.9} />
      <line x1="6" y1="8.2" x2="6" y2="11.2" strokeWidth={1.2} />
      <line x1="9.5" y1="12.2" x2="9.5" y2="15" strokeWidth={1.2} />
      <line x1="16.5" y1="12" x2="16.5" y2="14.8" strokeWidth={1.2} />
      <line x1="19.5" y1="9.2" x2="19.5" y2="12.2" strokeWidth={1.2} />
    </Svg>
  );
}

/** Local vol: an isometric surface mesh with a smile-shaped ridge. */
export function LocalVolIcon(props: IconProps) {
  return (
    <Svg {...props}>
      {/* base parallelogram */}
      <path d="M3 15 L10 19 L21 14 L14 10 Z" strokeOpacity="0.45" />
      {/* three surface curves receding in depth */}
      <path d="M3 15 C5.5 9.5, 8.5 8.5, 11 12.5 C12.5 14.5, 13 14.8, 14 10" />
      <path d="M6.5 17 C9 11.5, 12 10.5, 14.5 14.5 C16 16.5, 16.5 16.8, 17.5 12" strokeOpacity="0.7" />
      <path d="M10 19 C12.5 13.5, 15.5 12.5, 18 16.5 C19.5 18.5, 20 18.8, 21 14" />
      {/* cross rungs */}
      <line x1="3" y1="15" x2="10" y2="19" strokeOpacity="0.45" />
      <line x1="14" y1="10" x2="21" y2="14" strokeOpacity="0.45" />
    </Svg>
  );
}

/** Universe: a list of items (ticker rows with bullets). */
export function UniverseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="5" cy="6" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="5" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="5" cy="18" r="1.4" fill="currentColor" stroke="none" />
      <line x1="9" y1="6" x2="20" y2="6" />
      <line x1="9" y1="12" x2="17" y2="12" />
      <line x1="9" y1="18" x2="19" y2="18" />
    </Svg>
  );
}
