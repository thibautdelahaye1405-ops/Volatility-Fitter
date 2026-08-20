"""V3.5 item 9 — stage-split Calibrate verbs: /calibrate/parametric + /calibrate/lv.

Locks the new contracts WITHOUT touching the combined /calibrate semantics
(test_api_workflow / test_calibration_workflow / test_gated_workflow keep those):

  * parametric-only leaves the LV (affine) pointer stale and ``lvStaleTickers``
    counts it; LV-only clears it and leaves the parametric nodes stale;
  * LV-only completes both WARM (parametric fits present) and COLD (no
    parametric calibration at all — the flat-seed path);
  * one job at a time GLOBALLY: a running job makes all three verbs a no-op;
  * the combined verb composes EXACTLY the split stage builders (same groups,
    same labels/phases, ascending-T item order inside each ticker group).
"""

import time
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


@pytest.fixture()
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


def _off_auto(client) -> None:
    opts = client.get("/settings/options").json()
    opts["autoCalibrate"] = False
    client.put("/settings/options", json=opts)


def _iso(client) -> str:
    return client.get("/universe").json()["expiries"][TICKER][1]["expiry"]


def _drain(client, tries: int = 400) -> None:
    for _ in range(tries):
        if not client.get("/calibration/status").json()["running"]:
            return
        time.sleep(0.1)
    raise AssertionError("background calibration job did not drain")


def test_parametric_only_leaves_lv_stale_and_badged(client):
    """/calibrate/parametric refits the lit nodes but never touches the LV
    pointer: the affine surface stays STALE and lvStaleTickers keeps counting it."""
    _off_auto(client)
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # bootstrap the parametric node
    client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"})  # bootstrap LV

    client.post("/fetch/options", json={"tickers": [TICKER]})  # both go stale
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is True
    assert client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()["stale"] is True
    st = client.get("/calibration/status").json()
    assert st["lvStaleTickers"] == 1  # only ALPHA's LV surface was ever calibrated

    st = client.post("/calibrate/parametric").json()
    assert st["running"] is True or st["done"] == st["total"]  # job accepted
    _drain(client)
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is False
    # The LV surface was NOT rebuilt: still stale, still badged.
    assert client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()["stale"] is True
    st = client.get("/calibration/status").json()
    assert st["lvStaleTickers"] == 1
    # No LV items ran: the job total is EXACTLY the parametric stage's item
    # count (under the default symmetric solver that is one item per lit node
    # plus one calendar-repair item per ticker — never the LV surfaces).
    from volfit.api import workflow_stages

    n_parametric = sum(
        len(items)
        for _, items in workflow_stages.parametric_stage(client.app.state.volfit, "mid")
    )
    assert st["total"] == n_parametric


def test_lv_only_warm_clears_lv_and_leaves_parametric_stale(client):
    """/calibrate/lv (WARM: parametric fits exist) rebuilds only the affine
    surfaces: LV pointer current again, parametric nodes untouched (stale)."""
    _off_auto(client)
    iso = _iso(client)
    client.get(f"/smiles/{TICKER}/{iso}")  # warm parametric fit
    client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"})  # bootstrap LV

    client.post("/fetch/options", json={"tickers": [TICKER]})  # both go stale
    client.post("/calibrate/lv")
    _drain(client)
    assert client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()["stale"] is False
    assert client.get("/calibration/status").json()["lvStaleTickers"] == 0
    # Parametric nodes were NOT refit by the LV-only verb.
    assert client.get(f"/smiles/{TICKER}/{iso}").json()["stale"] is True


def test_lv_only_cold_fits_without_any_parametric_calibration():
    """COLD LV-only (gated app, nothing ever calibrated): /calibrate/lv
    auto-fetches the chains and fits every ticker's LV surface from the FLAT
    seed (fewer than two warm parametric slices -> _parametric_seed falls back;
    same converged optimum by the theta_ref decoupling). The parametric nodes
    stay unfitted — no hidden parametric stage ran."""
    from volfit.api.affine_fit import last_affine_diagnostics

    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        iso = _iso(client)
        client.post("/calibrate/lv")
        _drain(client)
        lv = client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"}).json()
        assert lv["hasFit"] is True and lv["stale"] is False
        assert len(lv["smiles"]) >= 2 and len(lv["localVol"]) > 0
        # Flat-seed path actually taken (no previous surface, no parametric fits).
        diag = last_affine_diagnostics(client.app.state.volfit, TICKER)
        assert diag is not None and diag.seed_source == "flat"
        # No parametric fit happened anywhere in the LV-only job.
        smile = client.get(f"/smiles/{TICKER}/{iso}").json()
        assert smile["hasFit"] is False and smile["model"] == []


def test_one_job_at_a_time_across_all_three_verbs(client):
    """The global one-job contract: while ANY background job runs, all three
    Calibrate verbs are no-ops (workflow layer returns False; the endpoints
    return the running status without enqueueing new items)."""
    from volfit.api import workflow

    state = client.app.state.volfit
    hold = [("hold", "Parametric", lambda: time.sleep(1.0))]
    assert state.calibration_jobs.start_stages([[("g", hold)]])
    try:
        assert workflow.calibrate_all(state) is False
        assert workflow.calibrate_parametric_all(state) is False
        assert workflow.calibrate_lv_all(state) is False
        for path in ("/calibrate", "/calibrate/parametric", "/calibrate/lv"):
            st = client.post(path).json()
            assert st["running"] is True
            assert st["total"] == 1  # the sleeper's single item; nothing enqueued
    finally:
        state.calibration_jobs.join(timeout=30)
    _drain(client)


def test_combined_calibrate_composes_the_split_builders(monkeypatch):
    """Byte-identity of the composition: calibrate_all's stages are EXACTLY
    parametric_stage then (localVolEnabled) lv_stage — same group names, same
    item labels and phases, ascending-T order inside every parametric group."""
    from volfit.api import workflow, workflow_stages
    from volfit.api.state import AppState

    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={"localVolEnabled": True}))
    captured: dict = {}
    monkeypatch.setattr(
        state.calibration_jobs, "start_stages",
        lambda stages, workers=1: (captured.__setitem__("stages", stages) or True),
    )
    assert workflow.calibrate_all(state, "mid")

    def skeleton(groups):
        return [(name, [(label, phase) for label, phase, _ in items]) for name, items in groups]

    got = [skeleton(groups) for groups in captured["stages"]]
    want = [
        skeleton(workflow_stages.parametric_stage(state, "mid")),
        skeleton(workflow_stages.lv_stage(state, "mid")),
    ]
    assert got == want
    # Ascending-T item order inside each parametric group (warm-start/calendar
    # chains consume lit_nodes' nearest-first order; ISO strings sort by T).
    for _name, items in got[0]:
        isos = [label.split(" ", 1)[1] for label, _phase in items if " calendar repair" not in label]
        assert isos == sorted(isos)


def test_lv_stale_tickers_zero_when_localvol_gated_off(client):
    """lvStaleTickers respects the localVolEnabled gate (badge hidden with the
    workspace): a genuinely stale LV surface reports 0 while gated off."""
    _off_auto(client)
    client.post(f"/fit/affine/{TICKER}", json={"fitMode": "mid"})  # bootstrap LV
    client.post("/fetch/options", json={"tickers": [TICKER]})  # LV goes stale
    assert client.get("/calibration/status").json()["lvStaleTickers"] == 1

    opts = client.get("/settings/options").json()
    opts["localVolEnabled"] = False
    client.put("/settings/options", json=opts)
    assert client.get("/calibration/status").json()["lvStaleTickers"] == 0
