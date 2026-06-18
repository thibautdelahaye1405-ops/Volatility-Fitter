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
    StackedDensityItem,
    StackedDensityResponse,
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
from volfit.api.service import K_DISPLAY_LO, fill_nonfinite, fit_or_get
from volfit.api.state import AppState
from volfit.calib.weighted_time import interp_total_variance, weighted_variance_years
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


def _tau_of(state: AppState, ticker: str):
    """A callable t_calendar -> tau (event-weighted variance years) for a ticker.

    Uses the SAME source as every fit (volfit.api.service.variance_time): the
    shared event calendar + OptionsSettings.eventsEnabled / normalizeEvents, so
    the term curve, the dividend markers and the per-expiry points share one
    clock. Reduces to the identity when the event clock is off or eventless.
    """
    options = state.options()
    events = state.events(ticker)
    if not options.eventsEnabled or not events:
        return lambda t: t
    pairs = [(e.time, e.weight) for e in events]
    return lambda t: weighted_variance_years(t, pairs, normalize=options.normalizeEvents)


def _dividend_markers(
    state: AppState, ticker: str, tau_of, t_max: float
) -> list[DividendMarker]:
    """Discrete ex-dates of the ticker inside (0, t_max], on both clocks.

    Only the modes that actually use the discrete schedule contribute; the
    forward already drops at each ex-date, so these are informational markers
    (their weighted tau lets the chart place them under either clock mode).
    """
    market = state.market_settings(ticker)
    if market.dividendMode not in _DISCRETE_DIV_MODES:
        return []
    markers: list[DividendMarker] = []
    for spec in market.dividends:
        dt = state.year_fraction(date.fromisoformat(spec.exDate))
        if 0.0 < dt <= t_max:
            markers.append(
                DividendMarker(exDate=spec.exDate, t=dt, tau=float(tau_of(dt)), amount=spec.amount)
            )
    return sorted(markers, key=lambda m: m.t)


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
    tau_of = _tau_of(state, ticker)
    from volfit.api import prior_transport

    active_prior = state.active_prior(ticker)
    regime = state.dynamics_regime()

    points: list[TermPoint] = []
    ts: list[float] = []  # calendar maturities (the x-axis)
    taus: list[float] = []  # event-weighted variance years (the dilated axis)
    w0s: list[float] = []  # ATM total variance (calendar-invariant, from price)
    for expiry in sorted(forwards):
        iso = expiry.isoformat()
        record = fit_or_get(state, ticker, iso, request.fitMode)
        t = record.prepared.t
        tau = record.prepared.tau
        atm_vol = displayed_atm_vol(record)  # weighted vol = sqrt(w0 / tau)
        w0 = atm_vol * atm_vol * tau  # ATM total variance (calendar-invariant)
        vs_session = state.varswap_session_if_exists((ticker, iso))
        # Active prior's ATM vol at this expiry, transported to the current forward.
        prior_vol: float | None = None
        prior_node = prior_transport.prior_node(active_prior, iso)
        if prior_node is not None:
            atm = prior_transport.transported_prior_points(
                prior_node, float(record.prepared.forward), regime, np.array([0.0])
            )
            prior_vol = atm[0].vol if atm else None
        points.append(
            TermPoint(
                expiry=iso,
                t=t,
                tau=tau,
                atmVol=atm_vol,
                w0=w0,
                varSwapVol=float(np.sqrt(displayed_var_swap_w(record) / tau)),
                varSwapQuote=None if vs_session is None else vs_session.state.level,
                varSwapExcluded=bool(vs_session is not None and vs_session.state.excluded),
                maxIvErrorBp=displayed_max_iv_error(record) * 1e4,
                priorVol=prior_vol,
            )
        )
        ts.append(t)
        taus.append(tau)
        w0s.append(w0)

    violations = sum(1 for near, far in zip(w0s, w0s[1:]) if far < near)

    # Dense curve over the CALENDAR maturity grid; total variance w(T) accrues
    # linearly in the WEIGHTED clock tau (flat forward variance per weighted-time
    # unit between expiries), and the working vol is sqrt(w / tau).
    t_max = CURVE_T_PAD * max(ts)
    t_grid = np.linspace(CURVE_T_MIN, t_max, CURVE_POINTS)
    tau_grid = np.array([tau_of(float(t)) for t in t_grid])
    w_grid = interp_total_variance(tau_grid, np.array(taus), np.array(w0s))
    curve = TermCurve(
        t=t_grid.tolist(),
        tau=tau_grid.tolist(),
        w=w_grid.tolist(),
        vol=np.sqrt(np.maximum(w_grid, 0.0) / tau_grid).tolist(),
    )
    return TermStructureResponse(
        ticker=ticker,
        points=points,
        curve=curve,
        calendarViolations=violations,
        dividends=_dividend_markers(state, ticker, tau_of, t_max),
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


def stacked_density_arrays(
    slice_: SmileModel, k_min: float = K_DISPLAY_LO
) -> tuple[np.ndarray, np.ndarray]:
    """(x, density) for the stacked-densities overlay, left-extended to ``k_min``.

    Uses the Breeden-Litzenberger functional (numeric_density) on a grid widened
    to reach ``k_min`` on the left, then keeps ``k >= k_min`` (the displayed lower
    bound, matching the smile/surface range) and trims the upper tail to the
    central probability mass (``cdf <= 1 - U_TRIM``). The deep-left pdf is ~0, so
    this draws the full left tail without distorting the central shape. Works for
    any model (LQD slice or SVI / Multi-Core-SIV overlay)."""
    k, pdf, cdf = numeric_density(slice_, half_floor=abs(k_min))
    keep = _trim((k >= k_min) & (cdf <= 1.0 - U_TRIM))
    return k[keep], pdf[keep]


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


def stacked_densities(state: AppState, ticker: str, fit_mode: str) -> StackedDensityResponse:
    """Risk-neutral density of every fitted expiry of a ticker, nearest first.

    Each curve follows the chosen display model (LQD exact, else the SVI /
    Multi-Core-SIV overlay's Breeden-Litzenberger density), the same per-node
    pipeline as density_payload — so overlaying them shows every density stays
    non-negative (no butterfly arbitrage on any slice).
    """
    forwards = state.forwards(ticker)  # raises UnknownNodeError when unknown
    items: list[StackedDensityItem] = []
    for expiry in sorted(forwards):
        iso = expiry.isoformat()
        record = fit_or_get(state, ticker, iso, fit_mode)
        slice_ = displayed_slice(record)
        # Density left-extended to the display lower bound (k_min = -1.4), so the
        # overlay's x-axis spans the same range as the smile / surface.
        x, density = stacked_density_arrays(slice_)
        # Per-expiry axis context: the displayed-model IV at each density x (= the
        # log-moneyness grid), so the overlay can re-coordinate to Δ / strike / etc.
        tau = record.prepared.tau
        vol = fill_nonfinite(np.sqrt(np.maximum(slice_.implied_w(x), 0.0) / tau))
        items.append(
            StackedDensityItem(
                expiry=iso,
                t=record.prepared.t,
                x=x.tolist(),
                density=density.tolist(),
                forward=float(record.prepared.forward),
                atmVol=displayed_atm_vol(record),
                vol=vol.tolist(),
            )
        )
    return StackedDensityResponse(ticker=ticker, expiries=items)
