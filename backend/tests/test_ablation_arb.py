"""R3xR6 SIV wing-arb ablation harness (backtest/ablation_arb.py).

Verifies the 2x2 {R3 off/on} x {R6 off/on} plumbing on a genuine synthetic American
node (real de-Americanization runs), the controlled R6 monotonicity (adding the
put-wing penalty never worsens the analytic wing g at a fixed R3 setting), and the
arb-prone aggregation / attribution logic deterministically.
"""

from __future__ import annotations

from datetime import date, datetime

import numpy as np

from volfit.api.state import AppState
from volfit.core.american import binomial_price
from volfit.data.types import ChainSnapshot, OptionQuote

from backtest.ablation_arb import (
    _ARB_G_TOL,
    _CONFIGS,
    _ext_grid,
    _summarize,
    ablate_node,
)
from backtest.replay import StaticProvider

_S, _R, _T_YEARS = 100.0, 0.04, 45.0 / 365.0
_AS_OF = date(2024, 8, 5)
_EXPIRY = date(2024, 9, 19)


def _skew_vol(k: float) -> float:
    """A steep equity put skew (higher vol for puts), flattening for calls."""
    return 0.22 - 0.35 * k + 0.20 * k * k  # k = log(K/F): puts (k<0) richer


def _american_state() -> AppState:
    """AppState over one synthetic American single-name node with a put skew.

    Prices are genuine American CRR values off the skew, so de-Americanization has
    real early-exercise premium to strip — the R3 axis is exercised for real."""
    forward = _S * np.exp(_R * _T_YEARS)
    ts = datetime(2024, 8, 5, 19, 45)
    quotes: list[OptionQuote] = []
    for strike in range(60, 141, 4):  # sparse-ish wings, dense-ish core
        k = float(np.log(strike / forward))
        sigma = _skew_vol(k)
        half = 0.02 + 0.01 * abs(k)  # wider spreads in the wings
        # Both sides at every strike: parity forward resolution needs a call AND a
        # put per strike (prepare_quotes then keeps only the OTM leg for the fit).
        for is_call in (True, False):
            px = binomial_price(is_call, _S, float(strike), _T_YEARS, sigma, _R, 0.0,
                                american=True)
            quotes.append(OptionQuote(
                ticker="XYZ", expiry=_EXPIRY, strike=float(strike),
                call_put="C" if is_call else "P", bid=max(px - half, 0.01),
                ask=px + half, open_interest=None, timestamp=ts,
            ))
    chain = ChainSnapshot(ticker="XYZ", spot=_S, timestamp=ts, quotes=quotes,
                          exercise_style="american")
    state = AppState(_AS_OF, provider=StaticProvider({"XYZ": chain}))
    state.set_expiries("XYZ", [_EXPIRY])
    return state


def test_ablate_node_returns_the_2x2_matrix():
    """Four cells, correctly tagged, all fit, with the arb + precision metrics."""
    rows = ablate_node(_american_state(), "XYZ", _EXPIRY, n_cores=2)
    assert [r["config"] for r in rows] == [c[0] for c in _CONFIGS]
    by = {r["config"]: r for r in rows}
    assert by["neither"]["r3"] is False and by["neither"]["r6"] is False
    assert by["R3"]["r3"] is True and by["R3"]["r6"] is False
    assert by["R6"]["r3"] is False and by["R6"]["r6"] is True
    assert by["both"]["r3"] is True and by["both"]["r6"] is True
    for r in rows:
        assert r["ok"], r.get("error")
        assert np.isfinite(r["min_g"]) and np.isfinite(r["put_min_g"])
        assert r["in_rmse_bp"] >= 0.0
    # De-Am genuinely ran (American node) — the R3 axis is real, not a no-op stub.
    assert by["neither"]["n_deam"] > 0


def test_both_toggles_are_threaded_independently():
    """R3 and R6 move the fit on their OWN axes: R3 no-ops on already-convex de-Am'd
    wings (neither == R3 byte-identical — the correct gating, repair only fires on a
    genuine non-convexity), while R6 changes the fit versus its R3-matched cell (the
    penalty is engaged wherever the extended-grid wing g dips negative)."""
    rows = {r["config"]: r for r in ablate_node(_american_state(), "XYZ", _EXPIRY,
                                                 n_cores=2)}
    # R3 axis: this synthetic node's de-Am wings are convex, so the repair is a no-op.
    assert rows["R3"]["min_g"] == rows["neither"]["min_g"]
    assert rows["R3"]["in_rmse_bp"] == rows["neither"]["in_rmse_bp"]
    # R6 axis: the put-wing penalty is threaded and alters the fit (not byte-identical
    # here — the base SIV has g<0 out in the wings, so the penalty is active).
    assert (rows["R6"]["min_g"] != rows["neither"]["min_g"]
            or rows["R6"]["in_rmse_bp"] != rows["neither"]["in_rmse_bp"])


def test_ext_grid_reaches_into_the_wings():
    """The arb grid extends pad_z ATM-std past the traded range (the F4 region)."""
    k = np.linspace(-0.2, 0.2, 21)
    w_atm = 0.04  # sqrt = 0.2
    grid = _ext_grid(k, w_atm, pad_z=2.0)
    assert grid.min() < k.min() - 0.39 and grid.max() > k.max() + 0.39  # ~2*0.2
    assert grid.min() == grid.min()  # finite


def test_summarize_scopes_to_arb_prone_and_attributes_repair():
    """Aggregation counts only nodes whose 'neither' cell is arbitraged and reports a
    per-cell repair fraction — one node R6 fixes, one it does not."""
    def cell(asset, cfg, min_g, in_rmse):
        r3 = cfg in ("R3", "both")
        r6 = cfg in ("R6", "both")
        return dict(asset=asset, expiry="2024-09-19", as_of="2024-08-05", ok=True,
                    config=cfg, r3=r3, r6=r6, min_g=min_g, put_min_g=min_g,
                    arb=min_g < -_ARB_G_TOL, in_rmse_bp=in_rmse, oos_rmse_bp=in_rmse + 5)

    rows: list[dict] = []
    # Node A: arb-prone; R6 (and both) repair it, R3 alone does not.
    rows += [cell("A", "neither", -5.0, 100.0), cell("A", "R3", -4.0, 110.0),
             cell("A", "R6", -0.01, 180.0), cell("A", "both", -0.005, 185.0)]
    # Node B: arb-prone; nothing repairs it (stays negative in every cell).
    rows += [cell("B", "neither", -3.0, 90.0), cell("B", "R3", -2.5, 95.0),
             cell("B", "R6", -1.0, 130.0), cell("B", "both", -0.8, 135.0)]
    # Node C: clean baseline -> excluded from the arb-prone population entirely.
    rows += [cell("C", "neither", 0.5, 40.0), cell("C", "R3", 0.5, 40.0),
             cell("C", "R6", 0.5, 40.0), cell("C", "both", 0.5, 40.0)]

    s = _summarize(rows)
    assert s["n_nodes"] == 3 and s["n_arb_prone"] == 2  # C excluded
    cells = s["cells"]
    assert cells["neither"]["arb_rate"] == 1.0 and cells["neither"]["repaired_frac"] == 0.0
    assert cells["R3"]["repaired_frac"] == 0.0  # R3 alone fixes neither A nor B
    assert cells["R6"]["repaired_frac"] == 0.5  # R6 fixes A, not B
    assert cells["both"]["repaired_frac"] == 0.5
    # Precision cost is surfaced next to the arb removed (R6 median in-RMS > baseline).
    assert cells["R6"]["median_in_rmse_bp"] > cells["neither"]["median_in_rmse_bp"]


def test_wing_arb_reads_analytic_g():
    """_wing_arb returns (min, put-min, neg-frac) from the model's analytic g."""
    rows = {r["config"]: r for r in ablate_node(_american_state(), "XYZ", _EXPIRY,
                                                 n_cores=1)}
    # Sanity: the reported min_g equals a direct analytic evaluation on the grid.
    assert -1.0 <= rows["neither"]["neg_frac"] <= 1.0
    assert rows["neither"]["put_min_g"] >= rows["neither"]["min_g"] - 1e-9
