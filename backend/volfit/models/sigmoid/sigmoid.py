"""Multi-Core Sigmoid Implied Variance (MC-SIV) smile model.

This replaces the legacy four-parameter monotone sigmoid with the
Generic Multi-Core SIV slice of ``Docs/Multi_Core_SIV_Technical_Note.tex``:

    v_R(z) = v_SIV(z; theta) + sum_{r=1}^{R} alpha_r B_{c_r, h_r, kappa_r}(z),
    z = k / (sigma_ref sqrt(T))                                  (eqs main-model, z-def)

where ``v`` is annualized Black implied *variance*, ``v_SIV`` is the one-core
SIV base (level / skew / convexity / asymmetric wing slopes, 6 parameters) and
the ``B`` kernels are normalized zero-wing hats (eq B-def). Each signed hat adds
a local variance hump (alpha > 0) or notch (alpha < 0) WITHOUT moving the SIV
wing slopes (eq model-wing-preservation), so the model fits WW / dual-hat
smiles while keeping Lee-compatible tails. The parameter count is 6 + 4R
(eq param-count); R is exposed to the user as the "cores" slider, the direct
analogue of the LQD Legendre order.

The model retains the historical name ``SigmoidSmile`` (SIV = Sigmoid Implied
Variance) so it stays the "sigmoid" family in the API and Smile Viewer. The
analytic kernels live in ``kernels.py``; calibration in ``calibrate.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from volfit.models.sigmoid.kernels import (
    gatheral_g_from_z,
    hat,
    hat_p,
    hat_pp,
    siv_base,
)


@dataclass(frozen=True)
class HatCore:
    """One zero-wing hat B_{c,h,kappa} with signed amplitude (eq B-def).

    ``alpha`` is in variance units and is approximately the variance
    displacement at the centre ``c`` (since B(c) = 1, eq B-center).
    """

    alpha: float
    c: float
    h: float
    kappa: float


@dataclass(frozen=True)
class MultiCoreSiv:
    """Multi-Core SIV smile at one expiry ``t`` (self-pricing SmileModel).

    The base SIV parameters are the structural set (V0, S0, K0, z0, kappa_P,
    kappa_C) of eqs (siv-convexity)-(siv-variance); ``sigma_ref`` fixes the
    z-scale z = k / (sigma_ref sqrt(t)). ``cores`` holds the R signed hats.
    """

    v0: float  # base variance level at z0
    s0: float  # base variance slope (skew) at z0
    k0: float  # base convexity amplitude (>= 0)
    z0: float  # base centre in z-space
    kappa_p: float  # put-wing steepness (z < z0)
    kappa_c: float  # call-wing steepness (z >= z0)
    sigma_ref: float  # reference vol defining z = k / (sigma_ref sqrt(t))
    t: float  # year fraction to expiry
    cores: tuple[HatCore, ...] = field(default_factory=tuple)

    #: Variance floor so vol = sqrt(v) stays real for extreme handles.
    _V_FLOOR = 1e-8

    # ------------------------------------------------------------- coordinates
    def z(self, k: np.ndarray | float) -> np.ndarray:
        """Dimensionless log-strike z = k / (sigma_ref sqrt(t)) (eq z-def)."""
        return np.asarray(k, dtype=float) / (self.sigma_ref * np.sqrt(self.t))

    def variance_z(
        self, z: np.ndarray | float
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Total model variance v_R(z) and z-derivatives (eqs mcsiv-slice/prime/second).

        Returns ``(v, v', v'')`` BEFORE the positivity floor, so the derivatives
        are the exact analytic ones used by the no-arbitrage diagnostic.
        """
        v, vz, vzz = siv_base(z, self.v0, self.s0, self.k0, self.z0, self.kappa_p, self.kappa_c)
        for core in self.cores:
            v = v + core.alpha * hat(z, core.c, core.h, core.kappa)
            vz = vz + core.alpha * hat_p(z, core.c, core.h, core.kappa)
            vzz = vzz + core.alpha * hat_pp(z, core.c, core.h, core.kappa)
        return v, vz, vzz

    # --------------------------------------------------------- SmileModel API
    def vol(self, k: np.ndarray | float) -> np.ndarray:
        """Implied Black volatility sigma(k) = sqrt(v_R(z))."""
        v, _, _ = self.variance_z(self.z(k))
        return np.sqrt(np.maximum(v, self._V_FLOOR))

    def implied_vol(self, k: np.ndarray | float, t: float | None = None) -> np.ndarray:
        """SmileModel interface; ``t`` is accepted for signature parity."""
        return self.vol(k)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """Total implied variance w(k) = sigma(k)^2 t = t v_R(z)."""
        v, _, _ = self.variance_z(self.z(k))
        return self.t * np.maximum(v, self._V_FLOOR)

    # ----------------------------------------------------------- diagnostics
    def gatheral_g(self, k: np.ndarray | float) -> np.ndarray:
        """Durrleman/Gatheral density functional g(k) (eq g-function); g>=0 => no butterfly."""
        z = self.z(k)
        v, vz, vzz = self.variance_z(z)
        return gatheral_g_from_z(z, np.maximum(v, self._V_FLOOR), vz, vzz, self.t, self.sigma_ref)

    def is_butterfly_free(self, k: np.ndarray, eps: float = 0.0) -> bool:
        """True iff g(k) >= eps and v(z) > 0 across the supplied grid."""
        v, _, _ = self.variance_z(self.z(k))
        return bool(np.all(v > 0.0) and np.all(self.gatheral_g(k) >= eps))

    def wing_slopes(self) -> tuple[float, float]:
        """Asymptotic z-space variance wing slopes (-W_P, W_C) (eq mcsiv-wing-slopes).

        The hats are zero-wing, so these depend only on the base SIV:
        v_R'(z) -> S0 -/+ 2 K0 / kappa_{P,C}.
        """
        left = self.s0 - 2.0 * self.k0 / self.kappa_p
        right = self.s0 + 2.0 * self.k0 / self.kappa_c
        return float(left), float(right)

    def to_vector(self) -> np.ndarray:
        """Flat parameter vector [base(6), then (alpha,c,h,kappa) per core]."""
        base = [self.v0, self.s0, self.k0, self.z0, self.kappa_p, self.kappa_c]
        for core in self.cores:
            base.extend([core.alpha, core.c, core.h, core.kappa])
        return np.asarray(base, dtype=float)


#: Historical alias — the API/UI family is still called "sigmoid" (SIV).
SigmoidSmile = MultiCoreSiv
