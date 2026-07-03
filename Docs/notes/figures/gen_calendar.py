"""Figures for Note 10 (calendar-arbitrage prevention).

(1) An inverted-wing term structure (high-vol short expiry over a calmer long
    one) creates a REAL calendar violation, cured by the floor.
(2) The PHANTOM calendar: a steep near slice's linear-wing extrapolation
    crosses a flat far slice in a no-data region; the wide floor grid reads it
    as a violation and flattens the far fit, the confined grid does not ---
    the scenario of test_overlay_calendar.py, run through the production
    calibrate_svi + variance_floor_grid[_from].

  fig_cal_cross.pdf    total variance: near, far-unconstrained, far-cured
  fig_cal_G.pdf        integrated upper-quantile curves, ordered after cure
  fig_cal_phantom.pdf  the phantom violation and the confinement cure
  cal_tables.tex       \\input-able macros
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import expit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, callout, label_panel, save, setup  # noqa: E402

from volfit.calib.calendar import (  # noqa: E402
    calendar_floor_targets,
    calendar_violation,
    variance_floor_grid,
    variance_floor_grid_from,
    variance_floor_targets,
)
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402
from volfit.models.svi_jw.calibrate import calibrate_svi  # noqa: E402
from volfit.models.svi_jw.svi import RawSVI  # noqa: E402

OUT = Path(__file__).resolve().parent
setup()


def smile_w(k, atm_vol, wing, t):
    """A simple skewed vol smile -> total variance."""
    vol = atm_vol + wing * (np.sqrt(k * k + 0.01) - 0.1) - 0.10 * k
    return (vol**2) * t


def cured_pair():
    t_near, t_far = 0.25, 0.50
    k = np.linspace(-0.32, 0.28, 21)
    w_near = smile_w(k, 0.30, 0.60, t_near)
    w_far = smile_w(k, 0.20, 0.25, t_far)

    near = calibrate_slice(k, w_near, t_near, n_order=6, reg_lambda=1e-6)
    far_free = calibrate_slice(k, w_far, t_far, n_order=6, reg_lambda=1e-6)
    cz, cfloor = calendar_floor_targets(near.slice)
    far_cured = calibrate_slice(k, w_far, t_far, n_order=6, reg_lambda=1e-6,
                                calendar_z=cz, calendar_floor=cfloor,
                                calendar_weight=1e6)

    v_free = calendar_violation(near.slice, far_free.slice)
    v_cured = calendar_violation(near.slice, far_cured.slice)

    kk = np.linspace(-0.40, 0.34, 300)
    fig, ax = plt.subplots(figsize=(6.9, 4.0))
    ax.plot(kk, near.slice.implied_w(kk), color=PALETTE["muted"],
            label=fr"near $T={t_near}$")
    wf_free = far_free.slice.implied_w(kk)
    ax.plot(kk, wf_free, color=PALETTE["rust"], ls="--",
            label="far, unconstrained (crosses)")
    ax.plot(kk, far_cured.slice.implied_w(kk), color=PALETTE["teal"],
            label="far, calendar-cured")
    wn = near.slice.implied_w(kk)
    ax.fill_between(kk, wn, wf_free, where=wf_free < wn, color=PALETTE["rust"],
                    alpha=0.12)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("Inverted wings: the cured far slice dominates")
    ax.legend(fontsize=9)
    save(fig, OUT / "fig_cal_cross.pdf")

    alpha = expit(near.slice.z)
    fig, ax = plt.subplots(figsize=(6.9, 3.4))
    sel = (alpha > 0.02) & (alpha < 0.98)
    ax.plot(alpha[sel], near.slice.a_z[sel], color=PALETTE["muted"],
            label=r"$G_{\rm near}(\alpha)$")
    ax.plot(alpha[sel], far_cured.slice.a_z[sel], color=PALETTE["teal"],
            label=r"$G_{\rm far}(\alpha)$ (cured)")
    ax.set_xlabel(r"quantile level $\alpha$")
    ax.set_ylabel(r"$G(\alpha)=\int_\alpha^1 e^{Q(u)}\,du$")
    ax.set_title(r"$G_{\rm far}\geq G_{\rm near}$: convex order restored")
    ax.legend()
    save(fig, OUT / "fig_cal_G.pdf")
    return v_free, v_cured


def phantom():
    """The wide-grid regression scenario of test_overlay_calendar.py."""
    near_steep = RawSVI(a=0.01, b=0.20, rho=-0.7, m=0.0, sigma=0.05)
    far_flat = RawSVI(a=0.08, b=0.08, rho=-0.3, m=0.0, sigma=0.10)
    k_narrow = np.linspace(-0.25, 0.20, 21)
    w_far = far_flat.total_variance(k_narrow)
    t = 1.0

    clean = calibrate_svi(k_narrow, w_far, t=t)
    wide_k, wide_w = variance_floor_targets(near_steep, variance_floor_grid())
    wide = calibrate_svi(k_narrow, w_far, t=t, calendar_k=wide_k,
                         calendar_floor=wide_w)
    data_k, data_w = variance_floor_targets(
        near_steep, variance_floor_grid_from(k_narrow))
    data = calibrate_svi(k_narrow, w_far, t=t, calendar_k=data_k,
                         calendar_floor=data_w)

    fig, axes = plt.subplots(1, 2, figsize=WIDE,
                             gridspec_kw={"width_ratios": [1.2, 1.0]})

    # Panel A: the phantom lives only where no data does.
    ax = axes[0]
    kk = np.linspace(-1.05, 1.05, 400)
    wn, wf = near_steep.total_variance(kk), far_flat.total_variance(kk)
    ax.axvspan(k_narrow.min(), k_narrow.max(), color="black", alpha=0.05)
    ax.plot(kk, wn, color=PALETTE["rust"], label="near (steep wings)")
    ax.plot(kk, wf, color=PALETTE["teal"], label="far (flat, true)")
    phantom_zone = wn > wf
    ax.fill_between(kk, wf, wn, where=phantom_zone, color=PALETTE["rust"],
                    alpha=0.12)
    ax.scatter(wide_k, np.full(wide_k.size, -0.006), s=5,
               color=PALETTE["muted"], label="wide floor grid")
    ax.scatter(data_k, np.full(data_k.size, -0.022), s=5,
               color=PALETTE["teal"], label="confined floor grid")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel(r"total variance $w(k)$")
    ax.set_title("The 'violation' exists only where no data does")
    label_panel(ax, "A")
    ax.legend(fontsize=8.5, loc="center right")
    callout(ax, "phantom: near\nextrapolates above far",
            xy=(-0.78, float(near_steep.total_variance(-0.78))),
            xytext=(-0.38, 0.305))

    # Panel B: the damage and the cure, on the far expiry's own quotes.
    ax = axes[1]
    kz = np.linspace(k_narrow.min() - 0.03, k_narrow.max() + 0.03, 200)
    ax.scatter(k_narrow, 100 * np.sqrt(w_far / t), s=16, color="black",
               zorder=5, label="far quotes")
    ax.plot(kz, 100 * wide.raw.implied_vol(kz, t), color=PALETTE["rust"],
            ls="--", label="fit, wide-grid floor")
    ax.plot(kz, 100 * data.raw.implied_vol(kz, t), color=PALETTE["teal"],
            label="fit, confined floor")
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied volatility (%)")
    ax.set_title("Flattened vs cured", loc="right")
    label_panel(ax, "B")
    ax.legend(fontsize=8.5, loc="upper right")
    fig.tight_layout(w_pad=2.0)
    save(fig, OUT / "fig_cal_phantom.pdf")

    wide_bp = wide.max_iv_error * 1e4
    data_bp = data.max_iv_error * 1e4
    clean_bp = clean.max_iv_error * 1e4
    print("phantom: max IV err wide %.0f bp, confined %.1f bp, clean %.1f bp"
          % (wide_bp, data_bp, clean_bp))
    return wide_bp, data_bp


def main():
    v_free, v_cured = cured_pair()
    wide_bp, data_bp = phantom()
    L = ["% Auto-generated by gen_calendar.py — do not edit."]
    L.append(r"\newcommand{\calviolfree}{%.4f}" % v_free)
    mant, expo = f"{v_cured:.1e}".split("e")
    L.append(r"\newcommand{\calviolcured}{\ensuremath{%s\times10^{%d}}}"
             % (mant, int(expo)))
    L.append(r"\newcommand{\calstride}{25}")
    L.append(r"\newcommand{\calphantomwide}{%.0f}" % wide_bp)
    L.append(r"\newcommand{\calphantomdata}{%.1f}" % data_bp)
    (OUT / "cal_tables.tex").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("calendar violation: unconstrained %.4f -> cured %.2e"
          % (v_free, v_cured))


if __name__ == "__main__":
    main()
