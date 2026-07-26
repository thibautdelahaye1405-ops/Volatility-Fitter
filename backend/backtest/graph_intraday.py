"""Intraday asynchronous timestamp replay (framework §16.1 — the decisive experiment).

Campaign 2 (daily granularity) HELD adoption of the layered residual state with
an honest scope caveat: every full_loo node relights each day, so the harness
never measures the framework's target regime — a name lit ONCE mid-session and
marked against moving liquid sources thereafter (the §5 A/B story). This module
replays exactly that, at the finest stored observation frequency:

  1. the day's FIRST stored instant is frozen as the active prior per ticker —
     the surface a desk would carry into the session;
  2. at every later instant a full state is rebuilt from the stored chains
     (intraday clock ON) and solved with the arm under test; the residual
     store is threaded CHRONOLOGICALLY through the instants (framework §10),
     with ``solve(now_day=<fractional day>)`` so residual age and half-life
     decay act WITHIN the session;
  3. the designated TARGET ticker is lit only per the design's schedule; its
     nodes are scored at every dark instant against its own (held-out)
     calibration at that instant.

Designs:
  * ``async_once`` — the target is lit at exactly one instant (``--lit-idx``);
    scored dark before (pre phase: pure spatial prediction) and after (post
    phase: spatial + decayed residual — where memory must earn its keep);
  * ``async_dark`` — the target is never lit intraday: the memory-free control
    (rows should be ~invariant across half-life variants; any post-lit skill
    in async_once ABOVE its own async_dark rows is the residual state's).

Topology: the shared harness taxonomy (``graph_edges``) over the stored
universe, with ``--hub`` (default SPY) relabelled a DIRECTED broad-market
informer for the layered arm — liquid hub -> target arcs, peer/calendar
reciprocal — so the DAG cut + residual machinery runs as designed.

Run (parts are per (tag, day), resumable — rerun skips finished days)::

    python -m backtest.graph_intraday run --tag intra_base --mode smooth_field
    python -m backtest.graph_intraday run --tag intra_hl01 \
        --mode layered_dynamic_harmonic --half-life 0.1
    python -m backtest.graph_intraday report
"""

from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import date, datetime

import numpy as np

from volfit.api import priors
from volfit.api.graph_extrapolation import _calibrated_handles, solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.api.state import AppState
from volfit.data.store import VolStore
from volfit.replay_report import _StoredChains

from backtest.graph_edges import EdgeConfig, build_directed_edges, build_message_edges
from backtest.graph_loo import (
    MessageKnobs,
    _baseline_maps,
    _score_node,
    summarize,
)

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results", "intraday_dyn")
DEFAULT_DB = os.path.join(os.path.dirname(__file__), "results", "intraday.sqlite")
_R_NAME = {0.0: "sticky_moneyness", 1.0: "sticky_strike"}
#: Persistence-accuracy buckets (§16.2), hours since the target's lit instant.
ELAPSED_BUCKETS = ((0.0, 0.75), (0.75, 1.75), (1.75, 3.25), (3.25, 24.0))


# ---------------------------------------------------------------- store access
def common_instants(store: VolStore, tickers: list[str]) -> dict[date, list[datetime]]:
    """Per day, the instants at which EVERY requested ticker has a snapshot,
    sorted. Days with < 4 common instants are dropped (no room for a prior
    instant + a lit instant + at least two scored marks)."""
    per_ticker: dict[str, set[datetime]] = defaultdict(set)
    for tk, _sid, ts in store.list_snapshots(tickers):
        per_ticker[tk].add(ts)
    if any(tk not in per_ticker for tk in tickers):
        return {}
    shared = set.intersection(*(per_ticker[tk] for tk in tickers))
    by_day: dict[date, list[datetime]] = defaultdict(list)
    for ts in shared:
        by_day[ts.date()].append(ts)
    return {d: sorted(v) for d, v in sorted(by_day.items()) if len(v) >= 4}


def frac_day(ts: datetime) -> float:
    """Fractional-day clock for the residual state (framework §10: any
    monotone float; only differences enter the math)."""
    secs = ts.hour * 3600 + ts.minute * 60 + ts.second
    return float(ts.toordinal()) + secs / 86400.0


def instant_state(store: VolStore, tickers: list[str], ts: datetime) -> AppState:
    """A full multi-ticker AppState at one stored instant: stored chains as the
    provider, same-day expiries EXCLUDED (a 0DTE rung has calendar t = 0 in the
    graph clock — degenerate ladder betas), intraday clock ON (sub-day tau)."""
    snaps = {tk: store.snapshot_at(tk, ts) for tk in tickers}
    for tk, snap in snaps.items():
        # snapshot_at is at-or-BEFORE: an absent instant would silently serve
        # stale chains as if they were this instant's — refuse instead.
        if snap is None or snap.timestamp != ts:
            raise ValueError(f"{tk} has no snapshot exactly at {ts}")
    state = AppState(ts.date(), provider=_StoredChains(snaps))
    for tk, snap in snaps.items():
        state.set_expiries(tk, sorted(e for e in snap.expiries() if e > ts.date()))
    state.set_options(state.options().model_copy(
        update={"intradayClock": True, "priorPersistenceMode": "off"}
    ))
    return state


# ------------------------------------------------------------------- schedules
def target_lit(design: str, instant_idx: int, lit_idx: int) -> bool:
    """The design's lit schedule for the target ticker at one instant."""
    if design == "async_once":
        return instant_idx == lit_idx
    if design == "async_dark":
        return False
    raise ValueError(f"unknown design {design!r}")


def phase_of(design: str, instant_idx: int, lit_idx: int) -> str:
    """Scored-row phase relative to the target's lit instant."""
    if design == "async_dark":
        return "dark"
    return "pre" if instant_idx < lit_idx else "post"


def elapsed_bucket(hours: float | None) -> str | None:
    """§16.2 persistence-accuracy axis: bucket label for hours-since-lit."""
    if hours is None or hours < 0.0:
        return None
    for lo, hi in ELAPSED_BUCKETS:
        if lo <= hours < hi:
            return f"{lo}-{hi}h"
    return None


def hub_directed(rows, hub: str):
    """Relabel the hub's informer rows as DIRECTED broad-market arcs (layered
    semantics; §9.2 makes peer rows reciprocal by default). The taxonomy
    classifies the intraday ETF triangle as unknown-sector peers — correct for
    the reciprocal pairs, but the hub -> target relation is the §5 A/B's
    directed liquid source, so it must ride the directed engine + the cut."""
    out = []
    for r in rows:
        if r.sourceTicker == hub and r.targetTicker != hub:
            r = r.model_copy(update={
                "relationClass": "broad_index", "relationSemantics": "directed",
            })
        out.append(r)
    return out


# ------------------------------------------------------------------ the replay
def _request(state: AppState, knobs: MessageKnobs, hub: str) -> GraphExtrapolateRequest:
    """One arm's request over this instant's universe (graph_loo's construction,
    hub rows relabelled directed for the layered arm)."""
    sigma, tmap = _baseline_maps(state)
    edges = build_directed_edges(list(sigma), sigma, tmap, EdgeConfig())
    if knobs.mode == "smooth_field":
        return GraphExtrapolateRequest(edges=edges)
    msg_rows = build_message_edges(list(sigma), sigma, tmap, EdgeConfig(),
                                   alpha_t=knobs.alpha_t)
    if knobs.mode == "layered_dynamic_harmonic":
        msg_rows = hub_directed(msg_rows, hub)
    return GraphExtrapolateRequest(
        edges=edges,
        propagationMode=knobs.mode,
        messageEdges=msg_rows,
        calendarBetaExponent=knobs.alpha_t,
        calendarAmplitude=knobs.amp_cal,
        crossAmplitude=knobs.amp_cross,
        calendarPrecisionScale=knobs.cal_precision,
        calendarPrecisionEpsilon=knobs.cal_epsilon,
        calendarPrecisionDecay=knobs.cal_decay,
        residualHalfLifeDays=knobs.residual_half_life,
        # Stable store identity (campaign-1 lesson): vol-normalized betas
        # drift per instant; the structural hash would purge every step.
        residualConfigVersion=f"intra:{knobs.mode}:{knobs.residual_half_life}",
    )


def run_day(
    store: VolStore, day: date, instants: list[datetime], tickers: list[str],
    knobs: MessageKnobs, designs, r_values, targets, hub: str,
    lit_idx: int, memoryless: bool, max_instants: int | None,
) -> list[dict]:
    """Replay one session: freeze the first instant as the prior, then thread
    each (r, design, target) cell's residual store through the later instants.
    States are built once per (instant, r) — fits are the dominant cost and do
    not depend on the lit schedule."""
    if max_instants:
        instants = instants[: max_instants + 1]
    state0 = instant_state(store, tickers, instants[0])
    snaps = {tk: priors.capture_snapshot(state0, tk, "mid", lv=False) for tk in tickers}
    lit_frac = frac_day(instants[lit_idx]) if lit_idx < len(instants) else None

    rows: list[dict] = []
    for r_val in r_values:
        stores: dict[tuple, dict] = defaultdict(dict)  # (design, target) cells
        for i, ts in enumerate(instants[1:], start=1):
            try:
                st = instant_state(store, tickers, ts)
            except Exception as exc:  # noqa: BLE001 — a broken instant is skipped
                print(f"  {ts}: SKIPPED ({type(exc).__name__})", flush=True)
                continue
            for tk in tickers:
                if snaps.get(tk) is not None:
                    st.set_active_prior(tk, snaps[tk], "saved")
            st.set_options(st.options().model_copy(
                update={"dynamicsRegime": _R_NAME[r_val]}
            ))
            req = _request(st, knobs, hub)
            for design in designs:
                for target in targets:
                    lit = target_lit(design, i, lit_idx)
                    for tk in tickers:
                        for iso in [e.isoformat() for e in sorted(st.selected_expiries(tk))]:
                            st.set_node_lit(tk, iso, lit if tk == target else True)
                    cell = stores[(design, target)]
                    if memoryless:
                        cell.clear()  # layered spatial only, no carried state
                    st.graph_dynamic_residuals = cell
                    # obs_ages_days={}: stored chains are fresh AS OF their
                    # instant — live-mode ages would read weeks old and demote
                    # every anchor (nothing certifies, no residual ever records).
                    full = solve(st, req, now_day=frac_day(ts), obs_ages_days={})
                    if full is None:
                        continue
                    if lit:
                        continue  # the lit instant records the residual, no score
                    elapsed_h = (
                        (frac_day(ts) - lit_frac) * 24.0
                        if design == "async_once" and lit_frac is not None
                        else None
                    )
                    for idx, node in enumerate(full.universe.nodes):
                        if node.ticker != target:
                            continue
                        truth = _calibrated_handles(st, target, node.expiry, "mid")
                        if truth is None:
                            continue
                        try:
                            row = _score_node(st, full, full, idx, node, truth, "mid")
                        except Exception:  # noqa: BLE001 — degenerate node skipped
                            continue
                        if row is None:
                            continue
                        rows.append(dict(
                            row, day=day.isoformat(), ts=ts.isoformat(),
                            instant=i, target=target, design=design,
                            ssr=int(r_val), phase=phase_of(design, i, lit_idx),
                            elapsedH=None if elapsed_h is None else round(elapsed_h, 3),
                            bucket=elapsed_bucket(elapsed_h),
                        ))
            print(f"  {ts.time()}: {sum(1 for r in rows if r['ts'] == ts.isoformat())} scores",
                  flush=True)
    return rows


# ----------------------------------------------------------------- persistence
def _part_path(tag: str, day: date) -> str:
    return os.path.join(RESULTS_DIR, f"{tag}_{day.isoformat()}.json")


def run(args) -> int:
    store = VolStore(args.db)
    tickers = sorted(tk.strip().upper() for tk in args.tickers.split(","))
    days = common_instants(store, tickers)
    if not days:
        raise SystemExit(f"no common intraday instants for {tickers} in {args.db}")
    if args.days:
        keep = {date.fromisoformat(d.strip()) for d in args.days.split(",")}
        days = {d: v for d, v in days.items() if d in keep}
    hub = args.hub.upper()
    targets = (
        [t.strip().upper() for t in args.targets.split(",")]
        if args.targets else [tk for tk in tickers if tk != hub]
    )
    knobs = MessageKnobs(
        mode=args.mode, alpha_t=args.alpha_t,
        amp_cal=args.amp_cal, amp_cross=args.amp_cross,
        residual_half_life=(
            None if args.half_life in (None, "", "inf") else float(args.half_life)
        ),
    )
    designs = tuple(d.strip() for d in args.designs.split(","))
    r_values = tuple(float(r) for r in args.regimes_r.split(","))
    os.makedirs(RESULTS_DIR, exist_ok=True)
    print(f"tag={args.tag} mode={knobs.mode} hl={knobs.residual_half_life} "
          f"memoryless={args.memoryless} days={len(days)} targets={targets}", flush=True)

    for day, instants in days.items():
        part = _part_path(args.tag, day)
        if os.path.exists(part) and not args.force:
            print(f"{day}: part exists, skipping", flush=True)
            continue
        print(f"{day}: {len(instants)} instants", flush=True)
        try:
            rows = run_day(
                store, day, instants, tickers, knobs, designs, r_values,
                targets, hub, args.lit_idx, args.memoryless, args.max_instants,
            )
        except Exception as exc:  # noqa: BLE001 — one bad day never kills the sweep
            print(f"{day}: FAILED ({type(exc).__name__}: {str(exc)[:100]})", flush=True)
            continue
        meta = {"tag": args.tag, "mode": knobs.mode,
                "halfLife": knobs.residual_half_life,
                "memoryless": args.memoryless, "litIdx": args.lit_idx, "hub": hub}
        with open(part, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "rows": rows}, fh, default=str, indent=1)
        print(f"{day}: wrote {len(rows)} rows -> {part}", flush=True)
    return 0


# --------------------------------------------------------------------- report
def _persistence(rows: list[dict]) -> list[dict]:
    """post-phase ATM RMS (graph vs transported prior) by elapsed bucket —
    the §16.2 persistence-accuracy curve."""
    out = []
    for lo, hi in ELAPSED_BUCKETS:
        key = f"{lo}-{hi}h"
        g = [r for r in rows if r.get("bucket") == key]
        if not g:
            continue
        gr = np.array([r["res_atm"] for r in g], float) * 1e4
        ba = np.array([r["base_atm"] for r in g], float) * 1e4
        out.append({
            "bucket": key, "n": len(g),
            "atm_graph_rms": round(float(np.sqrt(np.mean(gr**2))), 2),
            "atm_base_rms": round(float(np.sqrt(np.mean(ba**2))), 2),
        })
    return out


def report(args) -> int:
    parts = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for p in parts:
        with open(p, encoding="utf-8") as fh:
            doc = json.load(fh)
        by_tag[doc["meta"]["tag"]].extend(doc["rows"])
    if not by_tag:
        raise SystemExit(f"no parts under {RESULTS_DIR}")
    print(f"{'tag':<16}{'design':<12}{'phase':<6}{'R':>2}{'n':>6}"
          f"{'atmGr':>8}{'atmBs':>8}{'zStd':>7}")
    summary_doc: dict = {}
    for tag, rows in sorted(by_tag.items()):
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in rows:
            groups[(r["design"], r["phase"], r["ssr"])].append(r)
        for (design, phase, ssr), g in sorted(groups.items()):
            gr = np.array([r["res_atm"] for r in g], float) * 1e4
            ba = np.array([r["base_atm"] for r in g], float) * 1e4
            z = np.array([r["zeta"] for r in g if r.get("zeta") is not None], float)
            print(f"{tag:<16}{design:<12}{phase:<6}{ssr:>2}{len(g):>6}"
                  f"{float(np.sqrt(np.mean(gr**2))):>8.1f}"
                  f"{float(np.sqrt(np.mean(ba**2))):>8.1f}"
                  f"{float(z.std()) if z.size else float('nan'):>7.2f}")
        post = [r for r in rows if r.get("phase") == "post"]
        summary_doc[tag] = {
            "summary": summarize(rows), "persistence": _persistence(post),
        }
        for b in summary_doc[tag]["persistence"]:
            print(f"{tag:<16}  persistence {b['bucket']:>10}: n={b['n']:<4} "
                  f"graph {b['atm_graph_rms']} vs base {b['atm_base_rms']} bp")
    out = os.path.join(RESULTS_DIR, "report.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(summary_doc, fh, indent=1)
    print(f"\nwrote {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday async graph replay (§16.1).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run")
    rp.add_argument("--db", default=DEFAULT_DB)
    rp.add_argument("--tag", required=True)
    rp.add_argument("--tickers", default="SPY,QQQ,IWM")
    rp.add_argument("--hub", default="SPY")
    rp.add_argument("--targets", default="")
    rp.add_argument("--mode", default="smooth_field",
                    choices=("smooth_field", "precision_messages",
                             "layered_dynamic_harmonic"))
    rp.add_argument("--half-life", default=None,
                    help="residual half-life in DAYS (fractional; 'inf' = persistent)")
    rp.add_argument("--memoryless", action="store_true",
                    help="layered arm with the store cleared before every instant")
    rp.add_argument("--designs", default="async_once,async_dark")
    rp.add_argument("--regimes-r", default="0,1")
    rp.add_argument("--lit-idx", type=int, default=3,
                    help="instant index at which async_once lights the target")
    rp.add_argument("--days", default="", help="ISO dates to run (default all)")
    rp.add_argument("--max-instants", type=int, default=None)
    rp.add_argument("--alpha-t", type=float, default=1.0)
    rp.add_argument("--amp-cal", type=float, default=1.0)
    rp.add_argument("--amp-cross", type=float, default=1.0)
    rp.add_argument("--force", action="store_true")
    rp.set_defaults(fn=run)
    pp = sub.add_parser("report")
    pp.set_defaults(fn=report)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
