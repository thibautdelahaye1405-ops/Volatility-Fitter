"""Executable reference maps for the alternative SVI-JW note."""

from __future__ import annotations

import numpy as np

from volfit.models.svi_jw.svi import RawSVI, SVIJW


def raw_to_jw(raw: RawSVI, tau: float) -> dict[str, float]:
    """Read the five JW functionals from a raw SVI slice."""
    w0 = float(raw.total_variance(0.0))
    root0 = np.sqrt(raw.m * raw.m + raw.sigma * raw.sigma)
    sqw0 = np.sqrt(w0)
    return {
        "v": w0 / tau,
        "psi": raw.b * (raw.rho - raw.m / root0) / (2.0 * sqw0),
        "p": raw.b * (1.0 - raw.rho) / sqw0,
        "c": raw.b * (1.0 + raw.rho) / sqw0,
        "v_tilde": (
            raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)
        ) / tau,
    }


def jw_to_raw_checked(jw: SVIJW) -> RawSVI:
    """Checked regular inverse, using a cancellation-resistant denominator."""
    if not (
        jw.t > 0.0 and jw.v > 0.0 and jw.p > 0.0 and jw.c > 0.0
        and -0.5 * jw.p < jw.psi < 0.5 * jw.c
        and jw.psi != 0.0 and jw.v_tilde < jw.v
    ):
        raise ValueError("JW point is outside the regular inverse domain")
    w0 = jw.v * jw.t
    b = 0.5 * np.sqrt(w0) * (jw.p + jw.c)
    rho = (jw.c - jw.p) / (jw.c + jw.p)
    chi = rho - 4.0 * jw.psi / (jw.p + jw.c)
    q_rho, q_chi = np.sqrt(1.0 - rho * rho), np.sqrt(1.0 - chi * chi)
    dq = (chi - rho) * (chi + rho) / (q_rho + q_chi)
    denom = ((rho - chi) ** 2 + dq**2) / (2.0 * q_chi)
    width = (w0 - jw.v_tilde * jw.t) / (b * denom)
    m = chi * width / q_chi
    a = jw.v_tilde * jw.t - b * width * q_rho
    return RawSVI(a=float(a), b=float(b), rho=float(rho),
                  m=float(m), sigma=float(width))
