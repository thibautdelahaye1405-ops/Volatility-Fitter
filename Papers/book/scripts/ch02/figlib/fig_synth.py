"""Figures F10-F11: the synthetic double-hump and the order-control study.

F10 fig_doublehump    -- the N = 16 fit recovers the bimodal density.
F11 fig_order_control -- the N = 6 comparator: the smile barely moves,
                         the density loses the modes (what order buys).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from volfit.core.black import implied_total_variance

import synth
from figstyle import PALETTE, ROW2, panel, save
from macros import STORE, num


def _dense_target(dense_k: np.ndarray) -> np.ndarray:
    """Dense target implied vols of the mixture."""
    w = implied_total_variance(dense_k, synth.mixture_call(dense_k))
    return np.sqrt(w / synth.DH_EXPIRY)


def _errors_bp(result, quote_k, quote_w) -> tuple[float, float]:
    """(max, rms) IV error at the quotes, vol bp."""
    fit_iv = result.slice.implied_vol(quote_k, synth.DH_EXPIRY)
    err = 1e4 * (np.asarray(fit_iv) - np.sqrt(quote_w / synth.DH_EXPIRY))
    return float(np.max(np.abs(err))), float(np.sqrt(np.mean(err * err)))


def fig_doublehump() -> str:
    """F10: target smile + N = 16 fit; true vs recovered density."""
    dh = synth.double_hump()
    t = synth.DH_EXPIRY
    dense_k = np.linspace(-0.30, 0.30, 501)
    target_iv = _dense_target(dense_k)
    fit_iv = dh.high.slice.implied_vol(dense_k, t)

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    axes[0].plot(dense_k, 100.0 * target_iv, color=PALETTE["ink"], lw=1.6,
                 label="mixture target")
    axes[0].plot(dense_k, 100.0 * fit_iv, color=PALETTE["model"], ls="--",
                 label=f"LQD fit ($N={synth.DH_ORDER_HIGH}$)")
    axes[0].scatter(dh.quote_k, 100.0 * np.sqrt(dh.quote_w / t), s=8,
                    color=PALETTE["data"], zorder=4, label="quotes")
    axes[0].set_xlabel(r"log-moneyness $k$")
    axes[0].set_ylabel("implied volatility (%)")
    axes[0].legend(loc="upper right", fontsize=7.0)
    panel(axes[0], "a", "an event smile with two regimes")

    x, f = dh.high.slice.density()
    sel = np.abs(x) < 0.32
    axes[1].plot(x[sel], synth.mixture_density(x[sel]), color=PALETTE["ink"],
                 lw=1.6, label="true density")
    axes[1].plot(x[sel], f[sel], color=PALETTE["model"], ls="--",
                 label=f"recovered ($N={synth.DH_ORDER_HIGH}$)")
    axes[1].fill_between(x[sel], 0.0, f[sel], color=PALETTE["model"],
                         alpha=0.08, lw=0.0)
    axes[1].set_xlabel(r"log return $x$")
    axes[1].set_ylabel(r"density $f_X$")
    axes[1].set_ylim(top=1.30 * float(f[sel].max()))  # legend headroom
    axes[1].legend(loc="upper right", fontsize=7.0)
    panel(axes[1], "b", "both modes survive the inversion")

    save(fig, "fig_doublehump")

    max_bp, rms_bp = _errors_bp(dh.high, dh.quote_k, dh.quote_w)
    modes = synth.density_modes(x, f)
    STORE.add("doublehump", "DhOrderHigh", str(synth.DH_ORDER_HIGH),
              "order of the resolving double-hump fit")
    STORE.add("doublehump", "DhOrderLow", str(synth.DH_ORDER_LOW),
              "order of the smoothing comparator fit")
    STORE.add("doublehump", "DhNQuotes", str(dh.quote_k.size),
              "quotes in the double-hump strip")
    STORE.add("doublehump", "DhMaxErrBpHigh", num(max_bp, 2),
              "max IV error of the N = 16 double-hump fit, vol bp")
    STORE.add("doublehump", "DhRmsBpHigh", num(rms_bp, 2),
              "rms IV error of the N = 16 double-hump fit, vol bp")
    STORE.add("doublehump", "DhModeCountHigh", str(len(modes)),
              "modes of the N = 16 recovered density")
    if len(modes) >= 2:
        STORE.add("doublehump", "DhModeLeft", num(modes[0], 3),
                  "left mode location of the N = 16 recovered density")
        STORE.add("doublehump", "DhModeRight", num(modes[-1], 3),
                  "right mode location of the N = 16 recovered density")
    STORE.add("doublehump", "DhTrueModeLeft", num(synth.DH_MEANS[0], 3),
              "left mode of the true mixture density")
    STORE.add("doublehump", "DhTrueModeRight", num(synth.DH_MEANS[1], 3),
              "right mode of the true mixture density")
    return (f"double-hump N=16: max {max_bp:.2f} bp, {len(modes)} modes at "
            f"{[f'{m:+.3f}' for m in modes]}")


def fig_order_control() -> str:
    """F11: the same target at N = 6 -- the density pays, not the smile."""
    dh = synth.double_hump()
    t = synth.DH_EXPIRY
    dense_k = np.linspace(-0.30, 0.30, 501)
    iv_high = np.asarray(dh.high.slice.implied_vol(dense_k, t))
    iv_low = np.asarray(dh.low.slice.implied_vol(dense_k, t))
    gap_bp = 1e4 * np.max(np.abs(iv_high - iv_low))
    l1_high = synth.density_l1(dh.high.slice)
    l1_low = synth.density_l1(dh.low.slice)

    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    axes[0].plot(dense_k, 100.0 * _dense_target(dense_k), color=PALETTE["ink"],
                 lw=1.6, label="mixture target")
    axes[0].plot(dense_k, 100.0 * iv_high, color=PALETTE["model"], ls="--",
                 label=f"$N={synth.DH_ORDER_HIGH}$")
    axes[0].plot(dense_k, 100.0 * iv_low, color=PALETTE["alt"], ls="-.",
                 label=f"$N={synth.DH_ORDER_LOW}$")
    axes[0].text(0.03, 0.05, f"fits differ by $\\leq$ {gap_bp:.0f} vol bp",
                 transform=axes[0].transAxes, fontsize=7.5,
                 color=PALETTE["muted"])
    axes[0].set_xlabel(r"log-moneyness $k$")
    axes[0].set_ylabel("implied volatility (%)")
    axes[0].legend(loc="upper right", fontsize=7.0)
    panel(axes[0], "a", "two orders, almost one smile")

    x, f_high = dh.high.slice.density()
    x_low, f_low = dh.low.slice.density()
    sel = np.abs(x) < 0.32
    sel_low = np.abs(x_low) < 0.32
    axes[1].plot(x[sel], synth.mixture_density(x[sel]), color=PALETTE["ink"],
                 lw=1.6, label="true density")
    axes[1].plot(x[sel], f_high[sel], color=PALETTE["model"], ls="--",
                 label=f"$N={synth.DH_ORDER_HIGH}$"
                       f"  ($L_1$ = {l1_high:.3f})")
    axes[1].plot(x_low[sel_low], f_low[sel_low], color=PALETTE["alt"], ls="-.",
                 label=f"$N={synth.DH_ORDER_LOW}$"
                       f"  ($L_1$ = {l1_low:.3f})")
    axes[1].set_xlabel(r"log return $x$")
    axes[1].set_ylabel(r"density $f_X$")
    axes[1].set_ylim(top=1.30 * float(max(f_high[sel].max(),
                                          f_low[sel_low].max())))
    axes[1].legend(loc="upper right", fontsize=7.0)
    panel(axes[1], "b", "where the missing order went")

    save(fig, "fig_order_control")

    max_low, rms_low = _errors_bp(dh.low, dh.quote_k, dh.quote_w)
    x_modes_low = synth.density_modes(x_low, f_low)
    STORE.add("doublehump", "DhMaxErrBpLow", num(max_low, 1),
              "max IV error of the N = 6 comparator, vol bp")
    STORE.add("doublehump", "DhRmsBpLow", num(rms_low, 1),
              "rms IV error of the N = 6 comparator, vol bp")
    STORE.add("doublehump", "DhIvGapBp", num(gap_bp, 1),
              "max |N16 - N6| implied-vol gap on the dense grid, vol bp")
    STORE.add("doublehump", "DhLOneHigh", num(l1_high, 3),
              "L1 distance of the N = 16 density to the truth")
    STORE.add("doublehump", "DhLOneLow", num(l1_low, 3),
              "L1 distance of the N = 6 density to the truth")
    STORE.add("doublehump", "DhModeCountLow", str(len(x_modes_low)),
              "modes of the N = 6 recovered density")
    # Valley-to-peak ratio: how much of the bimodal relief each fit keeps.
    x_true = x[sel]
    for name, ratio in (
        ("DhValleyPeakTrue",
         synth.valley_to_peak(x_true, synth.mixture_density(x_true))),
        ("DhValleyPeakHigh", synth.valley_to_peak(x[sel], f_high[sel])),
        ("DhValleyPeakLow", synth.valley_to_peak(x_low[sel_low],
                                                 f_low[sel_low])),
    ):
        STORE.add("doublehump", name, num(ratio, 2),
                  "valley-to-peak density ratio"
                  f" ({name.removeprefix('DhValleyPeak').lower()} density)")
    return (f"order control: IV gap {gap_bp:.1f} bp, L1 {l1_high:.3f} vs "
            f"{l1_low:.3f}, N6 modes {len(x_modes_low)}")
