"""Figures and tables for Note 05 (De-Americanization).

(1) The early-exercise-premium bias: pricing an American put at a known vol and
    then Black-inverting it *as if European* over-states the implied vol; the
    de-Americanization recovers the true vol exactly.
(2) Numba kernel vs NumPy batch timing on a wide chain.

Outputs:
  fig_deam_bias.pdf   naive (biased) vs de-Am implied vol across strikes
  fig_deam_eep.pdf    the early-exercise premium
  deam_tables.tex     \\input-able macros
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

from volfit.core.american import (
    BATCH_BISECTIONS,
    DEFAULT_BATCH_STEPS,
    SIGMA_LO,
    _escrow,
    binomial_price,
    deamericanize,
    deamericanize_batch,
)
from volfit.core.american_numba import deamericanize_kernel, numba_available

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
TEAL, RUST, SLATE = "#0f766e", "#b91c1c", "#334155"


def bias_figures():
    # American calls on a dividend-paying stock: the textbook early-exercise case.
    s, t, r, q, sig = 100.0, 0.5, 0.02, 0.06, 0.25
    strikes = np.linspace(88, 120, 17)
    naive, deam, eep = [], [], []
    for k in strikes:
        am = binomial_price(True, s, k, t, sig, r, q, american=True)
        eu = binomial_price(True, s, k, t, sig, r, q, american=False)
        eep.append(am - eu)
        # naive European implied vol matching the AMERICAN price
        try:
            niv = brentq(
                lambda v: binomial_price(True, s, k, t, v, r, q, american=False) - am,
                0.02, 3.0, xtol=1e-8,
            )
        except ValueError:
            niv = np.nan
        naive.append(niv)
        deam.append(deamericanize(True, am, s, k, t, r, q))
    naive, deam, eep = map(np.array, (naive, deam, eep))

    fig, ax = plt.subplots()
    ax.axhline(100 * sig, color=SLATE, ls=":", label=r"true vol $25\%$")
    ax.plot(strikes, 100 * naive, color=RUST, label="naive (American as European)")
    ax.plot(strikes, 100 * deam, color=TEAL, ls="--", label="de-Americanized")
    ax.set_xlabel("strike $K$")
    ax.set_ylabel(r"implied volatility (%)")
    ax.set_title(r"American calls, dividend yield $6\%$: naive inversion biased up",
                 fontsize=10)
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_deam_bias.pdf")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(strikes, eep, color=TEAL)
    ax.fill_between(strikes, eep, color=TEAL, alpha=0.12)
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("early-exercise premium")
    ax.set_title("American $-$ European put price", fontsize=10)
    fig.savefig(OUT / "fig_deam_eep.pdf")
    plt.close(fig)

    max_bias_bp = float(np.nanmax(100 * (naive - deam)) * 100)
    return max_bias_bp


def timing():
    """Numba kernel vs NumPy batch on a wide chain of American puts."""
    s, t, r, q = 100.0, 0.5, 0.04, 0.0
    n = 300
    strikes = np.linspace(60, 160, n)
    is_call = np.zeros(n, dtype=bool)
    prices = np.array([binomial_price(False, s, float(k), t, 0.25, r, q, american=True)
                       for k in strikes])

    # NumPy batch
    def run_numpy():
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            deamericanize_batch(is_call, prices, s, strikes, t, r, q)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best

    # Numba kernel (precompute the escrow lattice constants)
    nb_ms = np.nan
    if numba_available():
        base, pv_step = _escrow(s, r, t, DEFAULT_BATCH_STEPS, None, None)
        dt_ = t / DEFAULT_BATCH_STEPS
        sqdt = float(np.sqrt(dt_))
        # warm up the JIT
        deamericanize_kernel(is_call, prices, strikes, base, pv_step, r, q,
                             dt_, sqdt, DEFAULT_BATCH_STEPS, BATCH_BISECTIONS, SIGMA_LO)

        def run_numba():
            best = None
            for _ in range(3):
                t0 = time.perf_counter()
                deamericanize_kernel(is_call, prices, strikes, base, pv_step, r, q,
                                     dt_, sqdt, DEFAULT_BATCH_STEPS, BATCH_BISECTIONS, SIGMA_LO)
                dd = time.perf_counter() - t0
                best = dd if best is None else min(best, dd)
            return best

        nb_ms = 1e3 * run_numba()
    np_ms = 1e3 * run_numpy()
    return np_ms, nb_ms, n


def main():
    max_bias_bp = bias_figures()
    np_ms, nb_ms, n = timing()
    speedup = (np_ms / nb_ms) if nb_ms == nb_ms else float("nan")

    L = ["% Auto-generated by gen_deam.py — do not edit."]
    L.append(r"\newcommand{\deammaxbias}{%.0f}" % max_bias_bp)
    L.append(r"\newcommand{\deamnumpyms}{%.1f}" % np_ms)
    L.append(r"\newcommand{\deamnumbams}{%.2f}" % nb_ms)
    L.append(r"\newcommand{\deamspeedup}{%.0f}" % speedup)
    L.append(r"\newcommand{\deamchainn}{%d}" % n)
    L.append(r"\newcommand{\deamsteps}{%d}" % DEFAULT_BATCH_STEPS)
    L.append(r"\newcommand{\deambisect}{%d}" % BATCH_BISECTIONS)
    (OUT / "deam_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "deam_numbers.json").write_text(json.dumps(
        {"max_bias_bp": max_bias_bp, "numpy_ms": np_ms, "numba_ms": nb_ms,
         "speedup": speedup, "n": n}, indent=2), encoding="utf-8")
    print("max naive bias %.0f bp; numpy %.1f ms, numba %.2f ms, speedup %.0fx"
          % (max_bias_bp, np_ms, nb_ms, speedup))


if __name__ == "__main__":
    main()
