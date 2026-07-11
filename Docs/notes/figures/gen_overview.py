"""Figures for Note 00 (System Overview).

Builds a small synthetic but calendar-monotone SVI surface (four expiries),
fits a production LQD slice to each, and renders three panels that illustrate
the app's structural guarantees end to end:

  fig_ov_smiles.pdf      four fitted smiles vs log-moneyness
  fig_ov_stackedvar.pdf  stacked total variance, non-crossing at every k —
                         THE calendar-arbitrage check (the app's Stacked IV
                         tab); measured on independently fitted slices and
                         asserted, enforcement itself is Note 10
  fig_ov_densities.pdf   stacked risk-neutral densities (all >= 0)

Run from the repo root with the project venv.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from volfit.models.lqd.calibrate import calibrate_slice

OUT = Path(__file__).resolve().parent
plt.rcParams.update(
    {
        "figure.figsize": (7.2, 4.3),
        "font.size": 11,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "lines.linewidth": 1.8,
        "savefig.bbox": "tight",
        "savefig.dpi": 200,
    }
)
COLORS = ["#0f766e", "#2563eb", "#b45309", "#b91c1c"]


def svi_w(k, a, b, rho, m, sig):
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sig**2))


def surface():
    """Four expiries, total variance scaled so the term structure is monotone."""
    expiries = [1 / 12, 3 / 12, 6 / 12, 12 / 12]
    base = dict(b=0.075, rho=-0.5, m=0.05, sig=0.10)
    fits = []
    for t in expiries:
        # a-level grows ~linearly in T -> monotone ATM total variance
        a = 0.02 * t + 0.004
        k = np.linspace(-0.35, 0.30, 23)
        w = svi_w(k, a=a, **base)
        res = calibrate_slice(k, w, t, n_order=6, reg_lambda=1e-6)
        fits.append((t, k, w, res))
    return fits


def main():
    fits = surface()

    # --- smiles
    fig, ax = plt.subplots()
    for (t, k, w, res), c in zip(fits, COLORS):
        kk = np.linspace(-0.40, 0.35, 300)
        ax.plot(kk, 100 * res.slice.implied_vol(kk, t), color=c,
                label=fr"$T={t*12:.0f}$m")
        ax.scatter(k, 100 * np.sqrt(w / t), s=10, color=c, alpha=0.6)
    ax.set_xlabel(r"log-moneyness $k=\log(K/F)$")
    ax.set_ylabel(r"implied volatility (%)")
    ax.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "fig_ov_smiles.pdf")
    plt.close(fig)

    # --- stacked TOTAL VARIANCE: the actual calendar-arbitrage check.
    # For forward-normalized (mean-one) slices, no calendar arbitrage at fixed
    # log-moneyness k is EXACTLY w(k, T_{i+1}) >= w(k, T_i) for every k — the
    # curves must not cross (the app's Stacked IV tab shows this same view).
    # Stacked IV smiles carry no calendar content (sigma mixes w and the
    # clock), and ATM-only monotonicity is necessary but far from sufficient.
    # The slices here are fitted INDEPENDENTLY, so the dominance is measured,
    # not enforced (enforcement is Note 10's coupling); assert it holds on
    # the displayed grid before writing the figure.
    kk = np.linspace(-0.40, 0.35, 400)
    w_curves = [res.slice.implied_w(kk) for (_, _, _, res) in fits]
    min_gap = min(float(np.min(hi - lo))
                  for lo, hi in zip(w_curves[:-1], w_curves[1:]))
    assert min_gap > 0.0, (
        f"fitted slices cross in total variance: min gap = {min_gap:.2e}"
    )
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    for (t, *_), wc, c in zip(fits, w_curves, COLORS):
        ax.plot(kk, wc, color=c, label=fr"$T={t*12:.0f}$m")
    ax.set_xlabel(r"log-moneyness $k=\log(K/F_T)$")
    ax.set_ylabel(r"total variance $w(k,T)$")
    ax.set_title("Stacked total variance: non-crossing at every $k$"
                 " (no calendar arbitrage on the displayed grid)", fontsize=10)
    ax.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "fig_ov_stackedvar.pdf")
    plt.close(fig)
    print(f"stacked-variance min inter-expiry gap: {min_gap:.2e}")

    # --- stacked densities
    fig, ax = plt.subplots()
    for (t, k, w, res), c in zip(fits, COLORS):
        x, f = res.slice.density()
        sel = (x > -0.7) & (x < 0.7)
        ax.plot(x[sel], f[sel], color=c, label=fr"$T={t*12:.0f}$m")
        ax.fill_between(x[sel], f[sel], color=c, alpha=0.08)
    ax.set_xlabel(r"log-forward return $X=\log(S_T/F_T)$")
    ax.set_ylabel(r"risk-neutral density $f_X$")
    ax.set_title(r"All densities $\geq 0$ (no butterfly arbitrage)", fontsize=10)
    ax.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "fig_ov_densities.pdf")
    plt.close(fig)

    print("Wrote overview figures to", OUT)


if __name__ == "__main__":
    main()
