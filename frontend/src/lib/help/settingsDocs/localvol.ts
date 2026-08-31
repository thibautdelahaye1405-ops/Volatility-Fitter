// Help Center settings corpus — Local-Vol section entry point
// (SettingsSectionId "opt-localvol"). The 18 LV-related OptionsSettings fields
// are documented in two themed modules so each stays under the 400-line
// policy: localvol_grid.ts (workspace gate + vertex grid) and
// localvol_wings_solver.ts (wing / front regularizers, lattice, solver). This
// module concatenates them into the single LOCALVOL_DOCS list the settings
// page renders and settingsDocs.test.ts locks complete against
// settingsSchema.json.
import type { SettingDoc } from "../types";
import { LV_GRID_DOCS } from "./localvol_grid";
import { LV_WINGS_SOLVER_DOCS } from "./localvol_wings_solver";

export const LOCALVOL_DOCS: SettingDoc[] = [...LV_GRID_DOCS, ...LV_WINGS_SOLVER_DOCS];
