"""Golden tests for the fast spot-move transport engine (volfit.dynamics.transport).

Validates the closed forms of Docs/spot_move_vol_surface_note_updated.tex: the
SSR horizontal transport recovers the canonical regimes exactly, the exact
sticky-local-vol ell_T gives the ~2 kappa h ATM "double-skew" response, the
optional ATM re-anchor hits an exact linear SSR target, and the LV-grid node
rule is the log-strike barycenter.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.dynamics import Regime
from volfit.dynamics.transport import (
    TransportedSlice,
    beta_of,
    ell_T,
    is_exact_lv,
    transport_grid_logk,
    transported_w,
)


class LinVol:
    """Toy SmileModel with affine vol in k: sigma(k) = s0 + kap * k, w = tau sigma^2."""

    def __init__(self, s0: float, kap: float, tau: float) -> None:
        self.s0, self.kap, self.tau = s0, kap, tau

    def implied_w(self, k):
        k = np.asarray(k, dtype=float)
        return self.tau * (self.s0 + self.kap * k) ** 2


TAU = 0.5
H = 0.03  # ~3% forward move


def test_h_zero_is_identity_all_regimes():
    base = LinVol(0.2, -0.4, TAU)
    k = np.linspace(-0.3, 0.3, 25)
    for regime in ("sticky_moneyness", "sticky_strike", "sticky_local_vol", 1.7):
        np.testing.assert_allclose(
            transported_w(base.implied_w, k, 0.0, regime), base.implied_w(k)
        )


def test_sticky_moneyness_leaves_smile_in_moneyness_unchanged():
    """R = 0: w_1(k) = w_0(k); the smile rides with the forward."""
    base = LinVol(0.2, -0.4, TAU)
    k = np.linspace(-0.3, 0.3, 25)
    np.testing.assert_allclose(
        transported_w(base.implied_w, k, H, Regime.STICKY_MONEYNESS), base.implied_w(k)
    )


def test_sticky_strike_fixes_vol_at_fixed_strike():
    """R = 1: the vol at a fixed strike is unchanged after the move.

    A fixed strike has old moneyness k0 and new moneyness k0 - h; the transported
    vol at k0 - h must equal the anchor vol at k0.
    """
    base = LinVol(0.2, -0.4, TAU)
    k0 = np.linspace(-0.25, 0.25, 21)
    old_vol = np.sqrt(base.implied_w(k0) / TAU)
    new_w = transported_w(base.implied_w, k0 - H, H, Regime.STICKY_STRIKE)
    np.testing.assert_allclose(np.sqrt(new_w / TAU), old_vol, atol=1e-12)


def test_sticky_strike_atm_moves_with_skew():
    """At the new ATM (k=0) sticky-strike gives sigma_0(h) ~ sigma0 + kappa h."""
    base = LinVol(0.2, -0.4, TAU)
    new_atm = float(np.sqrt(transported_w(base.implied_w, 0.0, H, "sticky_strike") / TAU))
    assert new_atm == pytest.approx(0.2 + (-0.4) * H, abs=1e-12)


def test_ell_T_small_move_expansion():
    """ell_T(k, h) = k + (1 + e^{-k}) h + O(h^2); ell_T(0, h) ~ 2h."""
    k = np.array([-0.2, 0.0, 0.15])
    h = 1e-4
    approx = k + (1.0 + np.exp(-k)) * h
    np.testing.assert_allclose(ell_T(k, h), approx, atol=5e-8)
    assert float(ell_T(0.0, h)) == pytest.approx(2.0 * h, abs=5e-8)


def test_sticky_local_vol_double_skew_atm_response():
    """Exact sticky-LV: Delta sigma_atm ~ 2 kappa h (the local-vol double skew)."""
    base = LinVol(0.2, -0.4, TAU)
    h = 1e-3
    base_atm = float(np.sqrt(base.implied_w(0.0) / TAU))
    new_atm = float(np.sqrt(transported_w(base.implied_w, 0.0, h, "sticky_local_vol") / TAU))
    assert (new_atm - base_atm) == pytest.approx(2.0 * (-0.4) * h, rel=2e-3)


def test_atm_anchor_hits_exact_linear_ssr_target():
    """With the ATM re-anchor a custom SSR moves ATM vol by exactly R kappa h."""
    base = LinVol(0.2, -0.4, TAU)
    r = 1.6
    new_atm = float(
        np.sqrt(
            transported_w(
                base.implied_w, 0.0, H, r, sigma0=0.2, kappa=-0.4, tau=TAU, atm_anchor=True
            )
            / TAU
        )
    )
    assert new_atm == pytest.approx(0.2 + r * (-0.4) * H, abs=1e-9)


def test_is_exact_lv_classification():
    assert is_exact_lv("sticky_local_vol")
    assert is_exact_lv(Regime.STICKY_LOCAL_VOL_GRID)
    assert not is_exact_lv("sticky_strike")
    assert not is_exact_lv("sticky_moneyness")
    assert not is_exact_lv(2.0)  # numeric custom SSR -> SSR-linear, not exact


def test_beta_of_canonical_values():
    assert beta_of("sticky_moneyness") == pytest.approx(1.0)
    assert beta_of("sticky_strike") == pytest.approx(0.5)
    assert beta_of("sticky_local_vol") == pytest.approx(0.0)


def test_grid_node_rule_barycenter():
    """x_i^1 = x_i^0 - (R/2) h: R=0 unchanged, R=1 half, R=2 full -h shift."""
    x = np.array([-0.2, 0.0, 0.1])
    np.testing.assert_allclose(transport_grid_logk(x, H, "sticky_moneyness"), x)
    np.testing.assert_allclose(transport_grid_logk(x, H, "sticky_strike"), x - 0.5 * H)
    np.testing.assert_allclose(transport_grid_logk(x, H, "sticky_local_vol"), x - H)


def test_transported_slice_matches_function_and_vol():
    base = LinVol(0.2, -0.4, TAU)
    slc = TransportedSlice(base, H, "sticky_strike", tau=TAU)
    k = np.linspace(-0.2, 0.2, 17)
    np.testing.assert_allclose(
        slc.implied_w(k), transported_w(base.implied_w, k, H, "sticky_strike")
    )
    np.testing.assert_allclose(slc.implied_vol(k, TAU), np.sqrt(slc.implied_w(k) / TAU))
