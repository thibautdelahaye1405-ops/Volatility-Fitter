"""Generate the additional figures for the alternative lecture edition of Note 01.

Run from the repository root with the project virtual environment::

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lqd_lecture.py

The six benchmark panels used by both editions remain owned by ``gen_lqd.py``.
This script adds three deterministic, pedagogical views and a small macro file:

* ``fig_lqd_logistic_lecture.pdf`` -- quantile, density, and smile of the
  logistic cold start;
* ``fig_lqd_tail_map.pdf`` -- endpoint scale, critical moment, and Lee slope;
* ``fig_lqd_jacobian_timing.pdf`` -- measured analytic-vs-FD calibration time;
* ``lqd_lecture_tables.tex`` -- generated numbers used in the lecture prose.

The figures call the production LQD implementation; there is no local pricing
or tail reimplementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import expit, logit

from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_psi, lee_slopes
from volfit.models.lqd.quadrature import build_slice

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, callout, label_panel, save, setup  # noqa: E402


OUT = Path(__file__).resolve().parent
setup()


def logistic_walkthrough() -> dict[str, float]:
    """Plot the production cold-start family at one concrete scale."""

    scale = 0.078
    expiry = 0.5
    params = LQDParams(np.log(scale), np.log(scale), np.zeros(5))
    slice_ = build_slice(params)

    fig, axes = plt.subplots(1, 3, figsize=(8.0, 2.75))

    # A: normalized quantile.  Interpolation is only for plotting; production
    # strike inversion uses the slice's cubic Hermite method.
    u = np.linspace(0.003, 0.997, 700)
    z = logit(u)
    q = np.interp(z, slice_.z, slice_.q_z)
    axes[0].plot(u, q, color=PALETTE["teal"])
    axes[0].axhline(0.0, color=PALETTE["muted"], lw=0.8)
    u_atm = float(expit(slice_.strike_to_z(0.0)))
    axes[0].scatter([u_atm], [0.0], color=PALETTE["rust"], zorder=5)
    axes[0].set_xlabel(r"percentile $u$")
    axes[0].set_ylabel(r"log-return quantile $Q(u)$")
    label_panel(axes[0], "A")

    # B: the same law in density coordinates.
    x, density = slice_.density()
    mask = (x > -0.55) & (x < 0.45)
    axes[1].plot(x[mask], density[mask], color=PALETTE["teal"])
    axes[1].fill_between(x[mask], density[mask], color=PALETTE["teal"], alpha=0.12)
    axes[1].axvline(0.0, color=PALETTE["muted"], lw=0.8)
    axes[1].set_xlabel(r"log-forward return $x$")
    axes[1].set_ylabel(r"density $f_X(x)$")
    label_panel(axes[1], "B")

    # C: the option market's view of the same law.
    k = np.linspace(-0.28, 0.24, 180)
    iv = slice_.implied_vol(k, expiry)
    atm = float(slice_.implied_vol(0.0, expiry))
    axes[2].plot(k, 100.0 * iv, color=PALETTE["teal"])
    axes[2].scatter([0.0], [100.0 * atm], color=PALETTE["rust"], zorder=5)
    axes[2].set_xlabel(r"log-moneyness $k$")
    axes[2].set_ylabel("implied volatility (%)")
    label_panel(axes[2], "C")

    fig.subplots_adjust(wspace=0.42)
    save(fig, OUT / "fig_lqd_logistic_lecture.pdf")

    a_left, a_right = endpoint_scales(params)
    beta_left, beta_right = lee_slopes(params)
    return {
        "scale": scale,
        "expiry": expiry,
        "mu": slice_.mu,
        "atm_vol_pct": 100.0 * atm,
        "u_atm": u_atm,
        "a_left": a_left,
        "a_right": a_right,
        "beta_left": beta_left,
        "beta_right": beta_right,
        "martingale_error": slice_.martingale_check() - 1.0,
    }


def tail_map() -> None:
    """Show the exact endpoint-scale-to-Lee-slope maps used in production."""

    a = np.linspace(0.01, 0.995, 900)
    p_left = 1.0 / a
    p_right = 1.0 / a - 1.0
    beta_left = np.asarray(lee_psi(p_left))
    beta_right = np.asarray(lee_psi(p_right))

    numbers = json.loads((OUT / "lqd_numbers.json").read_text(encoding="utf-8"))
    svi = numbers["svi"]

    fig, axes = plt.subplots(1, 2, figsize=WIDE)

    axes[0].semilogy(a, p_left, color=PALETTE["blue"], label=r"left: $1/A_L$")
    axes[0].semilogy(a, p_right, color=PALETTE["amber"], label=r"right: $1/A_R-1$")
    axes[0].axvline(1.0, color=PALETTE["rust"], lw=1.1, ls="--")
    axes[0].set_xlim(0.0, 1.02)
    axes[0].set_ylim(1e-3, 2e2)
    axes[0].set_xlabel(r"endpoint scale $A$")
    axes[0].set_ylabel("last finite moment exponent")
    axes[0].legend(loc="upper right")
    label_panel(axes[0], "A")

    beta = chr(92) + "beta"
    axes[1].plot(
        a, beta_left, color=PALETTE["blue"], label="left wing $" + beta + "_L$"
    )
    axes[1].plot(
        a, beta_right, color=PALETTE["amber"], label="right wing $" + beta + "_R$"
    )
    axes[1].scatter(
        [svi["A_L"], svi["A_R"]],
        [svi["beta_L"], svi["beta_R"]],
        color=PALETTE["rust"],
        zorder=5,
        label="SPX-like fit",
    )
    axes[1].axhline(2.0, color=PALETTE["muted"], lw=0.8, ls=":")
    axes[1].set_xlim(0.0, 1.02)
    axes[1].set_ylim(0.0, 2.08)
    axes[1].set_xlabel(r"endpoint scale $A$")
    axes[1].set_ylabel("Lee slope $" + beta + "$")
    axes[1].legend(loc="upper left")
    callout(
        axes[1],
        r"finite-forward wall $A_R=1$",
        xy=(0.992, float(beta_right[-1])),
        xytext=(0.48, 1.55),
    )
    label_panel(axes[1], "B")

    fig.subplots_adjust(wspace=0.34)
    save(fig, OUT / "fig_lqd_tail_map.pdf")


def jacobian_timing() -> None:
    """Turn the generated timing table into a desk-readable comparison."""

    numbers = json.loads((OUT / "lqd_numbers.json").read_text(encoding="utf-8"))
    rows = numbers["timing"]
    orders = np.array([row["n_order"] for row in rows])
    analytic = np.array([row["t_analytic_ms"] for row in rows])
    finite_diff = np.array([row["t_fd_ms"] for row in rows])
    speedup = finite_diff / analytic

    fig, ax = plt.subplots(figsize=(6.9, 3.45))
    x = np.arange(orders.size)
    width = 0.34
    ax.bar(x - width / 2, analytic, width, color=PALETTE["teal"], label="analytic")
    ax.bar(x + width / 2, finite_diff, width, color=PALETTE["muted"], label="2-point FD")
    for i, ratio in enumerate(speedup):
        ax.text(
            x[i],
            max(analytic[i], finite_diff[i]) + 0.8,
            f"{ratio:.2f}x",
            ha="center",
            va="bottom",
            color=PALETTE["rust"],
            fontsize=9.5,
        )
    ax.set_xticks(x, [f"N={n}\nP={n + 1}" for n in orders])
    ax.set_ylabel("calibration time (ms)")
    ax.set_ylim(0.0, 43.0)
    ax.legend(loc="upper left")
    save(fig, OUT / "fig_lqd_jacobian_timing.pdf")


def write_macros(logistic: dict[str, float]) -> None:
    lines = [
        "% Auto-generated by Docs/notes/figures/gen_lqd_lecture.py -- do not edit.",
        rf"\newcommand{{\lqdlecturescale}}{{{logistic['scale']:.3f}}}",
        rf"\newcommand{{\lqdlectureexpiry}}{{{logistic['expiry']:.1f}}}",
        rf"\newcommand{{\lqdlecturemu}}{{{logistic['mu']:.6f}}}",
        rf"\newcommand{{\lqdlectureatm}}{{{logistic['atm_vol_pct']:.2f}}}",
        rf"\newcommand{{\lqdlectureuatm}}{{{logistic['u_atm']:.4f}}}",
        rf"\newcommand{{\lqdlectureAL}}{{{logistic['a_left']:.3f}}}",
        rf"\newcommand{{\lqdlectureAR}}{{{logistic['a_right']:.3f}}}",
        rf"\newcommand{{\lqdlecturebetaL}}{{{logistic['beta_left']:.4f}}}",
        rf"\newcommand{{\lqdlecturebetaR}}{{{logistic['beta_right']:.4f}}}",
        rf"\newcommand{{\lqdlecturemart}}{{{logistic['martingale_error']:.2e}}}",
    ]
    (OUT / "lqd_lecture_tables.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    logistic = logistic_walkthrough()
    tail_map()
    jacobian_timing()
    write_macros(logistic)
    print("Wrote lecture figures and macros to", OUT)


if __name__ == "__main__":
    main()
