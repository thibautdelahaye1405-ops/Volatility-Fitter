"""Raw SVI total variance and the SVI-JW (jump-wings) conversion.

Raw SVI (Gatheral):  w(k) = a + b * (rho (k - m) + sqrt((k - m)^2 + sigma^2)).
The JW -> raw conversion follows Appendix A of Docs/lqd_model_note.tex.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RawSVI:
    """Raw SVI parameters for one expiry."""

    a: float
    b: float
    rho: float
    m: float
    sigma: float

    def total_variance(self, k: np.ndarray | float) -> np.ndarray:
        """w(k) = a + b (rho (k-m) + sqrt((k-m)^2 + sigma^2))."""
        km = np.asarray(k, dtype=float) - self.m
        return self.a + self.b * (self.rho * km + np.sqrt(km * km + self.sigma**2))

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        return np.sqrt(self.total_variance(k) / t)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """SmileModel interface alias for total variance."""
        return self.total_variance(k)

    def wing_slopes(self) -> tuple[float, float]:
        """Asymptotic total-variance slopes (left, right) = b(1 -+ rho)."""
        return self.b * (1.0 - self.rho), self.b * (1.0 + self.rho)


def durrleman_g_raw(raw: RawSVI, k: np.ndarray) -> np.ndarray:
    """Durrleman's g from the slice's CLOSED-FORM derivatives (exact — the
    production rule: model derivatives, never differenced prices):
    w' = b(rho + km/R), w'' = b s^2 / R^3 with R = sqrt(km^2 + s^2)."""
    k = np.asarray(k, dtype=float)
    km = k - raw.m
    r = np.sqrt(km * km + raw.sigma**2)
    w = np.maximum(raw.a + raw.b * (raw.rho * km + r), 1e-12)
    wp = raw.b * (raw.rho + km / r)
    wpp = raw.b * raw.sigma**2 / r**3
    return (1.0 - k * wp / (2.0 * w)) ** 2 - 0.25 * wp * wp * (1.0 / w + 0.25) + 0.5 * wpp


@dataclass(frozen=True)
class SVIJW:
    """SVI-JW parameters: ATM variance v, ATM skew psi, put/call wing slopes
    p and c, and minimum implied variance vtilde, all at expiry t."""

    t: float
    v: float
    psi: float
    p: float
    c: float
    v_tilde: float


class JWDomainError(ValueError):
    """A JW point outside the regular inverse domain (committee R5): the
    failure is STRUCTURED — ``code`` is machine-readable, the message says
    which inequality failed and what it means — instead of the unguarded
    converter's case-dependent NaNs/divisions."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def jw_to_raw_checked(jw: SVIJW) -> RawSVI:
    """Domain-guarded JW -> raw inverse with a cancellation-resistant
    denominator (committee R5; the note's Appendix D reference, promoted to
    production). Validates the COMPLETE regular domain and raises
    ``JWDomainError`` with a reason code; the singular stratum psi = 0 is
    rejected explicitly (the regular inverse does not exist there — the
    belly width is unidentified). The denominator D vanishes quadratically
    as psi -> 0, so it is evaluated in a form that never subtracts two
    large near-equal numbers."""
    if not jw.t > 0.0:
        raise JWDomainError("nonpositive_tenor", f"tenor t={jw.t} must be > 0")
    if not jw.v > 0.0:
        raise JWDomainError("nonpositive_variance", f"ATM variance v={jw.v} must be > 0")
    if not (jw.p > 0.0 and jw.c > 0.0):
        raise JWDomainError(
            "nonpositive_wing", f"wing handles p={jw.p}, c={jw.c} must both be > 0"
        )
    if not (-0.5 * jw.p < jw.psi < 0.5 * jw.c):
        raise JWDomainError(
            "atm_slope_out_of_range",
            f"psi={jw.psi} outside (-p/2, c/2)=({-0.5 * jw.p}, {0.5 * jw.c}) — "
            "|chi| >= 1, no hyperbola matches",
        )
    if jw.psi == 0.0:
        raise JWDomainError(
            "singular_stratum",
            "psi = 0 is the singular stratum: the belly width s is "
            "unidentified there (JW image theorem) — no regular inverse",
        )
    if not jw.v_tilde < jw.v:
        raise JWDomainError(
            "floor_not_below_level",
            f"minimum variance v_tilde={jw.v_tilde} must sit strictly below "
            f"the ATM level v={jw.v}",
        )
    w0 = jw.v * jw.t
    b = 0.5 * np.sqrt(w0) * (jw.p + jw.c)
    rho = (jw.c - jw.p) / (jw.c + jw.p)
    chi = rho - 4.0 * jw.psi / (jw.p + jw.c)
    q_rho, q_chi = np.sqrt(1.0 - rho * rho), np.sqrt(1.0 - chi * chi)
    # D = (1 - rho*chi)/q_chi - q_rho, rearranged so no two large near-equal
    # numbers are subtracted; algebraically identical, numerically stable.
    dq = (chi - rho) * (chi + rho) / (q_rho + q_chi)
    denom = ((rho - chi) ** 2 + dq**2) / (2.0 * q_chi)
    width = (w0 - jw.v_tilde * jw.t) / (b * denom)
    m = chi * width / q_chi
    a = jw.v_tilde * jw.t - b * width * q_rho
    return RawSVI(a=float(a), b=float(b), rho=float(rho), m=float(m), sigma=float(width))


def jw_to_raw(jw: SVIJW) -> RawSVI:
    """Convert SVI-JW to raw SVI (note Appendix A, eqs. jw_w0..sigma_solve).

    UNGUARDED fast path (the note's product caution): callers must feed
    handles inside the regular domain. Any user-facing workflow goes through
    ``jw_to_raw_checked`` instead (committee R5)."""
    w0 = jw.v * jw.t
    sqw = np.sqrt(w0)
    b = 0.5 * sqw * (jw.p + jw.c)
    rho = (jw.c - jw.p) / (jw.c + jw.p)
    # chi = m / sqrt(m^2 + sigma^2)  (eq. chi)
    chi = rho - 4.0 * jw.psi / (jw.p + jw.c)
    one_m_chi2 = np.sqrt(1.0 - chi * chi)
    one_m_rho2 = np.sqrt(1.0 - rho * rho)
    sigma = (w0 - jw.v_tilde * jw.t) / (b * ((1.0 - rho * chi) / one_m_chi2 - one_m_rho2))
    m = chi * sigma / one_m_chi2
    a = jw.v_tilde * jw.t - b * sigma * one_m_rho2
    return RawSVI(a=float(a), b=float(b), rho=float(rho), m=float(m), sigma=float(sigma))
