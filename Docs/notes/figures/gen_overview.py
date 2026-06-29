"""Figures for Note 00 (System Overview).

Builds a small synthetic but calendar-monotone SVI surface (four expiries),
fits a production LQD slice to each, and renders three panels that illustrate
the app's structural guarantees end to end:

  fig_ov_smiles.pdf     four fitted smiles vs log-moneyness
  fig_ov_termvar.pdf    ATM total-variance term structure (non-decreasing)
  fig_ov_densities.pdf  stacked risk-neutral densities (all >= 0)

Run from the repo root with the project venv.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from volfit.models.lqd.atm import atm_handles
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
    ax.set_ylabel(r"implied volatility (\%)")
    ax.legend(frameon=False, ncol=2)
    fig.savefig(OUT / "fig_ov_smiles.pdf")
    plt.close(fig)

    # --- ATM total-variance term structure
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ts = [t for t, *_ in fits]
    w0 = [atm_handles(res.slice, t).w0 for (t, _, _, res) in fits]
    ax.plot(ts, w0, "-o", color="#0f766e")
    ax.set_xlabel(r"expiry $T$ (years)")
    ax.set_ylabel(r"ATM total variance $w_0=\sigma_0^2 T$")
    ax.set_title("Non-decreasing in $T$ (no calendar arbitrage)", fontsize=10)
    fig.savefig(OUT / "fig_ov_termvar.pdf")
    plt.close(fig)

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
