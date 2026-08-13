"""Tail-exponent scenario report (backtest.tail_scenarios — arc Phase 3d).

Locks the book's scenario-policy instrument: the same stack refits under a
grid of stated tail classes with comparable strip RMS (the
indistinguishability point), while the moment domain flips, far digitals
fall with lighter tails, and downstream deltas (var-swap, RR/BF) are
tabulated against the exponential baseline. The artifact adapter reads the
surfaces-export format (the standing reference fixture's schema) end-to-end.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from backtest.tail_scenarios import (
    SliceQuotes,
    artifact_stacks,
    render_html,
    run_scenarios,
)

SCEN = {"exponential": (0.0, 0.0), "gaussian": (0.5, 0.5)}


@pytest.fixture(scope="module")
def report():
    k = np.linspace(-0.30, 0.30, 13)
    w1 = 0.20**2 * 0.25 * (1.0 + 0.6 * k**2 - 0.12 * k)
    w2 = 0.21**2 * 0.60 * (1.0 + 0.5 * k**2 - 0.10 * k)
    stack = [
        SliceQuotes(expiry="2026-09-18", t=0.25, k=k, w=w1),
        SliceQuotes(expiry="2026-12-18", t=0.60, k=k, w=w2),
    ]
    return run_scenarios({"TEST": stack}, SCEN, n_order=6)


def test_scenarios_fit_comparably_and_flip_the_moment_domain(report):
    rows = report["tickers"]["TEST"]
    for name in SCEN:
        assert [r["expiry"] for r in rows[name]] == ["2026-09-18", "2026-12-18"]
        for r in rows[name]:
            assert r["rmsBp"] < 25.0  # indistinguishable on the strip
    expo, gauss = rows["exponential"][0], rows["gaussian"][0]
    # Moment domain: finite boundaries at alpha = 0, unbounded at 1/2.
    assert expo["momentPlus"] is not None and expo["momentPlus"] > 0.0
    assert gauss["momentPlus"] is None and gauss["momentMinus"] is None
    # Far digitals fall when the tail lightens; near ones barely move.
    assert gauss["digitals"]["P(X>0.5)"] < expo["digitals"]["P(X>0.5)"]
    assert gauss["digitals"]["P(X<-0.5)"] < expo["digitals"]["P(X<-0.5)"]
    # Deltas ride the non-baseline rows only.
    assert "deltas" not in expo
    assert "varSwapVolBp" in gauss["deltas"]
    assert abs(gauss["deltas"]["rmsBp"]) < 25.0


def test_html_renders(report):
    html = render_html(report)
    assert "TEST" in html and "momentPlus" in html and "P(X&gt;0.5)" in html or "P(X>0.5)" in html


def test_artifact_adapter_runs_on_the_export_format():
    """End-to-end on the surfaces-export schema (the standing reference
    fixture's format): calibrate two nodes, export with embedded inputs,
    adapt, and run a one-scenario report."""
    from volfit.api import export, service
    from volfit.api.state import AppState

    state = AppState(date(2026, 6, 10))
    isos = [e.isoformat() for e in sorted(state.forwards("ALPHA"))][:2]
    for iso in isos:
        service.calibrate_node(state, "ALPHA", iso, "mid")
    doc = export.build_surface_export(state, tickers=["ALPHA"]).model_dump(mode="json")

    stacks = artifact_stacks(doc)
    assert list(stacks) == ["ALPHA"]
    assert [s.expiry for s in stacks["ALPHA"]] == isos
    out = run_scenarios(stacks, {"exponential": (0.0, 0.0)}, n_order=6)
    rows = out["tickers"]["ALPHA"]["exponential"]
    assert len(rows) == 2 and all(r["rmsBp"] < 50.0 for r in rows)
