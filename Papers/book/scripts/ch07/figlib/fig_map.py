"""Figure 7.2: the premium mapped over the quote plane, with its dead zone."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num, sci

S, SIGMA = 100.0, 0.25
KS = np.linspace(55.0, 165.0, 111)         # strikes (dollars per 100 spot)
TS = np.linspace(0.05, 1.5, 30)            # maturities (years)
PLATEAU_TOL = 0.001                        # dollars: A - intrinsic below this
N_MAP = 256

PUT_R, PUT_Q = 0.04, 0.0                   # panel (a): puts, positive rate
CALL_R, CALL_Q = 0.02, 0.06                # panel (b): the running example


def _surface(is_call: bool, r: float, q: float
             ) -> tuple[np.ndarray, np.ndarray]:
    """(premium, plateau flag) on the TS x KS grid."""
    prem = np.zeros((TS.size, KS.size))
    plateau = np.zeros_like(prem, dtype=bool)
    flags = np.full(KS.size, is_call)
    intr = np.maximum(S - KS, 0.0) if is_call else np.maximum(KS - S, 0.0)
    sig = np.full(KS.size, SIGMA)
    for i, t in enumerate(TS):
        a = tree.crr_batch(flags, S, KS, t, sig, r, q, n=N_MAP,
                           american=True)
        e = tree.crr_batch(flags, S, KS, t, sig, r, q, n=N_MAP,
                           american=False)
        prem[i] = np.maximum(a - e, 0.0)
        # The plateau of interest: the price IS a positive intrinsic value
        # (worthless far-out-of-the-money quotes are a different story).
        plateau[i] = ((a - intr) <= PLATEAU_TOL) & (intr > 0.0)
    return prem, plateau


def _boundary(plateau: np.ndarray, deep_is_high_strike: bool) -> np.ndarray:
    """Per-maturity strike where the intrinsic plateau begins (NaN if none)."""
    edge = np.full(TS.size, np.nan)
    for i in range(TS.size):
        idx = np.nonzero(plateau[i])[0]
        if idx.size:
            edge[i] = KS[idx.min()] if deep_is_high_strike else KS[idx.max()]
    return edge


def fig_deam_map() -> str:
    prem_p, plat_p = _surface(False, PUT_R, PUT_Q)
    prem_c, plat_c = _surface(True, CALL_R, CALL_Q)
    edge_p = _boundary(plat_p, True)
    edge_c = _boundary(plat_c, False)

    # Merton's theorem, measured: no-dividend calls never pay for the right.
    flags = np.ones(KS.size, dtype=bool)
    sig = np.full(KS.size, SIGMA)
    merton = 0.0
    for t in (0.25, 0.75, 1.5):
        a = tree.crr_batch(flags, S, KS, t, sig, PUT_R, 0.0, n=N_MAP,
                           american=True)
        e = tree.crr_batch(flags, S, KS, t, sig, PUT_R, 0.0, n=N_MAP,
                           american=False)
        merton = max(merton, float(np.nanmax(np.abs(a - e))))

    vmax = max(float(prem_p.max()), float(prem_c.max()))
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2,
                                     sharey=True)
    pcm = None
    for ax, prem, edge in ((ax_a, prem_p, edge_p), (ax_b, prem_c, edge_c)):
        pcm = ax.pcolormesh(KS / S * 100.0, TS, prem, cmap=figstyle.HEATMAP,
                            shading="auto", vmin=0.0, vmax=vmax,
                            rasterized=True)
        ax.plot(edge / S * 100.0, TS, color=PALETTE["data"], lw=1.4,
                zorder=5)
        ax.set_xlabel("strike (% of spot)")
        ax.grid(False)
    ax_a.set_ylabel("maturity $t$ (years)")
    figstyle.panel(ax_a, "a",
                   f"puts, $r={100.0 * PUT_R:.0f}\\%$, no dividends")
    figstyle.panel(ax_b, "b",
                   f"calls, $q_d={100.0 * CALL_Q:.0f}\\%$ against "
                   f"$r={100.0 * CALL_R:.0f}\\%$")
    cbar = fig.colorbar(pcm, ax=(ax_a, ax_b), pad=0.015, aspect=28)
    cbar.set_label("premium $A-E$ (dollars)")
    figstyle.callout(ax_a, "price $=$ intrinsic beyond\nthe orange edge",
                     (float(edge_p[10]) / S * 100.0 + 5.0, TS[10]),
                     (58.0, 1.05))

    figstyle.save(fig, "fig_deam_map")

    i_half = int(np.argmin(np.abs(TS - 0.5)))
    STORE.add("map", "DeamMapPutBdryPct", num(edge_p[i_half] / S * 100.0, 0),
              "put plateau onset at t=0.5 (strike, % of spot)")
    STORE.add("map", "DeamMapCallBdryPct", num(edge_c[i_half] / S * 100.0, 0),
              "call plateau onset at t=0.5 (strike, % of spot)")
    STORE.add("map", "DeamMapPutMaxDollars", num(float(prem_p.max()), 2),
              "largest put premium on the map (dollars per 100 spot)")
    STORE.add("map", "DeamMapCallMaxDollars", num(float(prem_c.max()), 2),
              "largest call premium on the map (dollars per 100 spot)")
    STORE.add("map", "DeamMapMertonMaxDollars", sci(merton, 1),
              "largest |A-E| for no-dividend calls anywhere on the grid "
              "(dollars; Merton's theorem measured)")
    return (f"put bdry {edge_p[i_half]:.0f}, call bdry {edge_c[i_half]:.0f}, "
            f"merton {merton:.1e}")
