"""Figure: three integrals for one number (strike side, law side, field side).

The strike and law panels live on the running LQD slice (Ch. 3 protocol fit);
the field panel lives on Chapter 4's calibrated whole-surface SPY sheet.  The
field-side value (backward source solve) is audited against the same sheet's
own strike-side replication on its lattice — production code on both routes.
"""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

import common
import figstyle
from figstyle import PALETTE
from macros import STORE, num, sci


def _field_side() -> dict:
    """The SPY sheet's fair strike at the running expiry, both routes."""
    import lvfits  # Chapter 4's protocol (path set up by common)
    from volfit.models.localvol import solve_varswap_source
    from volfit.models.localvol.affine import solve_affine_dupire
    from volfit.models.localvol.affine_calib import varswap_const, varswap_weights

    node = common.running_node()
    sf = lvfits.fit_ticker("SPY")
    t_sel = sf.t_grid[sf.t_grid <= node.t + 1e-12]
    assert abs(t_sel[-1] - node.t) < 1e-9, "running expiry must be a grid time"

    # Audit lattice: same strike step as the calibration lattice, but wide
    # enough (strike ratio up to 12) that the strike-side replication sees the
    # whole wing the extrapolated field implies.  Both routes consume the SAME
    # field on the SAME lattice, so the comparison isolates the mathematics.
    dy = float(np.min(np.diff(sf.y_grid)))
    y_hi = 12.0
    n_lo = int(np.ceil(1.0 / dy))
    n_hi = int(np.ceil((y_hi - 1.0) / dy))
    y_audit = np.unique(np.concatenate(
        [np.linspace(0.0, 1.0, n_lo + 1), np.linspace(1.0, y_hi, n_hi + 1)]))

    # Both routes are first-order in the time step, so the audit runs them at
    # the march's own step AND at an eight-fold refinement: the coarse gap is
    # the stepping bias, and it halves with the step.
    def refine_t(ts: np.ndarray, m: int) -> np.ndarray:
        out = [float(ts[0])]
        for a, b in zip(ts[:-1], ts[1:]):
            out.extend(np.linspace(a, b, m + 1)[1:])
        return np.asarray(out)

    k_lo = 0.01  # the reference lower strike-ratio cutoff
    q = varswap_weights(y_audit, k_lo)
    const = varswap_const(y_audit, k_lo)
    audit = {}
    for m in (1, 8):
        ts = refine_t(t_sel, m)
        w_src_m, _ = solve_varswap_source(sf.surface, y_audit, ts)
        sol_m = solve_affine_dupire(sf.surface, y_audit, ts, [float(ts[-1])])
        w_static_m = float(q @ np.asarray(sol_m.price_at(0, y_audit)) + const)
        audit[m] = (float(w_src_m), w_static_m)
    w_src, w_static = audit[8]
    w_src_coarse, w_static_coarse = audit[1]

    # Snapshots for the occupation contours (visual only: the coarse march).
    n_snap = 25
    idx = np.unique(np.linspace(1, t_sel.size - 1, n_snap).astype(int))
    snaps = [float(t_sel[i]) for i in idx]
    sol = solve_affine_dupire(sf.surface, y_audit, t_sel, snaps)

    # Density snapshots for the occupation contours (Breeden–Litzenberger).
    dens, taus = [], []
    for i, s in enumerate(snaps):
        p = np.asarray(sol.price_at(i, y_audit))
        d = np.gradient(np.gradient(p, y_audit), y_audit)
        dens.append(np.maximum(d, 0.0))
        taus.append(s)
    return {
        "surface": sf.surface, "y": y_audit, "taus": np.array(taus),
        "dens": np.array(dens), "w_src": float(w_src), "w_static": w_static,
        "w_src_coarse": float(w_src_coarse),
        "w_static_coarse": w_static_coarse, "t": float(node.t),
    }


def fig_vs_three() -> str:
    node = common.running_node()
    ff = common.family_fits()
    t = node.t
    slice_ = ff["LQD"].model

    # Law side (closed form) and strike side (replication) on the same slice.
    w_rank = float(slice_.var_swap_strike())
    w_repl = common.fair_w_replication(common.w_curve(ff["LQD"], t))
    agree_rank_bp = abs(common.vs_vol_pct(w_rank, t)
                        - common.vs_vol_pct(w_repl, t)) * 100.0

    field = _field_side()
    v_src, v_static = field["w_src"], field["w_static"]
    agree_field_bp = abs(common.vs_vol_pct(v_src, t)
                         - common.vs_vol_pct(v_static, t)) * 100.0
    agree_coarse_bp = abs(common.vs_vol_pct(field["w_src_coarse"], t)
                          - common.vs_vol_pct(field["w_static_coarse"], t)
                          ) * 100.0
    gap_lv_bp = abs(common.vs_vol_pct(v_src, t)
                    - common.vs_vol_pct(w_repl, t)) * 100.0

    fig, axes = plt.subplots(1, 3, figsize=figstyle.ROW3)
    ax_a, ax_b, ax_c = axes

    # (a) strike side: the replication integrand across strikes.
    k, integ = common.strike_integrand(common.w_curve(ff["LQD"], t))
    ax_a.fill_between(k, integ, 0.0, color=PALETTE["model"], alpha=0.20, lw=0)
    ax_a.plot(k, integ, color=PALETTE["model"], lw=1.3)
    ax_a.plot(node.k, np.zeros_like(node.k), "|", color=PALETTE["data"],
              ms=3.0, mew=0.7, alpha=0.8, zorder=4)
    ax_a.set_xlim(-1.6, 1.2)
    ax_a.set_xlabel("log-moneyness $k$")
    ax_a.set_ylabel("integrand")
    ax_a.text(0.03, 0.94,
              rf"area $= w_{{\rm vs}}$"
              "\n"
              rf"$\sigma_{{\rm vs}}={common.vs_vol_pct(w_repl, t):.2f}\%$",
              transform=ax_a.transAxes, ha="left", va="top", fontsize=7.5)
    figstyle.panel(ax_a, "a", "against option prices")

    # (b) law side: the rank integrand on the slice's own logit grid.
    z = slice_.z
    from scipy.special import expit
    integ_z = -2.0 * slice_.q_z * slice_.u * expit(-z)
    mask = np.abs(z) <= 12.0
    zc, ic = z[mask], integ_z[mask]
    ax_b.fill_between(zc, ic, 0.0, where=ic >= 0, color=PALETTE["alt"],
                      alpha=0.30, lw=0)
    ax_b.fill_between(zc, ic, 0.0, where=ic < 0, color=PALETTE["data"],
                      alpha=0.25, lw=0)
    ax_b.plot(zc, ic, color=PALETTE["alt"], lw=1.3)
    ax_b.axhline(0.0, color=PALETTE["muted"], lw=0.6)
    ax_b.set_xlabel("log-odds $z$")
    ax_b.set_ylabel("integrand")
    ax_b.text(0.03, 0.94,
              "signed area:\nthe same number\n"
              rf"(to {agree_rank_bp:.2f} vol bp)",
              transform=ax_b.transAxes, ha="left", va="top", fontsize=7.5)
    figstyle.panel(ax_b, "b", "against the law")

    # (c) field side: the sheet's local volatility with occupation contours.
    y_plot = np.linspace(0.74, 1.32, 220)
    tau_plot = np.linspace(1e-4, t, 90)
    theta = field["surface"].theta.ravel()
    v_map = np.empty((tau_plot.size, y_plot.size))
    for i, s in enumerate(tau_plot):
        v_map[i] = field["surface"].basis(y_plot, float(s)) @ theta
    sig_map = 100 * np.sqrt(np.maximum(v_map, 0.0))
    pcm = ax_c.pcolormesh(y_plot, tau_plot, sig_map,
                          cmap=figstyle.HEATMAP, shading="auto",
                          vmax=float(np.percentile(sig_map, 98.0)),
                          rasterized=True)
    fig.colorbar(pcm, ax=ax_c, label=r"$\sigma_{\rm loc}$ (%)", pad=0.02)
    d_plot = np.empty((field["taus"].size, y_plot.size))
    for i in range(field["taus"].size):
        d_plot[i] = np.interp(y_plot, field["y"], field["dens"][i])
    levels = np.max(d_plot) * np.array([0.05, 0.2, 0.5, 0.8])
    ax_c.contour(y_plot, field["taus"], d_plot, levels=levels,
                 colors="white", linewidths=0.6, alpha=0.85)
    ax_c.plot([1.0], [0.0], "v", color=PALETTE["data"], ms=6.0, zorder=5,
              clip_on=False)
    ax_c.set_xlabel("strike ratio $y$")
    ax_c.set_ylabel(r"$\tau$ (years)")
    ax_c.grid(False)
    figstyle.panel(ax_c, "c", "along paths: the field")

    figstyle.save(fig, "fig_vs_three")

    STORE.add("three", "VsThreeSvsPct", num(common.vs_vol_pct(w_repl, t)),
              "running slice fair var-swap vol, strike-side replication (%)")
    STORE.add("three", "VsAgreeRankBp", num(agree_rank_bp, 2),
              "law-side closed form vs strike-side replication (vol bp)")
    STORE.add("three", "VsFieldSvsPct", num(common.vs_vol_pct(v_src, t)),
              "SPY sheet fair var-swap vol at the running expiry, field side (%)")
    STORE.add("three", "VsAgreeFieldBp", num(agree_field_bp, 1),
              "field-side backward solve vs the sheet's own strike-side "
              "replication, time step refined 8x (vol bp)")
    STORE.add("three", "VsAgreeFieldCoarseBp", num(agree_coarse_bp, 1),
              "the same two reads at the march's own time step (vol bp)")
    STORE.add("three", "VsLvGapBp", num(gap_lv_bp, 1),
              "sheet vs running slice fair-strike gap (vol bp) — the identifiability gap")
    return (f"rank agree {agree_rank_bp:.2f} bp, field agree "
            f"{agree_field_bp:.2f} bp, LV gap {gap_lv_bp:.1f} bp")
