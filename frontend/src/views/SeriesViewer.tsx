// Series lens (SERIES ARC S4 §3.4): one ticker's harvested time-series of
// smiles, calibrated under model lanes, replayed frame by frame. A NODE
// lens: the ticker and expiry come from the enclosing scope (the tab),
// never from selectors of its own. Layout, top to bottom: SeriesHeader
// (picker · job verbs · lane chips · stage tabs) / a control row (axis ·
// ghost trail · the Surface stage's Sheets | Difference · the expiry note) /
// the stage (views/series/StageSwitch: Smile · Frames · Surface · Term ·
// Lanes) / Filmstrip / TransportBar sticky at the bottom. Keys with the lens
// focused: Space, ← / →, Shift+← / →, Home / End, L (lib/seriesPlayback
// keyAction). The data plumbing lives in views/series/useSeriesSelection,
// the per-tab view memory in useSeriesViewState, the pure selectors in
// seriesSelectors. Live server with a store only (VOLFIT_DB) — the empty
// states say so.
import { useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import SeriesHeader from "../components/series/SeriesHeader";
import NewSeriesDialog from "../components/series/NewSeriesDialog";
import TransportBar from "../components/series/TransportBar";
import Filmstrip from "../components/series/Filmstrip";
import { useSeriesPlayback } from "../state/useSeriesPlayback";
import { useSeriesFrames } from "../state/useSeriesFrames";
import { useSeriesStrip } from "../state/useSeriesStrip";
import { keyAction } from "../lib/seriesPlayback";
import { adoptSeriesPrior, seriesErrorMessage } from "../state/useSeries";
import { exportSeries, openSeriesPicker, openSeriesRecent, useSeriesRecent } from "../state/seriesFiles";
import type { SeriesRecentEntry } from "../lib/seriesFiles";
import { useSmileSession } from "../state/smileSession";
import type { FrameDoc, LaneSpec } from "../lib/seriesTypes";
import { buttonClass, cardClass, chartMessageClass, chipClass, primaryButtonClass, selectClass } from "../lib/ui";
import StageSwitch from "./series/StageSwitch";
import { useSeriesSelection } from "./series/useSeriesSelection";
import { AXIS_OPTIONS, GHOST_OPTIONS, SURFACE_MODES, useSeriesViewState } from "./series/useSeriesViewState";
import { ghostTrail, pickExpiry, productionLane } from "./series/seriesSelectors";

const EMPTY_FRAMES: FrameDoc[] = [];
const EMPTY_LANES: LaneSpec[] = [];
const EMPTY_STRINGS: string[] = [];
const STORE_HINT = "Series need the live server with a store (VOLFIT_DB)";

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

function EmptyCard({ title, body, action }: {
  title: string;
  body: ReactNode;
  action?: { label: string; onClick: () => void; primary?: boolean };
}) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center p-4">
      <div className={`${cardClass} max-w-md p-8 text-center`}>
        <h2 className="mb-2 text-sm font-semibold text-slate-100">{title}</h2>
        <p className="mb-5 text-xs leading-relaxed text-slate-500">{body}</p>
        {action && (
          <button className={action.primary ? primaryButtonClass : buttonClass} onClick={action.onClick}>{action.label}</button>
        )}
      </div>
    </div>
  );
}

export default function SeriesViewer() {
  const { ticker, expiry: tabExpiry, source, fitMode: sessionFitMode } = useSmileSession();
  const live = source === "live";
  const view = useSeriesViewState();
  const { seriesId, stage, hidden, axisMode, ghost, kWindow, surfaceMode, patch, toggleLane } = view;
  const recentFiles = useSeriesRecent();
  const sel = useSeriesSelection(ticker, live, seriesId, (id) => patch({ seriesId: id }));
  const { doc, progress, epochKey, pendingActive, pendingFrame, clearPending } = sel;
  const [dialogOpen, setDialogOpen] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    if (note === null) return;
    const t = window.setTimeout(() => setNote(null), 5000);
    return () => window.clearTimeout(t);
  }, [note]);

  const frames = doc?.frames ?? EMPTY_FRAMES;
  const nFrames = frames.length;
  const lanes = doc?.spec.lanes ?? EMPTY_LANES;
  const laneIds = useMemo(() => lanes.map((l) => l.id), [lanes]);
  // Every payload cache re-reads when the series or its job's counters change.
  const epoch = `${seriesId ?? ""}|${epochKey}`;

  const { playback, update, act } = useSeriesPlayback(nFrames, epoch);
  // Prefetch direction: the way the playhead last moved.
  const prevIndex = useRef(playback.index);
  const direction: 1 | -1 = playback.index >= prevIndex.current ? 1 : -1;
  useEffect(() => {
    prevIndex.current = playback.index;
  }, [playback.index]);
  const { frame, loading: frameLoading, peek } = useSeriesFrames(seriesId, laneIds, playback.index, nFrames, direction, epoch);

  // The shown expiry = the tab's when the frame carries it, else the nearest
  // later one the frame carries (the tab's has rolled off).
  const frameExpiries = frame?.expiries ?? frames[playback.index]?.expiries ?? EMPTY_STRINGS;
  const { expiry: shownExpiry, rolled } = useMemo(
    () => pickExpiry(frameExpiries, tabExpiry === "" ? null : tabExpiry),
    [frameExpiries, tabExpiry],
  );
  const { strip } = useSeriesStrip(seriesId, laneIds, shownExpiry, epoch);
  const production = productionLane(lanes);
  const ghostCurves = useMemo(
    () => ghostTrail(peek, playback.index, ghost, production?.id ?? null, shownExpiry),
    [peek, playback.index, ghost, production, shownExpiry],
  );

  // A deep link's frame: jump once the linked document is in, then forget it.
  useEffect(() => {
    if (!pendingActive || doc === null || doc.id !== seriesId) return;
    if (pendingFrame !== null && nFrames > 0) update({ index: Math.max(0, Math.min(nFrames - 1, pendingFrame)) });
    clearPending();
  }, [pendingActive, pendingFrame, doc, seriesId, nFrames, update, clearPending]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (doc === null || isTyping(e.target)) return;
    const a = keyAction({ key: e.key, shiftKey: e.shiftKey });
    if (a === null) return;
    act(a);
    e.preventDefault();
  };

  // Every hook is above this line (React #300: the hook count must not
  // change when the session flips live → mock after mount).
  if (!live) {
    return (
      <div className="flex h-full flex-col p-3">
        <EmptyCard title={STORE_HINT} body="Start the FastAPI server on :8000 with VOLFIT_DB set; the lens then lists the ticker's series and replays them." />
      </div>
    );
  }

  const storeMissing = sel.list.error !== null && /VOLFIT_DB/i.test(sel.list.error);

  const body = (): ReactNode => {
    if (storeMissing) return <EmptyCard title={STORE_HINT} body={sel.list.error} />;
    if (sel.list.error !== null && sel.list.series.length === 0) {
      return <EmptyCard title="The series list could not be read" body={sel.list.error} action={{ label: "Retry", onClick: sel.list.refresh }} />;
    }
    if (seriesId === null) {
      return sel.list.loaded && sel.list.series.length === 0
        ? (
          <EmptyCard
            title={`No series for ${ticker} yet`}
            body="Harvest the ticker's chains at a sequence of instants — historical, live or imported — and calibrate them under model lanes."
            action={{ label: "New series…", onClick: () => setDialogOpen(true), primary: true }}
          />
        )
        : <div className={chartMessageClass}>Loading series…</div>;
    }
    if (doc === null) return <div className={chartMessageClass}>{sel.docError ?? "Loading the series…"}</div>;
    return (
      <>
        <div className="flex shrink-0 flex-wrap items-center gap-3 text-[11px] text-slate-500">
          <label className="flex items-center gap-1.5">
            Axis
            <select aria-label="Axis" className={selectClass} value={axisMode} onChange={(e) => patch({ axisMode: e.target.value })}>
              {AXIS_OPTIONS.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            Ghost trail
            <select aria-label="Ghost trail" className={selectClass} value={ghost} onChange={(e) => patch({ ghost: Number(e.target.value) })}>
              {GHOST_OPTIONS.map((g) => <option key={g} value={g}>{g === 0 ? "off" : `${g} frame${g > 1 ? "s" : ""}`}</option>)}
            </select>
          </label>
          {stage === "surface" && (
            <span className="flex items-center gap-1" role="group" aria-label="Surface mode">
              {SURFACE_MODES.map((m) => (
                <button key={m.id} type="button" aria-pressed={surfaceMode === m.id} className={chipClass(surfaceMode === m.id)} onClick={() => patch({ surfaceMode: m.id })}>
                  {m.label}
                </button>
              ))}
            </span>
          )}
          {shownExpiry !== null && rolled && (
            <span className="text-amber-400/80" data-testid="expiry-note">
              Expiry {tabExpiry} is not in this frame — showing the nearest later expiry {shownExpiry}.
            </span>
          )}
          {sel.error && <span className="text-rose-400">{sel.error}</span>}
          {note && <span className="text-emerald-400" data-testid="series-note">{note}</span>}
        </div>
        <div className={`${cardClass} flex min-h-0 flex-1 flex-col p-3`} data-chart-card="">
          <StageSwitch
            stage={stage}
            seriesId={doc.id}
            ticker={ticker}
            frame={frame}
            frames={frames}
            index={playback.index}
            strip={strip}
            lanes={lanes}
            hidden={hidden}
            expiry={shownExpiry}
            axisMode={axisMode}
            surfaceMode={surfaceMode}
            kWindow={kWindow}
            onKWindowChange={(w) => patch({ kWindow: w })}
            ghostCurves={ghostCurves}
            fitMode={doc.spec.fitMode}
            loading={frameLoading}
            epoch={epoch}
            onScrub={(idx) => update({ index: idx })}
          />
        </div>
        <div className="shrink-0">
          <Filmstrip strip={strip} lanes={lanes} hidden={hidden} index={playback.index} onScrub={(idx) => update({ index: idx })} />
        </div>
        <div className="sticky bottom-0 shrink-0">
          <TransportBar playback={playback} nFrames={nFrames} frames={frames} onChange={(next) => update(next)} onAction={act} />
        </div>
      </>
    );
  };

  // Export remembers the file it saved; Open file… starts in that directory
  // and Reopen <latest> proposes it (state/seriesFiles). An opened series is
  // selected at once, like a series the dialog created.
  const onExport = async () => {
    if (!seriesId || !doc) return;
    try {
      const name = await exportSeries(seriesId, doc);
      if (name !== null) setNote(`exported ${name}`);
    } catch (err) {
      setNote(seriesErrorMessage(err));
    }
  };
  const onOpened = (res: { id: string; name: string; ticker: string; frames: number } | null) => {
    if (res === null) return;
    sel.markCreated(res.id);
    setNote(`opened ${res.name} · ${res.ticker} · ${res.frames} frame${res.frames === 1 ? "" : "s"}`);
  };
  const onOpenFile = async () => {
    try { onOpened(await openSeriesPicker()); } catch (err) { setNote(seriesErrorMessage(err)); }
  };
  const onOpenRecent = async (entry: SeriesRecentEntry) => {
    try { onOpened(await openSeriesRecent(entry)); } catch (err) { setNote(seriesErrorMessage(err)); }
  };
  const onAdoptPrior = async () => {
    if (!seriesId || !doc) return;
    try {
      const res = await adoptSeriesPrior(seriesId, production?.id ?? null, playback.index);
      setNote(`prior adopted: ${res.laneId} at frame ${res.idx + 1} (${res.nodes} nodes${res.lvSurface ? " + LV" : ""})`);
    } catch (err) {
      setNote(seriesErrorMessage(err));
    }
  };

  return (
    <div
      className="flex h-full flex-col gap-2 p-3 outline-none"
      tabIndex={0}
      onKeyDown={onKeyDown}
      aria-label="Series lens"
      data-series-lens=""
    >
      <SeriesHeader
        ticker={ticker}
        list={sel.list.series}
        seriesId={seriesId}
        doc={doc}
        progress={progress}
        busy={sel.busy}
        hidden={hidden}
        stage={stage}
        onSelect={(id) => patch({ seriesId: id })}
        onNew={() => setDialogOpen(true)}
        onDelete={sel.verbs.remove}
        onOpenFile={() => void onOpenFile()}
        onOpenRecent={(entry) => void onOpenRecent(entry)}
        recentFiles={recentFiles}
        onExport={() => void onExport()}
        onAdoptPrior={() => void onAdoptPrior()}
        onStart={sel.verbs.start}
        onResume={sel.verbs.resume}
        onPause={sel.verbs.pause}
        onCancel={sel.verbs.cancel}
        onToggleLane={toggleLane}
        onStage={(s) => patch({ stage: s })}
      />
      {body()}
      <NewSeriesDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        ticker={ticker}
        fitMode={sessionFitMode}
        onCreated={sel.markCreated}
      />
    </div>
  );
}
