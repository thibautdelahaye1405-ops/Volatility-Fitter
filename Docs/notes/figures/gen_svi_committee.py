"""Committee-revision figures for Note 02 (arc R4, review of 2026-07-24).

Four figures the committee asked for by name, each from production modules:

fig_svimom_momentmap.pdf  the ACTUAL moment map p* = (2-beta)^2 / (8 beta)
                          and its conditioning (explodes at 0, collapses at 2)
fig_svimom_bumps.pdf      5-handle bump-response matrix: JW is a normalized
                          quoting convention, not an orthogonal tail/belly
                          decomposition (an ATM bump moves the ACTUAL tails)
fig_svimom_mixture.pdf    the arbitrage-free expressiveness benchmark: a
                          martingale lognormal mixture (g >= 0 by construction)
                          fitted by SVI / LQD / MCS on equal footing
fig_svimom_atlas.pdf      jw_to_raw condition atlas over the (psi, p+c) wedge
                          with the 12 reference-fixture nodes overlaid
svi_committee_tables.tex  prose macros
svi_committee_numbers.json auditable payload
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import ndtr

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(OUT))

from style import PALETTE, label_panel, save, setup  # noqa: E402
from svi_moments_reference import raw_to_jw  # noqa: E402
from volfit.core.black import implied_vol  # noqa: E402
from volfit.models.diagnostics import belly_certificate, durrleman_g  # noqa: E402
from volfit.models.lqd.calibrate import calibrate_slice  # noqa: E402
from volfit.models.sigmoid import calibrate_sigmoid  # noqa: E402
from volfit.models.svi_jw.calibrate import _LEE_SLOPE_MAX, calibrate_svi  # noqa: E402
from volfit.models.svi_jw.svi import SVIJW, jw_to_raw  # noqa: E402

setup()
INK, MUTED = PALETTE["ink"], PALETTE["muted"]
TEAL, BLUE, RUST, AMBER = (
    PALETTE["teal"], PALETTE["blue"], PALETTE["rust"], PALETTE["amber"],
)

TAU = 0.5
BASE_JW = SVIJW(t=TAU, v=0.0425, psi=-0.25, p=0.75, c=0.25, v_tilde=0.034)
MACROS: list[str] = []
NUMBERS: dict = {}


def add(macro: str) -> None:
    MACROS.append(macro)


def p_star(beta: np.ndarray) -> np.ndarray:
    """Lee's critical-moment budget beyond the first moment."""
    return (2.0 - beta) ** 2 / (8.0 * beta)


# ------------------------------------------------------------- 1. moment map
def fig_momentmap() -> None:
    beta = np.linspace(0.02, 1.999, 800)
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4))
    ax = axes[0]
    ax.semilogy(beta, p_star(beta), color=TEAL)
    ax.axvline(_LEE_SLOPE_MAX, color=AMBER, lw=1.2, ls="--")
    ax.axvline(2.0, color=RUST, lw=1.2, ls=":")
    ax.set_xlabel(r"wing slope $\beta$")
    ax.set_ylabel(r"moment budget $p^\star$")
    ax.text(_LEE_SLOPE_MAX - 0.03, 2e-3, r"$\beta_{\max}$", color=AMBER,
            ha="right", fontsize=10)
    label_panel(ax, "A")
    ax = axes[1]
    sens = (4.0 - beta**2) / (8.0 * beta**2)  # |dp*/dbeta|
    ax.semilogy(beta, sens, color=BLUE)
    ax.axvline(_LEE_SLOPE_MAX, color=AMBER, lw=1.2, ls="--")
    ax.set_xlabel(r"wing slope $\beta$")
    ax.set_ylabel(r"$|\,\mathrm{d}p^\star/\mathrm{d}\beta\,|$")
    label_panel(ax, "B")
    fig.tight_layout()
    save(fig, OUT / "fig_svimom_momentmap.pdf")
    add(rf"\newcommand{{\svimompstarcap}}{{{p_star(np.array([_LEE_SLOPE_MAX]))[0]:.1e}}}")


# ----------------------------------------------------- 2. bump-response matrix
def _delta_k(raw, delta: float, is_call: bool) -> float:
    """Strike (log-moneyness) where the Black delta of the MODEL smile equals
    ``delta`` (call) / ``-delta`` (put) — bisection on N(d1)."""
    target = delta if is_call else 1.0 - delta
    lo, hi = -2.0, 2.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        w = float(raw.total_variance(mid))
        d1 = (-mid + 0.5 * w) / np.sqrt(w)
        if ndtr(d1) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _responses(jw: SVIJW) -> dict[str, float]:
    from volfit.models.diagnostics import numeric_var_swap_w

    raw = jw_to_raw(jw)
    sig = lambda k: float(np.sqrt(raw.total_variance(k) / jw.t))  # noqa: E731
    kc, kp = _delta_k(raw, 0.25, True), _delta_k(raw, 0.25, False)
    beta_l, beta_r = raw.wing_slopes()
    return {
        r"ATM vol": sig(0.0),
        r"25$\Delta$ RR": sig(kc) - sig(kp),
        r"25$\Delta$ BF": 0.5 * (sig(kc) + sig(kp)) - sig(0.0),
        r"$\beta_L$": beta_l,
        r"$\beta_R$": beta_r,
        r"$p^\star_R$": float(p_star(np.array([beta_r]))[0]),
        r"$w_\star$": jw.v_tilde * jw.t,
        r"var swap": float(np.sqrt(numeric_var_swap_w(raw) / jw.t)),
    }


def fig_bumps() -> None:
    bumps = [
        (r"$+\Delta v$ (ATM level)", "v", 0.004),
        (r"$+\Delta\psi$ (ATM slope)", "psi", 0.05),
        (r"$+\Delta p$ (left wing)", "p", 0.10),
        (r"$+\Delta c$ (right wing)", "c", 0.10),
        (r"$+\Delta\widetilde v$ (floor)", "v_tilde", 0.002),
    ]
    base = _responses(BASE_JW)
    cols = list(base)
    grid = np.zeros((len(bumps), len(cols)))
    for i, (_lbl, field, delta) in enumerate(bumps):
        jw = SVIJW(
            **{**BASE_JW.__dict__, field: getattr(BASE_JW, field) + delta}
        )
        resp = _responses(jw)
        grid[i] = [resp[c] - base[c] for c in cols]
    # Per-column normalization: sign + relative magnitude (an atlas of WHERE
    # a bump lands, not a common unit — the caption spells the units out).
    norm = grid / np.maximum(np.abs(grid).max(axis=0, keepdims=True), 1e-300)
    fig, ax = plt.subplots(figsize=(7.6, 3.2))
    ax.imshow(norm, cmap="RdBu_r", vmin=-1.0, vmax=1.0, aspect="auto")
    ax.set_xticks(range(len(cols)), cols, fontsize=10)
    ax.set_yticks(range(len(bumps)), [b[0] for b in bumps], fontsize=10)
    ax.grid(False)
    for i in range(len(bumps)):
        for j in range(len(cols)):
            v = grid[i, j]
            txt = f"{v:+.4f}" if abs(v) >= 5e-5 else ("0" if v == 0 else f"{v:+.0e}")
            ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                    color=INK if abs(norm[i, j]) < 0.6 else "white")
    fig.tight_layout()
    save(fig, OUT / "fig_svimom_bumps.pdf")
    # The committee's headline: an ATM-level bump moves the ACTUAL tails.
    col_beta_r = cols.index(r"$\beta_R$")
    col_pstar = cols.index(r"$p^\star_R$")
    add(rf"\newcommand{{\svimombumpbetaR}}{{{grid[0, col_beta_r]:+.4f}}}")
    add(rf"\newcommand{{\svimombumppstar}}{{{grid[0, col_pstar]:+.4f}}}")
    NUMBERS["bump_matrix"] = {b[0]: dict(zip(cols, map(float, row)))
                              for b, row in zip(bumps, grid)}


# ------------------------------------------- 3. arbitrage-free mixture bench
def _mixture_w(k: np.ndarray, tau: float) -> np.ndarray:
    """Implied total variance of a martingale two-lognormal mixture — a
    GENUINE distribution, so the smile is arbitrage-free by construction."""
    q = np.array([0.65, 0.35])
    sig = np.array([0.14, 0.42])
    f2 = 0.90
    f = np.array([(1.0 - q[1] * f2) / q[0], f2])  # sum q_i f_i = 1
    strike = np.exp(k)
    call = np.zeros_like(k, dtype=float)
    for qi, fi, si in zip(q, f, sig):
        s = si * np.sqrt(tau)
        d1 = (np.log(fi / strike) + 0.5 * s * s) / s
        call += qi * (fi * ndtr(d1) - strike * ndtr(d1 - s))
    iv = np.array([float(implied_vol(kk, cc, tau)) for kk, cc in zip(k, call)])
    return iv * iv * tau


def fig_mixture() -> None:
    tau = 0.25
    k = np.linspace(-0.55, 0.55, 37)
    w = _mixture_w(k, tau)

    class _W:  # SmileModel shim for the diagnostics helpers
        def __init__(self, fn):
            self.implied_w = fn

    # The target's OWN g on a dense analytic evaluation (not interpolation):
    # a genuine law prices it, so this is >= 0 up to inversion noise.
    dense = np.linspace(float(k.min()), float(k.max()), 801)
    target_g = durrleman_g(_W(lambda kk: _mixture_w(np.asarray(kk, float), tau)), dense)
    g_min_target = float(np.nanmin(target_g[np.isfinite(target_g)]))
    assert g_min_target > -1e-4, "mixture target must be arbitrage-free"

    svi = calibrate_svi(k, w, tau).raw
    lqd = calibrate_slice(k, w, tau, n_order=6, reg_lambda=1e-6).slice
    mcs = calibrate_sigmoid(k, w, tau, n_cores=2, ridge=1e-2)
    # Held-out: fit on even-index quotes, score on the held-out odd ones.
    ho_svi = calibrate_svi(k[::2], w[::2], tau).raw
    ho_lqd = calibrate_slice(k[::2], w[::2], tau, n_order=6, reg_lambda=1e-6).slice
    ho_mcs = calibrate_sigmoid(k[::2], w[::2], tau, n_cores=2, ridge=1e-2)

    iv_t = np.sqrt(w / tau)
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.5))
    ax = axes[0]
    ax.plot(k, 100 * iv_t, "o", ms=3.5, color=INK, label="mixture target")
    stats = {}
    for name, model, ho, color in (
        ("SVI", svi, ho_svi, RUST), ("LQD", lqd, ho_lqd, TEAL), ("MCS", mcs, ho_mcs, BLUE),
    ):
        iv_m = np.sqrt(np.maximum(model.implied_w(dense), 1e-12) / tau)
        ax.plot(dense, 100 * iv_m, color=color, lw=1.8, label=name)
        err = (np.sqrt(np.maximum(model.implied_w(k), 1e-12) / tau) - iv_t) * 1e4
        held = (np.sqrt(np.maximum(ho.implied_w(k[1::2]), 1e-12) / tau)
                - iv_t[1::2]) * 1e4
        cert = belly_certificate(model, float(k.min()), float(k.max()))
        stats[name] = {
            "rms_bp": float(np.sqrt(np.mean(err**2))),
            "heldout_rms_bp": float(np.sqrt(np.mean(held**2))),
            "min_g": float(cert.min_g),
            "certified": bool(cert.certified),
        }
        axes[1].plot(k, err, color=color, lw=1.6, label=name)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("implied vol (%)")
    ax.legend()
    label_panel(ax, "A")
    ax = axes[1]
    ax.axhline(0.0, color=INK, lw=0.8)
    ax.set_xlabel(r"log-moneyness $k$")
    ax.set_ylabel("fit error (vol bp)")
    label_panel(ax, "B")
    fig.tight_layout()
    save(fig, OUT / "fig_svimom_mixture.pdf")

    add(rf"\newcommand{{\svimommixtargetg}}{{{g_min_target:+.3f}}}")
    for name in ("SVI", "LQD", "MCS"):
        s = stats[name]
        add(rf"\newcommand{{\svimommix{name.lower()}rms}}{{{s['rms_bp']:.1f}}}")
        add(rf"\newcommand{{\svimommix{name.lower()}ho}}{{{s['heldout_rms_bp']:.1f}}}")
        add(rf"\newcommand{{\svimommix{name.lower()}ming}}{{{s['min_g']:+.3f}}}")
    NUMBERS["mixture"] = {"target_min_g": g_min_target, **stats}


# ------------------------------------------------------- 4. condition atlas
def _jw_condition(jw: SVIJW) -> float:
    """Condition number of the scaled jw->raw Jacobian at one JW point
    (relative central differences; rows scaled by the raw magnitudes)."""
    handles = ("v", "psi", "p", "c", "v_tilde")
    base = jw_to_raw(jw)
    base_vec = np.array([base.a, base.b, base.rho, base.m, base.sigma])
    jac = np.zeros((5, 5))
    for j, h in enumerate(handles):
        step = max(abs(getattr(jw, h)), 0.02) * 1e-4
        up = jw_to_raw(SVIJW(**{**jw.__dict__, h: getattr(jw, h) + step}))
        dn = jw_to_raw(SVIJW(**{**jw.__dict__, h: getattr(jw, h) - step}))
        up_vec = np.array([up.a, up.b, up.rho, up.m, up.sigma])
        dn_vec = np.array([dn.a, dn.b, dn.rho, dn.m, dn.sigma])
        jac[:, j] = (up_vec - dn_vec) / (2.0 * step) * step / 1e-4  # relative col
    jac /= np.maximum(np.abs(base_vec), 1e-3)[:, None]  # relative rows
    if not np.all(np.isfinite(jac)):
        return np.nan
    sv = np.linalg.svd(jac, compute_uv=False)
    return float(sv[0] / max(sv[-1], 1e-300))


def fig_atlas() -> None:
    psi_grid = np.linspace(-0.45, 0.45, 121)
    # Total wing weight p + c, LOG-spaced: the normalized JW wings scale as
    # beta/sqrt(w0), so real short-dated nodes sit at p + c of order 10-100.
    s_grid = np.geomspace(0.15, 120.0, 111)
    cond = np.full((s_grid.size, psi_grid.size), np.nan)
    for i, s_tot in enumerate(s_grid):
        for j, psi in enumerate(psi_grid):
            if abs(psi) >= 0.25 * s_tot * 0.98 or psi == 0.0:
                continue  # outside/at the regular domain -p/2 < psi < c/2
            jw = SVIJW(t=TAU, v=0.0425, psi=psi, p=0.5 * s_tot, c=0.5 * s_tot,
                       v_tilde=0.034)
            try:
                cond[i, j] = np.log10(_jw_condition(jw))
            except Exception:
                continue
    fig, ax = plt.subplots(figsize=(6.9, 3.8))
    im = ax.pcolormesh(psi_grid, s_grid, np.clip(cond, 1.0, 8.0),
                       cmap="magma_r", shading="auto")
    ax.set_yscale("log")
    fig.colorbar(im, ax=ax, label=r"$\log_{10}$ cond of scaled $\partial$raw$/\partial$JW")
    ax.axvline(0.0, color=RUST, lw=1.4, ls="--")
    ax.text(0.02, 0.35, r"singular stratum $\psi=0$", color=RUST, fontsize=9.5)
    # The 12 reference-fixture nodes (Massive 2026-07-18): where real chains
    # actually sit in this atlas. Skipped gracefully when the fixture is absent.
    fixture = ROOT / "tmp" / "volfit_surfaces_20260718_1324.json"
    pts = []
    if fixture.exists():
        doc = json.loads(fixture.read_text())
        for tkr in doc["tickers"]:
            for node in tkr["nodes"]:
                colsn = node["inputs"]["preparedColumns"]
                rows = np.array(node["inputs"]["prepared"], dtype=float)
                fit = calibrate_svi(rows[:, colsn.index("k")],
                                    rows[:, colsn.index("wMid")],
                                    float(node["tau"]))
                jwp = raw_to_jw(fit.raw, float(node["tau"]))
                pts.append((jwp["psi"], jwp["p"] + jwp["c"]))
        if pts:
            arr = np.array(pts)
            ax.plot(arr[:, 0], arr[:, 1], "o", ms=5, mfc="white", mec=INK,
                    mew=1.1, label="reference-fixture nodes (n=12)")
            ax.legend(loc="lower left")
    ax.set_xlabel(r"ATM total-vol slope $\psi$")
    ax.set_ylabel(r"total wing weight $p + c$")
    save(fig, OUT / "fig_svimom_atlas.pdf")
    if pts:
        psis = np.array([p[0] for p in pts])
        add(rf"\newcommand{{\svimomatlasminpsi}}{{{np.abs(psis).min():.3f}}}")
        NUMBERS["atlas_nodes"] = [list(map(float, p)) for p in pts]


def main() -> None:
    fig_momentmap()
    fig_bumps()
    fig_mixture()
    fig_atlas()
    (OUT / "svi_committee_tables.tex").write_text(
        "% generated by gen_svi_committee.py - do not edit\n" + "\n".join(MACROS) + "\n",
        encoding="utf-8",
    )
    (OUT / "svi_committee_numbers.json").write_text(
        json.dumps(NUMBERS, indent=2), encoding="utf-8"
    )
    m = NUMBERS["mixture"]
    print(
        "committee figures written; mixture target min g "
        f"{m['target_min_g']:+.3f}; RMS bp SVI {m['SVI']['rms_bp']:.1f} / "
        f"LQD {m['LQD']['rms_bp']:.1f} / MCS {m['MCS']['rms_bp']:.1f}"
    )


if __name__ == "__main__":
    main()
