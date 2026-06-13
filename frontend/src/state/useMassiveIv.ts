// Read-only Massive implied-vol overlay for the smile chart.
//
// Fetches GET /massive/iv/{ticker}?expiry= (the Massive provider's own
// per-contract American IVs / greeks) and maps each contract to a chart point
// in log-moneyness k = ln(K / F). It is purely informational — a comparison
// against volfit's de-Americanized European fit — so any failure (the active
// provider isn't Massive -> 404, network, mock mode) silently yields null and
// the overlay simply doesn't render.
import { useEffect, useState } from "react";
import { api } from "./api";
import type { SmilePoint } from "../lib/mockData";

/** One contract in the /massive/iv payload (subset we plot). */
interface MassiveIvPoint {
  strike: number | null;
  callPut: string;
  iv: number;
}

/** Response of GET /massive/iv/{ticker}. */
interface MassiveIvResponse {
  ticker: string;
  points: MassiveIvPoint[];
}

/**
 * Massive IV points for the current node as `{k, vol}`, or null when the
 * overlay is off / unavailable. Uses the out-of-the-money side at each strike
 * (puts below the forward, calls above) and dedupes by strike so the scatter
 * reads as a single smile.
 */
export function useMassiveIv(
  live: boolean,
  ticker: string,
  expiry: string,
  forward: number,
  enabled: boolean,
): SmilePoint[] | null {
  const [curve, setCurve] = useState<SmilePoint[] | null>(null);

  useEffect(() => {
    if (!enabled || !live || ticker === "" || expiry === "" || !(forward > 0)) {
      setCurve(null);
      return;
    }
    const controller = new AbortController();
    api
      .get<MassiveIvResponse>(`/massive/iv/${ticker}`, {
        params: { expiry },
        signal: controller.signal,
      })
      .then((res) => {
        const byStrike = new Map<number, SmilePoint>();
        for (const p of res.points) {
          if (p.strike === null || !(p.iv > 0) || !Number.isFinite(p.iv)) continue;
          const k = Math.log(p.strike / forward);
          const otmSide = k < 0 ? "P" : "C"; // keep the liquid OTM wing only
          if (p.callPut !== otmSide) continue;
          byStrike.set(p.strike, { k, vol: p.iv });
        }
        const points = [...byStrike.values()].sort((a, b) => a.k - b.k);
        setCurve(points.length > 0 ? points : null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setCurve(null);
      });
    return () => controller.abort();
  }, [enabled, live, ticker, expiry, forward]);

  return curve;
}
