"""Figure 6.5: dividend conventions -- the implied-carry sawtooth, and the
forward's spot elasticity that truly separates them."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
from figstyle import PALETTE
from macros import STORE, num

S0 = 100.0
R = 0.04
CASH = 0.65            # quarterly cash dividend (dollars)
FIRST_EX = 30.0 / 365.0
PERIOD = 0.25
HORIZON = 2.5


def _ex_dates(T: float) -> np.ndarray:
    dates = np.arange(FIRST_EX, HORIZON + PERIOD, PERIOD)
    return dates[dates <= T]


def _pv_divs(T: float, S: float = S0, proportional: bool = False) -> float:
    ti = _ex_dates(T)
    if proportional:
        return 0.0
    return float(np.sum(CASH * np.exp(-R * ti)))


def forward_cash(T: float, S: float = S0) -> float:
    return (S - _pv_divs(T)) * np.exp(R * T)


def forward_prop(T: float, S: float = S0) -> float:
    frac = CASH / S0  # each event pays this fraction of the prevailing level
    return S * float(np.prod(1.0 - frac * np.ones(_ex_dates(T).size))) * np.exp(R * T)


def forward_yield(T: float, S: float = S0, qd: float | None = None) -> float:
    qd = QEQ if qd is None else qd
    return S * np.exp((R - qd) * T)


# The one-year equivalent yield of the cash schedule (computed at import).
QEQ = -np.log(1.0 - _pv_divs(1.0) / S0) / 1.0


def fig_fwd_divs() -> str:
    T = np.linspace(0.01, HORIZON, 1200)

    q_impl = np.array([R - np.log(forward_cash(t) / S0) / t for t in T])
    tooth = CASH / S0 / FIRST_EX  # the first ex-date, annualized at 30 days

    # Spot elasticity by direct bump (1 bp of spot), each convention.
    Tg = np.linspace(0.05, HORIZON, 60)
    bump = 1e-4
    def elas(fwd) -> np.ndarray:
        return np.array([
            (np.log(fwd(t, S0 * (1 + bump))) - np.log(fwd(t, S0))) / bump
            for t in Tg
        ])
    e_cash, e_prop, e_yield = elas(forward_cash), elas(forward_prop), elas(forward_yield)
    e_closed = np.array([S0 / (S0 - _pv_divs(t)) for t in Tg])

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax_a.plot(T, 100 * q_impl, color=PALETTE["model"], lw=1.2,
              label="cash schedule (escrow)")
    ax_a.axhline(100 * QEQ, color=PALETTE["muted"], lw=1.0, ls="--",
                 label=f"flat yield {100 * QEQ:.2f}%")
    ax_a.set_xlabel("maturity $T$ (years)")
    ax_a.set_ylabel("implied dividend yield (%)")
    ax_a.set_ylim(0.0, min(8.5, 105 * tooth))
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the implied-carry sawtooth")

    ax_b.plot(Tg, e_cash, color=PALETTE["model"], lw=1.3, label="cash (measured)")
    ax_b.plot(Tg, e_closed, color=PALETTE["ink"], lw=0.9, ls=":",
              label="cash (closed form)")
    ax_b.plot(Tg, e_prop, color=PALETTE["alt"], lw=1.2, label="proportional")
    ax_b.plot(Tg, e_yield, color=PALETTE["third"], lw=1.0, ls="--", label="yield")
    ax_b.set_xlabel("maturity $T$ (years)")
    ax_b.set_ylabel(r"spot elasticity $\partial\log F/\partial\log S$")
    ax_b.legend(loc="upper left", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the discriminator: how $F$ rides a spot move")

    figstyle.save(fig, "fig_fwd_divs")

    STORE.add("divs", "FwdDivCashDollars", num(CASH, 2),
              "quarterly cash dividend of the running schedule (dollars)")
    STORE.add("divs", "FwdDivFirstDays", str(int(round(FIRST_EX * 365))),
              "days to the first ex-date")
    STORE.add("divs", "FwdDivToothPct", num(100 * tooth, 1),
              "annualized implied yield just after the first ex-date enters (%)")
    STORE.add("divs", "FwdDivQeqPct", num(100 * QEQ, 2),
              "one-year equivalent continuous yield of the cash schedule (%)")
    STORE.add("divs", "FwdDivElasTwoYr",
              num(float(S0 / (S0 - _pv_divs(2.0))), 3),
              "cash-schedule spot elasticity at two years")
    STORE.add("divs", "FwdDivPvTwoYr", num(_pv_divs(2.0), 2),
              "present value of the cash schedule to two years (dollars)")
    return f"q_eq {100 * QEQ:.2f}%, tooth {100 * tooth:.1f}%, elas(2y) {S0 / (S0 - _pv_divs(2.0)):.3f}"
