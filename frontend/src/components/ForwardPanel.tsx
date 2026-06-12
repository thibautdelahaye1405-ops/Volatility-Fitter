// "Forward" panel for the Smile Viewer diagnostics aside.
//
// Implements the per-expiry forward fitting mode (ROADMAP [REQ 2026-06-12]):
// the active forward of the selected expiry can come from put-call parity
// regression, from the theoretical carry model, or from a manual override.
// The panel shows the three candidates side by side (GET /forwards/{ticker}),
// lets the user switch the mode / type a manual level (PUT
// /forwards/{ticker}/{expiry}), and exposes the carry inputs r and q that
// feed the theoretical forward (GET/PUT /settings/market/{ticker}). Applying
// triggers the session's reload() so the current smile refits.
import { useEffect, useState } from "react";
import { api } from "../state/api";

/** Forward source selector — mirror of the backend ForwardMode enum. */
export type ForwardMode = "parity" | "theoretical" | "manual";

/** One expiry's forward diagnostics (backend ForwardEntry schema). */
export interface ForwardEntry {
  expiry: string;
  t: number;
  parityForward: number | null;
  parityDiscount: number | null;
  parityResidualRms: number | null;
  parityNStrikes: number | null;
  parityNOutliers: number | null;
  theoForward: number;
  theoDiscount: number;
  mode: ForwardMode;
  manualForward: number | null;
  activeForward: number;
  activeDiscount: number;
  activeSource: string;
}

/** Response of GET /forwards/{ticker}. */
export interface ForwardsResponse {
  ticker: string;
  spot: number;
  exerciseStyle: "european" | "american";
  entries: ForwardEntry[];
}

/** One discrete dividend (part of MarketSettings). */
export interface DividendItem {
  exDate: string;
  amount: number;
}

/** Per-ticker market/carry settings (GET/PUT /settings/market/{ticker}). */
export interface MarketSettings {
  rate: number;
  dividendMode: "continuous" | "discrete_absolute" | "discrete_proportional" | "mixed";
  dividendYield: number;
  dividends: DividendItem[];
  switchYears: number;
}

const MODE_OPTIONS: { id: ForwardMode; label: string; title: string }[] = [
  { id: "parity", label: "Parity", title: "Put-call parity regression over liquid strikes" },
  { id: "theoretical", label: "Theo", title: "Carry model: spot, rate r, dividends" },
  { id: "manual", label: "Manual", title: "User-supplied forward level" },
];

/** Parse a text field into a finite number, or null when invalid/empty. */
function parseNum(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

/** Equity-level forward formatting; em-dash for missing values. */
function fmtFwd(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : value.toFixed(2);
}

interface ForwardPanelProps {
  /** Greyed out in mock mode (forwards live on the backend). */
  disabled: boolean;
  /** Currently selected underlying / expiry (from the smile session). */
  ticker: string;
  expiry: string;
  /** Refetch the current smile after the forward changed server-side. */
  onApplied: () => void;
}

export default function ForwardPanel({
  disabled,
  ticker,
  expiry,
  onApplied,
}: ForwardPanelProps) {
  // `entry` / `market` mirror the backend; the draft fields are panel state.
  const [entry, setEntry] = useState<ForwardEntry | null>(null);
  const [market, setMarket] = useState<MarketSettings | null>(null);
  const [draftMode, setDraftMode] = useState<ForwardMode>("theoretical");
  const [draftManual, setDraftManual] = useState("");
  const [draftRate, setDraftRate] = useState("");
  const [draftQ, setDraftQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Sync all drafts to a freshly fetched server state. */
  const adopt = (e: ForwardEntry | null, mkt: MarketSettings | null) => {
    setEntry(e);
    if (mkt !== null) {
      setMarket(mkt);
      setDraftRate(String(mkt.rate));
      setDraftQ(String(mkt.dividendYield));
    }
    if (e !== null) {
      setDraftMode(e.mode);
      setDraftManual((e.manualForward ?? e.activeForward).toFixed(2));
    }
  };

  // (Re)load forwards + market settings whenever the node changes.
  useEffect(() => {
    if (disabled || ticker === "" || expiry === "") return;
    const controller = new AbortController();
    Promise.all([
      api.get<ForwardsResponse>(`/forwards/${ticker}`, { signal: controller.signal }),
      api.get<MarketSettings>(`/settings/market/${ticker}`, { signal: controller.signal }),
    ])
      .then(([fwd, mkt]) => {
        adopt(fwd.entries.find((en) => en.expiry === expiry) ?? null, mkt);
        setError(null);
      })
      .catch(() => {
        /* aborted or transient; the Apply PUT will surface real failures */
      });
    return () => controller.abort();
  }, [disabled, ticker, expiry]);

  // ---- draft validation / dirtiness --------------------------------------
  const manualNum = parseNum(draftManual);
  const manualValid = manualNum !== null && manualNum > 0;
  const rateNum = parseNum(draftRate);
  const qNum = parseNum(draftQ);

  const carryDirty =
    market !== null &&
    rateNum !== null &&
    qNum !== null &&
    (rateNum !== market.rate || qNum !== market.dividendYield);
  const forwardDirty =
    entry !== null &&
    (draftMode !== entry.mode ||
      (draftMode === "manual" && manualValid && manualNum !== entry.manualForward));
  const dirty = carryDirty || forwardDirty;

  const inputError =
    rateNum === null || qNum === null
      ? "carry inputs must be numbers"
      : draftMode === "manual" && !manualValid
        ? "manual forward must be > 0"
        : null;
  const canApply = !disabled && !busy && dirty && inputError === null;

  /** Switch the draft mode; seed the manual field when first entered. */
  const selectMode = (mode: ForwardMode) => {
    setDraftMode(mode);
    if (mode === "manual" && draftManual.trim() === "" && entry !== null) {
      setDraftManual((entry.manualForward ?? entry.activeForward).toFixed(2));
    }
  };

  /** PUT carry and/or mode changes, then refetch forwards and refit. */
  const apply = async () => {
    if (!canApply) return;
    setBusy(true);
    setError(null);
    try {
      if (carryDirty && market !== null && rateNum !== null && qNum !== null) {
        // Preserve every other MarketSettings field as received.
        const mkt = await api.put<MarketSettings>(`/settings/market/${ticker}`, {
          body: { ...market, rate: rateNum, dividendYield: qNum },
        });
        setMarket(mkt);
        setDraftRate(String(mkt.rate));
        setDraftQ(String(mkt.dividendYield));
      }
      if (forwardDirty) {
        await api.put<ForwardEntry>(`/forwards/${ticker}/${expiry}`, {
          body: {
            mode: draftMode,
            manualForward: draftMode === "manual" ? manualNum : null,
          },
        });
      }
      const fwd = await api.get<ForwardsResponse>(`/forwards/${ticker}`);
      adopt(fwd.entries.find((en) => en.expiry === expiry) ?? null, null);
      setFlash(true);
      setTimeout(() => setFlash(false), 1200);
      onApplied();
    } catch {
      // Keep the draft dirty so the user can retry.
      setError("update rejected by backend");
    } finally {
      setBusy(false);
    }
  };

  // ---- presentation -------------------------------------------------------
  const paritySub =
    entry !== null && entry.parityResidualRms !== null
      ? `rms ${entry.parityResidualRms.toFixed(2)} · n ${entry.parityNStrikes ?? 0} · drop ${entry.parityNOutliers ?? 0}`
      : "—";

  const cellLabel = "text-[10px] uppercase tracking-wider text-slate-500";
  const cellValue = "font-mono text-xs font-medium text-slate-100";
  const inputClass =
    "w-16 rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 " +
    "text-right font-mono text-[11px] text-slate-200 outline-none " +
    "hover:border-slate-600 focus:border-accent-500 " +
    "disabled:cursor-not-allowed disabled:opacity-50";

  return (
    <section
      className={disabled ? "opacity-40" : ""}
      title={disabled ? "requires live backend" : undefined}
    >
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Forward</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        Per-expiry forward source · refits this smile
      </p>

      {/* Side-by-side candidates: parity / theoretical / active */}
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div title="Parity-implied forward (regression diagnostics below)">
          <div className={cellLabel}>Parity</div>
          <div className={cellValue}>{fmtFwd(entry?.parityForward)}</div>
          <div className="text-[9px] leading-tight text-slate-500">{paritySub}</div>
        </div>
        <div title="Theoretical forward from the carry model">
          <div className={cellLabel}>Theo</div>
          <div className={cellValue}>{fmtFwd(entry?.theoForward)}</div>
        </div>
        <div title="Forward currently used by the fit">
          <div className={cellLabel}>Active</div>
          <div className={cellValue}>{fmtFwd(entry?.activeForward)}</div>
          <span className="inline-block rounded border border-slate-700 bg-surface-800 px-1 py-px text-[9px] text-slate-400">
            {entry?.activeSource ?? "—"}
          </span>
        </div>
      </div>

      {/* Mode segmented control (draft state, applied via the button) */}
      <div className="mb-3 flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
        {MODE_OPTIONS.map((m) => {
          const unavailable = m.id === "parity" && entry !== null && entry.parityForward === null;
          return (
            <button
              key={m.id}
              title={unavailable ? "no parity estimate for this expiry" : m.title}
              disabled={disabled || unavailable}
              onClick={() => selectMode(m.id)}
              className={[
                "flex-1 px-2 py-1 text-[11px] font-medium transition-colors disabled:cursor-not-allowed",
                m.id === draftMode
                  ? "bg-accent-600/25 text-accent-400"
                  : unavailable
                    ? "text-slate-600"
                    : "text-slate-400 enabled:hover:text-slate-200",
              ].join(" ")}
            >
              {m.label}
            </button>
          );
        })}
      </div>

      {/* Manual forward level (only editable in manual mode) */}
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs text-slate-400">Manual forward</span>
        <input
          type="text"
          inputMode="decimal"
          value={draftManual}
          disabled={disabled || draftMode !== "manual"}
          onChange={(e) => setDraftManual(e.target.value)}
          className={[
            inputClass,
            draftMode === "manual" && !manualValid ? "border-amber-500/70" : "",
          ].join(" ")}
        />
      </div>

      {/* Carry inputs feeding the theoretical forward */}
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-slate-400" title="Continuous rate r and dividend yield q">
          Carry r / div q
        </span>
        <span className="flex gap-1.5">
          <input
            type="text"
            inputMode="decimal"
            value={draftRate}
            disabled={disabled}
            onChange={(e) => setDraftRate(e.target.value)}
            className={[inputClass, rateNum === null ? "border-amber-500/70" : ""].join(" ")}
          />
          <input
            type="text"
            inputMode="decimal"
            value={draftQ}
            disabled={disabled}
            onChange={(e) => setDraftQ(e.target.value)}
            className={[inputClass, qNum === null ? "border-amber-500/70" : ""].join(" ")}
          />
        </span>
      </div>
      <p className="mb-3 text-[10px] text-slate-600">feeds Theo forward · de-Am carry</p>

      {/* Apply errors / validation hints */}
      {(error !== null || (inputError !== null && dirty)) && (
        <p className="mb-2 text-[10px] text-amber-400">{error ?? inputError}</p>
      )}

      <button
        onClick={() => void apply()}
        disabled={!canApply}
        className={[
          "w-full rounded-md border px-2 py-1.5 text-[11px] font-medium transition-colors",
          flash
            ? "border-emerald-600/60 bg-emerald-600/15 text-emerald-400"
            : canApply
              ? "border-accent-600/60 bg-accent-600/15 text-accent-400 hover:bg-accent-600/25"
              : "cursor-not-allowed border-slate-700 text-slate-600",
        ].join(" ")}
      >
        {flash ? "Applied ✓" : busy ? "Refitting…" : "Apply & refit"}
      </button>
    </section>
  );
}
