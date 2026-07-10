"""Certification pack v0 (backtest.certification) — registry + report locks.

Contracts: (1) the registry is well-formed — unique keys, valid dimensions,
every lock's test FILE exists (a renamed test must update its cases);
(2) the HTML report renders every registered case with its verdict badge;
(3) a single case's runner round-trips a real pytest verdict.
"""

from __future__ import annotations

import os

from backtest import certification as cert

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_registry_is_well_formed():
    keys = [c.key for c in cert.CASES]
    assert len(keys) == len(set(keys))  # unique keys
    assert len(cert.CASES) >= 15  # every named historical bug stays registered
    for c in cert.CASES:
        assert c.dimension in cert.DIMENSIONS
        assert c.story and c.origin and c.locks
        for lock in c.locks:
            path = lock.split("::")[0]
            assert os.path.exists(os.path.join(BACKEND, path)), (c.key, lock)
    # all three dimensions populated (the matrix, not a flat list)
    assert {c.dimension for c in cert.CASES} == set(cert.DIMENSIONS)


def test_report_renders_all_cases_and_badges(tmp_path, monkeypatch):
    monkeypatch.setattr(cert, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(cert, "RESULTS_JSON", str(tmp_path / "cert_results.json"))
    results = {
        "generatedAt": "2026-07-10T00:00:00+00:00",
        "appVersion": "test",
        "cases": [
            {"key": cert.CASES[0].key, "passed": True, "summary": "ok"},
            {"key": cert.CASES[3].key, "passed": False, "summary": "1 failed"},
        ],
    }
    html = cert.build_report_html(results)
    for c in cert.CASES:
        assert c.title in html
    assert html.count("PASS") >= 1 and html.count("FAIL") >= 1
    assert html.count("not run") == len(cert.CASES) - 2

    html_path, json_path = cert.write_report()
    assert os.path.exists(html_path) and os.path.exists(json_path)


def test_runner_round_trips_one_real_case(tmp_path, monkeypatch):
    """End-to-end on the cheapest registered lock: real pytest, real verdict."""
    monkeypatch.setattr(cert, "RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(cert, "RESULTS_JSON", str(tmp_path / "cert_results.json"))
    payload = cert.run(only="duplicate_strikes")
    (case,) = payload["cases"]
    assert case["key"] == "duplicate_strikes"
    assert case["passed"] is True
    assert "passed" in case["summary"]
