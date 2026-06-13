// Universe-management workspace: curate the tickers the app works on.
//
// Search the provider catalogue by symbol or company name, add a hit to the
// active universe (the backend fetches its chain on demand), remove tickers,
// and save / load / delete named universes (when a store is configured). Edits
// flow into the shared smile session, so every other workspace's selectors
// update immediately. Live backend only (the universe lives on the server).
import { useState } from "react";
import { useUniverse } from "../state/useUniverse";

const card =
  "flex min-h-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30";
const inputClass =
  "w-full rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "text-slate-100 outline-none placeholder:text-slate-600 hover:border-slate-600 focus:border-accent-500";
const smallBtn =
  "rounded border border-slate-700 bg-surface-800 px-2 py-0.5 text-[11px] font-medium " +
  "text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 " +
  "disabled:cursor-not-allowed disabled:opacity-40";

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
  } = useUniverse();
  const [newName, setNewName] = useState("");

  if (source === "mock") {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
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

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-3">
        <h1 className="text-sm font-semibold text-slate-100">Universe</h1>
        <span className="text-[11px] text-slate-500">
          {tickers.length} underlying{tickers.length === 1 ? "" : "s"} · as of {universe?.asOf}
        </span>
        {error && (
          <span className="ml-auto truncate text-[11px] text-amber-400" title={error}>
            {error}
          </span>
        )}
      </div>

      <div className="flex min-h-0 flex-1 gap-4">
        {/* Add + active universe */}
        <div className="flex min-w-0 flex-1 flex-col gap-4">
          {/* Search / add */}
          <div className={`${card} shrink-0`}>
            <h2 className="mb-2 text-sm font-semibold text-slate-100">Add underlying</h2>
            <input
              className={inputClass}
              placeholder="Search symbol or company name (e.g. AAPL, Microsoft)…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="mt-2 max-h-56 overflow-y-auto">
              {searching && <p className="px-1 py-2 text-[11px] text-slate-500">Searching…</p>}
              {!searching && query.trim() !== "" && results.length === 0 && (
                <p className="px-1 py-2 text-[11px] text-slate-500">No matches.</p>
              )}
              <div className="divide-y divide-slate-800/60">
                {results.map((m) => {
                  const present = inUniverse.has(m.symbol);
                  return (
                    <div key={m.symbol} className="flex items-center gap-2 py-1.5">
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
                        {present ? "Added" : busy === `add:${m.symbol}` ? "Adding…" : "Add"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Active universe */}
          <div className={`${card} min-h-0 flex-1`}>
            <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-100">Active universe</h2>
            <div className="min-h-0 flex-1 overflow-y-auto">
              <div className="divide-y divide-slate-800/60">
                {tickers.map((t) => {
                  const ladder = universe?.expiries[t] ?? [];
                  return (
                    <div key={t} className="flex items-center gap-2 py-1.5">
                      <span className="w-24 font-mono text-xs font-medium text-slate-100">{t}</span>
                      <span className="flex-1 text-[11px] text-slate-500">
                        {ladder.length} expir{ladder.length === 1 ? "y" : "ies"}
                      </span>
                      <button
                        className={smallBtn}
                        disabled={tickers.length <= 1 || busy !== null}
                        title={tickers.length <= 1 ? "the universe needs at least one ticker" : undefined}
                        onClick={() => removeTicker(t)}
                      >
                        {busy === `remove:${t}` ? "Removing…" : "Remove"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Saved universes */}
        <aside className={`${card} w-72 shrink-0`}>
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
                          {busy === `load:${name}` ? "…" : "Load"}
                        </button>
                        <button
                          className={smallBtn}
                          disabled={busy !== null}
                          onClick={() => deleteUniverse(name)}
                          title="Delete this saved universe"
                        >
                          ×
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
  );
}
