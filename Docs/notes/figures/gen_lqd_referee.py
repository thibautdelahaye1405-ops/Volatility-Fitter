"""Referee-evidence figures for the coordinates edition of Note 01.

Run from the repository root with the project virtual environment::

    .venv\\Scripts\\python.exe Docs\\notes\\figures\\gen_lqd_referee.py

The committee revision's evidence suite — every panel answers one referee
challenge with production code:

* ``fig_lqd_ref_tailfan.pdf``     -- tail-stability fans: jackknife / order /
  ridge / 1-bp noise / multi-start refits move the tail ladder while the
  liquid observables stay pinned (running example vs a live SPY node);
* ``fig_lqd_ref_lee.pdf``         -- how fast w(k)/|k| approaches the Lee
  limit; effective slopes at the 10- and 1-delta strikes marked;
* ``fig_lqd_ref_decouple.pdf``    -- a raw body mode drags both tail scales
  (a2 -> A factor e^{0.1}); the endpoint-chart body mode cannot;
* ``fig_lqd_ref_event_order.pdf`` -- the event case with a low-order
  comparator: what the extra modes actually buy;
* ``fig_lqd_ref_vegafloor.pdf``   -- the vega floor's effective weighting
  regime by maturity (strike- and maturity-dependent, as charged);
* ``lqd_referee_tables.tex``      -- macros for every quoted number.

The tail study itself runs through ``backend/lqd_tail_study.py`` (the same
protocol module the committee report cites); the live-SPY panel reads the
stored artifact ``tail_study_spy.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[2] / "backend"))

from volfit.core.black import black_vega_sigma, implied_total_variance  # noqa: E402
from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_slopes  # noqa: E402
from volfit.models.lqd.calibrate import _VEGA_FLOOR, calibrate_slice  # noqa: E402
from volfit.models.lqd.charts import build_chart  # noqa: E402

from lqd_tail_study import _delta_strike, run_study  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.stats import norm  # noqa: E402

from gen_lqd_geometry import (  # noqa: E402
    EXPIRY,
    QUOTE_K,
    fit_spx_case,
    mixture_call,
    quote_iv,
)
from style import FULL, PALETTE, WIDE, label_panel, save, setup  # noqa: E402

setup()

#: The fan observables, their display names, and the JSON keys.
FAN_KEYS = (
    ("aL", r"$A_L$"), ("aR", r"$A_R$"),
    ("betaL", r"$\beta_L$"), ("betaR", r"$\beta_R$"),
    ("vol_1d_put", r"$\sigma(1\Delta\,\mathrm{put})$"),
    ("vol_10d_put", r"$\sigma(10\Delta\,\mathrm{put})$"),
    ("varSwapVol", r"$\sigma_{\mathrm{VS}}$"),
)


def fan_values(study: dict, key: str) -> np.ndarray:
    vals = []
    for group in ("jackknife", "orders", "lambdas"):
        vals += [obs[key] for obs in study[group].values()]
    for group in ("noise", "multistart"):
        vals += [obs[key] for obs in study[group]]
    return np.asarray(vals, dtype=float)


def figure_tailfan(note_study: dict, spy_study: dict) -> dict:
    """Min-max fans relative to baseline, one row per observable."""
    fig, axes = plt.subplots(1, 2, figsize=WIDE, sharey=True)
    spreads = {}
    for ax, study, tag, letter in (
        (axes[0], note_study, "note", "A"),
        (axes[1], spy_study, "spy", "B"),
    ):
        y = np.arange(len(FAN_KEYS))[::-1]
        for yi, (key, _) in zip(y, FAN_KEYS):
            base = study["baseline"][key]
            vals = fan_values(study, key)
            rel = 100.0 * (vals / base - 1.0)
            lo, hi = float(rel.min()), float(rel.max())
            color = PALETTE["rust"] if key in ("aL", "aR", "betaL", "betaR") \
                else PALETTE["teal"]
            ax.plot([lo, hi], [yi, yi], color=color, lw=5, alpha=0.75,
                    solid_capstyle="butt")
            ax.plot(0.0, yi, marker="o", color=PALETTE["ink"], ms=5, zorder=5)
            spreads[f"{tag}_{key}"] = hi - lo
        ax.axvline(0.0, color=PALETTE["muted"], lw=0.8)
        ax.set_yticks(np.arange(len(FAN_KEYS))[::-1],
                      [name for _, name in FAN_KEYS])
        ax.set_xlabel("refit value vs baseline (%)")
        label_panel(ax, letter)
    save(fig, OUT / "fig_lqd_ref_tailfan.pdf")
    return spreads


def figure_lee(spx) -> dict:
    """w(k)/|k| against the Lee limits, with the delta strikes marked."""
    s = spx.slice
    beta_l, beta_r = lee_slopes(spx.params)
    fig, ax = plt.subplots(figsize=FULL)
    out = {}
    for sign, beta, color, label in (
        (-1, beta_l, PALETTE["rust"], "left wing  ($k<0$)"),
        (+1, beta_r, PALETTE["teal"], "right wing ($k>0$)"),
    ):
        kk = sign * np.geomspace(0.05, 8.0, 300)
        # Draw only where double-precision Black inversion still resolves the
        # option price — the curve ENDS before it reaches the Lee limit, which
        # is the figure's point.
        price = np.asarray(s.call_price(kk), dtype=float)
        if sign < 0:
            price = price - (1.0 - np.exp(kk))  # put value
        alive = price > 1e-13
        kk, ratio = kk[alive], (
            np.asarray(s.implied_w(kk[alive]), dtype=float) / np.abs(kk[alive]))
        ax.plot(np.abs(kk), ratio, color=color, label=label)
        ax.axhline(beta, color=color, ls=":", lw=1.2)
        side = "put" if sign < 0 else "call"
        for delta, tag in ((0.10, "10d"), (0.01, "1d")):
            k_d = _delta_strike(s, EXPIRY, delta, sign)
            r_d = float(s.implied_w(np.asarray([k_d]))[0]) / abs(k_d)
            ax.plot(abs(k_d), r_d, marker="D", color=color, ms=6, zorder=6)
            out[f"ratio_{tag}_{side}"] = r_d / beta
    ax.set_xscale("log")
    ax.set_xlabel(r"$|k|$ (log scale)")
    ax.set_ylabel(r"effective slope $w(k)/|k|$")
    ax.legend(loc="upper right")
    save(fig, OUT / "fig_lqd_ref_lee.pdf")
    return out


def figure_decouple(spx) -> dict:
    """A raw a2 bump vs the endpoint-chart b2 bump: who moves the tails."""
    theta = spx.params.to_vector()
    n_order = spx.params.order
    chart = build_chart(n_order, "endpoint")
    bump = 0.10
    kk = np.linspace(-0.9, 0.9, 400)
    base_iv = spx.slice.implied_vol(kk, EXPIRY)
    _, ar0 = endpoint_scales(spx.params)
    al0, _ = endpoint_scales(spx.params)

    raw = theta.copy()
    raw[2] += bump
    phi = chart.from_theta(theta)
    phi[2] += bump
    body = chart.to_theta(phi)

    fig, axes = plt.subplots(1, 2, figsize=WIDE, sharey=True)
    out = {}
    for ax, vec, letter, title_key in (
        (axes[0], raw, "A", "raw"),
        (axes[1], body, "B", "endpoint"),
    ):
        from volfit.models.lqd.quadrature import build_slice
        pert = build_slice(LQDParams.from_vector(vec))
        d_iv = 1e4 * (pert.implied_vol(kk, EXPIRY) - base_iv)
        ax.plot(kk, d_iv, color=PALETTE["teal"])
        ax.axhline(0.0, color=PALETTE["muted"], lw=0.8)
        al1, ar1 = endpoint_scales(LQDParams.from_vector(vec))
        out[f"{title_key}_alfac"] = al1 / al0
        out[f"{title_key}_arfac"] = ar1 / ar0
        ax.text(0.03, 0.94,
                rf"$A_L\times{al1 / al0:.3f}$, $A_R\times{ar1 / ar0:.3f}$",
                transform=ax.transAxes, fontsize=10.5, va="top",
                color=PALETTE["ink"])
        ax.set_xlabel(r"log-moneyness $k$")
        label_panel(ax, letter)
    axes[0].set_ylabel(r"$\Delta\sigma$ (vol bp)")
    save(fig, OUT / "fig_lqd_ref_decouple.pdf")
    return out


def figure_event_order() -> dict:
    """Event case with a low-order comparator (what the modes buy)."""
    expiry = 24.0 / 365.0
    weights = np.array([0.56, 0.44])
    raw_means = np.array([-0.075, 0.085])
    sigmas = np.array([0.052, 0.047])
    shift = -np.log(np.sum(weights * np.exp(raw_means + 0.5 * sigmas**2)))
    means = raw_means + shift
    quote_k = np.linspace(-0.22, 0.22, 37)
    target_w = implied_total_variance(
        quote_k, mixture_call(quote_k, weights, means, sigmas))
    hi = calibrate_slice(quote_k, target_w, expiry, n_order=16, reg_lambda=1e-11)
    lo = calibrate_slice(quote_k, target_w, expiry, n_order=6, reg_lambda=1e-11)

    dense_k = np.linspace(-0.25, 0.25, 500)
    dense_iv = np.sqrt(implied_total_variance(
        dense_k, mixture_call(dense_k, weights, means, sigmas)) / expiry)

    fig, (ax_s, ax_d) = plt.subplots(1, 2, figsize=WIDE)
    ax_s.plot(dense_k, 100 * dense_iv, color=PALETTE["ink"], lw=2.2,
              label="two-regime target")
    ax_s.plot(dense_k, 100 * hi.slice.implied_vol(dense_k, expiry),
              color=PALETTE["teal"], ls="--", label="$N=16$ fit")
    ax_s.plot(dense_k, 100 * lo.slice.implied_vol(dense_k, expiry),
              color=PALETTE["amber"], ls="-.", label="$N=6$ comparator")
    ax_s.set_xlabel(r"log-moneyness $k$")
    ax_s.set_ylabel("implied volatility (%)")
    ax_s.legend(loc="upper right")
    label_panel(ax_s, "A")

    x = np.linspace(-0.28, 0.28, 500)
    true_pdf = sum(w * norm.pdf(x, m, s)
                   for w, m, s in zip(weights, means, sigmas, strict=True))
    for res, color, ls, label in (
        (hi, PALETTE["teal"], "--", "$N=16$"),
        (lo, PALETTE["amber"], "-.", "$N=6$"),
    ):
        qx, pdf = res.slice.density()
        ax_d.plot(x, np.interp(x, qx, pdf), color=color, ls=ls, label=label)
    ax_d.plot(x, true_pdf, color=PALETTE["ink"], lw=2.2, label="target")
    ax_d.set_xlabel(r"log-forward return $X$")
    ax_d.set_ylabel(r"density $f_X$")
    ax_d.legend(loc="upper right")
    label_panel(ax_d, "B")
    save(fig, OUT / "fig_lqd_ref_event_order.pdf")

    # Quantified density recovery (committee point 6): L1 distance and the
    # recovered mode locations, per order.
    out = {"hi_err_bp": 1e4 * hi.max_iv_error, "lo_err_bp": 1e4 * lo.max_iv_error}
    dx = x[1] - x[0]
    for tag, res in (("hi", hi), ("lo", lo)):
        qx, pdf = res.slice.density()
        fit_pdf = np.interp(x, qx, pdf)
        out[f"{tag}_l1"] = float(np.sum(np.abs(fit_pdf - true_pdf)) * dx)
        left = x < 0.0
        out[f"{tag}_dmode_bp"] = 1e4 * max(
            abs(x[left][np.argmax(fit_pdf[left])] - x[left][np.argmax(true_pdf[left])]),
            abs(x[~left][np.argmax(fit_pdf[~left])] - x[~left][np.argmax(true_pdf[~left])]),
        )
    return out


def figure_vegafloor() -> dict:
    """Effective calibration weight 1/(vega+eta), normalized at ATM."""
    fig, ax = plt.subplots(figsize=FULL)
    out = {}
    kk = np.linspace(-0.45, 0.45, 400)
    for tau, color, ls in ((0.75, PALETTE["teal"], "-"),
                           (30 / 365, PALETTE["amber"], "--"),
                           (2 / 365, PALETTE["rust"], "-.")):
        from gen_lqd_geometry import ssvi_total_variance
        w = ssvi_total_variance(kk) * tau / 0.75
        sigma = np.sqrt(w / tau)
        vega = black_vega_sigma(kk, sigma, tau)
        weight = 1.0 / (vega + _VEGA_FLOOR)
        rel = weight / weight[np.argmin(np.abs(kk))]
        ax.plot(kk, rel, color=color, ls=ls,
                label=rf"$\tau={tau:.3f}$ y")
        floored = np.abs(kk)[vega < _VEGA_FLOOR]
        out[f"kfloor_{tau:.3f}"] = float(floored.min()) if floored.size else np.nan
    ax.set_yscale("log")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("relative residual weight (log scale)")
    ax.legend(loc="upper center")
    save(fig, OUT / "fig_lqd_ref_vegafloor.pdf")
    return out


def write_tables(spreads, lee, dec, event, floor) -> None:
    lines = ["% Auto-generated by Docs/notes/figures/gen_lqd_referee.py - do not edit."]

    def pct(x):
        return "%.1f" % x

    for tag in ("note", "spy"):
        lines.append(r"\newcommand{\lqdref%sfanAR}{%s}" % (tag, pct(spreads[f"{tag}_aR"])))
        lines.append(r"\newcommand{\lqdref%sfanBR}{%s}" % (tag, pct(spreads[f"{tag}_betaR"])))
        lines.append(r"\newcommand{\lqdref%sfanVS}{%s}" % (tag, pct(spreads[f"{tag}_varSwapVol"])))
        lines.append(r"\newcommand{\lqdref%sfanTend}{%s}" % (tag, pct(spreads[f"{tag}_vol_10d_put"])))
        lines.append(r"\newcommand{\lqdref%sfanOned}{%s}" % (tag, pct(spreads[f"{tag}_vol_1d_put"])))
    lines.append(r"\newcommand{\lqdrefleetenput}{%.2f}" % lee["ratio_10d_put"])
    lines.append(r"\newcommand{\lqdrefleeoneput}{%.2f}" % lee["ratio_1d_put"])
    lines.append(r"\newcommand{\lqdrefleetencall}{%.2f}" % lee["ratio_10d_call"])
    lines.append(r"\newcommand{\lqdrefleeonecall}{%.2f}" % lee["ratio_1d_call"])
    lines.append(r"\newcommand{\lqdrefrawarfac}{%.3f}" % dec["raw_arfac"])
    lines.append(r"\newcommand{\lqdrefrawalfac}{%.3f}" % dec["raw_alfac"])
    lines.append(r"\newcommand{\lqdrefbodyarfac}{%.3f}" % dec["endpoint_arfac"])
    lines.append(r"\newcommand{\lqdrefeventhi}{%.2f}" % event["hi_err_bp"])
    lines.append(r"\newcommand{\lqdrefeventlo}{%.1f}" % event["lo_err_bp"])
    lines.append(r"\newcommand{\lqdrefeventhiLone}{%.3f}" % event["hi_l1"])
    lines.append(r"\newcommand{\lqdrefeventloLone}{%.3f}" % event["lo_l1"])
    lines.append(r"\newcommand{\lqdrefeventhimode}{%.0f}" % event["hi_dmode_bp"])
    lines.append(r"\newcommand{\lqdrefeventlomode}{%.0f}" % event["lo_dmode_bp"])
    (OUT / "lqd_referee_tables.tex").write_text("\n".join(lines) + "\n",
                                                encoding="utf-8")


def main() -> None:
    print("Fitting the running example ...")
    spx = fit_spx_case()

    print("Tail-stability study on the running example (committee protocol) ...")
    iv = quote_iv(EXPIRY)
    note_study = run_study(QUOTE_K, iv * iv * EXPIRY, EXPIRY,
                           n_order=9, reg_lambda=3e-8, reg_power=1.2)
    (OUT / "tail_study_note.json").write_text(json.dumps(note_study, indent=1))
    spy_study = json.loads((OUT / "tail_study_spy.json").read_text())

    spreads = figure_tailfan(note_study, spy_study)
    print("  fan spreads (%):", {k: round(v, 1) for k, v in spreads.items()
                                 if k.endswith(("aR", "varSwapVol"))})
    lee = figure_lee(spx)
    print("  effective/limit slope at 10d put:", round(lee["ratio_10d_put"], 2))
    dec = figure_decouple(spx)
    print("  raw a2 bump A_R factor:", round(dec["raw_arfac"], 4),
          " endpoint-chart:", round(dec["endpoint_arfac"], 4))
    event = figure_event_order()
    print("  event max err bp: N=16", round(event["hi_err_bp"], 2),
          " N=6", round(event["lo_err_bp"], 1))
    floor = figure_vegafloor()
    write_tables(spreads, lee, dec, event, floor)
    print("Wrote 5 figures + lqd_referee_tables.tex to", OUT)


if __name__ == "__main__":
    main()
