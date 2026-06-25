"""Operator-prior -> Local-Vol synthetic quotes (roadmap Phase 4).

The LV adapter turns the under-observed quote operators into synthetic prior-vol
leg quotes + a var-swap quote (the parametric models get the exact signed
residual; the PDE-based LV surface gets these). Pure builder — tested directly;
Phase 5 wires it into the live affine fit.
"""

import numpy as np

from volfit.api.prior_lv import build_operator_lv_quotes
from volfit.api.schemas import OptionsSettings

T = 0.5


def prior_w(k):
    k = np.asarray(k, dtype=float)
    sig = 0.25 - 0.45 * k  # skewed prior
    return sig * sig * T


# tight bandwidth so the near-ATM cluster does not leak into the wing legs
OPTS = OptionsSettings(priorOperatorBandwidth=0.03)


def test_emits_leg_quotes_and_varswap_when_wings_sparse():
    k_quotes = np.array([-0.01, 0.0, 0.01])  # ATM-only quotes
    opts, vs = build_operator_lv_quotes(prior_w, T, T, k_quotes, None, OPTS)
    # RR25 + BF25 active -> their legs (ATM strike + both wings) become quotes
    assert len(opts) == 3
    xs = sorted(q.x for q in opts)
    assert xs[0] < 1.0 < xs[-1]  # a put wing, ATM (~1), a call wing
    assert any(abs(q.x - 1.0) < 1e-6 for q in opts)  # ATM leg (from BF)
    for q in opts:
        assert q.t == T and q.price > 0.0 and q.tol > 0.0
    # the var-swap operator is under-covered too -> one var-swap quote
    assert len(vs) == 1
    assert vs[0].t == T and vs[0].total_var > 0.0 and vs[0].tol > 0.0


def test_full_coverage_emits_nothing():
    # dense quotes spanning ~2.5 ATM-std (past the var-swap probe wings) -> every
    # operator AND the var-swap level are well observed, so no prior leaks in
    k_quotes = np.linspace(-0.45, 0.45, 61)
    opts, vs = build_operator_lv_quotes(prior_w, T, T, k_quotes, None, OPTS)
    assert opts == [] and vs == []


def test_no_quotes_when_node_degenerate():
    assert build_operator_lv_quotes(prior_w, T, 0.0, np.array([0.0]), None, OPTS) == ([], [])
    assert build_operator_lv_quotes(prior_w, T, T, np.array([]), None, OPTS) == ([], [])


def test_higher_strength_tightens_tolerances():
    """A bigger operator budget -> tighter (smaller) tolerances on the leg quotes."""
    k_quotes = np.array([-0.01, 0.0, 0.01])
    weak, _ = build_operator_lv_quotes(
        prior_w, T, T, k_quotes, None, OPTS.model_copy(update={"priorOperatorStrengthPct": 10.0})
    )
    strong, _ = build_operator_lv_quotes(
        prior_w, T, T, k_quotes, None, OPTS.model_copy(update={"priorOperatorStrengthPct": 200.0})
    )
    # match legs by strike, compare tolerances
    weak_by_x = {round(q.x, 6): q.tol for q in weak}
    for q in strong:
        assert q.tol < weak_by_x[round(q.x, 6)]
