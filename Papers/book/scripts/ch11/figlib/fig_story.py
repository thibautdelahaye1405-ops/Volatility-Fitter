"""F6: the asynchronous pair -- what a snapshot solver cannot say.

The toy tape (handle levels, pure synthetic): the liquid name A prints
10, 11, ..., 15 at t = 0..5; the thin name B prints 10 at t = 0 and 10 at
t = 3.5; the desk asserts B follows A one for one, one way.  Panel (a):
the desk path (carry the relation between prints, learn the dislocation at
the print, keep it afterwards) against the per-snapshot symmetric solve
(which drags A down at t = 3.5 and erases B's dislocation at t = 4).
Panel (b): the dislocation's decay under three half-lives -- the memory
dial made visible.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import solver
from figstyle import PALETTE, panel
from macros import STORE, num

CLAMP_VAR = 1e-8
P_REL = 4.0                      # the asserted relation's precision


def _snapshot_solve(lit: dict[int, float]) -> np.ndarray:
    """The memoryless symmetric solve: nodes (A, B), whoever prints is lit."""
    prob = solver.Problem(n=2)
    prob.edge(1, 0, P_REL, 1.0)          # B <- A, beta one
    for node, value in lit.items():
        prob.observe(node, value, CLAMP_VAR)
    return solver.solve(prob).mean


def fig_gr_story() -> str:
    # The tape.
    a_prints = {t: 10.0 + t for t in range(6)}
    b_prints = {0.0: 10.0, 3.5: 10.0}

    # The desk path for B: ride the relation from A's last print, learn the
    # dislocation at the print, keep it afterwards (infinite half-life).
    times = [0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 5.0]
    a_last = {t: a_prints[int(np.floor(t))] for t in times}
    desk_b = []
    dislocation = 0.0
    for t in times:
        if t in b_prints:
            dislocation = b_prints[t] - a_last[t]
            desk_b.append(b_prints[t])
        else:
            desk_b.append(a_last[t] + dislocation)

    # The memoryless path: solve each print instant with whoever is lit.
    snap_times = [0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 5.0]
    snap_a, snap_b = [], []
    for t in snap_times:
        lit = {}
        if t in a_prints:
            lit[0] = a_prints[t]
        if t in b_prints:
            lit[1] = b_prints[t]
        mean = _snapshot_solve(lit)
        snap_a.append(mean[0]), snap_b.append(mean[1])

    fig, axes = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax = axes[0]
    ta = sorted(a_prints)
    ax.step(ta, [a_prints[t] for t in ta], where="post",
            color=PALETTE["ink"], lw=1.2, label="A prints")
    ax.step(times, desk_b, where="post", color=PALETTE["model"],
            label="B, desk path")
    ax.step(snap_times, snap_b, where="post", color=PALETTE["third"],
            ls="--", label="B, snapshot solve")
    ax.plot([3.42], [snap_a[4]], "v", color=PALETTE["third"], ms=6)
    ax.plot([0.0, 3.5], [10.0, 10.0], "s", mfc="white",
            mec=PALETTE["data"], mew=1.3, ms=6, label="B prints")
    figstyle.callout(ax, "A dragged to the print", xy=(3.42, snap_a[4]),
                     xytext=(1.5, 8.6))
    figstyle.callout(ax, "dislocation erased", xy=(4.0, snap_b[5]),
                     xytext=(4.15, 12.2))
    ax.set_xlabel("session time (hours)")
    ax.set_ylabel("published mark (handle level)")
    ax.set_ylim(7.9, 15.8)
    ax.legend(loc="upper left", fontsize=7.5)
    panel(ax, "a", "the desk path vs the memoryless solve")

    # (b) the memory dial: the dislocation under three half-lives.
    ax = axes[1]
    tt = np.linspace(3.5, 6.5, 200)
    for half, cname, label in [(0.5, "data", r"$t_{1/2}=0.5$ h"),
                               (2.0, "model", r"$t_{1/2}=2$ h"),
                               (np.inf, "ink", r"$t_{1/2}=\infty$")]:
        u = [solver.residual_decay(-3.0, t - 3.5, half) for t in tt]
        ax.plot(tt, u, color=PALETTE[cname], label=label)
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.set_xlabel("session time (hours)")
    ax.set_ylabel("carried dislocation (handle pts)")
    ax.legend(loc="lower right")
    panel(ax, "b", "how long is a private dislocation believed?")

    figstyle.save(fig, "fig_gr_story")

    STORE.add("story", "GrStorySnapA", num(snap_a[4], 1),
              "the snapshot solve's A mark at t=3.5 (dragged to the print)")
    STORE.add("story", "GrStorySnapB", num(snap_b[5], 1),
              "the snapshot solve's B mark at t=4 (dislocation erased)")
    STORE.add("story", "GrStoryDeskB", num(desk_b[5], 1),
              "the desk path's B mark at t=4 (dislocation kept)")
    return "asynchronous pair drawn"
