"""Chapter 3 SVI figures: zoo, handles, Lee boundary, Vogt, stratum,
structural chart (F1-F6)."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from volfit.models.svi_jw.calibrate import LEE_SLOPE_BUFFER, calibrate_svi
from volfit.models.svi_jw.svi import RawSVI, durrleman_g_raw

import data3
from figstyle import PALETTE, ROW2, ROW3, callout, panel, save
from macros import STORE, num, sci

BETA_MAX = 2.0 - LEE_SLOPE_BUFFER

# The classical Vogt slice (Gatheral-Jacquier Example 3.1).
VOGT = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
# A slice exactly AT Lee's boundary: beta_L = beta_R = 2, floor-clean.
BOUNDARY = RawSVI(a=0.04, b=2.0, rho=0.0, m=0.0, sigma=0.2)


def raw_to_jw(raw: RawSVI, t: float) -> tuple[float, float, float, float, float]:
    """(v, psi, p, c, vtilde): the JW functionals of a raw slice at clock t."""
    w0 = float(raw.total_variance(0.0))
    sq = np.sqrt(w0)
    q = np.sqrt(1.0 - raw.rho**2)
    psi = raw.b / (2.0 * sq) * (raw.rho - raw.m / np.hypot(raw.m, raw.sigma))
    p = raw.b * (1.0 - raw.rho) / sq
    c = raw.b * (1.0 + raw.rho) / sq
    vt = (raw.a + raw.b * raw.sigma * q) / t
    return w0 / t, float(psi), float(p), float(c), float(vt)


def _spy_svi() -> tuple[data3.Node, RawSVI]:
    n = data3.node(*data3.SPY_DEC)
    res = calibrate_svi(n.k, n.w_mid, n.t, chart="structural")
    return n, res.raw


# ------------------------------------------------------------------ F1: zoo
def fig_svi_zoo() -> str:
    base = dict(a=0.015, b=0.35, rho=-0.4, m=0.0, sigma=0.25)
    k = np.linspace(-1.1, 1.1, 401)
    fig, axes = plt.subplots(1, 3, figsize=ROW3)
    shades = ["#bcd5f2", "#8db6e8", "#5d97dd", "#2a78d6", "#1a4e8f"]

    for rho, col in zip([-0.8, -0.4, 0.0, 0.4, 0.8], shades):
        axes[0].plot(k, RawSVI(**{**base, "rho": rho}).total_variance(k),
                     color=col, lw=1.2)
    panel(axes[0], "a", r"tilt $\rho_S\in[-0.8,0.8]$")

    for sig, col in zip([0.05, 0.15, 0.3, 0.5, 0.8], shades):
        axes[1].plot(k, RawSVI(**{**base, "sigma": sig}).total_variance(k),
                     color=col, lw=1.2)
    panel(axes[1], "b", r"width $s_S\in[0.05,0.8]$")

    for b, col in zip([0.1, 0.2, 0.35, 0.55, 0.8], shades):
        axes[2].plot(k, RawSVI(**{**base, "b": b}).total_variance(k),
                     color=col, lw=1.2)
    panel(axes[2], "c", r"steepness $b_S\in[0.1,0.8]$")

    for ax in axes:
        ax.set_xlabel(r"log-moneyness $k$")
        ax.set_ylim(bottom=0.0)
    axes[0].set_ylabel(r"total variance $w$")
    save(fig, "fig_svi_zoo")
    return "5x3 parameter sweeps"


# -------------------------------------------------------------- F2: handles
def fig_svi_handles() -> str:
    n, raw = _spy_svi()
    t = n.t
    v, psi, p, c, vt = raw_to_jw(raw, t)
    w0 = v * t
    rms = 1e4 * float(np.sqrt(np.mean((raw.implied_vol(n.k, t) - n.iv_mid) ** 2)))
    b_l, b_r = raw.wing_slopes()
    k_star = raw.m - raw.sigma * raw.rho / np.sqrt(1.0 - raw.rho**2)

    STORE.add("handles", "SviSpyRmsBp", num(rms, 1),
              "SVI structural-chart mid fit rms on SPY Dec-2026, vol bp")
    STORE.add("handles", "SviSpyAtmVolPct", num(100 * np.sqrt(v), 2),
              "sqrt(v_J), ATM implied vol of the SVI fit, percent")
    STORE.add("handles", "SviSpyPsi", num(psi, 4), "psi_J of the SPY fit")
    STORE.add("handles", "SviSpyP", num(p, 3), "p_J of the SPY fit")
    STORE.add("handles", "SviSpyC", num(c, 3), "c_J of the SPY fit")
    STORE.add("handles", "SviSpyMinVolPct", num(100 * np.sqrt(vt), 2),
              "sqrt(vtilde_J), minimum implied vol, percent")
    STORE.add("handles", "SviSpyBetaL", num(b_l, 3), "actual left wing slope")
    STORE.add("handles", "SviSpyBetaR", num(b_r, 3), "actual right wing slope")
    STORE.add("handles", "SviSpyTangent", num(psi / np.sqrt(t), 3),
              "plotted ATM IV tangent slope psi_J/sqrt(tau)")

    k = np.linspace(-0.55, 0.45, 401)
    fig, axes = plt.subplots(1, 2, figsize=ROW2)

    ax = axes[0]
    ax.plot(n.k, 100 * n.iv_mid, "o", ms=2.6, color=PALETTE["data"],
            alpha=0.7, label="mid quotes")
    ax.plot(k, 100 * raw.implied_vol(k, t), color=PALETTE["model"], label="SVI fit")
    ax.axhline(100 * np.sqrt(v), color=PALETTE["muted"], lw=0.8, ls=":")
    ax.axhline(100 * np.sqrt(vt), color=PALETTE["muted"], lw=0.8, ls=":")
    kt = np.linspace(-0.16, 0.16, 2)
    ax.plot(kt, 100 * (np.sqrt(v) + psi / np.sqrt(t) * kt),
            color=PALETTE["ink"], lw=0.9, ls="--", label="ATM tangent")
    ax.text(k[-1], 100 * np.sqrt(v) + 0.15, r"$\sqrt{v_J}$", ha="right",
            fontsize=8, color=PALETTE["muted"])
    ax.text(k[-1], 100 * np.sqrt(vt) - 0.55, r"$\sqrt{\tilde v_J}$", ha="right",
            fontsize=8, color=PALETTE["muted"])
    ax.set_xlabel(r"$k$"); ax.set_ylabel("implied vol (%)")
    ax.legend(loc="upper right")
    panel(ax, "a", "belly handles, IV chart")

    ax = axes[1]
    kk = np.linspace(-2.6, 2.6, 401)
    ax.plot(kk, raw.total_variance(kk), color=PALETTE["model"], label=r"$w(k)$")
    left = raw.a + raw.b * (raw.rho - 1.0) * (kk - raw.m)
    right = raw.a + raw.b * (raw.rho + 1.0) * (kk - raw.m)
    ax.plot(kk[kk < 0.3], left[kk < 0.3], ls="--", lw=0.9, color=PALETTE["ink"])
    ax.plot(kk[kk > -0.3], right[kk > -0.3], ls="--", lw=0.9, color=PALETTE["ink"])
    ax.plot([k_star], [raw.total_variance(k_star)], "o", ms=3.5,
            color=PALETTE["data"])
    ax.text(-2.45, raw.total_variance(-2.3) + 0.02,
            rf"slope $\beta_L=p_J\sqrt{{v_J\tau}}={b_l:.3f}$", fontsize=7.5)
    ax.text(0.35, raw.total_variance(2.0) - 0.10,
            rf"slope $\beta_R=c_J\sqrt{{v_J\tau}}={b_r:.3f}$", fontsize=7.5)
    ax.set_ylim(0.0, float(raw.total_variance(-2.6)) * 1.08)
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"total variance $w$")
    panel(ax, "b", "tail handles, total-variance chart")

    save(fig, "fig_svi_handles")
    return f"SPY Dec fit rms {rms:.1f} bp"


# ------------------------------------------------------------------ F3: Lee
def fig_svi_lee() -> str:
    g10 = float(durrleman_g_raw(BOUNDARY, np.array([10.0]))[0])
    p_star_cap = (2.0 - BETA_MAX) ** 2 / (8.0 * BETA_MAX)
    STORE.add("lee", "SviBoundaryGTen", num(g10, 4),
              "g_D(10) of the boundary slice (a=0.04, b=2, rho=0, m=0, s=0.2)")
    STORE.add("lee", "SviPstarCap", sci(p_star_cap, 1),
              "moment budget p* remaining at the buffered cap beta_max")
    STORE.add("lee", "SviBetaMax", num(BETA_MAX, 2),
              "the buffered wing-slope cap of the reference implementation")

    fig, axes = plt.subplots(1, 3, figsize=ROW3)

    ax = axes[0]
    beta = np.linspace(0.0, 2.4, 300)
    ax.plot(beta, (4.0 - beta**2) / 16.0, color=PALETTE["model"])
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.axvline(2.0, color=PALETTE["data"], lw=0.9, ls=":")
    ax.axvline(BETA_MAX, color=PALETTE["muted"], lw=0.9, ls="--")
    ax.text(2.04, 0.21, r"$\beta=2$", fontsize=7.5, color=PALETTE["data"])
    ax.text(0.1, -0.085, rf"$\beta_{{\max}}={BETA_MAX}$ (dashed)",
            fontsize=7.5, color=PALETTE["muted"])
    ax.set_xlabel(r"wing slope $\beta$")
    ax.set_ylabel(r"$\lim g_{\rm D}=(4-\beta^2)/16$")
    panel(ax, "a", "the tail limit changes sign at 2")

    ax = axes[1]
    kk = np.linspace(1.0, 60.0, 800)
    ax.plot(kk, durrleman_g_raw(BOUNDARY, kk), color=PALETTE["data"],
            label=r"at the bound ($\beta_R=2$)")
    under = RawSVI(a=0.04, b=BETA_MAX, rho=0.0, m=0.0, sigma=0.2)
    ax.plot(kk, durrleman_g_raw(under, kk), color=PALETTE["model"],
            label=rf"at the cap ($\beta_R={BETA_MAX}$)")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.axhline((4 - BETA_MAX**2) / 16, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"$g_{\rm D}(k)$")
    ax.set_ylim(-0.06, 0.08)
    ax.legend(loc="lower right", fontsize=7)
    panel(ax, "b", "the boundary carries negative density")

    ax = axes[2]
    beta = np.linspace(0.02, 2.0, 400)
    ax.semilogy(beta, (2.0 - beta) ** 2 / (8.0 * beta), color=PALETTE["model"])
    ax.axvline(2.0, color=PALETTE["data"], lw=0.9, ls=":")
    ax.axvline(BETA_MAX, color=PALETTE["muted"], lw=0.9, ls="--")
    ax.plot([BETA_MAX], [p_star_cap], "o", ms=3.5, color=PALETTE["muted"])
    ax.set_xlabel(r"wing slope $\beta$")
    ax.set_ylabel(r"moment budget $r^*$")
    panel(ax, "c", "the moment budget collapses at the cap")

    save(fig, "fig_svi_lee")
    return f"boundary g(10) = {g10:.4f}"


# ----------------------------------------------------------------- F4: Vogt
def fig_svi_vogt() -> str:
    k = np.linspace(-1.5, 2.0, 1401)
    w = VOGT.total_variance(k)
    g = durrleman_g_raw(VOGT, k)
    b_l, b_r = VOGT.wing_slopes()
    w_min = float(VOGT.a + VOGT.b * VOGT.sigma * np.sqrt(1 - VOGT.rho**2))
    i_dip = int(np.argmin(g))
    tail_r = (4.0 - b_r**2) / 16.0

    STORE.add("vogt", "SviVogtWmin", num(w_min, 4), "Vogt minimum total variance")
    STORE.add("vogt", "SviVogtLee", num(max(b_l, b_r), 3),
              "Vogt larger wing slope (far under the cap)")
    STORE.add("vogt", "SviVogtGmin", num(float(g[i_dip]), 3),
              "Vogt minimum of g_D (the belly violation)")
    STORE.add("vogt", "SviVogtKdip", num(float(k[i_dip]), 2),
              "log-moneyness of the Vogt g_D dip")
    STORE.add("vogt", "SviVogtTail", num(tail_r, 2),
              "Vogt right tail limit of g_D (positive)")

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    ax = axes[0]
    ax.plot(k, w, color=PALETTE["model"])
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.axhline(w_min, color=PALETTE["muted"], lw=0.8, ls=":")
    ax.text(-1.45, w_min + 0.004, rf"floor $w_\star={w_min:.4f}>0$",
            fontsize=7.5, color=PALETTE["muted"])
    ax.text(0.10, 0.152,
            rf"wings $\beta_L={b_l:.3f}$, $\beta_R={b_r:.3f}\ll\beta_{{\max}}$",
            fontsize=7.5, color=PALETTE["muted"])
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"total variance $w$")
    panel(ax, "a", "both cheap screens pass")

    ax = axes[1]
    ax.plot(k, g, color=PALETTE["model"])
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.axhline(0.25, color=PALETTE["muted"], lw=0.7, ls=":")
    ax.text(-1.45, 0.26, r"tail limits $\approx(4-\beta^2)/16$",
            fontsize=7.5, color=PALETTE["muted"])
    callout(ax, rf"$g_{{\rm D}}={g[i_dip]:.3f}$ at $k={k[i_dip]:.2f}$",
            (k[i_dip], g[i_dip]), (0.9, -0.25))
    ax.set_ylim(-0.4, 1.6)
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"$g_{\rm D}(k)$")
    panel(ax, "b", "the belly violates anyway")

    save(fig, "fig_svi_vogt")
    return f"Vogt dip {g[i_dip]:.3f} at k={k[i_dip]:.2f}"


# -------------------------------------------------------------- F5: stratum
def fig_svi_stratum() -> str:
    t, v, p, c = 0.5, 0.04, 1.0, 0.6
    w0 = v * t
    b = 0.5 * np.sqrt(w0) * (p + c)
    rho = (c - p) / (c + p)
    q = np.sqrt(1.0 - rho**2)

    psi = np.linspace(-0.2, 0.2, 801)
    chi = rho - 4.0 * psi / (p + c)
    denom = (1.0 - rho * chi) / np.sqrt(1.0 - chi**2) - q
    asym = 8.0 * psi**2 / ((p + c) ** 2 * q**3)

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    ax = axes[0]
    ax.plot(psi, denom, color=PALETTE["model"], label=r"$\mathcal{D}(\psi_J)$")
    ax.plot(psi, asym, ls="--", lw=0.9, color=PALETTE["muted"],
            label=r"$8\psi_J^2/\{(p_J{+}c_J)^2(1-\rho_S^2)^{3/2}\}$")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.set_xlabel(r"$\psi_J$"); ax.set_ylabel("inverse denominator")
    ax.legend(loc="upper center", fontsize=7)
    panel(ax, "a", "the denominator vanishes quadratically")

    ax = axes[1]
    k = np.linspace(-0.6, 0.6, 601)
    jw_check = []
    for s, col in zip([0.08, 0.20, 0.45], ["#8db6e8", "#2a78d6", "#1a4e8f"]):
        m = rho * s / q
        a = w0 - b * s * q
        raw = RawSVI(a=a, b=b, rho=rho, m=m, sigma=s)
        jw_check.append(raw_to_jw(raw, t))
        ax.plot(k, raw.total_variance(k), color=col, lw=1.2,
                label=rf"$s_S={s:.2f}$")
    # All three must share the SAME five handles (the singular stratum).
    jw = np.array(jw_check)
    spread = float(np.max(np.ptp(jw, axis=0)))
    if spread > 1e-12:
        raise RuntimeError(f"stratum construction broken: handle spread {spread}")
    STORE.add("stratum", "SviStratumSpread", sci(max(spread, 1e-17), 1),
              "max spread of the five handles across the three stratum slices")
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"total variance $w$")
    ax.legend(loc="upper right", fontsize=7)
    panel(ax, "b", "three bellies, one set of handles")

    save(fig, "fig_svi_stratum")
    return "handles agree to machine precision"


# ----------------------------------------------------------- F6: structural
def fig_svi_structural() -> str:
    n, raw = _spy_svi()
    t = n.t
    raw_chart = calibrate_svi(n.k, n.w_mid, n.t, chart="raw").raw
    kk = np.linspace(float(n.k.min()), float(n.k.max()), 801)
    agree_bp = 1e4 * float(np.max(np.abs(
        raw.implied_vol(kk, t) - raw_chart.implied_vol(kk, t))))
    STORE.add("structural", "SviChartAgreeBp", num(agree_bp, 2),
              "max |structural - raw chart| IV gap on SPY Dec, vol bp")

    q = np.sqrt(1.0 - raw.rho**2)
    k_star = raw.m - raw.sigma * raw.rho / q
    w_star = raw.a + raw.b * raw.sigma * q
    kappa_star = raw.b * q**3 / raw.sigma
    b_l, b_r = raw.wing_slopes()
    STORE.add("structural", "SviSpyKstar", num(k_star, 3),
              "structural vertex location k* of the SPY fit")
    STORE.add("structural", "SviSpyWstar", num(w_star, 4),
              "structural floor w* of the SPY fit")
    STORE.add("structural", "SviSpyKappastar", num(kappa_star, 3),
              "structural vertex curvature kappa* of the SPY fit")

    fig, axes = plt.subplots(1, 2, figsize=ROW2)
    ax = axes[0]
    ell = np.linspace(-7.0, 7.0, 400)
    ax.plot(ell, BETA_MAX / (1.0 + np.exp(-ell)), color=PALETTE["model"])
    ax.axhline(BETA_MAX, color=PALETTE["muted"], lw=0.9, ls="--")
    ax.axhline(2.0, color=PALETTE["data"], lw=0.9, ls=":")
    ax.axhline(0.0, color=PALETTE["ink"], lw=0.7)
    ax.text(-6.8, BETA_MAX - 0.16, rf"$\beta_{{\max}}={BETA_MAX}$",
            fontsize=7.5, color=PALETTE["muted"])
    ax.text(-6.8, 2.03, r"Lee bound $2$", fontsize=7.5, color=PALETTE["data"])
    ax.set_xlabel(r"chart coordinate $\theta$")
    ax.set_ylabel(r"wing slope $\beta=\beta_{\max}\Lambda(\theta)$")
    panel(ax, "a", "the lift keeps every iterate strictly inside")

    ax = axes[1]
    kk2 = np.linspace(-0.42, 0.34, 601)
    ax.plot(kk2, raw.total_variance(kk2), color=PALETTE["model"], label=r"$w(k)$")
    osc = w_star + 0.5 * kappa_star * (kk2 - k_star) ** 2
    mask = np.abs(kk2 - k_star) < 0.14
    ax.plot(kk2[mask], osc[mask], ls="--", lw=1.0, color=PALETTE["data"],
            label="osculating parabola")
    ax.plot([k_star], [w_star], "o", ms=4, color=PALETTE["ink"], zorder=5)
    ax.annotate(r"$(k^*,\,w^*)$", (k_star, w_star),
                xytext=(k_star + 0.07, w_star + 0.003), fontsize=8)
    left = raw.a + raw.b * (raw.rho - 1.0) * (kk2 - raw.m)
    right = raw.a + raw.b * (raw.rho + 1.0) * (kk2 - raw.m)
    ax.plot(kk2[kk2 < k_star], left[kk2 < k_star], lw=0.7, ls=":",
            color=PALETTE["muted"])
    ax.plot(kk2[kk2 > k_star], right[kk2 > k_star], lw=0.7, ls=":",
            color=PALETTE["muted"])
    ax.text(-0.40, raw.total_variance(-0.33), rf"$\beta_L={b_l:.3f}$",
            fontsize=7.5, color=PALETTE["muted"])
    ax.text(0.16, raw.total_variance(0.30), rf"$\beta_R={b_r:.3f}$",
            fontsize=7.5, color=PALETTE["muted"])
    ax.set_ylim(0.0, float(raw.total_variance(-0.42)) * 1.06)
    ax.set_xlabel(r"$k$"); ax.set_ylabel(r"total variance $w$")
    ax.legend(loc="upper right", fontsize=7)
    panel(ax, "b", "the five structural coordinates, on the SPY fit")

    save(fig, "fig_svi_structural")
    return f"charts agree to {agree_bp:.2f} bp"
