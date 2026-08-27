"""Quality "as-of mismatch" issue + publish gate (workbench follow-on,
2026-08-27; OptionsSettings.asOfMismatchGate).

Locks (gated workflow, synthetic providers of tests/test_universe_asof.py):
  * gate OFF (default) — a node served off the requested session is ADVISORY:
    the row carries asOfExact=False / effectiveAsOf, stays ready and exports;
  * gate ON — the same node is not ready with the issue "as-of mismatch:
    chain stamped <ISO> vs the requested <day>", the ticker's arbFlags do not
    count it (a data issue), and the publish export blocks naming "as-of"
    (a draft still exports with require_clean=False);
  * exact nodes are unaffected either way;
  * flipping the gate never bumps the options version (display/report policy).
"""

from __future__ import annotations

from datetime import date, datetime, time

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app, export, service
from volfit.api.schemas import OptionsSettings
from volfit.api.state import AppState
from volfit.api.export_blockers import PublishBlockedError

from tests.test_universe_asof import PREV, REF, _CloseProvider, _IgnoringProvider

TICKER = "ALPHA"
TODAY_STAMP = datetime.combine(REF, time(16, 0)).isoformat()  # the synthetic stamp
PREV_STAMP = datetime.combine(PREV, time(16, 0)).isoformat()


def _client(provider):
    return TestClient(
        create_app(
            reference_date=REF, gated=True, providers={"synthetic": provider},
            active_source="synthetic",
        )
    )


def _fetch_prev_close_and_fit(c: TestClient, n: int = 2) -> AppState:
    """Select the previous close, fetch, calibrate the first ``n`` expiries."""
    assert c.post("/asof", json={"mode": "prev_close"}).status_code == 200
    # Resolve the ladder first (the UI always loads /universe before a fetch;
    # an unresolved ladder yields an empty, uncached chain).
    assert c.get("/universe").status_code == 200
    assert c.post("/fetch/options", json={}).status_code == 200
    state = c.app.state.volfit
    for expiry in sorted(state.forwards(TICKER))[:n]:
        service.calibrate_node(state, TICKER, expiry.isoformat(), "mid")
    return state


def _rows(c: TestClient) -> list[dict]:
    report = c.get("/quality").json()
    return [r for r in report["nodes"] if r["ticker"] == TICKER and r["hasFit"]]


def test_gate_off_inexact_node_is_advisory_and_exports():
    with _client(_IgnoringProvider(reference_date=REF, tickers=(TICKER,))) as c:
        state = _fetch_prev_close_and_fit(c)
        assert not state.options().asOfMismatchGate  # the default
        rows = _rows(c)
        assert rows
        for r in rows:
            assert r["effectiveAsOf"] == TODAY_STAMP  # today's chain served
            assert r["asOfExact"] is False and r["asOfGated"] is False
            assert r["ready"] is True
            assert not any("as-of" in s for s in r["issues"])
        out = export.build_surface_export(state, tickers=[TICKER])  # no raise
        assert len(out.tickers[0].nodes) == len(rows)


def test_gate_on_inexact_node_not_ready_and_publish_blocks():
    with _client(_IgnoringProvider(reference_date=REF, tickers=(TICKER,))) as c:
        state = _fetch_prev_close_and_fit(c)
        assert c.put("/settings/options", json={"asOfMismatchGate": True}).status_code == 200
        report = c.get("/quality").json()
        rows = [r for r in report["nodes"] if r["ticker"] == TICKER and r["hasFit"]]
        assert rows
        expected = f"as-of mismatch: chain stamped {TODAY_STAMP} vs the requested {PREV.isoformat()}"
        for r in rows:
            assert r["asOfExact"] is False and r["asOfGated"] is True
            assert r["ready"] is False
            assert expected in r["issues"]
        # A data issue, not an arb one: the ticker rollup's arbFlags stay 0.
        ticker_row = next(t for t in report["tickers"] if t["ticker"] == TICKER)
        assert ticker_row["arbFlags"] == 0 and ticker_row["ready"] == 0
        assert report["summary"]["readyNodes"] == 0

        with pytest.raises(PublishBlockedError, match="as-of"):
            export.build_surface_export(state, tickers=[TICKER])
        draft = export.build_surface_export(state, tickers=[TICKER], require_clean=False)
        assert len(draft.tickers[0].nodes) == len(rows)


@pytest.mark.parametrize("gate", [False, True])
def test_exact_nodes_unaffected_either_way(gate):
    with _client(_CloseProvider(reference_date=REF, tickers=(TICKER,))) as c:
        state = _fetch_prev_close_and_fit(c)
        assert c.put("/settings/options", json={"asOfMismatchGate": gate}).status_code == 200
        rows = _rows(c)
        assert rows
        for r in rows:
            assert r["effectiveAsOf"] == PREV_STAMP  # the honored close
            assert r["asOfExact"] is True and r["asOfGated"] is gate
            assert r["ready"] is True
            assert not any("as-of" in s for s in r["issues"])
        out = export.build_surface_export(state, tickers=[TICKER])
        assert len(out.tickers[0].nodes) == len(rows)


def test_live_nodes_are_exact_under_the_gate():
    with TestClient(create_app(reference_date=REF, gated=True)) as c:
        assert c.put("/settings/options", json={"asOfMismatchGate": True}).status_code == 200
        assert c.post("/fetch/options", json={}).status_code == 200
        state = c.app.state.volfit
        iso = sorted(state.forwards(TICKER))[0].isoformat()
        service.calibrate_node(state, TICKER, iso, "mid")
        row = next(r for r in _rows(c) if r["expiry"] == iso)
        assert row["asOfExact"] is True and row["asOfGated"] is True and row["ready"] is True


def test_gate_flip_does_not_bump_the_options_version():
    """Display/report policy: warm fit caches survive the toggle (the
    test_only_calendar_weight_bumps_version idiom)."""
    state = AppState(reference_date=REF)
    v0 = state.options_version
    state.set_options(state.options().model_copy(update={"asOfMismatchGate": True}))
    assert state.options().asOfMismatchGate and state.options_version == v0
    state.set_options(OptionsSettings(asOfMismatchGate=False))
    assert state.options_version == v0
