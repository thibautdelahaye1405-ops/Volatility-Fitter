"""Generalized LQD tails — Phase 1 golden battery (model layer).

Docs/generalized_tails_calendar_roadmap.md Phase 1; math: book ch. 2
(eqs. xspeed, rightcontinuation, rightroot, beyondgrid,
operationaltailguard, rightsublinearwing, martcondition). Locks:

1. BYTE-IDENTITY — alpha = 0 takes the existing code path exactly: every
   stored array and every priced curve is byte-equal with and without the
   explicit zero exponents (the arc's compatibility bar).
2. GAUSSIAN-RATE REFERENCE — the constant-speed slice at alpha = 1/2 with
   lambda = s/sqrt(2) (the book's normal-tail benchmark): transport against
   an independent integrator, martingale normalization, tail masses against
   scipy.integrate.quad of the same continuation, density, symmetry, the
   flat Gaussian wing constant 2 lambda^2 = s^2, and Lee slopes 0.
3. TAIL SEMANTICS — the lambda_+ < 1 wall applies ONLY in the exponential
   subclass; alpha_+ > 0 builds beyond it but refuses at the saddle guard;
   the moment-domain flip shows up as super-exponential far-call decay.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import quad

from volfit.models.lqd.basis import LQDParams, lee_slopes, wing_law
from volfit.models.lqd.quadrature import Z_MAX, build_slice
from volfit.models.lqd.tails import right_root, tail_mass_left, tail_mass_right

S = 0.2  # Gaussian benchmark: X ~ N(-s^2/2, s^2), lambda = s / sqrt(2)
LAM = S / math.sqrt(2.0)

#: A generic asymmetric smile (same family as the calibration benchmarks).
BODY = dict(L=np.log(0.12), R=np.log(0.10), a=np.array([0.020, -0.010]))


def _softplus(t: float) -> float:
    return max(t, 0.0) + math.log1p(math.exp(-abs(t)))


def _gauss_speed(t: float) -> float:
    """Closed-form x'(t) of the constant-g alpha = 1/2 slice (eq. xspeed)."""
    lm = 1.0 + _softplus(-t)
    lp = 1.0 + _softplus(t)
    return LAM / math.sqrt(lm * lp)


@pytest.fixture(scope="module")
def gauss():
    return build_slice(
        LQDParams(L=np.log(LAM), R=np.log(LAM), a=np.zeros(0),
                  alpha_left=0.5, alpha_right=0.5)
    )


# ---------------------------------------------------------------- identity
def test_alpha_zero_is_byte_identical():
    plain = build_slice(LQDParams(**BODY))
    tagged = build_slice(LQDParams(**BODY, alpha_left=0.0, alpha_right=0.0))
    for name in ("z", "u", "q_z", "a_z", "dq_dz", "da_dz"):
        assert getattr(plain, name).tobytes() == getattr(tagged, name).tobytes()
    assert plain.mu == tagged.mu
    assert plain.a_left == tagged.a_left and plain.a_right == tagged.a_right
    k = np.linspace(-3.0, 3.0, 301)  # spans both beyond-grid tail branches
    assert plain.call_price(k).tobytes() == tagged.call_price(k).tobytes()
    assert plain.density()[1].tobytes() == tagged.density()[1].tobytes()
    assert plain.martingale_check() == tagged.martingale_check()


def test_alphas_are_config_not_theta():
    p = LQDParams(**BODY, alpha_left=0.25, alpha_right=0.5)
    vec = p.to_vector()
    assert vec.size == 2 + p.a.size  # theta length is load-bearing (wire/filter/graph)
    back = LQDParams.from_vector(vec)
    assert back.alpha_left == 0.0 and back.alpha_right == 0.0


@pytest.mark.parametrize("bad", [-0.1, 0.51, float("nan")])
def test_alpha_range_is_validated(bad):
    with pytest.raises(ValueError, match="tail range"):
        LQDParams(**BODY, alpha_right=bad)


# ------------------------------------------------- Gaussian-rate reference
def test_gaussian_transport_matches_independent_integrator(gauss):
    """q_bar(z) = int_0^z x' against scipy.integrate.quad of the closed-form
    speed — locks the gauge arrays and the cumulative quadrature at
    alpha = 1/2 with an integrator that shares no code with the pipeline."""
    h = float(gauss.z[1] - gauss.z[0])
    for z_probe in (-39.0, -20.0, -5.0, 0.7, 5.0, 20.0, 39.0):
        idx = int(round((z_probe + Z_MAX) / h))
        ref, err = quad(_gauss_speed, 0.0, z_probe, limit=500,
                        epsabs=1e-13, epsrel=1e-13)
        assert err < 1e-9  # quad's own (conservative) error estimate
        assert abs((float(gauss.q_z[idx]) - gauss.mu) - ref) < 1e-8


def test_gaussian_tail_masses_match_quad(gauss):
    """The log-domain Gauss-Legendre tail masses against scipy quad of the
    SAME power continuation (eq. rightcontinuation and its mirror)."""
    p = 0.5  # 1 - alpha
    xbar_end = float(gauss.q_z[-1]) - gauss.mu
    ref_r, err_r = quad(
        lambda zz: math.exp(
            xbar_end + LAM / p * ((zz + 1.0) ** p - (Z_MAX + 1.0) ** p) - zz
        ),
        Z_MAX, np.inf, limit=200,
    )
    assert err_r < 1e-16
    got_r = tail_mass_right(xbar_end, gauss.a_right, 0.5, Z_MAX)
    assert got_r == pytest.approx(ref_r, rel=1e-9)
    # The stored ledger boundary IS the normalized right tail mass.
    assert float(gauss.a_z[-1]) == pytest.approx(ref_r * math.exp(gauss.mu), rel=1e-9)

    xbar_start = float(gauss.q_z[0]) - gauss.mu
    ref_l, err_l = quad(
        lambda zz: math.exp(
            xbar_start - LAM / p * ((1.0 - zz) ** p - (Z_MAX + 1.0) ** p) + zz
        ),
        -np.inf, -Z_MAX, limit=200,
    )
    assert err_l < 1e-16
    got_l = tail_mass_left(xbar_start, gauss.a_left, 0.5, Z_MAX)
    assert got_l == pytest.approx(ref_l, rel=1e-9)


def test_gaussian_normalization_symmetry_and_density(gauss):
    assert gauss.martingale_check() == pytest.approx(1.0, abs=1e-9)
    # Symmetric speed -> exactly antisymmetric anchored transport.
    q_bar = gauss.q_z - gauss.mu
    assert float(np.max(np.abs(q_bar + q_bar[::-1]))) < 1e-10
    x, f = gauss.density()
    assert np.all(f > 0.0)
    assert np.allclose(f, f[::-1], rtol=1e-9)  # symmetric law
    assert float(np.trapezoid(f, x)) == pytest.approx(1.0, abs=1e-6)
    # Symmetry makes E[xbar] = 0 exactly, so the var-swap strike is -2 mu.
    # (The s^2 association lives in the TAIL — the wing-law test; the
    # constant-g body is narrower than the matching normal's by design.)
    assert gauss.var_swap_strike() == pytest.approx(-2.0 * gauss.mu, abs=1e-10)
    assert gauss.var_swap_strike() > 0.0


def test_gaussian_prices_match_rank_space_integral(gauss):
    """Interior calls against the direct rank-space integral
    c = int (e^Q - e^k)^+ rho dz — an independent pricing path from the
    ledger/Hermite conjugate the production call_price uses."""
    from scipy.special import expit

    rho = gauss.u * expit(-gauss.z)
    for k in (-0.5, -0.1, 0.0, 0.1, 0.5):
        payoff = np.maximum(np.exp(gauss.q_z) - math.exp(k), 0.0)
        ref = float(np.trapezoid(payoff * rho, gauss.z))
        got = float(gauss.call_price(k))
        assert got == pytest.approx(ref, rel=3e-6, abs=1e-9)


def test_gaussian_wing_law_and_lee(gauss):
    assert lee_slopes(gauss.params) == (0.0, 0.0)
    left, right = wing_law(gauss.params)
    for law in (left, right):
        assert law.tail_class == "gaussian"
        assert law.exponent == 0.0
        # w(k) -> 2 lambda^2 = s^2: the flat implied variance of the
        # matching Gaussian tail (eq. rightsublinearwing at alpha = 1/2).
        assert law.coeff == pytest.approx(S * S, rel=1e-12)


def test_beyond_grid_call_matches_continuation_quad(gauss):
    """Far calls beyond the grid: eq. beyondgrid against scipy quad of the
    exact continuation integral int_{z_k}^inf (e^{Q} - e^k) e^{-z} dz."""
    q_end = float(gauss.q_z[-1])
    p = 0.5
    for k in (q_end + 0.3, q_end + 1.0, q_end + 2.0):
        z_k = float(right_root(k, q_end, gauss.a_right, 0.5, Z_MAX))
        assert z_k > Z_MAX

        def q_hat(zz):
            return q_end + gauss.a_right / p * ((zz + 1.0) ** p - (Z_MAX + 1.0) ** p)

        scale = math.exp(k - z_k)  # factor out the leading magnitude
        ref, _ = quad(
            lambda zz: (math.exp(q_hat(zz) - k) - 1.0) * math.exp(k - zz) / scale,
            z_k, z_k + 2000.0, limit=500,
        )
        got = float(gauss.call_price(k)) / scale
        assert got == pytest.approx(ref, rel=0.05)
        assert got > 0.0


# ------------------------------------------------------- tail semantics
def test_wall_applies_only_to_exponential_subclass():
    hot = dict(L=np.log(0.3), R=np.log(1.2), a=np.zeros(0))  # lambda_+ = 1.2
    with pytest.raises(ValueError, match="integrability"):
        build_slice(LQDParams(**hot))  # alpha_+ = 0: the exact wall
    sl = build_slice(LQDParams(**hot, alpha_right=0.25))  # beyond the wall
    assert sl.martingale_check() == pytest.approx(1.0, abs=1e-9)
    assert np.all(np.isfinite(sl.call_price(np.linspace(-2.0, 6.0, 101))))


def test_saddle_guard_refuses_near_saddle_builds():
    # x'(Z) = lam (Z+1)^{-1/4} > 1 - eps  <=>  lam > (1 - eps) 41^{1/4}
    lam = 1.001 * (Z_MAX + 1.0) ** 0.25
    with pytest.raises(ValueError, match="saddle"):
        build_slice(
            LQDParams(L=np.log(0.3), R=np.log(lam), a=np.zeros(0), alpha_right=0.25)
        )


def test_alpha_continuity_on_the_quoted_strip():
    """Small alpha is indistinguishable from alpha = 0 on the strip (the
    book's nonuniform-limit point: prices converge, the Lee slope does not).
    """
    plain = build_slice(LQDParams(**BODY))
    eps = build_slice(LQDParams(**BODY, alpha_left=1e-6, alpha_right=1e-6))
    k = np.linspace(-1.0, 1.0, 201)
    assert float(np.max(np.abs(plain.call_price(k) - eps.call_price(k)))) < 1e-4
    # ... while the moment domain flips discontinuously (by design).
    assert lee_slopes(eps.params) == (0.0, 0.0)
    assert lee_slopes(plain.params)[1] > 0.03  # beta ~ lambda/2 at small lambda


def test_moment_domain_flip_shows_in_far_price_decay():
    """alpha_+ > 0 makes every positive moment finite: far calls must decay
    super-exponentially, while the exponential subclass caps the log-price
    slope at 1/lambda_+ - 1 (Lee)."""
    lam = dict(L=np.log(0.14), R=np.log(0.14), a=np.zeros(0))
    expo = build_slice(LQDParams(**lam))
    gauss = build_slice(LQDParams(**lam, alpha_left=0.5, alpha_right=0.5))
    k1, k2 = 3.0, 4.0
    slope_expo = float(np.log(expo.call_price(k1)) - np.log(expo.call_price(k2)))
    slope_gauss = float(np.log(gauss.call_price(k1)) - np.log(gauss.call_price(k2)))
    assert slope_expo < 8.0  # bounded by 1/lambda - 1 ~ 6.1 (+ curvature)
    assert slope_gauss > 20.0  # Gaussian-rate decay


def test_asymmetric_exponents_build_and_mix_wing_classes():
    p = LQDParams(**BODY, alpha_left=0.0, alpha_right=0.5)
    sl = build_slice(p)
    assert sl.martingale_check() == pytest.approx(1.0, abs=1e-9)
    beta_l, beta_r = lee_slopes(p)
    assert beta_l > 0.0 and beta_r == 0.0
    left, right = wing_law(p)
    assert left.tail_class == "exponential" and left.coeff == pytest.approx(beta_l)
    assert right.tail_class == "gaussian"
    x, f = sl.density()
    assert np.all(f > 0.0)
    inter = LQDParams(**BODY, alpha_right=0.25)
    law = wing_law(inter)[1]
    assert law.tail_class == "intermediate"
    assert law.exponent == pytest.approx((1.0 - 0.5) / 0.75)
    a_r = np.exp(inter.R + inter.a[0] - inter.a[1])  # P_2(-1)=1, P_3(-1)=-1
    assert law.coeff == pytest.approx(0.5 * (a_r / 0.75) ** (4.0 / 3.0))
