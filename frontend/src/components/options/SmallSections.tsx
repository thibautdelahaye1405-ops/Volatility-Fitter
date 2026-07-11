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
        Viewer's solver panel (κ = stiffness toward the baseline). Per-edge
        weights are edited in the Universe ▸ Graph workspace.
      </p>
    </>
  );
}

/** Workflow & data: calibration/fetch triggers and streaming. Feature switches
 *  (Events, Var-swaps, Local-Vol) live in their thematic sections. */
export function WorkflowSection({ draft, patch, live }: SectionProps) {
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
          label="Stream live book (Massive)"
          hint="On: a streaming source (Massive) auto-opens its real-time WS book so Fetch / Calibrate / spot serve from the fast in-memory book instead of the slow REST snapshot. Off: force REST. No effect on Yahoo / Bloomberg / Synthetic."
          checked={draft.autoStream} disabled={!live}
          onChange={(v) => patch({ autoStream: v })}
        />
        <div>
          <span className={`${rowLabel} mb-1 block`}>Spot prices</span>
          <Segmented
            options={[
              { id: "static", label: "On-demand", title: "Fetch spots only via the 'Fetch spots' button" },
              { id: "realtime", label: "Real-time", title: "The scheduler polls live spots and transports the surface" },
            ]}
            value={draft.spotMode} disabled={!live}
            onChange={(v) => patch({ spotMode: v })}
          />
          {draft.spotMode === "realtime" && (
            <div className="mt-2">
              <NumberRow
                label="Poll every (s)" value={draft.spotPollSeconds} step={1}
                disabled={!live} onChange={(v) => patch({ spotPollSeconds: v })}
              />
            </div>
          )}
        </div>
        <div>
          <span className={`${rowLabel} mb-1 block`}>Options quotes</span>
          <Segmented
            options={[
              { id: "on_demand", label: "On-demand", title: "Fetch chains only via the 'Fetch Options Quotes' button" },
              { id: "auto", label: "Auto", title: "The scheduler refetches chains on a timer (then auto-calibrates if enabled)" },
            ]}
            value={draft.optionsFetchMode} disabled={!live}
            onChange={(v) => patch({ optionsFetchMode: v })}
          />
          {draft.optionsFetchMode === "auto" && (
            <div className="mt-2">
              <NumberRow
                label="Fetch every (min)" value={draft.optionsFetchMinutes} step={1}
                disabled={!live} onChange={(v) => patch({ optionsFetchMinutes: v })}
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
      <p className="mt-3 text-[11px] text-slate-500">
        A spot move transports the surface (no recalibration); fetching fresh option
        quotes (or any change with Auto-calibrate off) marks lit nodes STALE until Calibrate.
        Data-age alerts watch how old the loaded LIVE quotes are (a stale delayed-feed
        book, a premarket fetch): past amber the market pill warns; past red the quality
        report fails publish-readiness and Calibrate shows a stale-data warning.
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
