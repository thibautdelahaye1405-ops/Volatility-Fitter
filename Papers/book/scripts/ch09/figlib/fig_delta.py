"""F4 -- the price of the choice (section 9.4).

Panel (a): the total forward delta of a call across strikes on the frozen
hero smile under the three regimes -- Black delta plus the smile response
phi(d+) sqrt(t) (R-1) sigma'(k), the LOCAL slope of today's smile at the
strike.  Panel (b): the R=0 vs R=2 gap, 2 phi(d+) sqrt(t) |sigma'(k)|,
in delta points across strikes: a vega profile weighted by the local
slope.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import ndtr

sys.path.insert(0, str(Path(__file__).resolve().parent))

import data9
import figstyle
from blackutil import d_plus, phi
from figstyle import PALETTE, REGIME_COLORS, REGIME_NAMES
from macros import STORE, num

_SPAN = (-0.25, 0.12)


def _delta_tot(sm, k: np.ndarray, regime: float) -> np.ndarray:
    d_p = d_plus(k, sm.w(k))
    return (ndtr(d_p)
            + phi(d_p) * np.sqrt(sm.t) * (regime - 1.0)
            * data9.local_slope(sm, k))


def fig_ssr_delta() -> str:
    sm = data9.hero()
    k = np.linspace(*_SPAN, 401)
    k_mark = np.array([data9.K_MARK])

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) total delta under the three regimes -------------------------------
    ax = axes[0]
    for regime in data9.REGIMES:
        ax.plot(k, 100.0 * _delta_tot(sm, k, regime),
                color=REGIME_COLORS[regime], lw=1.4,
                label=REGIME_NAMES[regime])
    lo = float(_delta_tot(sm, k_mark, 0.0)[0])
    hi = float(_delta_tot(sm, k_mark, 2.0)[0])
    gap_pts = 100.0 * abs(hi - lo)
    ax.plot([data9.K_MARK, data9.K_MARK], [100.0 * lo, 100.0 * hi],
            color=PALETTE["ink"], lw=1.6, zorder=5)
    figstyle.callout(
        ax, f"{gap_pts:.1f} delta points\nat the marked strike",
        xy=(data9.K_MARK, 100.0 * 0.5 * (lo + hi)),
        xytext=(data9.K_MARK - 0.115, 100.0 * 0.5 * (lo + hi) - 14.0),
    )
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("total forward call delta (delta points)")
    ax.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax, "a", "one book, three deltas")

    # (b) the regime gap across strikes -------------------------------------
    ax = axes[1]
    d_p = d_plus(k, sm.w(k))
    gap = 2.0 * phi(d_p) * np.sqrt(sm.t) * np.abs(data9.local_slope(sm, k))
    ax.plot(k, 100.0 * gap, color=PALETTE["ink"], lw=1.5)
    ax.axvline(data9.K_MARK, color=PALETTE["muted"], lw=0.7, ls="--")
    max_pts = float(100.0 * gap.max())
    k_max = float(k[np.argmax(gap)])
    figstyle.callout(
        ax, f"peak {max_pts:.1f} points\nat $k={k_max:+.2f}$",
        xy=(k_max, max_pts), xytext=(k_max + 0.06, max_pts - 1.2),
    )
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"$\mathcal{R}=0$ vs $\mathcal{R}=2$ gap (delta points)")
    figstyle.panel(ax, "b",
                   r"the gap $2\varphi(d_+)\sqrt{t}\,|\sigma_{\rm old}'(k)|$")

    figstyle.save(fig, "fig_ssr_delta")

    put_delta = 100.0 * (1.0 - float(ndtr(d_plus(k_mark, sm.w(k_mark)))[0]))
    atm_gap = float(100.0 * np.interp(0.0, k, gap))
    STORE.add("delta", "SsrDeltaGapPts", num(gap_pts, 1),
              "R=0 vs R=2 total-delta gap at the marked strike, delta pts")
    STORE.add("delta", "SsrDeltaMaxPts", num(max_pts, 1),
              "largest regime delta gap across the span, delta pts")
    STORE.add("delta", "SsrDeltaMaxK", num(k_max, 2),
              "log-moneyness where the regime delta gap peaks")
    STORE.add("delta", "SsrDeltaAtmPts", num(atm_gap, 1),
              "regime delta gap at the money, delta pts")
    STORE.add("delta", "SsrDeltaMarkPutDelta", f"{put_delta:.0f}",
              "Black forward put delta magnitude at the marked strike, pts")
    return (f"gap {gap_pts:.1f} pts at mark ({put_delta:.0f}-delta put), "
            f"peak {max_pts:.1f} at k={k_max:+.2f}")
