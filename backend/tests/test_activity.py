"""Engine-activity reporter (volfit.api.activity) + its surfacing on the status.

The bottom status bar narrates what the compute engine is doing; this checks the
reporter's stack semantics (most-recent-wins, restore-on-pop, monotonic seq) and
that a fetch / calibration narration shows up on GET /calibration/status while it
runs and clears to idle afterwards.
"""

from __future__ import annotations

import threading
from datetime import date

from volfit.api import service, workflow
from volfit.api.activity import ActivityReporter
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _iso(state: AppState) -> str:
    return sorted(state.forwards(TICKER))[1].isoformat()


# ------------------------------------------------------------- reporter unit
def test_reporter_idle_then_active_then_idle():
    r = ActivityReporter()
    assert r.snapshot().active is False
    with r.activity("fetch", "Fetching SPY quotes from Yahoo") as a:
        snap = r.snapshot()
        assert snap.active and snap.stage == "fetch"
        assert snap.message == "Fetching SPY quotes from Yahoo"
        a.detail("de-americanizing")
        assert r.snapshot().detail == "de-americanizing"
    assert r.snapshot().active is False


def test_reporter_stack_restores_outer_on_pop():
    r = ActivityReporter()
    with r.activity("fetch", "outer"):
        with r.activity("calibrate", "inner"):
            assert r.snapshot().message == "inner"  # most-recent wins
        assert r.snapshot().message == "outer"  # inner popped -> outer resumes
    assert r.snapshot().active is False


def test_reporter_seq_is_monotonic():
    r = ActivityReporter()
    seqs = [r.snapshot().seq]
    fid = r.push("calibrate", "x")
    seqs.append(r.snapshot().seq)
    r._update(fid, None, "step", None, None)
    seqs.append(r.snapshot().seq)
    r.pop(fid)
    seqs.append(r.snapshot().seq)
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_reporter_thread_safe_push_pop():
    r = ActivityReporter()

    def worker() -> None:
        for _ in range(200):
            fid = r.push("calibrate", "n")
            r.pop(fid)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert r.snapshot().active is False  # every frame popped


# ----------------------------------------------------- surfaced on the status
def test_status_carries_idle_activity_by_default():
    state = AppState(REF_DATE)
    act = workflow.status(state, "mid").activity
    assert act.active is False and act.seq == 0


def test_calibrate_narrates_then_clears():
    state = AppState(REF_DATE)
    iso = _iso(state)
    # While a calibration runs we should see a "calibrate" activity; assert the
    # narration is pushed by calibrating with the reporter watched mid-flight.
    seen: list[str] = []
    orig_push = state.activity.push

    def spy(stage, message, detail="", done=0, total=0):  # type: ignore[no-untyped-def]
        seen.append(f"{stage}:{message}")
        return orig_push(stage, message, detail, done, total)

    state.activity.push = spy  # type: ignore[method-assign]
    service.calibrate_node(state, TICKER, iso, "mid")
    assert any(s.startswith("calibrate:") for s in seen)
    # Reporter returns to idle after the synchronous calibration completes.
    assert workflow.status(state, "mid").activity.active is False


def test_fetch_options_narrates_source(monkeypatch):
    state = AppState(REF_DATE)
    seen: list[str] = []
    orig_push = state.activity.push

    def spy(stage, message, detail="", done=0, total=0):  # type: ignore[no-untyped-def]
        seen.append(message)
        return orig_push(stage, message, detail, done, total)

    state.activity.push = spy  # type: ignore[method-assign]
    workflow.fetch_options(state, [TICKER], "mid")
    assert any("quotes from" in m and TICKER in m for m in seen)
