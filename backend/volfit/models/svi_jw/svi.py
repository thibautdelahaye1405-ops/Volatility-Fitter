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

    def wing_slopes(self) -> tuple[float, float]:
        """Asymptotic total-variance slopes (left, right) = b(1 -+ rho)."""
        return self.b * (1.0 - self.rho), self.b * (1.0 + self.rho)


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


def jw_to_raw(jw: SVIJW) -> RawSVI:
    """Convert SVI-JW to raw SVI (note Appendix A, eqs. jw_w0..sigma_solve)."""
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
