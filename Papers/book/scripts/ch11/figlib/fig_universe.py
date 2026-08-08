"""F1: the staged universe -- the board as a graph, and the lit morning."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import universe
from figstyle import PALETTE, panel
from macros import STORE, num

_ROWY = {"SPY": 3.0, "NVDA": 2.0, "sister": 1.0, "blend": 0.0}


def _positions():
    nodes = universe.build()
    return {(n.name, n.expiry): (np.log(n.tau), _ROWY[n.name])
            for n in nodes}


def fig_gr_universe() -> str:
    nodes = universe.build()
    pos = _positions()
    obs = universe.observations()

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2,
                             gridspec_kw={"width_ratios": [1.35, 1.0]})

    # (a) the universe as a graph.
    ax = axes[0]
    ax.grid(False)
    # Calendar edges: along each row.
    for name, exps in (("SPY", universe.EXPIRIES),
                       ("NVDA", universe.EXPIRIES),
                       ("sister", universe.SYN_EXPIRIES),
                       ("blend", universe.SYN_EXPIRIES)):
        for e0, e1 in zip(exps[:-1], exps[1:]):
            (x0, y0), (x1, y1) = pos[(name, e0)], pos[(name, e1)]
            ax.plot([x0, x1], [y0, y1], color=PALETTE["muted"], lw=1.0,
                    zorder=1)
    # Cross edges: informer -> receiver arrows at shared expiries.  Edges
    # spanning more than one row are bowed so they visibly bypass the rows
    # in between (the blend hears SPY, not the sister).
    for recv, inf, beta in universe.CROSS:
        exps = universe.SYN_EXPIRIES if recv in universe.SYN \
            else universe.EXPIRIES
        for e in exps:
            (xi, yi) = pos[(inf, e)]
            (xr, yr) = pos[(recv, e)]
            rad = 0.35 if abs(yi - yr) > 1.5 else 0.0
            ax.annotate(
                "", xy=(xr, yr + 0.13 * np.sign(yi - yr)),
                xytext=(xi, yi - 0.13 * np.sign(yi - yr)),
                arrowprops={"arrowstyle": "-|>", "color": PALETTE["muted"],
                            "lw": 0.8, "shrinkA": 0, "shrinkB": 0,
                            "connectionstyle": f"arc3,rad={rad}"},
                zorder=1,
            )
    for n in nodes:
        x, y = pos[(n.name, n.expiry)]
        if n.lit:
            ax.plot([x], [y], "o", color=PALETTE["data"], ms=7.5, zorder=3)
        else:
            ax.plot([x], [y], "o", mfc="white", mec=PALETTE["model"],
                    mew=1.4, ms=7.5, zorder=3)
    for name, y in _ROWY.items():
        ax.text(np.log(0.030), y, name, ha="right", va="center",
                fontsize=8.5, color=PALETTE["ink"])
    days = [18, 46, 137, 228, 410, 501]
    taus_ = [universe.taus()[e] for e in universe.EXPIRIES]
    for pos_i, (tau, d) in enumerate(zip(taus_, days)):
        dy = -0.62 if pos_i < 4 else (-0.62 if d == 410 else -0.88)
        ax.text(np.log(tau), dy, f"{d}d", ha="center", fontsize=7.5,
                color=PALETTE["muted"])
    ax.plot([], [], "o", color=PALETTE["data"], ms=6, label="lit this morning")
    ax.plot([], [], "o", mfc="white", mec=PALETTE["model"], mew=1.4, ms=6,
            label="dark")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.06), ncol=2)
    ax.set_ylim(-0.95, 3.55)
    ax.set_xlim(np.log(0.028), np.log(2.1))
    ax.set_xticks([]), ax.set_yticks([])
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    panel(ax, "a", "the universe: twenty nodes, four names")

    # (b) the lit morning: measured innovations at the eight lit nodes.
    ax = axes[1]
    lit = [n for n in nodes if n.lit]
    xs = np.arange(len(lit))
    vals = [obs[(n.name, n.expiry)] for n in lit]
    colors = [PALETTE["data"]] * 6 + [PALETTE["ink"]] * 2
    ax.bar(xs, vals, 0.62, color=colors)
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xticks(xs)
    ax.set_xticklabels(
        [f"{d}d" for d in days] + ["46d", "228d"], fontsize=7.5)
    ax.text(2.5, 5.6, "SPY", color=PALETTE["data"], fontsize=8.5)
    ax.text(6.35, 5.6, "NVDA", color=PALETTE["ink"], fontsize=8.5)
    ax.set_ylabel("measured innovation (vol pts)")
    panel(ax, "b", "the eight lit innovations")

    figstyle.save(fig, "fig_gr_universe")

    STORE.add("universe", "GrNodeCount", "20", "universe node count")
    STORE.add("universe", "GrLitCount", "8", "lit nodes this morning")
    STORE.add("universe", "GrDarkCount", "12", "dark nodes this morning")
    STORE.add("universe", "GrAnchorMovePts", num(universe.ANCHOR_MOVE, 2),
              "the constructed systematic move at the SPY December anchor")
    STORE.add("universe", "GrScatterSd", num(universe.SCATTER_SD, 2),
              "per-node idiosyncratic scatter sd, vol points")
    STORE.add("universe", "GrObsSd", num(universe.OBS_SD, 2),
              "lit observation noise sd, vol points")
    STORE.add("universe", "GrBetaNvda", num(universe.TRUE_BETA["NVDA"], 1),
              "NVDA's stated beta on the index")
    STORE.add("universe", "GrBetaSister", num(universe.TRUE_BETA["sister"], 2),
              "the sister's true beta on the index")
    STORE.add("universe", "GrBetaBlend", num(universe.TRUE_BETA["blend"], 1),
              "the blend's stated beta on the index")
    obs_short = obs[("SPY", "2026-08-21")]
    STORE.add("universe", "GrSpyShortObs", f"{obs_short:+.2f}",
              "measured innovation at the lit 18-day SPY node, vol pts")
    obs_dec = obs[("SPY", "2026-12-18")]
    STORE.add("universe", "GrSpyDecObs", f"{obs_dec:+.2f}",
              "measured innovation at the lit SPY December node, vol pts")
    nvda_sep = obs[("NVDA", "2026-09-18")]
    STORE.add("universe", "GrNvdaSepObs", f"{nvda_sep:+.2f}",
              "measured innovation at the lit NVDA September node, vol pts")
    return "20-node universe drawn"
