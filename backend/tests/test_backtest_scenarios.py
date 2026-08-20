"""V3.8 replay-campaign machinery locks (item 6) — fully offline, synthetic.

Layers:
  * the ``--step`` grid generator + the shared CLI resolution (mutual
    exclusion with ``--times``; legacy default byte-identical) and the
    half-day clip through ``session_instants``;
  * the ``--ladder term`` selector (front weeklies + monthlies to 120 DTE,
    capped at 6, 0DTE excluded) and the default-ladder identity;
  * ``load_fixtures`` re-persisting a fixture through ``_persist_db``
    byte-identically and idempotently (re-loading overwrites);
  * the scenario schema (five shipped cells validate; malformed cells raise)
    and its pure resolution helpers (lit_flags / maturity_scope / rung_role);
  * one end-to-end mini-run per design family (loo + dark) over a 2-instant
    2-ticker synthetic VolStore: parts written, resume skips, report emits
    the arm columns including the synthesized ``dark_spot_only`` baseline arm.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta

import pytest

from volfit.data.provider import SyntheticProvider
from volfit.data.store import VolStore

import backtest.scenarios as scenarios
from backtest.capture_intraday import (
    DEFAULT_TIMES,
    LADDERS,
    _is_monthly,
    _persist_db,
    grid_times,
    resolve_times,
    select_expiries,
    select_expiries_term,
    session_instants,
)
from backtest.load_fixtures import load_fixture_file
from backtest.scenarios import (
    SCENARIOS,
    Arm,
    Scenario,
    lit_flags,
    maturity_scope,
    rung_role,
    validate_scenario,
)
from backtest.scenarios_report import BASELINE_ARM, write_report


# ------------------------------------------------------------- grid generator
def test_grid_times_15min_default_window():
    g = grid_times(15)
    assert len(g) == 25  # 09:45..15:45 inclusive at 15 min
    assert g[0] == time(9, 45) and g[-1] == time(15, 45)
    deltas = {
        (datetime.combine(date(2000, 1, 3), b) - datetime.combine(date(2000, 1, 3), a))
        for a, b in zip(g, g[1:])
    }
    assert deltas == {timedelta(minutes=15)}


def test_grid_times_custom_window_and_validation():
    assert grid_times(30, time(10, 0), time(11, 0)) == (
        time(10, 0), time(10, 30), time(11, 0))
    with pytest.raises(ValueError):
        grid_times(0)


def test_grid_half_day_clip_through_session_instants():
    # Black Friday 2024 half-day (13:00 ET close): 09:45..13:00 = 14 instants.
    half = session_instants(date(2024, 11, 29), grid_times(15))
    assert len(half) == 14
    assert all(t.hour * 60 + t.minute <= 18 * 60 for t in half)  # 13:00 EST=18:00 UTC


def test_resolve_times_mutual_exclusion_and_legacy_default():
    assert resolve_times(None, None, None, None) == DEFAULT_TIMES  # byte-identical
    assert resolve_times("10:00,12:00", None, None, None) == (time(10, 0), time(12, 0))
    assert resolve_times(None, 15, None, None) == grid_times(15)
    assert resolve_times(None, 60, "10:00", "12:00") == (
        time(10, 0), time(11, 0), time(12, 0))
    with pytest.raises(SystemExit):
        resolve_times("10:00", 15, None, None)  # --times XOR --step
    with pytest.raises(SystemExit):
        resolve_times(None, None, "10:00", None)  # --from needs --step


# ----------------------------------------------------------------- term ladder
def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 15)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def test_term_ladder_shape_cap_and_default_identity():
    day = date(2026, 8, 20)
    monthlies = [_third_friday(2026, m) for m in (9, 10, 11, 12)]
    far_monthly = _third_friday(2027, 1)  # DTE > 120: never picked
    weeklies = [day + timedelta(days=d) for d in (1, 4, 8)]
    weeklies = [w for w in weeklies if not _is_monthly(w)]
    board = {day, far_monthly, day + timedelta(days=150), *monthlies, *weeklies}
    kept = select_expiries_term(board, day)
    assert day not in kept  # 0DTE excluded from the term ladder
    assert far_monthly not in kept
    assert kept == sorted(kept) and len(kept) <= 6
    for w in weeklies:  # front weeklies are nearest — they survive the cap
        assert w in kept
    in_range = [m for m in monthlies if (m - day).days <= 120]
    assert kept == sorted(set(weeklies) | set(in_range))[:6]
    # default --ladder 0dte IS the legacy selector (byte-identical path)
    assert LADDERS["0dte"] is select_expiries
    assert LADDERS["term"] is select_expiries_term


# ------------------------------------------------------- fixture loader (CLI)
REF = date(2026, 6, 10)  # a Wednesday trading day
T1 = datetime(2026, 6, 10, 14, 0)
T2 = datetime(2026, 6, 10, 15, 30)
EXPIRIES = (REF + timedelta(days=30), REF + timedelta(days=91))


def _mini_doc(ticker: str) -> dict:
    """A tiny synthetic intraday fixture: the deterministic synthetic chain
    (belly only, |K/S - 1| <= 0.2) snapshotted at two instants."""
    prov = SyntheticProvider(reference_date=REF, tickers=(ticker,))
    ch = prov.fetch_chain(ticker, expiries=list(EXPIRIES))
    quotes = [
        {"expiry": q.expiry.isoformat(), "strike": float(q.strike), "cp": q.call_put,
         "bid": float(q.bid), "ask": float(q.ask), "size": int(q.open_interest)}
        for q in ch.quotes if 0.8 <= q.strike / ch.spot <= 1.2
    ]
    return {
        "asset": ticker, "day": REF.isoformat(), "exercise_style": "american",
        "expiries": [e.isoformat() for e in EXPIRIES],
        "snapshots": [
            {"ts": T1.isoformat(), "spot": float(ch.spot), "quotes": quotes},
            {"ts": T2.isoformat(), "spot": float(ch.spot), "quotes": quotes},
        ],
    }


def _snap_key(snap):
    return (
        snap.ticker, snap.spot, snap.timestamp, snap.exercise_style,
        snap.tick_size, sorted(snap.settlement) if snap.settlement else None,
        [(q.expiry, q.call_put, q.strike, q.bid, q.ask, q.open_interest)
         for q in snap.quotes],
    )


def test_load_fixtures_round_trip_and_idempotency(tmp_path):
    doc = _mini_doc("SPY")
    db_a, db_b = str(tmp_path / "a.sqlite"), str(tmp_path / "b.sqlite")
    assert _persist_db(db_a, "SPY", doc) == 2  # the reference persistence path
    path = tmp_path / "SPY_2026-06-10.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    ticker, n = load_fixture_file(db_b, str(path))
    assert (ticker, n) == ("SPY", 2)
    with VolStore(db_a) as va, VolStore(db_b) as vb:
        for ts in (T1, T2):
            a, b = va.snapshot_at("SPY", ts), vb.snapshot_at("SPY", ts)
            assert a is not None and a.timestamp == ts
            assert _snap_key(a) == _snap_key(b)  # byte-identical round trip
            assert b.settlement and b.tick_size == 0.01  # load-bearing stamps
    # idempotent: re-loading OVERWRITES (no duplicate snapshot rows)
    load_fixture_file(db_b, str(path))
    with VolStore(db_b) as vb:
        assert len(vb.list_snapshots(["SPY"])) == 2
        assert _snap_key(vb.snapshot_at("SPY", T1)) == _snap_key(
            VolStore(db_a).snapshot_at("SPY", T1))


# --------------------------------------------------------------- schema locks
def test_shipped_scenarios_validate_with_ratified_parameters():
    assert set(SCENARIOS) == {
        "loo_basket_1mat", "dark_spot_only", "dark_graph_msg",
        "dark_graph_layered", "leave3out_5exp",
    }
    for name, sc in SCENARIOS.items():
        assert sc.name == name
        validate_scenario(sc)  # must not raise
        assert set(sc.tickers) == {"SPY", "NVDA", "AAPL", "MSFT"}  # the basket
    assert SCENARIOS["loo_basket_1mat"].design == "loo"
    assert SCENARIOS["loo_basket_1mat"].maturity_filter == "single"
    assert SCENARIOS["dark_graph_msg"].modes == (Arm("precision_messages"),)
    assert SCENARIOS["dark_graph_layered"].modes == (
        Arm("layered_dynamic_harmonic", half_life=0.1),)
    l3 = SCENARIOS["leave3out_5exp"]
    assert l3.min_rungs == 5
    assert l3.lit_map == {("*", 1): False, ("*", 2): True, ("*", 3): False,
                          ("*", 4): True, ("*", 5): False}
    for sc_name in ("dark_spot_only", "dark_graph_msg", "dark_graph_layered"):
        sc = SCENARIOS[sc_name]
        assert sc.lit_map[("SPY", "*")] is True  # SPY stays lit
        assert set(sc.targets) == {"NVDA", "AAPL", "MSFT"}


def test_schema_validation_rejects_malformed_cells():
    ok = dict(name="x", tickers=("A", "B"), design="dark",
              modes=(Arm("smooth_field"),), targets=("A",),
              lit_map={("A", "*"): False})
    validate_scenario(Scenario(**ok))
    with pytest.raises(ValueError):
        validate_scenario(Scenario(**{**ok, "design": "nope"}))
    with pytest.raises(ValueError):
        validate_scenario(Scenario(**{**ok, "modes": (Arm("bad_mode"),)}))
    with pytest.raises(ValueError):  # layered arm needs a half-life
        validate_scenario(Scenario(**{**ok, "modes": (Arm("layered_dynamic_harmonic"),)}))
    with pytest.raises(ValueError):  # targets must be a subset of tickers
        validate_scenario(Scenario(**{**ok, "targets": ("Z",)}))
    with pytest.raises(ValueError):  # dark needs a lit_map
        validate_scenario(Scenario(**{**ok, "lit_map": None}))
    with pytest.raises(ValueError):  # loo keeps every node lit
        validate_scenario(Scenario(**{**ok, "design": "loo"}))
    with pytest.raises(ValueError):  # rungs are 1-indexed
        validate_scenario(Scenario(**{**ok, "lit_map": {("A", 0): False}}))


def test_lit_flags_min_rungs_guard_and_wildcards():
    sc = SCENARIOS["leave3out_5exp"]
    five = [f"2026-0{m}-17" for m in range(1, 6)]
    rungs = {"NVDA": five, "SPY": five[:3]}
    flags = lit_flags(sc, rungs)
    assert [flags[("NVDA", iso)] for iso in five] == [False, True, False, True, False]
    assert all(flags[("SPY", iso)] for iso in five[:3])  # < 5 rungs: fully lit
    # loo design: everything lit regardless of any map
    assert all(lit_flags(SCENARIOS["loo_basket_1mat"], rungs).values())


def test_rung_role_interp_vs_extrap():
    assert rung_role([2, 4], 3) == "interp"
    assert rung_role([2, 4], 1) == "extrap"
    assert rung_role([2, 4], 5) == "extrap"
    assert rung_role([], 1) is None  # fully dark ticker: no role


def test_maturity_scope_single_int_and_explicit():
    day = REF
    near, far, later = "2026-06-25", "2026-07-10", "2026-08-21"  # 15/30/72 DTE
    rungs = {"A": [near, far], "B": [far, later]}
    sc = Scenario(name="s", tickers=("A", "B"), design="loo",
                  modes=(Arm("smooth_field"),), targets=("A",),
                  maturity_filter="single")
    # smallest COMMON expiry with DTE >= 20 is `far` (near fails the floor)
    assert maturity_scope(sc, rungs, day) == {"A": {far}, "B": {far}}
    sc2 = Scenario(name="s2", tickers=("A", "B"), design="loo",
                   modes=(Arm("smooth_field"),), targets=("A",),
                   maturity_filter=2)
    assert maturity_scope(sc2, rungs, day) == {"A": {far}, "B": {later}}
    sc3 = Scenario(name="s3", tickers=("A", "B"), design="loo",
                   modes=(Arm("smooth_field"),), targets=("A",),
                   maturity_filter=(far,))
    assert maturity_scope(sc3, rungs, day) == {"A": {far}, "B": {far}}
    sc4 = Scenario(name="s4", tickers=("A", "B"), design="loo",
                   modes=(Arm("smooth_field"),), targets=("A",))
    assert maturity_scope(sc4, rungs, day) == {"A": {near, far}, "B": {far, later}}


# ----------------------------------------------------- end-to-end mini-runs
@pytest.fixture(scope="module")
def mini_db(tmp_path_factory):
    """2 tickers x 2 instants x 2 expiries, persisted through _persist_db —
    the same synthetic-chain-into-VolStore shape the replay locks use."""
    db = str(tmp_path_factory.mktemp("scen_db") / "mini.sqlite")
    for tk in ("SPY", "NVDA"):
        assert _persist_db(db, tk, _mini_doc(tk)) == 2
    return db


MINI_DARK = Scenario(
    name="mini_dark", tickers=("SPY", "NVDA"), design="dark",
    modes=(Arm("smooth_field"), Arm("layered_dynamic_harmonic", half_life=0.1)),
    targets=("NVDA",), lit_map={("NVDA", "*"): False})
MINI_LOO = Scenario(
    name="mini_loo", tickers=("SPY", "NVDA"), design="loo",
    modes=(Arm("smooth_field"),), targets=("NVDA",), maturity_filter="single")


@pytest.fixture(scope="module")
def mini_run(mini_db, tmp_path_factory):
    out = str(tmp_path_factory.mktemp("scen_out"))
    written = scenarios.run(mini_db, [MINI_DARK, MINI_LOO], out_dir=out)
    return out, written


def _rows(out: str, name: str) -> list[dict]:
    with open(os.path.join(out, f"{name}_{REF.isoformat()}.json"), encoding="utf-8") as fh:
        return json.load(fh)["rows"]


def test_mini_dark_run_scores_dark_nodes_per_arm(mini_run):
    out, written = mini_run
    assert len(written) == 2
    rows = _rows(out, "mini_dark")
    assert rows, "the dark design must score the dark NVDA nodes"
    assert {r["arm"] for r in rows} == {"smooth_field", "layered_hl0.1"}
    for r in rows:
        assert r["ticker"] == "NVDA" and r["design"] == "dark"
        assert r["rung"] in (1, 2) and r["rungRole"] is None  # NVDA fully dark
        assert r["bucket"] == "0.75-1.75h"  # 14:00 -> 15:30 = 1.5h since freeze
        assert isinstance(r["res_atm"], float) and isinstance(r["base_atm"], float)
        assert r["zeta"] is not None


def test_mini_loo_run_holds_out_the_single_maturity(mini_run):
    out, _written = mini_run
    rows = _rows(out, "mini_loo")
    assert rows, "loo must score the held-out NVDA node"
    single = EXPIRIES[0].isoformat()  # nearest common DTE >= 20
    for r in rows:
        assert r["ticker"] == "NVDA" and r["design"] == "loo"
        assert r["expiry"] == single and r["arm"] == "smooth_field"
        assert isinstance(r["res_atm"], float) and isinstance(r["base_atm"], float)


def test_mini_run_resume_skips_existing_parts(mini_run, mini_db):
    out, _written = mini_run
    again = scenarios.run(mini_db, [MINI_DARK, MINI_LOO], out_dir=out)
    assert again == []  # both parts exist -> nothing recomputed


def test_report_emits_arm_columns_including_baseline(mini_run):
    out, _written = mini_run
    html_path, json_path = write_report(out)
    assert os.path.exists(html_path) and os.path.exists(json_path)
    with open(json_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    by_arm = {(rec["scenario"], rec["arm"]): rec for rec in doc["byArm"]}
    assert ("mini_dark", "smooth_field") in by_arm
    assert ("mini_dark", "layered_hl0.1") in by_arm
    assert ("mini_dark", BASELINE_ARM) in by_arm  # the transported-prior arm
    assert ("mini_loo", BASELINE_ARM) in by_arm
    base = by_arm[("mini_dark", BASELINE_ARM)]
    assert base["atm_graph_rms"] == base["atm_base_rms"]  # baseline IS the prior
    assert base["atm_skill"] == 0.0 and base["zeta_std"] is None
    for rec in doc["byArm"]:
        assert "cov95" in rec and "zeta_std" in rec and "smile_full" in rec
    html = open(html_path, encoding="utf-8").read()
    assert BASELINE_ARM in html and "mini_loo" in html and "mini_dark" in html
