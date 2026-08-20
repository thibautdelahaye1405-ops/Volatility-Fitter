"""Unified snapshot fetch (V3.7 item 15): quotes + spot + prior auto-roll.

``POST /fetch/snapshot`` sequences the two legacy fetch verbs and an optional
CHEAP prior roll into one action:

  (i)   refresh every chosen ticker's option chain — the ``fetch_options``
        chain-refresh block (same ≤8-wide pool): nodes go stale, the data
        version bumps, calibrated pointers + spot shift are PRESERVED (the
        frozen-until-Calibrate contract);
  (ii)  probe live spots and apply them as spot SHIFTS — the ``fetch_spots``
        transport block (shift = live/anchor - 1): pure transport, no refit;
  (iii) when ``OptionsSettings.autoRollPriorOnFetch`` is on: roll each ticker's
        ACTIVE prior to its latest SAVED snapshot — the O(1) saved branch of
        the freshness ladder ONLY. Never the prev-close recalibration ladder
        (volfit.api.priors._recalibrate_at_prev_close), never an as-of flip.
        A roll bumps the ticker's active-prior version (folded into the fit /
        affine cache keys), so the NEXT calibration sees the rolled prior with
        zero extra machinery; spot re-anchoring of the prior itself stays
        read-time transport. Tickers with no saved snapshot, or whose saved
        snapshot is already the active prior, are SKIPPED — ``set_active_prior``
        logs a governance event on every call, so no-ops must not reach it;
  (iv)  when ``autoCalibrate`` is on: background-calibrate all lit nodes (the
        same tail as ``fetch_options``).

The legacy ``/fetch/spots`` and ``/fetch/options`` endpoints are preserved
verbatim; with ``autoRollPriorOnFetch`` off (the default) this verb is exactly
their sequence.
"""

from __future__ import annotations

from volfit.api import workflow
from volfit.api.schemas import FetchResult
from volfit.api.state import AppState


def _roll_saved_priors(state: AppState, tickers: list[str]) -> int:
    """The CHEAP prior roll: activate each ticker's latest SAVED snapshot.

    O(1) per ticker (in-memory cache, then one store read) — never the
    expensive prev-close recalibration ladder. A no-op detector guards the
    governance log: when the saved snapshot IS already the active prior (same
    object, or the same savedTs/dataTs identity after a store round-trip) the
    ticker is skipped, so repeated snapshot fetches neither flood the audit
    trail with ``prior_selection`` events nor bump the active-prior version
    (which would needlessly re-key warm fits). Returns the tickers rolled."""
    rolled = 0
    for ticker in tickers:
        snap = state.latest_prior_snapshot(ticker)
        if snap is None:
            continue  # nothing saved — never fall through to the ladder here
        current = state.active_prior(ticker)
        if current is not None and (
            current is snap
            or (current.savedTs == snap.savedTs and current.dataTs == snap.dataTs)
        ):
            continue  # already active: no event, no version bump
        state.set_active_prior(ticker, snap, "saved")
        rolled += 1
    return rolled


def fetch_snapshot(
    state: AppState, tickers: list[str] | None = None, fit_mode: str = "mid"
) -> FetchResult:
    """The unified fetch: chains -> spot transport -> optional cheap prior roll
    -> optional auto-calibrate (the module docstring's (i)-(iv) sequence).

    Returns the same shape as ``fetch_options``: the tickers whose chain
    refreshed, a per-ticker spot (the live probe where it succeeded, else the
    chain spot), and whether an auto-calibration job was started."""
    chosen = tickers if tickers is not None else state.active_tickers()
    fetched, spots = workflow._refresh_chains(state, chosen)  # (i) quotes
    live = workflow.fetch_spots(state, chosen)  # (ii) spot shift — no refit
    spots.update({t: probe.liveSpot for t, probe in live.items()})
    if state.options().autoRollPriorOnFetch:  # (iii) cheap roll only
        _roll_saved_priors(state, chosen)
    started = False
    if state.options().autoCalibrate and fetched:  # (iv) same tail as fetch_options
        started = workflow.calibrate_all(state, fit_mode)
    return FetchResult(tickers=fetched, spots=spots, calibrationStarted=started)
