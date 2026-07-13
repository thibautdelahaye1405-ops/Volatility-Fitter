"""Figures, tables and worked-example macros for Note 05 (De-Americanization).

Everything runs the PRODUCTION machinery (volfit.core.american /
volfit.core.american_numba); nothing is re-implemented.

(1) The early-exercise-premium bias: pricing American CALLS on a 6%-dividend
    stock at a known 25% vol and Black-inverting the American price *as if
    European* over-states the implied vol; de-Americanization recovers 25%.
(2) A fully numeric worked example at one ITM strike (macros: American /
    European tree prices, EEP, naive IV, recovered IV).
(3) Numba kernel vs NumPy fallback timing on a wide chain. Both paths go
    through the PUBLIC `deamericanize_batch` dispatch — identical static
    screens, identical drift-floor bracket — with the NumPy leg timed by
    forcing the fallback (`NUMBA_AVAILABLE = False`). Before any number is
    written the two result arrays must agree: identical finite/NaN lanes and
    max |sigma diff| below tree rounding, else this generator RAISES (a timed
    all-NaN path once produced a fictitious 218x headline; never again).
    CPU model, thread count, warm-up policy and repetition count are recorded
    in deam_numbers.json.

Outputs:
  fig_deam_bias.pdf   naive (biased) vs de-Am implied vol across strikes
  fig_deam_eep.pdf    the early-exercise premium (American - European CALL)
  deam_tables.tex     \\input-able macros
  deam_numbers.json   machine-readable numbers + benchmark provenance
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))  # shared figure style (STYLE_GUIDE.md section 6)

from style import PALETTE, save, setup  # noqa: E402

from volfit.core import american_numba  # noqa: E402
from volfit.core.american import (  # noqa: E402
    BATCH_BISECTIONS,
    DEFAULT_BATCH_STEPS,
    binomial_price,
    deamericanize,
    deamericanize_batch,
)
from volfit.core.black import implied_total_variance  # noqa: E402

setup()
TEAL, RUST, SLATE = PALETTE["teal"], PALETTE["rust"], PALETTE["muted"]

#: Timing repetitions per path (fastest is reported) and the agreement gate.
TIMING_REPS = 5
AGREE_TOL = 1e-9  # kernel mirrors the NumPy bracketing exactly; observed 0.0
MIN_FINITE_FRAC = 0.5  # a benchmark that mostly returns NaN is not a benchmark


def bias_figures():
    """Panels (a)/(b): the naive-inversion bias and the EEP, American CALLS."""
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
    save(fig, OUT / "fig_deam_bias.pdf")

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(strikes, eep, color=TEAL)
    ax.fill_between(strikes, eep, color=TEAL, alpha=0.12)
    ax.set_xlabel("strike $K$")
    ax.set_ylabel("early-exercise premium")
    ax.set_title("American $-$ European call price", fontsize=10)
    save(fig, OUT / "fig_deam_eep.pdf")

    max_bias_bp = float(np.nanmax(100 * (naive - deam)) * 100)
    return max_bias_bp


def worked_example():
    """One strike of the bias experiment, fully numeric (note section 5).

    ITM call K = 90 on the same (s, t, r, q, sigma) = (100, 0.5, 2%, 6%, 25%)
    setup: tree prices at the scalar depth, the EEP, the naive Black IV of the
    American price, and the recovered de-Americanized vol.
    """
    s, t, r, q, sig, k = 100.0, 0.5, 0.02, 0.06, 0.25, 90.0
    am = binomial_price(True, s, k, t, sig, r, q, american=True)
    eu = binomial_price(True, s, k, t, sig, r, q, american=False)
    # Naive: invert the AMERICAN price through the analytic European Black
    # formula (production's inversion), in normalized forward units.
    f = s * float(np.exp((r - q) * t))
    d = float(np.exp(-r * t))
    logm = float(np.log(k / f))
    w = implied_total_variance(np.array([logm]), np.array([am / (d * f)]))[0]
    naive_iv = float(np.sqrt(w / t))
    recovered = deamericanize(True, am, s, k, t, r, q)
    return {
        "strike": k, "american": am, "european": eu, "eep": am - eu,
        "naive_iv_pct": 100 * naive_iv, "recovered_iv_pct": 100 * recovered,
        "naive_bias_bp": 1e4 * (naive_iv - sig),
    }


def timing():
    """Numba kernel vs NumPy fallback through the SAME public dispatch.

    Chain: wide American puts priced by the production tree at a known vol.
    Both timed paths call `deamericanize_batch(is_call, prices, s, k, t, r, q)`
    verbatim; only `american_numba.NUMBA_AVAILABLE` differs, so bracketing,
    static screens and the drift-floor lower bracket are identical. Raises if
    the two paths disagree (NaN alignment or sigma drift) or if the chain
    mostly fails to invert — see module docstring.
    """
    s, t, r, q = 100.0, 0.5, 0.04, 0.0
    n = 300
    strikes = np.linspace(60, 160, n)
    is_call = np.zeros(n, dtype=bool)
    prices = np.array([binomial_price(False, s, float(k), t, 0.25, r, q, american=True)
                       for k in strikes])
    if not american_numba.NUMBA_AVAILABLE:
        raise RuntimeError("Numba unavailable: the kernel-vs-fallback table "
                           "cannot be generated on this machine.")

    def run(reps: int) -> tuple[float, np.ndarray]:
        best, out = None, None
        for _ in range(reps):
            t0 = time.perf_counter()
            out = deamericanize_batch(is_call, prices, s, strikes, t, r, q)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best, out

    # Warm-up (untimed): JIT-compile the kernel / first-touch the fallback.
    run(1)
    best_nb, out_nb = run(TIMING_REPS)
    american_numba.NUMBA_AVAILABLE = False  # force the NumPy fallback
    try:
        run(1)
        best_np, out_np = run(TIMING_REPS)
    finally:
        american_numba.NUMBA_AVAILABLE = True

    # Agreement gate: same finite lanes, same roots (to tree rounding).
    ok_nb, ok_np = np.isfinite(out_nb), np.isfinite(out_np)
    if not np.array_equal(ok_nb, ok_np):
        raise RuntimeError("kernel/fallback NaN lanes differ: %d vs %d finite"
                           % (ok_nb.sum(), ok_np.sum()))
    n_finite = int(ok_nb.sum())
    if n_finite < MIN_FINITE_FRAC * n:
        raise RuntimeError("only %d/%d quotes inverted — not a valid benchmark"
                           % (n_finite, n))
    max_diff = float(np.max(np.abs(out_nb[ok_nb] - out_np[ok_np]))) if n_finite else 0.0
    if max_diff > AGREE_TOL:
        raise RuntimeError(f"kernel/fallback sigma drift {max_diff:.3e} > {AGREE_TOL}")

    try:
        import numba
        threads = int(numba.get_num_threads())
    except Exception:  # pragma: no cover - numba just proved available
        threads = -1
    env = {
        "cpu": platform.processor(), "logical_cores": os.cpu_count(),
        "numba_threads": threads, "reps": TIMING_REPS,
        "warmup": "one untimed call per path (JIT compile excluded)",
        "path": "public deamericanize_batch dispatch, NumPy leg via "
                "NUMBA_AVAILABLE=False", "n_finite": n_finite,
        "max_sigma_diff": max_diff,
    }
    return 1e3 * best_np, 1e3 * best_nb, n, n_finite, env


def main():
    max_bias_bp = bias_figures()
    wex = worked_example()
    np_ms, nb_ms, n, n_finite, env = timing()
    speedup = np_ms / nb_ms

    L = ["% Auto-generated by gen_deam.py — do not edit."]
    L.append(r"\newcommand{\deammaxbias}{%.0f}" % max_bias_bp)
    L.append(r"\newcommand{\deamnumpyms}{%.1f}" % np_ms)
    L.append(r"\newcommand{\deamnumbams}{%.2f}" % nb_ms)
    L.append(r"\newcommand{\deamspeedup}{%.0f}" % speedup)
    L.append(r"\newcommand{\deamchainn}{%d}" % n)
    L.append(r"\newcommand{\deamchainfinite}{%d}" % n_finite)
    L.append(r"\newcommand{\deamthreads}{%d}" % env["numba_threads"])
    L.append(r"\newcommand{\deamsteps}{%d}" % DEFAULT_BATCH_STEPS)
    L.append(r"\newcommand{\deambisect}{%d}" % BATCH_BISECTIONS)
    # Worked example (note section 5): one ITM call, every number shown.
    L.append(r"\newcommand{\deamwexstrike}{%.0f}" % wex["strike"])
    L.append(r"\newcommand{\deamwexam}{%.4f}" % wex["american"])
    L.append(r"\newcommand{\deamwexeu}{%.4f}" % wex["european"])
    L.append(r"\newcommand{\deamwexeep}{%.4f}" % wex["eep"])
    L.append(r"\newcommand{\deamwexnaive}{%.2f}" % wex["naive_iv_pct"])
    L.append(r"\newcommand{\deamwexdeam}{%.2f}" % wex["recovered_iv_pct"])
    L.append(r"\newcommand{\deamwexbias}{%.0f}" % wex["naive_bias_bp"])
    (OUT / "deam_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "deam_numbers.json").write_text(json.dumps(
        {"max_bias_bp": max_bias_bp, "numpy_ms": np_ms, "numba_ms": nb_ms,
         "speedup": speedup, "n": n, "worked_example": wex,
         "benchmark_env": env}, indent=2), encoding="utf-8")
    print("max naive bias %.0f bp; numpy %.1f ms, numba %.2f ms, speedup %.0fx "
          "(%d/%d finite, max sigma diff %.1e, %d threads)"
          % (max_bias_bp, np_ms, nb_ms, speedup, n_finite, n,
             env["max_sigma_diff"], env["numba_threads"]))


if __name__ == "__main__":
    main()
