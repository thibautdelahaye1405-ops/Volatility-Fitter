// Help Center settings corpus — Prior persistence section entry point
// (SettingsSectionId "opt-prior"). The 18 prior-related OptionsSettings fields
// are documented in two themed modules so each stays under the 400-line
// policy: priors_operators.ts (modes, strike anchor, quote operators and the
// activation gate) and priors_tails.ts (smile factors and the tail carriers).
// This module concatenates them into the single PRIOR_DOCS list the settings
// page renders and settingsDocs.test.ts locks complete against
// settingsSchema.json.
import type { SettingDoc } from "../types";
import { PRIOR_OPERATOR_DOCS } from "./priors_operators";
import { PRIOR_TAIL_DOCS } from "./priors_tails";

export const PRIOR_DOCS: SettingDoc[] = [...PRIOR_OPERATOR_DOCS, ...PRIOR_TAIL_DOCS];
