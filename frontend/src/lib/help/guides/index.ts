// Guides index (HELP CENTER ARC, H1): the ordered list of guide pages, the
// id lookup, and the lens → guide map F1 uses. The pages themselves live in
// the sibling modules (≤ 400 lines each): workbench.ts (getting-started,
// workbench, files), universe.ts (universe, data-sources, workflow),
// lenses_a.ts (graph, forwards), lenses_b.ts (parametric, localvol, quality),
// options.ts (options, priors, filter). PURE DATA — vitest-testable.
import type { Activity } from "../../../state/workbenchPersist";
import type { GuideId, GuidePage } from "../types";
import { FILES, GETTING_STARTED, WORKBENCH } from "./workbench";
import { DATA_SOURCES, UNIVERSE, WORKFLOW } from "./universe";
import { FORWARDS, GRAPH } from "./lenses_a";
import { LOCALVOL, PARAMETRIC, QUALITY } from "./lenses_b";
import { FILTER, OPTIONS, PRIORS } from "./options";

/** The guides, in the order the Guides page lists them. */
export const GUIDES: GuidePage[] = [
  GETTING_STARTED,
  WORKBENCH,
  UNIVERSE,
  DATA_SOURCES,
  WORKFLOW,
  GRAPH,
  FORWARDS,
  PARAMETRIC,
  LOCALVOL,
  QUALITY,
  OPTIONS,
  PRIORS,
  FILTER,
  FILES,
];

const BY_ID: Record<string, GuidePage> = Object.fromEntries(GUIDES.map((g) => [g.id, g]));

/** Guide lookup (throws on an unknown id — every GuideId has a page). */
export function guide(id: GuideId): GuidePage {
  const g = BY_ID[id];
  if (!g) throw new Error(`unknown guide ${id}`);
  return g;
}

/** Lens → guide (every lens has exactly one guide; the ids coincide today). */
const LENS_GUIDE: Record<Activity, GuideId> = {
  graph: "graph",
  forwards: "forwards",
  parametric: "parametric",
  localvol: "localvol",
  quality: "quality",
};

/** The guide F1 opens for the active lens. */
export function guideForLens(lens: Activity): GuideId {
  return LENS_GUIDE[lens];
}
