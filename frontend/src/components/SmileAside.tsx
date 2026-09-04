// Right-hand column of the Parametric lens (UI SHELL v2 wave 2): three
// stacked cards, top to bottom —
//   Spot move        follow the market spot or the scenario dial (transports
//                    every lens live); Recalibrate = the top-bar Calibrate for
//                    this ticker (same scope, same snapshot rule)
//   Variance swap    the var-swap quote editor (adds a calibration penalty;
//                    Options-gated)
//   Fit diagnostics  headline handles (ATM / skew / curvature / RMS); the
//                    secondary readouts (wings, Lee slopes, var-swap vol) at
//                    the expanded size; the displayed model + hyperparameters
//                    as a compact chip (full values in the tooltip)
// The three cards always fit the column without scrolling it: each has a
// compact / standard / expanded size and ONE shared focus (lib/asideSizes —
// expanding a card compresses the other two to a single row; folding it back
// returns all three to standard). Model selection itself lives in Options.
import { AsideBody, AsideCard, AsideHeader } from "./AsideCard";
import SpotPanel from "./SpotPanel";
import VarSwapPanel from "./VarSwapPanel";
import { ASIDE_PANELS } from "../lib/asideSizes";
import type { AsidePanelId } from "../lib/asideSizes";
import { formatPct } from "../lib/chartScale";
import { useAsideFocus } from "../state/useAsideFocus";
import { useSmileSession } from "../state/smileSession";
import { useWorkflowContext } from "../state/workflowContext";

/** Fixed-decimal string, or "—" for a null/NaN diagnostic (a degenerate or
 *  transported fit can yield a non-finite value, which JSON-serializes to null —
 *  a diagnostic readout must never crash on it). */
function fixed(v: number | null | undefined, digits: number): string {
  return v != null && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

interface DiagRow {
  label: string;
  value: string;
}

const DiagList = ({ rows }: { rows: DiagRow[] }) => (
  <dl className="divide-y divide-slate-800">
    {rows.map((row) => (
      <div key={row.label} className="flex items-center justify-between py-1.5">
        <dt className="text-xs text-slate-400">{row.label}</dt>
        <dd className="font-mono text-xs font-medium text-slate-100">{row.value}</dd>
      </div>
    ))}
  </dl>
);

const WITHOUT_VARSWAP: readonly AsidePanelId[] = ["spot", "diag"];

export default function SmileAside() {
  const {
    smile, source, spotReturn, spotState, setSpotReturn, setFollow, recalibrate,
    probeLive, spotNote, applyVarSwap, undoVarSwap, redoVarSwap,
  } = useSmileSession();
  const { workflow } = useWorkflowContext(); // the background job (Re-anchor progress)
  const live = source === "live";
  const varSwapShown = smile?.varSwap.enabled === true;
  const { sizeOf, toggle } = useAsideFocus(varSwapShown ? ASIDE_PANELS : WITHOUT_VARSWAP);
  const diagSize = sizeOf("diag");

  const info = smile?.modelInfo;
  const d = smile?.diagnostics;

  const headline: DiagRow[] = d
    ? [
        {
          label: "ATM vol",
          // Quote-derived 1σ error bar (the fit's own Jacobian + bid-ask noise).
          value: d.atmVolStd != null ? `${formatPct(d.atmVol)} ±${formatPct(d.atmVolStd, 2)}` : formatPct(d.atmVol),
        },
        { label: "Skew", value: fixed(d.skew, 3) },
        { label: "Curvature", value: fixed(d.curvature, 2) },
        { label: "RMS — smile", value: formatPct(d.rmsError, 2) },
        { label: "RMS — surface", value: formatPct(smile?.surfaceRmsError, 2) },
      ]
    : [];
  const secondary: DiagRow[] = d
    ? [
        { label: "A_L (left wing)", value: fixed(d.aLeft, 3) },
        { label: "A_R (right wing)", value: fixed(d.aRight, 3) },
        { label: "Lee slope L", value: fixed(d.leeLeft, 3) },
        { label: "Lee slope R", value: fixed(d.leeRight, 3) },
        { label: "Var-swap vol", value: formatPct(d.varSwapVol) },
      ]
    : [];

  // Fit-state markers (stale / loaded): inside the model chip at the standard
  // and expanded sizes, beside the title on the compact row.
  const markers = (
    <>
      {smile?.stale && <span className="font-sans text-[10px] font-semibold uppercase text-amber-400">stale</span>}
      {info?.provenance === "loaded" && (
        <span className="font-sans text-[10px] font-semibold uppercase text-emerald-400" title="Reinstalled from a snapshot file">loaded</span>
      )}
    </>
  );
  const chip = info && (
    <span
      title={info.params.map((p) => `${p.label}: ${p.value}`).join(" · ") || info.label}
      className="flex min-w-0 items-center gap-1.5 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-300"
    >
      {markers}
      {info.label}
      {info.params.length > 0 && (
        <span className="truncate font-medium text-slate-400">
          {info.params.map((p) => `${p.label} ${p.value}`).join(" · ")}
        </span>
      )}
    </span>
  );
  // Compact row: the two numbers a glance needs (the model chip returns at
  // the standard size — the row is too narrow for both).
  const diagSummary = d ? `ATM ${formatPct(d.atmVol)} · RMS ${formatPct(d.rmsError, 2)}` : "Awaiting data…";

  return (
    <aside className="flex min-h-0 w-72 shrink-0 flex-col gap-3 overflow-y-auto">
      {/* 1. Spot move: follow the market or the scenario (no recalibration);
          Recalibrate = Calibrate for this ticker. Applies across every lens,
          not just Smile. */}
      <AsideCard id="spot" size={sizeOf("spot")}>
        <SpotPanel
          spotReturn={spotReturn}
          spotState={spotState}
          onSpotReturn={setSpotReturn}
          onFollow={(f) => void setFollow(f)}
          onCalibrate={(scope) => void recalibrate(scope)}
          onProbeLive={() => void probeLive()}
          calib={workflow.calib}
          note={spotNote}
          disabled={!live}
          disabledReason={!live ? "requires live backend" : undefined}
          size={sizeOf("spot")}
          onToggleSize={() => toggle("spot")}
        />
      </AsideCard>

      {/* 2. Variance-swap quote: adds a calibration penalty (Options-gated). */}
      {varSwapShown && smile && (
        <AsideCard id="varswap" size={sizeOf("varswap")}>
          <VarSwapPanel
            info={smile.varSwap}
            live={live}
            onSet={(level) => void applyVarSwap("set", level)}
            onExclude={() => void applyVarSwap("exclude")}
            onInclude={() => void applyVarSwap("include")}
            onRemove={() => void applyVarSwap("remove")}
            onUndo={() => void undoVarSwap()}
            onRedo={() => void redoVarSwap()}
            onReset={() => void applyVarSwap("reset")}
            size={sizeOf("varswap")}
            onToggleSize={() => toggle("varswap")}
          />
        </AsideCard>
      )}

      {/* 3. Fit diagnostics: headline handles; wings / Lee / var-swap vol when expanded */}
      <AsideCard id="diag" size={diagSize}>
        <AsideHeader
          title="Fit diagnostics"
          size={diagSize}
          onToggle={() => toggle("diag")}
          badge={diagSize === "S" ? markers : undefined}
          right={chip}
          summary={diagSummary}
          expandTip="wings, Lee slopes, var-swap vol"
        />
        {diagSize !== "S" && (
          <AsideBody>
            <p className="mb-2 text-[11px] text-slate-500">
              {smile ? `Current calibration · ${smile.ticker} ${smile.expiry}` : "Awaiting data…"}
            </p>
            <DiagList rows={headline} />
            {diagSize === "L" && secondary.length > 0 && (
              <div className="mt-2 border-t border-slate-800 pt-1">
                <p className="pt-1 text-[10px] uppercase tracking-wide text-slate-600">wings · Lee · var-swap</p>
                <DiagList rows={secondary} />
              </div>
            )}
          </AsideBody>
        )}
      </AsideCard>
    </aside>
  );
}
