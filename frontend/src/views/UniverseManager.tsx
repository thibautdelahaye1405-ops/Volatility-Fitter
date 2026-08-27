// Universe manager (the "Manage universe" dialog since UI SHELL v2): curate
// the tickers the app works on.
//
// One mental model, one card: every ticker row shows its expiry chips with the
// lit/dark designation toggled directly on the chips (the shared lit map —
// nodes pane + Graph canvas follow), ▸ expands the expiry-selection picker,
// Remove drops the ticker. The header hosts the catalogue search (results in
// an anchored dropdown); the right column stacks the Data-sources card (pick
// the active feed; the per-node policy is UI-ready but disabled until the
// multi-source engine — state/nodeSources.ts) over the saved-universes aside
// (when a store is configured). Edits flow into the shared smile session, so
// the nodes pane and every lens update immediately (tabs of removed nodes are
// pruned). Live backend only (the universe lives on the server).
import { useState } from "react";
import { FolderOpen, Plus, Save, Trash2 } from "lucide-react";
import { useUniverse } from "../state/useUniverse";
import { useWorkflowContext } from "../state/workflowContext";
import { PER_NODE_HINT, useNodeSources } from "../state/nodeSources";
import { useOptionalSnapshotFile } from "../state/snapshotFile";
import type { SourceStatus } from "../state/useDataSources";
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
const segBtn = "px-2 py-0.5 text-[10px] font-medium transition-colors";

const STATUS_DOT: Record<SourceStatus, string> = {
  green: "bg-emerald-500",
  amber: "bg-amber-400",
  red: "bg-rose-500",
};

export default function UniverseManager() {
  const {
    universe,
    source,
    query,
    setQuery,
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
  const { policy, setMode, clearOverrides } = useNodeSources();
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
  const overrideCount = Object.keys(policy.overrides).length;

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header: summary · catalogue search (anchored dropdown) · error */}
      <div className="flex shrink-0 flex-wrap items-center gap-3">
        <span className="text-[11px] text-slate-500">
          {tickers.length} underlying{tickers.length === 1 ? "" : "s"} · {nodeCount} expiries · as
          of {universe?.asOf}
        </span>

        {/* Add underlying: search-as-you-type, results anchored below. */}
        <div className="relative w-96 max-w-full">
          <input
            className={inputClass}
            placeholder="Add underlying — search symbol or name (e.g. AAPL, Microsoft)…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {showResults && (
            <>
              {/* Click-away closes by clearing the query. */}
              <button
                className="fixed inset-0 z-10 cursor-default"
                aria-hidden
                onClick={() => setQuery("")}
              />
              <div className="absolute left-0 right-0 z-20 mt-1 max-h-80 overflow-y-auto rounded-lg border border-slate-700 bg-surface-800 py-1 shadow-xl shadow-black/40">
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
                        onClick={() => addTicker(m.symbol)}
                      >
                        <Plus size={11} strokeWidth={1.75} className="opacity-80" />
                        {present ? "Added" : busy === `add:${m.symbol}` ? "Adding…" : "Add"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>

        {error && (
          <span className="ml-auto truncate text-[11px] text-amber-400" title={error}>
            {error}
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
              // One active feed today: every row shows the universe source.
              label: () => active,
              options: sources.map((s) => ({ id: s.id, label: s.label })),
              disabled: true,
              title: PER_NODE_HINT,
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
          {/* Data sources: the active feed (radio list) + the per-node policy */}
          <section className={`${card} shrink-0`}>
            <h2 className="mb-1 text-sm font-semibold text-slate-100">Data sources</h2>
            <p className="mb-2 text-[11px] text-slate-500">
              One active feed for the whole universe; switching refetches the chains.
            </p>
            {sources.length === 0 ? (
              <p className="text-[11px] text-slate-500">No data sources registered.</p>
            ) : (
              <div
                role="radiogroup"
                aria-label="Active data source"
                className={`flex flex-col gap-0.5 ${switching ? "animate-pulse" : ""}`}
              >
                {sources.map((s) => {
                  const unavailable = s.status === "red";
                  const isActive = s.id === active;
                  return (
                    <button
                      key={s.id}
                      role="radio"
                      aria-checked={isActive}
                      disabled={unavailable || switching}
                      title={unavailable ? s.detail : undefined}
                      onClick={() => void switchSource(s.id)}
                      className={[
                        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                        unavailable
                          ? "cursor-not-allowed text-slate-600"
                          : isActive
                            ? "bg-accent-500/10 text-accent-300"
                            : "text-slate-300 hover:bg-slate-700/40 hover:text-slate-100",
                      ].join(" ")}
                    >
                      <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[s.status]}`} />
                      <span className="min-w-0 flex-1 truncate font-medium">{s.label}</span>
                      <span className="truncate text-[10px] text-slate-500" title={s.detail}>
                        {s.detail}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {snapshot !== null && (
              <button
                className="mt-2 w-full rounded-md border border-dashed border-slate-700 px-2 py-1.5 text-left text-[11px] text-slate-400 transition-colors hover:border-slate-500 hover:text-slate-200"
                title="Open a snapshot file (quotes + calibrations): it becomes the File data source"
                disabled={snapshot.busy}
                onClick={() => void snapshot.openPicker()}
              >
                + Open snapshot file… <span className="text-slate-600">(File source)</span>
              </button>
            )}

            {/* Per-node policy: UI-ready, disabled until the multi-source engine. */}
            <div className="mt-3 border-t border-slate-800/60 pt-2">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <span className="text-[11px] font-medium text-slate-300">Per-node sources</span>
                <div className="flex overflow-hidden rounded-md border border-slate-700 bg-surface-800">
                  <button
                    className={`${segBtn} ${
                      policy.mode === "universe"
                        ? "bg-accent-600/25 text-accent-400"
                        : "text-slate-400 hover:text-slate-200"
                    }`}
                    onClick={() => setMode("universe")}
                  >
                    Universe source
                  </button>
                  <button
                    className={`${segBtn} cursor-not-allowed text-slate-600`}
                    disabled
                    title={PER_NODE_HINT}
                  >
                    Per node
                  </button>
                </div>
              </div>
              <p className="text-[10px] text-slate-500">
                Every node fetches from the universe source today; per-node picks are recorded for
                the multi-source engine.
                {overrideCount > 0 && (
                  <>
                    {" "}
                    {overrideCount} recorded ·{" "}
                    <button className="text-slate-400 underline hover:text-slate-200" onClick={clearOverrides}>
                      clear
                    </button>
                  </>
                )}
              </p>
            </div>
          </section>

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
                  Save the active set, then reload it any time.
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
