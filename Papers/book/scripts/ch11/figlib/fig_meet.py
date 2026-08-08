"""F3: messages meet -- competing informers vote; chains tax the band only."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import solver
from figstyle import PALETTE, panel
from macros import STORE, sci

CLAMP_VAR = 1e-8
P = 4.0                      # chain relation precision: sd 0.5 per hop
OBS_VAR = 0.01               # chain source observation variance (sd 0.1)


def _vote(p_short: float, betas: bool):
    """6M dark; 3M lit at -1, 1Y lit at +1; returns the 6M posterior."""
    prob = solver.Problem(n=3)          # order: 3M, 6M, 1Y
    b_short = 0.5 if betas else 1.0     # 6M <- 3M reads tau ratio 1/2
    b_long = 2.0 if betas else 1.0      # 6M <- 1Y reads tau ratio 2
    prob.edge(1, 0, p_short, b_short)
    prob.edge(1, 2, 1.0, b_long)
    prob.observe(0, -1.0, CLAMP_VAR)
    prob.observe(2, +1.0, CLAMP_VAR)
    return solver.solve(prob)


def fig_gr_meet() -> str:
    scenarios = [
        ("equal trust,\nbeta one", _vote(1.0, betas=False)),
        ("short leg at $3p$,\nbeta one", _vote(3.0, betas=False)),
        ("equal trust,\ncalendar betas", _vote(1.0, betas=True)),
    ]

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax = axes[0]
    xs = np.arange(len(scenarios))
    vals = [post.mean[1] for _, post in scenarios]
    sds = [post.sd()[1] for _, post in scenarios]
    ax.bar(xs, vals, 0.55, color=PALETTE["model"])
    ax.errorbar(xs, vals, yerr=sds, fmt="none", ecolor=PALETTE["ink"],
                elinewidth=1.0, capsize=3)
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xticks(xs)
    ax.set_xticklabels([s for s, _ in scenarios], fontsize=7.5)
    ax.set_ylabel("6M posterior (vol pts)")
    panel(ax, "a", "two informers vote at the receiver")

    # (b) the six-hop chain: mean undamped, band accumulating.
    n = 7
    prob = solver.Problem(n=n)
    for k in range(n - 1):
        prob.edge(k + 1, k, P, 1.0)
    prob.observe(0, 1.0, OBS_VAR)
    post = solver.solve(prob)
    hops = np.arange(n)
    closed = np.sqrt(OBS_VAR + hops / P)

    ax = axes[1]
    ax.plot(hops, post.mean, "o-", color=PALETTE["model"], label="posterior mean")
    ax.fill_between(hops, post.mean - post.sd(), post.mean + post.sd(),
                    color=PALETTE["band"], zorder=0, label=r"$\pm1$ sd")
    ax.plot(hops, post.mean + closed, ls=":", color=PALETTE["ink"], lw=0.9,
            label="accumulation law")
    ax.plot(hops, post.mean - closed, ls=":", color=PALETTE["ink"], lw=0.9)
    ax.set_xlabel("hops from the lit node")
    ax.set_ylabel("innovation (vol pts)")
    ax.set_ylim(-0.6, 2.6)
    ax.legend(loc="upper left", fontsize=7.5)
    panel(ax, "b", "the chain law: mean undamped, band accumulating")

    figstyle.save(fig, "fig_gr_meet")

    STORE.add("meet", "GrVoteCancel", f"{scenarios[0][1].mean[1]:+.2f}",
              "equal-trust beta-one opposing signals at the 6M receiver")
    STORE.add("meet", "GrVoteOut", f"{scenarios[1][1].mean[1]:+.2f}",
              "the 3p short leg outvotes: 6M posterior")
    STORE.add("meet", "GrVoteBeta", f"{scenarios[2][1].mean[1]:+.2f}",
              "same signals under calendar betas: receiver-unit average")
    gap = np.abs(post.sd() - closed).max()
    STORE.add("meet", "GrHopGap", sci(gap, 1),
              "max gap between solved chain sds and the accumulation law")
    STORE.add("meet", "GrHopMean", f"{post.mean[-1]:+.2f}",
              "posterior mean at hop six (undamped)")
    return "voting and chain locked"
