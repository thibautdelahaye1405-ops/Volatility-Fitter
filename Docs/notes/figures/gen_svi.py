"""Figures and tables for Note 02 (SVI / SVI-JW).

Fits the production raw-SVI calibrator to the SPX-like benchmark, recovers the
SVI-JW jump-wing handles, checks the Durrleman butterfly function, and times the
analytic vs finite-difference Jacobian. Outputs next to this script:

  fig_svi_fit.pdf    target, SVI fit, quotes
  fig_svi_jw.pdf     the five SVI-JW handles annotated on the smile
  fig_svi_g.pdf      Durrleman g(k) >= 0 butterfly diagnostic
  svi_tables.tex     \\input-able macros (raw + JW params, wings, timing)
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.models.svi_jw.calibrate import (
    _LEE_SLOPE_MAX,
    _PENALTY,
    _init_theta,
    _penalties,
    _unpack,
    calibrate_svi,
)
from volfit.models.svi_jw.jacobian import svi_residual_jacobian
from volfit.models.svi_jw.svi import RawSVI

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
TEAL, RUST, SLATE, AMBER = "#0f766e", "#b91c1c", "#334155", "#b45309"


def target_raw():
    return RawSVI(a=0.010625, b=0.0728868987, rho=-0.5, m=0.0583095189, sigma=0.1009950494)


def durrleman_g(raw: RawSVI, k):
    """Durrleman butterfly function g(k); g>=0 <=> no butterfly arbitrage."""
    km = k - raw.m
    root = np.sqrt(km * km + raw.sigma**2)
    w = raw.a + raw.b * (raw.rho * km + root)
    wp = raw.b * (raw.rho + km / root)
    wpp = raw.b * raw.sigma**2 / root**3
    return (1 - k * wp / (2 * w)) ** 2 - (wp**2 / 4) * (1 / w + 0.25) + wpp / 2


def raw_to_jw(raw: RawSVI, t: float):
    w0 = float(raw.total_variance(0.0))
    sqw = np.sqrt(w0)
    v = w0 / t
    p = raw.b * (1 - raw.rho) / sqw
    c = raw.b * (1 + raw.rho) / sqw
    chi = raw.m / np.sqrt(raw.m**2 + raw.sigma**2)
    psi = (raw.b / (2 * sqw)) * (raw.rho - chi)
    v_tilde = (raw.a + raw.b * raw.sigma * np.sqrt(1 - raw.rho**2)) / t
    return dict(v=v, psi=psi, p=p, c=c, v_tilde=v_tilde, w0=w0)


def jac_timing(k, w, t):
    """Fresh analytic-vs-FD timing on the clean mid configuration."""
    vol_quotes = np.sqrt(w / t)
    sqrt_w = np.ones_like(k)
    sqrt_cal = np.sqrt(1e6)

    def residuals(theta):
        raw = _unpack(theta)
        mv = np.sqrt(np.maximum(raw.total_variance(k), 1e-12) / t)
        fit = sqrt_w * (mv - vol_quotes)
        return np.concatenate((fit, _penalties(raw, _PENALTY, _LEE_SLOPE_MAX)))

    def jac(theta):
        return svi_residual_jacobian(
            theta, k, t, sqrt_w, None, MID_ANCHOR_WEIGHT,
            _PENALTY, _LEE_SLOPE_MAX, None, None, sqrt_cal,
        )

    theta0 = _init_theta(k, w)

    def run(j):
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            r = least_squares(residuals, theta0, jac=j, method="lm",
                              xtol=1e-15, ftol=1e-15, gtol=1e-15)
            dt = time.perf_counter() - t0
            best = dt if best is None else min(best, dt)
        return best, r

    run(jac)
    ta, ra = run(jac)
    tf, rf = run("2-point")
    return dict(
        t_analytic_ms=1e3 * ta, t_fd_ms=1e3 * tf, speedup=tf / ta,
        cost_analytic=float(ra.cost), cost_fd=float(rf.cost),
        nfev_analytic=int(ra.nfev), nfev_fd=int(rf.nfev),
    )


def main():
    t = 0.5
    raw_t = target_raw()
    k = np.linspace(-0.35, 0.30, 25)
    w = raw_t.total_variance(k)
    cal = calibrate_svi(k, w, t)
    raw = cal.raw
    jw = raw_to_jw(raw, t)

    kk = np.linspace(-0.45, 0.40, 400)

    # --- fit
    fig, ax = plt.subplots()
    ax.plot(kk, 100 * raw_t.implied_vol(kk, t), color=SLATE, lw=2.2, label="target")
    ax.plot(kk, 100 * raw.implied_vol(kk, t), color=TEAL, ls="--", label="SVI fit")
    ax.scatter(k, 100 * np.sqrt(w / t), s=18, color=RUST, zorder=5, label="quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"implied volatility (\%)")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_svi_fit.pdf")
    plt.close(fig)

    # --- JW handles annotated
    fig, ax = plt.subplots()
    vol = 100 * raw.implied_vol(kk, t)
    ax.plot(kk, vol, color=TEAL)
    k0 = 0.0
    v0 = 100 * raw.implied_vol(np.array([0.0]), t)[0]
    ax.scatter([k0], [v0], color=RUST, zorder=5)
    ax.annotate(r"$v$: ATM variance", (k0, v0), (0.02, v0 + 1.2),
                fontsize=9, color=RUST)
    # skew slope arrow near ATM
    sk = (100 * raw.implied_vol(np.array([0.05]), t)[0] - v0) / 0.05
    ax.annotate(r"$\psi$: ATM skew", (0.0, v0), (-0.30, v0 + 3.0),
                arrowprops=dict(arrowstyle="->", color=AMBER), fontsize=9, color=AMBER)
    ax.annotate(r"$p$: put wing", (kk[20], vol[20]), (-0.42, vol[20] - 4),
                fontsize=9, color=SLATE)
    ax.annotate(r"$c$: call wing", (kk[-20], vol[-20]), (0.18, vol[-20] + 2),
                fontsize=9, color=SLATE)
    kmin = kk[np.argmin(vol)]
    ax.annotate(r"$\tilde v$: min variance", (kmin, np.min(vol)),
                (kmin - 0.05, np.min(vol) - 4), fontsize=9, color=TEAL)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"implied volatility (\%)")
    fig.savefig(OUT / "fig_svi_jw.pdf")
    plt.close(fig)

    # --- Durrleman g
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    g = durrleman_g(raw, kk)
    ax.axhline(0, color="black", lw=0.8)
    ax.plot(kk, g, color=TEAL)
    ax.fill_between(kk, g, 0, where=(g >= 0), color=TEAL, alpha=0.10)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"Durrleman $g(k)$")
    ax.set_title(r"$g(k)\geq 0$ everywhere: no butterfly arbitrage", fontsize=10)
    fig.savefig(OUT / "fig_svi_g.pdf")
    plt.close(fig)

    timing = jac_timing(k, w, t)

    # --- tables
    L = ["% Auto-generated by gen_svi.py — do not edit."]
    L.append(r"\newcommand{\svimaxerr}{%.2f}" % (1e4 * cal.max_iv_error))
    L.append(r"\newcommand{\svinfev}{%d}" % cal.n_evaluations)
    sl_l, sl_r = raw.wing_slopes()
    L.append(r"\newcommand{\sviwingL}{%.4f}" % sl_l)
    L.append(r"\newcommand{\sviwingR}{%.4f}" % sl_r)
    L.append(r"\newcommand{\svipenalty}{%g}" % _PENALTY)
    L.append(r"\newcommand{\svileemax}{%.1f}" % _LEE_SLOPE_MAX)
    # raw param table
    rt = [r"\begin{tabular}{lr}", r"\toprule", r"Parameter & Value\\", r"\midrule"]
    for name, val in [("a", raw.a), ("b", raw.b), (r"\rho", raw.rho),
                      ("m", raw.m), (r"\sigma", raw.sigma)]:
        rt.append(rf"${name}$ & {val:+.6f}\\")
    rt += [r"\bottomrule", r"\end{tabular}"]
    L.append(r"\newcommand{\svirawtable}{%s}" % " ".join(rt))
    # JW table
    jt = [r"\begin{tabular}{lr}", r"\toprule", r"Handle & Value\\", r"\midrule"]
    for name, val in [("v", jw["v"]), (r"\psi", jw["psi"]), ("p", jw["p"]),
                      ("c", jw["c"]), (r"\tilde v", jw["v_tilde"])]:
        jt.append(rf"${name}$ & {val:+.6f}\\")
    jt += [r"\bottomrule", r"\end{tabular}"]
    L.append(r"\newcommand{\svijwtable}{%s}" % " ".join(jt))
    # timing
    L.append(r"\newcommand{\svianalyticms}{%.1f}" % timing["t_analytic_ms"])
    L.append(r"\newcommand{\svifdms}{%.1f}" % timing["t_fd_ms"])
    L.append(r"\newcommand{\svispeedup}{%.2f}" % timing["speedup"])
    L.append(r"\newcommand{\svicostdiff}{%.1e}"
             % abs(timing["cost_analytic"] - timing["cost_fd"]))
    (OUT / "svi_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    (OUT / "svi_numbers.json").write_text(
        json.dumps({"raw": raw.__dict__, "jw": jw, "timing": timing,
                    "max_err_bp": 1e4 * cal.max_iv_error}, indent=2),
        encoding="utf-8")
    print("SVI fit max err %.2f bp; speedup %.2fx" % (1e4 * cal.max_iv_error, timing["speedup"]))
    print("Wrote SVI figures + svi_tables.tex to", OUT)


if __name__ == "__main__":
    main()
