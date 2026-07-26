"""Committee revision R5: the guarded JW converter and the desk-unit layer.

The unguarded ``jw_to_raw`` fails differently per case (division error, NaN,
negative width); ``jw_to_raw_checked`` validates the COMPLETE regular domain
with structured reason codes and evaluates the psi->0 denominator in a
cancellation-resistant form. The desk layer converts model units into the
instruments a desk trades (ATM convention, 25/10-delta RR/BF, actual wing
slopes, var swap) plus the committee's missing derivative: what a pure
FORWARD error does to every one of them.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.models.svi_jw.desk import desk_ticket, forward_bump, ticket_delta
from volfit.models.svi_jw.svi import (
    JWDomainError,
    RawSVI,
    SVIJW,
    jw_to_raw,
    jw_to_raw_checked,
)

LAB_JW = SVIJW(t=0.5, v=0.0425, psi=-0.25, p=0.75, c=0.25, v_tilde=0.034)


def _read_jw(raw: RawSVI, tau: float) -> dict[str, float]:
    """The five JW functionals of a raw slice (the note's eq. rawtojw)."""
    w0 = float(raw.total_variance(0.0))
    root0 = np.sqrt(raw.m**2 + raw.sigma**2)
    return {
        "v": w0 / tau,
        "psi": raw.b * (raw.rho - raw.m / root0) / (2.0 * np.sqrt(w0)),
        "p": raw.b * (1.0 - raw.rho) / np.sqrt(w0),
        "c": raw.b * (1.0 + raw.rho) / np.sqrt(w0),
        "v_tilde": (raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)) / tau,
    }


def test_guarded_converter_structured_failures():
    """Every domain violation raises JWDomainError with its reason code —
    never a case-dependent NaN or division error."""
    cases = [
        ({"t": 0.0}, "nonpositive_tenor"),
        ({"v": -0.01}, "nonpositive_variance"),
        ({"p": 0.0}, "nonpositive_wing"),
        ({"psi": -0.40}, "atm_slope_out_of_range"),  # below -p/2 = -0.375
        ({"psi": 0.0}, "singular_stratum"),
        ({"v_tilde": 0.05}, "floor_not_below_level"),
    ]
    for patch, code in cases:
        jw = SVIJW(**{**LAB_JW.__dict__, **patch})
        with pytest.raises(JWDomainError) as err:
            jw_to_raw_checked(jw)
        assert err.value.code == code


def test_guarded_matches_unguarded_inside_the_domain():
    """On regular-domain handles the guarded path is the SAME map — the
    guard adds validation and stability, never a different slice."""
    checked = jw_to_raw_checked(LAB_JW)
    fast = jw_to_raw(LAB_JW)
    for f in ("a", "b", "rho", "m", "sigma"):
        assert getattr(checked, f) == pytest.approx(getattr(fast, f), rel=1e-12)


def test_guarded_converter_is_stable_near_the_stratum():
    """psi -> 0 is where the textbook denominator cancels catastrophically;
    the stable form still round-trips the five functionals at psi = 1e-5."""
    jw = SVIJW(**{**LAB_JW.__dict__, "psi": 1e-5, "c": 0.75})
    raw = jw_to_raw_checked(jw)
    assert raw.sigma > 0.0 and np.isfinite(raw.sigma)
    back = _read_jw(raw, jw.t)
    for name, want in (("v", jw.v), ("psi", jw.psi), ("p", jw.p),
                       ("c", jw.c), ("v_tilde", jw.v_tilde)):
        assert back[name] == pytest.approx(want, rel=1e-6, abs=1e-9)


def test_desk_ticket_reads_the_instruments():
    """Desk sanity — including a conversion subtlety the module exists for:
    a FLAT smile has zero RR/BF exactly, but a smile symmetric in k has a
    POSITIVE 25-delta RR (the lognormal delta convention puts the 25d call
    strike farther from k=0 than the 25d put strike: k_c = |k_p| + w).
    Put skew pushes the RR down; the slopes are the ACTUAL Lee objects."""
    t = 0.25
    flat = RawSVI(a=0.01, b=1e-9, rho=0.0, m=0.0, sigma=0.2)
    ticket = desk_ticket(flat, t)
    assert ticket.rr25 == pytest.approx(0.0, abs=1e-6)
    assert ticket.bf25 == pytest.approx(0.0, abs=1e-6)

    sym = RawSVI(a=0.01, b=0.12, rho=0.0, m=0.0, sigma=0.2)
    ticket = desk_ticket(sym, t)
    assert ticket.rr25 > 0.0  # k-symmetric is NOT delta-symmetric
    assert ticket.bf25 > 0.0 and ticket.bf10 > ticket.bf25
    assert ticket.beta_left == pytest.approx(0.12, abs=5e-3)
    assert ticket.beta_right == pytest.approx(0.12, abs=5e-3)
    assert ticket.var_swap_vol > ticket.atm_vol  # convexity premium

    skew = RawSVI(a=0.01, b=0.12, rho=-0.5, m=0.0, sigma=0.2)
    assert desk_ticket(skew, t).rr25 < ticket.rr25 - 1e-3  # puts bid up


def test_forward_bump_moves_desk_quantities_on_a_skewed_smile():
    """The missing derivative: a +1% forward error re-reads a SKEWED smile as
    an ATM + risk-reversal move even though the smile never changed."""
    skew = RawSVI(a=0.01, b=0.12, rho=-0.5, m=0.0, sigma=0.2)
    t = 0.25
    base = desk_ticket(skew, t)
    bumped = forward_bump(skew, t, rel_bump=0.01)
    row = ticket_delta(base, bumped)
    # F too HIGH by 1%: every strike's log-moneyness drops, the ticket reads
    # the smile shifted LEFT — on a put skew that is a HIGHER ATM reading.
    assert row.atm_vol > 1e-4
    assert abs(row.rr25) > 1e-5  # and a phantom risk-reversal move
    # A symmetric smile at its vertex barely moves ATM (second order).
    sym = RawSVI(a=0.01, b=0.12, rho=0.0, m=0.0, sigma=0.2)
    sym_row = ticket_delta(desk_ticket(sym, t), forward_bump(sym, t, 0.01))
    assert abs(sym_row.atm_vol) < abs(row.atm_vol) / 10.0
