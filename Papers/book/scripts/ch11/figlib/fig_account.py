"""F4: silent neighbours cost nothing, and one source is one.

Panel (a): the dead-informer fixture.  A receiver trusts two informers
equally; one is lit, the other is a dark dead end.  The factor assembly
transfers the whole message no matter how much trust the dead informer was
configured to carry; the row-normalized averaging assembly destroys the
live signal as that configured trust grows.

Panel (b): the repeated-route fixture.  One source, observed at finite
precision, reaches the target directly and through a middle node.  The
joint solve prices the two routes' shared origin: marginal variance
5/(3p).  Counting the routes as independent messages yields 6/(5p).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import solver
from figstyle import PALETTE, panel
from macros import STORE, num

P = 1.0


def fig_gr_account() -> str:
    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) the dead informer: transfer against configured dead trust.
    ratios = np.logspace(-1, 3, 25)
    pair, avg = [], []
    for r in ratios:
        factors = [solver.Factor(0, 1, P, 1.0),        # receiver <- lit A
                   solver.Factor(0, 2, r * P, 1.0)]    # receiver <- dead D
        obs = [(1, 1.0, 1.0 / P)]
        prob = solver.Problem(n=3, factors=list(factors))
        prob.obs = list(obs)
        pair.append(solver.solve(prob).mean[0])
        avg.append(solver.averaging_solve(3, factors, obs)[0])
    pair, avg = np.asarray(pair), np.asarray(avg)

    ax = axes[0]
    ax.semilogx(ratios, pair, color=PALETTE["model"],
                label="factor assembly")
    ax.semilogx(ratios, avg, color=PALETTE["third"],
                label="averaging assembly")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xlabel("configured dead-informer trust (relative to the live one)")
    ax.set_ylabel("receiver posterior / lit message")
    ax.set_ylim(-0.05, 1.1)
    ax.legend(loc="center left")
    panel(ax, "a", "a silent neighbour must cost nothing")

    # (b) the repeated route: joint variance against naive accounting.
    prob = solver.Problem(n=3)              # order: source, middle, target
    prob.edge(2, 0, P, 1.0)                 # direct route
    prob.edge(1, 0, P, 1.0)                 # two-leg route, first leg
    prob.edge(2, 1, P, 1.0)                 # two-leg route, second leg
    prob.observe(0, 1.0, 1.0 / P)
    post = solver.solve(prob)
    joint = post.var[2] * P                 # in 1/p units
    naive = 1.0 / (P / 2.0 + P / 3.0) * P   # effective precisions summed

    ax = axes[1]
    xs = [0, 1]
    ax.bar(xs, [joint, naive], 0.5,
           color=[PALETTE["model"], PALETTE["third"]])
    ax.set_xticks(xs)
    ax.set_xticklabels(["joint solve", "per-route\naccounting"], fontsize=8)
    ax.set_ylabel(r"target marginal variance ($1/p$ units)")
    for x, v, lab in zip(xs, [joint, naive], ["5/3", "6/5"]):
        ax.text(x, v + 0.04, lab, ha="center", fontsize=8.5,
                color=PALETTE["ink"])
    ax.set_ylim(0, 2.1)
    panel(ax, "b", "two routes, one source: variance is not divisible")

    figstyle.save(fig, "fig_gr_account")

    STORE.add("account", "GrDeadPairMin", num(pair.min(), 4),
              "factor-assembly transfer, minimum across the trust sweep")
    i_eq = int(np.argmin(np.abs(ratios - 1.0)))
    STORE.add("account", "GrDeadAvgEq", num(avg[i_eq], 2),
              "averaging-assembly transfer at equal configured trust")
    STORE.add("account", "GrDeadAvgHigh", num(avg[-1], 2),
              "averaging-assembly transfer at 1000x dead trust")
    STORE.add("account", "GrRepeatJoint", num(joint, 3),
              "joint marginal variance at the target, 1/p units (5/3)")
    STORE.add("account", "GrRepeatNaive", num(naive, 3),
              "naive per-route variance, 1/p units (6/5)")
    STORE.add("account", "GrRepeatOverstatePct",
              num(100.0 * (joint / naive - 1.0), 0),
              "precision overstatement of per-route accounting, percent")
    return "dead informer + repeated route locked"
