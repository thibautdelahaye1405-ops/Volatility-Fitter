"""Executable reference maps for the "base and correction" edition of Note 03.

Two functions are the note's Appendix D listing.  ``v_model`` evaluates the
Multi-Core Sigmoid variance by *superposition* --- a convex base carries the
tails, and each signed zero-wing hat adds a local body correction --- returning
the three z-jets (value, slope, curvature) together because the butterfly
diagnostic needs all three.  ``durrleman_g`` converts those jets to
total-variance k-space and evaluates the density factor.  Both are built from
the *production* kernel primitives, and the generator asserts they agree with
the production ``MultiCoreSiv`` to 1e-13 before drawing a single figure, so the
listing printed in the note is the code that produced its numbers.
"""

from __future__ import annotations

import numpy as np

from volfit.models.sigmoid.kernels import (
    hat, hat_p, hat_pp, phi, phi_p, phi_pp,
)


def v_model(z, base, cores):
    """MCS variance v_R(z) = v_base(z) + sum_r alpha_r B_r(z), with its z-jets.

    ``base`` is (v0, s0, k0, z0, kappa_p, kappa_c); ``cores`` is a list of
    (alpha, c, h, kappa).  The base is one convex log-cosh slice that owns the
    asymptotic wings; every hat is a centred second difference that vanishes ---
    in value, slope, and curvature --- in both tails, so the corrections reshape
    the body without moving the wing slopes.
    """
    v0, s0, k0, z0, kp, kc = base
    u = np.asarray(z, dtype=float) - z0
    kappa = np.where(u < 0.0, kp, kc)                 # asymmetric wings, C^2 at z0
    v = v0 + s0 * u + k0 * phi(u, kappa)
    vz = s0 + k0 * phi_p(u, kappa)
    vzz = k0 * phi_pp(u, kappa)
    for alpha, c, h, kap in cores:                    # add the signed zero-wing hats
        v = v + alpha * hat(z, c, h, kap)
        vz = vz + alpha * hat_p(z, c, h, kap)
        vzz = vzz + alpha * hat_pp(z, c, h, kap)
    return v, vz, vzz


def durrleman_g(z, base, cores, t, sigma_ref, v_floor=1e-8):
    """Butterfly diagnostic g(k) >= 0, converting the z-jets to k-space.

    k = sigma_ref sqrt(t) z and w = t v, so w' and w'' pick up sigma_ref/sqrt(t)
    factors.  g is proportional to the risk-neutral density, so g >= 0 on the
    grid is the no-butterfly condition; it is a diagnostic on a finite grid, not
    a global certificate.
    """
    v, vz, vzz = v_model(z, base, cores)
    v = np.maximum(v, v_floor)
    k = sigma_ref * np.sqrt(t) * np.asarray(z, dtype=float)
    w = t * v
    wk = np.sqrt(t) / sigma_ref * vz
    wkk = vzz / sigma_ref**2
    return (1.0 - k * wk / (2.0 * w)) ** 2 - 0.25 * wk**2 * (1.0 / w + 0.25) + 0.5 * wkk
