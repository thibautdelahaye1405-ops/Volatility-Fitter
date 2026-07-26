"""Adjudicate the SVI structural-chart default (committee R3 rider).

Reads the three `--tag svichart` parametric result files and scores the
PRE-REGISTERED gate of FINDINGS_svi_chart.md: SVI-STRUCT vs SVI-JW-195
(like-for-like at the production cap 1.95), with the frozen SVI-JW (raw
@ 2.0) row anchoring against every older part. Prints the markdown verdict
table; the findings file records it.

    python -m backtest.analyze_svi_chart
"""

from __future__ import annotations

import json
import os
from statistics import median

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
#: Result-file tag (round 1 = "svichart"; pass another as argv[1]).
RESULTS_TAG = "svichart"
REGIMES = ("spike_aug2024", "high_oct2022", "low_jul2023")
MODES = ("mid", "haircut")
ARMS = ("SVI-JW", "SVI-JW-195", "SVI-STRUCT")
#: Pre-registered thresholds (FINDINGS_svi_chart.md).
RMS_PARITY_BP = 0.5
WALL_RATIO_MAX = 1.5
EVAL_CAP = 500


def _cell(rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("ok")]
    bad = [r for r in rows if not r.get("ok")]
    oos = [r["oos_rmse_bp"] for r in ok if r.get("oos_rmse_bp") is not None]
    return {
        "n": len(rows),
        "fail": len(bad),
        "in_med": median(r["in_rmse_bp"] for r in ok) if ok else float("nan"),
        "oos_med": median(oos) if oos else float("nan"),
        "exhaust": sum(1 for r in ok if (r.get("n_eval") or 0) >= EVAL_CAP),
        "ms_med": median(r["fit_ms"] for r in ok) if ok else float("nan"),
        "arb_rate": (sum(1 for r in ok if r.get("arb_real")) / len(ok)) if ok else 0.0,
        "g_worst": min((r.get("bfly_min_g_an", 0.0) for r in ok), default=0.0),
        "nonfinite": sum(
            1 for r in ok
            if not all(
                isinstance(r.get(f), (int, float)) and r.get(f) == r.get(f)
                for f in ("in_rmse_bp",)
            )
        ),
    }


def load_cells() -> dict:
    cells: dict = {}
    for regime in REGIMES:
        for mode in MODES:
            path = os.path.join(
                RESULTS_DIR,
                f"{regime}_parametric_tv_density_{mode}_{RESULTS_TAG}.json",
            )
            with open(path, encoding="utf-8") as fh:
                rows = json.load(fh)
            for arm in ARMS:
                cells[(regime, mode, arm)] = _cell(
                    [r for r in rows if r.get("model") == arm]
                )
    return cells


def adjudicate(cells: dict) -> tuple[bool, list[str]]:
    """The pre-registered gate, cell by cell. Returns (flip, reasons)."""
    reasons: list[str] = []
    ok = True
    tot_exh = {arm: 0 for arm in ("SVI-JW-195", "SVI-STRUCT")}
    tot_arb = {arm: [0, 0] for arm in ("SVI-JW-195", "SVI-STRUCT")}
    for regime in REGIMES:
        for mode in MODES:
            raw = cells[(regime, mode, "SVI-JW-195")]
            st = cells[(regime, mode, "SVI-STRUCT")]
            where = f"{regime}/{mode}"
            if abs(st["in_med"] - raw["in_med"]) > RMS_PARITY_BP:
                ok = False
                reasons.append(
                    f"GATE 1 FAIL {where}: in-sample median gap "
                    f"{st['in_med'] - raw['in_med']:+.2f}bp > {RMS_PARITY_BP}"
                )
            if abs(st["oos_med"] - raw["oos_med"]) > RMS_PARITY_BP:
                ok = False
                reasons.append(
                    f"GATE 1 FAIL {where}: OOS median gap "
                    f"{st['oos_med'] - raw['oos_med']:+.2f}bp > {RMS_PARITY_BP}"
                )
            if st["fail"] > raw["fail"] or st["nonfinite"] > 0:
                ok = False
                reasons.append(
                    f"GATE 2 FAIL {where}: breaks {st['fail']} vs {raw['fail']} "
                    f"(nonfinite {st['nonfinite']})"
                )
            if st["ms_med"] > WALL_RATIO_MAX * raw["ms_med"]:
                ok = False
                reasons.append(
                    f"GATE 3 FAIL {where}: median fit {st['ms_med']:.1f}ms vs "
                    f"{raw['ms_med']:.1f}ms (> {WALL_RATIO_MAX}x)"
                )
            for arm in tot_exh:
                c = cells[(regime, mode, arm)]
                tot_exh[arm] += c["exhaust"]
                tot_arb[arm][0] += round(c["arb_rate"] * (c["n"] - c["fail"]))
                tot_arb[arm][1] += c["n"] - c["fail"]
    if not tot_exh["SVI-STRUCT"] < tot_exh["SVI-JW-195"]:
        ok = False
        reasons.append(
            f"GATE 3 FAIL aggregate: eval-cap exhaustions "
            f"{tot_exh['SVI-STRUCT']} vs {tot_exh['SVI-JW-195']} (not fewer)"
        )
    # Gate 4 AS AMENDED (ratified 2026-07-26, FINDINGS_svi_chart.md): score
    # arb incidence on CONVERGED populations — the original all-fits form
    # compared unlike populations (raw's headline was diluted by its
    # non-converged third, whose 0.317% rate is fits stopping before any
    # optimum). The round-1/2 tables above keep the raw-form numbers for
    # the record.
    r195 = _converged_arb_rate("SVI-JW-195")
    rst = _converged_arb_rate("SVI-STRUCT")
    if rst > r195 + 1e-9:
        ok = False
        reasons.append(
            f"GATE 4 FAIL (amended, converged): arb {rst:.3%} vs {r195:.3%}"
        )
    reasons.append(
        f"aggregate: exhaustions {tot_exh['SVI-STRUCT']} (struct) vs "
        f"{tot_exh['SVI-JW-195']} (raw@1.95); CONVERGED arb rate "
        f"{rst:.3%} vs {r195:.3%}"
    )
    return ok, reasons


def _converged_arb_rate(arm: str) -> float:
    """Genuine-arb incidence among the arm's CONVERGED fits (nfev < cap)."""
    hits = total = 0
    for regime in REGIMES:
        for mode in MODES:
            path = os.path.join(
                RESULTS_DIR,
                f"{regime}_parametric_tv_density_{mode}_{RESULTS_TAG}.json",
            )
            with open(path, encoding="utf-8") as fh:
                for r in json.load(fh):
                    if (
                        r.get("model") == arm and r.get("ok")
                        and (r.get("n_eval") or 0) < EVAL_CAP
                    ):
                        hits += bool(r.get("arb_real"))
                        total += 1
    return hits / max(total, 1)


def main() -> int:
    import sys

    global RESULTS_TAG
    if len(sys.argv) > 1:
        RESULTS_TAG = sys.argv[1]
    cells = load_cells()
    print("| regime/mode | arm | n | fail | in med bp | OOS med bp | "
          "exhaust | med ms | arb rate | worst g |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for regime in REGIMES:
        for mode in MODES:
            for arm in ARMS:
                c = cells[(regime, mode, arm)]
                print(
                    f"| {regime}/{mode} | {arm} | {c['n']} | {c['fail']} | "
                    f"{c['in_med']:.2f} | {c['oos_med']:.2f} | {c['exhaust']} | "
                    f"{c['ms_med']:.1f} | {c['arb_rate']:.2%} | {c['g_worst']:+.4f} |"
                )
    flip, reasons = adjudicate(cells)
    print()
    for r in reasons:
        print("-", r)
    print(f"\nVERDICT: {'FLIP default to structural' if flip else 'HOLD raw default'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
