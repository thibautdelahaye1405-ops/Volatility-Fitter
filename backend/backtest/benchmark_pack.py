"""Benchmark pack: the regenerable validation artifact for graph extrapolation.

Packages the graph leave-one-out backtest (backtest.graph_loo) over every
captured regime into ONE self-contained HTML report + a machine-readable
JSON — the sales/model-governance artifact: graph posterior vs the
transported-prior baseline per handle, the R∈{0,1} SSR bracket, the
liquid-split dark-name product case, per-asset-kind splits and ζ calibration.

Chunked + RESUMABLE: ``run`` scores day pairs in chunks and writes one part
file per chunk under ``results/benchmark/`` (existing parts are skipped, so
an interrupted run continues where it left off); ``report`` merges whatever
parts exist and renders the artifact. The full 25-asset sweep is hours of
compute — launch ``run_benchmark_pack.ps1`` in YOUR OWN PowerShell window
(tool-managed background jobs get killed on this box).

Run::

    python -m backtest.benchmark_pack run --regime spike_aug2024
    python -m backtest.benchmark_pack report
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from html import escape

import numpy as np

import volfit

from backtest.graph_edges import EdgeConfig
from backtest.graph_loo import HANDLES, run as run_loo
from backtest.replay import list_fixtures, load_fixture

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "benchmark")
REGIMES = ("spike_aug2024", "high_oct2022", "low_jul2023")
_REGIME_LABELS = {
    "spike_aug2024": "Aug-2024 vol spike (yen-carry unwind)",
    "high_oct2022": "Oct-2022 bear-market lows",
    "low_jul2023": "Jul-2023 calm (VIX ~13-14)",
}


# ------------------------------------------------------------------ run (parts)
def _n_pairs(regime: str) -> int:
    dates = sorted({load_fixture(p).as_of for p in list_fixtures(regime=regime)})
    return max(len(dates) - 1, 0)


def _part_path(regime: str, a: int, b: int) -> str:
    return os.path.join(RESULTS_DIR, f"{regime}_pairs{a:02d}-{b:02d}.json")


def chunk_ranges(n_pairs: int, chunk: int) -> list[tuple[int, int]]:
    """[(a, b), ...) chunk boundaries covering 0..n_pairs."""
    return [(a, min(a + chunk, n_pairs)) for a in range(0, n_pairs, chunk)]


def run_regime(
    regime: str, designs, r_values, chunk: int, cfg: EdgeConfig,
    max_pairs: int | None = None,
) -> None:
    """Score one regime chunk-by-chunk, skipping chunks whose part file exists."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    n = _n_pairs(regime)
    if max_pairs is not None:
        n = min(n, max_pairs)
    for a, b in chunk_ranges(n, chunk):
        path = _part_path(regime, a, b)
        if os.path.exists(path):
            print(f"{regime} pairs {a}-{b}: part exists, skipped", flush=True)
            continue
        print(f"{regime} pairs {a}-{b}: scoring…", flush=True)
        rows = run_loo(regime, designs, r_values, None, cfg, pair_range=(a, b))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"regime": regime, "pairs": [a, b], "rows": rows}, fh, default=str)
        print(f"{regime} pairs {a}-{b}: {len(rows)} scores -> {path}", flush=True)


def load_parts(regime: str | None = None) -> list[dict]:
    """Merge every part file (optionally one regime) into one row list.

    Rows are DEDUPED on their natural key (regime, day, design, R, node):
    parts written with different chunk sizes or design subsets (a smoke run
    before the full sweep) can overlap on day pairs, and a double-counted
    node would silently bias every aggregate. First occurrence wins."""
    if not os.path.isdir(RESULTS_DIR):
        return []
    rows: list[dict] = []
    seen: set[tuple] = set()
    for name in sorted(os.listdir(RESULTS_DIR)):
        if not name.endswith(".json") or "_pairs" not in name:
            continue
        if regime is not None and not name.startswith(regime):
            continue
        with open(os.path.join(RESULTS_DIR, name), encoding="utf-8") as fh:
            for row in json.load(fh)["rows"]:
                key = (row.get("regime"), row.get("as_of"), row.get("design"),
                       row.get("ssr"), row.get("ticker"), row.get("expiry"))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
    return rows


# ------------------------------------------------------------------- aggregate
def _finite(values) -> np.ndarray:
    a = np.array([v for v in values if v is not None], dtype=float)
    return a[np.isfinite(a)]


def summarize_by(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """graph_loo's summary math grouped by arbitrary row fields.

    Per group: graph vs baseline residual RMS + skill per handle (ATM in bp),
    median held-out wing RMS graph vs baseline, ζ mean/std."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k) for k in keys)].append(r)
    out: list[dict] = []
    for key, g in sorted(groups.items(), key=lambda kv: tuple(str(v) for v in kv[0])):
        rec: dict = dict(zip(keys, key))
        rec["n"] = len(g)
        for h in HANDLES:
            gr = _finite([x.get(f"res_{h}") for x in g])
            ba = _finite([x.get(f"base_{h}") for x in g])
            scale = 1e4 if h == "atm" else 1.0  # ATM in bp, skew/curv raw
            rec[f"{h}_graph_rms"] = round(float(np.sqrt(np.mean(gr**2))) * scale, 3) if gr.size else None
            rec[f"{h}_base_rms"] = round(float(np.sqrt(np.mean(ba**2))) * scale, 3) if ba.size else None
            rec[f"{h}_skill"] = (
                round(rec[f"{h}_base_rms"] - rec[f"{h}_graph_rms"], 3)
                if gr.size and ba.size
                else None
            )
        wg = _finite([x.get("wing_wing_g") for x in g])
        wb = _finite([x.get("wing_wing_b") for x in g])
        rec["wing_graph"] = round(float(np.median(wg)), 2) if wg.size else None
        rec["wing_base"] = round(float(np.median(wb)), 2) if wb.size else None
        z = _finite([x.get("zeta") for x in g])
        rec["zeta_mean"] = round(float(z.mean()), 3) if z.size else None
        rec["zeta_std"] = round(float(z.std()), 3) if z.size else None
        out.append(rec)
    return out


# ---------------------------------------------------------------------- report
_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; margin: 24px auto; max-width: 1100px;
       color: #1e293b; }
h1 { font-size: 20px; margin-bottom: 2px; }
h2 { font-size: 15px; margin: 26px 0 6px; }
h3 { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: #64748b;
     margin: 16px 0 6px; }
.meta { color: #64748b; font-size: 12px; margin-bottom: 16px; }
.tiles { display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0; }
.tile { border: 1px solid #e2e8f0; border-radius: 8px; padding: 8px 14px; min-width: 130px; }
.tile .label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #94a3b8; }
.tile .value { font-size: 18px; font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 12px; margin-bottom: 6px; }
th, td { border-bottom: 1px solid #e2e8f0; padding: 4px 8px; text-align: right;
         font-variant-numeric: tabular-nums; white-space: nowrap; }
th { background: #f8fafc; color: #64748b; font-weight: 600; }
th:first-child, td:first-child { text-align: left; }
.ok { color: #059669; } .bad { color: #dc2626; } .muted { color: #94a3b8; }
.note { font-size: 11px; color: #64748b; margin: 6px 0 14px; }
footer { margin-top: 26px; color: #94a3b8; font-size: 11px; }
"""

_SUMMARY_COLS = (
    ("n", "n"), ("atm_graph_rms", "ATM graph bp"), ("atm_base_rms", "ATM prior bp"),
    ("atm_skill", "ATM skill bp"), ("skew_skill", "Skew skill"), ("curv_skill", "Curv skill"),
    ("wing_graph", "Wing graph bp"), ("wing_base", "Wing prior bp"),
    ("zeta_mean", "ζ mean"), ("zeta_std", "ζ std"),
)


def _cell(rec: dict, field: str) -> str:
    v = rec.get(field)
    if v is None:
        return '<td class="muted">—</td>'
    if field.endswith("_skill"):
        cls = "ok" if v > 0 else ("bad" if v < 0 else "")
        return f'<td class="{cls}">{v:+g}</td>'
    return f"<td>{v:g}</td>"


def _table(rows: list[dict], label_fields: tuple[str, ...], label_names: tuple[str, ...]) -> str:
    head = "".join(f"<th>{escape(n)}</th>" for n in label_names) + "".join(
        f"<th>{escape(n)}</th>" for _f, n in _SUMMARY_COLS
    )
    body = []
    for rec in rows:
        labels = "".join(f"<td>{escape(str(rec.get(f, '')))}</td>" for f in label_fields)
        body.append("<tr>" + labels + "".join(_cell(rec, f) for f, _n in _SUMMARY_COLS) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _tile(label: str, value: str, tone: str = "") -> str:
    return (
        f'<div class="tile"><div class="label">{escape(label)}</div>'
        f'<div class="value {tone}">{escape(value)}</div></div>'
    )


def _headline_tiles(rows: list[dict]) -> str:
    tiles = []
    full = [r for r in rows if r["design"] == "full_loo"]
    if full:
        s = summarize_by(full, ("ssr",))
        skills = [rec["atm_skill"] for rec in s if rec.get("atm_skill") is not None]
        if skills:
            lo, hi = min(skills), max(skills)
            tone = "ok" if lo > 0 else ""
            tiles.append(_tile("Full-LOO ATM skill (R-bracket)", f"{lo:+g} … {hi:+g} bp", tone))
    liquid = [r for r in rows if r["design"] == "liquid_split"]
    if liquid:
        s = summarize_by(liquid, ("ssr",))
        skills = [rec["atm_skill"] for rec in s if rec.get("atm_skill") is not None]
        if skills:
            lo, hi = min(skills), max(skills)
            tiles.append(_tile("Dark-name ATM skill (R-bracket)", f"{lo:+g} … {hi:+g} bp",
                               "ok" if lo > 0 else ""))
    z = _finite([r.get("zeta") for r in rows])
    if z.size:
        tiles.append(_tile("ζ calibration (all scores)",
                           f"{z.mean():+.2f} ± {z.std():.2f}",
                           "ok" if abs(z.mean()) < 0.3 and z.std() < 1.3 else ""))
    tiles.append(_tile("Scored nodes", f"{len(rows)}"))
    return f'<div class="tiles">{"".join(tiles)}</div>'


def _manifest(rows: list[dict]) -> str:
    regimes = sorted({r["regime"] for r in rows})
    days = sorted({r["as_of"] for r in rows})
    tickers = sorted({r["ticker"] for r in rows})
    cfg = EdgeConfig()
    parts = [
        f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"volfit {volfit.__version__}",
        f"regimes {', '.join(regimes)}",
        f"{len(days)} scored days",
        f"{len(tickers)} assets",
        (
            f"edges: calendar √T w{cfg.cal_weight:g} · index β{cfg.beta_index} w{cfg.index_weight:g}"
            f" · sector-ETF β{cfg.beta_etf} w{cfg.etf_weight:g} · name β{cfg.beta_name} w{cfg.name_weight:g}"
        ),
    ]
    return f'<div class="meta">{escape(" · ".join(parts))}</div>'


def build_report_html(rows: list[dict]) -> str:
    """The self-contained benchmark artifact from merged part rows."""
    sections: list[str] = []
    for regime in sorted({r["regime"] for r in rows}):
        g = [r for r in rows if r["regime"] == regime]
        days = sorted({r["as_of"] for r in g})
        sections.append(
            f"<h2>{escape(_REGIME_LABELS.get(regime, regime))}</h2>"
            f'<p class="note">{len(days)} day pairs · {len(g)} scored nodes.</p>'
        )
        sections.append("<h3>By design × SSR regime</h3>")
        sections.append(
            _table(summarize_by(g, ("design", "ssr")), ("design", "ssr"), ("Design", "R"))
        )
        full = [r for r in g if r["design"] == "full_loo"]
        if full:
            sections.append("<h3>Full-LOO by asset kind</h3>")
            sections.append(
                _table(summarize_by(full, ("kind", "ssr")), ("kind", "ssr"), ("Kind", "R"))
            )
    method = (
        "Per consecutive captured day pair (T-1, T): T-1's calibrated surface is frozen as "
        "the prior, transported to day T under the SSR regime R; the lit nodes' calibration "
        "innovations propagate through the directed graph (calendar √T edges + vol-normalized "
        "index/sector betas); each held-out node's posterior is scored against its ACTUAL "
        "day-T calibration and against the pure transported prior (the baseline). "
        "SKILL = baseline RMS − graph RMS (positive = the graph beats mechanical transport). "
        "R∈{0,1} brackets the truth: R=0 over-credits the graph, R=1 under-credits it. "
        "full_loo withholds every validation-clean node in turn; liquid_split lights only "
        "indices/ETFs and scores the single names as dark targets (the product use case). "
        "ζ standardizes residuals by the posterior + observation uncertainty — mean ≈ 0, "
        "std ≈ 1 means the reported confidence is honest."
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>volfit — graph extrapolation benchmark pack</title>
<style>{_CSS}</style></head><body>
<h1>volfit — graph extrapolation benchmark pack</h1>
{_manifest(rows)}
{_headline_tiles(rows)}
{''.join(sections)}
<h2>Methodology</h2>
<p class="note">{escape(method)}</p>
<footer>Regenerable: python -m backtest.benchmark_pack run / report (chunked part files under
results/benchmark/). Lit calibrations run in persistence mode OFF so innovations are the pure
market-vs-prior move.</footer>
</body></html>"""


def write_report() -> tuple[str, str]:
    rows = load_parts()
    if not rows:
        raise SystemExit("no benchmark part files found — run `benchmark_pack run` first")
    os.makedirs(RESULTS_DIR, exist_ok=True)
    html_path = os.path.join(RESULTS_DIR, "benchmark_report.html")
    json_path = os.path.join(RESULTS_DIR, "benchmark_pack.json")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_report_html(rows))
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "appVersion": volfit.__version__,
        "nRows": len(rows),
        "byDesign": summarize_by(rows, ("regime", "design", "ssr")),
        "byKind": summarize_by(
            [r for r in rows if r["design"] == "full_loo"], ("regime", "kind", "ssr")
        ),
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    return html_path, json_path


# ------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="Graph extrapolation benchmark pack.")
    ap.add_argument("command", choices=("run", "report"))
    ap.add_argument("--regime", default=None, help="one regime (default: all captured)")
    ap.add_argument("--designs", default="full_loo,liquid_split")
    ap.add_argument("--regimes-r", default="0,1")
    ap.add_argument("--chunk", type=int, default=2, help="day pairs per resumable part")
    ap.add_argument("--max-pairs", type=int, default=None, help="cap pairs (smoke runs)")
    args = ap.parse_args()

    if args.command == "report":
        html_path, json_path = write_report()
        print(f"wrote {html_path}\nwrote {json_path}")
        return 0

    designs = tuple(d.strip() for d in args.designs.split(","))
    r_values = tuple(float(r) for r in args.regimes_r.split(","))
    regimes = (args.regime,) if args.regime else REGIMES
    for regime in regimes:
        run_regime(regime, designs, r_values, args.chunk, EdgeConfig(), args.max_pairs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
