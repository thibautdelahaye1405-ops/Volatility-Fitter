"""Audit numbers for the coordinates edition of Note 01 (committee revision).

Run from the repository root with the project virtual environment::

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lqd_audit.py

Three measured blocks, every quoted number emitted as a macro so the note can
never disagree with its own figure again (the old timing table and timing
figure came from two different runs of two different generators):

* Jacobian timing — ONE interleaved measurement produces BOTH the table
  macro and ``fig_lqd_ref_timing.pdf``: median over ``N_REPS`` alternating
  analytic/finite-difference solves per order, inter-quartile range shown as
  whiskers, iteration counts reported.
* Chart equivalence — the running-example strip fitted in the "lr",
  "endpoint" and "logistic" charts; worst parameter / fit-quality / tail
  differences emitted (plus the stored 12-node live-fixture validation if
  its artifact ``lqd_chart_equivalence_live.json`` is present).
* Certification envelope — a compact rerun of the strike-space no-arbitrage
  battery of ``backend/tests/test_lqd_numerical_certification.py`` (same
  draw classes through the logistic chart), worst cases emitted.

Outputs: ``fig_lqd_ref_timing.pdf`` + ``lqd_audit_tables.tex``.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import matplotlib
import numpy as np

from volfit.calib.band import MID_ANCHOR_WEIGHT
from volfit.core.black import black_call, black_vega_sigma
from volfit.models.lqd.basis import LQDParams, endpoint_scales
from volfit.models.lqd.calibrate import (
    OPT_N_POINTS,
    _BARRIER_CENTER,
    _BARRIER_SCALE,
    _residuals,
    calibrate_slice,
    logistic_init,
)
from volfit.models.lqd.charts import build_chart
from volfit.models.lqd.jacobian import residual_jacobian
from volfit.models.lqd.quadrature import build_slice

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.optimize import least_squares  # noqa: E402

from gen_lqd_geometry import EXPIRY, QUOTE_K, quote_iv  # noqa: E402
from style import FULL, PALETTE, save, setup  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()

ORDERS = (6, 8, 10, 12)
N_REPS = 11  # timing repeats per (order, jacobian) pair, interleaved


# ------------------------------------------------------------------- timing
def _timing_args(n_order: int):
    w = quote_iv(EXPIRY) ** 2 * EXPIRY
    sigma = np.sqrt(w / EXPIRY)
    n_idx = np.arange(2, n_order + 1, dtype=float)
    return (
        QUOTE_K, black_call(QUOTE_K, w),
        1.0 / (black_vega_sigma(QUOTE_K, sigma, EXPIRY) + 1e-4),
        np.ones_like(QUOTE_K),
        np.sqrt(3e-8) * np.where(n_idx >= 4, n_idx**1.2, 0.0),
        None, None, 1e6, None, None, None,
        None, None,
        _BARRIER_CENTER, _BARRIER_SCALE, MID_ANCHOR_WEIGHT,
        None, None, None, None, OPT_N_POINTS,
    ), np.interp(0.0, QUOTE_K, w)


def time_jacobians() -> list[dict]:
    """One interleaved measurement per order: alternating analytic / FD
    solves so slow machine drift hits both estimators equally."""
    rows = []
    for n_order in ORDERS:
        args, w0 = _timing_args(n_order)
        init = logistic_init(float(w0), n_order=n_order).to_vector()

        def solve(jac):
            t0 = time.perf_counter()
            r = least_squares(_residuals, init, jac=jac, args=args,
                              method="trf", xtol=1e-10, ftol=1e-10,
                              gtol=1e-10, max_nfev=4000)
            return time.perf_counter() - t0, r

        solve(residual_jacobian)  # warm the cached grids once
        solve("2-point")
        t_a, t_f = [], []
        for _ in range(N_REPS):  # interleaved, never fastest-of-k
            t_a.append(solve(residual_jacobian)[0])
            t_f.append(solve("2-point")[0])
        _, ra = solve(residual_jacobian)
        _, rf = solve("2-point")
        rows.append(dict(
            n_order=n_order, p=n_order + 1,
            a_med=1e3 * float(np.median(t_a)),
            a_iqr=1e3 * float(np.subtract(*np.percentile(t_a, [75, 25]))),
            f_med=1e3 * float(np.median(t_f)),
            f_iqr=1e3 * float(np.subtract(*np.percentile(t_f, [75, 25]))),
            nfev_a=int(ra.nfev), nfev_f=int(rf.nfev),
            dcost=abs(float(ra.cost) - float(rf.cost)),
        ))
        print(f"  N={n_order:2d}  analytic {rows[-1]['a_med']:6.1f} ms  "
              f"FD {rows[-1]['f_med']:6.1f} ms  "
              f"x{rows[-1]['f_med'] / rows[-1]['a_med']:.2f}")
    return rows


def timing_figure(rows: list[dict]) -> None:
    """The SAME measurement drawn: median bars, IQR whiskers, ratio labels."""
    fig, ax = plt.subplots(figsize=FULL)
    x = np.arange(len(rows))
    wd = 0.36
    for i, (key, color, label) in enumerate(
        (("a_med", PALETTE["teal"], "analytic (one pass)"),
         ("f_med", PALETTE["rust"], "finite difference ($P{+}1$ rebuilds)"))
    ):
        vals = [r[key] for r in rows]
        errs = [0.5 * r[key.replace("med", "iqr")] for r in rows]
        ax.bar(x + (i - 0.5) * wd, vals, wd, color=color, label=label,
               yerr=errs, capsize=3,
               error_kw={"ecolor": PALETTE["ink"], "lw": 1.0})
    for xi, r in zip(x, rows):
        ax.text(xi, max(r["a_med"], r["f_med"]) * 1.06,
                f"{r['f_med'] / r['a_med']:.2f}$\\times$",
                ha="center", fontsize=10, color=PALETTE["ink"])
    ax.set_xticks(x, [f"$N={r['n_order']}$\n$P={r['p']}$" for r in rows])
    ax.set_ylabel("median fit wall time (ms)")
    ax.set_ylim(0, 1.28 * max(r["f_med"] for r in rows))
    ax.legend(loc="upper left")
    save(fig, OUT / "fig_lqd_ref_timing.pdf")


# --------------------------------------------------------- chart equivalence
def chart_equivalence() -> dict:
    """Fit the running-example strip in all three optimization charts."""
    iv = quote_iv(EXPIRY)
    w = iv * iv * EXPIRY
    fits = {
        c: calibrate_slice(QUOTE_K, w, EXPIRY, n_order=9, reg_lambda=3e-8,
                           reg_power=1.2, coords=c)
        for c in ("lr", "endpoint", "logistic")
    }
    lr, lo = fits["lr"], fits["logistic"]
    _, ar_lr = endpoint_scales(lr.params)
    _, ar_lo = endpoint_scales(lo.params)
    return dict(
        dtheta=float(np.max(np.abs(lo.params.to_vector() - lr.params.to_vector()))),
        derr_bp=abs(lo.max_iv_error - lr.max_iv_error) * 1e4,
        dar_rel=abs(ar_lo - ar_lr) / ar_lr,
        nfev={c: fits[c].n_evaluations for c in fits},
    )


# ------------------------------------------------- certification envelope
def _draw(rng, n_order, near_wall=False, wild=False) -> LQDParams:
    chart = build_chart(n_order, "logistic")
    n = np.arange(2, n_order + 1)
    psi = np.empty(n_order + 1)
    psi[0] = rng.uniform(-5.0, -0.5)
    psi[1] = rng.uniform(2.2, 5.0) if near_wall else rng.uniform(-6.0, 2.0)
    psi[2:] = (rng.normal(0.0, 0.9, n.size) / (n / 2.0) ** 2 if wild
               else rng.normal(0.0, 0.25, n.size) * (2.0 / n))
    return LQDParams.from_vector(chart.to_theta(psi))


def certification_envelope(n_each: int = 4) -> dict:
    """Compact rerun of the strike-space audit battery (worst cases)."""
    rng = np.random.default_rng(20260719)
    worst = dict(bounds=0.0, butterfly=0.0, digital=0.0, vs_fine=0.0)
    for n_order in (4, 6, 8, 12, 16):
        for kind in ({}, {"near_wall": True}, {"wild": True}):
            for _ in range(n_each):
                s = build_slice(_draw(rng, n_order, **kind))
                k_lo, k_hi = s.q_z[40], s.q_z[-40]
                k = np.linspace(k_lo, k_hi, 2001)[1:-1] + 1.2e-7
                c = s.call_price(k)
                lower = np.maximum(1.0 - np.exp(k), 0.0)
                worst["bounds"] = max(worst["bounds"], float(np.max(lower - c)),
                                      float(np.max(c - 1.0)))
                kc = np.linspace(k_lo, k_hi, 201)[1:-1] + 3.2e-8
                strike = np.exp(kc)
                for eps in (1e-3, 1e-2, 5e-2):
                    width = eps * strike
                    cl = s.call_price(np.log(strike - width))
                    cm = s.call_price(kc)
                    cr = s.call_price(np.log(strike + width))
                    worst["butterfly"] = max(
                        worst["butterfly"], -float(np.min(cl + cr - 2.0 * cm)))
                    win = np.abs(kc) <= 3.0
                    if win.any():
                        dig = (cm[win] - cr[win]) / width[win]
                        worst["digital"] = max(worst["digital"], float(
                            np.max(np.maximum(-dig, dig - 1.0))))
                fine = build_slice(s.params, n_points=32001)
                kk = rng.uniform(k_lo, k_hi, 200)
                worst["vs_fine"] = max(worst["vs_fine"], float(
                    np.max(np.abs(s.call_price(kk) - fine.call_price(kk)))))
    return worst


# ------------------------------------------------------------------- output
def _sci(x: float) -> str:
    """m x 10^e in ensuremath form (STYLE_GUIDE tiny-number convention)."""
    if x == 0.0:
        return r"\ensuremath{0}"
    e = int(np.floor(np.log10(abs(x))))
    return r"\ensuremath{%.1f\times10^{%d}}" % (x / 10.0**e, e)


def write_tables(timing, equiv, cert, live) -> None:
    lines = ["% Auto-generated by Docs/notes/figures/gen_lqd_audit.py - do not edit."]
    tt = [r"\begin{tabular}{rrrrrrr}", r"\toprule",
          r"$N$ & $P$ & analytic (ms) & FD (ms) & speed-up & its.\ (a/FD) & "
          r"$|\Delta\mathrm{cost}|$\\", r"\midrule"]
    for r in timing:
        tt.append(
            rf"{r['n_order']} & {r['p']} & {r['a_med']:.1f} $\pm$ {r['a_iqr']:.1f} & "
            rf"{r['f_med']:.1f} $\pm$ {r['f_iqr']:.1f} & "
            rf"{r['f_med'] / r['a_med']:.2f}$\times$ & "
            rf"{r['nfev_a']}/{r['nfev_f']} & {_sci(r['dcost'])}\\")
    tt += [r"\bottomrule", r"\end{tabular}"]
    lines.append(r"\newcommand{\lqdreftimingtable}{%s}" % " ".join(tt))
    lines.append(r"\newcommand{\lqdrefspeedmin}{%.2f}" % min(
        r["f_med"] / r["a_med"] for r in timing))
    lines.append(r"\newcommand{\lqdrefspeedmax}{%.2f}" % max(
        r["f_med"] / r["a_med"] for r in timing))
    lines.append(r"\newcommand{\lqdrefeqdtheta}{%s}" % _sci(equiv["dtheta"]))
    lines.append(r"\newcommand{\lqdrefeqerr}{%s}" % _sci(equiv["derr_bp"]))
    lines.append(r"\newcommand{\lqdrefeqar}{%s}" % _sci(equiv["dar_rel"]))
    lines.append(r"\newcommand{\lqdrefcertbounds}{%s}" % _sci(cert["bounds"]))
    lines.append(r"\newcommand{\lqdrefcertfly}{%s}" % _sci(cert["butterfly"]))
    lines.append(r"\newcommand{\lqdrefcertdig}{%s}" % _sci(cert["digital"]))
    lines.append(r"\newcommand{\lqdrefcertfine}{%s}" % _sci(cert["vs_fine"]))
    if live is not None:
        lines.append(r"\newcommand{\lqdreflivenodes}{%d}" % live["n_nodes"])
        lines.append(r"\newcommand{\lqdreflivedtheta}{%s}" % _sci(live["dtheta"]))
        lines.append(r"\newcommand{\lqdrefliveerr}{%s}" % _sci(live["derr_bp"]))
    (OUT / "lqd_audit_tables.tex").write_text("\n".join(lines) + "\n",
                                              encoding="utf-8")


def main() -> None:
    print("Timing (single interleaved run) ...")
    timing = time_jacobians()
    timing_figure(timing)
    print("Chart equivalence on the running example ...")
    equiv = chart_equivalence()
    print(f"  |dtheta|max {equiv['dtheta']:.2e}  derr {equiv['derr_bp']:.2e} bp")
    print("Certification envelope (compact battery) ...")
    cert = certification_envelope()
    print("  ", {k: f"{v:.2e}" for k, v in cert.items()})
    live_path = OUT / "lqd_chart_equivalence_live.json"
    live = json.loads(live_path.read_text()) if live_path.exists() else None
    write_tables(timing, equiv, cert, live)
    (OUT / "lqd_audit_numbers.json").write_text(
        json.dumps({"timing": timing, "equiv": {k: v for k, v in equiv.items()},
                    "cert": cert}, indent=1, default=str), encoding="utf-8")
    print("Wrote fig_lqd_ref_timing.pdf + lqd_audit_tables.tex to", OUT)


if __name__ == "__main__":
    main()
