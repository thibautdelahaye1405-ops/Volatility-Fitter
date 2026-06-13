"""Dividend models and theoretical forwards (ROADMAP Phase 3 [REQ 2026-06-12]).

Design intent: parity-implied forwards (data/forwards.py) stay the primary
source because they are robust to dividend-forecast error, but the
"Dividends model selection" requirement needs an explicit model too — it
feeds the *theoretical* forward mode (spot + carry), the side-by-side
forward diagnostics, and later the ex-date handling.  Four desk-standard
modes are supported; with tau_i = (ex_date_i - reference_date)/365 and only
dividends inside 0 < tau_i <= t entering:

- "continuous"             F = S e^{(r - q) t}
- "discrete_absolute"      escrowed cash:  F = (S - sum_i D_i e^{-r tau_i}) e^{r t}
- "discrete_proportional"  F = S e^{r t} prod_i (1 - d_i),  d_i a fraction of spot
- "mixed"                  desk practice — forecast *cash* amounts near-dated
                           (tau_i <= switch_years, escrowed) and switch to
                           *proportional* far-dated (fraction D_i / S):
                           F = (S - PV(near cash)) e^{r t} prod_far (1 - D_i / S)

`equivalent_yield` maps any forward back to the continuous yield q solving
F = S e^{(r - q) t}; this is what the smile/fitter layer consumes, so every
mode collapses to the same (r, q) interface downstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

DividendMode = Literal[
    "continuous", "discrete_absolute", "discrete_proportional", "mixed"
]

#: Modes accepted by DividendModel (kept in sync with DividendMode).
_MODES = ("continuous", "discrete_absolute", "discrete_proportional", "mixed")

#: Day-count for ex-date year fractions (ACT/365, matching the quote layer).
DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class Dividend:
    """One forecast dividend: cash amount, or fraction of spot in
    proportional interpretation (which one applies depends on the model
    mode at use time)."""

    ex_date: date
    amount: float

    def __post_init__(self) -> None:
        if self.amount < 0.0:
            raise ValueError(f"dividend amount must be >= 0, got {self.amount}")


@dataclass(frozen=True)
class DividendModel:
    """Dividend assumptions for one underlying (see module docstring)."""

    mode: DividendMode = "continuous"
    yield_: float = 0.0  # continuous dividend yield q (mode "continuous")
    dividends: tuple[Dividend, ...] = ()  # discrete schedule, any order
    switch_years: float = 1.0  # mixed: cash before this horizon, proportional after

    def __post_init__(self) -> None:
        if self.mode not in _MODES:
            raise ValueError(f"unknown dividend mode {self.mode!r}; expected one of {_MODES}")


def _schedule(model: DividendModel, reference_date: date, t: float) -> list[tuple[float, float]]:
    """(tau_i, amount_i) for dividends inside (0, t], sorted by tau."""
    pairs = [
        ((div.ex_date - reference_date).days / DAYS_PER_YEAR, div.amount)
        for div in model.dividends
    ]
    return sorted((tau, amt) for tau, amt in pairs if 0.0 < tau <= t)


def _check_fraction(fraction: float, context: str) -> None:
    """Proportional dividends must be a fraction of spot in [0, 1)."""
    if not 0.0 <= fraction < 1.0:
        raise ValueError(f"{context}: proportional fraction must lie in [0, 1), got {fraction}")


def theoretical_forward(
    spot: float,
    rate: float,
    t: float,
    model: DividendModel,
    reference_date: date,
) -> float:
    """Theoretical forward F(t) under the dividend model (formulas above).

    ``rate`` is the continuously compounded risk-free rate to ``t``.  Raises
    ValueError when the inputs cannot produce a positive forward (escrowed
    cash PV at or above spot, proportional fraction outside [0, 1)); returns
    ``spot`` for t <= 0 (degenerate horizon, nothing accrues).
    """
    if spot <= 0.0:
        raise ValueError(f"spot must be positive, got {spot}")
    if t <= 0.0:
        return spot

    if model.mode == "continuous":
        return spot * float(np.exp((rate - model.yield_) * t))

    schedule = _schedule(model, reference_date, t)

    if model.mode == "discrete_absolute":
        pv_cash = sum(amt * float(np.exp(-rate * tau)) for tau, amt in schedule)
        if pv_cash >= spot:
            raise ValueError(f"escrowed dividend PV {pv_cash:.4f} >= spot {spot}")
        return (spot - pv_cash) * float(np.exp(rate * t))

    if model.mode == "discrete_proportional":
        factor = 1.0
        for _, amt in schedule:
            _check_fraction(amt, "discrete_proportional")
            factor *= 1.0 - amt
        return spot * float(np.exp(rate * t)) * factor

    # mixed: escrowed cash up to switch_years, proportional (D_i / S) beyond.
    pv_cash, factor = 0.0, 1.0
    for tau, amt in schedule:
        if tau <= model.switch_years:
            pv_cash += amt * float(np.exp(-rate * tau))
        else:
            _check_fraction(amt / spot, "mixed far-dated dividend")
            factor *= 1.0 - amt / spot
    if pv_cash >= spot:
        raise ValueError(f"escrowed dividend PV {pv_cash:.4f} >= spot {spot}")
    return (spot - pv_cash) * float(np.exp(rate * t)) * factor


#: Cap on the dividend rescaling factor (a sanity net: if the model forecast
#: is tiny relative to the forward-implied dividend, don't inflate it absurdly).
_MAX_DIV_SCALE = 5.0


def forward_consistent_cash_schedule(
    spot: float,
    forward: float,
    rate: float,
    t: float,
    model: DividendModel,
    reference_date: date,
    max_scale: float = _MAX_DIV_SCALE,
) -> tuple[np.ndarray, np.ndarray] | None:
    """Discrete CASH dividends (ex year-fractions, amounts) for de-Americanizing.

    Used to de-Americanize an American chain with the real dividend TIMING
    (which drives the call/put early-exercise asymmetry, hence the ATM smile
    kink near an ex-date) while staying consistent with the resolved forward.
    The ex-dates come from ``model``; the amounts are scaled by

        alpha = (S - F e^{-r t}) / sum_i D_i e^{-r tau_i}

    so the escrowed-tree forward (S - PV) e^{r t} reproduces ``forward`` exactly
    — the amounts bend to the market while the timing stays the user's forecast.

    ``rate`` is the (physical) continuously-compounded rate the de-Am tree uses;
    it must exceed the dividend-implied carry for ``alpha`` to be positive
    (i.e. F < S e^{r t}). Returns None — so the caller keeps the continuous-yield
    de-Am — when the mode carries no cash leg, there is no cash dividend inside
    (0, t], or ``alpha`` is non-physical (<= 0 or > ``max_scale``).
    """
    if model.mode not in ("discrete_absolute", "mixed") or t <= 0.0 or spot <= 0.0:
        return None
    cash: list[tuple[float, float]] = []
    for div in model.dividends:
        tau = (div.ex_date - reference_date).days / DAYS_PER_YEAR
        if 0.0 < tau <= t and not (model.mode == "mixed" and tau > model.switch_years):
            cash.append((tau, div.amount))  # mixed: only the near cash leg
    if not cash:
        return None
    taus = np.array([c[0] for c in cash])
    amounts = np.array([c[1] for c in cash])
    pv_unit = float(np.sum(amounts * np.exp(-rate * taus)))
    if pv_unit <= 0.0:
        return None
    alpha = (spot - forward * float(np.exp(-rate * t))) / pv_unit
    if not 0.0 < alpha <= max_scale:
        return None  # non-physical (rate too low for positive dividends), bail
    return taus, alpha * amounts


def equivalent_yield(spot: float, forward: float, rate: float, t: float) -> float:
    """Continuous yield q with F = S e^{(r - q) t}: q = r - ln(F/S) / t.

    Guard, don't raise: returns 0.0 for t <= 0 or non-positive spot/forward
    (callers feed live data; a broken forward must not kill the pipeline).
    """
    if t <= 0.0 or spot <= 0.0 or forward <= 0.0:
        return 0.0
    return float(rate - np.log(forward / spot) / t)
