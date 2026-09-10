// Local Vol lens · derived views (split out of LocalVolViewer.tsx on 2026-09-10,
// the 400-line policy — a pure move): everything the viewer builds client-side
// from the cached affine fit — the reconstructed IV surface, the nodal LV mesh
// with its display-x transform, the stacked total variance with its calendar
// marker, and the stacked densities. Same memos, same dependencies.
import { useMemo } from "react";
import { maturityColor } from "../../components/OverlayCurvesChart";
import type { OverlayMarker, OverlaySeries } from "../../components/OverlayCurvesChart";
import type { SurfaceMeshData } from "../../components/SurfaceMesh";
import type { LvAxis } from "../../components/localvol/LocalVolToolbar";
import { lvMeshFormatX, lvMeshXTransform } from "../../components/localvol/lvMeshAxis";
import { buildIvSurface, smileAxisContext } from "../../lib/affineSurface";
import { axisTransform } from "../../lib/axisModes";
import type { AxisMode } from "../../lib/axisModes";
import { formatExpiry } from "../../lib/expiryFormat";
import type { ExpiryFormat } from "../../lib/expiryFormat";
import { cropPoints, cropRangeAt } from "../../lib/stackCrop";
import { lvCalendarMarker } from "../../lib/stackedVariance";
import type { AffineFitResponse } from "../../state/useAffine";
import { useStackCrop } from "../../state/useStackCrop";

export function useLocalVolOverlays(
  data: AffineFitResponse | null,
  { lvAxis, axisMode, format, spotVersion }: {
    lvAxis: LvAxis; axisMode: AxisMode; format: ExpiryFormat; spotVersion: number;
  },
) {
  // Reconstructed IV surface: every expiry's smile resampled onto a shared
  // log-moneyness grid (intersection range, no extrapolation) → 3D σ_IV mesh.
  const ivSurface = useMemo(() => (data ? buildIvSurface(data.smiles) : null), [data]);

  // Nodal LV surface as a 3D mesh in LOCAL VARIANCE σ²_loc (what the pricing
  // PDE consumes): rows = vertex maturities t, columns = vertex strikes x = K/F.
  const lvMesh = useMemo<SurfaceMeshData | null>(() => {
    if (!data || data.tNodes.length < 2 || data.xNodes.length < 2) return null;
    return {
      expiries: data.tNodes.map((t) => t.toFixed(2)),
      t: data.tNodes,
      k: data.xNodes,
      vol: data.localVol.map((row) => row.map((v) => v * v)),
    };
  }, [data]);

  // Display-x transform + corner-label formatter for the 3D LV mesh (grid
  // x = K/F, per t-row; localvol/lvMeshAxis). Memoized for SurfaceMesh's memo.
  const lvXTransform = useMemo(() => lvMeshXTransform(lvAxis, data), [lvAxis, data]);
  const lvFormatX = lvMeshFormatX(lvAxis, lvXTransform !== undefined);

  // Stacked IV: every reconstructed expiry's total variance w(k) = σ(k)²·τ on
  // shared axes (mirrors the Parametric workspace). σ is quoted in the event-
  // variance clock τ, so this is the price total variance — non-crossing across
  // expiries ⟺ no calendar arbitrage in the local-vol surface. Each expiry
  // re-coordinates k by its own forward / smile for the chosen axis mode.
  // Opt-in display crop (Options ▸ stackCrop): each expiry's curve only inside
  // its realistic k-range at the chosen tail probability (lib/stackCrop),
  // read off the payload's crop table; the quote markers are untouched.
  const crop = useStackCrop(spotVersion);
  const stackedIv = useMemo<OverlaySeries[] | null>(() => {
    if (!data || data.smiles.length === 0) return null;
    const n = data.smiles.length;
    return data.smiles.map((s, i) => {
      const tau = s.tau && s.tau > 0 ? s.tau : s.t;
      const ctx = smileAxisContext(s);
      // Prefer the untruncated modelExt (shared display grid, V3.3 item 3) so
      // short expiries are no longer stubs — same pattern as densityExt below.
      const full = s.modelExt && s.modelExt.length > 1 ? s.modelExt : s.model;
      const pts = crop.enabled
        ? cropPoints(full, (p) => p.k, cropRangeAt(s.cropRanges, crop.eps))
        : full;
      return {
        label: formatExpiry(s.expiry, s.t, format),
        t: s.t,
        xs: pts.map((p) =>
          axisMode === "logmoneyness" ? p.k : axisTransform(axisMode, p.k, ctx),
        ),
        ys: pts.map((p) => p.vol * p.vol * tau),
        color: maturityColor(n > 1 ? i / (n - 1) : 0),
      };
    });
  }, [data, format, axisMode, crop]);

  // Worst calendar crossing on the PDE lattice (V3.3 item 10): a circle at
  // (k*, curve midpoint) on the stacked-IV axes; empty when arb-free.
  const lvCalMarkers = useMemo<OverlayMarker[]>(() => {
    if (!data) return [];
    const m = lvCalendarMarker(data.smiles, data.calendarWorstPair, data.calendarWorstK);
    if (m === null) return [];
    const far = data.smiles[(data.calendarWorstPair ?? 0) + 1];
    const x =
      axisMode === "logmoneyness" || !far
        ? m.k
        : axisTransform(axisMode, m.k, smileAxisContext(far));
    return [{ x, y: m.y, label: m.label }];
  }, [data, axisMode]);

  // Densities: every reconstructed expiry's risk-neutral pdf (Breeden-
  // Litzenberger, carried on each smile) overlaid on shared axes — mirrors the
  // Parametric "Densities" view. All curves staying ≥ 0 ⟺ no butterfly arbitrage.
  const stackedDensities = useMemo<OverlaySeries[] | null>(() => {
    if (!data || data.smiles.length === 0) return null;
    const n = data.smiles.length;
    // Prefer the left-extended density (reaches k_min = -1.4) over the
    // central-mass PDE density, so the overlay spans the full smile range.
    // Since 2026-09-03 both are the model's own lattice density (densityExt on
    // the converged operator) — no implied-vol Breeden-Litzenberger rebuild.
    const series = data.smiles
      .map((s, i) => ({ d: s.densityExt ?? s.density, s, i }))
      .filter(({ d }) => d && d.x.length > 0)
      .map(({ d, s, i }) => {
        const ctx = smileAxisContext(s);
        return {
          label: formatExpiry(s.expiry, s.t, format),
          t: s.t,
          xs: d!.x.map((k) => (axisMode === "logmoneyness" ? k : axisTransform(axisMode, k, ctx))),
          ys: d!.density,
          color: maturityColor(n > 1 ? i / (n - 1) : 0),
        };
      });
    return series.length > 0 ? series : null;
  }, [data, format, axisMode]);

  return { ivSurface, lvMesh, lvXTransform, lvFormatX, stackedIv, lvCalMarkers, stackedDensities };
}
