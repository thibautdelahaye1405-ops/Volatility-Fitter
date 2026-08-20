"""Scripted leave-out replay scenarios over captured intraday days (V3.8 item 6).

Declarative :class:`Scenario` cells over a stored intraday DB (the
``run_replay_day.ps1`` capture: ``--step 15 --ladder term``, basket
NVDA/AAPL/MSFT + SPY). Per (scenario, day): the FIRST stored instant is frozen
as the active prior per ticker; each later instant is rebuilt
(``graph_intraday.instant_state``: intraday clock ON, same-day expiries
excluded) and solved once per arm, the layered arm's residual store threaded
chronologically. Designs: ``loo`` = every node lit, each target withheld in
turn via ``solve(hold_out=...)`` (graph_loo's full_loo protocol); ``dark`` =
lit flags per ``lit_map`` for the WHOLE day, dark targets scored against their
own held-out calibration. The transported-prior baseline ("dark, spot-only")
is NOT a separate arm — it is the ``base_*`` columns on every scored row;
``backtest.scenarios_report`` surfaces it as the ``dark_spot_only`` arm.
Parts are per (scenario, day), skipped when present (resumable); campaign runs
belong in the USER'S window.

Run::

    python -m backtest.scenarios run --db backtest/results/replay_day.sqlite
    python -m backtest.scenarios report
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Sequence

from volfit.api import priors
from volfit.api.graph_extrapolation import _calibrated_handles, solve
from volfit.api.schemas import GraphExtrapolateRequest
from volfit.data.store import VolStore

from backtest.graph_edges import EdgeConfig, build_directed_edges, build_message_edges
from backtest.graph_intraday import (
    DEFAULT_DB, elapsed_bucket, frac_day, hub_directed, instant_state,
)
from backtest.graph_loo import MessageKnobs, _baseline_maps, _score_node

OUT_DIR = os.path.join(os.path.dirname(__file__), "results", "scenarios")
MODES = ("smooth_field", "precision_messages", "layered_dynamic_harmonic")
#: maturity_filter="single": smallest common DTE at or above this floor.
SINGLE_MIN_DTE = 20


# ---------------------------------------------------------------------- schema
@dataclass(frozen=True)
class Arm:
    """One propagation arm: the mode + (layered only) the residual half-life."""

    mode: str
    half_life: float | None = None

    @property
    def label(self) -> str:
        return (f"layered_hl{self.half_life:g}"
                if self.mode == "layered_dynamic_harmonic" else self.mode)


@dataclass(frozen=True)
class Scenario:
    """One declarative leave-out cell.

    ``maturity_filter`` scopes which rungs are SCORED (the solved universe
    keeps every rung as context): None = all; int = that 1-indexed rung;
    ``"single"`` = the expiry COMMON to every scenario ticker with the
    smallest DTE >= SINGLE_MIN_DTE (each ticker's own nearest such rung when
    no common expiry qualifies); an iso-date tuple = exactly those expiries.
    ``lit_map`` (dark only) keys are (ticker, rung) with ``"*"`` wildcards on
    either side; rungs are 1-indexed positions in the ticker's sorted expiry
    ladder at each instant. ``min_rungs`` guards the map: a ticker with fewer
    rungs stays fully lit (source-only)."""

    name: str
    tickers: tuple[str, ...]
    design: str  # "loo" | "dark"
    modes: tuple[Arm, ...]
    targets: tuple[str, ...]
    maturity_filter: object = None
    lit_map: Mapping[tuple, bool] | None = None
    min_rungs: int | None = None


def validate_scenario(sc: Scenario) -> None:
    """Raise ValueError on any schema violation (checked before every run)."""
    def _bad(msg: str):
        raise ValueError(f"{sc.name}: {msg}")

    if sc.design not in ("loo", "dark"):
        _bad(f"design must be 'loo' or 'dark', got {sc.design!r}")
    if not sc.tickers or not sc.targets:
        _bad("tickers and targets must be non-empty")
    if not set(sc.targets) <= set(sc.tickers):
        _bad("targets must be a subset of tickers")
    if not sc.modes:
        _bad("at least one arm required")
    for arm in sc.modes:
        if arm.mode not in MODES:
            _bad(f"unknown mode {arm.mode!r}")
        if arm.mode == "layered_dynamic_harmonic" and arm.half_life is None:
            _bad("layered arm needs a half_life")
    if sc.design == "loo" and sc.lit_map:
        _bad("loo keeps every node lit (hold_out withholds)")
    if sc.design == "dark" and not sc.lit_map:
        _bad("dark design needs a lit_map")
    mf = sc.maturity_filter
    if not (mf is None or mf == "single" or isinstance(mf, (int, list, tuple))):
        _bad(f"bad maturity_filter {mf!r}")
    for tk, r in (sc.lit_map or {}):
        if tk != "*" and tk not in sc.tickers:
            _bad(f"lit_map ticker {tk!r} not in tickers")
        if r != "*" and not (isinstance(r, int) and r >= 1):
            _bad(f"lit_map rung {r!r} must be int >= 1 or '*'")


# ---------------------------------------------------- the five shipped cells
_NAMES = ("NVDA", "AAPL", "MSFT")
#: The item-6 basket: 3 names + SPY (the index stand-in — the intraday REST
#: path lacks SPX/SPXW multi-root discovery; recorded as a roadmap rider).
BASKET = ("SPY",) + _NAMES
ARM_CONTROL = Arm("smooth_field")  # the control column
ARM_MSG = Arm("precision_messages")  # graph option 1 (production default)
ARM_LAYERED = Arm("layered_dynamic_harmonic", half_life=0.1)  # graph option 2
ALL_ARMS = (ARM_CONTROL, ARM_MSG, ARM_LAYERED)
_DARK_NAMES = {("SPY", "*"): True, ("NVDA", "*"): False,
               ("AAPL", "*"): False, ("MSFT", "*"): False}

#: The five ratified cells. loo_basket_1mat: full LOO at ONE shared maturity
#: (nearest common DTE >= 20). dark_spot_only: the transported-prior baseline
#: view — a dark run whose interesting numbers are the base_* columns (the
#: report's dark_spot_only arm; the control solve only produces scored rows).
#: dark_graph_msg / dark_graph_layered: names dark all day, SPY lit, graph
#: option 1 / 2. leave3out_5exp: per ticker with >= 5 rungs, rungs 2 and 4 lit
#: (1-indexed), 1/3/5 dark — rung 3 is INTERPOLATION, 1/5 EXTRAPOLATION
#: (rungRole separates them in the report).
SCENARIOS: dict[str, Scenario] = {
    "loo_basket_1mat": Scenario(
        name="loo_basket_1mat", tickers=BASKET, design="loo", modes=ALL_ARMS,
        targets=BASKET, maturity_filter="single"),
    "dark_spot_only": Scenario(
        name="dark_spot_only", tickers=BASKET, design="dark",
        modes=(ARM_CONTROL,), targets=_NAMES, lit_map=_DARK_NAMES),
    "dark_graph_msg": Scenario(
        name="dark_graph_msg", tickers=BASKET, design="dark",
        modes=(ARM_MSG,), targets=_NAMES, lit_map=_DARK_NAMES),
    "dark_graph_layered": Scenario(
        name="dark_graph_layered", tickers=BASKET, design="dark",
        modes=(ARM_LAYERED,), targets=_NAMES, lit_map=_DARK_NAMES),
    "leave3out_5exp": Scenario(
        name="leave3out_5exp", tickers=BASKET, design="dark", modes=ALL_ARMS,
        targets=BASKET, min_rungs=5,
        lit_map={("*", 1): False, ("*", 2): True, ("*", 3): False,
                 ("*", 4): True, ("*", 5): False}),
}


# ------------------------------------------------------------ pure resolution
def lit_flags(sc: Scenario, rungs: dict[str, list[str]]) -> dict[tuple[str, str], bool]:
    """(ticker, iso) -> lit for one instant's ladder. loo = everything lit;
    dark resolves lit_map most-specific-first: (tk, r), (tk, '*'), ('*', r),
    ('*', '*'); unmatched nodes (and tickers under min_rungs) stay lit."""
    flags: dict[tuple[str, str], bool] = {}
    for tk, isos in rungs.items():
        eligible = sc.min_rungs is None or len(isos) >= sc.min_rungs
        for r, iso in enumerate(isos, start=1):
            hit = [sc.lit_map[k] for k in ((tk, r), (tk, "*"), ("*", r), ("*", "*"))
                   if k in sc.lit_map] if sc.design == "dark" and sc.lit_map and eligible else []
            flags[(tk, iso)] = bool(hit[0]) if hit else True
    return flags


def maturity_scope(sc: Scenario, rungs: dict[str, list[str]], day: date) -> dict[str, set[str]]:
    """Per ticker, the ISO expiries whose rows are scored (see Scenario doc)."""
    mf = sc.maturity_filter
    if mf is None:
        return {tk: set(isos) for tk, isos in rungs.items()}
    if isinstance(mf, int):
        return {tk: ({isos[mf - 1]} if len(isos) >= mf else set())
                for tk, isos in rungs.items()}
    if isinstance(mf, (list, tuple)):
        return {tk: set(isos) & set(mf) for tk, isos in rungs.items()}

    def _ok(iso: str) -> bool:
        return (date.fromisoformat(iso) - day).days >= SINGLE_MIN_DTE

    common = sorted(iso for iso in set.intersection(
        *(set(isos) for isos in rungs.values())) if _ok(iso)) if rungs else []
    if common:
        return {tk: {common[0]} for tk in rungs}
    # fallback: each ticker's own nearest qualifying rung
    return {tk: ({min(c)} if (c := [i for i in isos if _ok(i)]) else set())
            for tk, isos in rungs.items()}


def rung_role(lit_rungs: Sequence[int], r: int) -> str | None:
    """A dark rung's role given the ticker's lit rungs: lit on both sides =
    'interp', one side = 'extrap', no lit rung on the ticker = None."""
    lo = any(x < r for x in lit_rungs)
    hi = any(x > r for x in lit_rungs)
    return "interp" if lo and hi else ("extrap" if lo or hi else None)


# ------------------------------------------------------------------ the driver
def _instants_by_day(store: VolStore, tickers, min_instants: int = 2) -> dict[date, list[datetime]]:
    """graph_intraday.common_instants with the min-instant floor as a knob
    (copied per the V3.8 note, <= 10 lines: scenarios need only a prior
    instant + one scored instant; the campaign module pins >= 4)."""
    per: dict[str, set] = defaultdict(set)
    for tk, _sid, ts in store.list_snapshots(list(tickers)):
        per[tk].add(ts)
    if any(tk not in per for tk in tickers):
        return {}
    by_day: dict[date, list[datetime]] = defaultdict(list)
    for ts in set.intersection(*(per[tk] for tk in tickers)):
        by_day[ts.date()].append(ts)
    return {d: sorted(v) for d, v in sorted(by_day.items()) if len(v) >= min_instants}


def _arm_request(sc_name: str, arm: Arm, sigma: dict, tmap: dict, hub: str) -> GraphExtrapolateRequest:
    """graph_intraday._request's construction, with the baseline maps computed
    ONCE per instant (shared across arms) and the residual store identity
    pinned per (scenario, arm) so it survives across instants unpurged."""
    knobs = MessageKnobs(mode=arm.mode, residual_half_life=arm.half_life)
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
        residualConfigVersion=f"scn:{sc_name}:{knobs.mode}:{knobs.residual_half_life}",
    )


def _score_nodes(st, req, full, sc, scope, flags, rungs, now_day: float) -> list[dict]:
    """Score target nodes for one solved instant. dark: every DARK target node
    in scope vs its own held-out calibration (graph_intraday's protocol);
    loo: withhold each in-scope target node in turn (graph_loo's full_loo)."""
    dark = sc.design == "dark"
    lit_rungs = {tk: [r for r, iso in enumerate(rungs[tk], 1) if flags[(tk, iso)]]
                 for tk in rungs}
    out = []
    for idx, node in enumerate(full.universe.nodes):
        tk = node.ticker
        if tk not in sc.targets or node.expiry not in scope.get(tk, set()):
            continue
        if dark and flags.get((tk, node.expiry), True):
            continue  # only DARK nodes are scored in the dark design
        if not dark and (not full.calibrated[idx]
                         or not full.priors_meta[idx].valid_for_validation):
            continue
        try:
            if dark:
                truth, held = _calibrated_handles(st, tk, node.expiry, "mid"), full
            else:
                truth = full.obs_value_by_idx[idx]
                held = solve(st, req, hold_out=frozenset({node.name}),
                             now_day=now_day, obs_ages_days={})
            if truth is None or held is None:
                continue
            row = _score_node(st, full, held, idx, node, truth, "mid")
        except Exception:  # noqa: BLE001 — degenerate node skipped
            continue
        if row is not None:
            r = rungs[tk].index(node.expiry) + 1
            out.append(dict(row, rung=r,
                            rungRole=rung_role(lit_rungs[tk], r) if dark else None))
    return out


def _run_day(store: VolStore, sc: Scenario, day: date, instants, hub: str) -> list[dict]:
    """One (scenario, day): first instant frozen as the prior, each later
    instant solved once per arm, residual stores threaded chronologically.
    ``elapsedH``/``bucket`` = hours since the prior freeze (the §16.2 axis
    for all-day-dark designs — the targets have no intraday lit instant)."""
    tickers = list(sc.tickers)
    state0 = instant_state(store, tickers, instants[0])
    snaps = {tk: priors.capture_snapshot(state0, tk, "mid", lv=False) for tk in tickers}
    t0 = frac_day(instants[0])
    cells: dict[str, dict] = defaultdict(dict)  # per-arm residual stores
    rows: list[dict] = []
    for i, ts in enumerate(instants[1:], start=1):
        try:
            st = instant_state(store, tickers, ts)
        except Exception as exc:  # noqa: BLE001 — a broken instant is skipped
            print(f"  {ts}: SKIPPED ({type(exc).__name__})", flush=True)
            continue
        for tk in (tk for tk in tickers if snaps.get(tk) is not None):
            st.set_active_prior(tk, snaps[tk], "saved")
        st.set_options(st.options().model_copy(
            update={"dynamicsRegime": "sticky_moneyness"}))  # R=0 pinned (one cell)
        rungs = {tk: [e.isoformat() for e in sorted(st.selected_expiries(tk))]
                 for tk in tickers}
        flags = lit_flags(sc, rungs)
        for (tk, iso), lit in flags.items():
            st.set_node_lit(tk, iso, lit)
        scope = maturity_scope(sc, rungs, day)
        sigma, tmap = _baseline_maps(st)
        elapsed_h = (frac_day(ts) - t0) * 24.0
        for arm in sc.modes:
            cell = cells[arm.label]
            pre = dict(cell)  # frozen states: shallow copy is safe (graph_loo)
            st.graph_dynamic_residuals = cell
            req = _arm_request(sc.name, arm, sigma, tmap, hub)
            full = solve(st, req, now_day=frac_day(ts), obs_ages_days={})
            if full is None:
                continue
            if sc.design != "dark":  # holdouts read the pre-instant store
                st.graph_dynamic_residuals = pre
            scored = _score_nodes(st, req, full, sc, scope, flags, rungs, frac_day(ts))
            for row in scored:
                rows.append(dict(
                    row, scenario=sc.name, design=sc.design, arm=arm.label,
                    day=day.isoformat(), ts=ts.isoformat(), instant=i,
                    elapsedH=round(elapsed_h, 3), bucket=elapsed_bucket(elapsed_h),
                ))
        print(f"  {ts.time()}: {sum(1 for r in rows if r['ts'] == ts.isoformat())} scores",
              flush=True)
    return rows


def run(db: str, scenarios: Sequence[Scenario], days: Sequence[str] | None = None,
        out_dir: str = OUT_DIR, hub: str = "SPY", force: bool = False) -> list[str]:
    """Run scenarios over the store's common days; one part file per
    (scenario, day), skipped when present (resume). Returns paths written."""
    os.makedirs(out_dir, exist_ok=True)
    store = VolStore(db)
    want = {date.fromisoformat(d) for d in days} if days else None
    written: list[str] = []
    for sc in scenarios:
        validate_scenario(sc)
        by_day = _instants_by_day(store, sc.tickers)
        if want is not None:
            by_day = {d: v for d, v in by_day.items() if d in want}
        if not by_day:
            print(f"{sc.name}: no common instants for {sc.tickers} in {db}", flush=True)
            continue
        for day, instants in by_day.items():
            part = os.path.join(out_dir, f"{sc.name}_{day.isoformat()}.json")
            if os.path.exists(part) and not force:
                print(f"{sc.name} {day}: part exists, skipped", flush=True)
                continue
            print(f"{sc.name} {day}: {len(instants)} instants", flush=True)
            rows = _run_day(store, sc, day, instants, hub)
            meta = {"scenario": sc.name, "design": sc.design, "day": day.isoformat(),
                    "arms": [a.label for a in sc.modes], "tickers": list(sc.tickers)}
            with open(part, "w", encoding="utf-8") as fh:
                json.dump({"meta": meta, "rows": rows}, fh, default=str, indent=1)
            written.append(part)
            print(f"{sc.name} {day}: wrote {len(rows)} rows -> {part}", flush=True)
    return written


# ------------------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description="Scripted leave-out replay scenarios (V3.8).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("run")
    rp.add_argument("--db", default=DEFAULT_DB)
    rp.add_argument("--scenarios", default=",".join(SCENARIOS),
                    help=f"comma-separated names (default all: {','.join(SCENARIOS)})")
    rp.add_argument("--days", default="", help="ISO dates to run (default all common)")
    rp.add_argument("--out-dir", default=OUT_DIR)
    rp.add_argument("--hub", default="SPY")
    rp.add_argument("--force", action="store_true")
    pp = sub.add_parser("report")
    pp.add_argument("--dir", default=OUT_DIR)
    args = ap.parse_args()
    if args.cmd == "report":
        from backtest.scenarios_report import write_report

        print("wrote {0}\nwrote {1}".format(*write_report(args.dir)))
        return 0
    names = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    if any(n not in SCENARIOS for n in names):
        raise SystemExit(f"unknown scenario(s) in {names}; known: {list(SCENARIOS)}")
    run(args.db, [SCENARIOS[n] for n in names],
        days=[d.strip() for d in args.days.split(",") if d.strip()] or None,
        out_dir=args.out_dir, hub=args.hub.upper(), force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
