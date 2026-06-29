"""Generate the figures and timing tables for Note 01 (the LQD model).

Run from the repo root with the project venv:

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lqd.py

Everything is deterministic and offline: the SVI-JW benchmark smile and the
bimodal "double-hat" event smile are both synthetic targets defined in closed
form, fitted with the production ``volfit`` LQD calibrator. Outputs (written
next to this script):

  fig_lqd_svi_fit.pdf        SVI-JW target vs 7-parameter LQD smile
  fig_lqd_svi_error.pdf      LQD implied-vol residual in vol bps
  fig_lqd_density.pdf        risk-neutral log-return density of the SVI fit
  fig_lqd_logq.pdf           log quantile density l(u) of the SVI fit
  fig_lqd_doublehat.pdf      bimodal event smile + N=12 LQD fit
  fig_lqd_doublehat_dens.pdf target vs LQD bimodal density
  lqd_tables.tex             \\input-able LaTeX tables (coeffs, diagnostics, timing)
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
from scipy.stats import norm

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.core.black import black_call, black_vega_sigma, implied_total_variance
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_slopes
from volfit.models.lqd.calibrate import (
    OPT_N_POINTS,
    _BARRIER_CENTER,
    _BARRIER_SCALE,
    _residuals,
    calibrate_slice,
    logistic_init,
)
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import build_slice

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


# ----------------------------------------------------------------- SVI target
def raw_svi_w(k: np.ndarray) -> np.ndarray:
    """Raw-SVI total variance for the note's SPX-like 6-month slice."""
    a, b, rho, m, sig = (
        0.010625,
        0.0728868987,
        -0.5,
        0.0583095189,
        0.1009950494,
    )
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sig**2))


def fit_svi():
    t = 0.5
    k = np.linspace(-0.35, 0.30, 25)
    w = raw_svi_w(k)
    res = calibrate_slice(k, w, t, n_order=6, reg_lambda=1e-6)
    # dense reporting grid
    kk = np.linspace(-0.45, 0.40, 400)
    iv_model = res.slice.implied_vol(kk, t)
    iv_target = np.sqrt(raw_svi_w(kk) / t)
    iv_quote = np.sqrt(w / t)
    iv_model_q = res.slice.implied_vol(k, t)
    return t, k, kk, iv_quote, iv_target, iv_model, iv_model_q, res


def svi_figs(t, k, kk, iv_quote, iv_target, iv_model, iv_model_q, res):
    # --- smile fit
    fig, ax = plt.subplots()
    ax.plot(kk, 100 * iv_target, color=SLATE, lw=2.2, label="SVI-JW target")
    ax.plot(kk, 100 * iv_model, color=TEAL, ls="--", label="LQD fit ($N{=}6$)")
    ax.scatter(k, 100 * iv_quote, s=22, color=RUST, zorder=5, label="quotes")
    ax.set_xlabel(r"log-moneyness $k=\log(K/F)$")
    ax.set_ylabel(r"implied volatility (\%)")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_lqd_svi_fit.pdf")
    plt.close(fig)

    # --- residual in vol bps at the quotes + on the calibration grid
    fig, ax = plt.subplots()
    err = 1e4 * (iv_model_q - iv_quote)
    ax.axhline(0, color="black", lw=0.8)
    ax.stem(k, err, linefmt=TEAL, markerfmt="o", basefmt=" ")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("LQD residual (vol bps)")
    fig.savefig(OUT / "fig_lqd_svi_error.pdf")
    plt.close(fig)

    # --- density
    x, f = res.slice.density()
    fig, ax = plt.subplots()
    sel = (x > -0.6) & (x < 0.6)
    ax.plot(x[sel], f[sel], color=TEAL)
    ax.fill_between(x[sel], f[sel], color=TEAL, alpha=0.12)
    ax.set_xlabel(r"log-forward return $X=\log(S_T/F_T)$")
    ax.set_ylabel(r"risk-neutral density $f_X$")
    fig.savefig(OUT / "fig_lqd_density.pdf")
    plt.close(fig)

    # --- log quantile density l(u) = log q(u)
    u = res.slice.u
    g = res.slice.dq_dz  # e^{g}
    # l(u) = g(u) - log(u(1-u))
    lu = np.log(g) - np.log(u * (1.0 - u))
    fig, ax = plt.subplots()
    sel = (u > 1e-3) & (u < 1 - 1e-3)
    ax.plot(u[sel], lu[sel], color=TEAL)
    ax.set_xlabel(r"quantile level $u$")
    ax.set_ylabel(r"log quantile density $\ell(u)=\log q(u)$")
    fig.savefig(OUT / "fig_lqd_logq.pdf")
    plt.close(fig)


# ----------------------------------------------------------------- double-hat
def doublehat_target(k: np.ndarray):
    """Closed-form mixture-of-two-normals call prices (note eq. mix_call)."""
    t = 30.0 / 365.0
    m1, m2, s = -0.10075573, 0.08924427, 0.05
    w = 0.5

    def comp(mi):
        return np.exp(mi + s**2 / 2) * norm.cdf((mi + s**2 - k) / s) - np.exp(
            k
        ) * norm.cdf((mi - k) / s)

    c = w * comp(m1) + w * comp(m2)
    return t, c


def fit_doublehat():
    k = np.linspace(-0.25, 0.25, 41)
    t, c = doublehat_target(k)
    w = implied_total_variance(k, c)
    res = calibrate_slice(k, w, t, n_order=12, reg_lambda=1e-7)
    return t, k, w, res


def doublehat_figs(t, k, w, res):
    kk = np.linspace(-0.30, 0.30, 400)
    iv_model = res.slice.implied_vol(kk, t)
    _, c_t = doublehat_target(kk)
    iv_target = np.sqrt(implied_total_variance(kk, c_t) / t)

    fig, ax = plt.subplots()
    ax.plot(kk, 100 * iv_target, color=SLATE, lw=2.2, label="bimodal target")
    ax.plot(kk, 100 * iv_model, color=TEAL, ls="--", label="LQD fit ($N{=}12$)")
    ax.scatter(k, 100 * np.sqrt(w / t), s=16, color=RUST, zorder=5, label="quotes")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"implied volatility (\%)")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_lqd_doublehat.pdf")
    plt.close(fig)

    # density: LQD vs true mixture density in X-space
    x, f = res.slice.density()
    m1, m2, s = -0.10075573, 0.08924427, 0.05
    true = 0.5 * norm.pdf(x, m1, s) + 0.5 * norm.pdf(x, m2, s)
    fig, ax = plt.subplots()
    sel = (x > -0.35) & (x < 0.35)
    ax.plot(x[sel], true[sel], color=SLATE, lw=2.2, label="mixture density")
    ax.plot(x[sel], f[sel], color=TEAL, ls="--", label="LQD density")
    ax.set_xlabel(r"log-forward return $X$")
    ax.set_ylabel(r"risk-neutral density $f_X$")
    ax.legend(frameon=False)
    fig.savefig(OUT / "fig_lqd_doublehat_dens.pdf")
    plt.close(fig)


# ----------------------------------------------------- analytic vs FD Jacobian
def jac_timing():
    """Fresh end-to-end timing: identical mid-fit least_squares run with the
    analytic Jacobian vs scipy's 2-point finite-difference Jacobian, at a range
    of model orders. Reproduces the ROADMAP perf #2 claim with new numbers."""
    t = 0.5
    rows = []
    for n_order in (6, 8, 10, 12):
        k = np.linspace(-0.35, 0.30, 25)
        w = raw_svi_w(k)
        sigma = np.sqrt(w / t)
        target_price = black_call(k, w)
        inv_vega = 1.0 / (black_vega_sigma(k, sigma, t) + 1e-4)
        sqrt_weights = np.ones_like(k)
        n_idx = np.arange(2, n_order + 1, dtype=float)
        reg = np.sqrt(1e-6) * np.where(n_idx >= 4, n_idx, 0.0)
        init = logistic_init(float(np.interp(0.0, k, w)), n_order=n_order).to_vector()
        args = (
            k, target_price, inv_vega, sqrt_weights, reg,
            None, None, 1e6, None, None,
            _BARRIER_CENTER, _BARRIER_SCALE, MID_ANCHOR_WEIGHT,
            None, None, None, None, OPT_N_POINTS,
        )

        def run(jac):
            best = None
            for _ in range(3):  # take the fastest of 3 to damp noise
                t0 = time.perf_counter()
                r = least_squares(
                    _residuals, init, jac=jac, args=args, method="trf",
                    xtol=1e-10, ftol=1e-10, gtol=1e-10, max_nfev=4000,
                )
                dt = time.perf_counter() - t0
                best = dt if best is None else min(best, dt)
            return best, r

        # warm up numba/jit-free but cached grids
        run(residual_jacobian)
        ta, ra = run(residual_jacobian)
        tf, rf = run("2-point")
        rows.append(
            dict(
                n_order=n_order,
                p=n_order + 1,
                t_analytic_ms=1e3 * ta,
                t_fd_ms=1e3 * tf,
                speedup=tf / ta,
                cost_analytic=float(ra.cost),
                cost_fd=float(rf.cost),
                nfev_analytic=int(ra.nfev),
                nfev_fd=int(rf.nfev),
            )
        )
    return rows


# ------------------------------------------------------------------- LaTeX out
def write_tables(svi_res, dh_res, t_svi, t_dh, timing):
    p = svi_res.params
    a_l, a_r = endpoint_scales(p)
    b_l, b_r = lee_slopes(p)
    h = atm_handles(svi_res.slice, t_svi)
    lines = []
    lines.append("% Auto-generated by Docs/notes/figures/gen_lqd.py — do not edit.")
    # --- code constants (so the note's prose and atlas cite the live defaults)
    lines.append(r"\newcommand{\lqdoptpts}{%d}" % OPT_N_POINTS)
    lines.append(r"\newcommand{\lqdbarriercenter}{%.2f}" % _BARRIER_CENTER)
    lines.append(r"\newcommand{\lqdbarrierscale}{%.1f}" % _BARRIER_SCALE)
    # --- SVI fit diagnostics
    lines.append(r"\newcommand{\lqdsviAL}{%.6f}" % a_l)
    lines.append(r"\newcommand{\lqdsviAR}{%.6f}" % a_r)
    lines.append(r"\newcommand{\lqdsvimu}{%.6f}" % svi_res.slice.mu)
    lines.append(r"\newcommand{\lqdsvibetaL}{%.6f}" % b_l)
    lines.append(r"\newcommand{\lqdsvibetaR}{%.6f}" % b_r)
    lines.append(r"\newcommand{\lqdsvimaxerr}{%.2f}" % (1e4 * svi_res.max_iv_error))
    lines.append(r"\newcommand{\lqdsvisigma}{%.2f}" % (100 * h.sigma0))
    lines.append(r"\newcommand{\lqdsviskew}{%.4f}" % h.skew)
    lines.append(r"\newcommand{\lqdsvicurv}{%.4f}" % h.curvature)
    lines.append(r"\newcommand{\lqdsvimart}{%.2e}" % (svi_res.slice.martingale_check() - 1.0))
    lines.append(r"\newcommand{\lqdsvinfev}{%d}" % svi_res.n_evaluations)
    # --- SVI coefficient table
    coef = [("L", p.L), ("R", p.R)] + [
        (f"a_{{{i + 2}}}", v) for i, v in enumerate(p.a)
    ]
    tbl = [r"\begin{tabular}{lr}", r"\toprule", r"Parameter & Value\\", r"\midrule"]
    for name, val in coef:
        tbl.append(rf"${name}$ & {val:+.8f}\\")
    tbl += [r"\bottomrule", r"\end{tabular}"]
    lines.append(r"\newcommand{\lqdsvicoefftable}{%s}" % " ".join(tbl))
    # --- double-hat
    lines.append(r"\newcommand{\lqddhmaxerr}{%.2f}" % (1e4 * dh_res.max_iv_error))
    al2, ar2 = endpoint_scales(dh_res.params)
    lines.append(r"\newcommand{\lqddhAL}{%.6f}" % al2)
    lines.append(r"\newcommand{\lqddhAR}{%.6f}" % ar2)
    # --- timing table
    tt = [
        r"\begin{tabular}{rrrrrr}",
        r"\toprule",
        r"$N$ & $P$ & analytic (ms) & FD (ms) & speed-up & $|\Delta\mathrm{cost}|$\\",
        r"\midrule",
    ]
    for r in timing:
        tt.append(
            rf"{r['n_order']} & {r['p']} & {r['t_analytic_ms']:.1f} & "
            rf"{r['t_fd_ms']:.1f} & {r['speedup']:.2f}$\times$ & "
            rf"{abs(r['cost_analytic'] - r['cost_fd']):.1e}\\"
        )
    tt += [r"\bottomrule", r"\end{tabular}"]
    lines.append(r"\newcommand{\lqdtimingtable}{%s}" % " ".join(tt))

    (OUT / "lqd_tables.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # also dump raw json for the record
    (OUT / "lqd_numbers.json").write_text(
        json.dumps(
            {
                "svi": {
                    "A_L": a_l, "A_R": a_r, "mu": svi_res.slice.mu,
                    "beta_L": b_l, "beta_R": b_r,
                    "max_iv_err_bp": 1e4 * svi_res.max_iv_error,
                    "nfev": svi_res.n_evaluations,
                    "coeffs": p.to_vector().tolist(),
                },
                "doublehat": {
                    "max_iv_err_bp": 1e4 * dh_res.max_iv_error,
                    "A_L": al2, "A_R": ar2,
                    "coeffs": dh_res.params.to_vector().tolist(),
                },
                "timing": timing,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main():
    print("Fitting SVI-JW benchmark ...")
    svi = fit_svi()
    svi_figs(*svi)
    t_svi, _, _, _, _, _, _, svi_res = svi

    print("Fitting double-hat event smile ...")
    t_dh, k_dh, w_dh, dh_res = fit_doublehat()
    doublehat_figs(t_dh, k_dh, w_dh, dh_res)

    print("Timing analytic vs finite-difference Jacobian ...")
    timing = jac_timing()
    for r in timing:
        print(
            f"  N={r['n_order']:2d}  analytic={r['t_analytic_ms']:6.1f} ms  "
            f"FD={r['t_fd_ms']:7.1f} ms  speedup={r['speedup']:.2f}x"
        )

    write_tables(svi_res, dh_res, t_svi, t_dh, timing)
    print("Wrote figures + lqd_tables.tex to", OUT)


if __name__ == "__main__":
    main()
