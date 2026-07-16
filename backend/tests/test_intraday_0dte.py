"""First 0DTE stress-pack exit gate (R2 item 10) — REAL captured SPY chains.

The fixture is one instant (12:30 ET) of the REST-captured SPY 2026-07-10
day, trimmed to {same-day, next daily, monthly anchor} — 862 real NBBO
quotes (tests/fixtures/intraday_spy_0dte.json; regenerate via
``backtest.capture_intraday_rest`` and re-trim, see the fixture's ``source``
note). On real data these lock:

  * the capture persistence round-trip (``_persist_db`` -> ``snapshot_at``),
    settlement map included;
  * the intraday clock prices the SAME-DAY node sub-day (t = 3.5h to the
    16:00 ET settle — the legacy clock's unrepresentable t = 0);
  * every node calibrates finitely below the UNSTABLE threshold ("no NaN/IV
    explosions on valid quotes", the roadmap exit-gate wording);
  * the same-day parity discount is clamped over its sub-day horizon
    (data/forwards.py ``_clamp_horizon``), not passed through absurd.
"""

from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime

import pytest

from backtest.capture_intraday import _persist_db
from backtest.validate_intraday_clock import validate_snapshot
from volfit.data.forwards import RATE_MIN, implied_forward
from volfit.data.store import VolStore

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "intraday_spy_0dte.json")
INSTANT = datetime(2026, 7, 10, 16, 30)  # 12:30 ET
SUBDAY_T_DAYS = 3.5 / 24.0  # 12:30 -> 16:00 ET settle


@pytest.fixture(scope="module")
def stored_snapshot(tmp_path_factory):
    """The fixture pushed through the REAL capture persistence path."""
    db = str(tmp_path_factory.mktemp("db") / "intraday.sqlite")
    with open(FIXTURE, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert _persist_db(db, "SPY", doc) == 1
    with VolStore(db) as vs:
        snap = vs.snapshot_at("SPY", INSTANT)
    assert snap is not None and snap.timestamp == INSTANT
    assert snap.settlement, "settlement map must survive the round-trip"
    return snap


def test_0dte_node_prices_subday_and_all_nodes_calibrate(stored_snapshot):
    failures, lines, worst = validate_snapshot(stored_snapshot, "SPY")
    assert failures == 0, "\n".join(lines)
    assert worst is not None and math.isfinite(worst)
    same_day = next(line for line in lines if line.strip().startswith("2026-07-10:"))
    t_days = float(re.search(r"t=\s*([0-9.]+)d", same_day).group(1))
    assert abs(t_days - SUBDAY_T_DAYS) < 1e-3  # sub-day, not the legacy 0.0
    assert 0.0 < t_days < 1.0


def test_same_day_discount_clamped_on_real_chain(stored_snapshot):
    f = implied_forward(stored_snapshot, date(2026, 7, 10), INSTANT.date())
    assert f is not None
    t = SUBDAY_T_DAYS / 365.0
    assert f.discount <= math.exp(-RATE_MIN * t) + 1e-12
    # The raw regression on this chain reads D ~ 1.0005 (~ -125%/yr); the
    # clamp must have actually engaged, not merely been inside the band.
    assert f.discount < 1.0004
    assert abs(f.forward / stored_snapshot.spot - 1.0) < 5e-3


def test_deterministic_replay_bitwise(stored_snapshot):
    """R2 exit gate: replaying the SAME captured chain in two fresh states
    (intraday clock ON) reproduces the same-day node's fitted parameter
    vector BITWISE — no wall-clock, no ordering, no cache leakage."""
    import numpy as np

    from volfit.api import service
    from volfit.api.state import AppState
    from volfit.replay_report import _StoredChains

    def params_once() -> np.ndarray:
        state = AppState(INSTANT.date(),
                         provider=_StoredChains({"SPY": stored_snapshot}))
        state.set_expiries("SPY", sorted(stored_snapshot.expiries()))
        state.set_options(state.options().model_copy(update={"intradayClock": True}))
        rec = service.calibrate_node(state, "SPY", "2026-07-10", "mid")
        return np.asarray(rec.result.params.to_vector(), dtype=float)

    first, second = params_once(), params_once()
    assert np.array_equal(first, second)  # bitwise, not approx
