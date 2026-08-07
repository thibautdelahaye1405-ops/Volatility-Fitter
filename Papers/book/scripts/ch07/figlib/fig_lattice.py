"""Figure 7.3: the two-step hand tree, and how fast trees converge."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import figstyle
import tree
from figstyle import PALETTE
from macros import STORE, num

# The hand example of Section 7.3 (appendix 7.A): an American put.
S, K, SIGMA, T, R = 100.0, 105.0, 0.30, 0.5, 0.06
N_HAND = 2


def _hand_tree() -> dict[str, float]:
    """Every number of the two-step solve, computed the way the text walks it."""
    dt = T / N_HAND
    u = float(np.exp(SIGMA * np.sqrt(dt)))
    d = 1.0 / u
    p = float((np.exp(R * dt) - d) / (u - d))
    disc = float(np.exp(-R * dt))
    s_u, s_d = S * u, S * d
    s_uu, s_ud, s_dd = S * u * u, S, S * d * d
    pay = lambda s: max(K - s, 0.0)
    # American rollback
    cont_u = disc * (p * pay(s_uu) + (1.0 - p) * pay(s_ud))
    val_u = max(cont_u, pay(s_u))
    cont_d = disc * (p * pay(s_ud) + (1.0 - p) * pay(s_dd))
    val_d = max(cont_d, pay(s_d))
    cont_0 = disc * (p * val_u + (1.0 - p) * val_d)
    val_0 = max(cont_0, pay(S))
    # European twin: same recursion, no obstacle
    eu_u = cont_u
    eu_d = cont_d
    eu_0 = disc * (p * eu_u + (1.0 - p) * eu_d)
    return {
        "u": u, "d": d, "p": p, "disc": disc,
        "s_u": s_u, "s_d": s_d, "s_uu": s_uu, "s_ud": s_ud, "s_dd": s_dd,
        "pay_uu": pay(s_uu), "pay_ud": pay(s_ud), "pay_dd": pay(s_dd),
        "cont_u": cont_u, "val_u": val_u, "intr_u": pay(s_u),
        "cont_d": cont_d, "val_d": val_d, "intr_d": pay(s_d),
        "cont_0": cont_0, "val_0": val_0, "intr_0": pay(S),
        "eu_0": eu_0, "eu_d": eu_d, "prem": val_0 - eu_0,
    }


def fig_deam_tree() -> str:
    h = _hand_tree()

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # ---- (a) the lattice, drawn with its numbers
    xy = {"root": (0.0, 0.0), "up": (1.0, 1.0), "dn": (1.0, -1.0),
          "uu": (2.0, 2.0), "ud": (2.0, 0.0), "dd": (2.0, -2.0)}
    for a, b in (("root", "up"), ("root", "dn"), ("up", "uu"), ("up", "ud"),
                 ("dn", "ud"), ("dn", "dd")):
        ax_a.plot(*zip(xy[a], xy[b]), color=PALETTE["muted"], lw=0.9,
                  zorder=1)
    spots = {"root": S, "up": h["s_u"], "dn": h["s_d"], "uu": h["s_uu"],
             "ud": h["s_ud"], "dd": h["s_dd"]}
    vals = {"root": h["val_0"], "up": h["val_u"], "dn": h["val_d"],
            "uu": h["pay_uu"], "ud": h["pay_ud"], "dd": h["pay_dd"]}
    for name, (x, y) in xy.items():
        exercised = name == "dn"
        ax_a.plot([x], [y], "o", ms=16.5, mfc="white",
                  mec=PALETTE["data"] if exercised else PALETTE["model"],
                  mew=1.6 if exercised else 1.1, zorder=3)
        ax_a.annotate(f"{spots[name]:.2f}", (x, y), (x, y + 0.46),
                      ha="center", fontsize=7.0, color=PALETTE["muted"])
        ax_a.annotate(f"{vals[name]:.2f}", (x, y), (x, y),
                      ha="center", va="center", fontsize=6.4,
                      color=PALETTE["ink"], zorder=4)
    ax_a.annotate(f"exercise: intrinsic {h['intr_d']:.2f}\n"
                  f"beats continuation {h['cont_d']:.2f}",
                  xy=xy["dn"], xytext=(0.02, -2.5), fontsize=7.0,
                  color=PALETTE["data"],
                  arrowprops={"arrowstyle": "->", "color": PALETTE["data"],
                              "lw": 0.9})
    ax_a.annotate(f"$p={h['p']:.3f}$", (0.5, 0.62), ha="center",
                  fontsize=7.0, color=PALETTE["muted"])
    ax_a.annotate(f"$1-p={1.0 - h['p']:.3f}$", (0.5, -0.78), ha="center",
                  fontsize=7.0, color=PALETTE["muted"])
    ax_a.set_xlim(-0.8, 2.55)
    ax_a.set_ylim(-2.95, 2.75)
    ax_a.axis("off")
    figstyle.panel(ax_a, "a",
                   "the two-step American put (spot above, value below)")

    # ---- (b) convergence of the tree price in the step count
    a_ref = tree.crr_price(False, S, K, T, SIGMA, R, 0.0, n=tree.N_REF,
                           american=True)
    e_ref = tree.crr_price(False, S, K, T, SIGMA, R, 0.0, n=tree.N_REF,
                           american=False)
    # Even step counts only: the CRR odd/even sawtooth otherwise buries
    # the 1/N trend the panel is about.
    ns = np.unique(np.concatenate([np.arange(2, 64, 2),
                                   np.arange(64, 421, 6)]))
    a_err = np.empty(ns.size)
    e_err = np.empty(ns.size)
    p_err = np.empty(ns.size)
    for i, n in enumerate(ns):
        a_n = tree.crr_price(False, S, K, T, SIGMA, R, 0.0, n=int(n),
                             american=True)
        e_n = tree.crr_price(False, S, K, T, SIGMA, R, 0.0, n=int(n),
                             american=False)
        a_err[i] = abs(a_n - a_ref)
        e_err[i] = abs(e_n - e_ref)
        p_err[i] = abs((a_n - e_n) - (a_ref - e_ref))
    ax_b.loglog(ns, a_err, color=PALETTE["model"], lw=1.0,
                label="American price error")
    ax_b.loglog(ns, e_err, color=PALETTE["data"], lw=1.0, alpha=0.85,
                label="European price error")
    ax_b.loglog(ns, p_err, color=PALETTE["alt"], lw=1.0,
                label="error of the difference $A-E$")
    guide = a_err[np.argmin(np.abs(ns - 32))] * (32.0 / ns)
    ax_b.loglog(ns, guide, color=PALETTE["muted"], lw=0.8, ls=":",
                label=r"$1/N_t$ guide")
    ax_b.set_xlabel("tree steps $N_t$")
    ax_b.set_ylabel("absolute price error (dollars)")
    ax_b.legend(loc="lower left", fontsize=6.6)
    figstyle.panel(ax_b, "b", "both legs converge like $1/N_t$;"
                              " their difference is cleaner")

    figstyle.save(fig, "fig_deam_tree")

    i256 = int(np.argmin(np.abs(ns - 256)))
    STORE.add("lattice", "DeamTreeUpFactor", num(h["u"], 4),
              "hand tree: up factor exp(sigma sqrt(dt))")
    STORE.add("lattice", "DeamTreeDownFactor", num(h["d"], 4),
              "hand tree: down factor 1/u")
    STORE.add("lattice", "DeamTreeProbUp", num(h["p"], 4),
              "hand tree: risk-neutral up probability")
    STORE.add("lattice", "DeamTreeProbDown", num(1.0 - h["p"], 4),
              "hand tree: down probability 1 - p")
    STORE.add("lattice", "DeamTreeGrowth", num(float(np.exp(R * T / 2)), 4),
              "hand tree: one-step growth factor exp(r dt)")
    STORE.add("lattice", "DeamTreeStepDisc", num(h["disc"], 4),
              "hand tree: one-step discount factor exp(-r dt)")
    STORE.add("lattice", "DeamTreeSpotUp", num(h["s_u"], 2),
              "hand tree: spot at the up node")
    STORE.add("lattice", "DeamTreeSpotDown", num(h["s_d"], 2),
              "hand tree: spot at the down node")
    STORE.add("lattice", "DeamTreeSpotUU", num(h["s_uu"], 2),
              "hand tree: spot after two up moves")
    STORE.add("lattice", "DeamTreeSpotDD", num(h["s_dd"], 2),
              "hand tree: spot after two down moves")
    STORE.add("lattice", "DeamTreePayUD", num(h["pay_ud"], 2),
              "hand tree: terminal payoff at the middle node")
    STORE.add("lattice", "DeamTreePayDD", num(h["pay_dd"], 2),
              "hand tree: terminal payoff at the double-down node")
    STORE.add("lattice", "DeamTreeContUp", num(h["cont_u"], 2),
              "hand tree: continuation value at the up node")
    STORE.add("lattice", "DeamTreeContDown", num(h["cont_d"], 2),
              "hand tree: continuation value at the down node")
    STORE.add("lattice", "DeamTreeIntrDown", num(h["intr_d"], 2),
              "hand tree: intrinsic value at the down node")
    STORE.add("lattice", "DeamTreeRootAm", num(h["val_0"], 2),
              "hand tree: American value at the root")
    STORE.add("lattice", "DeamTreeRootEu", num(h["eu_0"], 2),
              "hand tree: European value at the root")
    STORE.add("lattice", "DeamTreeValDownEu", num(h["eu_d"], 2),
              "hand tree: European value at the down node")
    STORE.add("lattice", "DeamTreePremTwoStep", num(h["prem"], 2),
              "hand tree: the two-step premium A - E")
    STORE.add("lattice", "DeamConvAmErrCents",
              num(100.0 * a_err[i256], 2),
              "American price error at N_t=256 (cents)")
    STORE.add("lattice", "DeamConvPremErrCents",
              num(100.0 * p_err[i256], 2),
              "error of the difference A-E at N_t=256 (cents)")
    STORE.add("lattice", "DeamConvRatio",
              num(float(np.median(a_err[ns >= 64] / p_err[ns >= 64])), 0),
              "median ratio of American-leg to difference error, N_t>=64")
    return (f"hand root {h['val_0']:.2f} (eu {h['eu_0']:.2f}), "
            f"A-err@256 {a_err[i256]:.4f}")
