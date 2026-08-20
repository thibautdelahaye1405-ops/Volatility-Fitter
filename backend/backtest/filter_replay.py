"""Offline Kalman-filter replay over the intraday store (V3.9 item 7).

The intraday sweep (``observation_filter_intraday``) scores the PURE filter
core over pre-built measurement tables — it never exercises the production app
layer. This module closes that gap: per (ticker, day) it drives the REAL
commit path — ``service.calibrate_node`` -> ``commit_record`` ->
``observation_filter.commit_hook`` with retained solver diagnostics — so the
actual seed/reset/adaptive/idempotence logic runs, and the evidence collected
is the app-layer :class:`volfit.api.filter_history.FilterHistory` ring itself.

Mechanics (the replay-store pattern that does NOT wipe filter state): one
AppState per stored instant via ``graph_intraday.instant_state`` (the
``_StoredChains`` provider — an as-of flip would wipe the filter through
``_clear_chain_caches``; a fresh stored-chains state does not), with the
filter states + history rings CARRIED across the per-instant states and the
data version bumped once per instant so each instant is a genuinely NEW
observation — exactly the live fetch -> calibrate -> commit sequence.

Artifacts, per (ticker, day): ``<out>/<TICKER>_<day>.json`` — the ring per
node in the FilterStepOut wire shape (byte-identical to the live
``/smiles/{t}/{e}/filter/history`` steps) — plus one ``filter_replay.html``
evidence page over every part in the directory (regenerable).

Run (from backend\\; the campaign store is SPY/QQQ/IWM x 8 days x 13 instants;
expect roughly 1-3 minutes per (ticker, day) at the default --max-expiries 1 —
one LQD calibration per instant dominates. Tests use a tiny synthetic store
and NEVER run the real intraday.sqlite)::

    python -m backtest.filter_replay --db backtest/results/intraday.sqlite \
        --tickers SPY --days 2025-07-18 --out backtest/results/filter_replay
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import date, datetime
from html import escape

import numpy as np

import volfit
from volfit.api import service
from volfit.data.store import VolStore

from backtest.graph_intraday import instant_state

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "results", "intraday.sqlite")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "results", "filter_replay")


# ---------------------------------------------------------------- store access
def instants_by_day(store: VolStore, ticker: str) -> dict[date, list[datetime]]:
    """The ticker's stored instants per day, sorted; days with < 2 instants are
    dropped (no room for a seed + at least one predict/update step)."""
    by_day: dict[date, list[datetime]] = defaultdict(list)
    for _tk, _sid, ts in store.list_snapshots([ticker]):
        by_day[ts.date()].append(ts)
    return {d: sorted(v) for d, v in sorted(by_day.items()) if len(v) >= 2}


# ------------------------------------------------------------------ the replay
def replay_day(
    store: VolStore,
    ticker: str,
    day: date,
    instants: list[datetime],
    max_expiries: int = 1,
    fit_mode: str = "mid",
) -> dict:
    """One session's filter evidence: calibrate the target node(s) at every
    stored instant through the production path (observationFilterMode=overlay)
    and return the accumulated history rings as a JSON-safe doc."""
    from volfit.api.filter_history import step_doc

    carried_states: dict[tuple, object] = {}
    carried_hist: dict[tuple, object] = {}
    node_keys: list[tuple] = []
    for i, ts in enumerate(instants):
        st = instant_state(store, [ticker], ts)
        st.set_options(
            st.options().model_copy(update={"observationFilterMode": "overlay"})
        )
        # Thread the filter across the per-instant states (the live AppState
        # keeps them; a stored-chains rebuild must restore them explicitly).
        for k, v in carried_states.items():
            st.set_filter_node(k, v)
        for k, v in carried_hist.items():
            st.set_filter_history(k, v)
        for _ in range(i):  # each instant is a genuinely NEW observation
            st.bump_data_version(ticker)
        isos = [e.isoformat() for e in sorted(st.selected_expiries(ticker))]
        for iso in isos[: max(int(max_expiries), 1)]:
            key = (ticker, iso, fit_mode)
            try:
                service.calibrate_node(st, ticker, iso, fit_mode)
            except Exception as exc:  # noqa: BLE001 — one broken fit, keep going
                print(f"  {ts.time()} {iso}: fit FAILED ({type(exc).__name__})",
                      flush=True)
                continue
            if key not in node_keys:
                node_keys.append(key)
        carried_states = {
            k: st.filter_node(k) for k in node_keys if st.filter_node(k) is not None
        }
        carried_hist = {
            k: st.filter_history(k)
            for k in node_keys
            if st.filter_history(k) is not None
        }
    nodes = {
        k[1]: [step_doc(s) for s in carried_hist[k].steps()]
        for k in node_keys
        if k in carried_hist
    }
    return {
        "meta": {
            "ticker": ticker,
            "day": day.isoformat(),
            "fitMode": fit_mode,
            "filterMode": "overlay",
            "nInstants": len(instants),
            "appVersion": volfit.__version__,
        },
        "nodes": nodes,
    }


def replay(
    db: str,
    tickers: list[str],
    days: set[date] | None = None,
    out_dir: str = DEFAULT_OUT,
    max_expiries: int = 1,
    force: bool = False,
) -> list[str]:
    """Replay every requested (ticker, day), write the JSON parts + the HTML
    evidence page; returns the written paths (existing parts are skipped
    unless ``force`` — the resumable-parts convention)."""
    os.makedirs(out_dir, exist_ok=True)
    written: list[str] = []
    with VolStore(db) as store:
        for tk in tickers:
            by_day = instants_by_day(store, tk)
            if days is not None:
                by_day = {d: v for d, v in by_day.items() if d in days}
            if not by_day:
                print(f"{tk}: no stored days match", flush=True)
                continue
            for day, instants in by_day.items():
                part = os.path.join(out_dir, f"{tk}_{day.isoformat()}.json")
                if os.path.exists(part) and not force:
                    print(f"{tk} {day}: part exists, skipping", flush=True)
                    continue
                print(f"{tk} {day}: {len(instants)} instants", flush=True)
                doc = replay_day(store, tk, day, instants, max_expiries)
                with open(part, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, indent=1)
                n = sum(len(v) for v in doc["nodes"].values())
                print(f"{tk} {day}: wrote {n} steps -> {part}", flush=True)
                written.append(part)
    written.append(write_html(out_dir))
    return written


# --------------------------------------------------------------------- report
_HANDLES = ("ATM", "skew", "curv")


def _fmt(x, digits=4) -> str:
    return "—" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"


def _node_rows(steps: list[dict]) -> str:
    rows = []
    for s in steps:
        z = s.get("zeta") or [None] * 3
        flag = s.get("resetReason") or ("cont." if s.get("contaminated") else "")
        rows.append(
            "<tr><td>{ts}</td><td>{dt}</td><td>{pred}</td><td>{obs}</td>"
            "<td>{post}</td><td>{z}</td><td>{gain}</td><td>{prov}</td>"
            "<td>{flag}</td></tr>".format(
                ts=escape(datetime.fromtimestamp(s["ts"]).strftime("%H:%M")),
                dt=_fmt(s["dtDays"], 4),
                pred=_fmt(s["prediction"][0] if s["prediction"] else None),
                obs=_fmt(s["observation"][0] if s["observation"] else None),
                post=_fmt(s["posterior"][0] if s["posterior"] else None),
                z=" / ".join(_fmt(v, 2) for v in z),
                gain=" / ".join(_fmt(v, 2) for v in (s["gain"] or [None] * 3)),
                prov=escape(s.get("provenance") or ""),
                flag=escape(str(flag)),
            )
        )
    return "".join(rows)


def _node_summary(steps: list[dict]) -> str:
    zs = np.array(
        [s["zeta"] for s in steps if s.get("zeta") is not None], dtype=float
    )
    resets = sum(1 for s in steps if s.get("resetReason"))
    z_std = (
        " / ".join(f"{v:.2f}" for v in zs.std(axis=0)) if zs.shape[0] >= 2 else "—"
    )
    return (
        f"{len(steps)} steps · {resets} reset(s) · std(ζ) ATM/skew/curv = {z_std}"
        " (≈1 per handle = Q scaled right)"
    )


def write_html(out_dir: str) -> str:
    """One self-contained evidence page over every part in ``out_dir`` (the
    scenarios_report emitter pattern; regenerable from the JSON parts)."""
    from backtest.benchmark_pack import _CSS

    sections: list[str] = []
    for path in sorted(glob.glob(os.path.join(out_dir, "*_*.json"))):
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta = doc.get("meta", {})
        sections.append(
            f"<h2>{escape(meta.get('ticker', '?'))} — {escape(meta.get('day', '?'))}"
            f" ({meta.get('nInstants', '?')} instants, overlay mode)</h2>"
        )
        for iso, steps in sorted(doc.get("nodes", {}).items()):
            sections.append(f"<h3>{escape(iso)}</h3>")
            sections.append(f"<p class='note'>{escape(_node_summary(steps))}</p>")
            sections.append(
                "<table><thead><tr><th>ts</th><th>dt (d)</th><th>ATM m⁻</th>"
                "<th>ATM z</th><th>ATM m⁺</th><th>ζ (ATM/skew/curv)</th>"
                "<th>K (ATM/skew/curv)</th><th>provenance</th><th>flag</th>"
                f"</tr></thead><tbody>{_node_rows(steps)}</tbody></table>"
            )
    method = (
        "Per (ticker, day): one AppState per stored instant (stored-chains "
        "provider — no as-of flips, so filter state is never wiped); filter "
        "states + history rings carried across instants; the node calibrated "
        "through the PRODUCTION service path with observationFilterMode="
        "overlay, so on_fit_commit runs the real seed/reset/adaptive logic. "
        "Steps are the app-layer FilterHistory ring in the live wire shape."
    )
    html = (
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        "<title>volfit — observation-filter replay evidence</title>\n"
        f"<style>{_CSS}</style></head><body>\n"
        "<h1>volfit — observation-filter replay (production app layer)</h1>\n"
        f"<div class=\"meta\">volfit {escape(volfit.__version__)}</div>\n"
        f"{''.join(sections)}\n<h2>Methodology</h2>"
        f"<p class=\"note\">{escape(method)}</p>\n"
        "<footer>Regenerable: python -m backtest.filter_replay --db "
        "backtest/results/intraday.sqlite (parts + this page under the "
        "--out directory).</footer>\n</body></html>"
    )
    out = os.path.join(out_dir, "filter_replay.html")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    return out


# ----------------------------------------------------------------------- entry
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Replay the observation filter's app layer over stored "
        "intraday chains (V3.9 item 7)."
    )
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--tickers", default="SPY", help="comma-separated")
    ap.add_argument("--days", default="", help="ISO dates to run (default all)")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--max-expiries", type=int, default=1,
                    help="front rungs calibrated per instant (default 1)")
    ap.add_argument("--force", action="store_true",
                    help="recompute existing parts")
    args = ap.parse_args()
    tickers = sorted(t.strip().upper() for t in args.tickers.split(",") if t.strip())
    days = (
        {date.fromisoformat(d.strip()) for d in args.days.split(",") if d.strip()}
        or None
    )
    written = replay(args.db, tickers, days, args.out, args.max_expiries, args.force)
    print(f"wrote {len(written)} file(s); page: {written[-1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
