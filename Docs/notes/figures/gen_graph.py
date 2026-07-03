"""Figures and tables for Note 14 (graph smile-extrapolation).

Every figure is a real run of the production graph solver (build_graph /
build_increment_prior / posterior_update) on universes small enough that the
note can explain every node on the page:

  fig_graph_prop.pdf      full-width: a lit innovation propagating along a
                          calendar chain (posterior + credible band) and the
                          matching marginal-precision decay
  fig_graph_eta.pdf       reach of the innovation vs directed smoothness eta
  fig_graph_sixnode.pdf   the six-node case file of Section "case"
  fig_graph_backtest.pdf  the temporal leave-one-out verdict
                          (numbers from backend/backtest/FINDINGS_graph_loo.md)
  graph_tables.tex        \\input-able macros incl. the case-file table rows
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, callout, label_panel, save, setup  # noqa: E402

from volfit.graph.build import build_graph  # noqa: E402
from volfit.graph.posterior import posterior_update  # noqa: E402
from volfit.graph.prior import build_increment_prior  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()

# Headline numbers of the temporal leave-one-out backtest, as reported in
# backend/backtest/FINDINGS_graph_loo.md (full spike regime, 18 day-pairs,
# 4134 held-out nodes). They are measured offline, not regenerated here.
LOO_ATM_SKILL = {"R0": 37.0, "R1": 26.0}     # vol bps vs transported prior
LOO_WING_SKILL = {"R0": 3.0, "R1": 7.0}
LOO_ZETA_STD = {"R0": 0.72, "R1": 0.90}


# ------------------------------------------------------------------ universes
def calendar_chain(n: int = 8):
    """A one-name calendar chain with bidirectional unit trust."""
    tenors = ["1W", "1M", "2M", "3M", "6M", "9M", "1Y", "2Y"][:n]
    weights: dict[tuple[str, str], float] = {}
    for a, b in zip(tenors, tenors[1:]):
        weights[(a, b)] = 1.0   # b informs a
        weights[(b, a)] = 1.0   # a informs b
    return build_graph(tenors, weights), tenors


LIT_TENOR = 3  # the 3M node is the lit calibration


def solve_calendar(eta: float, kappa: float = 0.2):
    graph, tenors = calendar_chain()
    prior = build_increment_prior(graph, kappa=kappa, eta=eta)
    n = graph.n_nodes
    post = posterior_update(
        prior,
        np.zeros(n),                    # baseline: transported prior = no move
        np.full(n, 2.0),                # modest baseline precision (dark nodes)
        np.array([LIT_TENOR]),          # one lit node
        np.array([1.0]),                # unit innovation in one handle
        np.array([100.0]),              # tightly observed calibration
    )
    return graph, tenors, post


def six_node_graph():
    """The case-file universe: an index calendar, a sector ETF, two names."""
    nodes = ["SPX 1M", "SPX 3M", "SPX 6M", "XLK 3M", "AAPL 3M", "MSFT 3M"]
    weights = {
        # SPX calendar chain: high trust both ways.
        ("SPX 1M", "SPX 3M"): 1.00,
        ("SPX 3M", "SPX 1M"): 1.00,
        ("SPX 3M", "SPX 6M"): 1.00,
        ("SPX 6M", "SPX 3M"): 1.00,
        # Index <-> sector ETF: the ETF listens to the index far more than
        # the index listens back.
        ("XLK 3M", "SPX 3M"): 0.35,
        ("SPX 3M", "XLK 3M"): 0.08,
        # Names listen to their sector ETF first, the broad index second.
        ("AAPL 3M", "XLK 3M"): 0.55,
        ("MSFT 3M", "XLK 3M"): 0.55,
        ("AAPL 3M", "SPX 3M"): 0.22,
        ("MSFT 3M", "SPX 3M"): 0.22,
        # Weak feedback edges keep the chain irreducible.
        ("XLK 3M", "AAPL 3M"): 0.20,
        ("XLK 3M", "MSFT 3M"): 0.20,
        ("SPX 3M", "AAPL 3M"): 0.04,
        ("SPX 3M", "MSFT 3M"): 0.04,
    }
    return build_graph(nodes, weights), nodes


def solve_six_node():
    graph, nodes = six_node_graph()
    prior = build_increment_prior(graph, kappa=0.025, eta=9.0)
    post = posterior_update(
        prior,
        np.zeros(graph.n_nodes),
        # Names carry weaker baseline precision than the index nodes, so they
        # are allowed to listen more.
        np.array([0.18, 0.20, 0.18, 0.12, 0.08, 0.08]),
        np.array([1, 3]),               # lit: SPX 3M and XLK 3M
        np.array([1.0, 0.55]),          # their calibrated innovations
        np.array([240.0, 130.0]),
    )
    return graph, nodes, post


# ------------------------------------------------------------------ figures
def draw_propagation():
    _, tenors, post = solve_calendar(eta=40.0)
    idx = np.arange(len(tenors))
    lo, hi = post.credible_band(z_score=1.0)
    std = np.sqrt(post.marginal_variance)
    lit = int(post.observed[0])

    fig, axes = plt.subplots(
        1, 2, figsize=WIDE, gridspec_kw={"width_ratios": [1.4, 1.0]}
    )
    ax = axes[0]
    ax.fill_between(idx, lo, hi, color=PALETTE["teal"], alpha=0.16,
                    label=r"$\pm1\sigma$ band")
    ax.plot(idx, post.mean, "-o", color=PALETTE["teal"],
            label="posterior increment")
    ax.scatter([lit], [post.mean[lit]], s=95, color=PALETTE["rust"],
               zorder=6, label="lit calibration")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.8)
    ax.set_xticks(idx)
    ax.set_xticklabels(tenors)
    ax.set_xlabel("calendar node")
    ax.set_ylabel("increment in one smile handle")
    ax.set_title("A lit move travels, then fades")
    label_panel(ax, "A")
    ax.legend(loc="lower left")
    callout(ax, "dark nodes inherit a\nshrunk version of the move",
            xy=(5, post.mean[5]), xytext=(4.6, 1.35))

    ax = axes[1]
    ax.plot(idx, std, "-o", color=PALETTE["blue"])
    ax.scatter([lit], [std[lit]], s=85, color=PALETTE["rust"], zorder=6)
    ax.set_xticks(idx)
    ax.set_xticklabels(tenors)
    ax.set_xlabel("calendar node")
    ax.set_ylabel(r"posterior std $\sqrt{K^{+}_{ii}}$")
    ax.set_title("Uncertainty widens", loc="right")
    label_panel(ax, "B")
    ax.text(lit - 0.1, 1.30, "marginal\nvariance, never\nthe precision\ndiagonal",
            ha="center", va="center", fontsize=8.5, color=PALETTE["muted"])
    fig.tight_layout(w_pad=2.2)
    save(fig, OUT / "fig_graph_prop.pdf")
    return post


def draw_eta():
    fig, ax = plt.subplots(figsize=(6.9, 3.4))
    for eta, color in [(8.0, PALETTE["amber"]), (40.0, PALETTE["teal"]),
                       (200.0, PALETTE["violet"])]:
        _, tenors, post = solve_calendar(eta=eta)
        ax.plot(np.arange(len(tenors)), post.mean, "-o", color=color,
                label=fr"$\eta={eta:g}$")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.8)
    ax.set_xticks(np.arange(len(tenors)))
    ax.set_xticklabels(tenors)
    ax.set_xlabel("calendar node")
    ax.set_ylabel("posterior increment")
    ax.set_title("Directed smoothness controls the reach of a lit innovation")
    ax.legend(ncol=3, loc="upper right")
    callout(ax, "larger $\\eta$: unexplained neighbour\ndisagreement is more expensive,\nso the move travels farther",
            xy=(5.55, 0.46), xytext=(4.35, 0.66))
    save(fig, OUT / "fig_graph_eta.pdf")


def draw_six_node():
    graph, nodes, post = solve_six_node()
    pos = {
        "SPX 1M": (0.0, 0.8),
        "SPX 3M": (1.2, 0.8),
        "SPX 6M": (2.4, 0.8),
        "XLK 3M": (1.2, -0.05),
        "AAPL 3M": (0.35, -0.85),
        "MSFT 3M": (2.05, -0.85),
    }
    fig, ax = plt.subplots(figsize=(6.9, 4.2))
    ax.set_axis_off()
    for i, src in enumerate(nodes):
        for j, dst in enumerate(nodes):
            w = graph.kernel[i, j]
            if i != j and w > 1e-9:
                arrow = FancyArrowPatch(
                    pos[src], pos[dst], arrowstyle="-|>", mutation_scale=11,
                    lw=0.8 + 1.7 * w, color=PALETTE["muted"], alpha=0.36,
                    shrinkA=18, shrinkB=18,
                )
                ax.add_patch(arrow)
    observed = set(post.observed.tolist())
    for i, node in enumerate(nodes):
        x, y = pos[node]
        color = PALETTE["rust"] if i in observed else PALETTE["teal"]
        ax.scatter([x], [y], s=760, color=color, alpha=0.96,
                   edgecolor="white", linewidth=1.5, zorder=4)
        ticker, tenor = node.split()
        ax.text(x, y + 0.012, f"{ticker}\n{tenor}", ha="center", va="center",
                color="white", fontsize=8.6, fontweight="bold",
                linespacing=0.85, zorder=5)
        ax.text(x, y - 0.19,
                f"$z$={post.mean[i]:.2f}\nprec={post.marginal_precision[i]:.2f}",
                ha="center", va="top", fontsize=9.0, color=PALETTE["ink"],
                zorder=5)
    ax.text(0.0, 1.22, "lit", color=PALETTE["rust"], fontsize=10,
            fontweight="bold")
    ax.text(0.30, 1.22, "dark", color=PALETTE["teal"], fontsize=10,
            fontweight="bold")
    ax.text(0.75, 1.22, "edge thickness = kernel weight (arrow: informer $\\to$ informed)",
            color=PALETTE["muted"], fontsize=10)
    ax.set_xlim(-0.45, 2.85)
    ax.set_ylim(-1.25, 1.35)
    save(fig, OUT / "fig_graph_sixnode.pdf")
    return nodes, post


def draw_backtest():
    fig, axes = plt.subplots(
        1, 2, figsize=WIDE, gridspec_kw={"width_ratios": [1.25, 1.0]}
    )
    ax = axes[0]
    skill = np.array([LOO_ATM_SKILL["R0"], LOO_ATM_SKILL["R1"],
                      LOO_WING_SKILL["R0"], LOO_WING_SKILL["R1"]])
    colors = [PALETTE["teal"], PALETTE["teal"], PALETTE["blue"], PALETTE["blue"]]
    ax.bar(np.arange(4), skill, color=colors, alpha=0.9)
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.8)
    ax.set_xticks(np.arange(4))
    ax.set_xticklabels(["ATM\n$R{=}0$", "ATM\n$R{=}1$",
                        "wing\n$R{=}0$", "wing\n$R{=}1$"])
    ax.set_ylabel("skill vs transported prior (vol bps)")
    ax.set_xlabel("$R{=}0$ sticky-moneyness, $R{=}1$ sticky-strike", labelpad=8)
    ax.set_title("Leave-one-out skill")
    label_panel(ax, "A")
    for i, value in enumerate(skill):
        ax.text(i, value + 1.1, f"+{value:.0f}", ha="center", va="bottom",
                fontsize=10)

    ax = axes[1]
    z_std = np.array([LOO_ZETA_STD["R0"], LOO_ZETA_STD["R1"]])
    ax.bar([0, 1], z_std, color=[PALETTE["amber"], PALETTE["violet"]],
           alpha=0.9)
    ax.axhline(1.0, color=PALETTE["ink"], lw=1.0, ls="--")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["sticky\nmoneyness", "sticky\nstrike"])
    ax.set_ylim(0.0, 1.2)
    ax.set_ylabel("std of standardized residual $\\zeta$")
    ax.set_title("Uncertainty calibration")
    label_panel(ax, "B")
    ax.text(0.5, 1.03, "1.0 = perfectly calibrated", ha="center", va="bottom",
            fontsize=9.5, color=PALETTE["muted"])
    fig.tight_layout(w_pad=2.0)
    save(fig, OUT / "fig_graph_backtest.pdf")


def write_tables(chain_post, six_nodes, six_post):
    lit = int(chain_post.observed[0])
    far_decay = 100.0 * chain_post.mean[-1] / chain_post.mean[lit]
    std = np.sqrt(chain_post.marginal_variance)
    observed = set(six_post.observed.tolist())
    rows = [
        rf"{node} & {'lit' if i in observed else 'dark'} & "
        rf"{six_post.mean[i]:.3f} & {six_post.marginal_precision[i]:.2f} \\"
        for i, node in enumerate(six_nodes)
    ]
    L = [
        "% Auto-generated by gen_graph.py — do not edit.",
        r"\newcommand{\graphdecay}{%.0f}" % far_decay,
        r"\newcommand{\graphlitsd}{%.2f}" % std[lit],
        r"\newcommand{\graphfarsd}{%.2f}" % std[-1],
        r"\newcommand{\graphsixrows}{%",
        *rows,
        r"}",
    ]
    (OUT / "graph_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(
        "graph: chain decay lit->far %.0f%%; posterior std lit %.2f far %.2f"
        % (far_decay, std[lit], std[-1])
    )


def main():
    chain_post = draw_propagation()
    draw_eta()
    six_nodes, six_post = draw_six_node()
    draw_backtest()
    write_tables(chain_post, six_nodes, six_post)


if __name__ == "__main__":
    main()
