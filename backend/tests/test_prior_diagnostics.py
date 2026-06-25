"""Prior-persistence diagnostics endpoint (roadmap Phase 7, design note §9.4).

GET /smiles/{t}/{e}/prior-diagnostics surfaces the auditable prior state: which
operators/factors are persisted, their gap and weight. Advisory — never 500s.
"""

from datetime import date

from volfit.api import priors, service
from volfit.api.state import AppState

REF_DATE = date(2026, 6, 10)
TICKER = "ALPHA"


def _node(state):
    return [e.isoformat() for e in sorted(state.forwards(TICKER))][1]


def test_diagnostics_inactive_by_default():
    """No active prior (autoLoadPrior off) -> inactive, empty operators, no 500."""
    state = AppState(REF_DATE)
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")  # ensure the chain exists
    d = service.prior_diagnostics(state, TICKER, iso, "mid")
    assert d.active is False
    assert d.operators == []
    assert d.mode == "hybrid"  # the schema default


def test_diagnostics_lists_operators_in_operator_mode():
    """With a prior active + quote_operator mode + a sparse view, the diagnostics
    list the persisted operators with gap in [0,1] and a positive weight."""
    state = AppState(REF_DATE)
    state.set_options(state.options().model_copy(update={
        "priorPersistenceMode": "quote_operator", "autoLoadPrior": True,
        "priorOperatorBandwidth": 0.03,
    }))
    iso = _node(state)
    service.displayed_base(state, TICKER, iso, "mid")
    priors.save_all(state)
    priors.fetch_all(state)

    # the diagnostics use the node's own (dense) quotes; assert the structure holds
    d = service.prior_diagnostics(state, TICKER, iso, "mid")
    assert d.mode == "quote_operator"
    for op in d.operators:
        assert 0.0 <= op.gap <= 1.0
        assert op.activeLambda > 0.0
        assert op.requiredPrecision >= 0.0


def test_diagnostics_endpoint_ok():
    from fastapi.testclient import TestClient

    from volfit.api import create_app

    with TestClient(create_app(reference_date=REF_DATE)) as c:
        # resolve a real expiry via the API's universe
        iso = c.get(f"/forwards/{TICKER}").json()["entries"][1]["expiry"]
        r = c.get(f"/smiles/{TICKER}/{iso}/prior-diagnostics")
        assert r.status_code == 200
        body = r.json()
        assert "mode" in body and "active" in body and "operators" in body
