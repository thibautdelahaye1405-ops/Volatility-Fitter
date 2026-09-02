"""Live quote-table ticks — the per-node push channel off the streaming book.

Backs GET /smiles/{ticker}/{expiry}/table/stream (volfit.api.routers.smiles), a
Server-Sent Events stream the Quote Table opens for the node it shows. While
the active source streams (Massive WS book / Bloomberg ``//blp/mktdata`` book),
the node's LIVE market is pushed into the table at ~1 Hz so it ticks between
refits — independent of the calibration snapshot the table's rows come from.

Contract (what keeps this honest and cheap):

* **Same pipeline as the table.** The live chain is read BOOK-ONLY from the
  provider (``live_chain`` — never a metered / REST request; an absent reader or
  a non-streaming source means "no live ticks") and run through the SAME
  ``prepare_quotes`` (OTM side, de-Americanization, tick floor, event clock)
  with the node's cash dividends / clocks and the LIVE forward — the node's
  resolved forward transported by the streamed spot's return under the app's
  own forward-transport rule (service.spot_forward_shift: proportional, or
  additive under discrete cash dividends) — so live IVs are on exactly the
  footing of the table's IVs at today's spot, and prices are reconstructed by
  the same Black map (volfit.api.table). Rows are keyed by STRIKE
  (``"123.4500"``, the table's 4-dp precision): one OTM row per strike, so the
  frontend overlays them onto the calibrated table rows (and draws them on the
  smile chart at ``log(strike / chart forward)``) without positional coupling,
  and a side flip of the ATM-straddling strike under a spot move cannot
  orphan a row.
* **Deltas, not snapshots.** ``LiveTableTracker`` fingerprints the raw live
  (bid, ask) set per poll and re-prepares only when it changed; a frame carries
  only rows whose band moved (``full`` on the first / after a reset) plus the
  keys that went one-sided (``gone``). Status frames flag streaming / ready so
  the UI shows a LIVE badge or "warming" instead of silently going stale.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from volfit.api.quotes import prepare_quotes
from volfit.api.schemas import SmilePoint
from volfit.api.service import displayed_base, node_clock, spot_forward_shift, variance_time
from volfit.api.smile_layers import model_iv_at, rolled_record, stream_frame, strike_key
from volfit.api.state import AppState
from volfit.api.table import _price as band_price
from volfit.calib.band import resolve_band
from volfit.data.forwards import ResolvedForward
from volfit.data.types import ChainSnapshot


class LiveTickRow(BaseModel):
    """One live OTM quote of the node's slice, in the table's conventions."""

    key: str  # "<strike .4f>" — joins the table row / chart quote by strike
    strike: float
    type: str
    k: float
    bidIv: float
    midIv: float
    askIv: float
    bidPrice: float
    midPrice: float
    askPrice: float
    #: Fit-target band of the requested fit mode (None in "mid"), the market as
    #: quoted (no edits) — the chart's live target ribbon.
    targetLo: float | None = None
    targetHi: float | None = None
    #: The calibration quote at the same strike (click-through), -1 when none.
    index: int = -1
    #: The fit ROLLED to the live spot, at this row's live moneyness (the table's
    #: "Model IV" of the market frame); None when the node has no fit.
    modelIv: float | None = None


class LiveTableFrame(BaseModel):
    """One SSE event of the table tick stream."""

    type: Literal["ticks", "status"]
    streaming: bool  # the active source has a live book
    ready: bool  # the book served this node's chain (painted + covered)
    full: bool = False  # rows are the whole live slice (first frame / reset)
    ts: str | None = None  # newest provider stamp of the live chain (ISO, UTC)
    spot: float | None = None  # the FRAME's spot (the manual dial's when one is set)
    forward: float | None = None
    #: The book's actual underlying spot (independent of the dial) — the Spot
    #: panel's streamed readout.
    liveSpot: float | None = None
    rows: list[LiveTickRow] = Field(default_factory=list)
    gone: list[str] = Field(default_factory=list)  # keys no longer two-sided
    nLive: int = 0  # live two-sided rows in the slice after this frame
    #: The displayed fit ROLLED to the live spot (k relative to ``forward``),
    #: sent whenever the live forward moved / the calibration changed; None =
    #: unchanged (or no fit).
    model: list[SmilePoint] | None = None


def row_key(strike: float) -> str:
    """The overlay join key: the strike at 4 dp (the table's precision)."""
    return f"{strike:.4f}"


def live_forward(
    state: AppState, ticker: str, expiry: date, base: ResolvedForward, t: float, spot: float
) -> ResolvedForward:
    """The node's forward moved to the streamed ``spot`` under the app's own
    forward-transport rule (service.spot_forward_shift with the live spot's
    return vs the calibration anchor). Falls back to ``base`` when no anchor /
    spot is available, so the inversion never silently changes basis."""
    try:
        anchor = float(state.anchor_spot(ticker))
    except Exception:  # noqa: BLE001 — no anchor: keep the node's forward
        return base
    if anchor <= 0.0 or spot <= 0.0:
        return base
    f1, _h = spot_forward_shift(
        state, ticker, expiry, base.forward, base.discount, t, shift=spot / anchor - 1.0
    )
    return ResolvedForward(expiry, float(f1), base.discount, base.source)


# ------------------------------------------------------------ live slice
@dataclass(frozen=True)
class LiveSlice:
    rows: list[LiveTickRow]
    ts: datetime | None
    spot: float
    forward: float
    fingerprint: str
    shift: float = 0.0  # the FRAME's return vs the calibration anchor (rolls the fit)
    live_spot: float = 0.0  # the book's actual spot (the frame's unless a manual dial is set)


def live_chain(state: AppState, ticker: str, expiry: date) -> ChainSnapshot | None:
    """The node's live chain straight from the provider's streaming book, or None
    (not streaming, no book reader, book not ready). NEVER a request."""
    if not state.is_streaming(ticker):
        return None
    reader = getattr(state.provider_for(ticker), "live_chain", None)
    if reader is None:
        return None
    try:
        return reader(ticker, [expiry])
    except Exception:  # noqa: BLE001 — a book hiccup is "not ready", not an error
        return None


def chain_fingerprint(chain: ChainSnapshot, expiry: date) -> str:
    """Digest of the raw (strike, side, bid, ask) set + spot for one expiry — the
    cheap 'did anything tick?' check that gates the de-Am re-preparation."""
    h = hashlib.blake2b(digest_size=16)
    h.update(repr(round(chain.spot, 6)).encode())
    for q in chain.quotes_for(expiry):
        h.update(f"{q.strike}|{q.call_put}|{q.bid}|{q.ask};".encode())
    return h.hexdigest()


def live_shift(state: AppState, ticker: str, spot: float) -> float:
    """The live spot's return vs the calibration anchor (0 when unknown)."""
    try:
        anchor = float(state.anchor_spot(ticker))
    except Exception:  # noqa: BLE001
        return 0.0
    return spot / anchor - 1.0 if anchor > 0.0 and spot > 0.0 else 0.0


def live_slice(
    state: AppState,
    ticker: str,
    expiry_iso: str,
    fit_mode: str = "mid",
    calib_index: dict[str, int] | None = None,
) -> LiveSlice | None:
    """Prepare the node's LIVE slice in the table's conventions, or None when the
    book has nothing for it yet (or the node has no stored chain to resolve a
    forward against). Rows carry the fit-target band of ``fit_mode`` (pure
    market, no edits) and the calibration quote index at the same strike.
    Raises UnknownNodeError for an unknown node."""
    expiry = state.resolve_expiry(ticker, expiry_iso)
    chain = live_chain(state, ticker, expiry)
    if chain is None or not state.has_quotes(ticker):
        return None
    try:
        t_cal, base_days = node_clock(state, ticker, expiry)
        forward = live_forward(
            state, ticker, expiry, state.resolved_forward(ticker, expiry), t_cal, chain.spot
        )
        cash = state.cash_dividend_schedule(ticker, expiry, forward.forward)
        tau = variance_time(state, ticker, expiry, t_cal, base_days)
    except Exception:  # noqa: BLE001 — no forward yet: not ready
        return None
    fingerprint = chain_fingerprint(chain, expiry)
    # The FRAME the rows and the rolled fit live in (smile_layers.stream_frame):
    # a MANUAL dial move overrides the live spot; a poll-set shift does not.
    shift, frame_spot, frame_forward = stream_frame(
        state, ticker, expiry, t_cal, chain.spot, forward.forward, live_shift(state, ticker, chain.spot)
    )
    try:
        prepared = prepare_quotes(chain, expiry, forward, t_cal, cash, tau=tau)
    except ValueError:  # no two-sided OTM quotes right now: an empty live slice
        return LiveSlice(
            [], chain.timestamp, frame_spot, frame_forward, fingerprint, shift, live_spot=chain.spot
        )
    f, d, tv = prepared.forward, prepared.discount, prepared.tau
    # Live IVs are inverted at the LIVE forward (the prices are the market's);
    # only the moneyness is re-expressed against the frame forward (fixed strikes).
    dk = math.log(f / frame_forward) if frame_forward > 0.0 else 0.0
    band = resolve_band(
        prepared.iv_bid, prepared.iv_mid, prepared.iv_ask, fit_mode, state.fit_settings().haircut
    )
    rows: list[LiveTickRow] = []
    for i, (k, bid, mid, ask) in enumerate(
        zip(prepared.k, prepared.iv_bid, prepared.iv_mid, prepared.iv_ask)
    ):
        k = float(k)
        strike = f * math.exp(k)
        side = "C" if k >= 0.0 else "P"
        # Wire rounding (8 dp vols, 6 dp prices): far below any display/fit
        # precision, ~40% smaller frames at 1 Hz (~100 ticked rows/s on SPY).
        rows.append(
            LiveTickRow(
                key=row_key(strike),
                strike=round(strike, 6),
                type=side,
                k=round(k + dk, 8),
                bidIv=round(float(bid), 8),
                midIv=round(float(mid), 8),
                askIv=round(float(ask), 8),
                bidPrice=round(band_price(k, float(bid), tv, f, d), 6),
                midPrice=round(band_price(k, float(mid), tv, f, d), 6),
                askPrice=round(band_price(k, float(ask), tv, f, d), 6),
                targetLo=round(float(band.iv_lo[i]), 8) if band is not None else None,
                targetHi=round(float(band.iv_hi[i]), 8) if band is not None else None,
                index=(calib_index or {}).get(strike_key(strike), -1),
            )
        )
    return LiveSlice(
        rows, chain.timestamp, frame_spot, frame_forward, fingerprint, shift, live_spot=chain.spot
    )


# ---------------------------------------------------------------- tracker
def _signature(row: LiveTickRow) -> tuple[float, float, float]:
    return (row.bidIv, row.midIv, row.askIv)


class LiveTableTracker:
    """Per-connection delta state: turns successive live slices into frames.

    ``frame`` returns None when there is nothing new to push (the caller then
    sends nothing / a keep-alive). Status transitions are pushed once each:
    streaming→off resets the overlay (``streaming=False``), a streaming-but-not-
    ready book is announced once (``ready=False``) so the UI can say "warming".
    """

    def __init__(self, fit_mode: str = "mid") -> None:
        self._fit_mode = fit_mode
        self._sent: dict[str, tuple[float, float, float]] = {}
        self._fingerprint: str | None = None
        self._announced: tuple[bool, bool] | None = None  # (streaming, ready)
        self._model_shift: float | None = None  # shift the last sent rolled model was at
        self._frame_shift: float | None = None  # shift the last sent ROWS were framed at
        self._base_id: int | None = None  # identity of the calibration record last seen
        self._rolled = None  # the rolled FitRecord at (_base_id, _rolled_shift)
        self._rolled_shift: float | None = None

    def _status(self, streaming: bool, ready: bool) -> LiveTableFrame | None:
        """A status frame if (streaming, ready) changed since the last push."""
        if self._announced == (streaming, ready):
            return None
        self._announced = (streaming, ready)
        return LiveTableFrame(type="status", streaming=streaming, ready=ready)

    def frame(self, state: AppState, ticker: str, expiry_iso: str) -> LiveTableFrame | None:
        if not state.is_streaming(ticker):
            self._sent.clear()
            self._fingerprint = None
            return self._status(False, False)
        iso = state.resolve_expiry(ticker, expiry_iso).isoformat()
        base = displayed_base(state, ticker, iso, self._fit_mode)  # the calibration (no transport)
        sl = live_slice(state, ticker, expiry_iso, self._fit_mode, _calib_index(base))
        if sl is None:
            self._sent.clear()
            self._fingerprint = None
            return self._status(True, False)
        self._announced = (True, True)  # a ticks frame announces ready itself
        base_changed = id(base) != self._base_id  # a refit: full repaint + new rolled fit
        # The frame moved (a manual dial move, or the live spot ticked): every
        # row's moneyness changed, so every row is re-sent (not a `full` reset —
        # the UI flashes only material IV moves, and the map is unchanged).
        frame_moved = self._frame_shift is not None and sl.shift != self._frame_shift
        if sl.fingerprint == self._fingerprint and self._sent and not base_changed and not frame_moved:
            return None
        self._fingerprint = sl.fingerprint
        self._frame_shift = sl.shift
        full = not self._sent or base_changed
        current = {r.key: r for r in sl.rows}
        changed = [
            r for r in sl.rows if full or frame_moved or self._sent.get(r.key) != _signature(r)
        ]
        gone = [k for k in self._sent if k not in current]
        self._sent = {k: _signature(r) for k, r in current.items()}
        # The fit rolled to the live spot: recomputed only when the spot (hence the
        # forward) moved or the calibration changed — a quote-only tick sends none.
        # The same rolled record prices each sent row's Model IV at its live k.
        model: list[SmilePoint] | None = None
        if base is not None:
            if self._rolled is None or base_changed or sl.shift != self._rolled_shift:
                self._rolled = rolled_record(state, ticker, iso, base, sl.shift)
                self._rolled_shift = sl.shift
            if full or sl.shift != self._model_shift:
                from volfit.api.service import model_curve

                model = model_curve(self._rolled)
                self._model_shift = sl.shift
            if changed:
                ivs = model_iv_at(self._rolled, [r.k for r in changed])
                for r, iv in zip(changed, ivs):
                    r.modelIv = round(float(iv), 8)
        else:
            self._rolled = None
        self._base_id = id(base)
        if not (changed or gone or full or model is not None):
            return None
        return LiveTableFrame(
            type="ticks",
            streaming=True,
            ready=True,
            full=full,
            ts=sl.ts.isoformat() if sl.ts is not None else None,
            spot=sl.spot,
            forward=sl.forward,
            liveSpot=sl.live_spot,
            rows=changed,
            gone=gone,
            nLive=len(current),
            model=model,
        )


def _calib_index(base) -> dict[str, int]:
    """``{strike key -> prepared index}`` of the calibration quotes (click-through)."""
    if base is None:
        return {}
    p = base.prepared
    f = float(p.forward)
    return {strike_key(f * math.exp(float(k))): i for i, k in enumerate(p.k)}


# -------------------------------------------------------------- SSE loop
#: Poll cadence (s) — matches the 1 s conflation of the Bloomberg stream.
TICK_SECONDS = 1.0
#: Keep-alive comment cadence (s) when nothing changed, to hold the connection.
HEARTBEAT_SECONDS = 15.0


async def table_events(
    state: AppState,
    ticker: str,
    expiry_iso: str,
    is_disconnected,
    tick: float = TICK_SECONDS,
    fit_mode: str = "mid",
):
    """Async generator of SSE chunks for one node's tick stream. The prepare
    (de-Am on American chains) runs in a worker thread so the event loop stays
    responsive; a bad node ends the stream with an ``error`` event."""
    import asyncio
    from time import monotonic

    from volfit.api.state import UnknownNodeError

    tracker = LiveTableTracker(fit_mode)
    last_beat = monotonic()
    while True:
        if await is_disconnected():
            return
        try:
            frame = await asyncio.to_thread(tracker.frame, state, ticker, expiry_iso)
        except UnknownNodeError as exc:
            yield f"event: error\ndata: {str(exc)!r}\n\n"
            return
        except Exception:  # noqa: BLE001 — a transient failure never kills the stream
            frame = None
        now = monotonic()
        if frame is not None:
            last_beat = now
            yield f"data: {frame.model_dump_json()}\n\n"
        elif now - last_beat >= HEARTBEAT_SECONDS:
            last_beat = now
            yield ": keepalive\n\n"
        await asyncio.sleep(tick)
