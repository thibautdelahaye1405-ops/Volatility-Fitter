"""Figure: the limit is not the wing — a zero-wing hat breaks the finite wing.

One hat kernel (the production zero-wing kernel of Chapter 3) is parked just
beyond the running node's last quote.  The asymptotic wing slopes move by an
amount at rounding scale — inheritance working exactly as proved — while the
Durrleman factor is driven negative at finite strike: asymptotic and
finite-strike admissibility are independent.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import matplotlib.pyplot as plt

import common
import figstyle
import fits  # Chapter 3's protocol module (g_mcs, mcs_wing_slopes)
from figstyle import PALETTE
from macros import STORE, num, sci

from volfit.models.sigmoid.sigmoid import HatCore

HAT_H = 0.55     # hat half-width (standardized moneyness)
HAT_KAPPA = 4.0  # hat shoulder steepness
HAT_OFFSET = 1.4  # hat centre: this far past the last quote, in z units


def _with_hat(model, node):
    """The fitted MCS slice plus one adversarial hat beyond the last quote."""
    z_bar = float(model.z(float(node.k.min())))  # put side: beyond the LAST
    z_c = z_bar - HAT_OFFSET                     # put-side quote (z < 0)
    v_c, _, _ = model.variance_z(np.array([z_c]))
    # Deterministic amplitude search: the smallest dent (in steps) that drives
    # the Durrleman factor clearly negative while total variance stays positive.
    k_grid = np.linspace(float(node.k.min()) - 1.2, float(node.k.max()) + 0.8,
                         801)
    for frac in (0.05, 0.10, 0.20, 0.35, 0.55):
        hat = HatCore(alpha=-frac * float(v_c[0]), c=z_c, h=HAT_H,
                      kappa=HAT_KAPPA)
        cand = dataclasses.replace(model, cores=model.cores + (hat,))
        g = np.asarray(fits.g_mcs(cand, k_grid))
        w = np.asarray(cand.implied_w(k_grid))
        if np.min(g) < -0.05 and np.min(w) > 0.0:
            return cand, hat
    return cand, hat  # the largest tried dent (still positive variance)


def _realized_slopes(model) -> tuple[float, float]:
    """Measured wing slopes of w(k) by far-field finite differences.

    A measurement, not the analytic base formula: the hats enter (and are
    seen to underflow) exactly as they would for any smile handed over as a
    curve."""
    k_l = np.array([-8.0, -7.9])
    k_r = np.array([7.9, 8.0])
    w_l = np.asarray(model.implied_w(k_l))
    w_r = np.asarray(model.implied_w(k_r))
    return (float((w_l[0] - w_l[1]) / 0.1), float((w_r[1] - w_r[0]) / 0.1))


def fig_wing_limit() -> str:
    node = common.running_node()
    ff = common.family_fits()
    base = ff["MCS"].model
    hatted, hat = _with_hat(base, node)

    slopes_base = _realized_slopes(base)
    slopes_hat = _realized_slopes(hatted)
    slope_diff = max(abs(a - b) for a, b in zip(slopes_base, slopes_hat))

    k = np.linspace(float(node.k.min()) - 1.2, float(node.k.max()) + 0.8, 801)
    w_base = np.asarray(base.implied_w(k))
    w_hat = np.asarray(hatted.implied_w(k))
    g_base = np.asarray(fits.g_mcs(base, k))
    g_hat = np.asarray(fits.g_mcs(hatted, k))
    i_min = int(np.argmin(g_hat))
    g_min, k_min = float(g_hat[i_min]), float(k[i_min])

    k_lo, k_hi = float(node.k.min()), float(node.k.max())
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=figstyle.ROW2)

    # (a) total variance: the hat is invisible at the scale of the wings.
    ax_a.axvspan(k_lo, k_hi, color=PALETTE["band"], alpha=0.55, lw=0, zorder=0)
    ax_a.plot(k, w_base, color=PALETTE["mcs"], lw=1.3, label="fitted slice")
    ax_a.plot(k, w_hat, color=PALETTE["data"], lw=1.1, ls="--",
              label="one hat added")
    k_c = hat.c * base.sigma_ref * np.sqrt(base.t)
    figstyle.callout(ax_a, "the hat sits here,\npast the last quote",
                     xy=(k_c, float(np.interp(k_c, k, w_hat))),
                     xytext=(k_c + 0.28, float(np.interp(k_c, k, w_hat))
                             + 0.35 * float(np.max(w_base))))
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel("total implied variance $w$")
    ax_a.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_a, "a", "the smile: wings unchanged")

    # (b) the Durrleman factor: negative density at finite strike.
    ax_b.axvspan(k_lo, k_hi, color=PALETTE["band"], alpha=0.55, lw=0, zorder=0)
    ax_b.plot(k, g_base, color=PALETTE["mcs"], lw=1.3, label="fitted slice")
    ax_b.plot(k, g_hat, color=PALETTE["data"], lw=1.1, ls="--",
              label="one hat added")
    ax_b.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax_b.plot([k_min], [g_min], "o", color=PALETTE["ink"], ms=3.5, zorder=5)
    figstyle.callout(ax_b, rf"$g_{{\rm D}}={g_min:.2f}$",
                     xy=(k_min, g_min), xytext=(k_min + 0.3, g_min - 0.15))
    ax_b.set_xlabel("log-moneyness $k$")
    ax_b.set_ylabel(r"Durrleman factor $g_{\rm D}$")
    ax_b.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_b, "b", "the density factor: broken at finite strike")

    figstyle.save(fig, "fig_wing_limit")

    STORE.add("limit", "WingHatSlopeDiff", sci(slope_diff, 1),
              "measured realized wing-slope change from adding the hat "
              "(far-field finite difference at |k| = 8)")
    STORE.add("limit", "WingHatGmin", num(g_min, 2),
              "worst Durrleman factor after the hat")
    STORE.add("limit", "WingHatKmin", num(k_min, 2),
              "log-moneyness of the worst dent")
    STORE.add("limit", "WingHatBaseGmin", num(float(np.min(g_base)), 3),
              "worst Durrleman factor of the fitted slice on the same range")
    return (f"slope diff {slope_diff:.1e}, g_min {g_min:.2f} at k {k_min:.2f}")
