"""Certification pack v0 (forward roadmap R0 item 4): named stress cases.

Every historical bug becomes a NAMED case in one regenerable matrix across
three dimensions — market regimes, data failures, model stress. A case
points at the pytest locks that regression-guard it (the same tests the
suite runs — validation and production share definitions rather than
drifting apart), plus, for market-regime cases, the standing benchmark-pack
verdict read from ``results/benchmark`` parts. The pack emits a
client-facing HTML certification report + machine JSON.

Run (from backend\\)::

    python -m backtest.certification run       # execute every case's locks
    python -m backtest.certification run --only zero_carry_chains
    python -m backtest.certification report    # render HTML + JSON artifact

``run`` writes per-case verdicts to ``results/certification/cert_results.json``
(re-run any time; one pytest process per case keeps failures isolated);
``report`` merges the verdicts with the benchmark-pack tables.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import escape

import volfit

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "certification")
RESULTS_JSON = os.path.join(RESULTS_DIR, "cert_results.json")
DIMENSIONS = ("market_regime", "data_failure", "model_stress")


@dataclass(frozen=True)
class CertCase:
    """One named certification case: what broke (or what regime must hold),
    where it came from, and the pytest locks that guard it forever."""

    key: str
    title: str
    dimension: str  # one of DIMENSIONS
    origin: str  # commit / finding date the case was born from
    story: str  # client-readable: what happened and what now guards it
    locks: tuple[str, ...]  # pytest targets (tests/file.py[::test]) run by `run`


CASES: tuple[CertCase, ...] = (
    # ------------------------------------------------------- market regimes
    CertCase(
        "regime_spike_aug2024", "Aug-2024 vol spike (yen-carry unwind)",
        "market_regime", "benchmark pack 2026-07-09",
        "Stress regime of the 25-asset graph benchmark: dark-name propagation "
        "must add skill (+7.9…+14.2 bp ATM over mechanical transport) with "
        "honest bands (zeta std ~1 after the idio floor). Verdict table below "
        "comes from the stored benchmark parts.",
        ("tests/test_graph_loo_backtest.py", "tests/test_benchmark_pack.py"),
    ),
    CertCase(
        "regime_high_oct2022", "Oct-2022 bear-market lows",
        "market_regime", "benchmark pack 2026-07-09",
        "Out-of-sample regime for the graph knobs (tuned on the spike): skill "
        "must stay positive (+3.8…+7.2 bp) and bands conservative-to-honest.",
        ("tests/test_graph_loo_backtest.py",),
    ),
    CertCase(
        "regime_low_jul2023", "Jul-2023 calm tape (earnings-idiosyncratic)",
        "market_regime", "benchmark pack 2026-07-09 + idio floor 2026-07-10",
        "Calm regime where single-name moves are earnings-driven: propagation "
        "must never hurt (skill >= 0) and the idio band floor must keep dark "
        "bands honest (zeta std 1.91 -> ~1.0 offline replay).",
        ("tests/test_graph_idio.py",),
    ),
    # -------------------------------------------------------- data failures
    CertCase(
        "zero_carry_chains", "IV-synthesized zero-carry chains",
        "data_failure", "6731dc4 (2026-07-08)",
        "Massive delayed-tier chains synthesized at F=spot with zero spreads "
        "made parity regress garbage forwards (recurring SPY breakage). The "
        "zero_carry pin holds F=spot,D=1 and is persisted; legit EOD "
        "zero-spread closes still resolve sane forwards.",
        ("tests/test_forward_robust.py",),
    ),
    CertCase(
        "duplicate_strikes", "Duplicate strikes across listings",
        "data_failure", "f1a9982 (2026-07-07)",
        "Multiple listings quoting the same strike divided the de-Am anchor "
        "slope by zero and killed whole capture day-pairs. The core slope now "
        "uses the nearest strictly-distinct strike; clean chains byte-identical.",
        ("tests/test_convex_deam.py::test_duplicate_strike_at_core_boundary_does_not_crash",),
    ),
    CertCase(
        "tick_noise_quotes", "Few-tick OTM quotes (tick noise)",
        "data_failure", "e810713 (2026-07-10)",
        "Deep-OTM quotes worth a couple of ticks carry no vol information and "
        "whipsawed wings; real-feed chains screen them (3-tick OTM floor) and "
        "the tick size persists with the snapshot (schema v6).",
        ("tests/test_quotes_deam.py::test_tick_floor_drops_few_tick_quotes_on_real_feed_chains",
         "tests/test_data_layer.py::test_snapshot_round_trip_keeps_tick_size"),
    ),
    CertCase(
        "stale_crossed_markets", "Stale / crossed wing quotes",
        "data_failure", "parity screens (2026-06) + forward clamp",
        "A stale or crossed put/call pair drags the parity regression; the "
        "outlier filter drops the pair and the discount clamp keeps the "
        "forward sane even when wings break.",
        ("tests/test_data_layer.py::test_parity_outlier_filter_drops_stale_pair",
         "tests/test_forward_robust.py::test_stale_wings_break_unclamped_but_clamp_stays_sane"),
    ),
    CertCase(
        "stale_data_age", "Delayed / idle live feed",
        "data_failure", "e9832ff (2026-07-10)",
        "A perfect fit of yesterday's book is still yesterday's book: red-stale "
        "chain age fails publish-readiness; amber only warns.",
        ("tests/test_data_age.py",),
    ),
    # --------------------------------------------------------- model stress
    CertCase(
        "weekly_lv_resolution", "True-weekly local-vol resolution",
        "model_stress", "fixes #1-#3 (2026-06-25 … cac686c 2026-07-10)",
        "A 1-week SPY expiry fitted 108 bp RMS at default grids: per-expiry "
        "strike-coverage floor, short-expiry PDE dx and short-first-expiry dt "
        "refinement took it to ~24 bp with normal surfaces byte-identical.",
        ("tests/test_affine_grid_design.py",),
    ),
    CertCase(
        "lv_operator_blindness", "In-operator LV rms hides operator error",
        "model_stress", "converged-reprice metric (2026-07-10)",
        "The optimizer bends theta to cancel PDE time-discretization error, so "
        "in-operator rms reads ~0 while a converged reprice shows the real "
        "error (weekly SPY: 11 vs 46 bp). The quality metric now reprices on "
        "a refined operator; the exposure test forces a coarse march and "
        "requires the metric to reveal it.",
        ("tests/test_lv_reprice.py",),
    ),
    CertCase(
        "convex_wing_tail", "Convex-wing fighting dense quotes",
        "model_stress", "ff853be (2026-06-20)",
        "The convex-wing constraint on a fine grid fought dense SPY quotes "
        "(26 bp regression); it is confined to the unquoted extrapolation "
        "tail and never bites where quotes constrain vertices.",
        ("tests/test_affine_grid_design.py::test_convex_wing_confined_to_quoted_extrapolation",),
    ),
    CertCase(
        "calendar_phantom", "Phantom calendar violations in the wings",
        "model_stress", "2026-06-18 (user-confirmed NVDA/SPY fix)",
        "A fixed wide floor grid let SVI's linear wings manufacture phantom "
        "calendar violations that flattened far fits; the floor is confined "
        "to the traded range and the no-floor path is byte-identical.",
        ("tests/test_overlay_calendar.py",),
    ),
    CertCase(
        "deam_repair_confinement", "American de-bias repair authority",
        "model_stress", "R3 revert ec68c52 + convex de-Am",
        "Extending a price-moving repair beyond the data turned a 27% put "
        "wing into 104% and gapped live ATM smiles (the R3 revert). The "
        "de-Am convex repair keeps its authority confined; the certification "
        "locks its clean-chain no-op and boundary behavior.",
        ("tests/test_convex_deam.py",),
    ),
    CertCase(
        "extrap_wing_contracts", "Extrapolated-region arbitrage (Notes 09/10)",
        "model_stress", "Phases 1-3 (2026-07-09 / 2026-07-10)",
        "Beyond the last quote the surface is a stated contract: Phase 1 "
        "measures wing arb (advisory), Phase 2 optionally leans on fits "
        "(clean pair = exact no-op), Phase 3 projects PUBLISHED wings onto "
        "the discrete arb-free set with the traded core pinned.",
        ("tests/test_diagnostics.py", "tests/test_extrap_enforce.py",
         "tests/test_wing_projection.py"),
    ),
    CertCase(
        "graph_dark_disconnection", "One-way cross edges strand dark names",
        "model_stress", "topology root cause (2026-07-09)",
        "Directed one-way informer->name edges made single names transient "
        "(stationary mass 0 -> conductance 0): dark names silently decoupled "
        "and the harness reported zero skill. Reverse edges with inverse beta "
        "restore recurrence; the legacy topology stays reproducible.",
        ("tests/test_graph_loo_backtest.py",),
    ),
    CertCase(
        "dark_band_honesty", "Dark-name band honesty (idio floor)",
        "model_stress", "a7dde85 (2026-07-10)",
        "Calm-tape dark-name bands understated realized moves by ~1.9x; the "
        "idio floor lifts a non-observed node's band to ~0.55x its own "
        "trailing innovation RMS — strictly causal, mean-invariant, "
        "cold-start silent, self-gating across asset kinds.",
        ("tests/test_graph_idio.py",),
    ),
    CertCase(
        "0dte_exit_gates", "0DTE exit gates (clock, replay, publish, latency)",
        "model_stress", "R2 item 10 campaign (2026-07-15/16)",
        "The intraday campaign's acceptance bar, locked on REAL captured SPY "
        "0DTE NBBO (862 quotes, 12:30 ET): the same-day node prices sub-day "
        "(t = 3.5h, never the unrepresentable 0), replays BITWISE across "
        "fresh states, a publish set with unresolved intrinsic or calendar "
        "inconsistency FAILS HARD before any manifest persists (HTTP 409), "
        "and a warm 0DTE slice refit stays inside the 50 ms design target "
        "(~20 ms measured; rail ceiling 3x for shared runners).",
        ("tests/test_intraday_0dte.py",
         "tests/test_export.py::test_publish_blocked_on_calendar_inconsistency",
         "tests/test_export.py::test_node_blockers_name_intrinsic_and_core_conflicts",
         "tests/test_perf.py::test_perf_warm_slice_0dte"),
    ),
)


# ------------------------------------------------------------------ running
def _run_case(case: CertCase, python: str) -> dict:
    """One pytest process over the case's locks; isolated pass/fail verdict."""
    cmd = [python, "-m", "pytest", "-q", "--tb=line", *case.locks]
    proc = subprocess.run(
        cmd, cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True, text=True, timeout=1800,
    )
    tail = (proc.stdout or "").strip().splitlines()
    return {
        "key": case.key,
        "passed": proc.returncode == 0,
        "summary": tail[-1] if tail else "",
    }


def run(only: str | None = None) -> dict:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    chosen = [c for c in CASES if only is None or c.key == only]
    if not chosen:
        raise SystemExit(f"no case named {only!r}")
    results: dict[str, dict] = {}
    if only is not None and os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as fh:  # keep other verdicts
            results = {r["key"]: r for r in json.load(fh)["cases"]}
    for case in chosen:
        print(f"{case.key}: running {len(case.locks)} lock target(s)…", flush=True)
        results[case.key] = _run_case(case, sys.executable)
        print(f"  -> {'PASS' if results[case.key]['passed'] else 'FAIL'} "
              f"({results[case.key]['summary']})", flush=True)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "appVersion": volfit.__version__,
        "cases": list(results.values()),
    }
    with open(RESULTS_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {RESULTS_JSON}")
    return payload


# ---------------------------------------------------------------- reporting
def _benchmark_tables() -> str:
    """Regime verdict tables from the stored benchmark parts (if present)."""
    from backtest.benchmark_pack import _table, load_parts, summarize_by

    rows = load_parts()
    if not rows:
        return '<p class="note">No benchmark parts found — run the benchmark pack.</p>'
    sections = []
    liquid = [r for r in rows if r.get("design") == "liquid_split"]
    if liquid:
        sections.append("<h3>Dark single names behind lit indexes/ETFs (liquid_split)</h3>")
        sections.append(_table(summarize_by(liquid, ("regime", "ssr")),
                               ("regime", "ssr"), ("Regime", "R")))
    full = [r for r in rows if r.get("design") == "full_loo"]
    if full:
        sections.append("<h3>Every node held out in turn (full_loo), by asset kind</h3>")
        sections.append(_table(summarize_by(full, ("regime", "kind", "ssr")),
                               ("regime", "kind", "ssr"), ("Regime", "Kind", "R")))
    return "".join(sections)


def build_report_html(results: dict) -> str:
    from backtest.benchmark_pack import _CSS

    verdicts = {r["key"]: r for r in results.get("cases", [])}
    sections: list[str] = []
    labels = {
        "market_regime": "Market regimes",
        "data_failure": "Data failures",
        "model_stress": "Model stress",
    }
    for dim in DIMENSIONS:
        cases = [c for c in CASES if c.dimension == dim]
        rows = []
        for c in cases:
            v = verdicts.get(c.key)
            badge = (
                '<span class="muted">not run</span>' if v is None
                else ('<span class="ok">PASS</span>' if v["passed"]
                      else '<span class="bad">FAIL</span>')
            )
            rows.append(
                f"<tr><td>{badge}</td><td><b>{escape(c.title)}</b><br>"
                f'<span class="note">{escape(c.story)}</span></td>'
                f'<td class="note">{escape(c.origin)}<br>'
                f"{escape(', '.join(c.locks))}</td></tr>"
            )
        sections.append(
            f"<h2>{labels[dim]}</h2><table><thead><tr><th></th><th>Case</th>"
            f"<th>Origin · locks</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    n = len(results.get("cases", []))
    n_pass = sum(1 for r in results.get("cases", []) if r["passed"])
    meta = (
        f"generated {escape(results.get('generatedAt', '—'))} · volfit "
        f"{escape(results.get('appVersion', volfit.__version__))} · "
        f"{n_pass}/{n} cases passing · {len(CASES)} registered"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>volfit — certification pack</title>
<style>{_CSS}
td:nth-child(2) {{ text-align: left; white-space: normal; }}
td:nth-child(3) {{ text-align: left; white-space: normal; }}</style></head><body>
<h1>volfit — certification pack</h1>
<div class="meta">{meta}</div>
<p class="note">Every historical bug is a NAMED case guarded by the same tests
the production suite runs — validation and production monitoring share one set
of definitions. Market-regime verdicts below come from the stored benchmark
parts (graph posterior vs mechanical transport; zeta std ~ 1 = honest bands).</p>
{''.join(sections)}
<h2>Benchmark verdict (stored parts)</h2>
{_benchmark_tables()}
<footer>Regenerable: python -m backtest.certification run / report.</footer>
</body></html>"""


def write_report() -> tuple[str, str]:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {}
    if os.path.exists(RESULTS_JSON):
        with open(RESULTS_JSON, encoding="utf-8") as fh:
            results = json.load(fh)
    html_path = os.path.join(RESULTS_DIR, "certification_report.html")
    json_path = os.path.join(RESULTS_DIR, "certification_pack.json")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_report_html(results))
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"results": results, "cases": [asdict(c) for c in CASES]},
            fh, indent=2,
        )
    return html_path, json_path


def main() -> int:
    ap = argparse.ArgumentParser(description="volfit certification pack.")
    ap.add_argument("command", choices=("run", "report"))
    ap.add_argument("--only", default=None, help="run a single case by key")
    args = ap.parse_args()
    if args.command == "run":
        run(args.only)
        return 0
    html_path, json_path = write_report()
    print(f"wrote {html_path}\nwrote {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
