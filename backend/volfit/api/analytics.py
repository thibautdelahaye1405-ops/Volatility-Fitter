"""Term-structure and density analytics over cached slice fits (Phase 6).

Two read-only views assembled from the same fit cache that backs the smile
endpoints (volfit.api.service.fit_or_get), so they are always consistent
with what the Smile Viewer charts:

* ``term_structure`` — one point per fitted expiry (exact ATM handles from
  volfit.models.lqd.atm, var-swap strike by log-contract replication) plus
  a dense ATM total-variance curve interpolated linearly in *event-dilated*
  time (volfit.calib.event_time): flat forward variance between expiries
  away from events, each event's variance lumped exactly on its date.
  ``calendarViolations`` counts adjacent expiries whose ATM total variance
  strictly decreases.
* ``density_payload`` — the risk-neutral log-return density f_X on x = Q(z)
  and the quantile function (u, Q(u)) of the current fit, trimmed to the
  central probability mass and strided down to chart size. A saved prior
  (state.PriorRecord) carries its fitted LQDParams, so its slice is rebuilt
  with build_slice (bitwise-identical to the original fit's slice) and
  rendered through the same pipeline.

Lives outside service.py purely for the file-size policy; same conventions
(pure functions over AppState returning pydantic response models).
"""

from __future__ import annotations

import numpy as np

from datetime import date

from volfit.api.schemas import (
    DensityResponse,
    DistributionArrays,
    DividendMarker,
    TermCurve,
    TermPoint,
    TermStructureRequest,
    TermStructureResponse,
)
from volfit.api.displayed import (
    displayed_atm_vol,
    displayed_max_iv_error,
    displayed_slice,
    displayed_var_swap_w,
)
from volfit.api.service import fit_or_get
from volfit.api.state import AppState
from volfit.calib.event_time import Event, EventClock
from volfit.models.base import SmileModel
from volfit.models.diagnostics import numeric_density
from volfit.models.lqd.quadrature import LQDSlice, build_slice

#: Dense term-structure grid: 80 samples from 0.02y to 5% past the last expiry.
CURVE_POINTS = 80
CURVE_T_MIN = 0.02
CURVE_T_PAD = 1.05

#: Density/quantile chart arrays: keep the central mass u in [U_TRIM, 1-U_TRIM]
#: (~99.8% of probability), then stride down to at most MAX_CHART_POINTS.
U_TRIM = 1e-3
MAX_CHART_POINTS = 241

#: Dividend modes whose discrete ex-dates are surfaced as term-structure
#: markers (the "continuous" yield has no dated cash flows to mark).
_DISCRETE_DIV_MODES = ("discrete_absolute", "discrete_proportional", "mixed")


def _dividend_markers(
    state: AppState, ticker: str, clock: EventClock, t_max: float
) -> list[DividendMarker]:
    """Discrete ex-dates of the ticker inside (0, t_max], on both clocks.

    Only the modes that actually use the discrete schedule contribute; the
    forward already drops at each ex-date, so these are informational markers
    (their dilated tau lets the chart place them under either clock mode).
    """
    market = state.market_settings(ticker)
    if market.dividendMode not in _DISCRETE_DIV_MODES:
        return []
    markers: list[DividendMarker] = []
    for spec in market.dividends:
        dt = state.year_fraction(date.fromisoformat(spec.exDate))
        if 0.0 < dt <= t_max:
            markers.append(
                DividendMarker(
                    exDate=spec.exDate,
                    t=dt,
                    tau=float(clock.dilated_time(dt)),
                    amount=spec.amount,
                )
            )
    return sorted(markers, key=lambda m: m.t)


# ------------------------------------------------------------ term structure
def _event_clock(request: TermStructureRequest) -> EventClock:
    """The request's dilated clock (identity when disabled or eventless)."""
    events = tuple(Event(time=e.time, weight=e.weight, label=e.label) for e in request.events)
    return EventClock(events=events, enabled=request.eventsEnabled)


def term_structure(
    state: AppState, ticker: str, request: TermStructureRequest
) -> TermStructureResponse:
    """Per-expiry ATM/var-swap points plus the event-dilated dense curve.

    Slice fits flow through fit_or_get with the request's fit mode, and every
    point is read from the *displayed* fit (the chosen model's overlay when one
    is active, else the LQD slice), so atmVol/varSwapVol here are bitwise-equal
    to GET /smiles' diagnostics for the same model.
    """
    forwards = state.forwards(ticker)  # raises UnknownNodeError when unknown
    clock = _event_clock(request)

    points: list[TermPoint] = []
    ts: list[float] = []
    w0s: list[float] = []
    for expiry in sorted(forwards):
        iso = expiry.isoformat()
        record = fit_or_get(state, ticker, iso, request.fitMode)
        t = record.prepared.t
        atm_vol = displayed_atm_vol(record)
        w0 = atm_vol * atm_vol * t  # ATM total variance of the displayed fit
        points.append(
            TermPoint(
                expiry=iso,
                t=t,
                tau=float(clock.dilated_time(t)),
                atmVol=atm_vol,
                w0=w0,
                varSwapVol=float(np.sqrt(displayed_var_swap_w(record) / t)),
                maxIvErrorBp=displayed_max_iv_error(record) * 1e4,
            )
        )
        ts.append(t)
        w0s.append(w0)

    violations = sum(1 for near, far in zip(w0s, w0s[1:]) if far < near)

    # Dense curve: w(T) linear in dilated time tau(T) — the whole point of
    # the event clock (flat forward variance per dilated-time unit).
    t_max = CURVE_T_PAD * max(ts)
    t_grid = np.linspace(CURVE_T_MIN, t_max, CURVE_POINTS)
    w_grid = np.asarray(clock.interpolate_total_variance(t_grid, np.array(ts), np.array(w0s)))
    curve = TermCurve(
        t=t_grid.tolist(),
        tau=np.asarray(clock.dilated_time(t_grid)).tolist(),
        w=w_grid.tolist(),
        vol=np.sqrt(w_grid / t_grid).tolist(),
    )
    return TermStructureResponse(
        ticker=ticker,
        points=points,
        curve=curve,
        calendarViolations=violations,
        dividends=_dividend_markers(state, ticker, clock, t_max),
    )


# ------------------------------------------------------------------- density
def _trim(idx_mask: np.ndarray) -> np.ndarray:
    """Central-mass indices strided down to at most MAX_CHART_POINTS."""
    keep = np.flatnonzero(idx_mask)
    stride = max(1, -(-keep.size // MAX_CHART_POINTS))  # ceil division
    return keep[::stride]


def _distribution(slice_: LQDSlice) -> DistributionArrays:
    """Exact LQD density + quantile arrays, trimmed and chart-sized.

    LQDSlice.density() returns the pdf on x = Q(z); the quantile pairs (u, Q)
    live on the same z grid, so one central-mass mask + stride keeps x/density
    and u/quantile aligned point-for-point.
    """
    x, pdf = slice_.density()
    idx = _trim((slice_.u >= U_TRIM) & (slice_.u <= 1.0 - U_TRIM))
    return DistributionArrays(
        x=x[idx].tolist(),
        density=pdf[idx].tolist(),
        u=slice_.u[idx].tolist(),
        quantile=slice_.q_z[idx].tolist(),
    )


def _distribution_model(slice_: SmileModel) -> DistributionArrays:
    """Model-agnostic density + quantile for a non-LQD overlay (SVI / sigmoid).

    Breeden-Litzenberger via models.diagnostics.numeric_density: x = quantile =
    log-return k, u = CDF, so the chart matches the LQD layout (the quantile
    chart plots (u, k) = the inverse CDF). Trimmed to the central probability
    mass like the LQD path.
    """
    k, pdf, cdf = numeric_density(slice_)
    idx = _trim((cdf >= U_TRIM) & (cdf <= 1.0 - U_TRIM))
    return DistributionArrays(
        x=k[idx].tolist(),
        density=pdf[idx].tolist(),
        u=cdf[idx].tolist(),
        quantile=k[idx].tolist(),
    )


def density_payload(state: AppState, ticker: str, expiry: str, fit_mode: str) -> DensityResponse:
    """Current-fit distribution plus the saved prior's, when one exists.

    The current distribution follows the chosen display model (LQD exact, else
    the SVI / Multi-Core-SIV overlay's own Breeden-Litzenberger density); the
    saved prior is always the LQD snapshot that was stored.
    """
    record = fit_or_get(state, ticker, expiry, fit_mode)
    if record.display is not None:
        current = _distribution_model(displayed_slice(record))
    else:
        current = _distribution(record.result.slice)
    saved = state.get_prior((ticker, expiry))
    prior = None if saved is None else _distribution(build_slice(saved.params))
    return DensityResponse(current=current, prior=prior)
