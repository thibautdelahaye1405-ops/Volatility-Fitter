// The Lanes stage's evidence (SERIES ARC S5): GET /series/{id}/evidence?
// lanes=…&expiry=… — per lane over the READY frames of the shown expiry the
// frame counts, the mean rms / max error, the worst frame, the roughness of
// the ATM vol and the skew, the pull, the fit time and the ζ std. One
// request per (series, lane set, expiry, epoch) — the useSeriesStrip
// pattern: the previous payload stays while the same series refetches (a
// chip change never flashes an empty table) and drops when the series does.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { EvidencePayload } from "../lib/seriesTypes";

const EVIDENCE_TIMEOUT_MS = 30_000;

export function useSeriesEvidence(
  seriesId: string | null,
  laneIds: readonly string[],
  expiry: string | null,
  epoch: string,
): { evidence: EvidencePayload | null } {
  const lanesKey = laneIds.join(",");
  const [evidence, setEvidence] = useState<EvidencePayload | null>(null);

  useEffect(() => {
    if (seriesId === null) {
      setEvidence(null);
      return;
    }
    const controller = new AbortController();
    api
      .get<EvidencePayload>(`/series/${encodeURIComponent(seriesId)}/evidence`, {
        params: {
          lanes: lanesKey !== "" ? lanesKey : undefined,
          expiry: expiry ?? undefined,
        },
        signal: controller.signal,
        timeoutMs: EVIDENCE_TIMEOUT_MS,
      })
      .then((e) => setEvidence(e))
      .catch(() => {
        if (controller.signal.aborted) return; // superseded or unmounted
        // A failed read of another series must not linger under this one.
        setEvidence((prev) => (prev !== null && prev.seriesId === seriesId ? prev : null));
      });
    return () => controller.abort();
  }, [seriesId, lanesKey, expiry, epoch]);

  // Never serve another series' evidence under this one, even for one render.
  return { evidence: evidence !== null && evidence.seriesId === seriesId ? evidence : null };
}
