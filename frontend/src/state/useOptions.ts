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
/** Spot price mode: "realtime" = backend polls live spots; "static" = on-demand. */
export type SpotMode = "realtime" | "static";
/** Options-chain fetch mode: "auto" = scheduler timer; "on_demand" = button only. */
export type OptionsFetchMode = "auto" | "on_demand";

/** Mirror of the backend OptionsSettings schema (volfit/api/schemas.py). */
export interface OptionsSettings {
  enforceCalendar: boolean;
  eventsEnabled: boolean;
  normalizeEvents: boolean;
  varSwapEnabled: boolean;
  varSwapWeightPct: number;
  autoLoadPrior: boolean;
  gridXNodes: number;
  gridTNodes: number;
  gridRegLambda: number;
  gridRegRho: number;
  calendarWeight: number;
  graphKappaScale: number;
  graphEtaScale: number;
  graphLambdaScale: number;
  graphNu: number;
  dynamicsRegime: DynamicsRegime;
  ssr: number;
  autoCalibrate: boolean;
  /** Master switch for Local-Vol (affine) calibration + the Local Vol tab. */
  localVolEnabled: boolean;
  spotMode: SpotMode;
  spotPollSeconds: number;
  optionsFetchMode: OptionsFetchMode;
  optionsFetchMinutes: number;
  /** Seconds between full refits while a live WS book streams (Massive realtime). */
  streamRefitSeconds: number;
}

export const OPTIONS_DEFAULTS: OptionsSettings = {
  enforceCalendar: true,
  eventsEnabled: true,
  normalizeEvents: false,
  varSwapEnabled: true,
  varSwapWeightPct: 10.0,
  autoLoadPrior: false,
  gridXNodes: 7,
  gridTNodes: 0,
  gridRegLambda: 1e-2,
  gridRegRho: 1.0,
  calendarWeight: 1e6,
  graphKappaScale: 1.0,
  graphEtaScale: 1.0,
  graphLambdaScale: 0.0,
  graphNu: 0.1,
  dynamicsRegime: "sticky_strike",
  ssr: 2.0,
  autoCalibrate: true,
  localVolEnabled: true,
  spotMode: "static",
  spotPollSeconds: 5.0,
  optionsFetchMode: "on_demand",
  optionsFetchMinutes: 5.0,
  streamRefitSeconds: 5.0,
};

export interface UseOptionsResult {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  dirty: boolean;
  busy: boolean;
  flash: boolean;
  /** Commit the draft (PUT); resolves once saved (a no-op when not dirty). */
  apply: () => Promise<void>;
  /** Adopt a server-authoritative value (e.g. after a defaults reset). */
  adopt: (s: OptionsSettings) => void;
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

  const apply = useCallback((): Promise<void> => {
    if (!dirty || busy) return Promise.resolve();
    setBusy(true);
    return api
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

  const adopt = useCallback((s: OptionsSettings) => {
    setSaved(s);
    setDraft(s);
  }, []);

  return { draft, patch, dirty, busy, flash, apply, adopt, loaded };
}
