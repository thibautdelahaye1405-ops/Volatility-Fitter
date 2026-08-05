"""Figures F8-F9: tail speeds, moment budgets, and Lee slopes.

F8 fig_tails -- the three-link chain endpoint speed -> last finite moment
                -> Lee slope, with all 16 fitted nodes marked and the two
                featured nodes highlighted.
F9 fig_lee   -- effective slope w(k)/|k| vs the Lee limit on the SPY
                deep-dive node, with 10-delta / 1-delta diamonds.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from volfit.models.lqd.basis import lee_psi

import data
from figstyle import PALETTE, ROW2, ROW3, panel, save
from macros import STORE, num

TICKER_COLOR = {"SPY": PALETTE["model"], "NVDA": PALETTE["data"]}
SIDE_MARKER = {"left": "o", "right": "^"}


def _tail_points() -> list[dict]:
    """(ticker, side, A, p, beta, featured) for every node and both wings."""
    featured = {data.SPY_DEC, data.NVDA_LONG}
    points = []
    for node in data.nodes():
        a_l, a_r, b_l, b_r = node.tails()
        star = (node.ticker, node.expiry) in featured
        points.append(dict(ticker=node.ticker, side="left", a=a_l,
                           p=1.0 / a_l, beta=b_l, featured=star))
        points.append(dict(ticker=node.ticker, side="right", a=a_r,
                           p=1.0 / a_r - 1.0, beta=b_r, featured=star))
    return points


def _scatter(ax, points, xkey, ykey) -> None:
    for pt in points:
        ax.scatter(pt[xkey], pt[ykey], s=16 if pt["featured"] else 9,
                   marker=SIDE_MARKER[pt["side"]],
                   color=TICKER_COLOR[pt["ticker"]],
                   edgecolor=PALETTE["ink"] if pt["featured"] else "none",
                   linewidths=0.6, zorder=4)


def fig_tails() -> str:
    """F8: endpoint speed -> critical moment -> Lee slope, data overlaid."""
    points = _tail_points()
    for pt in points:  # x-coordinate of the first panel
        pt["h"] = float(np.log(pt["a"]))

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    h_grid = np.linspace(min(pt["h"] for pt in points) - 0.4,
                         max(pt["h"] for pt in points) + 0.3, 300)
    axes[0].plot(h_grid, np.exp(h_grid), color=PALETTE["ink"], lw=1.0)
    _scatter(axes[0], points, "h", "a")
    axes[0].set_xlabel(r"endpoint log-speed $g(0)$, $g(1)$")
    axes[0].set_ylabel(r"tail scale $\lambda_- = e^{g(0)}$, $\lambda_+ = e^{g(1)}$")
    panel(axes[0], "a", "first link: the endpoint speed")

    a_max = max(pt["a"] for pt in points) + 0.08  # A_L may exceed 1
    a_grid = np.linspace(0.02, max(0.99, a_max), 400)
    axes[1].semilogy(a_grid, 1.0 / a_grid, color=PALETTE["ink"], lw=1.0,
                     label=r"left: $r_-^* = 1/\lambda_-$")
    right_grid = a_grid[a_grid < 0.995]  # the right wall sits at lambda_+ = 1
    axes[1].semilogy(right_grid, np.maximum(1.0 / right_grid - 1.0, 1e-3),
                     color=PALETTE["ink"], lw=1.0, ls="--",
                     label=r"right: $r_+^* = 1/\lambda_+ - 1$")
    _scatter(axes[1], points, "a", "p")
    axes[1].set_xlabel(r"tail scale $\lambda_\pm$")
    axes[1].set_ylabel(r"critical moment order $r_\pm^*$")
    axes[1].legend(loc="upper right", fontsize=6.8)
    panel(axes[1], "b", "second link: the moment budget")

    p_grid = np.logspace(-2.0, 2.5, 400)
    axes[2].semilogx(p_grid, lee_psi(p_grid), color=PALETTE["ink"], lw=1.0)
    axes[2].axhline(2.0, color=PALETTE["muted"], lw=0.7, ls=":")
    axes[2].text(1.3e-2, 1.9, "slope bound 2", fontsize=7.0,
                 color=PALETTE["muted"], va="top")
    _scatter(axes[2], points, "p", "beta")
    axes[2].set_xlabel(r"critical moment order $r^*$")
    axes[2].set_ylabel(r"Lee slope $\Psi(r^*)$")
    axes[2].set_ylim(-0.05, 2.1)
    panel(axes[2], "c", "third link: the asymptotic wing")

    # Shared marker legend on the middle panel's spare space.
    for ticker, color in TICKER_COLOR.items():
        axes[0].scatter([], [], s=12, marker="s", color=color, label=ticker)
    for side, marker in SIDE_MARKER.items():
        axes[0].scatter([], [], s=12, marker=marker, color=PALETTE["muted"],
                        label=f"{side} wing")
    axes[0].legend(loc="upper left", fontsize=6.8)

    save(fig, "fig_tails")

    for prefix, key in (("SpyDec", data.SPY_DEC), ("NvdaLong", data.NVDA_LONG)):
        node = data.node(*key)
        a_l, a_r, _, _ = node.tails()
        STORE.add("tails", f"{prefix}MomentLeft", num(1.0 / a_l, 2),
                  "last finite moment order of the left tail, 1/lambda_-")
        STORE.add("tails", f"{prefix}MomentRight", num(1.0 / a_r - 1.0, 2),
                  "last finite moment order of the right tail,"
                  " 1/lambda_+ - 1")
    return f"tails chain drawn over {len(points)} node-wings"


# ------------------------------------------------------------------ F9
def _delta_strike(node: data.Node, target: float, side: str) -> float:
    """Log-moneyness where the Black delta reaches ``target`` (0.10 / 0.01)."""

    def excess(k: float) -> float:
        w = float(node.slice.implied_w(k))
        d1 = -k / np.sqrt(w) + 0.5 * np.sqrt(w)
        prob = norm.cdf(d1) if side == "right" else norm.cdf(-d1)
        return float(prob - target)

    lo, hi = (0.005, 6.0) if side == "right" else (-6.0, -0.005)
    return float(brentq(excess, lo, hi, xtol=1e-10))


def fig_lee() -> str:
    """F9: effective slope vs the Lee limit on SPY 2026-12-18, both wings."""
    node = data.node(*data.SPY_DEC)
    _, _, beta_l, beta_r = node.tails()

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    diamonds: dict[str, dict[str, float]] = {}
    for ax, side, beta, leg in ((axes[0], "left", beta_l, "center"),
                                (axes[1], "right", beta_r, "upper right")):
        sign = -1.0 if side == "left" else 1.0
        kk = sign * np.logspace(np.log10(0.08), np.log10(6.0), 220)
        # Stop where the OTM price underflows: inverting a ~1e-16 price
        # returns Black-inversion noise, not a smile (right wing dies fast,
        # A_R = 0.066 means C ~ e^{-k/A_R}).
        otm = np.asarray(node.slice.call_price(kk))
        if side == "left":
            otm = otm - (1.0 - np.exp(kk))
        alive = otm > 1e-13
        kk = kk[alive]
        eff = np.asarray(node.slice.implied_w(kk)) / np.abs(kk)
        ax.semilogx(np.abs(kk), eff, color=PALETTE["model"],
                    label=r"effective $w(k)/|k|$")
        ax.axhline(beta, color=PALETTE["ink"], lw=0.9, ls=":",
                   label=rf"Lee limit $\beta = {beta:.3f}$")
        for target, tag in ((0.10, "ten"), (0.01, "one")):
            k_d = _delta_strike(node, target, side)
            e_d = float(node.slice.implied_w(k_d)) / abs(k_d)
            diamonds[f"{side}_{tag}"] = {"k": k_d, "eff": e_d}
            ax.scatter([abs(k_d)], [e_d], s=22, marker="D",
                       color=PALETTE["data"], zorder=5)
            ax.annotate(rf"{int(target * 100)}$\Delta$", (abs(k_d), e_d),
                        xytext=(0, 7), textcoords="offset points",
                        ha="center", fontsize=7.5, color=PALETTE["muted"])
        ax.set_xlabel(r"$|k|$")
        ax.set_ylabel(r"total variance slope $w(k)/|k|$")
        ax.legend(loc=leg, fontsize=7.0)
    panel(axes[0], "a", "left wing (puts)")
    panel(axes[1], "b", "right wing (calls)")

    save(fig, "fig_lee")

    for side, beta in (("Left", beta_l), ("Right", beta_r)):
        for tag, name in (("ten", "TenDelta"), ("one", "OneDelta")):
            entry = diamonds[f"{side.lower()}_{tag}"]
            STORE.add("lee", f"SpyDecEff{name}{side}", num(entry["eff"], 3),
                      f"effective slope w(k)/|k| at the {side.lower()}-wing"
                      f" {'10' if tag == 'ten' else '1'}-delta strike")
            STORE.add("lee", f"SpyDec{name}K{side}", num(entry["k"], 3),
                      f"log-moneyness of the {side.lower()}-wing"
                      f" {'10' if tag == 'ten' else '1'}-delta strike")
    STORE.add("lee", "SpyDecOneDeltaShareLeft",
              num(100.0 * diamonds["left_one"]["eff"] / beta_l, 0),
              "left 1-delta effective slope as % of the Lee limit")
    STORE.add("lee", "SpyDecOneDeltaShareRight",
              num(100.0 * diamonds["right_one"]["eff"] / beta_r, 0),
              "right 1-delta effective slope as % of the Lee limit")
    return (f"Lee: beta L/R {beta_l:.3f}/{beta_r:.3f}; 1-delta reaches "
            f"{100 * diamonds['left_one']['eff'] / beta_l:.0f}% /"
            f" {100 * diamonds['right_one']['eff'] / beta_r:.0f}% of the limit")
