// Load / edit the global model fit settings (GET/PUT /settings/fit).
//
// Lifted out of HyperparamPanel so the Options tab can render the FitSettings
// controls across two themed cards (Model & hyperparameters / Calibration) that
// share ONE draft and ONE Apply. Mirrors useOptions exactly.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { FitSettings } from "../components/HyperparamPanel";
import { FIT_DEFAULTS } from "../components/HyperparamPanel";

export interface UseFitSettingsResult {
  draft: FitSettings;
  patch: (p: Partial<FitSettings>) => void;
  dirty: boolean;
  busy: boolean;
  flash: boolean;
  /** Commit the draft (PUT); resolves once saved (a no-op when not dirty). */
  apply: () => Promise<void>;
  /** Adopt a server-authoritative value (e.g. after a defaults reset). */
  adopt: (s: FitSettings) => void;
  loaded: boolean;
}

export function useFitSettings(enabled: boolean, onApplied: () => void): UseFitSettingsResult {
  const [saved, setSaved] = useState<FitSettings>(FIT_DEFAULTS);
  const [draft, setDraft] = useState<FitSettings>(FIT_DEFAULTS);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    api
      .get<FitSettings>("/settings/fit", { signal: controller.signal })
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
    (p: Partial<FitSettings>) => setDraft((d) => ({ ...d, ...p })),
    [],
  );

  const dirty = (Object.keys(draft) as (keyof FitSettings)[]).some(
    (k) => draft[k] !== saved[k],
  );

  const apply = useCallback((): Promise<void> => {
    if (!dirty || busy) return Promise.resolve();
    setBusy(true);
    return api
      .put<FitSettings>("/settings/fit", { body: draft })
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

  const adopt = useCallback((s: FitSettings) => {
    setSaved(s);
    setDraft(s);
  }, []);

  return { draft, patch, dirty, busy, flash, apply, adopt, loaded };
}
