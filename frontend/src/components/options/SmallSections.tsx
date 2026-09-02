// The short Options sections: Events, Graph prior, Workflow & data triggers,
// and Spot-vol dynamics. Grouped in one file (each is a screenful of controls
// at most); every feature-dependent knob renders only while its feature is on.
import { NumberRow, Segmented, Toggle } from "../OptionsControls";
import type { AutoUpdate, DynamicsRegime, OptionsSettings } from "../../state/useOptions";
import { numInput, rowLabel, sectionTitle } from "./shared";

/** Floor of the "Spot + quotes" cadence (mirrors the backend): a full chain per tick. */
const SNAPSHOT_FLOOR_SECONDS = 15;

interface SectionProps {
  draft: OptionsSettings;
  patch: (p: Partial<OptionsSettings>) => void;
  live: boolean;
}

/** Events: the variance-clock feature switch + its normalization. Per-ticker
 *  event calendars are edited in Parametric ▸ Term. */
export function EventsSection({ draft, patch, live }: SectionProps) {
  return (
    <>
      <h3 className={sectionTitle}>Events</h3>
      <Toggle
        label="Event variance clock"
        hint="Events add day-weights to the variance clock, so an event before an expiry lowers its IV (price-preserving). Affects all fits, LV, term and tables."
        checked={draft.eventsEnabled} disabled={!live}
        onChange={(v) => patch({ eventsEnabled: v })}
      />
      {draft.eventsEnabled && (
        <Toggle
          label="Normalize events"
          hint="Rescale all days so the 1Y weight budget stays 365 (1Y vols unchanged; events redistribute variance within the year)"
          checked={draft.normalizeEvents} disabled={!live}
          onChange={(v) => patch({ normalizeEvents: v })}
        />
      )}
      <p className="mt-1 text-[10px] text-slate-600">
        Per-ticker event calendars (dates &amp; weights) are edited in the
        Parametric workspace's Term sub-tab.
      </p>
      <Toggle
        label="Intraday clock (0DTE research)"
        hint="Value each expiry from the chain snapshot's timestamp to its exact settlement instant (NYSE sessions, AM/PM, half-days), with variance accruing on the session-weighted profile below. Off = day-granular maturities, byte-identical fits."
        checked={draft.intradayClock} disabled={!live}
        onChange={(v) => patch({ intradayClock: v })}
      />
      {draft.intradayClock && (
        <div className="space-y-2">
          <NumberRow
            label="Session variance share" value={draft.sessionVarShare}
            step={0.05} disabled={!live}
            onChange={(v) => patch({ sessionVarShare: v })}
          />
          <NumberRow
            label="Non-trading day weight" value={draft.nonTradingWeight}
            step={0.1} disabled={!live}
            onChange={(v) => patch({ nonTradingWeight: v })}
          />
          <p className="mt-1 text-[10px] text-slate-600">
            Share 0.271 (= 6.5/24) is the flat-density legacy convention;
            ~0.7–0.9 concentrates variance in trading hours (remaining
            minutes for a live 0DTE, cheap overnight). Weight 1 prices a
            weekend at three full days; lower it to study the weekend effect.
          </p>
        </div>
      )}
    </>
  );
}

/** Graph prior defaults: seeds the Graph Viewer's solver panel. */
export function GraphSection({ draft, patch, live }: SectionProps) {
  return (
    <>
      <h3 className={sectionTitle}>Graph</h3>
      <div className="space-y-2">
        <label className="flex items-center justify-between gap-2 text-xs text-slate-400"
          title="Default propagation operator (message arc): smooth field = the legacy increment prior, byte-identical; precision messages = the pairwise relation-factor operator. Hybrid is config-only until validated.">
          <span>Propagation operator</span>
          <select
            value={draft.graphPropagationMode}
            disabled={!live}
            onChange={(e) =>
              patch({
                graphPropagationMode: e.target
                  .value as typeof draft.graphPropagationMode,
              })
            }
            className="rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <option value="smooth_field">smooth field</option>
            <option value="precision_messages">precision messages</option>
          </select>
        </label>
        <NumberRow label="κ prior strength" value={draft.graphKappaScale} step={0.1} disabled={!live}
          onChange={(v) => patch({ graphKappaScale: v })} />
        <NumberRow label="η reach" value={draft.graphEtaScale} step={0.1} disabled={!live}
          onChange={(v) => patch({ graphEtaScale: v })} />
        <NumberRow label="λ OT flux (0 = off)" value={draft.graphLambdaScale} step={0.1} disabled={!live}
          onChange={(v) => patch({ graphLambdaScale: v })} />
        <NumberRow label="ν OT source" value={draft.graphNu} step={0.05} disabled={!live}
          onChange={(v) => patch({ graphNu: v })} />
      </div>
      <p className="mt-1 text-[10px] text-slate-600">
        Default solver parameters for the graph extrapolator — seed the Graph
        Viewer's solver panel (κ = stiffness toward the baseline; the
        κ/η/λ/ν knobs drive the smooth-field operator only). Message
        relations are edited in the Universe ▸ Graph workspace.
      </p>
    </>
  );
}

/** Workflow & data: the trigger model (calibration on demand or continuous),
 *  Auto-update without a live stream, streaming, and the freshness policy.
 *  Feature switches (Events, Var-swaps, Local-Vol) live in their thematic
 *  sections. */
export function WorkflowSection({ draft, patch, live }: SectionProps) {
  // The model: a calibration always prices spot and quotes from ONE snapshot
  // (a fetch, or a synchronous read of the streaming book); a spot-only update
  // only transports the surface. With the book streaming, spot and quotes flow
  // continuously and the Auto-update timer is not used (dimmed); "Freeze fit
  // while streaming" holds the fit at its calibration spot instead.
  const streaming = draft.autoStream;
  const setAutoUpdate = (v: AutoUpdate) =>
    patch(
      v === "snapshot" && draft.autoUpdateSeconds < SNAPSHOT_FLOOR_SECONDS
        ? { autoUpdate: v, autoUpdateSeconds: SNAPSHOT_FLOOR_SECONDS }
        : { autoUpdate: v },
    );
  const setSeconds = (v: number) =>
    patch({ autoUpdateSeconds: draft.autoUpdate === "snapshot" ? Math.max(SNAPSHOT_FLOOR_SECONDS, v) : v });
  return (
    <>
      <h3 className={sectionTitle}>Workflow &amp; data</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Toggle
          label="Auto-calibrate"
          hint="On: continuous calibration — lit nodes refit whenever a quotes + spot snapshot arrives (a fetch, the Auto-update snapshot tick, the streaming refit) and on any edit; a spot-only update only transports. Off: on-demand — nodes go STALE until you press Calibrate."
          checked={draft.autoCalibrate} disabled={!live}
          onChange={(v) => patch({ autoCalibrate: v })}
        />
        <Toggle
          label="Auto-roll prior on fetch"
          hint="On: a Snapshot fetch (Fetch ▸ Snapshot: quotes + spot) rolls each ticker's active prior to its latest SAVED snapshot before any auto-calibration (cheap — never a prev-close recalibration). Off: the active prior changes only via Fetch priors."
          checked={draft.autoRollPriorOnFetch} disabled={!live}
          onChange={(v) => patch({ autoRollPriorOnFetch: v })}
        />
        <div data-testid="auto-update">
          <span className={`${rowLabel} mb-1 block`}>Auto-update (without a live stream)</span>
          <Segmented
            options={[
              { id: "off", label: "Off", title: "Manual Fetch only" },
              { id: "spot", label: "Spot only", title: "Probe the spot every interval and transport the surface — never a refit" },
              { id: "snapshot", label: "Spot + quotes", title: "Fetch quotes + spot every interval (the Snapshot sequence), then auto-calibrate if it is on" },
            ]}
            value={draft.autoUpdate} disabled={!live || streaming}
            onChange={setAutoUpdate}
          />
          {streaming ? (
            <p className="mt-1 text-[10px] text-slate-500" data-testid="update-streaming-note">
              Stream live book is on: on a streaming source spot and quotes flow continuously
              and this timer is not used; a source without a stream (Yahoo, Cboe) still
              follows it.
            </p>
          ) : draft.autoUpdate !== "off" && (
            <div className="mt-2">
              <NumberRow
                label="Every (s)" value={draft.autoUpdateSeconds} step={1}
                disabled={!live} onChange={setSeconds}
              />
              {draft.autoUpdate === "snapshot" && (
                <p className="mt-1 text-[10px] text-slate-500">
                  {SNAPSHOT_FLOOR_SECONDS} s minimum: every tick downloads a full chain.
                </p>
              )}
            </div>
          )}
        </div>
        <div>
          <Toggle
            label="Stream live book (Massive / Bloomberg)"
            hint="On: a streaming source auto-opens its real-time push feed — Massive's WebSocket book, or Bloomberg's //blp/mktdata subscriptions (quota-free: no metered bdp while streaming) — and spot + quotes flow continuously: the surface transports live and, with Auto-calibrate on, refits every N s. Off: force the request path (Auto-update applies). No effect on Yahoo / Synthetic."
            checked={draft.autoStream} disabled={!live}
            onChange={(v) => patch({ autoStream: v })}
          />
          {streaming && (
            <div className="mt-1 space-y-2">
              <Toggle
                label="Freeze fit while streaming"
                hint="On: while the book streams the fit stays at its calibration spot — no live transport, no streaming refit (Fetch, Calibrate and the live quotes still read the book; the Spot card's dial stays free). Off: the book spot re-prices the surface live and, with Auto-calibrate on, refits every N s."
                checked={draft.streamFreezeFit} disabled={!live}
                onChange={(v) => patch({ streamFreezeFit: v })}
              />
              {!draft.streamFreezeFit && (
                <NumberRow
                  label="Stream refit every (s)" value={draft.streamRefitSeconds} step={1}
                  disabled={!live} onChange={(v) => patch({ streamRefitSeconds: v })}
                />
              )}
            </div>
          )}
        </div>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <NumberRow
          label="Data age · amber (min)" value={draft.dataAgeAmberMin} step={5}
          disabled={!live} onChange={(v) => patch({ dataAgeAmberMin: v })}
        />
        <NumberRow
          label="Data age · red (min)" value={draft.dataAgeRedMin} step={15}
          disabled={!live} onChange={(v) => patch({ dataAgeRedMin: v })}
        />
      </div>
      {/* Data-freshness policy beside the age thresholds: the per-node
          effective as-of (Nodes pane "≠ as-of") promoted to a readiness /
          publish gate. Off = advisory; never touches a fit. */}
      <Toggle
        label="As-of mismatch gate"
        hint="On: a node whose served chain is NOT in the requested as-of session (the Nodes pane's ≠ as-of — a live-only source ignoring a close request, a feed stamping another session) gets the Quality issue 'as-of mismatch' (not ready) and the publish export blocks on it. Off: advisory only — the Nodes pane and the Quality card still flag it. A data issue, never an arb flag; display/report policy only."
        checked={draft.asOfMismatchGate} disabled={!live}
        onChange={(v) => patch({ asOfMismatchGate: v })}
      />
      <p className="mt-3 text-[11px] text-slate-500">
        A spot move — from the stream, a timer or a Fetch — transports the surface and never
        recalibrates. Option quotes arrive by fetch or stream; a calibration always prices spot
        and quotes from the same snapshot, and fresh quotes with Auto-calibrate off mark lit
        nodes STALE until Calibrate. Data-age alerts watch how old the loaded LIVE quotes are
        (a stale delayed-feed book, a premarket fetch): past amber the market pill warns; past
        red the quality report fails publish-readiness and Calibrate shows a stale-data
        warning. The as-of mismatch gate does the same for a chain served off the selected as-of.
      </p>
    </>
  );
}

const REGIMES: { id: DynamicsRegime; label: string; title: string }[] = [
  { id: "sticky_moneyness", label: "Mny", title: "Sticky moneyness / delta" },
  { id: "sticky_strike", label: "Strike", title: "Sticky strike (smile fixed in absolute strike)" },
  { id: "sticky_local_vol", label: "LV", title: "Sticky local-vol (SSR = 2 short-end rule)" },
  { id: "sticky_local_vol_grid", label: "LV grid", title: "Sticky local-vol grid (exact Dupire reprice)" },
  { id: "custom", label: "SSR", title: "Custom skew-stickiness ratio (set below)" },
];

/** Spot-vol dynamics: scenario regime; the SSR value shows only for "custom". */
export function DynamicsSection({ draft, patch, live }: SectionProps) {
  return (
    <>
      <h3 className={sectionTitle}>Spot-vol dynamics</h3>
      <Segmented
        options={REGIMES} value={draft.dynamicsRegime} disabled={!live}
        onChange={(v) => patch({ dynamicsRegime: v })}
      />
      {draft.dynamicsRegime === "custom" && (
        <div className="mt-2 flex items-center justify-between">
          <span className={rowLabel} title="Custom skew-stickiness ratio (used when the regime is SSR)">
            SSR value
          </span>
          <input
            type="number" step={0.1} min={0} value={draft.ssr} disabled={!live}
            onChange={(e) => patch({ ssr: Number(e.target.value) })}
            className={numInput}
          />
        </div>
      )}
      <p className="mt-1 text-[10px] text-slate-600">
        Drives the Parametric spot-scenario overlay (its aside has the spot slider only).
      </p>
    </>
  );
}
