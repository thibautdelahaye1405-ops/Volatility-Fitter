// Read-side hook for the Stacked-IV display crop (Options ▸ stackCrop /
// stackCropTailProb): the current values off GET /settings/options, refreshed
// whenever the caller's version bumps (the session's spotVersion, which the
// Options dialog bumps on apply). Display-only: the crop itself is
// lib/stackCrop applied by the Stacked-IV views to payload crop tables.
import { useEffect, useState } from "react";
import { api } from "./api";

export interface StackCropSettings {
  /** Crop on/off (Options default: off). */
  enabled: boolean;
  /** Tail probability ε per side (Options default 1e-7). */
  eps: number;
}

const DEFAULTS: StackCropSettings = { enabled: false, eps: 1e-7 };

/** The crop settings; `version` re-reads them (pass the session spotVersion). */
export function useStackCrop(version: number): StackCropSettings {
  const [settings, setSettings] = useState<StackCropSettings>(DEFAULTS);
  useEffect(() => {
    const controller = new AbortController();
    api
      .get<{ stackCrop?: boolean; stackCropTailProb?: number }>("/settings/options", {
        signal: controller.signal,
      })
      .then((o) =>
        setSettings({
          enabled: o.stackCrop ?? DEFAULTS.enabled,
          eps: o.stackCropTailProb ?? DEFAULTS.eps,
        }),
      )
      .catch(() => {
        /* mock / offline: keep the defaults (crop off) */
      });
    return () => controller.abort();
  }, [version]);
  return settings;
}
