// New series… dialog (SERIES ARC S4 §3.1): mode tabs Historical · Live ·
// Import, the clock and ladder fields, the fit target, the lane composer,
// Estimate (instants · servable · harvest / calibration time · warnings)
// and Start (create or import, then start the job → onCreated(id)). Backend
// errors print inline; the buttons are inert while a request is in flight.
// Built on the shell's Dialog primitive; the spec mapping is newSeriesSpec.ts.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import Dialog from "../shell/Dialog";
import LaneComposer from "./LaneComposer";
import type { FitMode, LaneSpec, SeriesEstimate, SeriesMode } from "../../lib/seriesTypes";
import { SERIES_STEPS, STEP_LABELS } from "../../lib/seriesTypes";
import { fmtInstant, fmtSeconds } from "../../lib/seriesFormat";
import { buttonClass, chipClass, primaryButtonClass, selectClass } from "../../lib/ui";
import { createSeries, estimateSeries, fetchPresets, importSeries, startSeries } from "../../state/useSeries";
import {
  DAILY_STEPS, MAX_FRAMES, buildImport, buildSpec, defaultForm, defaultLanes, defaultName, validateForm,
} from "./newSeriesSpec";
import type { NewSeriesForm } from "./newSeriesSpec";

const MODES: { id: SeriesMode; label: string; hint: string }[] = [
  { id: "historical", label: "Historical", hint: "instants in the past, harvested now through the source's as-of path" },
  { id: "live", label: "Live", hint: "instants from now on, one frame per tick" },
  { id: "import", label: "Import", hint: "stored snapshots: the app's captures, a backtest store, a fixture directory" },
];
const inputClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-xs text-slate-200 outline-none focus:border-accent-500 " +
  "read-only:text-slate-500";
const labelClass = "text-[10px] uppercase tracking-wider text-slate-500";

function Field({ label, children, className = "" }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={`flex min-w-0 flex-col gap-1 ${className}`}>
      <span className={labelClass}>{label}</span>
      {children}
    </label>
  );
}

function EstimateCard({ estimate }: { estimate: SeriesEstimate }) {
  const n = estimate.instants.length;
  const servable = estimate.servable.filter(Boolean).length;
  const perLane = Object.entries(estimate.perLaneSeconds);
  return (
    <section className="rounded-lg border border-slate-800 bg-surface-950/60 p-3" data-testid="series-estimate">
      <dl className="grid grid-cols-[7rem_1fr] gap-y-1 font-mono text-[11px] text-slate-300">
        <dt className="text-slate-500">Instants</dt>
        <dd>{n}{n > 0 ? ` · ${fmtInstant(estimate.instants[0])} → ${fmtInstant(estimate.instants[n - 1])}` : ""}</dd>
        <dt className="text-slate-500">Servable</dt>
        <dd className={servable < n ? "text-amber-400" : ""}>{servable}/{n}</dd>
        <dt className="text-slate-500">Frames</dt>
        <dd>{estimate.nFrames}</dd>
        <dt className="text-slate-500">Harvest</dt>
        <dd>{fmtSeconds(estimate.harvestSeconds)}</dd>
        <dt className="text-slate-500">Calibrate</dt>
        <dd>
          {fmtSeconds(estimate.calibrateSeconds)}
          {perLane.length > 0 && (
            <span className="text-slate-500"> · {perLane.map(([id, s]) => `${id} ${fmtSeconds(s)}`).join(" · ")}</span>
          )}
        </dd>
      </dl>
      {estimate.warnings.length > 0 && (
        <ul className="mt-2 list-disc pl-4 text-[11px] text-amber-400">
          {estimate.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
    </section>
  );
}

export interface NewSeriesDialogProps {
  open: boolean;
  onClose: () => void;
  /** The tab's ticker (read-only in the form). */
  ticker: string;
  /** The session's fit target seeds the series'. */
  fitMode: FitMode;
  onCreated: (id: string) => void;
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : String(e));

export default function NewSeriesDialog({ open, onClose, ticker, fitMode, onCreated }: NewSeriesDialogProps) {
  const [form, setForm] = useState<NewSeriesForm>(() => defaultForm(fitMode));
  const [presets, setPresets] = useState<LaneSpec[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [lanes, setLanes] = useState<LaneSpec[]>([]);
  const [estimate, setEstimate] = useState<SeriesEstimate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"estimate" | "start" | null>(null);
  const patch = (p: Partial<NewSeriesForm>) => {
    setForm((f) => ({ ...f, ...p }));
    setEstimate(null); // an estimate describes ONE spec
  };

  // Each opening starts clean and re-reads the presets against the LIVE settings.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setForm(defaultForm(fitMode));
    setEstimate(null);
    setError(null);
    setBusy(null);
    setPresetsLoading(true);
    setPresetsError(null);
    fetchPresets()
      .then((p) => {
        if (cancelled) return;
        setPresets(p);
        setLanes(defaultLanes(p));
      })
      .catch((err: unknown) => {
        if (!cancelled) setPresetsError(messageOf(err));
      })
      .finally(() => {
        if (!cancelled) setPresetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, fitMode]);

  const onEstimate = async () => {
    const blocked = validateForm(form, lanes);
    if (blocked) { setError(blocked); return; }
    setBusy("estimate");
    setError(null);
    try {
      setEstimate(await estimateSeries(buildSpec(ticker, form, lanes)));
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const onStart = async () => {
    const blocked = validateForm(form, lanes);
    if (blocked) { setError(blocked); return; }
    setBusy("start");
    setError(null);
    try {
      const id = form.mode === "import"
        ? (await importSeries(buildImport(ticker, form, lanes))).id
        : (await createSeries(buildSpec(ticker, form, lanes))).id;
      await startSeries(id);
      onCreated(id);
      onClose();
    } catch (err: unknown) {
      setError(messageOf(err));
    } finally {
      setBusy(null);
    }
  };

  const inflight = busy !== null;
  const isImport = form.mode === "import";
  const daily = DAILY_STEPS.has(form.step);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New series"
      subtitle={`${ticker} — frames × lanes, calibrated through time`}
      width="w-[min(96vw,46rem)]"
      height="h-[min(90vh,46rem)]"
    >
      <div className="flex h-full flex-col">
        <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4 text-xs text-slate-300">
          <div className="flex flex-wrap items-center gap-1.5" role="tablist" aria-label="Mode">
            {MODES.map((m) => (
              <button key={m.id} role="tab" aria-selected={form.mode === m.id} title={m.hint} className={chipClass(form.mode === m.id)} onClick={() => patch({ mode: m.id })}>
                {m.label}
              </button>
            ))}
            <span className="ml-2 text-[11px] text-slate-500">{MODES.find((m) => m.id === form.mode)?.hint}</span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Field label="Name" className="col-span-2">
              <input className={inputClass} value={form.name} placeholder={defaultName(ticker, form)} onChange={(e) => patch({ name: e.target.value })} />
            </Field>
            <Field label="Ticker">
              <input className={inputClass} value={ticker} readOnly />
            </Field>
            {isImport ? (
              <>
                <Field label="Kind">
                  <select className={selectClass} value={form.importKind} onChange={(e) => patch({ importKind: e.target.value as NewSeriesForm["importKind"] })}>
                    <option value="captures">App captures</option>
                    <option value="store">Backtest store</option>
                    <option value="fixtures">Fixture directory</option>
                  </select>
                </Field>
                <Field label="Path" className="col-span-2">
                  <input className={inputClass} value={form.importPath} placeholder="a store file or a directory (blank = the app's own store)" onChange={(e) => patch({ importPath: e.target.value })} />
                </Field>
                <Field label="Max frames">
                  <input className={inputClass} type="number" min={1} max={MAX_FRAMES} value={form.importMaxFrames} placeholder="all" onChange={(e) => patch({ importMaxFrames: e.target.value })} />
                </Field>
              </>
            ) : (
              <>
                <Field label="Step">
                  <select className={selectClass} value={form.step} onChange={(e) => patch({ step: e.target.value as NewSeriesForm["step"] })}>
                    {SERIES_STEPS.map((s) => <option key={s} value={s}>{STEP_LABELS[s]}</option>)}
                  </select>
                </Field>
                <Field label="Count">
                  <input className={inputClass} type="number" min={1} max={MAX_FRAMES} value={form.count} onChange={(e) => patch({ count: Number(e.target.value) })} />
                </Field>
                <Field label={form.mode === "live" ? "Start (blank = now)" : "Start (blank = the latest instants)"}>
                  <input className={inputClass} type="datetime-local" value={form.start} onChange={(e) => patch({ start: e.target.value })} />
                </Field>
                {daily && (
                  <Field label="Time of day (New York)">
                    <input className={inputClass} type="time" value={form.timeOfDay} onChange={(e) => patch({ timeOfDay: e.target.value })} />
                  </Field>
                )}
                <Field label="Warm-up frames">
                  <input className={inputClass} type="number" min={0} max={64} value={form.warmupFrames} title="extra frames before the start, harvested only to seed the prior and filter lanes" onChange={(e) => patch({ warmupFrames: Number(e.target.value) })} />
                </Field>
                <label className="flex items-center gap-2 self-end pb-1.5 text-xs text-slate-300">
                  <input type="checkbox" checked={form.sessionOnly} onChange={(e) => patch({ sessionOnly: e.target.checked })} />
                  Session only
                </label>
              </>
            )}
            <Field label="Ladder">
              <select className={selectClass} value={form.policy} onChange={(e) => patch({ policy: e.target.value as NewSeriesForm["policy"] })}>
                <option value="pinned">Pinned (universe expiries)</option>
                <option value="term">Term</option>
                <option value="0dte">0DTE</option>
              </select>
            </Field>
            <Field label="Max expiries">
              <input className={inputClass} type="number" min={1} max={40} value={form.maxExpiries} placeholder="all" onChange={(e) => patch({ maxExpiries: e.target.value })} />
            </Field>
            <Field label="Fit target">
              <select className={selectClass} value={form.fitMode} onChange={(e) => patch({ fitMode: e.target.value as FitMode })}>
                <option value="mid">Mid</option>
                <option value="bidask">Bid-ask</option>
                <option value="haircut">Haircut</option>
              </select>
            </Field>
            <Field label="Note" className="col-span-2 sm:col-span-3">
              <input className={inputClass} value={form.note} onChange={(e) => patch({ note: e.target.value })} />
            </Field>
          </div>

          <section>
            <h3 className={`${labelClass} mb-1`}>Lanes</h3>
            <LaneComposer presets={presets} loading={presetsLoading} error={presetsError} lanes={lanes} onChange={(l) => { setLanes(l); setEstimate(null); }} />
          </section>

          {estimate && <EstimateCard estimate={estimate} />}
          {error && (
            <p role="alert" className="rounded border border-rose-500/40 bg-rose-500/10 px-2 py-1 text-[11px] text-rose-300">{error}</p>
          )}
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-slate-800 px-4 py-2.5">
          <span className="text-[11px] text-slate-500">
            {isImport
              ? "Import creates the frames from stored snapshots, then calibrates them."
              : "Estimate before Start: the instants, what the source can serve, and the time."}
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button className={buttonClass} onClick={onClose} disabled={inflight}>Cancel</button>
            {!isImport && (
              <button className={buttonClass} onClick={() => void onEstimate()} disabled={inflight || presetsLoading}>
                {busy === "estimate" ? "Estimating…" : "Estimate"}
              </button>
            )}
            <button className={primaryButtonClass} onClick={() => void onStart()} disabled={inflight || presetsLoading}>
              {busy === "start" ? "Starting…" : "Start"}
            </button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
