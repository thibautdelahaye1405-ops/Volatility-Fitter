"""SVI-JW conversion domain + screen-vs-butterfly gap (Note 02).

Locks three things the note states as contracts:

  * the regular inverse domain of ``jw_to_raw`` (Note 02 prop. domain): on
    v > 0, p, c > 0, -p/2 < psi < c/2, psi != 0, vtilde < v the conversion is
    exact and round-trips through the JW definitions;
  * the psi = 0 stratum is a genuine coordinate singularity — the handles do
    not identify (m, sigma), so distinct raw slices share the same quintuple;
  * the documented behaviour on invalid input (the converter has NO guards by
    design): scalar p + c = 0 raises ZeroDivisionError, a skew outside
    (-p/2, c/2) yields NaNs (|chi| >= 1), and vtilde >= v yields sigma <= 0 —
    none of these is a silent wrong-but-plausible slice;
  * the two coded fences (min variance >= 0, Lee cap) do NOT certify
    Durrleman g >= 0: the Gatheral–Jacquier butterfly example passes both
    screens while carrying real butterfly arbitrage.
"""

import numpy as np
import pytest

from volfit.models.svi_jw.svi import RawSVI, SVIJW, jw_to_raw


def _raw_to_jw(raw: RawSVI, t: float) -> tuple[float, float, float, float, float]:
    """The JW definitions read off a raw slice (Note 02 eq. jw_def)."""
    w0 = float(raw.total_variance(0.0))
    sqw = np.sqrt(w0)
    chi = raw.m / np.sqrt(raw.m**2 + raw.sigma**2)
    return (
        w0 / t,
        float(raw.b / (2.0 * sqw) * (raw.rho - chi)),
        float(raw.b * (1.0 - raw.rho) / sqw),
        float(raw.b * (1.0 + raw.rho) / sqw),
        float((raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)) / t),
    )


@pytest.mark.parametrize(
    "jw",
    [
        SVIJW(t=0.5, v=0.0425, psi=-0.25, p=0.75, c=0.25, v_tilde=0.034),  # benchmark
        SVIJW(t=0.25, v=0.09, psi=0.10, p=0.40, c=0.60, v_tilde=0.07),  # call-skewed
        SVIJW(t=2.0, v=0.03, psi=-0.05, p=0.30, c=0.28, v_tilde=0.028),  # long-dated
    ],
)
def test_regular_domain_round_trips(jw):
    """Inside the regular domain, jw_to_raw is the exact inverse of the JW
    definitions: converting back recovers the quintuple."""
    raw = jw_to_raw(jw)
    assert raw.b > 0.0 and abs(raw.rho) < 1.0 and raw.sigma > 0.0
    v, psi, p, c, v_tilde = _raw_to_jw(raw, jw.t)
    np.testing.assert_allclose(
        [v, psi, p, c, v_tilde], [jw.v, jw.psi, jw.p, jw.c, jw.v_tilde],
        rtol=1e-10, atol=1e-12,
    )


def test_psi_zero_stratum_not_identified():
    """On psi = 0 (ATM at the vertex, so vtilde = v) the handles do not pin
    (m, sigma): raw slices built with different sigma share the SAME quintuple."""
    t, v, p, c = 0.5, 0.04, 0.5, 0.3
    w0 = v * t
    b = 0.5 * np.sqrt(w0) * (p + c)
    rho = (c - p) / (c + p)
    quintuples = []
    for sigma in (0.05, 0.15, 0.40):
        m = rho * sigma / np.sqrt(1.0 - rho**2)
        a = w0 - b * sigma * np.sqrt(1.0 - rho**2)
        quintuples.append(_raw_to_jw(RawSVI(a=a, b=b, rho=rho, m=m, sigma=sigma), t))
    for q in quintuples[1:]:
        np.testing.assert_allclose(q, quintuples[0], rtol=1e-12, atol=1e-14)
    v_r, psi_r, _, _, vt_r = quintuples[0]
    assert psi_r == pytest.approx(0.0, abs=1e-14)
    assert vt_r == pytest.approx(v_r, abs=1e-14)


def test_invalid_inputs_fail_loudly_not_plausibly():
    """The converter has no guards (deliberate); the failure modes are
    documented and none returns a silently-wrong valid-looking slice."""
    # p + c = 0: scalar float division raises.
    with pytest.raises(ZeroDivisionError):
        jw_to_raw(SVIJW(t=0.5, v=0.04, psi=0.0, p=0.5, c=-0.5, v_tilde=0.03))
    # psi outside (-p/2, c/2): |chi| >= 1 -> sqrt of a negative -> NaNs.
    with np.errstate(invalid="ignore"):
        bad = jw_to_raw(SVIJW(t=0.5, v=0.04, psi=1.0, p=0.5, c=0.5, v_tilde=0.03))
    assert np.isnan(bad.sigma) and np.isnan(bad.m) and np.isnan(bad.a)
    # vtilde >= v: the sigma numerator flips sign -> sigma <= 0, not a slice.
    deg = jw_to_raw(SVIJW(t=0.5, v=0.04, psi=-0.1, p=0.5, c=0.5, v_tilde=0.05))
    assert deg.sigma <= 0.0


def test_core_screens_do_not_certify_butterfly_freedom():
    """The Gatheral–Jacquier example (QF 2014, sec. 3): positive minimum
    variance AND Lee cap satisfied, yet Durrleman g(k) < 0 — the two coded
    fences bound the conditions that usually bite, they are not a butterfly
    certificate. This is the note's (and the deck's) honesty anchor."""
    raw = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
    min_var = raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)
    assert min_var >= 0.0  # screen 1 passes
    assert raw.b * (1.0 + abs(raw.rho)) <= 2.0  # screen 2 (Lee) passes
    k = np.linspace(-1.5, 1.5, 2001)
    km = k - raw.m
    r = np.sqrt(km * km + raw.sigma**2)
    w = raw.total_variance(k)
    assert (w > 0.0).all()
    wp = raw.b * (raw.rho + km / r)
    wpp = raw.b * raw.sigma**2 / r**3
    g = (1.0 - k * wp / (2.0 * w)) ** 2 - (wp**2 / 4.0) * (1.0 / w + 0.25) + wpp / 2.0
    assert g.min() < -0.01  # genuine butterfly arbitrage survives both screens
