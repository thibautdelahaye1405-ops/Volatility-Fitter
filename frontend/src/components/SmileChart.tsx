// Interactive implied-volatility smile chart. Hand-rolled SVG, no chart deps.
//
// Geometry is plotted in the SELECTED strike-axis coordinate (k = ln(K/F),
// strike, %ATM, delta, normalized…), so switching the mode genuinely reshapes
// the smile — the x-axis follows the chosen coordinate strictly, not a fixed
// log axis (every mode is a monotone map of k; delta runs high→low). The coarse
// strike window is owned by the parent via the RangeBrush; on top of that, the
// chart supports wheel-zoom (x by default, +Shift = x only, +Alt = y only),
// drag-to-pan and double-click / ⌂ reset — and zoom-out reveals beyond the data.
//
// Two comparable FRAMES are drawn (lib/smileLayers), each in its own moneyness:
//   market  (primary)  the prevailing bid/ask quotes + fit target, and the fit
//                      ROLLED to the prevailing spot — live when streaming;
//   calib   (toggles)  the quotes + target the last calibration used, and the
//                      fit on its CALIBRATION spot.
// The x axis is referenced to the market forward; the calibration frame gets
// its own axis transform (its forward), so strike mode places both by true
// strike and k mode shows each in its own moneyness (a sticky-strike move reads
// as the lateral shift it is).
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, ReactNode } from "react";
import type { SmilePoint } from "../lib/mockData";
import type { FitMode } from "../state/useSmile";
import { clamp, formatPct, linearScale, niceTicks } from "../lib/chartScale";
import { axisDisplayTicks, axisInvert, axisTransform, formatHoverValue } from "../lib/axisModes";
import type { AxisContext, AxisMode } from "../lib/axisModes";
import type { MarketFrame, SmileFrame } from "../lib/smileLayers";
import { useElementSize } from "../lib/useElementSize";
import { useZoom } from "../lib/useZoom";
import { autoScaleYWindow, DEFAULT_AUTOSCALE } from "../lib/autoScaleY";
import type { AutoScaleToggles } from "../lib/autoScaleY";
import QuoteLayer from "./QuoteLayer";
import RangeBrush from "./RangeBrush";

interface SmileChartProps {
  /** The PREVAILING market frame (layers 1 + 3): quotes + target and the fit
   *  rolled to the prevailing spot, in the market forward's moneyness — the
   *  chart's primary layer and its x reference. */
  market: MarketFrame;
  /** The calibration frame (layers 2 + 4): the quotes + target of the last
   *  calibration and the fit on its calibration spot (its own forward). */
  calib: SmileFrame | null;
  /** Toggles for the calibration layers (2: quotes + target, 4: fit). */
  showCalibQuotes?: boolean;
  showCalibFit?: boolean;
  /** Strike keys (4 dp) whose live band moved in the last frame (flash). */
  liveFlash?: Set<string>;
  prior: SmilePoint[];
  /** True when `prior` is the active fetched prior (spot-updated): drawn as a
   *  distinct dotted teal "spot-updated prior" line rather than the saved dash. */
  priorTransported?: boolean;
  /** Visible log-moneyness window [lo, hi] (controlled, the coarse brush). */
  kWindow: readonly [number, number];
  onKWindowChange: (next: [number, number]) => void;
  /** Full brushable k extent of the data. */
  fullRange: readonly [number, number];
  /** Strike-axis display coordinate (geometry plotted in these units). */
  axisMode?: AxisMode;
  /** Year-fraction to expiry — delta / normalized axis modes. */
  t?: number;
  /** ATM implied vol — normalized axis modes. */
  atmVol?: number;
  /** Stable `index` of the highlighted quote, or null for no selection. */
  selectedIndex?: number | null;
  /** Quote click handler; called with null on background clicks. */
  onQuoteSelect?: (index: number | null) => void;
  /** SSR scenario overlay (shifted smile); drawn dotted amber when set. */
  scenario?: SmilePoint[] | null;
  /** Active var-swap quote vol — drawn as a horizontal teal line when set. */
  varSwapLevel?: number | null;
  /** Graph-extrapolated reconstructed smile (plan Phase 5 overlay): solid violet
   *  posterior curve with a shaded credible band, over the live quotes. */
  graphPost?: SmilePoint[] | null;
  graphBandLo?: SmilePoint[] | null;
  graphBandHi?: SmilePoint[] | null;
  /** Observation-filter overlay (Note 15 Phase 4): solid teal filtered
   *  posterior with a shaded ±1.96σ (95%) band, plus a dashed prediction. */
  filterPost?: SmilePoint[] | null;
  filterBandLo?: SmilePoint[] | null;
  filterBandHi?: SmilePoint[] | null;
  filterPred?: SmilePoint[] | null;
  /** Quote-derived fit confidence half-width (vol units, e.g. 1.96·σ_atm from
   *  the fit's own Jacobian + bid-ask noise): a subtle accent band around the
   *  current fit — "error bars from the quotes". */
  fitBandHalf?: number | null;
  /** Named degraded-market condition (backend SmileData.degraded): the node's
   *  DATA is unfittable (e.g. a 0DTE chain minutes from settlement), so the
   *  cue explains the market — not "press Calibrate" — while the dotted
   *  transported prior keeps being served. */
  degraded?: string | null;
  /** Live fit target (mid / bidask / haircut): picks which target band the
   *  V3.4 overlay emphasizes (the haircut ribbon only draws in haircut mode). */
  fitMode?: FitMode;
  /** Draw the fit-target overlay (mid polyline + bid-ask/haircut ribbons). */
  showTarget?: boolean;
  /** Optional strip rendered between the plot and the RangeBrush (the V3.4
   *  weight strip mounts here so it shares the x extent above the brush). */
  footer?: ReactNode;
  /** Y-axis auto-scale policy applied after x-view changes (wheel/pan/brush/
   *  axis mode — lib/autoScaleY): fit snaps the y window to the auto-fitted
   *  base, center keeps the y zoom but recenters it on the data. Both off =
   *  legacy free zoom; alt+wheel (manual y) always bypasses the policy. */
  autoScaleY?: AutoScaleToggles;
}

/** Human labels for the named degraded-market conditions. */
const DEGRADED_LABELS: Record<string, string> = {
  no_parity_forward: "no parity forward",
  no_fittable_market: "no fittable quotes",
};

const MARGIN = { top: 14, right: 14, bottom: 30, left: 52 } as const;

/** Linear interpolation of a curve's vol at log-moneyness k. */
function volAt(curve: SmilePoint[], k: number): number | null {
  if (curve.length === 0) return null;
  const first = curve[0];
  const last = curve[curve.length - 1];
  if (k <= first.k) return first.vol;
  if (k >= last.k) return last.vol;
  for (let i = 1; i < curve.length; i++) {
    const p1 = curve[i];
    if (k <= p1.k) {
      const p0 = curve[i - 1];
      const tt = (k - p0.k) / (p1.k - p0.k);
      return p0.vol + tt * (p1.vol - p0.vol);
    }
  }
  return last.vol;
}

export default function SmileChart({
  market,
  calib,
  showCalibQuotes = false,
  showCalibFit = true,
  liveFlash,
  prior,
  priorTransported = false,
  kWindow,
  onKWindowChange,
  fullRange,
  axisMode = "logmoneyness",
  t,
  atmVol,
  selectedIndex = null,
  onQuoteSelect,
  scenario = null,
  varSwapLevel = null,
  graphPost = null,
  graphBandLo = null,
  graphBandHi = null,
  filterPost = null,
  filterBandLo = null,
  filterBandHi = null,
  filterPred = null,
  fitBandHalf = null,
  degraded = null,
  fitMode = "mid",
  showTarget = false,
  footer = null,
  autoScaleY = DEFAULT_AUTOSCALE,
}: SmileChartProps) {
  // The market frame is the primary layer: its curve drives the hover readout,
  // the confidence band and the y-domain; its forward is the axis reference.
  const model = market.model;
  const quotes = market.quotes;
  const forward = market.forward;
  const { ref, size } = useElementSize();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const clipId = useId();
  const zoom = useZoom();
  // Y auto-scale policy (lib/autoScaleY): the y BASE already fits the data in
  // the x-window, so the policy only rewrites the y FRACTIONS — always through
  // zoom.setYWindow, so the QuoteLayer remount viewKey still fires.
  const autoCenter = autoScaleY.center;
  const autoFit = autoScaleY.fit;
  const autoActive = autoCenter || autoFit;
  const applyAutoY = () => {
    const w = autoScaleYWindow(zoom.fractions, { center: autoCenter, fit: autoFit });
    if (w !== null) zoom.setYWindow(w.yLo, w.yHi);
  };
  /** Hover position in k-space, or null when the pointer is outside. */
  const [hoverK, setHoverK] = useState<number | null>(null);
  /** Hover y-position in vol units (pointer level), or null when outside. */
  const [hoverV, setHoverV] = useState<number | null>(null);
  /** Active drag-pan: last pointer px and whether it has moved past a click. */
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const [kLo, kHi] = kWindow;
  const plotW = Math.max(0, size.width - MARGIN.left - MARGIN.right);
  const plotH = Math.max(0, size.height - MARGIN.top - MARGIN.bottom);

  // Context for the axis-mode transforms.
  const axisCtx: AxisContext = useMemo(
    () => ({
      forward: forward ?? 1,
      t: t ?? 0,
      atmVol: atmVol ?? 0,
      volAt: (kv: number) => volAt(model, kv),
      kRange:
        model.length > 1
          ? ([model[0].k, model[model.length - 1].k] as const)
          : fullRange,
    }),
    [forward, t, atmVol, model, fullRange],
  );

  /** Map k -> the selected display coordinate (market frame / axis reference). */
  const tx = useMemo(() => (k: number) => axisTransform(axisMode, k, axisCtx), [axisMode, axisCtx]);
  /** The calibration frame's own transform: same mode, ITS forward — so strike
   *  mode places it by true strike while k mode keeps its own moneyness. */
  const txCalib = useMemo(
    () => (k: number) => axisTransform(axisMode, k, { ...axisCtx, forward: calib?.forward ?? axisCtx.forward }),
    [axisMode, axisCtx, calib?.forward],
  );

  // Scales: x in display units (base = brushed window mapped through tx, then
  // zoomed); y auto-fits the data visible inside the x view, then zoomed.
  const { xScale, yScale, xView } = useMemo(() => {
    const baseX: [number, number] = [tx(kLo), tx(kHi)];
    const view = zoom.viewX(baseX);
    const xs = linearScale(view, [0, plotW]);
    const vMin = Math.min(view[0], view[1]);
    const vMax = Math.max(view[0], view[1]);
    const inView = (k: number) => {
      const X = tx(k);
      return X >= vMin && X <= vMax;
    };
    let yMin = Infinity;
    let yMax = -Infinity;
    const scan = (pts: SmilePoint[]) => {
      for (const p of pts) if (inView(p.k)) { yMin = Math.min(yMin, p.vol); yMax = Math.max(yMax, p.vol); }
    };
    scan(model);
    scan(prior);
    if (scenario) scan(scenario);
    if (calib && showCalibFit) scan(calib.model);
    if (calib && showCalibQuotes)
      for (const q of calib.quotes) if (inView(q.k)) { yMin = Math.min(yMin, q.bid); yMax = Math.max(yMax, q.ask); }
    if (graphPost) scan(graphPost);
    if (graphBandLo) scan(graphBandLo);
    if (graphBandHi) scan(graphBandHi);
    if (filterPost) scan(filterPost);
    if (filterBandLo) scan(filterBandLo);
    if (filterBandHi) scan(filterBandHi);
    if (filterPred) scan(filterPred);
    for (const q of quotes) if (inView(q.k)) { yMin = Math.min(yMin, q.bid); yMax = Math.max(yMax, q.ask); }
    if (varSwapLevel !== null) { yMin = Math.min(yMin, varSwapLevel); yMax = Math.max(yMax, varSwapLevel); }
    if (!Number.isFinite(yMin)) { yMin = 0; yMax = 1; }
    const pad = Math.max(1e-4, (yMax - yMin) * 0.08);
    const yView = zoom.viewY([yMin - pad, yMax + pad]);
    return { xScale: xs, yScale: linearScale(yView, [plotH, 0]), xView: view };
  }, [model, prior, scenario, calib, showCalibFit, showCalibQuotes, graphPost, graphBandLo, graphBandHi, filterPost, filterBandLo, filterBandHi, filterPred, quotes, varSwapLevel, kLo, kHi, plotW, plotH, tx, zoom]);

  /** Build an SVG path for a curve in display coordinates (clip handles overflow). */
  const pathOf = (curve: SmilePoint[], txf: (k: number) => number = tx): string => {
    let d = "";
    for (const p of curve) {
      const x = xScale.map(txf(p.k));
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    return d;
  };
  const modelPath = useMemo(() => pathOf(model), [model, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const priorPath = useMemo(() => pathOf(prior), [prior, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const scenarioPath = useMemo(() => (scenario ? pathOf(scenario) : ""), [scenario, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const calibFitPath = useMemo(() => (calib && showCalibFit ? pathOf(calib.model, txCalib) : ""), [calib, showCalibFit, xScale, yScale, txCalib]); // eslint-disable-line react-hooks/exhaustive-deps
  const graphPostPath = useMemo(() => (graphPost ? pathOf(graphPost) : ""), [graphPost, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterPostPath = useMemo(() => (filterPost ? pathOf(filterPost) : ""), [filterPost, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterPredPath = useMemo(() => (filterPred ? pathOf(filterPred) : ""), [filterPred, xScale, yScale]); // eslint-disable-line react-hooks/exhaustive-deps
  // Credible-band area: forward along the high edge, back along the low edge.
  const bandPathOf = (lo: SmilePoint[] | null, hi: SmilePoint[] | null): string => {
    if (!lo || !hi || lo.length === 0 || hi.length === 0) return "";
    let d = "";
    for (const p of hi) {
      const x = xScale.map(tx(p.k));
      const y = yScale.map(p.vol);
      d += d === "" ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`;
    }
    for (let i = lo.length - 1; i >= 0; i--) {
      const p = lo[i];
      d += `L${xScale.map(tx(p.k)).toFixed(2)},${yScale.map(p.vol).toFixed(2)}`;
    }
    return d + "Z";
  };
  const graphBandPath = useMemo(() => bandPathOf(graphBandLo, graphBandHi), [graphBandLo, graphBandHi, xScale, yScale, tx]); // eslint-disable-line react-hooks/exhaustive-deps
  const filterBandPath = useMemo(() => bandPathOf(filterBandLo, filterBandHi), [filterBandLo, filterBandHi, xScale, yScale, tx]); // eslint-disable-line react-hooks/exhaustive-deps
  // Fit confidence band: the current fit shifted by ±the quote-derived
  // ATM-level half-width (a level band — the uncertainty IS the ATM handle's).
  const fitBandPath = useMemo(() => {
    if (fitBandHalf === null || fitBandHalf <= 0 || model.length === 0) return "";
    const lo = model.map((p) => ({ k: p.k, vol: p.vol - fitBandHalf }));
    const hi = model.map((p) => ({ k: p.k, vol: p.vol + fitBandHalf }));
    return bandPathOf(lo, hi);
  }, [model, fitBandHalf, xScale, yScale, tx]); // eslint-disable-line react-hooks/exhaustive-deps
  // Pixel maps for the quote layers: the market frame on the axis reference,
  // the calibration frame through its own forward (QuoteLayer draws the beams
  // and the fit-target overlay — lib/smileTarget — per frame).
  const toX = (k: number) => xScale.map(tx(k));
  const toXCalib = (k: number) => xScale.map(txCalib(k));
  const toY = (v: number) => yScale.map(v);
  // Remount-on-zoom key for the quote layers: every zoom / pan / resize step
  // REPLACES the beam elements instead of mutating their geometry in place —
  // removal + insertion is invalidated reliably by every engine (Chrome left
  // ghost beams at the old positions under live streaming until the next tick
  // rebuilt them). Live ticks themselves do not change this key, so a beam's
  // click target survives between pointer-down and click while streaming.
  const zf = zoom.fractions;
  const viewKey = `${zf.xLo},${zf.xHi},${zf.yLo},${zf.yHi},${plotW},${plotH},${axisMode}`;
  const tickStamp = market.timestamp ? `${market.timestamp.slice(11, 19)} UTC` : "";

  // X ticks: nice values in display units, placed directly on the display scale.
  const xTicks = useMemo(
    () => axisDisplayTicks(axisMode, xView[0], xView[1], 6).map((d) => ({ x: xScale.map(d.value), label: d.label })),
    [axisMode, xView, xScale],
  );
  const yTicks = niceTicks(yScale.domain[0], yScale.domain[1], 6);
  const zeroX = useMemo(() => {
    const X0 = axisTransform(axisMode, 0, axisCtx);
    const lo = Math.min(xView[0], xView[1]);
    const hi = Math.max(xView[0], xView[1]);
    return X0 >= lo && X0 <= hi ? xScale.map(X0) : null;
  }, [axisMode, axisCtx, xView, xScale]);

  /* ---------------- wheel zoom (native, non-passive) ---------------- */

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (e: WheelEvent) => {
      if (plotW <= 0 || plotH <= 0) return;
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const fx = clamp((e.clientX - rect.left - MARGIN.left) / plotW, 0, 1);
      const fy = clamp((e.clientY - rect.top - MARGIN.top) / plotH, 0, 1);
      const axis = e.shiftKey ? "x" : e.altKey ? "y" : "both";
      if (autoActive && axis !== "y") {
        // The policy owns y: zoom x only, then re-apply it. Alt+wheel — the
        // manual y-only zoom — falls through untouched (no policy).
        zoom.zoomAt(fx, fy, e.deltaY, "x");
        applyAutoY();
      } else {
        zoom.zoomAt(fx, fy, e.deltaY, axis);
      }
    };
    svg.addEventListener("wheel", onWheel, { passive: false });
    return () => svg.removeEventListener("wheel", onWheel);
  }, [zoom, plotW, plotH, autoActive]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-apply the policy when the x view changes OUTSIDE the zoom handlers —
  // the coarse RangeBrush window or an axis-mode switch — and when the chips
  // themselves flip on (so enabling one takes effect immediately). Reset is
  // already the identity, so no trigger is needed there. No loop: the deps
  // exclude the fractions, and a satisfied window is a state no-op.
  useEffect(() => {
    if (!autoActive) return;
    applyAutoY();
  }, [kLo, kHi, axisMode, autoCenter, autoFit]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------------- hover + drag-pan ---------------- */

  const onPointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    drag.current = { x: e.clientX, y: e.clientY, moved: false };
  };
  const onPointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = e.clientX - rect.left - MARGIN.left;
    const py = e.clientY - rect.top - MARGIN.top;
    // Hover readout (x tracks the model curve, y the pointer level).
    if (px < 0 || px > plotW) setHoverK(null);
    else {
      const k = axisInvert(axisMode, xScale.invert(px), axisCtx);
      setHoverK(k !== null && Number.isFinite(k) ? k : null);
    }
    setHoverV(py >= 0 && py <= plotH ? yScale.invert(py) : null);
    // Drag-pan.
    const d = drag.current;
    if (d && plotW > 0 && plotH > 0) {
      const dx = e.clientX - d.x;
      const dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) {
        zoom.panBy(dx / plotW, dy / plotH, "both");
        if (autoActive && dx !== 0) applyAutoY(); // x moved: policy rules y
        drag.current = { x: e.clientX, y: e.clientY, moved: true };
      }
    }
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d && !d.moved) onQuoteSelect?.(null); // a plain click clears selection
  };
  const onPointerLeave = () => {
    setHoverK(null);
    setHoverV(null);
    drag.current = null;
  };

  const hoverVol = hoverK !== null ? volAt(model, hoverK) : null;
  const hoverX = hoverK !== null ? xScale.map(tx(hoverK)) : 0;
  const hoverLabel =
    hoverK !== null && hoverVol !== null
      ? `${formatHoverValue(axisMode, axisTransform(axisMode, hoverK, axisCtx))} · σ ${formatPct(hoverVol, 2)}` +
        (hoverV !== null ? ` · y ${formatPct(hoverV, 2)}` : "")
      : null;

  /* ---------------- render ---------------- */

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Legend */}
      <div className="mb-1 flex shrink-0 items-center gap-4 px-1 text-[11px] text-slate-400">
        {/* Market frame (primary): quotes + target, fit at the prevailing spot */}
        <span className="flex items-center gap-1.5" title="The prevailing bid/ask quotes (the market as quoted; live when streaming)">
          <span className="inline-block h-3 w-0.5 rounded bg-red-400" /> Market quotes
        </span>
        {model.length > 0 && (
          <span className="flex items-center gap-1.5" title={`The fit rolled to the prevailing spot${market.spot !== null ? ` (S ${market.spot.toFixed(2)})` : ""} under the dynamics regime`}>
            <span className="h-0.5 w-5 rounded bg-accent-400" /> Fit @ market spot
          </span>
        )}
        {market.live && (
          <span
            className="flex items-center gap-1.5"
            title={
              market.warming
                ? "The stream is up but the book has not served this node yet"
                : `Live market off the streaming book (${quotes.length} quotes${tickStamp ? `, ${tickStamp}` : ""})`
            }
          >
            <span
              className={[
                "inline-block h-1.5 w-1.5 rounded-full",
                market.warming ? "bg-amber-400" : "bg-emerald-400 volfit-live-dot",
              ].join(" ")}
            />
            <span className={market.warming ? "text-amber-400" : "text-emerald-400"}>
              {market.warming ? "live feed warming" : `LIVE ${tickStamp}`}
            </span>
          </span>
        )}
        {/* Calibration frame (toggles): muted, dashed */}
        {calib && showCalibQuotes && (
          <span className="flex items-center gap-1.5" title="The quotes + target the last calibration used (with your exclusions / amended mids)">
            <span className="inline-block h-3 w-0.5 rounded border-l border-dashed border-slate-400" /> Calibration quotes
          </span>
        )}
        {calibFitPath !== "" && (
          <span className="flex items-center gap-1.5" title="The fitted smile on its calibration spot">
            <span className="h-0 w-5 border-t-2 border-dashed border-accent-400/50" /> Fit @ calibration spot
          </span>
        )}
        {fitBandPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-5 rounded bg-accent-400/15" /> ±1.96σ quotes
          </span>
        )}
        {showTarget && quotes.length > 0 && (
          <span className="flex items-center gap-1.5" title="Fit target of the viewed fit mode: bid-ask ribbon, haircut ribbon (haircut mode) and the mid polyline">
            <span className="h-2 w-5 rounded bg-red-400/20" /> {fitMode === "haircut" ? "Haircut target" : fitMode === "bidask" ? "Bid-ask target" : "Mid target"}
          </span>
        )}
        {prior.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-slate-500" /> Prior
          </span>
        )}
        {scenarioPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dotted border-amber-400" /> SSR scenario
          </span>
        )}
        {varSwapLevel !== null && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-teal-400" /> Var-swap
          </span>
        )}
        {graphPostPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded" style={{ background: "rgb(167 139 250)" }} /> Graph extrapolation
          </span>
        )}
        {filterPostPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-5 rounded" style={{ background: "rgb(20 184 166)" }} /> Filter
          </span>
        )}
        {filterPredPath !== "" && (
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-5 border-t-2 border-dashed border-teal-300" /> Filter pred
          </span>
        )}
        <span className="ml-auto text-[10px] text-slate-600">scroll: zoom · drag: pan · dbl-click: reset</span>
      </div>

      {/* Plot area (measured for responsive SVG) */}
      <div ref={ref} className="relative min-h-0 flex-1">
        {size.width > 0 && size.height > 0 && (
          <svg
            ref={svgRef}
            width={size.width}
            height={size.height}
            className="absolute inset-0 cursor-crosshair touch-none select-none"
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerLeave}
            onDoubleClick={zoom.reset}
          >
            <defs>
              <clipPath id={clipId}>
                <rect x={0} y={0} width={plotW} height={plotH} />
              </clipPath>
            </defs>
            <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
              {/* Gridlines */}
              {yTicks.map((tv) => (
                <line key={`gy${tv}`} x1={0} x2={plotW} y1={yScale.map(tv)} y2={yScale.map(tv)}
                  stroke="rgb(255 255 255 / 0.05)" />
              ))}
              {xTicks.map((tick, i) => (
                <line key={`gx${i}`} x1={tick.x} x2={tick.x} y1={0} y2={plotH}
                  stroke="rgb(255 255 255 / 0.04)" />
              ))}

              {/* Zero log-moneyness (ATM forward) reference */}
              {zeroX !== null && (
                <line x1={zeroX} x2={zeroX} y1={0} y2={plotH}
                  stroke="rgb(148 163 184 / 0.25)" strokeDasharray="2 4" />
              )}

              {/* Axes labels */}
              {yTicks.map((tv) => (
                <text key={`ly${tv}`} x={-8} y={yScale.map(tv)} dy="0.32em" textAnchor="end"
                  className="fill-slate-500 font-mono text-[10px]">
                  {formatPct(tv)}
                </text>
              ))}
              {xTicks.map((tick, i) => (
                <text key={`lx${i}`} x={tick.x} y={plotH + 16} textAnchor="middle"
                  className="fill-slate-500 font-mono text-[10px]">
                  {tick.label}
                </text>
              ))}

              {/* Clipped plot geometry */}
              <g clipPath={`url(#${clipId})`}>
                {/* Variance-swap quote: horizontal teal line at the quoted vol */}
                {varSwapLevel !== null &&
                  varSwapLevel >= yScale.domain[0] &&
                  varSwapLevel <= yScale.domain[1] && (
                    <g pointerEvents="none">
                      <line x1={0} x2={plotW} y1={yScale.map(varSwapLevel)} y2={yScale.map(varSwapLevel)}
                        stroke="rgb(45 212 191 / 0.85)" strokeWidth={1.5} strokeDasharray="6 4" />
                      <text x={plotW - 2} y={yScale.map(varSwapLevel) - 3} textAnchor="end"
                        className="fill-teal-300 font-mono text-[10px]">
                        VS {formatPct(varSwapLevel, 2)}
                      </text>
                    </g>
                  )}

                {/* Calibration frame (toggle): the quotes + target the last fit
                    used, muted and dashed, in its own moneyness. Drawn under the
                    market frame so the prevailing market stays on top. */}
                {calib && showCalibQuotes && (
                  <QuoteLayer
                    key={`calib-${viewKey}`}
                    quotes={calib.quotes}
                    variant="calib"
                    toX={toXCalib}
                    toY={toY}
                    plotW={plotW}
                    fitMode={fitMode}
                    showTarget={showTarget}
                    selectedIndex={selectedIndex}
                    onQuoteSelect={onQuoteSelect}
                  />
                )}

                {/* Market frame (primary): the prevailing bid/ask quotes + their
                    fit target, bright red; live-ticked strikes flash teal. */}
                <QuoteLayer
                  key={`market-${viewKey}`}
                  quotes={quotes}
                  variant="market"
                  toX={toX}
                  toY={toY}
                  plotW={plotW}
                  fitMode={fitMode}
                  showTarget={showTarget}
                  selectedIndex={selectedIndex}
                  onQuoteSelect={onQuoteSelect}
                  flash={liveFlash}
                />

                {/* Prior: saved = dashed slate; active fetched (spot-updated) =
                    dotted teal so it reads as the live, transported prior. */}
                <path
                  d={priorPath}
                  fill="none"
                  stroke={priorTransported ? "rgb(45 212 191 / 0.95)" : "rgb(100 116 139 / 0.9)"}
                  strokeWidth={1.5}
                  strokeDasharray={priorTransported ? "2 3" : "5 4"}
                />

                {/* SSR scenario overlay: dotted amber */}
                {scenarioPath !== "" && (
                  <path d={scenarioPath} fill="none" stroke="rgb(251 191 36 / 0.85)"
                    strokeWidth={1.5} strokeDasharray="2 3" />
                )}

                {/* Calibration frame (toggle): the fit on its calibration spot —
                    dimmed dashed accent, its own moneyness. */}
                {calibFitPath !== "" && (
                  <path d={calibFitPath} fill="none" stroke="var(--color-accent-400)"
                    strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="6 4"
                    strokeLinejoin="round" pointerEvents="none" />
                )}

                {/* Graph-extrapolated reconstruction: shaded credible band + a
                    solid violet posterior curve (plan Phase 5 live overlay). */}
                {graphBandPath !== "" && (
                  <path d={graphBandPath} fill="rgb(167 139 250 / 0.16)" stroke="none" pointerEvents="none" />
                )}
                {graphPostPath !== "" && (
                  <path d={graphPostPath} fill="none" stroke="rgb(167 139 250 / 0.95)"
                    strokeWidth={2} strokeLinejoin="round" pointerEvents="none" />
                )}

                {/* Observation-filter overlay (Note 15): shaded ±1.96σ (95%)
                    band, a dashed lighter one-step prediction and a solid
                    teal filtered-posterior curve. */}
                {filterBandPath !== "" && (
                  <path d={filterBandPath} fill="rgb(20 184 166 / 0.14)" stroke="none" pointerEvents="none" />
                )}
                {filterPredPath !== "" && (
                  <path d={filterPredPath} fill="none" stroke="rgb(94 234 212 / 0.8)"
                    strokeWidth={1.5} strokeDasharray="3 3" pointerEvents="none" />
                )}
                {filterPostPath !== "" && (
                  <path d={filterPostPath} fill="none" stroke="rgb(20 184 166 / 0.95)"
                    strokeWidth={2} strokeLinejoin="round" pointerEvents="none" />
                )}

                {/* Quote-derived confidence band around the current fit
                    (±1.96·σ_atm from the fit's own Jacobian + bid-ask noise). */}
                {fitBandPath !== "" && (
                  <path d={fitBandPath} fill="var(--color-accent-400)" fillOpacity={0.09}
                    stroke="none" pointerEvents="none" />
                )}

                {/* Market frame: the fit rolled to the prevailing spot (accent) */}
                <path d={modelPath} fill="none" stroke="var(--color-accent-400)"
                  strokeWidth={2} strokeLinejoin="round" />

                {/* Trigger-gated cue: no model curve yet — never calibrated,
                    or a NAMED degraded-market condition (unfittable data:
                    Calibrate would not help, the prior is the surface). */}
                {model.length === 0 && (
                  <text
                    x={plotW / 2}
                    y={18}
                    textAnchor="middle"
                    className={degraded ? "fill-amber-500" : "fill-slate-500"}
                    style={{ fontSize: 11 }}
                  >
                    {degraded
                      ? `Degraded market (${DEGRADED_LABELS[degraded] ?? degraded}) — showing transported prior`
                      : quotes.length === 0
                        ? "No quotes — press Fetch"
                        : "No fit yet — press Calibrate"}
                  </text>
                )}

                {/* Crosshair: vertical guide + model dot, plus a horizontal
                    guide at the pointer's vol level (the badge's y readout). */}
                {hoverK !== null && hoverVol !== null && (
                  <g pointerEvents="none">
                    <line x1={hoverX} x2={hoverX} y1={0} y2={plotH}
                      stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                    {hoverV !== null && (
                      <line x1={0} x2={plotW} y1={yScale.map(hoverV)} y2={yScale.map(hoverV)}
                        stroke="rgb(148 163 184 / 0.4)" strokeDasharray="3 3" />
                    )}
                    <circle cx={hoverX} cy={yScale.map(hoverVol)} r={3.5}
                      fill="var(--color-accent-400)" stroke="var(--color-surface-900)" strokeWidth={1.5} />
                  </g>
                )}
              </g>
            </g>
          </svg>
        )}

        {/* Tooltip readout badge (top-right corner) */}
        {hoverLabel && (
          <div className="pointer-events-none absolute top-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2.5 py-1 font-mono text-[11px] text-slate-200 shadow-lg shadow-black/40">
            {hoverLabel}
          </div>
        )}

        {/* Reset-zoom affordance */}
        {zoom.zoomed && (
          <button
            onClick={zoom.reset}
            title="Reset zoom (or double-click the chart)"
            className="absolute bottom-1 right-2 rounded-md border border-slate-700 bg-surface-800/95 px-2 py-0.5 text-[10px] text-slate-300 shadow hover:text-slate-100"
          >
            ⌂ reset
          </button>
        )}
      </div>

      {/* Optional footer strip (V3.4 weight strip) — above the brush */}
      {footer !== null && <div className="mt-2 shrink-0 px-1">{footer}</div>}

      {/* Strike-window brush (coarse, in log-moneyness k) */}
      <div className="mt-2 shrink-0 px-1">
        <RangeBrush
          min={fullRange[0]}
          max={fullRange[1]}
          value={kWindow}
          onChange={onKWindowChange}
          format={(v) => v.toFixed(2)}
        />
      </div>
    </div>
  );
}
