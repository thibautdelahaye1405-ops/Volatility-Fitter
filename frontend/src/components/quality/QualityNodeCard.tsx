// Quality lens node card (UI SHELL v2, S3): ONE node's publish certificate —
// the active tab's (ticker, expiry) — as a compact label/value card beside
// the headline tiles. Every figure mirrors a column of the node table (same
// formatting, same tones, same tooltips), so the card reads as that row
// unrolled. StatusCell and the data-age helpers live here and are shared
// with the table / ticker rollup in QualityViewer.
import type { ReactNode } from "react";
import { fmtBp } from "../../lib/qualityFormat";
import { cardClass } from "../../lib/ui";
import type { QualityNode } from "../../state/useQuality";

/** Human age of the loaded live chain ("4m" / "13.5h"); "—" off-live. */
export function fmtAge(minutes: number | null): string {
  if (minutes === null) return "—";
  if (minutes < 90) return `${Math.round(minutes)}m`;
  const hours = minutes / 60;
  return hours < 48 ? `${hours.toFixed(1)}h` : `${(hours / 24).toFixed(1)}d`;
}

/** Display tone mirroring the backend's default 20/120-min thresholds (the
 *  authoritative gate is the backend-issued "stale data" issue). */
export function ageTone(minutes: number | null): string {
  if (minutes === null) return "text-slate-600";
  if (minutes >= 120) return "text-rose-400";
  if (minutes >= 20) return "text-amber-300";
  return "";
}

/** Publish status: ready (emerald) / arb (rose) / other issue (amber) /
 *  no fit (muted) — the issues list is the text, joined. */
export function StatusCell({ node }: { node: QualityNode }) {
  if (node.ready) {
    return (
      <span className="inline-flex items-center gap-1.5 text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> ready
      </span>
    );
  }
  const arb = !node.leeOk || !node.calendarOk;
  const tone = !node.hasFit ? "text-slate-500" : arb ? "text-rose-400" : "text-amber-300";
  const dot = !node.hasFit ? "bg-slate-600" : arb ? "bg-rose-500" : "bg-amber-400";
  return (
    <span className={`inline-flex items-center gap-1.5 ${tone}`} title={node.issues.join("; ")}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {node.issues.join(" · ")}
    </span>
  );
}

// Column tooltips shared verbatim with the node table headers.
export const EXTRAP_TIP =
  "Extrapolated-region arb over the time-value envelope (advisory): worst Durrleman g · calendar crossing bp. '—' = worthless past the quoted range.";
export const BELLY_TIP =
  "Belly butterfly certificate over the traded range: min Durrleman g @ its strike (rose = uncertified, blocks publish). ·R = certified repair refit.";
export const AGE_TIP = "Age of the loaded live quotes (— when not live)";

/** Belly cell tooltip: dip width when the certificate grid dips below -tol. */
export function bellyTitle(node: QualityNode): string {
  return node.negShare != null && node.negShare > 0
    ? `dip width: ${(node.negShare * 100).toFixed(1)}% of the certificate grid below -tol`
    : "belly certified (no grid point below -tol)";
}

/** Belly chip text "min g@k ·R" (·R = certified repair refit); "—" without a certificate. */
export function bellyText(node: QualityNode): string {
  if (!node.hasFit || node.bellyMinG == null) return "—";
  const at = node.bellyArgminK != null ? `@${node.bellyArgminK.toFixed(2)}` : "";
  return `${node.bellyMinG.toFixed(3)}${at}${node.bellyRepaired === true ? " ·R" : ""}`;
}

/** Extrapolated-region chip text "g · cal bp" with "—" for unmeasured halves. */
export function extrapText(node: QualityNode): string {
  if (!node.hasFit) return "—";
  const g = node.extrapMinG == null ? "—" : node.extrapMinG.toFixed(2);
  const cal = node.extrapCalBp == null ? "—" : node.extrapCalBp.toFixed(0);
  return `${g} · ${cal}`;
}

const chip = "rounded border px-1.5 py-0.5 text-[10px] leading-none";

/** One label → value line; `title` carries the column tooltip. */
function Row({
  label, title, tone, children,
}: { label: string; title?: string; tone?: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2" title={title}>
      <span className="shrink-0 text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={`min-w-0 text-right font-mono tabular-nums ${tone || "text-slate-300"}`}>
        {children}
      </span>
    </div>
  );
}

/** Advisory flags (var-swap quote, filter, wing order, vega floor, quarantine)
 *  as chips; "—" when the node carries none. */
function Flags({ node }: { node: QualityNode }) {
  const screened = Object.entries(node.screened ?? {}).filter(([, n]) => n > 0);
  const screenedTotal = screened.reduce((s, [, n]) => s + n, 0);
  const items: { text: string; tone: string; title: string }[] = [];
  if (node.varSwapQuoted) {
    items.push({ text: "VS", tone: "border-accent-500/40 text-accent-400", title: "var-swap quote active" });
  }
  if (node.filterActive) {
    items.push(
      node.filterContaminated
        ? { text: "F ·contaminated", tone: "border-amber-500/40 text-amber-300", title: "filter active (contaminated measurement)" }
        : { text: "F", tone: "border-slate-700 text-slate-400", title: "filter active" },
    );
  }
  if (node.wingOrderOk === false) {
    items.push({
      text: "wing order",
      tone: "border-rose-500/40 text-rose-400",
      title: "Wing-order clause violated (tail slopes out of order across expiries)",
    });
  }
  if ((node.vegaFloored ?? 0) > 0) {
    items.push({
      text: `vega-floored ${node.vegaFloored}`,
      tone: "border-amber-500/40 text-amber-300",
      title: "Kept quotes with Black vega below the diagnostic floor (IVs unreliable)",
    });
  }
  if (screenedTotal > 0) {
    items.push({
      text: `screened ${screenedTotal}`,
      tone: "border-slate-700 text-slate-400",
      title: `Quarantined quotes by reason: ${screened.map(([r, n]) => `${r} ${n}`).join(", ")}`,
    });
  }
  if (items.length === 0) return <span className="text-slate-600">—</span>;
  return (
    <span className="inline-flex flex-wrap justify-end gap-1">
      {items.map((i) => (
        <span key={i.text} className={`${chip} ${i.tone}`} title={i.title}>
          {i.text}
        </span>
      ))}
    </span>
  );
}

export interface QualityNodeCardProps {
  /** undefined: no active tab; null: the tab's node has no report row. */
  node: QualityNode | null | undefined;
  /** Publish RMS budget (bp) — RMS turns amber above it. */
  rmsBudgetBp: number;
  /** Universe fit mode (mid / bid-ask / haircut) — shown on the model line. */
  fitMode: string;
  /** Card heading ("SPY · 2026-09-18"). */
  label: string;
}

export default function QualityNodeCard({ node, rmsBudgetBp, fitMode, label }: QualityNodeCardProps) {
  const hint = (text: string) => <p className="py-2 text-slate-500">{text}</p>;
  return (
    <div className={`flex w-80 shrink-0 flex-col gap-1 p-3 text-[11px] ${cardClass}`}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="truncate text-sm font-semibold text-slate-100">{label}</h2>
        {node ? <StatusCell node={node} /> : null}
      </div>
      {node === undefined ? (
        hint("Open a node (Nodes pane) to see its certificate")
      ) : node === null || !node.hasFit ? (
        hint("No cached fit for this node")
      ) : (
        <>
          <Row label="Model">{node.model}{node.provenance === "loaded" ? " · loaded" : ""} · {node.nQuotes} q · {fitMode}</Row>
          <Row
            label="RMS · max IV"
            title="Fit RMS vs the publish budget (amber above it) · worst single-quote IV error"
          >
            <span className={node.rmsBp > rmsBudgetBp ? "text-amber-300" : ""}>{fmtBp(node.rmsBp)} bp</span>
            {" · "}{fmtBp(node.maxIvBp)} bp
          </Row>
          <Row label="ATM · skew">{(node.atmVol * 100).toFixed(1)}% · {node.skew.toFixed(3)}</Row>
          <Row
            label="Lee L/R"
            tone={!node.leeOk ? "text-rose-400" : undefined}
            title="Lee wing slopes (left/right); rose = beyond the Lee bound (blocks publish)"
          >
            {node.leeLeft.toFixed(2)}/{node.leeRight.toFixed(2)}
          </Row>
          <Row
            label="Cal viol"
            tone={!node.calendarOk ? "text-rose-400" : undefined}
            title="Sampled calendar violation vs the previous expiry · exact full-line ledger gap (book ch. 2); rose = calendar arb, blocks publish"
          >
            {node.calendarViolation > 0 ? node.calendarViolation.toExponential(1) : "0"}
            {node.ledgerGapMin != null ? ` · ledger ${node.ledgerGapMin.toExponential(1)}` : ""}
          </Row>
          <Row
            label="Extrap g · cal"
            tone={node.extrapOk === false || node.extrapCalOk === false ? "text-amber-300" : undefined}
            title={EXTRAP_TIP}
          >
            {extrapText(node)}
          </Row>
          <Row
            label="Belly g"
            tone={node.butterflyCertified === false ? "text-rose-400" : undefined}
            title={BELLY_TIP}
          >
            <span title={bellyTitle(node)}>{bellyText(node)}</span>
          </Row>
          <Row label="Flags">
            <Flags node={node} />
          </Row>
          <Row label="Data age" tone={ageTone(node.dataAgeMin)} title={AGE_TIP}>
            {fmtAge(node.dataAgeMin)}
          </Row>
        </>
      )}
    </div>
  );
}
