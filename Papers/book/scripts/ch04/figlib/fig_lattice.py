"""F5: monotonicity is a property of the scheme, not of luck.

The same flat 40%-vol surface, the same lattice, marched to tau = 0.1 by the
same solver: fully implicit Euler produces a clean bell of second
differences (the discrete density); undamped Crank-Nicolson excites the
payoff kink and swings the second difference negative -- butterflies the
scheme invented out of nothing.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import pde1d
from figstyle import PALETTE
from macros import STORE, num

V_FLAT = 0.16   # 40% local vol
DY = 0.005      # a refined strike lattice (short-dated resolution)
TAU = 0.1
DT = 0.01


def fig_lv_monotone() -> str:
    y = pde1d.uniform_grid(3.0, DY)
    t_grid = np.linspace(0.0, TAU, int(round(TAU / DT)) + 1)

    def v_fn(tau, yy):
        return np.full_like(np.asarray(yy, dtype=float), V_FLAT)

    u_imp = pde1d.march(v_fn, y, t_grid, scheme="implicit")[TAU]
    u_cn = pde1d.march(v_fn, y, t_grid, scheme="cn", rannacher_steps=0)[TAU]

    def density(u):
        return (u[:-2] - 2.0 * u[1:-1] + u[2:]) / DY**2

    yi = y[1:-1]
    f_imp, f_cn = density(u_imp), density(u_cn)
    keep = (yi > 0.55) & (yi < 1.55)

    fig, ax = plt.subplots(figsize=figstyle.ONE)
    ax.axhline(0.0, color=PALETTE["muted"], lw=0.7)
    ax.plot(yi[keep], f_cn[keep], color=PALETTE["data"], lw=0.9,
            label="Crank–Nicolson, undamped")
    ax.plot(yi[keep], f_imp[keep], color=PALETTE["model"], lw=1.5,
            label="implicit Euler")
    ax.set_xlabel(r"strike $y$")
    ax.set_ylabel(r"second difference / $\Delta y^2$  (discrete density)")
    ax.set_ylim(-9.5, 7.5)
    ax.legend(loc="upper left")
    figstyle.callout(ax, "negative density: butterflies\ninvented by the scheme"
                     f"\n(clipped; minimum {f_cn[keep].min():.0f})",
                     (float(yi[keep][np.argmin(f_cn[keep])]), -9.0),
                     (0.62, -6.5))

    cfl = 2.0 * DY**2 / V_FLAT   # the monotonicity bound at y = 1
    STORE.add("lattice", "LvLatImplMinDens", num(float(f_imp[keep].min()), 4),
              "min discrete density under fully implicit Euler (plot window)")
    STORE.add("lattice", "LvLatCnMinDens", num(float(f_cn[keep].min()), 0),
              "min discrete density under undamped Crank-Nicolson "
              "(plot window)")
    STORE.add("lattice", "LvLatCflBound", num(cfl, 4),
              "CN monotonicity bound 2 dy^2/(v y^2) at the money on this "
              "lattice (the marching step 0.01 exceeds it)")
    figstyle.save(fig, "fig_lv_monotone")
    return f"impl min {f_imp.min():.3f}, CN min {f_cn.min():.2f}"
