"""Figure: the term structure of the integral (frozen gallery, stored fits)."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import common
import figstyle
from figstyle import PALETTE
from macros import STORE, num


def _series(ticker: str) -> dict:
    taus, w_vs, w_atm = [], [], []
    for n in common.gallery(ticker):
        sl = common.stored_slice(n.ticker, n.expiry)
        taus.append(n.t)
        w_vs.append(float(sl.var_swap_strike()))
        w_atm.append(float(np.asarray(sl.implied_w(0.0)).ravel()[0]))
    taus = np.array(taus)
    w_vs = np.array(w_vs)
    w_atm = np.array(w_atm)
    return {
        "tau": taus, "w_vs": w_vs, "w_atm": w_atm,
        "vol_vs": 100 * np.sqrt(w_vs / taus),
        "vol_atm": 100 * np.sqrt(w_atm / taus),
    }


def fig_vs_term() -> str:
    spy = _series("SPY")
    nvda = _series("NVDA")

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) SPY in total variance: both curves rise; the fair strike rides above.
    ax_a.plot(spy["tau"], spy["w_vs"], "o-", color=PALETTE["data"], ms=4.0,
              lw=1.2, label=r"$w_{\rm vs}$ (fair strike)")
    ax_a.plot(spy["tau"], spy["w_atm"], "s-", color=PALETTE["model"], ms=3.6,
              lw=1.2, label=r"$w(0)$ (ATM)")
    ax_a.set_xlabel(r"maturity $\tau$ (years)")
    ax_a.set_ylabel("total variance")
    ax_a.legend(loc="upper left", fontsize=7.5)
    figstyle.panel(ax_a, "a", "SPY: the integral's term structure")

    # (b) both names in vol units: the spread over ATM is the priced wing mass.
    for series, name, color in ((spy, "SPY", PALETTE["model"]),
                                (nvda, "NVDA", PALETTE["mcs"])):
        ax_b.plot(series["tau"], series["vol_vs"], "o-", color=color, ms=4.0,
                  lw=1.2, label=rf"{name} $\sigma_{{\rm vs}}$")
        ax_b.plot(series["tau"], series["vol_atm"], "s--", color=color,
                  ms=3.4, lw=1.0, alpha=0.75,
                  label=rf"{name} ATM $\sigma$")
    ax_b.set_xscale("log")
    ax_b.set_xlabel(r"maturity $\tau$ (years, log scale)")
    ax_b.set_ylabel("volatility (%)")
    ax_b.legend(loc="upper right", fontsize=6.8, ncol=2)
    figstyle.panel(ax_b, "b", "both names: fair strike vs ATM")

    figstyle.save(fig, "fig_vs_term")

    spy_spread = float(np.max((spy["vol_vs"] - spy["vol_atm"]) * 100.0))
    nvda_spread = float(np.max((nvda["vol_vs"] - nvda["vol_atm"]) * 100.0))
    inc_spy = np.diff(spy["w_vs"])
    inc_nvda = np.diff(nvda["w_vs"])
    inc_min = float(min(inc_spy.min(), inc_nvda.min()))
    fwd_var = inc_spy / np.diff(spy["tau"])
    fwd_vol_min = float(100.0 * np.sqrt(max(fwd_var.min(), 0.0)))

    STORE.add("term", "VsTermSpySpreadBp", num(spy_spread, 0),
              "largest SPY fair-strike spread over ATM vol (vol bp)")
    STORE.add("term", "VsTermNvdaSpreadBp", num(nvda_spread, 0),
              "largest NVDA fair-strike spread over ATM vol (vol bp)")
    STORE.add("term", "VsTermIncMinVarBp", num(1e4 * inc_min, 1),
              "smallest adjacent-expiry increment of w_vs across both names (variance bp)")
    STORE.add("term", "VsTermFwdVolMinPct", num(fwd_vol_min, 1),
              "smallest SPY forward variance between expiries, as a forward vol (%)")
    return (f"spread SPY {spy_spread:.0f} / NVDA {nvda_spread:.0f} bp, "
            f"min inc {1e4 * inc_min:.1f} var bp, min fwd vol {fwd_vol_min:.1f}%")
