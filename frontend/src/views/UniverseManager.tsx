// Universe manager (the "Manage universe" dialog since UI SHELL v2): curate
// the tickers the app works on.
//
// One mental model, one card: every ticker row shows its expiry chips with the
// lit/dark designation toggled directly on the chips (the shared lit map —
// nodes pane + Graph canvas follow), its DATA SOURCE select (the multi-source
// engine, state/tickerSources.ts: a ticker pinned to another source fetches,
// streams and captures from it; the rest follow the universe source), ▸
// expands the expiry-selection picker, Remove drops the ticker. The header
// hosts the catalogue search (results in an anchored dropdown) with a source
// selector — a name added from another source's catalogue is pinned to it;
// the right column stacks the Data-sources card (the universe source + the
// pins summary, components/universe/DataSourcesCard) over the saved-universes
// aside (when a store is configured). Edits flow into the shared smile
// session, so the nodes pane and every lens update immediately (tabs of
// removed nodes are pruned). Live backend only (the universe lives on the
// server).
import { useState } from "react";
import { FolderOpen, Plus, Save, Trash2 } from "lucide-react";
import { useUniverse } from "../state/useUniverse";
import { useWorkflowContext } from "../state/workflowContext";
import { useTickerSources } from "../state/tickerSources";
import { useOptionalSnapshotFile } from "../state/snapshotFile";
import DataSourcesCard from "../components/universe/DataSourcesCard";
import ExpiryPicker from "../components/ExpiryPicker";
import LitDarkMatrix from "../components/LitDarkMatrix";

const card =
  "flex min-h-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30";
const inputClass =
  "w-full rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "text-slate-100 outline-none placeholder:text-slate-600 hover:border-slate-600 focus:border-accent-500";
const smallBtn =
  "flex items-center gap-1 rounded border border-slate-700 bg-surface-800 px-2 py-0.5 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";
const miniSelect =
  "shrink-0 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1.5 text-[11px] " +
  "text-slate-300 outline-none hover:border-slate-600 focus:border-accent-500";

export default function UniverseManager() {
  const {
    universe,
    source,
    query,
    setQuery,
    searchSource,
    setSearchSource,
    results,
    searching,
    busy,
    error,
    saved,
    addTicker,
    removeTicker,
    saveUniverse,
    loadUniverse,
    deleteUniverse,
    refreshUniverse,
  } = useUniverse();
  const { dataSources } = useWorkflowContext();
  const pinsHook = useTickerSources();
  const [newName, setNewName] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  if (source === "mock") {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-800/40 p-8 text-center">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Universe editing requires the live backend
          </h2>
          <p className="text-xs text-slate-500">
            Start the FastAPI server on :8000; the universe lives on the server.
          </p>
        </div>
      </div>
    );
  }

  const tickers = universe?.tickers ?? [];
  const inUniverse = new Set(tickers);
  const nodeCount = tickers.reduce((n, t) => n + (universe?.expiries[t] ?? []).length, 0);
  const showResults = query.trim() !== "";
  const { sources, active, switching, switchSource } = dataSources;
  const snapshot = useOptionalSnapshotFile();
  const labelOf = (id: string) => sources.find((s) => s.id === id)?.label ?? id;
  // The catalogue the search reads: the universe source unless another is chosen.
  const addSource = searchSource ?? active;
  const onOtherSource = addSource !== active;
  const shownError = error ?? pinsHook.error;
  const clearPins = () => {
    for (const t of Object.keys(pinsHook.pins)) void pinsHook.setTickerSource(t, null);
  };

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: summary · catalogue search (anchored dropdown) · error */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <span className="text-[11px] text-slate-500">
          {tickers.length} underlying{tickers.length === 1 ? "" : "s"} · {nodeCount} expiries · as
          of {universe?.asOf}
        </span>

        {/* Add underlying: search-as-you-type on ONE source's catalogue, results anchored below. */}
        <div className="relative flex w-[30rem] max-w-full items-center gap-1.5">
          <input
            className={inputClass}
            placeholder="Add underlying — search symbol or name (e.g. AAPL, Microsoft)…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {sources.length > 1 && (
            <label className="flex shrink-0 items-center gap-1 text-[10px] text-slate-500">
              in
              <select
                className={miniSelect}
                value={addSource}
                aria-label="Search source"
                title="Search this source's catalogue; a name added from another source is pinned to it"
                onChange={(e) => setSearchSource(e.target.value === active ? null : e.target.value)}
              >
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id === active ? `${s.label} (default)` : s.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          {showResults && (
            <>
              {/* Click-away closes by clearing the query. */}
              <button
                className="fixed inset-0 z-10 cursor-default"
                aria-hidden
                onClick={() => setQuery("")}
              />
              <div className="absolute left-0 right-0 top-full z-20 mt-1 max-h-80 overflow-y-auto rounded-lg border border-slate-700 bg-surface-800 py-1 shadow-xl shadow-black/40">
                {searching && <p className="px-3 py-2 text-[11px] text-slate-500">Searching…</p>}
                {!searching && results.length === 0 && (
                  <p className="px-3 py-2 text-[11px] text-slate-500">No matches.</p>
                )}
                {results.map((m) => {
                  const present = inUniverse.has(m.symbol);
                  return (
                    <div
                      key={m.symbol}
                      className="flex items-center gap-2 px-3 py-1.5 hover:bg-slate-700/30"
                    >
                      <div className="min-w-0 flex-1">
                        <span className="font-mono text-xs font-medium text-slate-100">
                          {m.symbol}
                        </span>
                        {m.name && (
                          <span className="ml-2 truncate text-[11px] text-slate-500">{m.name}</span>
                        )}
                      </div>
                      {(m.type || m.exchange) && (
                        <span className="shrink-0 text-[10px] text-slate-600">
                          {[m.type, m.exchange].filter(Boolean).join(" · ")}
                        </span>
                      )}
                      <button
                        className={smallBtn}
                        disabled={present || busy !== null}
                        title={onOtherSource ? `Add and pin to ${labelOf(addSource)}` : undefined}
                        onClick={() => addTicker(m.symbol, onOtherSource ? addSource : undefined)}
                      >
                        <Plus size={11} strokeWidth={1.75} className="opacity-80" />
                        {present
                          ? "Added"
                          : busy === `add:${m.symbol}`
                            ? "Adding…"
                            : onOtherSource
                              ? `Add on ${labelOf(addSource)}`
                              : "Add"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {shownError && (
          <span className="ml-auto truncate text-[11px] text-amber-400" title={shownError}>
            {shownError}
          </span>
        )}
      </div>

      {/* Body: one merged nodes card + the right column (sources over saved) */}
      <div className="flex min-h-0 flex-1 gap-4">
        <div className={`${card} min-h-0 min-w-0 flex-1`}>
          <LitDarkMatrix
            universe={universe ?? null}
            expanded={expanded}
            onToggleExpand={(t) => setExpanded((cur) => (cur === t ? null : t))}
            renderExpanded={(t) => <ExpiryPicker ticker={t} onChanged={refreshUniverse} />}
            sourceColumn={{
              // The ticker's PIN ("" = follows the universe source); a change
              // refetches it from the chosen feed and marks its nodes stale.
              label: (t) => pinsHook.pins[t] ?? "",
              options: [
                { id: "", label: `Default (${labelOf(active)})` },
                ...sources.map((s) => ({
                  id: s.id,
                  label: s.status === "red" ? `${s.label} (red)` : s.label,
                })),
              ],
              disabled: pinsHook.busy !== null,
              title: "Data source this ticker fetches from — pinned here, or the universe source",
              onChange: (t, id) => void pinsHook.setTickerSource(t, id || null),
            }}
            actions={(t) => (
              <button
                className={smallBtn}
                disabled={tickers.length <= 1 || busy !== null}
                title={
                  tickers.length <= 1 ? "the universe needs at least one ticker" : "Remove ticker"
                }
                onClick={() => removeTicker(t)}
              >
                <Trash2 size={11} strokeWidth={1.75} className="opacity-80" />
                {busy === `remove:${t}` ? "Removing…" : "Remove"}
              </button>
            )}
          />
        </div>

        <div className="flex w-80 shrink-0 flex-col gap-4">
          <DataSourcesCard
            sources={sources}
            active={active}
            switching={switching}
            switchSource={switchSource}
            snapshot={snapshot}
            pins={pinsHook.pins}
            labelOf={labelOf}
            clearPins={clearPins}
            pinBusy={pinsHook.busy}
          />

          {/* Saved universes */}
          <aside className={`${card} min-h-0 flex-1`}>
            <h2 className="mb-1 text-sm font-semibold text-slate-100">Saved universes</h2>
            {!saved.storeEnabled ? (
              <p className="text-[11px] text-slate-500">
                Set <span className="font-mono">VOLFIT_DB</span> on the server to save and load named
                universes.
              </p>
            ) : (
              <>
                <p className="mb-2 text-[11px] text-slate-500">
                  Save the active set (tickers, expiry picks, lit marks, source pins), then
                  reload it any time.
                </p>
                <div className="mb-3 flex gap-1.5">
                  <input
                    className={inputClass}
                    placeholder="name…"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <button
                    className={smallBtn}
                    disabled={newName.trim() === "" || busy !== null}
                    onClick={() => saveUniverse(newName.trim())}
                  >
                    <Save size={11} strokeWidth={1.75} className="opacity-80" />
                    Save
                  </button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto">
                  {saved.names.length === 0 ? (
                    <p className="text-[11px] text-slate-500">No saved universes yet.</p>
                  ) : (
                    <div className="divide-y divide-slate-800/60">
                      {saved.names.map((name) => (
                        <div key={name} className="flex items-center gap-1.5 py-1.5">
                          <span className="min-w-0 flex-1 truncate text-xs text-slate-200">{name}</span>
                          <button
                            className={smallBtn}
                            disabled={busy !== null}
                            onClick={() => loadUniverse(name)}
                          >
                            <FolderOpen size={11} strokeWidth={1.75} className="opacity-80" />
                            {busy === `load:${name}` ? "…" : "Load"}
                          </button>
                          <button
                            className={smallBtn}
                            disabled={busy !== null}
                            onClick={() => deleteUniverse(name)}
                            title="Delete this saved universe"
                          >
                            <Trash2 size={11} strokeWidth={1.75} className="opacity-80" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
