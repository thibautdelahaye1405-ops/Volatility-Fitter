"""Generate the two formula-only figures used by the alternative chapter."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq
from scipy.special import betaincc, ndtr


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "figures" / "ch02"
PALETTE = {
    "blue": "#2a78d6",
    "orange": "#eb6834",
    "green": "#1baf7a",
    "ink": "#1f2430",
    "muted": "#898781",
    "grid": "#e1e0d9",
}


def setup() -> None:
    plt.rcParams.update(
        {
            "font.family": "STIXGeneral",
            "mathtext.fontset": "stix",
            "font.size": 9,
            "axes.titlesize": 9,
            "axes.labelsize": 9,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.grid": True,
            "grid.color": PALETTE["grid"],
            "grid.linewidth": 0.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.edgecolor": "#b9b7b0",
            "axes.linewidth": 0.7,
            "legend.frameon": False,
            "figure.constrained_layout.use": True,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
        }
    )


def panel(ax, tag: str, title: str) -> None:
    ax.set_title(f"({tag})  {title}", loc="left", pad=5)


def tail_family() -> None:
    colors = [PALETTE["orange"], PALETTE["green"], PALETTE["blue"]]
    alphas = [0.0, 0.25, 0.5]
    labels = [r"$\alpha=0$", r"$\alpha=1/4$", r"$\alpha=1/2$"]
    fig, axes = plt.subplots(1, 3, figsize=(6.3, 2.25))

    x = np.linspace(0.05, 3.0, 400)
    z = np.linspace(0.05, 12.0, 400)
    k = np.geomspace(1.0, 100.0, 400)
    for alpha, color, label in zip(alphas, colors, labels):
        p = 1.0 / (1.0 - alpha)
        axes[0].plot(x, x**p, color=color, label=label)
        axes[1].plot(z, z ** (1.0 - alpha), color=color, label=label)
        exponent = (1.0 - 2.0 * alpha) / (1.0 - alpha)
        axes[2].loglog(k, k**exponent, color=color, label=label)

    axes[0].set_xlabel(r"tail distance $x$")
    axes[0].set_ylabel(r"$-\log\Pr(X>x)$ (normalized)")
    panel(axes[0], "a", "tail decay")

    axes[1].set_xlabel(r"log-odds distance $z$")
    axes[1].set_ylabel(r"extreme quantile $Q$ (normalized)")
    panel(axes[1], "b", "quantile growth")

    axes[2].set_xlabel(r"$|k|$")
    axes[2].set_ylabel(r"wing variance $w$ (normalized)")
    panel(axes[2], "c", "smile-wing growth")
    axes[2].legend(loc="upper left")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_tail_family.pdf")
    plt.close(fig)


def black_call(k: float, w: float) -> float:
    sw = math.sqrt(w)
    dp = -k / sw + 0.5 * sw
    dm = dp - sw
    return float(ndtr(dp) - math.exp(k) * ndtr(dm))


def logistic_call(k: float, s: float) -> float:
    normalizer = math.sin(math.pi * s) / (math.pi * s)
    z = (k - math.log(normalizer)) / s
    if z >= 0:
        ez = math.exp(-z)
        u = 1.0 / (1.0 + ez)
        upper_prob = ez / (1.0 + ez)
    else:
        ez = math.exp(z)
        u = ez / (1.0 + ez)
        upper_prob = 1.0 / (1.0 + ez)
    share = float(betaincc(1.0 + s, 1.0 - s, u))
    return share - math.exp(k) * upper_prob


def implied_w(k: float, price: float) -> float:
    intrinsic = max(1.0 - math.exp(k), 0.0)
    if price <= intrinsic + 1e-14:
        return 0.0
    objective = lambda logw: black_call(k, math.exp(logw)) - price
    return math.exp(brentq(objective, -24.0, 6.0, xtol=1e-13))


def calendar_global() -> None:
    scales = [0.08, 0.12, 0.17, 0.23]
    names = ["3m", "6m", "1y", "2y"]
    colors = [PALETTE["ink"], PALETTE["blue"], PALETTE["green"], PALETTE["orange"]]
    k_grid = np.linspace(-1.1, 1.1, 241)
    z_grid = np.linspace(-11.0, 11.0, 501)
    u_grid = 1.0 / (1.0 + np.exp(-z_grid))

    calls = []
    ledgers = []
    variances = []
    for s in scales:
        row = np.array([logistic_call(float(k), s) for k in k_grid])
        calls.append(row)
        variances.append(np.array([implied_w(float(k), float(c)) for k, c in zip(k_grid, row)]))
        ledgers.append(betaincc(1.0 + s, 1.0 - s, u_grid))

    for near, far in zip(calls[:-1], calls[1:]):
        if np.min(far - near) < -2e-12:
            raise RuntimeError("synthetic calls are not calendar ordered")
    for near, far in zip(ledgers[:-1], ledgers[1:]):
        if np.min(far - near) < -2e-12:
            raise RuntimeError("synthetic ledgers are not calendar ordered")

    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.55))
    for w, name, color in zip(variances, names, colors):
        axes[0].plot(k_grid, w, color=color, label=name)
    axes[0].set_xlabel(r"log-moneyness $k$")
    axes[0].set_ylabel(r"total variance $w(k)$")
    axes[0].legend(loc="upper right", ncol=2)
    panel(axes[0], "a", "the variance curves are stacked")

    for i, color in enumerate(colors[1:]):
        gap = ledgers[i + 1] - ledgers[i]
        axes[1].plot(z_grid, gap, color=color, label=f"{names[i + 1]} - {names[i]}")
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.7)
    axes[1].set_xlabel(r"log-odds rank $z$")
    axes[1].set_ylabel(r"adjacent ledger gap")
    axes[1].legend(loc="upper right")
    panel(axes[1], "b", "every ledger gap is nonnegative")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / "fig_calendar_global.pdf")
    plt.close(fig)


if __name__ == "__main__":
    setup()
    tail_family()
    calendar_global()
