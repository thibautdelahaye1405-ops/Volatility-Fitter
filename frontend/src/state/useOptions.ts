// Load / edit the global Options settings (GET/PUT /settings/options).
//
// These are the app-wide meta toggles, engine defaults and the editable
// calendar penalty strength (ROADMAP Phase 10) — distinct from the live
// FitSettings the HyperparamPanel edits. The Options workspace holds a draft,
// PUTs it on Apply, and the caller refits the current smile afterwards.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

/** Spot-vol dynamics regime default (mirror of the backend literal).
 *  "custom" applies the explicit ``ssr`` value; the others are named regimes. */
export type DynamicsRegime =
  | "sticky_moneyness"
  | "sticky_strike"
  | "sticky_local_vol"
  | "sticky_local_vol_grid"
  | "custom";
/** Spot price mode (stubbed this phase). */
export type SpotMode = "realtime" | "static";

/** Mirror of the backend OptionsSettings schema (volfit/api/schemas.py). */
export interface OptionsSettings {
  enforceCalendar: boolean;
  eventsEnabled: boolean;
  varSwapEnabled: boolean;
  autoLoadPrior: boolean;
  gridXNodes: number;
  gridTNodes: number;
  gridRegLambda: number;
  calendarWeight: number;
  dynamicsRegime: DynamicsRegime;
  ssr: number;
  autoCalibrate: boolean;
  spotMode: SpotMode;
}

export const OPTIONS_DEFAULTS: OptionsSettings = {
  enforceCalendar: true,
  eventsEnabled: true,
  varSwapEnabled: true,
  autoLoadPrior: false,
  gridXNodes: 7,
  gridTNodes: 4,
  gridRegLambda: 1e-2,
  calendarWeight: 1e6,
  dynamicsRegime: "sticky_strike",
  ssr: 2.0,
  autoCalibrate: true,
  spotMode: "static",
};

export interface UseOptionsResult {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  dirty: boolean;
  busy: boolean;
  flash: boolean;
  apply: () => void;
  /** True until the backend's current settings have loaded. */
  loaded: boolean;
}

export function useOptions(enabled: boolean, onApplied: () => void): UseOptionsResult {
  const [saved, setSaved] = useState<OptionsSettings>(OPTIONS_DEFAULTS);
  const [draft, setDraft] = useState<OptionsSettings>(OPTIONS_DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    api
      .get<OptionsSettings>("/settings/options", { signal: controller.signal })
      .then((s) => {
        setSaved(s);
        setDraft(s);
        setLoaded(true);
      })
      .catch(() => {
        /* keep defaults; the Apply PUT will surface real failures */
      });
    return () => controller.abort();
  }, [enabled]);

  const patch = useCallback(
    (p: Partial<OptionsSettings>) => setDraft((d) => ({ ...d, ...p })),
    [],
  );

  const dirty = (Object.keys(draft) as (keyof OptionsSettings)[]).some(
    (k) => draft[k] !== saved[k],
  );

  const apply = useCallback(() => {
    if (!dirty || busy) return;
    setBusy(true);
    api
      .put<OptionsSettings>("/settings/options", { body: draft })
      .then((s) => {
        setSaved(s);
        setDraft(s);
        setFlash(true);
        setTimeout(() => setFlash(false), 1200);
        onApplied();
      })
      .catch(() => {
        /* leave the draft dirty so the user can retry */
      })
      .finally(() => setBusy(false));
  }, [dirty, busy, draft, onApplied]);

  return { draft, patch, dirty, busy, flash, apply, loaded };
}
