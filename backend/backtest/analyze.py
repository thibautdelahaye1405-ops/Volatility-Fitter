"""Analysis, break-triage and report over the compute-phase metrics (Phases 4/5/8).

Reads a results table (Parquet from ``run_compute``) and emits:
  * a model Pareto vs the SVI-JW baseline — precision (in- and out-of-sample RMS),
    speed, and no-arb rate (precision reported honestly, not a single number that
    more degrees of freedom always win);
  * end-to-end time attribution (de-Am/prep vs fit), split by exercise style
    (de-Am only bites American single-names / ETFs; index options are European);
  * a break inventory — non-convergence, LV max-nfev, bound-pinning, arb, RMSE
    outliers (z>3) — with the offending (asset, date, expiry) for triage.

Run:

    python -m backtest.analyze --results results/spike_aug2024_parametric.parquet
"""

from __future__ import annotations

import argparse
import os

BASELINE = "SVI-JW"


def _med(series) -> float:
    return float(series.median()) if len(series) else float("nan")


def _arb_mask(df):
    """Genuine-static-arb mask per row. Prefers the analytic, FD-free ``arb_real``
    (R2); falls back to the reconstructed ``bfly_neg_frac > 1e-6`` for older result
    tables that predate it (so prior parquets still render)."""
    if "arb_real" in df:
        return df["arb_real"].fillna(False).astype(bool)
    return df.get("bfly_neg_frac", 0) > 1e-6


def parametric_report(df) -> str:
    """Per-model Pareto + time attribution + break inventory as markdown."""

    ok = df[df.get("ok", True) == True]  # noqa: E712 - pandas truthiness needs ==
    lines: list[str] = ["## Model sweep vs SVI-JW baseline\n"]
    lines.append("| model | n | in-RMS bp | OOS-RMS bp | fit ms | arb % | vs SVI speed | vs SVI in-RMS |")
    lines.append("|---|---|---|---|---|---|---|---|")
    base = ok[ok["model"] == BASELINE]
    base_fit, base_in = _med(base.get("fit_ms", [])), _med(base.get("in_rmse_bp", []))
    for model in ok["model"].drop_duplicates():
        g = ok[ok["model"] == model]
        fit, in_rms = _med(g["fit_ms"]), _med(g["in_rmse_bp"])
        oos = _med(g["oos_rmse_bp"].dropna()) if "oos_rmse_bp" in g else float("nan")
        arb = 100.0 * float(_arb_mask(g).mean())
        spd = base_fit / fit if fit else float("nan")
        rel = in_rms / base_in if base_in else float("nan")
        lines.append(
            f"| {model} | {len(g)} | {in_rms:.2f} | {oos:.2f} | {fit:.1f} | "
            f"{arb:.1f} | {spd:.2f}x | {rel:.2f}x |"
        )

    lines.append("\n## Time attribution (median ms)\n")
    lines.append("| exercise | de-Am+prep ms | n_deam | fit ms (SVI) |")
    lines.append("|---|---|---|---|")
    for style in ok.get("exercise_style", []).drop_duplicates() if "exercise_style" in ok else []:
        g = ok[ok["exercise_style"] == style]
        gb = g[g["model"] == BASELINE]
        lines.append(
            f"| {style} | {_med(g.get('prep_ms', [])):.1f} | "
            f"{_med(g.get('n_deam', [])):.0f} | {_med(gb.get('fit_ms', [])):.1f} |"
        )

    # break inventory
    lines.append("\n## Breaks\n")
    breaks = df[df.get("ok", True) == False]  # noqa: E712
    lines.append(f"- fit failures: **{len(breaks)}**")
    if len(breaks):
        for _, r in breaks.head(20).iterrows():
            lines.append(f"  - {r.get('asset')} {r.get('as_of')} {r.get('expiry')} "
                         f"{r.get('model')}: {r.get('error')}")
    arb_rows = ok[_arb_mask(ok)]
    lines.append(f"- butterfly-arb slices: **{len(arb_rows)}**")
    # RMSE outliers (z>3 within model)
    n_out = 0
    for model in ok["model"].drop_duplicates():
        g = ok[ok["model"] == model]["in_rmse_bp"].dropna()
        if len(g) > 5:
            z = (g - g.mean()) / (g.std() + 1e-9)
            n_out += int((z > 3).sum())
    lines.append(f"- in-RMSE outliers (z>3 within model): **{n_out}**")
    return "\n".join(lines)


def localvol_report(df) -> str:
    """LV surface convergence + time split + break inventory."""
    ok = df[df.get("ok", True) == True]  # noqa: E712
    lines = ["## Local-Vol surface\n"]
    lines.append(f"- surfaces: {df.get('asset').nunique() if 'asset' in df else 0} assets, "
                 f"{len(ok)} expiry rows")
    lines.append(f"- median surface RMS: **{_med(ok.get('surface_rmse_bp', [])):.1f} bp**")
    lines.append(f"- hit max-nfev: **{int(ok.get('hit_max_nfev', []).sum()) if 'hit_max_nfev' in ok else 0}** rows")
    lines.append(f"- median wall: total {_med(ok.get('wall_ms_total', [])):.0f} ms "
                 f"(pde-val {_med(ok.get('wall_ms_pde_value', [])):.0f}, "
                 f"pde-sens {_med(ok.get('wall_ms_pde_sensitivity', [])):.0f}, "
                 f"opt {_med(ok.get('wall_ms_optimizer', [])):.0f})")
    breaks = df[df.get("ok", True) == False]  # noqa: E712
    lines.append(f"- fit failures: **{len(breaks)}**")
    for _, r in breaks.head(20).iterrows():
        lines.append(f"  - {r.get('asset')} {r.get('as_of')}: {r.get('error')}")
    return "\n".join(lines)


def main() -> int:
    import pandas as pd

    ap = argparse.ArgumentParser(description="Analyze backtest metrics.")
    ap.add_argument("--results", required=True, help="path to a results .parquet")
    ap.add_argument("--kind", choices=["parametric", "localvol", "auto"], default="auto")
    args = ap.parse_args()
    if args.results.endswith(".json"):
        import json

        df = pd.DataFrame(json.load(open(args.results, encoding="utf-8")))
    else:
        df = pd.read_parquet(args.results)
    kind = args.kind
    if kind == "auto":
        kind = "localvol" if "surface_rmse_bp" in df.columns else "parametric"
    report = localvol_report(df) if kind == "localvol" else parametric_report(df)
    print(report)
    out = os.path.splitext(args.results)[0] + "_report.md"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(report + "\n")
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
