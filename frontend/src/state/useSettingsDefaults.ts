// Persist / clear the global Fit + Options defaults (GET/POST/DELETE
// /settings/defaults). Backs the Options tab's "Save as default" / "Reset to
// defaults" buttons: Save writes the current backend settings to the app store
// so a restart restores them; Reset clears the saved blob and reverts the live
// settings to the built-in code defaults. Persistence needs a configured store
// (VOLFIT_DB) — `storeEnabled` is false otherwise, and the UI disables Save.
import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { FitSettings } from "../components/HyperparamPanel";
import type { OptionsSettings } from "./useOptions";

interface DefaultsStatus {
  storeEnabled: boolean;
  hasSaved: boolean;
}

/** DELETE response: status plus the reverted code-default settings. */
export interface DefaultsReset extends DefaultsStatus {
  fit: FitSettings;
  options: OptionsSettings;
}

export interface UseSettingsDefaultsResult {
  storeEnabled: boolean;
  hasSaved: boolean;
  busy: boolean;
  flash: boolean;
  /** Persist the current backend settings as the startup defaults. */
  save: () => Promise<void>;
  /** Clear saved defaults and revert live settings; resolves with the result. */
  reset: () => Promise<DefaultsReset | null>;
}

export function useSettingsDefaults(enabled: boolean): UseSettingsDefaultsResult {
  const [storeEnabled, setStoreEnabled] = useState(false);
  const [hasSaved, setHasSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    api
      .get<DefaultsStatus>("/settings/defaults", { signal: controller.signal })
      .then((s) => {
        setStoreEnabled(s.storeEnabled);
        setHasSaved(s.hasSaved);
      })
      .catch(() => {
        /* keep defaults; the save POST surfaces real failures */
      });
    return () => controller.abort();
  }, [enabled]);

  const save = useCallback((): Promise<void> => {
    if (busy) return Promise.resolve();
    setBusy(true);
    return api
      .post<DefaultsStatus>("/settings/defaults")
      .then((s) => {
        setStoreEnabled(s.storeEnabled);
        setHasSaved(s.hasSaved);
        setFlash(true);
        setTimeout(() => setFlash(false), 1200);
      })
      .catch(() => {
        /* leave state as-is so the user can retry */
      })
      .finally(() => setBusy(false));
  }, [busy]);

  const reset = useCallback((): Promise<DefaultsReset | null> => {
    if (busy) return Promise.resolve(null);
    setBusy(true);
    return api
      .delete<DefaultsReset>("/settings/defaults")
      .then((r) => {
        setStoreEnabled(r.storeEnabled);
        setHasSaved(r.hasSaved);
        return r;
      })
      .catch(() => null)
      .finally(() => setBusy(false));
  }, [busy]);

  return { storeEnabled, hasSaved, busy, flash, save, reset };
}
