"""Figures for Note 13 (Bayesian prior persistence).

(1) The universal activation gate gap = max(1 - obs/req, 0)^gamma.
(2) "Don't damp the signal": an overnight ATM jump is densely quoted (deficit
    zero at ATM, market wins) while the wings are unquoted (deficit total,
    prior holds them) -- built with the REAL build_prior_anchor +
    calibrate_slice prior block.
(3) Activation diagnostics: the strike-gap coverage deficit and the operator
    gate, both computed by the production builders on the same market.

  fig_prior_gate.pdf        activation gate vs observation precision
  fig_prior_nodamp.pdf      market-only vs prior-persisted fit
  fig_prior_activation.pdf  where the two mechanisms put the budget
  prior_tables.tex          \\input-able macros
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, label_panel, save, setup  # noqa: E402

from volfit.calib.operators import build_operator_prior  # noqa: E402
from volfit.calib.precision import activation_gap  # noqa: E402
from volfit.calib.prior import build_prior_anchor  # noqa: E402
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402
from volfit.models.svi_jw.svi import RawSVI  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()


def gate_fig():
    obs = np.linspace(0, 2, 300)
    req = 1.0
    fig, ax = plt.subplots(figsize=(6.9, 3.6))
    for gamma, c in [(0.5, PALETTE["amber"]), (1.0, PALETTE["teal"]),
                     (2.0, PALETTE["violet"])]:
        ax.plot(obs, activation_gap(obs, req, gamma), color=c,
                label=fr"$\gamma={gamma}$")
    ax.axvline(req, color=PALETTE["muted"], ls=":", label="required precision")
    ax.set_xlabel("observation precision / required")
    ax.set_ylabel(r"prior gate $\mathrm{gap}$")
    ax.set_title("Prior off where data is sufficient "
                 r"($\mathrm{obs}\geq\mathrm{req}$)")
    ax.legend()
    save(fig, OUT / "fig_prior_gate.pdf")


def nodamp_fig():
    t = 0.25
    # Yesterday's prior: calm 20% ATM, moderate skew.
    prior = RawSVI(a=0.018, b=0.05, rho=-0.45, m=0.04, sigma=0.11)
    # Today's market: ATM jumped to ~25% with steeper skew (a vol spike).
    today = RawSVI(a=0.030, b=0.07, rho=-0.55, m=0.05, sigma=0.10)

    # Only the ATM region is quoted today; the wings have no fresh quotes.
    k_q = np.linspace(-0.10, 0.10, 11)
    w_q = today.total_variance(k_q)

    market_only = calibrate_slice(k_q, w_q, t, n_order=6, reg_lambda=1e-6)

    target, unmet = build_prior_anchor(
        prior_w=lambda k: prior.total_variance(k),
        prior_tau=t, k_quotes=k_q, tau=t,
        total_budget=float(k_q.size),     # 100%-class budget
    )
    persisted = calibrate_slice(k_q, w_q, t, n_order=6, reg_lambda=1e-6,
                                prior_anchor=target)

    kk = np.linspace(-0.40, 0.34, 300)
    fig, ax = plt.subplots(figsize=(6.9, 4.0))
    ax.plot(kk, 100 * prior.implied_vol(kk, t), color=PALETTE["muted"], ls=":",
            label="prior (yesterday)")
    ax.plot(kk, 100 * market_only.slice.implied_vol(kk, t), color=PALETTE["rust"],
            ls="--", label="market-only fit (wings unpinned)")
    ax.plot(kk, 100 * persisted.slice.implied_vol(kk, t), color=PALETTE["teal"],
            label="prior-persisted fit")
    ax.scatter(k_q, 100 * np.sqrt(w_q / t), s=16, color="black", zorder=5,
               label="today's ATM quotes")
    ax.axvspan(-0.10, 0.10, color="black", alpha=0.04)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title("ATM follows the market jump; wings held by the prior")
    ax.legend(fontsize=9)
    save(fig, OUT / "fig_prior_nodamp.pdf")

    atm_market = 100 * np.sqrt(today.total_variance(0.0) / t)
    atm_prior = 100 * np.sqrt(prior.total_variance(0.0) / t)
    atm_persisted = 100 * persisted.slice.implied_vol(np.array([0.0]), t)[0]
    kw = -0.30
    wing_market_only = 100 * market_only.slice.implied_vol(np.array([kw]), t)[0]
    wing_persisted = 100 * persisted.slice.implied_vol(np.array([kw]), t)[0]
    wing_prior = 100 * prior.implied_vol(np.array([kw]), t)[0]
    return dict(atm_market=atm_market, atm_prior=atm_prior,
                atm_persisted=atm_persisted, wing_prior=wing_prior,
                wing_mo=wing_market_only, wing_ps=wing_persisted,
                unmet=unmet, prior=prior, k_q=k_q, target=target)


def activation_fig(d):
    """Both gating mechanisms on the no-damp regime, from production code."""
    tau = 0.5
    prior = RawSVI(a=0.036, b=0.10, rho=-0.45, m=0.04, sigma=0.11)
    k_q = np.linspace(-0.08, 0.08, 13)     # dense ATM quotes only

    fig, axes = plt.subplots(1, 2, figsize=WIDE,
                             gridspec_kw={"width_ratios": [1.25, 1.0]})

    # --- Panel A: strike-gap coverage deficit (weights per anchor).
    tgt, unmet = build_prior_anchor(
        prior_w=lambda k: prior.total_variance(k),
        prior_tau=tau, k_quotes=k_q, tau=tau,
        total_budget=float(k_q.size),
    )
    ax = axes[0]
    ax.axvspan(k_q.min(), k_q.max(), color="black", alpha=0.05)
    markerline, stemlines, baseline = ax.stem(tgt.k, tgt.weights)
    plt.setp(stemlines, color=PALETTE["teal"], linewidth=2.6)
    plt.setp(markerline, color=PALETTE["teal"], markersize=7)
    plt.setp(baseline, color=PALETTE["grid"], linewidth=0.8)
    ax.scatter(k_q, np.zeros_like(k_q), s=14, color="black", zorder=5,
               label="today's quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("strike-anchor weight")
    ax.set_title("Strike-gap: budget goes to the deficit")
    label_panel(ax, "A")
    ax.legend(loc="upper right", fontsize=9)
    ax.text(0.0, 0.94 * tgt.weights.max(),
            f"quoted band:\nzero anchors\n(unmet {100*unmet:.0f}%)",
            ha="center", va="top", fontsize=9.5, color=PALETTE["muted"])

    # --- Panel B: operator gate (quote support vs requirement -> gap).
    op, vs = build_operator_prior(
        lambda k: prior.total_variance(k), tau, tau, k_q, None,
        float(k_q.size), op_set=["ATM", "RR25", "BF25", "VarSwap"],
        bandwidth=0.03,
    )
    names, gaps, lams = [], [], []
    for diag in (op.diagnostics if op is not None else []):
        names.append(diag["operator"])
        gaps.append(diag["gap"])
        lams.append(diag.get("activeLambda", diag.get("active_lambda", 0.0)))
    if "ATM" not in names:                 # ATM gated off -> report gap 0
        names.insert(0, "ATM"); gaps.insert(0, 0.0); lams.insert(0, 0.0)
    names.append("VarSwap"); gaps.append(vs.gap); lams.append(vs.weight)

    ax = axes[1]
    colors = [PALETTE["muted"] if g <= 0 else PALETTE["rust"] for g in gaps]
    ax.bar(np.arange(len(names)), gaps, color=colors, alpha=0.9)
    ax.set_xticks(np.arange(len(names)))
    ax.set_xticklabels(names, fontsize=9.5)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel(r"gate $\mathrm{gap}$ (0 = off, 1 = full pull)")
    ax.set_title("ATM off, wings on", loc="right", fontsize=11.5)
    label_panel(ax, "B")
    for i, (g, lam) in enumerate(zip(gaps, lams)):
        note = "off" if g <= 0 else fr"$\lambda$={lam:.1f}"
        ax.text(i, g + 0.03, note, ha="center", fontsize=9,
                color=PALETTE["ink"])
    fig.tight_layout(w_pad=2.0)
    save(fig, OUT / "fig_prior_activation.pdf")
    print("activation: ops", list(zip(names, np.round(gaps, 2))),
          "| strike-gap unmet %.0f%%" % (100 * unmet))


def main():
    gate_fig()
    d = nodamp_fig()
    activation_fig(d)
    L = ["% Auto-generated by gen_prior.py — do not edit."]
    L.append(r"\newcommand{\priatmmarket}{%.1f}" % d["atm_market"])
    L.append(r"\newcommand{\priatmprior}{%.1f}" % d["atm_prior"])
    L.append(r"\newcommand{\priatmpersist}{%.1f}" % d["atm_persisted"])
    L.append(r"\newcommand{\priwingprior}{%.1f}" % d["wing_prior"])
    L.append(r"\newcommand{\priwingmo}{%.1f}" % d["wing_mo"])
    L.append(r"\newcommand{\priwingps}{%.1f}" % d["wing_ps"])
    L.append(r"\newcommand{\priunmet}{%.0f}" % (100 * d["unmet"]))
    (OUT / "prior_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("ATM: prior %.1f market %.1f persisted %.1f | wing: prior %.1f "
          "mkt-only %.1f persisted %.1f"
          % (d["atm_prior"], d["atm_market"], d["atm_persisted"],
             d["wing_prior"], d["wing_mo"], d["wing_ps"]))


if __name__ == "__main__":
    main()
