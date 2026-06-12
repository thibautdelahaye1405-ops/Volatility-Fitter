"""Dividend models: golden forwards per mode, yield round trips, validation.

Invariants:
1. Each mode reproduces its hand-computable desk formula (module docstring
   of data/dividends.py): continuous carry, escrowed cash, proportional
   haircut, and the mixed cash-then-proportional switch.
2. Only dividends with 0 < tau <= t enter; the mixed switch boundary
   (tau == switch_years) counts as near-dated cash.
3. equivalent_yield round-trips theoretical_forward for every mode:
   S e^{(r - q_eq) t} == F.
4. Bad inputs raise (unknown mode, negative amount, fraction outside [0,1),
   escrowed PV >= spot); equivalent_yield guards degenerate inputs with 0.0.
"""

from datetime import date, timedelta

import numpy as np
import pytest

from volfit.data.dividends import (
    Dividend,
    DividendModel,
    equivalent_yield,
    theoretical_forward,
)

S, R = 100.0, 0.03
REF = date(2026, 1, 2)


def ex(tau_years: float) -> date:
    """Ex-date a whole number of days from REF (so tau = days / 365 exactly)."""
    return REF + timedelta(days=round(tau_years * 365))


def tau_of(ex_date: date) -> float:
    return (ex_date - REF).days / 365.0


# ---------------------------------------------------------------- forwards


def test_continuous_yield_forward():
    model = DividendModel(mode="continuous", yield_=0.02)
    # F = S e^{(r - q) t}: the canonical carry formula.
    assert theoretical_forward(S, R, 1.0, model, REF) == pytest.approx(
        100.0 * np.exp(0.01), rel=1e-12
    )
    assert theoretical_forward(S, R, 0.5, model, REF) == pytest.approx(
        100.0 * np.exp(0.005), rel=1e-12
    )


def test_escrowed_cash_forward():
    div = Dividend(ex(0.5), 2.0)
    model = DividendModel(mode="discrete_absolute", dividends=(div,))
    tau = tau_of(div.ex_date)
    expected = (S - 2.0 * np.exp(-R * tau)) * np.exp(R * 1.0)
    assert theoretical_forward(S, R, 1.0, model, REF) == pytest.approx(expected, rel=1e-12)


def test_dividends_outside_window_are_ignored():
    late = Dividend(ex(1.5), 2.0)  # tau > t
    past = Dividend(REF, 2.0)  # tau == 0: already gone ex
    model = DividendModel(mode="discrete_absolute", dividends=(late, past))
    # Nothing enters: pure carry forward.
    assert theoretical_forward(S, R, 1.0, model, REF) == pytest.approx(
        S * np.exp(R), rel=1e-12
    )
    # A dividend exactly at the horizon (tau == t) does enter.
    at_t = Dividend(ex(1.0), 2.0)
    model_at = DividendModel(mode="discrete_absolute", dividends=(at_t,))
    tau = tau_of(at_t.ex_date)
    expected = (S - 2.0 * np.exp(-R * tau)) * np.exp(R * 1.0)
    assert theoretical_forward(S, R, 1.0, model_at, REF) == pytest.approx(expected, rel=1e-12)


def test_proportional_forward():
    model = DividendModel(
        mode="discrete_proportional", dividends=(Dividend(ex(0.5), 0.02),)
    )
    expected = S * np.exp(R) * (1.0 - 0.02)
    assert theoretical_forward(S, R, 1.0, model, REF) == pytest.approx(expected, rel=1e-12)


def test_mixed_forward_switches_at_horizon():
    near = Dividend(ex(0.5), 1.5)  # cash, escrowed (tau <= switch_years)
    far = Dividend(ex(1.5), 2.5)  # beyond switch: proportional, fraction 2.5/S
    model = DividendModel(mode="mixed", dividends=(far, near), switch_years=1.0)
    tau1 = tau_of(near.ex_date)
    expected = (S - 1.5 * np.exp(-R * tau1)) * np.exp(R * 2.0) * (1.0 - 2.5 / S)
    assert theoretical_forward(S, R, 2.0, model, REF) == pytest.approx(expected, rel=1e-12)


def test_mixed_switch_boundary_counts_as_cash():
    # tau exactly == switch_years stays escrowed cash, not proportional.
    div = Dividend(ex(1.0), 2.0)
    model = DividendModel(mode="mixed", dividends=(div,), switch_years=tau_of(div.ex_date))
    tau = tau_of(div.ex_date)
    expected = (S - 2.0 * np.exp(-R * tau)) * np.exp(R * 2.0)
    assert theoretical_forward(S, R, 2.0, model, REF) == pytest.approx(expected, rel=1e-12)


# -------------------------------------------------------- equivalent yield


def test_equivalent_yield_round_trips_every_mode():
    models = (
        DividendModel(mode="continuous", yield_=0.02),
        DividendModel(mode="discrete_absolute", dividends=(Dividend(ex(0.5), 2.0),)),
        DividendModel(mode="discrete_proportional", dividends=(Dividend(ex(0.5), 0.02),)),
        DividendModel(
            mode="mixed",
            dividends=(Dividend(ex(0.5), 1.5), Dividend(ex(1.5), 2.5)),
            switch_years=1.0,
        ),
    )
    for model in models:
        t = 2.0
        fwd = theoretical_forward(S, R, t, model, REF)
        q_eq = equivalent_yield(S, fwd, R, t)
        assert S * np.exp((R - q_eq) * t) == pytest.approx(fwd, rel=1e-12), model.mode
    # And the continuous mode recovers its own yield exactly.
    fwd = theoretical_forward(S, R, 1.0, models[0], REF)
    assert equivalent_yield(S, fwd, R, 1.0) == pytest.approx(0.02, abs=1e-12)


def test_equivalent_yield_guards_return_zero():
    assert equivalent_yield(S, 101.0, R, 0.0) == 0.0  # t <= 0
    assert equivalent_yield(S, -1.0, R, 1.0) == 0.0  # broken forward
    assert equivalent_yield(0.0, 101.0, R, 1.0) == 0.0  # broken spot


# ------------------------------------------------------------- validation


def test_validation_errors():
    with pytest.raises(ValueError):
        Dividend(ex(0.5), -1.0)  # negative amount
    with pytest.raises(ValueError):
        DividendModel(mode="lumpy")  # unknown mode
    with pytest.raises(ValueError):  # proportional fraction must be < 1
        theoretical_forward(
            S, R, 1.0,
            DividendModel(mode="discrete_proportional", dividends=(Dividend(ex(0.5), 1.0),)),
            REF,
        )
    with pytest.raises(ValueError):  # escrowed cash PV >= spot
        theoretical_forward(
            S, R, 1.0,
            DividendModel(mode="discrete_absolute", dividends=(Dividend(ex(0.5), 200.0),)),
            REF,
        )
    with pytest.raises(ValueError):  # mixed far-dated fraction D/S >= 1
        theoretical_forward(
            S, R, 2.0,
            DividendModel(mode="mixed", dividends=(Dividend(ex(1.5), 150.0),)),
            REF,
        )
    with pytest.raises(ValueError):  # non-positive spot
        theoretical_forward(0.0, R, 1.0, DividendModel(), REF)
