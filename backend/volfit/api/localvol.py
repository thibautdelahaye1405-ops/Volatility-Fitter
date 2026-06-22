"""Local-vol service: surface extraction + sticky-local-vol-grid scenarios.

Bridges the fitted smile surface to the local-volatility grid model
(volfit.models.localvol) for the API (ROADMAP Phase 2 "API exposure" and
Phase 8 "true sticky-local-vol-grid mode"). The Dupire extraction only needs
total implied variance w(k, t), i.e. the SmileModel.implied_w interface, so it
follows the *displayed* model (LQD by default, else the SVI / Multi-Core-SIV
overlay) — there is no structural LQD dependency. Caveat: Dupire's denominator
(small-w, second strike derivative) is ill-conditioned and assumes a smooth
arbitrage-free input; LQD/SVI are arbitrage-free by construction, but the signed
Multi-Core-SIV cores can violate butterfly, in which case the extraction clips
the offending local variances and the no-arb diagnostics below flag it.

- ``localvol_record``: fit every expiry of a ticker (through the same cached
  slice fits as GET /smiles, so quote edits apply), interpolate total
  implied variance linearly in t (w = 0 at t = 0), and extract a Dupire
  local-vol grid sampled at bucket midpoints — piecewise-constant forward-
  variance buckets between listed expiries ("pw_t"), the market convention.
  Cached per (ticker, fit mode, per-expiry session versions, fit settings).
- ``localvol_payload``: the grid + the model's no-arbitrage diagnostics
  (butterfly density minima, calendar residuals, repair counters).
- ``scenario_sticky_grid``: the exact sticky-local-vol dynamics — hold
  sigma_loc fixed in *absolute strike*, move the forward by delta = log(1+r),
  reprice through the Dupire forward PDE. In new-forward log-moneyness the
  grid simply shifts: sigma'(k, t) = sigma(k + delta, t). The realized SSR
  is reported instead of the SSR=2 shape-rule approximation used by the
  named "sticky_local_vol" regime.

Caveat (measured, not hidden): the shortest bucket's local vol inherits any
curvature wiggle of the fitted smile amplified by the small-w Dupire
denominator — bp-level fit error there can flatten the bucket's ATM slope
and drag the realized short-expiry SSR well below the theoretical ~2.
Longer buckets land in the expected 1.5-2.5 range. This is the classic
short-dated Dupire ill-conditioning (ROADMAP risk #4); the grid diagnostics
expose it rather than smooth it away.
"""

from __future__ import annotations

import numpy as np

from volfit.api.schemas import (
    LocalVolGridResponse,
    ScenarioRequest,
    ScenarioResponse,
)
from volfit.api.state import AppState
from volfit.models.localvol import LocalVolGrid, LocalVolModel, extract_grid

#: Extraction grid: strikes across the union of quoted ranges, padded.
#: 81 nodes keep the short-expiry ATM skew resolved (41 visibly flattens the
#: realized SSR of the nearest bucket).
N_K_NODES = 81
K_PAD = 0.02
#: PDE mesh for repricing (half the default — scenario latency over last-bp).
PDE_N_K = 601

_CACHE_ATTR = "_localvol_cache"  # AppState attribute, added lazily here


def _surface_records(state: AppState, ticker: str, fit_mode: str):
    """All cached slice fits of a ticker, nearest expiry first."""
    from volfit.api import service  # local import: service imports this module

    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    pairs = [(iso, service.fit_or_get(state, ticker, iso, fit_mode)) for iso in isos]
    return [(iso, rec) for iso, rec in pairs if rec is not None]  # skip uncalibrated


def _w_surface(ts: np.ndarray, slices: list):
    """Total-variance surface w(k, t): linear in t between slices, 0 at t=0.

    Within [0, t_last] this is the standard variance-time interpolation
    (calendar-safe when the slice fits are); beyond t_last the last bucket's
    forward variance is extended flat.
    """

    def w(k: np.ndarray, t: float) -> np.ndarray:
        k = np.asarray(k, dtype=float)
        t = float(t)
        w_rows = [s.implied_w(k) for s in slices]  # lazily small: few expiries
        if t <= 0.0:
            return np.zeros_like(k)
        i = int(np.searchsorted(ts, t))
        if i == 0:
            return w_rows[0] * (t / ts[0])
        if i >= ts.size:  # flat forward variance beyond the last expiry
            if ts.size == 1:
                return w_rows[-1] * (t / ts[-1])
            slope = (w_rows[-1] - w_rows[-2]) / (ts[-1] - ts[-2])
            return w_rows[-1] + np.maximum(slope, 0.0) * (t - ts[-1])
        lam = (t - ts[i - 1]) / (ts[i] - ts[i - 1])
        return (1.0 - lam) * w_rows[i - 1] + lam * w_rows[i]

    return w


def localvol_record(state: AppState, ticker: str, fit_mode: str):
    """(LocalVolModel, extraction, expiry ISOs, ts) for a ticker, cached.

    The cache key carries every expiry's quote-edit session version, so an
    edit anywhere on the surface triggers re-extraction (same convention as
    the slice-fit cache).
    """
    from volfit.api import service

    isos = [e.isoformat() for e in sorted(state.forwards(ticker))]
    versions = tuple(service.session_version(state, ticker, iso) for iso in isos)
    # spot_version: a spot move transports the slice fits, so re-extract the grid.
    # data_version: a fresh options fetch + recalibration changes the fits.
    key = (
        ticker,
        fit_mode,
        versions,
        state.settings_version,
        state.forwards_version(ticker),
        state.events_version(ticker),
        state.options_version,
        state.spot_version_for(ticker),  # per-ticker: another name's spot move won't bust this
        state.data_version(ticker),
    )
    cache = getattr(state, _CACHE_ATTR, None)
    if cache is None:
        cache = {}
        setattr(state, _CACHE_ATTR, cache)
    hit = cache.get(key)
    if hit is not None:
        return hit

    from volfit.api import service

    records = _surface_records(state, ticker, fit_mode)
    ts = np.array([rec.prepared.t for _, rec in records])
    # Extract from the displayed model's surface (overlay when active, else LQD).
    slices = [service.displayed_slice(rec) for _, rec in records]
    k_lo = min(float(rec.prepared.k.min()) for _, rec in records) - K_PAD
    k_hi = max(float(rec.prepared.k.max()) for _, rec in records) + K_PAD
    k_nodes = np.linspace(k_lo, k_hi, N_K_NODES)

    # Sample each forward-variance bucket at its midpoint; the t-step for the
    # w_t finite difference must stay inside the bucket.
    edges = np.concatenate([[0.0], ts])
    mids = 0.5 * (edges[:-1] + edges[1:])
    dt = 0.2 * float(np.min(np.diff(edges)))
    extraction = extract_grid(
        _w_surface(ts, slices), k_nodes, mids, dk=2e-3, dt=dt
    )
    # Rebuild as pw_t with bucket *left edges* as nodes: row i (sampled at
    # mids[i]) then applies on [edges[i], edges[i+1]) — constant forward
    # variance per listed-expiry bucket.
    t_nodes = np.concatenate([[min(1e-6, 0.5 * ts[0])], ts[:-1]])
    grid = LocalVolGrid(k=k_nodes, t=t_nodes, sigma=extraction.grid.sigma, interp="pw_t")
    model = LocalVolModel(grid, n_k=PDE_N_K)
    out = (model, extraction, isos, ts)
    cache[key] = out
    return out


def localvol_payload(state: AppState, ticker: str, fit_mode: str) -> LocalVolGridResponse:
    """Grid + no-arbitrage diagnostics for GET /localvol/{ticker}."""
    model, extraction, isos, ts = localvol_record(state, ticker, fit_mode)
    diag = model.diagnostics(ts)
    return LocalVolGridResponse(
        ticker=ticker,
        expiries=isos,
        t=[float(v) for v in ts],
        k=[float(v) for v in model.grid.k],
        sigma=[[float(v) for v in row] for row in model.grid.sigma],
        nNan=extraction.n_nan,
        nClipped=extraction.n_clipped,
        minDensity=[float(v) for v in diag.min_density],
        calendarViolation=[float(v) for v in diag.calendar_violation],
        arbitrageFree=bool(diag.arbitrage_free),
    )


def scenario_sticky_grid(state: AppState, request: ScenarioRequest) -> ScenarioResponse:
    """True sticky-local-vol-grid scenario: fixed-strike grid, PDE reprice."""
    from volfit.api import service

    record = service.fit_or_get(state, request.ticker, request.expiry, request.fitMode)
    if record is None:  # gated, never calibrated: nothing to transport yet
        return ScenarioResponse(
            k=[], baseVol=[], shiftedVol=[], ssr=2.0, regime="sticky_local_vol_grid"
        )
    t = record.prepared.t
    grid_k = np.linspace(
        float(record.prepared.k.min()) - K_PAD,
        float(record.prepared.k.max()) + K_PAD,
        service.N_MODEL_POINTS,
    )
    model, _, _, _ = localvol_record(state, request.ticker, request.fitMode)
    delta = float(np.log1p(request.spotReturn))

    def reprice(lv_grid: LocalVolGrid) -> np.ndarray:
        slice_ = LocalVolModel(lv_grid, n_k=PDE_N_K).slice_at(t)
        return np.sqrt(slice_.implied_w(grid_k) / t)

    base = reprice(model.grid)
    if delta == 0.0:
        shifted = base
    else:
        # sigma'(k) = sigma(k + delta): shift the k nodes by -delta.
        shifted = reprice(
            LocalVolGrid(
                k=model.grid.k - delta,
                t=model.grid.t,
                sigma=model.grid.sigma,
                interp=model.grid.interp,
            )
        )
    # Realized SSR: d sigma_atm / d ln F over the displayed fit's ATM skew.
    skew = service.displayed_skew(record)
    atm_base = float(np.interp(0.0, grid_k, base))
    atm_shift = float(np.interp(0.0, grid_k, shifted))
    ssr = (atm_shift - atm_base) / (skew * delta) if delta != 0.0 and skew != 0.0 else 2.0
    return ScenarioResponse(
        k=grid_k.tolist(),
        baseVol=base.tolist(),
        shiftedVol=shifted.tolist(),
        ssr=float(ssr),
        regime="sticky_local_vol_grid",
    )
