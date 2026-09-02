// The short Options sections: Events, Graph prior, Workflow & data triggers,
// and Spot-vol dynamics. Grouped in one file (each is a screenful of controls
// at most); every feature-dependent knob renders only while its feature is on.
import { NumberRow, Segmented, Toggle } from "../OptionsControls";
import type { DynamicsRegime, OptionsSettings } from "../../state/useOptions";
import { numInput, rowLabel, sectionTitle } from "./shared";

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

/** Workflow & data: calibration/fetch triggers and streaming. Feature switches
 *  (Events, Var-swaps, Local-Vol) live in their thematic sections. */
export function WorkflowSection({ draft, patch, live }: SectionProps) {
  // With the live book streaming, chains and spots are read from the book:
  // the options-quotes timer has nothing to fetch (dimmed), while the spot
  // selector keeps a meaning — Real-time is what turns on live re-pricing
  // and the streaming refit loop, On-demand keeps the fit at its
  // calibration spot (market-following tickers still track the book).
  const streaming = draft.autoStream;
  return (
    <>
      <h3 className={sectionTitle}>Workflow &amp; data</h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Toggle
          label="Auto-calibrate"
          hint="On: lit nodes refit automatically after a fetch / on any change. Off: nodes go STALE until you press Calibrate (top bar)."
          checked={draft.autoCalibrate} disabled={!live}
          onChange={(v) => patch({ autoCalibrate: v })}
        />
        <Toggle
          label="Auto-roll prior on fetch"
          hint="On: a Snapshot fetch (Fetch ▸ Snapshot: quotes + spot) rolls each ticker's active prior to its latest SAVED snapshot before any auto-calibration (cheap — never a prev-close recalibration). Off: the active prior changes only via Fetch priors."
          checked={draft.autoRollPriorOnFetch} disabled={!live}
          onChange={(v) => patch({ autoRollPriorOnFetch: v })}
        />
        <Toggle
          label="Stream live book (Massive / Bloomberg)"
          hint="On: a streaming source auto-opens its real-time push feed — Massive's WebSocket book, or Bloomberg's //blp/mktdata subscriptions (quota-free: no metered bdp while streaming) — so Fetch / Calibrate / spot serve from the fast in-memory book instead of a metered / slow snapshot pull. Off: force the request path. No effect on Yahoo / Synthetic."
          checked={draft.autoStream} disabled={!live}
          onChange={(v) => patch({ autoStream: v })}
        />
        <div data-testid="spot-prices">
          <span className={`${rowLabel} mb-1 block`}>Spot prices</span>
          <Segmented
            options={[
              {
                id: "static", label: "On-demand",
                title: streaming
                  ? "The fit stays at its calibration spot; market-following tickers still take the book spot at the poll cadence"
                  : "Spots refresh only with Fetch ▸ Snapshot (or the legacy palette command)",
              },
              {
                id: "realtime", label: "Real-time",
                title: streaming
                  ? "The book spot re-prices the surface live and runs the streaming refit loop"
                  : "The scheduler polls live spots and transports the surface",
              },
            ]}
            value={draft.spotMode} disabled={!live}
            onChange={(v) => patch({ spotMode: v })}
          />
          {streaming && (
            <p className="mt-1 text-[10px] text-slate-500" data-testid="spot-streaming-note">
              Streaming: the book supplies spots either way — Real-time also re-prices the
              surface live and runs the streaming refit; On-demand keeps the fit at its
              calibration spot.
            </p>
          )}
          {draft.spotMode === "realtime" && (
            <div className="mt-2 space-y-2">
              <NumberRow
                label="Poll every (s)" value={draft.spotPollSeconds} step={1}
                disabled={!live} onChange={(v) => patch({ spotPollSeconds: v })}
              />
              {streaming && (
                <NumberRow
                  label="Stream refit every (s)" value={draft.streamRefitSeconds} step={1}
                  disabled={!live} onChange={(v) => patch({ streamRefitSeconds: v })}
                />
              )}
            </div>
          )}
        </div>
        <div data-testid="options-quotes">
          <span className={`${rowLabel} mb-1 block`}>Options quotes</span>
          <Segmented
            options={[
              { id: "on_demand", label: "On-demand", title: "Chains refresh only with Fetch ▸ Snapshot (or the legacy palette command)" },
              { id: "auto", label: "Auto", title: "The scheduler refetches chains on a timer (then auto-calibrates if enabled)" },
            ]}
            value={draft.optionsFetchMode} disabled={!live || streaming}
            onChange={(v) => patch({ optionsFetchMode: v })}
          />
          {streaming && (
            <p className="mt-1 text-[10px] text-slate-500" data-testid="quotes-streaming-note">
              Streaming: chains come from the live book — Fetch reads it and the streaming
              refit replaces this timer. Turn Stream live book off to use it (a source
              without a stream, such as Yahoo or Cboe, still follows it).
            </p>
          )}
          {!streaming && draft.optionsFetchMode === "auto" && (
            <div className="mt-2 space-y-2">
              <NumberRow
                label="Fetch every (min)" value={draft.optionsFetchMinutes} step={1}
                disabled={!live} onChange={(v) => patch({ optionsFetchMinutes: v })}
              />
              {/* V3.7 rider: the timer runs the unified Snapshot sequence
                  instead of the bare chain refetch. Off = legacy split timers. */}
              <Toggle
                label="Scheduler uses unified snapshot fetch"
                hint="On: each auto tick runs the same sequence as Fetch ▸ Snapshot (chains → spot transport → optional prior roll → auto-calibrate) instead of the bare chain refetch. Double-fire guard: a snapshot tick re-arms the real-time spot timer, so a spot poll due on the same tick is absorbed, never fired twice. Off: the legacy split timers (byte-identical)."
                checked={draft.schedulerUnifiedFetch} disabled={!live}
                onChange={(v) => patch({ schedulerUnifiedFetch: v })}
              />
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
        A spot move transports the surface (no recalibration); fetching fresh option
        quotes (or any change with Auto-calibrate off) marks lit nodes STALE until Calibrate.
        Data-age alerts watch how old the loaded LIVE quotes are (a stale delayed-feed
        book, a premarket fetch): past amber the market pill warns; past red the quality
        report fails publish-readiness and Calibrate shows a stale-data warning. The
        as-of mismatch gate does the same for a chain served off the selected as-of.
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
