"""Figure 10.4 -- coordinates decide what gets damped.

A controlled overnight experiment: today's true smile is yesterday's lifted
by a level jump, today's quotes cover only the at-the-money band.  Three
fits of the same spline family: data only (the wing is left to the
smoothness rule), shape baskets from yesterday (RR/BF rows -- they ride
today's level and land on the lifted truth), and absolute wing anchors from
yesterday (they cling to the un-jumped wing).  The ATM gate is closed in
both prior fits: no damping.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import estimation
import figstyle
from figstyle import PALETTE
from macros import STORE, num

JUMP = 0.04                     # the overnight level jump (4 vol points)
BAND = 0.10                     # today's quoted band
NOISE = 0.0030                  # stated per-quote noise (30 vol bp)
LEGS = (0.20, 0.30)             # wing-leg pairs (moderate, deep)
KNOTS = np.array([-0.30, -0.20, -0.12, -0.05, 0.0, 0.05, 0.12, 0.20, 0.30])
BUDGET = 20.0 / NOISE**2        # total prior budget: twenty clean quotes


def sigma_yesterday(k):
    return 0.20 - 0.35 * np.asarray(k, dtype=float) + 0.80 * np.asarray(
        k, dtype=float) ** 2


def sigma_today(k):
    return sigma_yesterday(k) + JUMP


def fig_flt_jump() -> str:
    family = estimation.SplineFamily(KNOTS)
    k_q = np.linspace(-BAND, BAND, 15)
    vols_q = sigma_today(k_q)

    # --- the three fits -----------------------------------------------------
    fit_data = estimation.fit_spline(family, k_q, vols_q, NOISE)

    # candidate shape rows: level, RR and BF at each leg pair, targets from
    # yesterday.  Every gate is COMPUTED (harmonic precision vs requirement
    # one) and the budget is split across the open gates in proportion --
    # exactly the chapter's stated rule.  Nothing is hand-dropped.
    d_0 = family.design(np.array([0.0]))[0]
    candidates = [("level", d_0, float(sigma_yesterday(0.0)),
                   np.array([1.0]), np.array([0.0]))]
    for leg in LEGS:
        d_p = family.design(np.array([+leg]))[0]
        d_m = family.design(np.array([-leg]))[0]
        tag = "mod" if leg == LEGS[0] else "deep"
        candidates.append((
            f"rr_{tag}", d_p - d_m,
            float(sigma_yesterday(leg) - sigma_yesterday(-leg)),
            np.array([1.0, -1.0]), np.array([+leg, -leg])))
        candidates.append((
            f"bf_{tag}", 0.5 * (d_p + d_m) - d_0,
            float(0.5 * (sigma_yesterday(leg) + sigma_yesterday(-leg))
                  - sigma_yesterday(0.0)),
            np.array([0.5, 0.5, -1.0]), np.array([+leg, -leg, 0.0])))
    gates = {}
    for name, _row, _tgt, coeffs, leg_k in candidates:
        prec = estimation.basket_precision(
            coeffs, estimation.support(leg_k, k_q))
        gates[name] = float(estimation.gate(prec))
    gate_sum = sum(gates.values())
    rows, targets, weights = [], [], []
    for name, row, tgt, _c, _k in candidates:
        if gates[name] > 0.0:
            rows.append(row)
            targets.append(tgt)
            weights.append(BUDGET * gates[name] / gate_sum)
    fit_basket = estimation.fit_spline(
        family, k_q, vols_q, NOISE, np.vstack(rows), np.asarray(targets),
        np.asarray(weights))

    # absolute anchors: yesterday's wing vols at the same four wing legs,
    # at the same total budget split equally.
    anchor_k = np.array([-LEGS[1], -LEGS[0], LEGS[0], LEGS[1]])
    fit_anchor = estimation.fit_spline(
        family, k_q, vols_q, NOISE, family.design(anchor_k),
        sigma_yesterday(anchor_k),
        np.full(anchor_k.size, BUDGET / anchor_k.size))

    supp_atm = float(estimation.support(np.array([0.0]), k_q)[0])

    # --- draw ---------------------------------------------------------------
    grid = np.linspace(-0.32, 0.32, 401)
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    ax_a.axvspan(-BAND, BAND, color=PALETTE["band"], alpha=0.55, zorder=0)
    ax_a.plot(grid, 1e2 * sigma_today(grid), color=PALETTE["ink"], lw=1.2,
              ls="--", label="today's truth (lifted)")
    ax_a.plot(grid, 1e2 * sigma_yesterday(grid), color=PALETTE["muted"],
              lw=1.0, ls=":", label="yesterday")
    ax_a.plot(grid, 1e2 * fit_data.vol(grid), color=PALETTE["data"], lw=1.3,
              label="data only")
    ax_a.plot(grid, 1e2 * fit_basket.vol(grid), color=PALETTE["model"],
              lw=1.5, label="shape baskets")
    ax_a.plot(grid, 1e2 * fit_anchor.vol(grid), color=PALETTE["third"],
              lw=1.5, label="absolute anchors")
    ax_a.plot(k_q, 1e2 * vols_q, "o", ms=3.0, color=PALETTE["data"], zorder=5)
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel("implied volatility (%)")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", f"a {1e2 * JUMP:.0f}-point overnight level jump")

    for fit, color, label in [
        (fit_data, PALETTE["data"], "data only"),
        (fit_basket, PALETTE["model"], "shape baskets"),
        (fit_anchor, PALETTE["third"], "absolute anchors"),
    ]:
        ax_b.plot(grid, 1e2 * (fit.vol(grid) - sigma_today(grid)),
                  color=color, lw=1.4, label=label)
    ax_b.axhline(0.0, color=PALETTE["ink"], lw=0.8)
    ax_b.axhline(-1e2 * JUMP, color=PALETTE["muted"], lw=0.8, ls=":")
    ax_b.annotate("yesterday's level", (-0.31, -1e2 * JUMP + 0.25),
                  fontsize=7.5, color=PALETTE["muted"])
    ax_b.axvspan(-BAND, BAND, color=PALETTE["band"], alpha=0.55, zorder=0)
    ax_b.set_xlabel("log-moneyness $k$")
    ax_b.set_ylabel("error vs today's truth (vol pts)")
    ax_b.legend(loc="lower right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "who lands on the lifted wing")

    figstyle.save(fig, "fig_flt_jump")

    # --- macros -------------------------------------------------------------
    k_deep = np.array([-LEGS[1]])
    err = {
        "Data": float(fit_data.vol(k_deep)[0] - sigma_today(k_deep)[0]),
        "Basket": float(fit_basket.vol(k_deep)[0] - sigma_today(k_deep)[0]),
        "Anchor": float(fit_anchor.vol(k_deep)[0] - sigma_today(k_deep)[0]),
    }
    atm_gap = float(fit_basket.vol(np.array([0.0]))[0]
                    - fit_data.vol(np.array([0.0]))[0])
    STORE.add("jump", "PriorJumpPts", num(1e2 * JUMP, 0),
              "overnight level jump (vol points)")
    STORE.add("jump", "PriorJumpBasketErrDeep", num(abs(1e2 * err["Basket"]), 2),
              "shape-basket fit |error| vs lifted truth at k=-0.30 (pts)")
    STORE.add("jump", "PriorJumpAnchorErrDeep", num(abs(1e2 * err["Anchor"]), 1),
              "absolute-anchor fit |error| vs lifted truth at k=-0.30 (pts)")
    STORE.add("jump", "PriorJumpDataErrDeep", num(abs(1e2 * err["Data"]), 1),
              "data-only fit |error| vs lifted truth at k=-0.30 (pts)")
    STORE.add("jump", "PriorJumpAtmGapBp", num(abs(1e4 * atm_gap), 1),
              "ATM gap between shape-basket and data-only fits (vol bp)")
    STORE.add("jump", "PriorJumpGateAtm", num(gates["level"], 2),
              "computed gate of the level row on the staged morning")
    STORE.add("jump", "PriorJumpGateRr", num(gates["rr_mod"], 2),
              "computed gate of the moderate-wing RR row")
    STORE.add("jump", "PriorJumpGateBfMod", num(gates["bf_mod"], 2),
              "computed gate of the moderate-wing BF row")
    STORE.add("jump", "PriorJumpGateRrDeep", num(gates["rr_deep"], 2),
              "computed gate of the deep-wing RR row")
    STORE.add("jump", "PriorJumpGateBfDeep", num(gates["bf_deep"], 2),
              "computed gate of the deep-wing BF row")
    STORE.add("jump", "PriorJumpSuppAtm", num(supp_atm, 1),
              "ATM quote support on the staged morning")
    return (f"deep errors: data {1e2 * err['Data']:+.1f}, basket "
            f"{1e2 * err['Basket']:+.2f}, anchor {1e2 * err['Anchor']:+.1f} "
            f"pts; ATM gap {1e4 * atm_gap:.1f} bp; gates " +
            "/".join(f"{gates[n]:.2f}" for n in
                     ("level", "rr_mod", "bf_mod", "rr_deep", "bf_deep")))
