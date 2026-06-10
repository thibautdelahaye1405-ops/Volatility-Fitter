"""LQD (log-quantile-density) smile model.

Implements Docs/lqd_model_note.tex: an arbitrage-free-by-construction slice
parametrization of the risk-neutral log-forward return via its log quantile
density

    l(u) = -log u - log(1-u) + (1-u) L + u R + sum_{n>=2} a_n P_n(1 - 2u).
"""

from volfit.models.lqd.basis import LQDParams, endpoint_scales, lee_slopes
from volfit.models.lqd.quadrature import LQDSlice, build_slice
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.calibrate import calibrate_slice, logistic_init

__all__ = [
    "LQDParams",
    "LQDSlice",
    "atm_handles",
    "build_slice",
    "calibrate_slice",
    "endpoint_scales",
    "lee_slopes",
    "logistic_init",
]
