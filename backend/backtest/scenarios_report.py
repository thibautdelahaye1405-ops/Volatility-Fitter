"""Scenario report: merged JSON + self-contained HTML (V3.8 item 6).

Merges the per-(scenario, day) part files written by ``backtest.scenarios``
and renders the client-facing artifact (the benchmark_pack precedent), grouped
scenario x arm x held-out node/rung. The transported-prior baseline is
synthesized as its OWN arm-column ``dark_spot_only`` from the ``base_*``
columns present on every scored row (identical across arms — one arm's rows
are taken per node to avoid double counting).

Columns per group: handle RMS vs the dark baseline (+skill), smile
ATM/wing/full RMS, ζ std + cov95, n; plus the §16.2 persistence buckets
(hours since the session prior freeze) per scenario x arm.

Run::

    python -m backtest.scenarios report --dir backtest/results/scenarios
"""

from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from html import escape

import numpy as np

import volfit

from backtest.benchmark_pack import _CSS, _cell, _finite, summarize_by
from backtest.graph_intraday import _persistence
from backtest.graph_loo import HANDLES

#: The baseline arm-column name (roadmap: "dark, spot-only" = the transported
#: prior — the base_* columns, never a separate solve pass).
BASELINE_ARM = "dark_spot_only"

_COLS = (
    ("n", "n"), ("atm_graph_rms", "ATM arm bp"), ("atm_base_rms", "ATM prior bp"),
    ("atm_skill", "ATM skill bp"), ("skew_skill", "Skew skill"),
    ("curv_skill", "Curv skill"), ("smile_atm", "Smile ATM bp"),
    ("wing_graph", "Smile wing bp"), ("smile_full", "Smile full bp"),
    ("zeta_std", "ζ std"), ("cov95", "95% cov"),
)


# ------------------------------------------------------------------ row merge
def load_parts(out_dir: str) -> list[dict]:
    """Every part's rows, deduped on (scenario, arm, day, ts, node)."""
    rows: list[dict] = []
    seen: set[tuple] = set()
    for path in sorted(glob.glob(os.path.join(out_dir, "*_*.json"))):
        base = os.path.basename(path)
        if base.startswith("scenario_report"):
            continue
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        for r in doc.get("rows", []):
            key = (r.get("scenario"), r.get("arm"), r.get("day"),
                   r.get("ts"), r.get("ticker"), r.get("expiry"))
            if key in seen:
                continue
            seen.add(key)
            rows.append(r)
    return rows


def with_baseline_arm(rows: list[dict]) -> list[dict]:
    """Append the synthetic ``dark_spot_only`` arm: per (scenario, day, ts,
    node), ONE real arm's row rewritten so the "graph" columns ARE the
    transported-prior baseline (res_* := base_*, smile _g := _b, ζ dropped —
    the baseline carries no posterior band)."""
    out = list(rows)
    seen: set[tuple] = set()
    for r in rows:
        key = (r.get("scenario"), r.get("day"), r.get("ts"),
               r.get("ticker"), r.get("expiry"))
        if key in seen:
            continue
        seen.add(key)
        b = dict(r, arm=BASELINE_ARM, zeta=None)
        for h in HANDLES:
            b[f"res_{h}"] = r.get(f"base_{h}")
        for part in ("atm", "wing", "full"):
            b[f"wing_{part}_g"] = r.get(f"wing_{part}_b")
        out.append(b)
    return out


def _with_smile(recs: list[dict], rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Enrich summarize_by records with median smile ATM/full RMS (the wing
    column already rides summarize_by as wing_graph/wing_base)."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k) for k in keys)].append(r)
    for rec in recs:
        g = groups.get(tuple(rec.get(k) for k in keys), [])
        for part in ("atm", "full"):
            a = _finite([x.get(f"wing_{part}_g") for x in g])
            rec[f"smile_{part}"] = round(float(np.median(a)), 2) if a.size else None
    return recs


def summarize(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return _with_smile(summarize_by(rows, keys), rows, keys)


# ---------------------------------------------------------------------- HTML
def _table(recs: list[dict], label_fields: tuple[str, ...], label_names: tuple[str, ...]) -> str:
    head = "".join(f"<th>{escape(n)}</th>" for n in label_names) + "".join(
        f"<th>{escape(n)}</th>" for _f, n in _COLS
    )
    body = []
    for rec in recs:
        labels = "".join(f"<td>{escape(str(rec.get(f, '') or ''))}</td>"
                         for f in label_fields)
        body.append("<tr>" + labels + "".join(_cell(rec, f) for f, _n in _COLS) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _persistence_table(buckets: list[dict]) -> str:
    if not buckets:
        return '<p class="note">No bucketed rows.</p>'
    head = "<th>Bucket</th><th>n</th><th>ATM arm bp</th><th>ATM prior bp</th>"
    body = "".join(
        f"<tr><td>{escape(b['bucket'])}</td><td>{b['n']}</td>"
        f"<td>{b['atm_graph_rms']:g}</td><td>{b['atm_base_rms']:g}</td></tr>"
        for b in buckets
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_report_html(rows: list[dict]) -> str:
    """The self-contained scenario artifact from merged (baseline-augmented) rows."""
    sections: list[str] = []
    for sc in sorted({r["scenario"] for r in rows}):
        g = [r for r in rows if r["scenario"] == sc]
        days = sorted({r["day"] for r in g})
        sections.append(
            f"<h2>{escape(sc)}</h2>"
            f'<p class="note">{escape(g[0].get("design", ""))} design · '
            f"{len(days)} day(s) · {len(g)} scored rows (baseline arm included).</p>"
        )
        sections.append("<h3>By arm</h3>")
        sections.append(_table(summarize(g, ("arm",)), ("arm",), ("Arm",)))
        roles = [r for r in g if r.get("rungRole")]
        if roles:
            sections.append("<h3>By arm × rung role (interp = rung between lit"
                            " rungs; extrap = outside them)</h3>")
            sections.append(_table(
                summarize(roles, ("arm", "rungRole", "rung")),
                ("arm", "rungRole", "rung"), ("Arm", "Role", "Rung")))
        by_ticker = summarize(g, ("arm", "ticker"))
        if len({r["ticker"] for r in g}) > 1:
            sections.append("<h3>By arm × ticker</h3>")
            sections.append(_table(by_ticker, ("arm", "ticker"), ("Arm", "Ticker")))
        sections.append("<h3>Persistence (hours since the session prior freeze)</h3>")
        for arm in sorted({r["arm"] for r in g}):
            arm_rows = [r for r in g if r["arm"] == arm]
            sections.append(f"<h3>{escape(arm)}</h3>")
            sections.append(_persistence_table(_persistence(arm_rows)))
    method = (
        "Per (scenario, day): the day's first stored instant is frozen as the active "
        "prior per ticker; each later instant is rebuilt (intraday clock on) and solved "
        "per arm, the layered arm's residual store threaded chronologically. loo holds "
        "each target node out in turn; dark sets the scenario's lit map for the whole "
        "day and scores dark nodes against their own held-out calibration. "
        f"The {BASELINE_ARM} arm IS the transported-prior baseline (the base_* columns "
        "on every scored row) — no separate solve. SKILL = prior RMS − arm RMS "
        "(positive = the graph beats mechanical spot-transport)."
    )
    meta = (
        f"generated {datetime.now(timezone.utc).isoformat(timespec='seconds')}"
        f" · volfit {volfit.__version__} · {len(rows)} rows"
    )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>volfit — replay scenario report</title>
<style>{_CSS}</style></head><body>
<h1>volfit — replay scenario report (leave-out designs)</h1>
<div class="meta">{escape(meta)}</div>
{''.join(sections)}
<h2>Methodology</h2>
<p class="note">{escape(method)}</p>
<footer>Regenerable: python -m backtest.scenarios run / report (per-(scenario, day)
part files under results/scenarios/).</footer>
</body></html>"""


# --------------------------------------------------------------------- entry
def write_report(out_dir: str) -> tuple[str, str]:
    raw = load_parts(out_dir)
    if not raw:
        raise SystemExit(f"no scenario parts under {out_dir} — run `scenarios run` first")
    rows = with_baseline_arm(raw)
    html_path = os.path.join(out_dir, "scenario_report.html")
    json_path = os.path.join(out_dir, "scenario_report.json")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(build_report_html(rows))
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "appVersion": volfit.__version__,
        "nRows": len(rows),
        "byArm": summarize(rows, ("scenario", "arm")),
        "byRung": summarize([r for r in rows if r.get("rungRole")],
                            ("scenario", "arm", "rungRole", "rung")),
        "byTicker": summarize(rows, ("scenario", "arm", "ticker")),
        "persistence": {
            f"{sc}|{arm}": _persistence(
                [r for r in rows if r["scenario"] == sc and r["arm"] == arm])
            for sc in sorted({r["scenario"] for r in rows})
            for arm in sorted({r["arm"] for r in rows if r["scenario"] == sc})
        },
    }
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    return html_path, json_path
