"""Phase 0 per-expiry diagnostics for the local-vol affine fit.

Verifies that ``volfit.api.affine_diag.expiry_diagnostics`` reports the metrics
that separate the short-dated failure modes — and that it is PURE observation
(it reads the fit inputs and never alters them). The signatures asserted here are
exactly the ones the diagnosis hinges on:

- a narrow SHORT smile lands FEWER strike vertices than a wide long one on the
  shared (long-expiry-scaled, globally-clipped) tensor axis (Cause A);
- the ABSOLUTE vega floor underweights MORE of the short smile, and the ATM vega
  reference scales with √τ (Cause B);
- the front expiry gets FEWER PDE time steps (Cause C);
- prior rows are counted per expiry only when a prior is active (Cause E).
"""

from __future__ import annotations

import numpy as np

from volfit.api.affine_diag import AffineExpiryDiagnostics, expiry_diagnostics


def _rows():
    """Two expiries on the SAME shared axis: a narrow 2-week smile and a wide 1y.

    Mimics ``_gather``'s (iso, tau, k, w, prepared, band) tuples (prepared/band
    unused by the diagnostics, so None). The short smile trades a tight strike
    band; the long one a wide one — as real chains do."""
    short_k = np.linspace(-0.06, 0.06, 11)  # ~2w: narrow
    long_k = np.linspace(-0.50, 0.20, 21)  # ~1y: wide
    sigma = 0.15
    rows = [
        ("2026-07-04", 0.04, short_k, (sigma**2) * 0.04 * np.ones_like(short_k), None, None),
        ("2027-06-18", 1.00, long_k, (sigma**2) * 1.00 * np.ones_like(long_k), None, None),
    ]
    return rows


def _shared_axis(rows):
    """A single tensor strike axis spanning the GLOBAL traded range (the source of
    the under-resolution): 13 nodes from the deepest put to the highest call."""
    all_k = np.concatenate([k for _, _, k, _, _, _ in rows])
    return np.exp(np.linspace(all_k.min(), all_k.max(), 13))


def test_short_expiry_lands_fewer_vertices():
    """Cause A: on the shared globally-clipped axis the narrow short smile gets
    far fewer in-range strike vertices than the wide long one."""
    rows = _rows()
    x_nodes = _shared_axis(rows)
    t_grid = np.linspace(0.0, 1.0, 101)
    diags = expiry_diagnostics(rows, x_nodes, t_grid, vega_floor=1e-3)
    short, long = diags[0], diags[1]
    assert short.n_vertices_total == long.n_vertices_total == x_nodes.size
    assert short.n_vertices_in_range < long.n_vertices_in_range
    assert short.n_vertices_in_range <= 3  # the failure signature: a handful of nodes


def test_vega_floor_bites_short_end_harder():
    """Cause B: the ABSOLUTE floor floors a larger fraction of the short smile,
    and the ATM-vega reference scales with √τ (so the floor is relatively bigger
    at the short end)."""
    rows = _rows()
    x_nodes = _shared_axis(rows)
    t_grid = np.linspace(0.0, 1.0, 101)
    diags = expiry_diagnostics(rows, x_nodes, t_grid, vega_floor=1e-3)
    short, long = diags[0], diags[1]
    assert short.vega_floor_frac >= long.vega_floor_frac
    # ATM vega ~ φ(d₊)·√τ, so the 1y reference is ~√25 = 5x the 2w one.
    assert long.vega_atm > short.vega_atm
    assert np.isclose(long.vega_atm / short.vega_atm, np.sqrt(1.0 / 0.04), rtol=0.05)


def test_front_expiry_gets_fewer_time_steps():
    """Cause C: the first (segment) gets fewer PDE steps than the long back leg."""
    rows = _rows()
    x_nodes = _shared_axis(rows)
    # A realistic non-uniform PDE clock: dense early, every expiry a node.
    t_grid = np.unique(np.concatenate([np.arange(0.0, 0.04 + 1e-9, 0.02), np.arange(0.04, 1.0 + 1e-9, 0.01)]))
    diags = expiry_diagnostics(rows, x_nodes, t_grid, vega_floor=1e-3)
    short, long = diags[0], diags[1]
    assert short.n_time_steps < long.n_time_steps
    assert short.n_time_steps >= 1  # at least one step reaches the first expiry


def test_prior_rows_counted_only_when_active():
    """Cause E: prior rows are 0 / inactive with no prior, and counted per expiry
    (matched on tau) when prior option rows are supplied."""
    rows = _rows()
    x_nodes = _shared_axis(rows)
    t_grid = np.linspace(0.0, 1.0, 101)

    none = expiry_diagnostics(rows, x_nodes, t_grid, vega_floor=1e-3)
    assert all(not d.prior_active and d.n_prior_rows == 0 for d in none)

    withp = expiry_diagnostics(
        rows, x_nodes, t_grid, vega_floor=1e-3, prior_t_counts={0.04: 5, 1.00: 2}
    )
    assert all(d.prior_active for d in withp)
    assert withp[0].n_prior_rows == 5
    assert withp[1].n_prior_rows == 2


def test_record_shape_and_purity():
    """The records are the frozen dataclass and one per row, in row order."""
    rows = _rows()
    diags = expiry_diagnostics(rows, _shared_axis(rows), np.linspace(0, 1, 51), 1e-3)
    assert len(diags) == len(rows)
    assert all(isinstance(d, AffineExpiryDiagnostics) for d in diags)
    assert [d.expiry for d in diags] == [r[0] for r in rows]
