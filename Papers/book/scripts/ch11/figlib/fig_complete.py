"""F7: the universe completed -- skill, the withheld smile, and the audit.

Panel (a): per-dark-node reconstruction error against the baseline error
(log-log; the diagonal is 'no better than riding the prior').  Panel (b):
the withheld NVDA December node -- the real frozen quotes this node's
reconstruction never saw, against yesterday's baseline and the graph's
retargeted smile with its floored band.  Panel (c): the audit -- std of
the standardized dark-node errors under the overtrusting arm, the stated
precisions, and the stated precisions with the idiosyncratic floor.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
import universe
from figstyle import PALETTE, panel
from macros import STORE, num

import data3  # noqa: E402  (path installed by universe's import)
import data9  # noqa: E402
import fits  # noqa: E402
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402

NODE = ("NVDA", "2026-12-18")
RIDGE = 1e-6


def _retarget(k_quotes, w_target, t):
    """Refit the arbitrage-free family to the adjusted target curve."""
    n_eff = fits.lqd_effective_order(k_quotes.size, 16)
    res = calibrate_slice(
        np.asarray(k_quotes, float), np.asarray(w_target, float), t,
        n_order=n_eff, reg_lambda=RIDGE, reg_power=fits.LQD_RIDGE_POWER,
        coords="logistic",
    )
    return lambda kk: np.asarray(res.slice.implied_vol(np.asarray(kk), t))


def fig_gr_complete() -> str:
    post = universe.solve_morning()
    post_ot = universe.solve_morning(universe.OVERTRUST)
    nodes = universe.build()
    idx = universe.index_of()
    errs = universe.dark_errors(post)
    floor = universe.SCATTER_SD**2

    fig, axes = plt.subplots(
        1, 3, figsize=(6.3, 2.35),
        gridspec_kw={"width_ratios": [1.0, 1.25, 0.75]})

    # (a) skill scatter: graph error vs baseline error, log-log.
    ax = axes[0]
    ge = np.abs([e[1] for e in errs])
    be = np.abs([e[2] for e in errs])
    ax.loglog([2e-2, 20], [2e-2, 20], color=PALETTE["muted"], lw=0.8,
              ls=":")
    ax.loglog(be, ge, "o", color=PALETTE["model"], ms=5)
    worst = int(np.argmax(ge / np.maximum(be, 1e-9)))
    figstyle.callout(ax, "an idiosyncratic node", xy=(be[worst], ge[worst]),
                     xytext=(0.045, 3.2))
    ax.set_xlabel("baseline error (vol pts)")
    ax.set_ylabel("graph error (vol pts)")
    ax.set_xlim(2e-2, 20), ax.set_ylim(2e-2, 20)
    panel(ax, "a", "twelve dark nodes")

    # (b) the withheld December node.
    node = data3.node(*NODE)
    sm = data9.smile(*NODE)
    i = idx[NODE]
    un = nodes[i]
    theta_hat, theta_true = post.mean[i], un.theta_true
    band = float(np.sqrt(post.var[i] + floor))

    keep = (node.k >= -0.45) & (node.k <= 0.30)
    kq = node.k[keep]
    kk = np.linspace(kq.min(), kq.max(), 240)
    base_iv = sm.iv(kk) - theta_true / 100.0
    w_target = (sm.iv(node.k) + (theta_hat - theta_true) / 100.0) ** 2 \
        * node.t
    reco = _retarget(node.k, w_target, node.t)
    reco_iv = reco(kk)
    target_iv = sm.iv(kk) + (theta_hat - theta_true) / 100.0
    retarget_rms_bp = 1e4 * float(np.sqrt(np.mean(
        (reco(node.k) - (sm.iv(node.k) + (theta_hat - theta_true) / 100.0))
        ** 2)))

    ax = axes[1]
    ax.fill_between(kk, 100 * reco_iv - band, 100 * reco_iv + band,
                    color=PALETTE["band"], zorder=0,
                    label=r"$\pm1$ sd band")
    ax.plot(kk, 100 * base_iv, ls="--", color=PALETTE["alt"],
            label="yesterday (baseline)")
    ax.plot(kk, 100 * reco_iv, color=PALETTE["model"],
            label="graph reconstruction")
    ax.plot(kq, 100 * node.iv_mid[keep], "o", color=PALETTE["data"],
            ms=2.2, label="withheld quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied vol (%)")
    ax.legend(loc="upper right", fontsize=6.8)
    panel(ax, "b", "the withheld NVDA December node")

    # (c) the audit.
    z_ot = universe.audit_std(post_ot)
    z_stated = universe.audit_std(post)
    z_fl = [(n.theta_true - post.mean[j]) / np.sqrt(post.var[j] + floor)
            for j, n in enumerate(nodes) if not n.lit]
    z_floor = float(np.std(z_fl))

    ax = axes[2]
    xs = [0, 1, 2]
    vals = [z_ot, z_stated, z_floor]
    ax.bar(xs, vals, 0.55,
           color=[PALETTE["third"], PALETTE["data"], PALETTE["model"]])
    ax.axhline(1.0, color=PALETTE["ink"], lw=0.8, ls=":")
    ax.set_xticks(xs)
    ax.set_xticklabels(["over-\ntrust", "stated", "stated\n+ floor"],
                       fontsize=7.5)
    ax.set_ylabel(r"std of $\mathcal{Z}$ (dark nodes)")
    panel(ax, "c", "the audit")

    figstyle.save(fig, "fig_gr_complete")

    # --- macros -----------------------------------------------------------
    ge_rms = float(np.sqrt(np.mean(np.square([e[1] for e in errs]))))
    be_rms = float(np.sqrt(np.mean(np.square([e[2] for e in errs]))))
    STORE.add("complete", "GrRmsGraph", num(ge_rms, 2),
              "dark-node rms error of the graph posterior, vol pts")
    STORE.add("complete", "GrRmsBase", num(be_rms, 2),
              "dark-node rms error of riding the baseline, vol pts")
    STORE.add("complete", "GrAuditOver", num(z_ot, 1),
              "std(Z) under 25x overtrusted relation precisions")
    STORE.add("complete", "GrAuditStated", num(z_stated, 2),
              "std(Z) under stated precisions, no floor")
    STORE.add("complete", "GrAuditFloor", num(z_floor, 2),
              "std(Z) with the idiosyncratic floor added to the bands")
    STORE.add("complete", "GrNvdaDecPost", f"{theta_hat:+.2f}",
              "posterior innovation at the withheld NVDA December node")
    STORE.add("complete", "GrNvdaDecTrue", f"{theta_true:+.2f}",
              "true innovation at the withheld NVDA December node")
    STORE.add("complete", "GrNvdaDecBand", num(band, 2),
              "floored posterior sd at the withheld node, vol pts")
    STORE.add("complete", "GrRetargetRmsBp", num(retarget_rms_bp, 1),
              "rms gap between the retargeted smile and the shifted target,"
              " vol bp")
    STORE.add("complete", "GrNvdaDecQuotes", str(node.n_quotes),
              "prepared quote count at the withheld NVDA December node")

    # Attribution at the withheld node: every posterior point earned.
    obs = universe.observations()
    keys = list(obs)
    contrib = post.gains[i] * np.array([obs[k] for k in keys])
    from_nvda = sum(c for k, c in zip(keys, contrib) if k[0] == "NVDA")
    from_spy = sum(c for k, c in zip(keys, contrib) if k[0] == "SPY")
    res_part = float(theta_hat - contrib.sum())
    STORE.add("complete", "GrNvdaDecFromNvda", f"{from_nvda:+.2f}",
              "contribution of the two lit NVDA neighbours, vol pts")
    STORE.add("complete", "GrNvdaDecFromSpy", f"{from_spy:+.2f}",
              "contribution of the six lit index nodes, vol pts")
    STORE.add("complete", "GrNvdaDecFromRes", f"{res_part:+.2f}",
              "contribution routed through the sister's carried residual")

    # The idiosyncratic node the scatter panel calls out.
    STORE.add("complete", "GrCalmBase", num(be[worst], 2),
              "baseline error at the called-out idiosyncratic node")
    STORE.add("complete", "GrCalmGraph", num(ge[worst], 2),
              "graph error at the called-out idiosyncratic node")
    STORE.add("complete", "GrSkillBetter", str(int(np.sum(ge < be))),
              "dark nodes where the graph beats the baseline")
    STORE.add("complete", "GrSkillWorse", str(int(np.sum(ge >= be))),
              "dark nodes where riding the baseline would have been better")

    # The short dark NVDA node (the largest baseline error).
    j = idx[("NVDA", "2026-08-21")]
    STORE.add("complete", "GrShortDarkTrue", f"{nodes[j].theta_true:+.2f}",
              "true innovation at the dark 18-day NVDA node")
    STORE.add("complete", "GrShortDarkPost", f"{post.mean[j]:+.2f}",
              "posterior at the dark 18-day NVDA node")

    # The sister decomposition (the residual carried into a mark).
    s = idx[("sister", "2026-09-18")]
    contrib_s = post.gains[s] * np.array([obs[k] for k in keys])
    sys_part = float(contrib_s.sum())
    res_part_s = float(post.mean[s] - sys_part)
    STORE.add("complete", "GrSisterCarried", f"{universe.u_carried():+.2f}",
              "the sister's carried dislocation this morning, vol pts")
    STORE.add("complete", "GrSisterSepPost", f"{post.mean[s]:+.2f}",
              "posterior at the dark sister September node")
    STORE.add("complete", "GrSisterSepSys", f"{sys_part:+.2f}",
              "its lit-source (systematic) part")
    STORE.add("complete", "GrSisterSepTrue",
              f"{nodes[s].theta_true:+.2f}",
              "true innovation at the sister September node")
    return "universe completed"
