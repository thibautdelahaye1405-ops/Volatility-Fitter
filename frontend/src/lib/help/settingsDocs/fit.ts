// Help Center settings corpus — FitSettings entry point (HELP CENTER ARC, H2).
// The 25 FitSettings fields are documented in two themed modules so each stays
// under the 400-line policy: fit_models.ts (model-family knobs — Options ▸
// Parametric) and fit_objective.ts (objective knobs — Options ▸ Calibration).
// This module concatenates them into the single FIT_DOCS list the settings
// page renders and settingsDocs.test.ts locks complete against
// settingsSchema.json.
import type { SettingDoc } from "../types";
import { FIT_MODEL_DOCS } from "./fit_models";
import { FIT_OBJECTIVE_DOCS } from "./fit_objective";

export const FIT_DOCS: SettingDoc[] = [...FIT_MODEL_DOCS, ...FIT_OBJECTIVE_DOCS];
