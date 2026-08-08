"""Figure 10.7 -- the audit: were the error bars true?

A seeded synthetic experiment (the chapter's only randomness): the true ATM
level diffuses at 30 vol bp per sqrt(day) for 500 days and jumps five vol
points twice; every day a noisy observation arrives (30 bp stated noise,
100 bp on every seventh, wide-spread, day).  The scalar filter is run with
a starved, an honest, and a surprise-widened honest prediction budget.  Panel
(a): a window around a jump.  Panel (b): the standardized error's std
against the assumed walk scale -- error bars are true only near the true
scale, and a starved budget is confidently wrong.  Panel (c): recovery
after the jump -- starved is slow as well as overconfident.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

import figstyle
from figstyle import PALETTE
from macros import STORE, num

SEED = 20260807
T_DAYS = 500
Q_TRUE = 0.0030          # 30 vol bp per sqrt(day)
NOISE_BASE = 0.0030      # stated per-day observation noise (30 bp)
NOISE_WIDE = 0.0100      # every 7th day is a wide-spread day (100 bp)
SHOCK_DAYS = (151, 320)  # neither falls on a wide-spread (every-7th) day
SHOCK_SIZE = 0.05        # +5 vol points, spreads unchanged
GATE_SIGMA = 3.0
GATE_CAP = 25.0


def _world():
    rng = np.random.default_rng(SEED)
    steps = Q_TRUE * rng.standard_normal(T_DAYS)
    truth = 0.20 + np.cumsum(steps)
    for d in SHOCK_DAYS:
        truth[d:] += SHOCK_SIZE
    noise_sd = np.where(np.arange(T_DAYS) % 7 == 3, NOISE_WIDE, NOISE_BASE)
    obs = truth + noise_sd * rng.standard_normal(T_DAYS)
    return truth, obs, noise_sd


def _run(obs, noise_sd, q_walk: float, gated: bool):
    """Scalar predict/update chain; returns posterior means and variances."""
    m = obs[0]
    v = NOISE_WIDE ** 2
    means, variances = [m], [v]
    for t_i in range(1, obs.size):
        v_pred = v + q_walk ** 2
        r = noise_sd[t_i] ** 2
        if gated:
            ratio = abs(obs[t_i] - m) / np.sqrt(v_pred + r)
            if ratio > GATE_SIGMA:
                v_pred *= min((ratio / GATE_SIGMA) ** 2, GATE_CAP)
        gain = v_pred / (v_pred + r)
        m = m + gain * (obs[t_i] - m)
        v = (1.0 - gain) * v_pred
        means.append(m)
        variances.append(v)
    return np.asarray(means), np.asarray(variances)


def _zstd(truth, means, variances) -> float:
    z = (truth - means) / np.sqrt(variances)
    return float(np.std(z[1:]))


def _recovery(truth, means) -> np.ndarray:
    """Mean |error| (vol pts) vs days since a jump, averaged over jumps."""
    horizons = np.arange(0, 7)
    err = np.zeros_like(horizons, dtype=float)
    for d in SHOCK_DAYS:
        err += np.abs(means[d + horizons] - truth[d + horizons])
    return 1e2 * err / len(SHOCK_DAYS)


def fig_flt_audit() -> str:
    truth, obs, noise_sd = _world()

    m_starved, v_starved = _run(obs, noise_sd, 0.0010, gated=False)
    m_honest, v_honest = _run(obs, noise_sd, Q_TRUE, gated=False)
    m_gated, v_gated = _run(obs, noise_sd, Q_TRUE, gated=True)

    fig, (ax_a, ax_b, ax_c) = plt.subplots(1, 3, figsize=figstyle.ROW3)

    # (a) the window around the first jump.
    w0, w1 = SHOCK_DAYS[0] - 6, SHOCK_DAYS[0] + 16
    days = np.arange(w0, w1)
    ax_a.plot(days, 1e2 * truth[w0:w1], color=PALETTE["ink"], lw=1.3,
              label="truth")
    ax_a.plot(days, 1e2 * obs[w0:w1], "o", ms=2.6, color=PALETTE["data"],
              alpha=0.8, label="observations")
    band_lo = 1e2 * (m_honest[w0:w1] - np.sqrt(v_honest[w0:w1]))
    band_hi = 1e2 * (m_honest[w0:w1] + np.sqrt(v_honest[w0:w1]))
    ax_a.fill_between(days, band_lo, band_hi, color=PALETTE["band"],
                      alpha=0.9, zorder=1)
    ax_a.plot(days, 1e2 * m_honest[w0:w1], color=PALETTE["model"], lw=1.4,
              label="honest budget")
    ax_a.plot(days, 1e2 * m_starved[w0:w1], color=PALETTE["third"], lw=1.4,
              label="starved budget")
    ax_a.set_xlabel("day")
    ax_a.set_ylabel("ATM level (%)")
    ax_a.legend(loc="lower right", fontsize=6.6)
    figstyle.panel(ax_a, "a", "a five-point jump, followed or lagged")

    # (b) the audit curve: Z std vs the assumed walk scale.
    q_grid_bp = np.array([5, 10, 15, 20, 30, 45, 60, 90], dtype=float)
    zstds = [
        _zstd(truth, *_run(obs, noise_sd, q_bp * 1e-4, gated=False))
        for q_bp in q_grid_bp
    ]
    ax_b.semilogy(q_grid_bp, zstds, "o-", ms=3.5, color=PALETTE["model"],
                  lw=1.3)
    ax_b.axhline(1.0, color=PALETTE["muted"], lw=0.9, ls=":")
    ax_b.axvline(1e4 * Q_TRUE, color=PALETTE["muted"], lw=0.9, ls="--")
    ax_b.annotate("true scale", (1e4 * Q_TRUE, ax_b.get_ylim()[0] * 1.3),
                  xytext=(1e4 * Q_TRUE + 6, ax_b.get_ylim()[0] * 1.6),
                  fontsize=7.5, color=PALETTE["muted"])
    ax_b.annotate("std$(\\mathcal{Z})=1$", (52, 1.06),
                  fontsize=7.5, color=PALETTE["muted"])
    ax_b.set_xlabel(r"assumed walk scale $q_{\mathrm{walk}}$ (bp/$\sqrt{d}$)")
    ax_b.set_ylabel(r"std of $\mathcal{Z}$")
    figstyle.panel(ax_b, "b", "the audit curve")

    # (c) recovery after the jump.
    rec = {
        "starved": (_recovery(truth, m_starved), PALETTE["third"]),
        "honest": (_recovery(truth, m_honest), PALETTE["model"]),
        "honest + widening": (_recovery(truth, m_gated), PALETTE["alt"]),
    }
    for label, (curve, color) in rec.items():
        ax_c.plot(np.arange(7), curve, "o-", ms=3.2, lw=1.3, color=color,
                  label=label)
    ax_c.set_xlabel("days since the jump")
    ax_c.set_ylabel("mean |error| (vol pts)")
    ax_c.legend(loc="upper right", fontsize=7.0)
    figstyle.panel(ax_c, "c", "starved is slow as well as sure")

    figstyle.save(fig, "fig_flt_audit")

    z_starved = _zstd(truth, m_starved, v_starved)
    z_honest = _zstd(truth, m_honest, v_honest)
    z_gated = _zstd(truth, m_gated, v_gated)
    rec_s, rec_h, rec_g = (rec["starved"][0], rec["honest"][0],
                           rec["honest + widening"][0])
    STORE.add("audit", "FiltAuditDays", str(T_DAYS),
              "length of the synthetic history (days)")
    STORE.add("audit", "FiltAuditQTrueBp", num(1e4 * Q_TRUE, 0),
              "true walk scale (vol bp per sqrt day)")
    STORE.add("audit", "FiltAuditShockPts", num(1e2 * SHOCK_SIZE, 0),
              "jump size (vol points)")
    STORE.add("audit", "FiltAuditZstdStarved", num(z_starved, 1),
              "std of Z under the starved budget (10 bp)")
    STORE.add("audit", "FiltAuditZstdHonest", num(z_honest, 2),
              "std of Z under the honest budget (30 bp)")
    STORE.add("audit", "FiltAuditZstdGated", num(z_gated, 2),
              "std of Z under the gated honest budget")
    STORE.add("audit", "FiltAuditDayZeroStarved", num(rec_s[0], 1),
              "starved-budget |error| on the jump day (pts)")
    STORE.add("audit", "FiltAuditDayZeroHonest", num(rec_h[0], 1),
              "honest-budget |error| on the jump day (pts)")
    STORE.add("audit", "FiltAuditDayZeroGate", num(rec_g[0], 2),
              "gated-budget |error| on the jump day (pts)")
    STORE.add("audit", "FiltAuditDayThreeStarved", num(rec_s[3], 1),
              "starved-budget |error| three days after the jump (pts)")
    return (f"Z std starved {z_starved:.1f} / honest {z_honest:.2f} / gated "
            f"{z_gated:.2f}; day-0 err {rec_s[0]:.1f}/{rec_h[0]:.1f}/"
            f"{rec_g[0]:.2f} pts")
