"""GET /export/* — publish workflow (surfaces JSON/CSV + HTML quality report).

Locks: (1) exports read cached fits only and never calibrate; (2) the JSON
artifact carries the reproducibility manifest + full-fidelity nodes (curve,
LQD params, LV grid, quality); (3) the CSV flattens exactly the JSON curves;
(4) the HTML report renders the quality screen with the manifest stamp.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from volfit.api import export, service, workflow
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _isos(state: AppState, ticker: str = TICKER) -> list[str]:
    return [e.isoformat() for e in sorted(state.forwards(ticker))]


def test_export_is_fitted_nodes_only_and_never_fits():
    state = AppState(REF_DATE)
    for t in state.active_tickers():
        state.ensure_chain(t)
    empty = export.build_surface_export(state)
    assert empty.tickers == [] and empty.manifest.fittedNodes == 0
    assert empty.manifest.litNodes > 0  # universe visible, nothing published
    for t, iso in workflow.lit_nodes(state):
        assert state.get_calibrated_ptr(t, iso, "mid") is None  # no fit happened

    isos = _isos(state)
    for iso in isos[:2]:
        service.calibrate_node(state, TICKER, iso, "mid")
    out = export.build_surface_export(state)
    assert [t.ticker for t in out.tickers] == [TICKER]
    assert len(out.tickers[0].nodes) == 2  # only the calibrated expiries
    assert out.manifest.fittedNodes == 2


def test_export_node_payload_full_fidelity():
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
    workflow.calibrate_ticker(state, TICKER)

    out = export.build_surface_export(state, tickers=[TICKER])
    tk = out.tickers[0]
    assert tk.spot > 0.0 and tk.snapshotTimestamp != ""
    node = tk.nodes[0]
    assert node.forward > 0.0 and 0.0 < node.discount <= 1.0
    assert node.model == "lqd" and node.quality.ready
    assert len(node.lqdParams["a"]) >= 3  # the Legendre coefficients
    assert len(node.curve) > 100  # the display-grid sampling
    p = node.curve[len(node.curve) // 2]
    assert p.strike > 0.0 and abs(p.w - p.iv * p.iv * node.tau) < 1e-12
    assert node.varSwapVol > 0.0
    # LV surface rides along when calibrated.
    assert tk.localVol is not None
    assert len(tk.localVol.vol) == len(tk.localVol.tNodes)
    # Manifest reproducibility stamps.
    m = out.manifest
    assert m.source != "" and m.fitMode == "mid" and m.appVersion != ""
    assert m.fitSettings["model"] == "lqd"
    assert m.tickers == [TICKER]


def test_csv_flattens_the_json_curves():
    state = AppState(REF_DATE)
    iso = _isos(state)[0]
    service.calibrate_node(state, TICKER, iso, "mid")
    out = export.build_surface_export(state, tickers=[TICKER])
    text = export.surface_export_csv(out)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == sum(len(n.curve) for t in out.tickers for n in t.nodes)
    first = rows[0]
    assert first["ticker"] == TICKER and first["expiry"] == iso
    assert float(first["iv"]) > 0.0 and float(first["strike"]) > 0.0
    assert first["ready"] in ("0", "1")


def test_export_routes_over_http():
    from fastapi.testclient import TestClient

    from volfit.api.app import create_app

    client = TestClient(create_app(reference_date=REF_DATE))
    client.post("/calibrate")
    client.app.state.volfit.calibration_jobs.join(timeout=120)

    r = client.get("/export/surfaces")
    assert r.status_code == 200
    assert "volfit_surfaces_" in r.headers["content-disposition"]
    body = r.json()
    assert body["manifest"]["fittedNodes"] > 0
    assert len(body["tickers"]) == len(body["manifest"]["tickers"])

    r_csv = client.get("/export/surfaces", params={"format": "csv", "tickers": TICKER})
    assert r_csv.status_code == 200
    assert r_csv.headers["content-type"].startswith("text/csv")
    header = r_csv.text.splitlines()[0]
    assert header.startswith("ticker,expiry,")
    assert all(line.split(",")[0] == TICKER for line in r_csv.text.splitlines()[1:] if line)

    r_html = client.get("/export/report")
    assert r_html.status_code == 200
    assert r_html.headers["content-type"].startswith("text/html")
    assert "surface quality report" in r_html.text
    assert TICKER in r_html.text and "Publish rule" in r_html.text


# ------------------------------------------------- hard publish gate (R2)
def test_publish_blocked_on_calendar_inconsistency(monkeypatch):
    """The exit gate: a publish set with an unresolved calendar inconsistency
    FAILS (PublishBlockedError naming the node) before any manifest persists;
    require_clean=False still exports the draft. The calendar DETECTOR has its
    own locks (calib/calendar + quality); poisoned here to isolate the gate."""
    import pytest

    state = AppState(REF_DATE)
    isos = _isos(state)
    for iso in isos[:2]:
        service.calibrate_node(state, TICKER, iso, "mid")

    real = export.build_quality_report

    def poisoned(state_, mode):
        report = real(state_, mode)
        for row in report.nodes:
            if row.hasFit and row.expiry == isos[1]:
                row.calendarOk = False
                row.calendarViolation = 0.005
        return report

    monkeypatch.setattr(export, "build_quality_report", poisoned)
    with pytest.raises(export.PublishBlockedError, match="calendar inconsistency"):
        export.build_surface_export(state, tickers=[TICKER])
    draft = export.build_surface_export(state, tickers=[TICKER], require_clean=False)
    assert len(draft.tickers[0].nodes) == 2  # the explicit draft escape hatch


def test_node_blockers_name_intrinsic_and_core_conflicts():
    """The other two blocker classes on a real exported node: an unpriceable
    curve region (w <= 0 = below intrinsic) and a core calendar conflict the
    wing projection must not repair (wingsClean=False)."""
    state = AppState(REF_DATE)
    iso = _isos(state)[0]
    service.calibrate_node(state, TICKER, iso, "mid")
    out = export.build_surface_export(state, tickers=[TICKER])
    node = out.tickers[0].nodes[0]
    row = next(r for r in export.build_quality_report(state, "mid").nodes if r.hasFit)
    assert export._node_blockers(TICKER, row, node) == []  # clean fit: no blockers
    node.curve[0].w = -1.0
    node.wingsClean = False
    blockers = export._node_blockers(TICKER, row, node)
    assert any("intrinsic" in b for b in blockers)
    assert any("core calendar conflict" in b for b in blockers)
