"""Figures and tables for Note 15 (observation Kalman filtering).

Everything is computed by PRODUCTION code, never a re-implementation:

  fig_kalman_case.pdf      the note's close-strike case file pushed through
                           volfit.calib.observation_filter.kalman_update:
                           (A) per-handle gains, (B) where each posterior
                           lands between prediction and observation
  fig_kalman_backtest.pdf  zeta calibration and held-out ATM error from the
                           3-regime temporal backtest merged summaries
                           (backend/backtest/results/
                            <regime>_observation_filter_merged.json)
  kalman_tables.tex        \\input-able macros for every number the note quotes,
                           including the v2 full-regime sweep (overlay vs
                           active, adaptive Q on; <regime>_observation_filter_
                           v2_merged.json) behind FINDINGS F9-F11

The script also executes the note's Appendix C reference listing against the
production ``kalman_update`` on a random-seeded 3x3 problem and emits the max
deviation (\\KalRefAgreement). Missing backtest JSONs degrade gracefully: the
regime is skipped in the figure and its macros emit "--", so the note still
builds. Run with PYTHONPATH containing backend/ (volfit is pip-installed
editable in the repo .venv, so the plain venv python works too).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from style import PALETTE, WIDE, label_panel, save, setup  # noqa: E402

from volfit.calib.observation_filter import kalman_update  # noqa: E402

OUT = Path(__file__).resolve().parent
RESULTS = OUT.parents[2] / "backend" / "backtest" / "results"
setup()
TEAL, RUST, SLATE, AMBER = (
    PALETTE["teal"], PALETTE["rust"], PALETTE["muted"], PALETTE["amber"],
)

HANDLE_LABELS = ("ATM level", "ATM skew", "ATM curvature")

#: (results-file stem, macro suffix, display label) for the three regimes.
REGIMES = (
    ("spike_aug2024", "Spike", "Aug 2024\nspike"),
    ("high_oct2022", "High", "Oct 2022\nhigh-vol"),
    ("low_jul2023", "Low", "Jul 2023\nlow-vol"),
)
#: The decision-point cell of the backtest sweep (FINDINGS F6/F7).
SCEN, COV, BUCKET = "thinned", "jacobian", ">30d"

#: Numbers recorded in backtest/FINDINGS_observation_filter.md that are not
#: reproducible from the merged summaries (the F1 incident ran pre-fix, and
#: the post-fix EEM/EFA numbers come from the Phase-5 single-pair run). They
#: are centralized here so the note never retypes a measured number.
FINDINGS_F1 = {
    "KalBlowupMinPts": "3",     # full-covariance posterior ATM error range...
    "KalBlowupMaxPts": "28",    # ...on EEM/EFA, in vol POINTS (F1)
    "KalEEMPost": "4.5",        # EEM posterior ATM error after the fix (bp)
    "KalEEMMeas": "8.1",        # EEM raw-measurement baseline (bp)
    "KalEEMZeta": "0.14",       # EEM zeta mean after the fix
    "KalEFAZeta": "0.26",       # EFA zeta mean after the fix (conservative)
}


# --------------------------------------------------------------------- helpers
def sci(x: float) -> str:
    """LaTeX mantissa-times-power form for use inside math mode."""
    if x == 0.0:
        return "0"
    e = int(np.floor(np.log10(abs(x))))
    return rf"{x / 10.0 ** e:.1f}\times10^{{{e}}}"


def _load_regime(stem: str) -> list[dict] | None:
    path = RESULTS / f"{stem}_observation_filter_merged.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["summary"]


def _load_v2(stem: str) -> list[dict] | None:
    """The v2 full sweep (overlay vs ACTIVE, adaptive Q on) — FINDINGS F9–F11."""
    path = RESULTS / f"{stem}_observation_filter_v2_merged.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))["summary"]


def _row(rows: list[dict], scenario: str, cov: str, bp: float, bucket: str):
    for r in rows:
        if (
            r["scenario"] == scenario
            and r["cov_mode"] == cov
            and float(r["process_bp"]) == bp
            and r["bucket"] == bucket
        ):
            return r
    return None


def _row_v2(rows: list[dict], scenario: str, mode: str, bucket: str,
            cov: str = "jacobian"):
    for r in rows:
        if (
            r["scenario"] == scenario
            and r["cov_mode"] == cov
            and r["mode"] == mode
            and r["bucket"] == bucket
        ):
            return r
    return None


# ---------------------------------------------------------- Figure 1: case file
def case_figure(macros: dict[str, str]) -> None:
    """The Note 15 SS7 case file, computed by the production kalman_update.

    Diagonal covariances (the production DIAGONAL_UPDATE convention): the
    prediction is the transported previous state, the observation carries a
    contradiction-inflated curvature variance, and the update accepts the
    level/skew move while rejecting the curvature kink."""
    m_pred = np.array([0.20, -0.35, 0.10])       # 20.0 %, -0.35, 0.10
    sd_pred = np.array([0.0030, 0.08, 0.05])     # sqrt(diag P^-)
    z = np.array([0.204, -0.37, 0.55])           # the noisy handle observation
    sd_obs = np.array([0.0015, 0.05, 0.30])      # sqrt(diag R) after inflation

    upd = kalman_update(m_pred, np.diag(sd_pred**2), z, np.diag(sd_obs**2))
    gains = np.diag(upd.gain)

    macros["KalGainLevel"] = f"{gains[0]:.2f}"
    macros["KalGainSkew"] = f"{gains[1]:.2f}"
    macros["KalGainCurv"] = f"{gains[2]:.3f}"
    macros["KalPostLevel"] = f"{100.0 * upd.mean[0]:.2f}"
    macros["KalPostSkew"] = f"{upd.mean[1]:.3f}"
    macros["KalPostCurv"] = f"{upd.mean[2]:.3f}"

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=WIDE)

    # Panel A: the per-handle scalar gains.
    y = np.arange(3)[::-1]
    ax_a.barh(y, gains, height=0.55, color=[TEAL, TEAL, RUST])
    for yi, g in zip(y, gains):
        ax_a.text(g + 0.02, yi, f"{g:.2f}" if g > 0.1 else f"{g:.3f}",
                  va="center", fontsize=10, color=PALETTE["ink"])
    ax_a.set_yticks(y, HANDLE_LABELS)
    ax_a.set_xlim(0.0, 1.06)
    ax_a.set_xlabel(r"Kalman gain $K=p/(p+r)$")
    label_panel(ax_a, "A")

    # Panel B: where the posterior lands on the prediction->observation segment
    # (in the normalized coordinate the posterior position IS the gain).
    ax_b.hlines(y, 0.0, 1.0, color=PALETTE["grid"], lw=2.0, zorder=1)
    ax_b.scatter(np.zeros(3), y, s=55, color=SLATE, zorder=3,
                 label=r"prediction $m^-$")
    ax_b.scatter(np.ones(3), y, s=55, color=RUST, marker="s", zorder=3,
                 label=r"observation $z$")
    ax_b.scatter(gains, y, s=80, color=TEAL, marker="D", zorder=4,
                 label=r"posterior $m^+$")
    ax_b.annotate(
        "the stale-strike kink\nis rejected",
        xy=(gains[2], y[2]), xytext=(0.30, y[2] - 0.42),
        arrowprops={"arrowstyle": "->", "color": SLATE, "lw": 1.1},
        fontsize=9.5, color=SLATE,
    )
    ax_b.set_yticks(y, HANDLE_LABELS)
    ax_b.set_xlim(-0.08, 1.10)
    ax_b.set_ylim(-0.75, 2.55)
    ax_b.set_xlabel(r"position between $m^-$ (0) and $z$ (1)")
    ax_b.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), ncol=3,
                frameon=False, fontsize=9)
    label_panel(ax_b, "B")

    fig.tight_layout()
    save(fig, OUT / "fig_kalman_case.pdf")


# ------------------------------------------------------ Figure 2: the backtest
def backtest_figure(macros: dict[str, str]) -> None:
    """zeta calibration (bp=10 vs 30) and held-out ATM error per regime, at the
    decision cell (jacobian route, thinned scenario, >30 DTE bucket)."""
    loaded: list[tuple[str, str, list[dict]]] = []
    total_steps = 0
    shock_ratios: list[float] = []

    for stem, suffix, label in REGIMES:
        rows = _load_regime(stem)
        if rows is None:  # missing regime: figure skips it, macros say so
            for name in ("Zstd%sTen", "Zstd%sThirty", "ErrPost%s", "ErrMeas%s",
                         "ErrPred%s", "Win%s", "ContraJac%s", "ContraFac%s",
                         "ShockJac%s", "ShockFac%s"):
                macros["Kal" + name % suffix] = "--"
            continue
        loaded.append((suffix, label, rows))
        total_steps += sum(r["n"] for r in rows)

        r10 = _row(rows, SCEN, COV, 10.0, BUCKET)
        r30 = _row(rows, SCEN, COV, 30.0, BUCKET)
        macros[f"KalZstd{suffix}Ten"] = f"{r10['zeta_std'][0]:.2f}"
        macros[f"KalZstd{suffix}Thirty"] = f"{r30['zeta_std'][0]:.2f}"
        macros[f"KalErrPost{suffix}"] = f"{1e4 * r30['med_err_post'][0]:.1f}"
        macros[f"KalErrMeas{suffix}"] = f"{1e4 * r30['med_err_meas'][0]:.1f}"
        macros[f"KalErrPred{suffix}"] = f"{1e4 * r30['med_err_pred'][0]:.0f}"
        macros[f"KalWin{suffix}"] = f"{r30['win_vs_meas'][0]:.2f}"

        cj = _row(rows, "contradiction", "jacobian", 30.0, BUCKET)
        cf = _row(rows, "contradiction", "factors", 30.0, BUCKET)
        macros[f"KalContraJac{suffix}"] = f"{1e4 * cj['med_err_post'][0]:.1f}"
        macros[f"KalContraFac{suffix}"] = f"{1e4 * cf['med_err_post'][0]:.1f}"

        for cov in ("jacobian", "factors"):
            s10 = _row(rows, "shock", cov, 10.0, BUCKET)
            s30 = _row(rows, "shock", cov, 30.0, BUCKET)
            shock_ratios.append(s10["med_err_post"][0] / s30["med_err_post"][0])
        sj = _row(rows, "shock", "jacobian", 30.0, BUCKET)
        sf = _row(rows, "shock", "factors", 30.0, BUCKET)
        macros[f"KalShockJac{suffix}"] = f"{1e4 * sj['med_err_post'][0]:.1f}"
        macros[f"KalShockFac{suffix}"] = f"{1e4 * sf['med_err_post'][0]:.1f}"

    macros["KalStepsTotal"] = f"{total_steps:,}".replace(",", r"\,")
    if shock_ratios:
        macros["KalShockImproveMin"] = f"{min(shock_ratios):.0f}"
        macros["KalShockImproveMax"] = f"{max(shock_ratios):.0f}"
    else:
        macros["KalShockImproveMin"] = macros["KalShockImproveMax"] = "--"
    macros.setdefault("KalShockJacSpike", "--")
    macros.setdefault("KalShockFacSpike", "--")
    if not loaded:
        print("No merged backtest JSON found under", RESULTS, "- figure 2 skipped")
        return

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=WIDE)
    x = np.arange(len(loaded))
    labels = [lab for _, lab, _ in loaded]

    # Panel A: zeta std at bp = 10 vs 30 against the calibration target 1.
    z10 = [float(macros[f"KalZstd{s}Ten"]) for s, _, _ in loaded]
    z30 = [float(macros[f"KalZstd{s}Thirty"]) for s, _, _ in loaded]
    ax_a.bar(x - 0.19, z10, width=0.36, color=SLATE,
             label=r"clock $10\,$bp$/\sqrt{\mathrm{day}}$ (design note)")
    ax_a.bar(x + 0.19, z30, width=0.36, color=TEAL,
             label=r"clock $30\,$bp$/\sqrt{\mathrm{day}}$ (shipped)")
    ax_a.axhline(1.0, color=AMBER, lw=1.4, ls="--", zorder=1)
    ax_a.text(len(loaded) - 0.52, 1.08, "calibrated", color=AMBER, fontsize=9)
    ax_a.set_xticks(x, labels)
    ax_a.set_ylabel(r"$\zeta$ std (ATM, thinned, $>30$d)")
    ax_a.legend(frameon=False, fontsize=8.5, loc="upper right")
    label_panel(ax_a, "A")

    # Panel B: held-out ATM error, posterior vs the two baselines.
    pred = [float(macros[f"KalErrPred{s}"]) for s, _, _ in loaded]
    meas = [float(macros[f"KalErrMeas{s}"]) for s, _, _ in loaded]
    post = [float(macros[f"KalErrPost{s}"]) for s, _, _ in loaded]
    ax_b.bar(x - 0.25, pred, width=0.24, color=SLATE,
             label=r"prediction (gain $0$)")
    ax_b.bar(x, meas, width=0.24, color=RUST, label="raw measurement")
    ax_b.bar(x + 0.25, post, width=0.24, color=TEAL, label="filter posterior")
    ax_b.set_xticks(x, labels)
    ax_b.set_ylabel("median held-out ATM error (bp)")
    ax_b.legend(frameon=False, fontsize=8.5)
    label_panel(ax_b, "B")

    fig.tight_layout()
    save(fig, OUT / "fig_kalman_backtest.pdf")


# ------------------------------------------------- v2 sweep (overlay vs ACTIVE)
def v2_backtest_macros(macros: dict[str, str]) -> None:
    """Macros from the v2 full-regime sweep (overlay AND active modes, adaptive
    Q on; FINDINGS F9–F11). In active mode the committed fit IS the one-stage
    MAP solution, so ``med_err_post == med_err_meas`` there and the baseline is
    the OVERLAY run's raw-measurement column of the same sweep."""
    total_steps = 0
    all_loaded = True
    zetas: list[float] = []

    for stem, suffix, _ in REGIMES:
        rows = _load_v2(stem)
        if rows is None:
            all_loaded = False
            for name in ("ActThin%s", "ActContra%s", "ActShock%s",
                         "OvlContra%s", "RawContra%s", "OvlShock%s"):
                macros["Kal" + name % suffix] = "--"
            continue
        total_steps += sum(r["n"] for r in rows)

        act_thin = _row_v2(rows, "thinned", "active", BUCKET)
        act_con = _row_v2(rows, "contradiction", "active", BUCKET)
        act_shk = _row_v2(rows, "shock", "active", BUCKET)
        ovl_con = _row_v2(rows, "contradiction", "overlay", BUCKET)
        ovl_shk = _row_v2(rows, "shock", "overlay", BUCKET)

        macros[f"KalActThin{suffix}"] = f"{1e4 * act_thin['med_err_post'][0]:.1f}"
        macros[f"KalActContra{suffix}"] = f"{1e4 * act_con['med_err_post'][0]:.1f}"
        macros[f"KalActShock{suffix}"] = f"{1e4 * act_shk['med_err_post'][0]:.1f}"
        macros[f"KalOvlContra{suffix}"] = f"{1e4 * ovl_con['med_err_post'][0]:.1f}"
        macros[f"KalRawContra{suffix}"] = f"{1e4 * ovl_con['med_err_meas'][0]:.1f}"
        macros[f"KalOvlShock{suffix}"] = f"{1e4 * ovl_shk['med_err_post'][0]:.1f}"
        zetas += [act_thin["zeta_std"][0], act_con["zeta_std"][0]]

    if all_loaded and total_steps:
        macros["KalStepsVTwo"] = f"{total_steps:,}".replace(",", r"\,")
        macros["KalActZetaMin"] = f"{min(zetas):.1f}"
        macros["KalActZetaMax"] = f"{max(zetas):.1f}"
    else:
        macros["KalStepsVTwo"] = "--"
        macros["KalActZetaMin"] = macros["KalActZetaMax"] = "--"
        print("v2 merged backtest JSONs missing under", RESULTS,
              "- v2 macros emitted as '--'")


# ------------------------------------- Appendix C: reference vs production
def kalman_update_ref(mean_pred, cov_pred, obs, obs_cov, H=None):
    """The note's Appendix C listing, verbatim (numpy only)."""
    m = np.asarray(mean_pred, dtype=float)
    P = np.asarray(cov_pred, dtype=float)
    z = np.asarray(obs, dtype=float)
    R = np.asarray(obs_cov, dtype=float)
    H = np.eye(m.size) if H is None else np.asarray(H, dtype=float)
    innovation = z - H @ m
    S = H @ P @ H.T + R
    K = np.linalg.solve(S.T, (P @ H.T).T).T
    out_mean = m + K @ innovation
    I_KH = np.eye(m.size) - K @ H
    out_cov = I_KH @ P @ I_KH.T + K @ R @ K.T
    return out_mean, 0.5 * (out_cov + out_cov.T), innovation, S, K


def appendix_c_check(macros: dict[str, str]) -> None:
    """Execute the reference listing against production on a random-seeded
    3x3 problem (full covariances, H = I) and record the max deviation."""
    rng = np.random.default_rng(15)  # the note's number
    a = rng.standard_normal((3, 3))
    b = rng.standard_normal((3, 3))
    P = a @ a.T + 0.5 * np.eye(3)
    R = b @ b.T + 0.5 * np.eye(3)
    m = rng.standard_normal(3)
    z = rng.standard_normal(3)

    ref = kalman_update_ref(m, P, z, R)
    upd = kalman_update(m, P, z, R)
    dev = max(
        float(np.max(np.abs(ref[0] - upd.mean))),
        float(np.max(np.abs(ref[1] - upd.cov))),
        float(np.max(np.abs(ref[2] - upd.innovation))),
        float(np.max(np.abs(ref[3] - upd.innovation_cov))),
        float(np.max(np.abs(ref[4] - upd.gain))),
    )
    macros["KalRefAgreement"] = sci(dev) if dev > 0.0 else "0"
    print(f"Appendix C reference vs production kalman_update: max dev {dev:.2e}")


# ------------------------------------------------------------------------ main
def main() -> None:
    macros: dict[str, str] = {}
    case_figure(macros)
    backtest_figure(macros)
    v2_backtest_macros(macros)
    appendix_c_check(macros)
    macros.update(FINDINGS_F1)

    lines = ["% Auto-generated by gen_kalman.py — do not edit."]
    for name, value in macros.items():
        lines.append(rf"\newcommand{{\{name}}}{{{value}}}")
    (OUT / "kalman_tables.tex").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")
    print(f"Wrote {len(macros)} macros + figures to", OUT)


if __name__ == "__main__":
    main()
