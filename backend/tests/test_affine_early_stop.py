"""Stage 8 — stall-based early-stop of the cold affine calibration.

The cold fit runs to ``max_nfev`` even though its tail evals barely move the surface.
``stall_window`` terminates once the best cost has not improved by ``stall_rtol`` over
that many objective evals, returning the best-cost iterate. Gates: disabled
(``stall_window=0``) is byte-identical; enabled cuts the eval count while landing
essentially the full-fit surface.
"""

import numpy as np

from volfit.models.localvol import (
    AffineVarianceSurface,
    OptionQuote,
    calibrate_affine,
    solve_affine_dupire,
)


def _case(noise: float = 0.0):
    """An 11x13 surface fit (quotes from a known smooth surface). ``noise`` > 0 adds
    deterministic price noise so the LSQ has an irreducible residual and the optimizer
    takes a long tail of tiny steps (like real data) — the regime early-stop targets;
    noise = 0 is the self-consistent case that converges quickly."""
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
            p = float(sol.price_at(idx[float(e)], x))
            p = p * (1.0 + noise * rng.standard_normal())
            options.append(OptionQuote(t=float(e), x=float(x), price=p, tol=2e-4))
    flat = AffineVarianceSurface(t_nodes=t_nodes, x_nodes=x_nodes, theta=np.full((11, 13), 0.04))
    return flat, options, x_grid, t_grid


def test_early_stop_disabled_is_byte_identical():
    flat, options, x_grid, t_grid = _case()
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20))
    a = calibrate_affine(flat, options, x_grid, t_grid, **kw)
    b = calibrate_affine(flat, options, x_grid, t_grid, stall_window=0, **kw)
    assert np.array_equal(a.surface.theta, b.surface.theta)


def test_early_stop_cuts_evals_and_keeps_surface():
    # noisy quotes + very tight scipy tols => trf keeps taking tiny tail steps and
    # runs to the cap (the real-data regime; the synthetic otherwise satisfies ftol
    # and stops on its own), so the stall window is the binding terminator.
    flat, options, x_grid, t_grid = _case(noise=2e-3)
    kw = dict(reg_lambda=50.0, bounds=(0.005, 0.20), max_nfev=200,
              xtol=1e-14, ftol=1e-14, gtol=1e-14)
    full = calibrate_affine(flat, options, x_grid, t_grid, **kw)
    early = calibrate_affine(flat, options, x_grid, t_grid, stall_window=10, stall_rtol=1e-3, **kw)
    assert early.diagnostics.status == 99  # the stall path actually triggered
    assert early.n_evals < full.n_evals  # fewer expensive objective evaluations
    # essentially the same surface (the tail evals it skipped barely moved it)
    assert np.max(np.abs(early.surface.theta - full.surface.theta)) < 5e-3
    # the returned iterate is the best-cost one, never materially worse than the full fit
    assert early.cost <= full.cost * 1.02


def test_early_stop_reports_stall_status():
    """When the window triggers, the synthesized result flags the early stop."""
    flat, options, x_grid, t_grid = _case(noise=2e-3)
    early = calibrate_affine(
        flat, options, x_grid, t_grid, reg_lambda=50.0, bounds=(0.005, 0.20),
        stall_window=6, stall_rtol=5e-3, xtol=1e-14, ftol=1e-14, gtol=1e-14,
    )
    # status 99 / the stall message identify the early-stop path (vs scipy's codes)
    assert early.diagnostics.status == 99
    assert early.message.startswith("early stop")
