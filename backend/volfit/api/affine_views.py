"""Density / term-structure / table views derived from the local-vol-affine fit.

The Local Vol workspace mirrors the Parametric workspace's sub-tabs (ROADMAP
Phase 10), but every view is derived from the calibrated piecewise-affine
local-VARIANCE surface (volfit.api.affine_fit) rather than the LQD backbone.

All three views are reconstructed from the cached ``AffineFitResponse`` — each
expiry's arbitrage-free smile is already returned as reconstructed (k, vol)
points (the Dupire PDE call prices inverted through Black), so we wrap those
points in a light interpolating SmileModel and reuse the exact same numeric
pipeline the non-LQD overlays use:

  * **density**  — Breeden-Litzenberger via models.diagnostics.numeric_density
    (analytics._distribution_model), so the LV density chart is bitwise the same
    machinery as the Parametric SVI/sigmoid density;
  * **term**     — exact ATM handle sqrt(w(0)/t), var-swap by log-contract
    replication, and the event-dilated dense curve, identical in shape to
    POST /term (events default off here — the LV surface has no event clock);
  * **table**    — per-strike reconstructed IVs + discounted Black prices, the
    same row shape as GET /smiles/{t}/{e}/table.

Because everything derives from the cached affine response, these are O(1) after
the first fit (affine_payload caches the calibration).
"""

from __future__ import annotations

from datetime import date

import numpy as np

from volfit.api.affine_fit import affine_payload
from volfit.api.analytics import (
    CURVE_POINTS,
    CURVE_T_MIN,
    CURVE_T_PAD,
    _distribution_model,
    _dividend_markers,
    _tau_of,
)
from volfit.api.schemas import (
    DensityResponse,
    TableResponse,
    TableRow,
    TermCurve,
    TermPoint,
    TermStructureResponse,
)
from volfit.api.schemas_affine import AffineFitRequest, AffineSmile
from volfit.api.state import AppState
from volfit.api.table import _price
from volfit.calib.weighted_time import interp_total_variance
from volfit.models.diagnostics import numeric_var_swap_w


class _ReconSlice:
    """SmileModel wrapper over one reconstructed affine smile (k, w) points.

    Linearly interpolates total variance between the reconstructed nodes and
    flat-extrapolates beyond them (np.interp default) — fine for the density
    tails and the var-swap replication integral, which are dominated by the
    central mass the affine fit actually constrains.
    """

    def __init__(self, k: np.ndarray, w: np.ndarray) -> None:
        order = np.argsort(k)
        self._k = np.asarray(k, dtype=float)[order]
        self._w = np.asarray(w, dtype=float)[order]

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        return np.interp(np.asarray(k, dtype=float), self._k, self._w)

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        return np.sqrt(np.maximum(self.implied_w(k), 0.0) / t)


def _recon_slice(smile: AffineSmile) -> _ReconSlice:
    """Build the interpolating slice from a reconstructed smile's points.

    The model vols are in the event-weighted clock (smile.tau), so total variance
    is vol^2 * tau (= the calendar variance from the price); density and var-swap
    replication then come out clock-invariant, like the Parametric path."""
    tau = smile.tau if smile.tau > 0.0 else smile.t
    k = np.array([p.k for p in smile.model], dtype=float)
    w = np.array([p.vol * p.vol * tau for p in smile.model], dtype=float)
    return _ReconSlice(k, w)


def _affine_response(state: AppState, ticker: str, request: AffineFitRequest):
    """Run/serve the cached affine fit; raises like POST /fit/affine."""
    return affine_payload(state, ticker, request)


def _find_smile(response, expiry: str) -> AffineSmile:
    """The reconstructed smile for one expiry ISO, or ValueError (-> 422)."""
    for smile in response.smiles:
        if smile.expiry == expiry:
            return smile
    raise ValueError(f"no affine smile for expiry {expiry!r}")


# ------------------------------------------------------------------- density
def affine_density(
    state: AppState, ticker: str, expiry: str, request: AffineFitRequest
) -> DensityResponse:
    """Risk-neutral density of one expiry's reconstructed LV smile.

    Mirrors the Parametric Density view (analytics._distribution_model); the LV
    surface carries no saved prior, so ``prior`` is always None.
    """
    response = _affine_response(state, ticker, request)
    smile = _find_smile(response, expiry)
    current = _distribution_model(_recon_slice(smile))
    return DensityResponse(current=current, prior=None)


# ------------------------------------------------------------ term structure
def affine_term(
    state: AppState, ticker: str, request: AffineFitRequest
) -> TermStructureResponse:
    """ATM / var-swap term structure of the reconstructed LV surface.

    Same shape as POST /term so the Local Vol workspace reuses TermChart. The
    event clock comes from the SHARED per-ticker event calendar (the same one
    the Parametric Term edits), so event-time dilation is consistent across both
    workspaces; with no events it reduces to the identity clock. Discrete
    dividend ex-dates are still surfaced as informational markers.
    """
    response = _affine_response(state, ticker, request)
    tau_of = _tau_of(state, ticker)  # same weighted clock as the Parametric term

    points: list[TermPoint] = []
    ts: list[float] = []  # calendar maturities (axis)
    taus: list[float] = []  # weighted variance years (dilated axis)
    w0s: list[float] = []  # ATM total variance (calendar-invariant)
    for smile in response.smiles:
        recon = _recon_slice(smile)
        tau = smile.tau if smile.tau > 0.0 else smile.t
        w0 = float(recon.implied_w(0.0))  # calendar variance (recon uses tau)
        atm_vol = float(np.sqrt(max(w0, 0.0) / tau))
        points.append(
            TermPoint(
                expiry=smile.expiry,
                t=smile.t,
                tau=tau,
                atmVol=atm_vol,
                w0=w0,
                varSwapVol=float(np.sqrt(numeric_var_swap_w(recon) / tau)),
                maxIvErrorBp=smile.maxIvErrorBp,
            )
        )
        ts.append(smile.t)
        taus.append(tau)
        w0s.append(w0)

    violations = sum(1 for near, far in zip(w0s, w0s[1:]) if far < near)

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


# --------------------------------------------------------------- quote table
def affine_table(
    state: AppState, ticker: str, expiry: str, request: AffineFitRequest
) -> TableResponse:
    """Per-strike quote / reconstructed-IV / price table of one LV expiry.

    Same row shape as GET /smiles/{t}/{e}/table: the displayed quote band, the
    reconstructed model IV at each k, and discounted OTM Black prices at the band
    IVs. Forward/discount come from the node's resolved forward policy.
    """
    response = _affine_response(state, ticker, request)
    smile = _find_smile(response, expiry)
    expiry_date = date.fromisoformat(smile.expiry)
    forward = state.resolved_forward(ticker, expiry_date)
    fwd, discount, t = forward.forward, forward.discount, smile.t
    # IVs/prices reconstruct in the weighted clock (tau); ``t`` (calendar) is the
    # displayed maturity. recon total variance uses tau, so prices stay market.
    tau = smile.tau if smile.tau > 0.0 else smile.t

    recon = _recon_slice(smile)
    ks = np.array([q.k for q in smile.quotes], dtype=float)
    model_iv = recon.implied_vol(ks, tau) if ks.size else np.zeros(0)

    rows: list[TableRow] = []
    for i, q in enumerate(smile.quotes):
        k = q.k
        rows.append(
            TableRow(
                index=q.index,
                strike=fwd * float(np.exp(k)),
                type="C" if k >= 0.0 else "P",
                k=k,
                bidIv=q.bid,
                midIv=q.mid,
                askIv=q.ask,
                modelIv=float(model_iv[i]),
                bidPrice=_price(k, q.bid, tau, fwd, discount),
                midPrice=_price(k, q.mid, tau, fwd, discount),
                askPrice=_price(k, q.ask, tau, fwd, discount),
                excluded=q.excluded,
                amended=q.amended,
            )
        )
    return TableResponse(
        ticker=ticker, expiry=smile.expiry, t=t, forward=fwd, discount=discount, rows=rows
    )
