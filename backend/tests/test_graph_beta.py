"""Per-edge beta on the directed increment (plan Phase 6).

Beta is the move AMPLITUDE, separate from the conductance (the TRUST). beta=1
everywhere is byte-identical to the no-beta engine; raising an edge's beta amplifies
the propagated increment without touching the conductance; asymmetric betas give
asymmetric propagation; the residual stays PSD.
"""

from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.graph import build_graph, build_increment_prior, directed_residual
from volfit.graph.beta import beta_matrix, directed_residual_beta
from volfit.graph.operators import directed_residual as plain_residual
from volfit.graph.posterior import posterior_update

REF_DATE = date(2026, 6, 10)

A, B = ("A", "T"), ("B", "T")
WEIGHTS = {(A, B): 2.0, (B, A): 2.0}
KAPPA, ETA = 1.0 / 0.03**2, 2.0e4


def _graph():
    return build_graph([A, B], WEIGHTS)


def test_all_ones_beta_is_byte_identical():
    g = _graph()
    ones = beta_matrix(g)  # all-ones off-diagonal, 1 on diagonal
    np.testing.assert_array_equal(directed_residual_beta(g, ones), plain_residual(g))


def test_prior_beta_none_equals_ones():
    g = _graph()
    p_none = build_increment_prior(g, kappa=KAPPA, eta=ETA)
    p_ones = build_increment_prior(g, kappa=KAPPA, eta=ETA, beta=beta_matrix(g))
    np.testing.assert_allclose(p_none.precision, p_ones.precision, rtol=0, atol=0)


def test_directed_residual_beta_is_psd():
    g = _graph()
    bm = beta_matrix(g, {(B, A): 1.5})
    eig = np.linalg.eigvalsh(directed_residual_beta(g, bm))
    assert eig.min() > -1e-10


def _propagate(prior, g, observe, value):
    return posterior_update(
        prior,
        baseline=np.array([0.20, 0.20]),
        baseline_precision=np.array([1.0e6, 1.0e6]),
        observed=np.array([g.index[observe]]),
        observations=np.array([value]),
        observation_precision=np.array([1.0e6]),
    )


def test_higher_beta_amplifies_propagation():
    """Raising the B<-A edge beta pulls B's increment closer to beta x the source."""
    g = _graph()
    p_none = build_increment_prior(g, kappa=KAPPA, eta=ETA)
    p_beta = build_increment_prior(
        g, kappa=KAPPA, eta=ETA, beta=beta_matrix(g, {(B, A): 1.5})
    )
    inc_none = _propagate(p_none, g, A, 0.25).mean[g.index[B]] - 0.20
    inc_beta = _propagate(p_beta, g, A, 0.25).mean[g.index[B]] - 0.20
    assert inc_beta > inc_none > 0.0
    # Conductance (the trust object) is untouched by beta.
    assert np.array_equal(g.conductance, _graph().conductance)


def test_asymmetric_beta_gives_asymmetric_propagation():
    g = _graph()
    # Beta only on B<-A, not A<-B.
    p = build_increment_prior(g, kappa=KAPPA, eta=ETA, beta=beta_matrix(g, {(B, A): 1.6}))
    b_from_a = _propagate(p, g, A, 0.25).mean[g.index[B]] - 0.20  # observe A, see B
    a_from_b = _propagate(p, g, B, 0.25).mean[g.index[A]] - 0.20  # observe B, see A
    assert b_from_a > a_from_b  # the amplified direction propagates more


def test_production_cross_beta_changes_a_dark_neighbour():
    """crossBeta amplifies cross-ticker propagation in the production solve."""
    with TestClient(create_app(reference_date=REF_DATE, gated=False)) as client:
        tk = "BETA"
        iso = client.get("/universe").json()["expiries"][tk][1]["expiry"]
        client.put(f"/universe/lit/{tk}/{iso}", json={"lit": False})  # darken one node

        base = client.post("/graph/extrapolate", json={"flatAtm": True}).json()
        amp = client.post(
            "/graph/extrapolate", json={"flatAtm": True, "crossBeta": 2.5}
        ).json()
        d0 = next(n for n in base["nodes"] if n["ticker"] == tk and n["expiry"] == iso)
        d1 = next(n for n in amp["nodes"] if n["ticker"] == tk and n["expiry"] == iso)
        assert d0["shiftBp"] != pytest.approx(d1["shiftBp"], abs=1e-6)


def test_byte_identical_default_via_directed_residual_export():
    """The package re-exports both residual builders (Phase 6 API surface)."""
    g = _graph()
    np.testing.assert_array_equal(directed_residual(g), plain_residual(g))
