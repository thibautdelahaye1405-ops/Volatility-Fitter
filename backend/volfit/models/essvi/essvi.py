"""The SSVI slice: Gatheral-Jacquier's surface SVI restricted to one expiry.

Gatheral & Jacquier (2014), "Arbitrage-free SVI volatility surfaces",
Quantitative Finance 14(1), eq. (4.1): with theta the ATM total variance
of the expiry, a correlation rho in (-1, 1) and a curvature phi > 0,

    w(k) = theta / 2 * (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2)).

In SSVI proper phi = phi(theta) and rho are shared by every expiry;
Hendriks & Martini (2019), "The extended SSVI volatility surface" (eSSVI),
free rho per expiry too, so ONE slice carries exactly three handles
(theta, rho, phi) — the comparator-only family "essvi" of the Compare tab
(never a displayed model). A slice is the raw SVI of models/svi_jw/svi.py at

    a = theta (1 - rho^2) / 2,   b = theta phi / 2,
    m = -rho / phi,              sigma = sqrt(1 - rho^2) / phi,

i.e. a three-parameter sub-family in which the ATM level, the belly width
and the two wings are tied together — the yardstick the five-parameter
SVI-JW row is measured against on the same quotes.

Everything the compare row reads is CLOSED-FORM (never differenced):

  * ATM: w(0) = theta, w'(0) = rho phi theta, w''(0) = theta phi^2 (1-rho^2)/2;
  * derivatives, with R(k) = sqrt((phi k + rho)^2 + 1 - rho^2):
        w'(k)  = theta phi / 2 * (rho + (phi k + rho) / R),
        w''(k) = theta phi^2 (1 - rho^2) / (2 R^3);
  * Lee wings  w'(k) -> +- theta phi (1 +- rho) / 2  (k-space slopes of w);
  * Durrleman's g(k) = (1 - k w'/(2w))^2 - (w'/2)^2 (1/w + 1/4) + w''/2;
  * no-butterfly conditions (GJ Theorem 4.2, one slice at a time):
        (i)  theta phi (1 + |rho|) < 4      (Lee's bound: max slope < 2),
        (ii) theta phi^2 (1 + |rho|) <= 4.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from volfit.models.diagnostics import SliceHandles
from volfit.models.svi_jw.svi import RawSVI

#: Floor on total variance inside g (the svi.py convention).
_W_FLOOR = 1e-12


@dataclass(frozen=True)
class ESSVISlice:
    """One (e)SSVI slice at expiry ``t``: ATM total variance ``theta``,
    correlation ``rho`` and curvature ``phi`` (GJ 2014 eq. 4.1). Frozen, and
    deliberately WITHOUT a ``sigma`` attribute — the raw-SVI duck test in
    diagnostics.analytic_butterfly keys on that name."""

    theta: float
    rho: float
    phi: float
    t: float

    # ------------------------------------------------------------ the curve
    def _u_r(self, k: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """u = phi k + rho and the root R = sqrt(u^2 + 1 - rho^2)."""
        u = self.phi * k + self.rho
        return u, np.sqrt(u * u + 1.0 - self.rho * self.rho)

    def total_variance(self, k: np.ndarray | float) -> np.ndarray:
        """w(k) = theta/2 (1 + rho phi k + R(k))  (GJ 2014 eq. 4.1)."""
        k = np.asarray(k, dtype=float)
        _u, r = self._u_r(k)
        return 0.5 * self.theta * (1.0 + self.rho * self.phi * k + r)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        """SmileModel interface alias for total variance."""
        return self.total_variance(k)

    def implied_vol(self, k: np.ndarray | float, t: float | None = None) -> np.ndarray:
        """SmileModel interface; ``t`` defaults to the slice's own expiry."""
        return np.sqrt(self.total_variance(k) / (self.t if t is None else t))

    # --------------------------------------------------------- closed forms
    def w1(self, k: np.ndarray | float) -> np.ndarray:
        """dw/dk = theta phi / 2 * (rho + u / R)."""
        k = np.asarray(k, dtype=float)
        u, r = self._u_r(k)
        return 0.5 * self.theta * self.phi * (self.rho + u / r)

    def w2(self, k: np.ndarray | float) -> np.ndarray:
        """d2w/dk2 = theta phi^2 (1 - rho^2) / (2 R^3)."""
        k = np.asarray(k, dtype=float)
        _u, r = self._u_r(k)
        return 0.5 * self.theta * self.phi**2 * (1.0 - self.rho * self.rho) / r**3

    def durrleman_g(self, k: np.ndarray | float) -> np.ndarray:
        """Durrleman/Gatheral g(k) from the CLOSED-FORM w', w'' (exact — the
        production rule: model derivatives, never differenced prices)."""
        k = np.asarray(k, dtype=float)
        w = np.maximum(self.total_variance(k), _W_FLOOR)
        wp, wpp = self.w1(k), self.w2(k)
        return (1.0 - k * wp / (2.0 * w)) ** 2 - 0.25 * wp * wp * (1.0 / w + 0.25) + 0.5 * wpp

    def gatheral_g(self, k: np.ndarray | float) -> np.ndarray:
        """``durrleman_g`` under the Multi-Core Sigmoid's name, so
        diagnostics.analytic_butterfly dispatches both families on one branch."""
        return self.durrleman_g(k)

    def wing_slopes(self) -> tuple[float, float]:
        """Asymptotic total-variance slopes (left, right) = theta phi (1 -/+ rho) / 2,
        w ~ slope |k| on each side — the Lee columns of the compare row, in the
        same units as raw SVI's b(1 -/+ rho)."""
        half = 0.5 * self.theta * self.phi
        return float(half * (1.0 - self.rho)), float(half * (1.0 + self.rho))

    def lee_slopes(self) -> tuple[float, float]:
        """The wing slopes under the MCS name (models.wings.wing_laws_of)."""
        return self.wing_slopes()

    def atm_vol(self) -> float:
        """sqrt(theta / t): w(0) = theta exactly."""
        return float(np.sqrt(self.theta / self.t))

    def atm_handles(self) -> SliceHandles:
        """Exact ATM level / skew / curvature of sigma(k) = sqrt(w(k)/t):
        sigma' = w'/(2 sigma t) and sigma'' = (w''/(2t) - sigma'^2)/sigma at k = 0."""
        sig = self.atm_vol()
        wp0 = self.rho * self.phi * self.theta
        wpp0 = 0.5 * self.theta * self.phi**2 * (1.0 - self.rho * self.rho)
        skew = wp0 / (2.0 * sig * self.t)
        curvature = (wpp0 / (2.0 * self.t) - skew * skew) / sig
        return SliceHandles(atm_vol=sig, skew=float(skew), curvature=float(curvature))

    def to_vector(self) -> np.ndarray:
        """(theta, rho, phi) — the three free handles."""
        return np.array([self.theta, self.rho, self.phi], dtype=float)

    def to_raw_svi(self) -> RawSVI:
        """The identical curve as a raw SVI (module docstring embedding)."""
        s = float(np.sqrt(1.0 - self.rho * self.rho))
        return RawSVI(
            a=0.5 * self.theta * (1.0 - self.rho * self.rho),
            b=0.5 * self.theta * self.phi,
            rho=self.rho,
            m=-self.rho / self.phi,
            sigma=s / self.phi,
        )


def butterfly_lhs(slice_: ESSVISlice) -> tuple[float, float]:
    """The two left-hand sides of GJ Theorem 4.2, ``(theta phi (1+|rho|),
    theta phi^2 (1+|rho|))``, to be held strictly below 4 and at most 4."""
    lift = slice_.theta * (1.0 + abs(slice_.rho))
    return float(lift * slice_.phi), float(lift * slice_.phi**2)


def is_butterfly_free(slice_: ESSVISlice) -> bool:
    """Both GJ Theorem 4.2 conditions hold (sufficient for g >= 0 on the line)."""
    c1, c2 = butterfly_lhs(slice_)
    return c1 < 4.0 and c2 <= 4.0
