"""Spot-side workflow blocks: the live spot probe and the market follow sync.

  * ``fetch_spots``        — probe the provider spot per ticker (a request) and,
    for the tickers FOLLOWING THE MARKET (Spot panel selector), apply the
    implied return vs the calibration anchor as the spot shift — pure
    transport, no refit; a scenario ticker keeps its dial, the probe is still
    remembered for the readout;
  * ``sync_market_shifts`` — move the market-following tickers to the
    prevailing market spot WITHOUT a request (the streaming book, else the
    newer of the last probe and the fetched chain) — the scheduler runs it at
    the spot-poll cadence while a book streams, the chain fetches after a
    refetch.

Both are re-exported by volfit.api.workflow (the scheduler and the tests
address them there).
"""

from __future__ import annotations

from volfit.api.schemas import LiveSpot
from volfit.api.state import AppState


def fetch_spots(state: AppState, tickers: list[str] | None = None) -> dict[str, LiveSpot]:
    """Probe the live provider spot per ticker and apply it as a spot shift.

    Pure transport (no recalibration): the implied return vs the calibration
    anchor becomes the spot shift, moving the smile / term / LV grid. Returns the
    per-ticker probe so the UI can show the live level.
    """
    chosen = tickers if tickers is not None else state.active_tickers()
    from volfit.api import workflow  # lazy: workflow re-exports this module

    out: dict[str, LiveSpot] = {}
    for ticker in chosen:
        try:
            with state.activity.activity(
                "fetch", f"Fetching {ticker} spot from {workflow._source_label(state, ticker)}"
            ):
                anchor = float(state.anchor_spot(ticker))
                live = float(state.live_spot(ticker))
        except Exception:
            continue
        ret = (live / anchor - 1.0) if anchor > 0.0 else 0.0
        # Only a ticker following the MARKET moves; a scenario (the dial) keeps
        # its hypothetical spot — the probe is still remembered for the readout.
        if state.spot_follow(ticker) == "market":
            state.set_spot_shift(ticker, ret)
        out[ticker] = LiveSpot(ticker=ticker, anchorSpot=anchor, liveSpot=live, spotReturn=ret)
    return out


def sync_market_shifts(state: AppState, tickers: list[str] | None = None) -> list[str]:
    """Move every MARKET-following ticker's shift to the prevailing market spot
    (the streaming book — a free read — else the newer of the last probe and
    the fetched chain). No request, no refit. Returns the tickers whose shift
    changed. The scheduler runs this at the spot-poll cadence while a book
    streams; the chain fetches run it after a refetch."""
    chosen = tickers if tickers is not None else state.active_tickers()
    moved: list[str] = []
    for ticker in chosen:
        if state.spot_follow(ticker) != "market":
            continue
        try:
            before = state.spot_shift(ticker)
            if state.sync_market_shift(ticker) != before:
                moved.append(ticker)
        except Exception:
            continue
    return moved
