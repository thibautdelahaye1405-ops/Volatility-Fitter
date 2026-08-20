"""V3.5 item 13 — accepted-step replay trace of the affine LV calibration.

Solver locks (volfit.models.localvol.affine_trace):
  * trace OFF (default) ⇒ byte-identical result, ``trace is None`` (the perf
    rails call the defaults, so this is their guard too);
  * trace ON ⇒ frames strictly ascending in ``n_evals``, costs non-increasing
    (accepted steps only), LAST frame == the converged theta, cap honoured;
  * the GN path (the production default solver) records via the same hook.

API locks (GET /fit/affine/{ticker}/trace):
  * 404 before the first traced fit, and the GET itself is poll-safe (never
    triggers a fit); 200 after, with the final frame equal to the served
    surface and the per-expiry columns mapping 1:1 to the fitted expiries.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    solve_affine_dupire,
)

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _case(noise: float = 0.0):
    """Small self-consistent surface fit (test_affine_early_stop's shape)."""
    t_nodes = np.linspace(0.0, 2.0, 11)
    x_nodes = np.linspace(0.6, 1.6, 13)
    tt, xx = np.meshgrid(t_nodes, x_nodes, indexing="ij")
    theta = np.clip(0.04 + 0.01 * tt + 0.03 * (1 - xx) ** 2 + 0.01 * (1 - xx), 0.006, 0.19)
    surf = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=theta)
    x_grid = 0.01 * np.arange(251)
    exps = np.linspace(0.2, 2.0, 9)
    pts, prev = [0.0], 0.0
    for e in exps:
        s = max(1, int(np.ceil((e - prev) / 0.01)))
        pts.extend(np.linspace(prev, e, s + 1)[1:].tolist())
        prev = e
    t_grid = np.array(pts)
    sol = solve_affine_dupire(surf, x_grid, t_grid, list(exps))
    idx = {float(e): i for i, e in enumerate(sol.expiries)}
    strikes = np.linspace(0.75, 1.25, 11)
    rng = np.random.default_rng(0)
    options = []
    for e in exps:
        for x in strikes:
            p = float(sol.price_at(idx[float(e)], x)) * (1.0 + noise * rng.standard_normal())
            options.append(OptionQuote(t=float(e), x=float(x), price=p, tol=2e-4))
    flat = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((11, 13), 0.04))
    return flat, options, x_grid, t_grid


KW = dict(reg_lambda=50.0, bounds=(0.005, 0.20))


def test_trace_off_is_byte_identical_and_absent():
    """Default (trace_every=None): no trace object, and the fit is bit-identical
    to a traced run — tracing is pure observation."""
    flat, options, x_grid, t_grid = _case()
    off = calibrate_affine(flat, options, x_grid, t_grid, **KW)
    on = calibrate_affine(flat, options, x_grid, t_grid, trace_every=1, **KW)
    assert off.trace is None
    assert on.trace is not None
    assert off.surface.theta.tobytes() == on.surface.theta.tobytes()  # hash lock
    assert off.cost == on.cost and off.n_evals == on.n_evals
    assert np.array_equal(off.option_prices, on.option_prices)


def test_trace_frames_monotone_final_and_shapes():
    flat, options, x_grid, t_grid = _case(noise=2e-3)  # long, real-data-like run
    cal = calibrate_affine(flat, options, x_grid, t_grid, trace_every=1, **KW)
    trace = cal.trace
    assert trace is not None and len(trace.frames) >= 2
    evals = [f.n_evals for f in trace.frames]
    assert evals == sorted(evals) and len(set(evals)) == len(evals)  # strictly ascending
    costs = [f.cost for f in trace.frames]
    assert all(b <= a for a, b in zip(costs, costs[1:]))  # accepted steps only
    # The LAST frame is the converged surface, exactly.
    assert np.array_equal(trace.frames[-1].theta, cal.surface.theta)
    n_exp = len({o.t for o in options})
    assert trace.expiries == sorted(trace.expiries) and len(trace.expiries) == n_exp
    for f in trace.frames:
        assert f.theta.shape == cal.surface.theta.shape
        assert f.expiry_rms.shape == (n_exp,)
    assert len(trace.frames) <= 24  # default cap


def test_trace_cap_honoured_with_final_kept():
    flat, options, x_grid, t_grid = _case(noise=2e-3)
    full = calibrate_affine(flat, options, x_grid, t_grid, trace_every=1, **KW)
    assert len(full.trace.frames) > 4  # the cap below actually binds
    capped = calibrate_affine(flat, options, x_grid, t_grid, trace_every=1, trace_cap=4, **KW)
    assert len(capped.trace.frames) <= 4
    assert np.array_equal(capped.trace.frames[-1].theta, capped.surface.theta)
    # Subsampling keeps the seed frame (frame 0 of the uncapped run).
    assert capped.trace.frames[0].n_evals == full.trace.frames[0].n_evals


def test_trace_records_on_the_gn_path_too():
    """The production default solver is GN (lvSolver='gn'); the new-best-cost
    hook lives in the shared evaluate, so GN runs (and their TRF fallbacks)
    trace through the exact same mechanism."""
    flat, options, x_grid, t_grid = _case()
    cal = calibrate_affine(flat, options, x_grid, t_grid, trace_every=1, gn=True, **KW)
    trace = cal.trace
    assert trace is not None and len(trace.frames) >= 2
    evals = [f.n_evals for f in trace.frames]
    assert evals == sorted(evals) and len(set(evals)) == len(evals)
    assert np.array_equal(trace.frames[-1].theta, cal.surface.theta)


# ------------------------------------------------------------------- API ---
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_trace_endpoint_404_before_and_poll_safe(client):
    """404 until a traced fit completed; the GET itself never triggers a fit
    (repeated polls stay 404 and leave no affine pointer behind)."""
    for _ in range(2):
        assert client.get(f"/fit/affine/{TICKER}/trace").status_code == 404
    assert client.app.state.volfit.get_affine_ptr(TICKER) is None  # no fit ran


def test_trace_endpoint_200_after_fit_and_consistent(client):
    fit = client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()
    resp = client.get(f"/fit/affine/{TICKER}/trace")
    assert resp.status_code == 200
    trace = resp.json()
    assert trace["ticker"] == TICKER
    assert trace["tNodes"] == fit["tNodes"] and trace["xNodes"] == fit["xNodes"]
    # One rms column per fitted expiry, every frame consistent with the grid.
    assert len(trace["expiries"]) == len(fit["smiles"])
    assert len(trace["frames"]) >= 1
    for frame in trace["frames"]:
        assert len(frame["localVol"]) == len(fit["tNodes"])
        assert all(len(row) == len(fit["xNodes"]) for row in frame["localVol"])
        assert len(frame["expiryRms"]) == len(trace["expiries"])
    evals = [f["nEvals"] for f in trace["frames"]]
    assert evals == sorted(evals) and len(set(evals)) == len(evals)
    # The final frame IS the served surface (sqrt of the converged theta).
    assert np.array_equal(
        np.array(trace["frames"][-1]["localVol"]), np.array(fit["localVol"])
    )
    # Poll-safe: a second GET returns the same payload and triggers nothing.
    again = client.get(f"/fit/affine/{TICKER}/trace").json()
    assert again == trace
