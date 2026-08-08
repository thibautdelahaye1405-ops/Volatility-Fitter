"""Figures F1-F3: the transport heuristic, the basis modes, the exact audit.

F1 fig_transport   -- logistic score density, the constant-speed transport
                      map with two strike roots, and the resulting smile.
F2 fig_modes       -- switching on a2 / a3 / a4 = 0.10 one at a time:
                      log-speed h, implied vol, density.
F3 fig_exact       -- constant-speed slices vs the pi*s/sin(pi*s) closed
                      form (machine precision) + the cold-start mismatch.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.special import expit, logit

from volfit.models.lqd.basis import LQDParams, g_eval
from volfit.models.lqd.quadrature import build_slice

import synth
from figstyle import PALETTE, ROW2, ROW3, panel, save
from macros import STORE, num, sci

MODE_COLORS = {2: PALETTE["model"], 3: PALETTE["data"], 4: PALETTE["alt"]}


def fig_transport() -> str:
    """F1: rank -> log-odds -> return, on the exact-20%-ATM toy slice."""
    toy = synth.constant_speed_toy()
    slice_, t = toy.slice, toy.expiry
    k_otm = 0.10
    z_atm = float(slice_.strike_to_z(0.0))
    z_otm = float(slice_.strike_to_z(k_otm))
    u_otm = float(expit(z_otm))
    share = float(slice_.asset_share_at(z_otm))
    cash = float(np.exp(k_otm) * (1.0 - u_otm))
    call = float(slice_.call_price(k_otm))
    iv_otm = float(slice_.implied_vol(k_otm, t))

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    z = np.linspace(-6.0, 6.0, 601)
    axes[0].plot(z, expit(z) * expit(-z), color=PALETTE["model"])
    # The 10%/90% dots sit at z = -+ log 9 ~ -+ 2.197 (section 3's example).
    marks = np.array([0.01, 0.10, 0.50, 0.90, 0.99])
    axes[0].scatter(logit(marks), marks * (1 - marks), s=12,
                    color=PALETTE["data"], zorder=4)
    for u_mark in marks:
        axes[0].annotate(f"{100 * u_mark:.0f}%",
                         (float(logit(u_mark)), u_mark * (1 - u_mark)),
                         xytext=(0, 5), textcoords="offset points",
                         ha="center", fontsize=7.0, color=PALETTE["muted"])
    axes[0].set_xlabel(r"log-odds coordinate $z$")
    axes[0].set_ylabel(r"score density $u(1-u)$")
    panel(axes[0], "a", "the logistic rank clock")

    zz = np.linspace(-6.0, 6.0, 601)
    x_map = np.interp(zz, slice_.z, slice_.q_z)
    axes[1].plot(zz, x_map, color=PALETTE["model"])
    for z_root, k_val, label in ((z_atm, 0.0, "$k=0$"),
                                 (z_otm, k_otm, "$k=0.10$")):
        axes[1].plot([zz[0], z_root], [k_val, k_val],
                     color=PALETTE["muted"], lw=0.7, ls=":")
        axes[1].plot([z_root, z_root], [x_map[0], k_val],
                     color=PALETTE["muted"], lw=0.7, ls=":")
        axes[1].scatter([z_root], [k_val], s=14, color=PALETTE["data"],
                        zorder=4)
        axes[1].annotate(label, (z_root, k_val), xytext=(4, -9),
                         textcoords="offset points", fontsize=7.5,
                         color=PALETTE["muted"])
    axes[1].set_xlabel(r"log-odds coordinate $z$")
    axes[1].set_ylabel(r"log return $x(z)$")
    panel(axes[1], "b", "the transport map")

    k = np.linspace(-0.30, 0.30, 301)
    axes[2].plot(k, 100.0 * slice_.implied_vol(k, t), color=PALETTE["model"])
    axes[2].scatter([0.0], [100.0 * toy.atm_vol], s=14, color=PALETTE["data"],
                    zorder=4)
    axes[2].annotate("20.00%", (0.0, 100.0 * toy.atm_vol), xytext=(4, -10),
                     textcoords="offset points", fontsize=7.5,
                     color=PALETTE["muted"])
    axes[2].set_xlabel(r"log-moneyness $k$")
    axes[2].set_ylabel("implied volatility (%)")
    panel(axes[2], "c", "the resulting smile")

    save(fig, "fig_transport")

    STORE.add("toy", "ToyScale", num(toy.scale, 6),
              "constant speed s solved to exactly 20% ATM at 6 months")
    STORE.add("toy", "ToyMu", num(slice_.mu, 6),
              "martingale shift m of the toy slice")
    STORE.add("toy", "ToyAtmPercentile", num(100.0 * expit(z_atm), 2),
              "percentile rank of the forward (k = 0) on the toy, %")
    STORE.add("toy", "ToyOtmPercentile", num(100.0 * u_otm, 2),
              "percentile rank of the k = 0.10 strike on the toy, %")
    STORE.add("toy", "ToyShareOtm", num(share, 6),
              "upper-share ledger entry G(z_k) at k = 0.10 on the toy")
    STORE.add("toy", "ToyCashOtm", num(cash, 6),
              "cash leg e^k (1 - u_k) at k = 0.10 on the toy")
    STORE.add("toy", "ToyCallOtm", num(call, 6),
              "normalized call C(0.10) on the toy")
    STORE.add("toy", "ToyIvOtmPct", num(100.0 * iv_otm, 2),
              "implied vol at k = 0.10 on the toy, %")
    return f"toy s={toy.scale:.4f}, C(0.10)={call:.6f}, IV(0.10)={100 * iv_otm:.2f}%"


def fig_modes() -> str:
    """F2: one basis coefficient at a time on the symmetric reference."""
    toy = synth.constant_speed_toy()
    modes = synth.mode_slices(0.10)
    u = np.linspace(0.002, 0.998, 601)
    base_h = g_eval(toy.slice.params, u)

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    axes[0].plot(u, base_h, color=PALETTE["muted"], ls="--", label="baseline")
    for degree, slice_ in modes:
        axes[0].plot(u, g_eval(slice_.params, u), color=MODE_COLORS[degree],
                     label=rf"$a_{degree} = 0.10$")
    axes[0].set_xlabel(r"percentile rank $u$")
    axes[0].set_ylabel(r"log-speed $g(u)$")
    axes[0].legend(loc="upper center", ncols=2, columnspacing=0.8,
                   fontsize=7.0)
    panel(axes[0], "a", "the deformation")

    k = np.linspace(-0.30, 0.30, 301)
    axes[1].plot(k, 100.0 * toy.slice.implied_vol(k, toy.expiry),
                 color=PALETTE["muted"], ls="--")
    for degree, slice_ in modes:
        axes[1].plot(k, 100.0 * slice_.implied_vol(k, toy.expiry),
                     color=MODE_COLORS[degree])
    axes[1].set_xlabel(r"log-moneyness $k$")
    axes[1].set_ylabel("implied volatility (%)")
    panel(axes[1], "b", "the smile response")

    x0, f0 = toy.slice.density()
    window = (x0 > -0.45) & (x0 < 0.45)
    axes[2].plot(x0[window], f0[window], color=PALETTE["muted"], ls="--")
    for degree, slice_ in modes:
        x, f = slice_.density()
        sel = (x > -0.45) & (x < 0.45)
        axes[2].plot(x[sel], f[sel], color=MODE_COLORS[degree])
    axes[2].set_xlabel(r"log return $x$")
    axes[2].set_ylabel(r"density $f_X$")
    panel(axes[2], "c", "the density response")

    save(fig, "fig_modes")
    return "modes a2/a3/a4 = 0.10 drawn on the symmetric toy"


def fig_exact() -> str:
    """F3: the constant-speed family against its closed form."""
    scales = np.linspace(0.05, 0.95, 19)
    err_mu, err_map, err_mart = [], [], []
    for s in scales:
        slice_ = build_slice(LQDParams(np.log(s), np.log(s), np.zeros(5)))
        mu_exact = -np.log(np.pi * s / np.sin(np.pi * s))
        err_mu.append(abs(slice_.mu - mu_exact))
        err_map.append(float(np.max(np.abs(
            slice_.q_z - (slice_.mu + s * slice_.z)))))
        err_mart.append(abs(slice_.martingale_check() - 1.0))
    err_mu, err_map = np.asarray(err_mu), np.asarray(err_map)

    # Cold start: variance-matched scale vs the ATM variance it produces.
    atm_vols = np.linspace(0.08, 0.60, 27)
    t = synth.TOY_EXPIRY
    mismatch = []
    for vol in atm_vols:
        w_target = vol * vol * t
        s_init = float(np.sqrt(3.0 * w_target) / np.pi)
        slice_ = build_slice(
            LQDParams(np.log(s_init), np.log(s_init), np.zeros(5)))
        mismatch.append(100.0 * (float(slice_.implied_w(0.0)) / w_target - 1.0))
    mismatch = np.asarray(mismatch)
    mid = float(np.interp(0.20, atm_vols, mismatch))

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    floor = 1e-18  # keep exact zeros visible on the log axis
    axes[0].semilogy(scales, np.maximum(err_mu, floor), color=PALETTE["model"],
                     marker="o", ms=2.6, label=r"martingale shift $|m - m_s|$")
    axes[0].semilogy(scales, np.maximum(err_map, floor), color=PALETTE["data"],
                     marker="s", ms=2.6,
                     label=r"transport map $\max_z |x(z) - (m + sz)|$")
    axes[0].set_xlabel(r"constant speed $s$")
    axes[0].set_ylabel("absolute error")
    axes[0].legend(loc="upper left", fontsize=7.0)
    panel(axes[0], "a", r"error against $m_s = -\log\frac{\pi s}{\sin \pi s}$")

    axes[1].plot(100.0 * atm_vols, mismatch, color=PALETTE["model"])
    axes[1].axhline(0.0, color=PALETTE["muted"], lw=0.7)
    axes[1].scatter([20.0], [mid], s=14, color=PALETTE["data"], zorder=4)
    axes[1].annotate(f"{mid:+.1f}% at 20% vol", (20.0, mid), xytext=(6, 6),
                     textcoords="offset points", fontsize=7.5,
                     color=PALETTE["muted"])
    axes[1].set_xlabel("target ATM volatility (%)")
    axes[1].set_ylabel("ATM variance mismatch (%)")
    panel(axes[1], "b", "the variance-matched cold start")

    save(fig, "fig_exact")

    STORE.add("exact", "ExactMuWorst", sci(float(err_mu.max())),
              "worst |m - closed form| across constant speeds s in [0.05, 0.95]")
    STORE.add("exact", "ExactMapWorst", sci(float(err_map.max())),
              "worst transport-map linearity error across the same speeds")
    STORE.add("exact", "ExactMartWorst", sci(float(np.max(err_mart))),
              "worst |E e^X - 1| across the same constant-speed slices")
    STORE.add("exact", "ColdStartMismatchPct", num(mid, 1),
              "ATM variance mismatch of the variance-matched cold start"
              " at 20% vol, %")
    return (f"exact check: mu err {err_mu.max():.1e}, map err "
            f"{err_map.max():.1e}, cold start {mid:+.1f}%")
