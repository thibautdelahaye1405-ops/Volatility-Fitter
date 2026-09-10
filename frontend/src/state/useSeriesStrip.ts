// The Series filmstrip's data (roadmap §3.4): GET /series/{id}/strip?lanes=
// …&expiry=… — per frame the spot, the shown expiry's ATM vol per lane and
// every STRIP_METRIC per lane (null where a lane has no fit at a frame).
// One request per (series, lane set, expiry, epoch); the previous strip
// stays on screen while a refetch of the same series is in flight (no
// flicker when the shown expiry changes), and drops when the series does.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { StripPayload } from "../lib/seriesTypes";

const STRIP_TIMEOUT_MS = 30_000;

export function useSeriesStrip(
  seriesId: string | null,
  laneIds: readonly string[],
  expiry: string | null,
  epoch: string,
): { strip: StripPayload | null } {
  const lanesKey = laneIds.join(",");
  const [strip, setStrip] = useState<StripPayload | null>(null);

  useEffect(() => {
    if (seriesId === null) {
      setStrip(null);
      return;
    }
    const controller = new AbortController();
    api
      .get<StripPayload>(`/series/${encodeURIComponent(seriesId)}/strip`, {
        params: {
          lanes: lanesKey !== "" ? lanesKey : undefined,
          expiry: expiry ?? undefined,
        },
        signal: controller.signal,
        timeoutMs: STRIP_TIMEOUT_MS,
      })
      .then((s) => setStrip(s))
      .catch(() => {
        if (controller.signal.aborted) return; // superseded or unmounted
        // A failed strip of another series must not linger under this one.
        setStrip((prev) => (prev !== null && prev.seriesId === seriesId ? prev : null));
      });
    return () => controller.abort();
  }, [seriesId, lanesKey, expiry, epoch]);

  // Never serve another series' strip under this one, even for one render.
  return { strip: strip !== null && strip.seriesId === seriesId ? strip : null };
}
