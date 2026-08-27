"""Served filter-replay artifacts (V3.9 rider) — the test_graph_backtest
artifact-route pattern over a monkeypatched FILTER_REPLAY_DIR.

Locks: 404s (+ the run hint) on a missing/empty directory and an empty
listing; with two synthetic parts (built from ``step_doc`` of real
FilterStep records, so the shape is the live wire shape) the listing is
newest-first by replayed day, the ticker filter works case-insensitively,
unreadable files are skipped, the part endpoint returns the document
verbatim and the artifact endpoint serves the newest html.
"""

from __future__ import annotations

import json
import os
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

import volfit.api.routers.filter_replay as replay_router
from volfit.api import create_app
from volfit.api.filter_history import FilterStep, step_doc

REF_DATE = date(2026, 6, 10)


def _step(i: int, seed: bool = False) -> FilterStep:
    v = (0.2 + 0.001 * i, -0.3, 0.1)
    return FilterStep(
        ts=1_760_000_000.0 + 1800.0 * i, dt_days=0.0 if seed else 1800.0 / 86400.0,
        prediction=v, prediction_std=(0.01, 0.02, 0.05), observation=v,
        observation_std=(0.005, 0.01, 0.02), innovation=(0.001, 0.0, 0.0),
        zeta=None if seed else (0.9, 0.1, 0.0), gain=(0.8, 0.6, 0.4),
        posterior=v, posterior_std=(0.004, 0.009, 0.018),
        process_breakdown={} if seed else {"clock": (1e-6, 2e-6, 3e-6)},
        transport_distance=0.0, provenance="seed:today_fit" if seed else "update",
        reset_reason="first" if seed else None, contaminated=False,
    )


def _part(ticker: str, day: str, isos: list[str], n_steps: int = 3) -> dict:
    """The backtest.filter_replay part shape with honest wire-shape steps."""
    steps = [step_doc(_step(i, seed=(i == 0))) for i in range(n_steps)]
    return {
        "meta": {
            "ticker": ticker, "day": day, "fitMode": "mid",
            "filterMode": "overlay", "nInstants": n_steps, "appVersion": "test",
        },
        "nodes": {iso: steps for iso in isos},
    }


def _write(dir_, ticker: str, day: str, doc: dict, age_s: float = 0.0):
    path = dir_ / f"{ticker}_{day}.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    if age_s:
        past = time.time() - age_s
        os.utime(path, (past, past))
    return path


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def test_404s_and_empty_listing_without_a_replay(client, tmp_path, monkeypatch):
    monkeypatch.setattr(replay_router, "FILTER_REPLAY_DIR", tmp_path / "none")
    r = client.get("/filter/replay/artifact")
    assert r.status_code == 404 and "backtest.filter_replay" in r.json()["detail"]
    assert client.get("/filter/replay/parts").json() == {"parts": []}
    r = client.get("/filter/replay/parts/SPY/2026-06-10")
    assert r.status_code == 404 and "backtest.filter_replay" in r.json()["detail"]
    # an existing but EMPTY directory behaves the same
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(replay_router, "FILTER_REPLAY_DIR", empty)
    assert client.get("/filter/replay/artifact").status_code == 404
    assert client.get("/filter/replay/parts?ticker=SPY").json() == {"parts": []}


def test_listing_part_and_artifact_over_synthetic_parts(client, tmp_path, monkeypatch):
    out = tmp_path / "filter_replay"
    out.mkdir()
    monkeypatch.setattr(replay_router, "FILTER_REPLAY_DIR", out)
    spy = _part("SPY", "2026-06-10", ["2026-07-17", "2026-09-18"])
    qqq = _part("QQQ", "2026-06-11", ["2026-07-17"], n_steps=2)
    _write(out, "SPY", "2026-06-10", spy, age_s=120)  # older file, older day
    _write(out, "QQQ", "2026-06-11", qqq)
    (out / "broken_2026-01-01.json").write_text("{not json", encoding="utf-8")
    (out / "list_2026-01-02.json").write_text("[1, 2]", encoding="utf-8")

    # listing: newest replayed day first; the two unreadable files skipped
    rows = client.get("/filter/replay/parts").json()["parts"]
    assert [(r["ticker"], r["day"]) for r in rows] == [
        ("QQQ", "2026-06-11"), ("SPY", "2026-06-10"),
    ]
    spy_row = rows[1]
    assert spy_row["nInstants"] == 3 and spy_row["fitMode"] == "mid"
    assert spy_row["filterMode"] == "overlay"
    assert spy_row["expiries"] == ["2026-07-17", "2026-09-18"]
    assert rows[0]["mtime"] > spy_row["mtime"]

    # ticker filter (case-insensitive), unknown ticker = empty
    assert [r["ticker"] for r in client.get("/filter/replay/parts?ticker=spy").json()["parts"]] == ["SPY"]
    assert client.get("/filter/replay/parts?ticker=IWM").json() == {"parts": []}

    # the part document comes back VERBATIM (steps are the wire dicts)
    r = client.get("/filter/replay/parts/SPY/2026-06-10")
    assert r.status_code == 200 and r.json() == spy
    assert r.json()["nodes"]["2026-07-17"][0]["resetReason"] == "first"
    assert client.get("/filter/replay/parts/spy/2026-06-10").json() == spy
    assert client.get("/filter/replay/parts/SPY/2026-06-12").status_code == 404
    assert client.get("/filter/replay/parts/SPY/not-a-day").status_code == 404
    assert client.get("/filter/replay/parts/..%2Fx/2026-06-10").status_code == 404

    # the artifact: newest html by mtime
    (out / "old.html").write_text("<html>old</html>", encoding="utf-8")
    past = time.time() - 60
    os.utime(out / "old.html", (past, past))
    (out / "filter_replay.html").write_text("<html>new</html>", encoding="utf-8")
    r = client.get("/filter/replay/artifact")
    assert r.status_code == 200 and "new" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_meta_falls_back_to_the_file_stem(client, tmp_path, monkeypatch):
    """A part with a bare/missing meta block still lists from its name."""
    out = tmp_path / "fr"
    out.mkdir()
    monkeypatch.setattr(replay_router, "FILTER_REPLAY_DIR", out)
    path = _write(out, "IWM", "2026-06-09", {"nodes": {"2026-07-17": []}})
    (row,) = client.get("/filter/replay/parts").json()["parts"]
    assert row == {
        "ticker": "IWM", "day": "2026-06-09", "nInstants": 0, "fitMode": "mid",
        "filterMode": "overlay", "expiries": ["2026-07-17"],
        "mtime": pytest.approx(path.stat().st_mtime),
    }
