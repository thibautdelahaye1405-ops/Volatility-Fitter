"""Tests for the campaign sweep mode of ``backtest.validate_intraday_clock``.

The per-node calibration path is exercised for real by the capture campaign
(and the single-snapshot mode's output is part of the R2 acceptance record);
here we lock the sweep plumbing — instant selection, grouping, aggregation,
exit codes — with the calibration stubbed.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

import backtest.validate_intraday_clock as vic
from volfit.data.store import VolStore
from volfit.data.types import ChainSnapshot, OptionQuote


def _stamps(day: int, hours: list[int]) -> list[datetime]:
    return [datetime(2026, 7, day, h, 0) for h in hours]


def test_pick_instants_spread_includes_ends():
    ts = _stamps(10, [10, 11, 12, 13, 14, 15, 16])
    picked = vic.pick_instants(ts, 3)
    assert picked == [ts[0], ts[3], ts[6]]  # first, middle, last
    assert vic.pick_instants(ts, 1) == [ts[-1]]  # the before-close instant
    assert vic.pick_instants(ts, 0) == ts  # 0 = all
    assert vic.pick_instants(ts, 99) == ts  # more than available = all
    assert vic.pick_instants(list(reversed(ts)), 2) == [ts[0], ts[-1]]  # sorts


def _seed_store(path: str) -> None:
    """Two tickers x two days x three instants of minimal one-quote chains."""
    with VolStore(path) as vs:
        for ticker in ("SPY", "QQQ"):
            for day in (9, 10):
                for h in (14, 16, 19):
                    ts = datetime(2026, 7, day, h, 0)
                    vs.save_snapshot(ChainSnapshot(
                        ticker=ticker, spot=100.0, timestamp=ts,
                        quotes=[OptionQuote(
                            ticker=ticker, expiry=date(2026, 7, day), strike=100.0,
                            call_put="C", bid=1.0, ask=1.2, last=None, volume=None,
                            open_interest=None, timestamp=ts,
                        )],
                        exercise_style="american",
                    ))


def test_validate_all_groups_and_aggregates(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "v.sqlite")
    _seed_store(db)
    seen: list[tuple[str, datetime]] = []

    def stub(snap, ticker):
        seen.append((ticker, snap.timestamp))
        return 0, ["  node: ok"], 123.4

    monkeypatch.setattr(vic, "validate_snapshot", stub)
    rc = vic.validate_all(db, None, per_day=2)
    out = capsys.readouterr().out
    # 2 tickers x 2 days x 2 instants (first + last of the 3 stored).
    assert rc == 0 and len(seen) == 8
    hours = {ts.hour for _, ts in seen}
    assert hours == {14, 19}  # the middle 16:00 instant is skipped at per_day=2
    assert out.count("worst 123.4bp - ok") == 8
    assert "CAMPAIGN VALIDATION OK (8 snapshots, 0 failing node(s))" in out


def test_validate_all_failure_prints_detail_and_fails(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / "v.sqlite")
    _seed_store(db)

    def stub(snap, ticker):
        if ticker == "QQQ" and snap.timestamp.day == 10:
            return 1, ["  2026-07-10: FAILED (boom)"], None
        return 0, ["  node: ok"], 50.0

    monkeypatch.setattr(vic, "validate_snapshot", stub)
    rc = vic.validate_all(db, ["QQQ"], per_day=1)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAILED (boom)" in out  # per-node detail surfaces on failure
    assert "CAMPAIGN VALIDATION FAILED (2 snapshots, 1 failing node(s))" in out
    assert "SPY" not in out  # ticker restriction respected


def _one_sided_snapshot(ts: datetime) -> ChainSnapshot:
    """A same-day chain with NO two-sided pair anywhere (bid missing), the
    near-settle 0DTE pattern: parity has nothing to regress on."""
    expiry = ts.date()
    quotes = [
        OptionQuote("SPY", expiry, k, cp, bid=None, ask=1.0, last=None,
                    volume=None, open_interest=None, timestamp=ts)
        for k in (95.0, 100.0, 105.0) for cp in ("C", "P")
    ]
    return ChainSnapshot("SPY", 100.0, ts, quotes, "american")


def test_thin_chain_is_skipped_not_failed():
    """No parity forward = quarantined data, not a clock failure: the node is
    reported SKIPPED and the snapshot still validates (the IWM near-settle
    case from the 2026-07-15 early sweep)."""
    snap = _one_sided_snapshot(datetime(2026, 7, 10, 19, 45))
    failures, lines, worst = vic.validate_snapshot(snap, "SPY")
    assert failures == 0 and worst is None
    assert lines == ["  2026-07-10: SKIPPED (no parity forward - thin/one-sided chain)"]


def test_resolved_forward_missing_parity_raises_readable_error():
    """The production path raises UnknownNodeError (-> a readable 404), never
    an AttributeError, when a selected node has no parity regression."""
    from volfit.api.state import AppState, UnknownNodeError
    from volfit.replay_report import _StoredChains

    snap = _one_sided_snapshot(datetime(2026, 7, 10, 19, 45))
    state = AppState(snap.timestamp.date(), provider=_StoredChains({"SPY": snap}))
    state.set_expiries("SPY", sorted(snap.expiries()))
    with pytest.raises(UnknownNodeError, match="no parity forward"):
        state.resolved_forward("SPY", date(2026, 7, 10))
