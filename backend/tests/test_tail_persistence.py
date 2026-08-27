"""Tail-persistence flexibility arc: WingL/WingR slope operators, the
priorVarSwapMode="atm_spread" carrier, and varSwapHardPin.

Locks:
* Wing operators — leg placement at the two outermost anchor deltas, the
  ±1/(k_outer − k_inner) slope basket, the prior target = the prior's own
  slope, silent drop on degenerate geometry, the priorWingSlopeScale budget
  share, and byte-identity when no Wing name is in the set.
* atm_spread — the spread residual is exactly zero when the model matches the
  prior's SPREAD but not its level; absolute vs atm_spread produce different
  LQD fits (the analytic-Jacobian FD lock lives in test_lqd_jacobian.py).
* varSwapHardPin — the stiff-row weight (VARSWAP_PIN_MULT) forces the fitted
  var-swap onto the quote to solver tolerance while the soft default leaves a
  gap; API-level: the PUT flips the fit and the VarSwapInfo.pinned echo, and
  the LV (affine) surface honours the same pin.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.schemas import OptionsSettings
from volfit.api.service import _prior_varswap
from volfit.calib import operators as ops
from volfit.calib.varswap import (
    VARSWAP_PIN_MULT,
    VarSwapTarget,
    varswap_residual,
    varswap_residual_w,
    varswap_total_variance,
)
from volfit.models.lqd.calibrate import calibrate_slice

REF_DATE = date(2026, 6, 10)
TAU = 0.5
SIG0 = 0.20
DELTAS = (0.02, 0.05, 0.10, 0.25, 0.40)  # the priorAnchorDeltas default


def skew_w(k):
    """Linear-in-k vol smile: sigma = SIG0 - 0.5k, so the slope between ANY two
    strikes is exactly -0.5 — the wing operators' prior value is known."""
    k = np.asarray(k, dtype=float)
    sig = SIG0 - 0.5 * k
    return sig * sig * TAU


def flat_w(k):
    k = np.asarray(k, dtype=float)
    return np.full_like(k, SIG0 * SIG0 * TAU)


# ------------------------------------------------- Task 1: wing operators
def test_wing_legs_coefficients_and_prior_slope():
    """WingL/WingR legs sit at the 2-delta / 5-delta strikes of their side,
    coefficients are +-1/(k_outer - k_inner), and the prior target is the
    prior's own slope through the same basket (-0.5 on the linear smile)."""
    k_quotes = np.array([-0.02, 0.0, 0.02])  # ATM cluster: wings under-observed
    target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["WingL", "WingR"], bandwidth=0.03, anchor_deltas=DELTAS,
    )
    assert target is not None
    assert target.names == ["WingL", "WingR"]
    # 1e-4 tolerance: leg keys are rounded to 6 dp inside _resolve_legs, so the
    # slope through the rounded legs carries ~1e-5 of placement noise.
    np.testing.assert_allclose(target.prior_value, [-0.5, -0.5], atol=1e-4)
    # Legs match the delta->strike machinery of the anchor/operators.
    kr_out = ops.delta_strike(skew_w, TAU, 0.02)
    kr_in = ops.delta_strike(skew_w, TAU, 0.05)
    kl_out = ops.delta_strike(skew_w, TAU, 0.98)
    kl_in = ops.delta_strike(skew_w, TAU, 0.95)
    for leg in (kr_out, kr_in, kl_out, kl_in):
        assert np.min(np.abs(target.legs_k - leg)) < 1e-6
    # Each row: two non-zero legs, coefficients summing to zero, |c| = 1/dk.
    for r, (k_out, k_in) in enumerate([(kl_out, kl_in), (kr_out, kr_in)]):
        row = target.coeff[r]
        nz = row[row != 0.0]
        assert nz.size == 2 and abs(float(nz.sum())) < 1e-12
        assert np.max(np.abs(nz)) == pytest.approx(1.0 / abs(k_out - k_in), rel=1e-4)


def test_wing_evaluate_and_residual_direction():
    """evaluate_operators exposes the wing slopes; residuals vanish against the
    prior itself and pull a flat model (slope 0) toward the prior's slope."""
    vals = ops.evaluate_operators(
        skew_w, TAU, ["WingL", "WingR"], anchor_deltas=DELTAS
    )
    assert vals["WingL"] == pytest.approx(-0.5, abs=1e-4)  # 6-dp leg rounding
    assert vals["WingR"] == pytest.approx(-0.5, abs=1e-4)
    target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, np.array([-0.02, 0.0, 0.02]), None, total_budget=10.0,
        op_set=["WingL", "WingR"], bandwidth=0.03, anchor_deltas=DELTAS,
    )
    assert np.allclose(ops.operator_residuals(skew_w, target), 0.0, atol=1e-9)
    assert np.all(np.abs(ops.operator_residuals(flat_w, target)) > 1e-4)


def test_wing_dropped_on_degenerate_deltas():
    """Fewer than 2 usable per-side deltas -> the wing operators drop silently
    (the body operators are untouched)."""
    k_quotes = np.array([-0.02, 0.0, 0.02])
    for bad in ((), (0.05,), (0.05, 0.6)):  # empty / single / one out-of-range
        target, _ = ops.build_operator_prior(
            skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
            op_set=["RR25", "WingL", "WingR"], bandwidth=0.03, anchor_deltas=bad,
        )
        assert target is not None and target.names == ["RR25"]
    # Only wings requested + degenerate deltas -> nothing to persist at all.
    none_target, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        op_set=["WingL", "WingR"], bandwidth=0.03, anchor_deltas=(0.05,),
    )
    assert none_target is None


def test_wing_budget_share_scales_and_zero_drops():
    """priorWingSlopeScale scales the wing rows' share of the budget RELATIVE
    to the body operators (total conserved); scale 0 drops the wing rows."""
    k_quotes = np.array([-0.02, 0.0, 0.02])

    def shares(scale):
        target, _ = ops.build_operator_prior(
            skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
            op_set=["RR25", "WingL", "WingR"], bandwidth=0.03,
            anchor_deltas=DELTAS, wing_scale=scale,
        )
        assert target is not None
        lam = dict(zip(target.names, target.active_lambda))
        assert float(target.active_lambda.sum()) == pytest.approx(10.0)  # conserved
        return lam

    l1, l2 = shares(1.0), shares(2.0)
    ratio1 = l1["WingR"] / l1["RR25"]
    ratio2 = l2["WingR"] / l2["RR25"]
    assert ratio2 == pytest.approx(2.0 * ratio1, rel=1e-9)
    l0 = shares(0.0)
    assert set(l0) == {"RR25"} and l0["RR25"] == pytest.approx(10.0)


def test_no_wing_in_set_is_byte_identical():
    """Passing the new anchor_deltas / wing_scale arguments with a wing-free
    operator set reproduces the historical target EXACTLY (byte-identity)."""
    k_quotes = np.array([-0.02, 0.0, 0.02])
    kw = dict(op_set=["ATM", "RR25", "BF25"], bandwidth=0.03)
    a, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0, **kw)
    b, _ = ops.build_operator_prior(
        skew_w, TAU, TAU, k_quotes, None, total_budget=10.0,
        anchor_deltas=DELTAS, wing_scale=3.0, **kw)
    assert a.names == b.names
    np.testing.assert_array_equal(a.legs_k, b.legs_k)
    np.testing.assert_array_equal(a.coeff, b.coeff)
    np.testing.assert_array_equal(a.prior_value, b.prior_value)
    np.testing.assert_array_equal(a.active_lambda, b.active_lambda)


# --------------------------------------------- Task 2: atm_spread carrier
def test_spread_residual_zero_on_matching_spread_not_level():
    """The atm_spread residual is (to float precision) zero when the model
    matches the prior's SPREAD while its LEVEL is off by c; the absolute
    carrier still sees the level gap."""
    w_vs = varswap_total_variance(skew_w)
    s_vs = math.sqrt(w_vs / TAU)
    s_atm = math.sqrt(float(skew_w(np.array([0.0]))[0]) / TAU)
    c = 0.03  # common level offset -> same spread, different level
    spread = VarSwapTarget(
        total_var=(s_vs + c) ** 2 * TAU, weight=4.0, t=TAU,
        mode="atm_spread", atm_total_var=(s_atm + c) ** 2 * TAU,
    )
    assert abs(varswap_residual(skew_w, spread)) < 1e-9
    absolute = VarSwapTarget(total_var=(s_vs + c) ** 2 * TAU, weight=4.0, t=TAU)
    assert abs(varswap_residual(skew_w, absolute)) > 1e-2


def test_absolute_mode_ignores_atm_argument():
    """Default-mode targets are byte-identical no matter what ATM reference a
    caller passes (the LV silent-fallback contract)."""
    tgt = VarSwapTarget(total_var=0.02, weight=2.0, t=TAU)
    assert varswap_residual_w(0.025, tgt) == varswap_residual_w(0.025, tgt, 0.017)


def test_prior_varswap_helper_carries_mode_and_atm_reference():
    """service._prior_varswap: absolute keeps the historical construction;
    atm_spread rides the prior's ATM total variance re-expressed at the node
    tau (w(0) * tau/prior_tau — the vol-space-cancelling rescale)."""
    prior_tau, tau = TAU, 0.7
    absolute = _prior_varswap(OptionsSettings(), skew_w, prior_tau, tau, 0.02, 3.0)
    assert absolute.mode == "absolute" and absolute.atm_total_var == 0.0
    assert (absolute.total_var, absolute.weight, absolute.t) == (0.02, 3.0, tau)
    spread = _prior_varswap(
        OptionsSettings(priorVarSwapMode="atm_spread"), skew_w, prior_tau, tau, 0.02, 3.0
    )
    assert spread.mode == "atm_spread"
    expected = float(skew_w(np.array([0.0]))[0]) * (tau / prior_tau)
    assert spread.atm_total_var == pytest.approx(expected)


def test_lqd_absolute_vs_spread_fits_differ():
    """Same prior var-swap LEVEL under the two carriers pulls the LQD fit to
    different places: absolute raises the level against the data; atm_spread
    only widens the tail-over-body spread (the ATM stays with the quotes)."""
    k = np.linspace(-0.3, 0.3, 11)
    t = 0.5
    sig = 0.20 - 0.15 * k + 0.30 * k * k
    w = sig * sig * t
    base = calibrate_slice(k, w, t=t)
    w_vs = float(base.slice.var_swap_strike())
    w0 = float(base.slice.implied_w(np.array([0.0]))[0])
    s_vs, s_atm = math.sqrt(w_vs / t), math.sqrt(w0 / t)
    total_var = (s_vs + 0.03) ** 2 * t  # 3 vol pts above the data-only fair vs
    weight = 5.0 * k.size
    t_abs = VarSwapTarget(total_var=total_var, weight=weight, t=t)
    t_spr = VarSwapTarget(
        total_var=total_var, weight=weight, t=t, mode="atm_spread", atm_total_var=w0
    )
    fit_abs = calibrate_slice(k, w, t=t, prior_var_swap=t_abs)
    fit_spr = calibrate_slice(k, w, t=t, prior_var_swap=t_spr)
    # Both rows bind, and the two carriers land on different parameters.
    assert np.max(np.abs(fit_abs.params.to_vector() - base.params.to_vector())) > 1e-4
    assert np.max(np.abs(fit_spr.params.to_vector() - base.params.to_vector())) > 1e-4
    assert np.max(np.abs(fit_abs.params.to_vector() - fit_spr.params.to_vector())) > 1e-4
    # Directional: the spread carrier widened (sigma_vs - sigma_atm).
    s_vs_spr = math.sqrt(float(fit_spr.slice.var_swap_strike()) / t)
    s_atm_spr = math.sqrt(float(fit_spr.slice.implied_w(np.array([0.0]))[0]) / t)
    assert (s_vs_spr - s_atm_spr) > (s_vs - s_atm) + 0.005


# ------------------------------------------------- Task 3: varSwapHardPin
def test_hard_pin_weight_matches_quote_soft_leaves_gap():
    """The stiff-row weight (VARSWAP_PIN_MULT x summed quote weights) forces
    the fitted var-swap onto the quote to ~solver tolerance; the soft default
    weight leaves a visible gap on the same 4-vol-pt basis."""
    k = np.linspace(-0.2, 0.2, 9)
    t = 0.5
    w = np.full_like(k, SIG0 * SIG0 * t)
    quote = 0.24
    n = float(k.size)

    def vs_gap(weight):
        tgt = VarSwapTarget(total_var=quote * quote * t, weight=weight, t=t)
        res = calibrate_slice(k, w, t=t, var_swap=tgt)
        return abs(math.sqrt(float(res.slice.var_swap_strike()) / t) - quote)

    soft = vs_gap(0.10 * n)  # the varSwapWeightPct=10% default resolution
    hard = vs_gap(VARSWAP_PIN_MULT * n)  # the pinned resolution
    assert soft > 5e-4  # the soft default visibly trades the quote off
    assert hard < 2e-5  # the pin holds it to ~solver tolerance
    assert hard < soft / 25.0


# ----------------------------------------------------- API-level wiring
@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _first_node(client):
    uni = client.get("/universe").json()
    ticker = uni["tickers"][0]
    expiry = uni["expiries"][ticker][0]["expiry"]
    return ticker, expiry


def _put_options(client, **updates):
    options = client.get("/settings/options").json()
    options.update(updates)
    assert client.put("/settings/options", json=options).status_code == 200
    return options


def test_hard_pin_api_flips_fit_and_echoes_pinned(client):
    """PUT varSwapHardPin=True -> the refitted node's var-swap matches the
    quote to ~1e-4 vol (vs a clear soft gap) and VarSwapInfo.pinned echoes."""
    ticker, expiry = _first_node(client)
    model_vol = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]["modelVol"]
    quote = model_vol + 0.04
    client.post(f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": quote})

    soft = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]
    assert soft["pinned"] is False  # echoed (not None) while var-swap is enabled
    soft_gap = abs(soft["modelVol"] - quote)
    assert soft_gap > 1e-3

    _put_options(client, varSwapHardPin=True)
    pinned = client.get(f"/smiles/{ticker}/{expiry}").json()["varSwap"]
    assert pinned["pinned"] is True
    pinned_gap = abs(pinned["modelVol"] - quote)
    assert pinned_gap < 1e-4
    assert pinned_gap < soft_gap / 10.0


def test_hard_pin_reaches_the_lv_surface():
    """The LV (affine) path honours the pin at the row level AND in the solver.

    Row level: the resolved market VarSwapQuote tol shrinks by exactly
    sqrt(PIN_MULT / (pct/100)) — the same weight escalation as the parametric
    row — and the affine payload echoes ``pinned``. Solver level, with the
    DEFAULT options (``lvEarlyStop`` on, warm-started from the cached base
    fit): the soft 10 % row pulls the LV basis (quote − LV model, vol bp) by
    more than 50 bp off its 500 bp start, and the hard pin closes it below
    2 bp. Before the 2026-08-27 affine_stall fix the early-stopped fit
    returned the model UNCHANGED (500 bp) for soft and pinned alike — the
    stall criterion watched the option rows only, so the var-swap row was
    inert (lead's probe: 400.7 bp / 0.026 bp with early stop off)."""
    app = create_app(reference_date=REF_DATE)
    with TestClient(app) as client:
        ticker = client.get("/universe").json()["tickers"][0]
        base = client.post(f"/fit/affine/{ticker}", json={}).json()
        sm0 = base["smiles"][1]
        expiry = sm0["expiry"]
        quote = sm0["varSwap"]["modelVol"] + 0.05  # a 500 bp basis at the base surface
        client.post(
            f"/smiles/{ticker}/{expiry}/varswap", json={"action": "set", "level": quote}
        )

        from volfit.api import affine_fit
        from volfit.api.affine_varswap import market_varswap_quotes

        state = app.state.volfit
        rows = affine_fit._gather(state, ticker, "mid")
        scheme = state.fit_settings().weightScheme
        soft_q = market_varswap_quotes(state, ticker, rows, scheme)
        assert len(soft_q) == 1
        assert soft_q[0].atm_spread is None  # market rows: always the absolute carrier

        def lv_varswap():
            # The affine read serves the frozen fit — calibrate first so the
            # surface sees the (new / re-weighted) var-swap row.
            assert client.post(f"/calibrate/{ticker}").status_code == 200
            return next(
                s for s in client.post(f"/fit/affine/{ticker}", json={}).json()["smiles"]
                if s["expiry"] == expiry
            )["varSwap"]

        soft = lv_varswap()
        assert soft["pinned"] is False
        soft_basis = abs(soft["basisBp"])
        assert soft_basis < 500.0 - 50.0  # the soft row moved the LV surface by > 50 bp

        _put_options(client, varSwapHardPin=True)
        hard_q = market_varswap_quotes(state, ticker, rows, scheme)
        assert len(hard_q) == 1
        assert hard_q[0].total_var == soft_q[0].total_var  # same quote, same carrier
        # tol ~ 1/sqrt(u): u goes pct/100 -> PIN_MULT, so the shrink is exact.
        expected = math.sqrt(VARSWAP_PIN_MULT / 0.10)  # varSwapWeightPct default 10%
        assert soft_q[0].tol / hard_q[0].tol == pytest.approx(expected, rel=1e-9)

        pinned = lv_varswap()
        assert pinned["pinned"] is True
        assert abs(pinned["basisBp"]) < 2.0  # the pin closes the LV basis to ~solver tol
        assert abs(pinned["basisBp"]) < soft_basis / 25.0


def test_wing_ops_and_spread_carrier_api(client):
    """PUT the new options end-to-end: the validator keeps WingL/WingR, the
    options version bump refits, and the prior diagnostics list the wing
    operators (their 1/dk coefficients keep them under-observed on any
    realistically-quoted chain)."""
    ticker = client.get("/universe").json()["tickers"][0]
    expiry = client.get(f"/forwards/{ticker}").json()["entries"][1]["expiry"]
    client.get(f"/smiles/{ticker}/{expiry}")  # ensure a calibrated node
    assert client.post("/priors/save-all").status_code == 200
    assert client.post("/priors/fetch").status_code == 200

    echoed = _put_options(
        client,
        priorPersistenceMode="quote_operator",
        priorOperatorSet=["ATM", "RR25", "BF25", "WingL", "WingR", "VarSwap"],
        priorOperatorBandwidth=0.02,
        priorVarSwapMode="atm_spread",
        priorWingSlopeScale=2.0,
    )
    got = client.get("/settings/options").json()
    assert got["priorOperatorSet"] == echoed["priorOperatorSet"]
    assert "WingL" in got["priorOperatorSet"] and "WingR" in got["priorOperatorSet"]
    assert got["priorVarSwapMode"] == "atm_spread"

    diag = client.get(f"/smiles/{ticker}/{expiry}/prior-diagnostics").json()
    names = [op["operator"] for op in diag["operators"]]
    assert "WingL" in names and "WingR" in names
    for op in diag["operators"]:
        if op["operator"] in ("WingL", "WingR"):
            assert op["activeLambda"] > 0.0
    # The refit under the new options still serves a healthy smile payload.
    data = client.get(f"/smiles/{ticker}/{expiry}").json()
    assert len(data["model"]) > 0
