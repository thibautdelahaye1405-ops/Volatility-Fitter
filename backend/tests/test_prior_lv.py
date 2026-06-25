"""Operator-prior -> Local-Vol signed-basket targets (roadmap Phase 4, Option A).

The LV adapter turns the under-observed quote operators into signed BasketQuote
targets (preserving the RR/BF coupling) + a var-swap quote. Pure builder — tested
directly; the affine engine consumes BasketQuote (test_affine_basket); Phase 5
wires it into the live fit.
"""

import numpy as np

from volfit.api.prior_lv import build_operator_lv_targets
from volfit.api.schemas import OptionsSettings
from volfit.models.localvol import BasketQuote, VarSwapQuote

T = 0.5


def prior_w(k):
    k = np.asarray(k, dtype=float)
    sig = 0.25 - 0.45 * k  # skewed prior
    return sig * sig * T


# tight bandwidth so the near-ATM cluster does not leak into the wing legs
OPTS = OptionsSettings(priorOperatorBandwidth=0.03)


def test_emits_baskets_and_varswap_when_wings_sparse():
    k_quotes = np.array([-0.01, 0.0, 0.01])  # ATM-only quotes
    baskets, vs = build_operator_lv_targets(prior_w, T, T, k_quotes, None, OPTS)
    # RR25 + BF25 are under-observed -> one BASKET each (coupling preserved),
    # not independent per-leg quotes
    assert baskets and all(isinstance(b, BasketQuote) for b in baskets)
    n_legs = {len(b.xs) for b in baskets}
    assert 2 in n_legs  # RR25 is a 2-leg basket (call vs put)
    assert 3 in n_legs  # BF25 is a 3-leg basket (both wings vs ATM)
    for b in baskets:
        assert b.t == T and b.tol > 0.0 and len(b.xs) == len(b.weights)
    # the var-swap operator is under-covered too -> one var-swap quote
    assert len(vs) == 1 and isinstance(vs[0], VarSwapQuote)
    assert vs[0].t == T and vs[0].total_var > 0.0 and vs[0].tol > 0.0


def test_rr_basket_is_a_signed_difference():
    """The RR basket must be a DIFFERENCE (one + and one - leg) — that is what keeps
    it a skew constraint that doesn't pin the absolute level."""
    k_quotes = np.array([-0.01, 0.0, 0.01])
    baskets, _ = build_operator_lv_targets(
        prior_w, T, T, k_quotes, None,
        OPTS.model_copy(update={"priorOperatorSet": ["RR25"]}),
    )
    assert len(baskets) == 1
    rr = baskets[0]
    assert len(rr.xs) == 2
    signs = np.sign(rr.weights)
    assert set(signs) == {1.0, -1.0}  # one positive, one negative leg


def test_full_coverage_emits_nothing():
    # dense quotes spanning ~2.5 ATM-std (past the var-swap probe wings) -> every
    # operator AND the var-swap level are well observed, so no prior leaks in
    k_quotes = np.linspace(-0.45, 0.45, 61)
    baskets, vs = build_operator_lv_targets(prior_w, T, T, k_quotes, None, OPTS)
    assert baskets == [] and vs == []


def test_no_targets_when_node_degenerate():
    assert build_operator_lv_targets(prior_w, T, 0.0, np.array([0.0]), None, OPTS) == ([], [])
    assert build_operator_lv_targets(prior_w, T, T, np.array([]), None, OPTS) == ([], [])


def test_higher_strength_tightens_basket_tol():
    """A bigger operator budget -> tighter (smaller) tol on the basket residuals."""
    k_quotes = np.array([-0.01, 0.0, 0.01])
    weak, _ = build_operator_lv_targets(
        prior_w, T, T, k_quotes, None, OPTS.model_copy(update={"priorOperatorStrengthPct": 10.0})
    )
    strong, _ = build_operator_lv_targets(
        prior_w, T, T, k_quotes, None, OPTS.model_copy(update={"priorOperatorStrengthPct": 200.0})
    )
    weak_by_n = {len(b.xs): b.tol for b in weak}
    for b in strong:
        assert b.tol < weak_by_n[len(b.xs)]
