// Overlay provenance badges of the Parametric chart card (UI SHELL v2, S3):
// the GRAPH badge (graph-extrapolation drill-in: model · prior source · quote
// metrics · posterior var-swap ± 1σ, with a ✕ that clears the focus) and the
// FILTER badge (observation Kalman filter: per-handle gains · ρ · provenance,
// amber when the measurement was flagged contaminated). Extracted from
// SmileViewer so the view stays under the file-size policy.
import type { GraphNodeSmile } from "../../state/useGraphNodeSmile";
import type { FilterDiagnostics } from "../../state/useObservationFilter";

export function GraphOverlayBadge({
  overlay,
  onDismiss,
}: {
  overlay: GraphNodeSmile;
  onDismiss: () => void;
}) {
  const tails =
    overlay.tailMassLeft !== null && overlay.tailMassRight !== null
      ? ` · tail mass beyond chart: left ${(overlay.tailMassLeft * 100).toFixed(2)}%` +
        (overlay.tailMassLeftSd !== null ? `±${(overlay.tailMassLeftSd * 100).toFixed(2)}` : "") +
        `, right ${(overlay.tailMassRight * 100).toFixed(2)}%` +
        (overlay.tailMassRightSd !== null ? `±${(overlay.tailMassRightSd * 100).toFixed(2)}` : "")
      : "";
  return (
    <span className="flex items-center gap-1.5 rounded border border-violet-500/40 bg-violet-500/10 px-1.5 py-0.5 text-[10px] font-medium text-violet-300">
      <span className="font-semibold tracking-wider">GRAPH</span>
      <span className="uppercase text-violet-400/90">{overlay.model}</span>
      <span className="text-violet-400/90">{overlay.priorSource}</span>
      {overlay.metrics !== null && (
        <span className="font-mono text-violet-200/90">
          RMS {(overlay.metrics.rmsVol * 100).toFixed(2)}% · in-band{" "}
          {(overlay.metrics.insideSpreadHitRate * 100).toFixed(0)}%
          {overlay.metrics.standardizedResidual !== null &&
            ` · ζ ${overlay.metrics.standardizedResidual.toFixed(2)}`}
        </span>
      )}
      {/* Functional posterior (R3 item 12): var-swap vol ± 1σ from the
          delta-method pushforward; tail masses ride the tooltip. */}
      {overlay.varSwapVol !== null && overlay.varSwapVolSd !== null && (
        <span
          className="font-mono text-violet-200/90"
          title={`Posterior var-swap vol ± 1σ (functional band)${tails}`}
        >
          · VS {(overlay.varSwapVol * 100).toFixed(1)}±{(overlay.varSwapVolSd * 100).toFixed(1)}%
        </span>
      )}
      <button
        title="Dismiss the graph-extrapolation overlay"
        className="ml-0.5 text-violet-400 hover:text-violet-200"
        onClick={onDismiss}
      >
        ✕
      </button>
    </span>
  );
}

export function FilterBadge({ diag }: { diag: FilterDiagnostics }) {
  // The measurement breakdown is an open Record — the rho key may be absent.
  const rho: number | undefined = diag.measurementBreakdown["rho"];
  return (
    <span
      title={`Observation filter (${diag.mode}) — gains per handle (${diag.handleNames.join(", ")})${
        diag.resetReason !== null ? ` · reset: ${diag.resetReason}` : ""
      }`}
      className={[
        "flex items-center gap-1.5 rounded border px-1.5 py-0.5 text-[10px] font-medium",
        diag.contaminated
          ? "border-amber-500/40 bg-amber-500/10 text-amber-300"
          : "border-teal-500/40 bg-teal-500/10 text-teal-300",
      ].join(" ")}
    >
      <span className="font-semibold tracking-wider">FILTER</span>
      <span className="font-mono">K {diag.gain.map((g) => g.toFixed(2)).join("/")}</span>
      {rho !== undefined && <span className="font-mono">ρ {rho.toFixed(2)}</span>}
      {diag.provenance !== null && (
        <span className={diag.contaminated ? "text-amber-400/90" : "text-teal-400/90"}>
          {diag.provenance}
        </span>
      )}
      {diag.contaminated && <span className="font-semibold">cont.</span>}
    </span>
  );
}
