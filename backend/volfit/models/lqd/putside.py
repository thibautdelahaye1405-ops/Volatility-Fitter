"""Left-side (OTM put) pricing for LQD slices.

The right wing prices calls as C(k) = A(z_k) - e^k (1 - u_k) (eq. call_logit
of Docs/lqd_model_note.tex), each factor evaluated on its own numerically
clean side. This module is the LEFT mirror: the lower asset-share integral

    Lo(z) = int_{-inf}^{z} e^{Q} u(1-u) ds = E[e^X 1_{X <= Q(z)}]

accumulated from the left boundary (plus the same left tail correction the
martingale ledger uses — eq. left_tail_corr at alpha = 0, the log-domain
power continuation of volfit.models.lqd.tails otherwise) prices the put as

    P(k) = e^k u_k - Lo(z_k)               (parity mirror of eq. call_logit).

Both terms live on the e^{Q(z)+z} scale of the left wing, so the subtraction
only spends the ~A_L cancellation the right wing already spends and the deep
put keeps full RELATIVE accuracy. The parity route P = C - (1 - e^k) instead
floors the put's time value at the ~1e-16 ABSOLUTE round-off of the intrinsic
leg — on a 2-day slice that wipes out the whole lower wing (the short-dated
far-downside display bug: IV drawn flat left of the last invertible strike).

Lives outside quadrature.py only for the 400-line file policy; everything
here reads the built slice's own arrays (see LQDSlice._lower_share).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from volfit.models.lqd.interp import hermite_eval
from volfit.models.lqd.tails import left_tail_put, right_tail_call, tail_mass_left

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from volfit.models.lqd.quadrature import LQDSlice


def lower_share(sl: "LQDSlice") -> np.ndarray:
    """Lo(z) on the slice grid: forward cumulative quadrature of the exact
    nodal mass e^{Q} u(1-u) (= -da_dz, already normalized) plus the left tail
    correction, mirroring how build_slice assembles ``a_z`` from the right."""
    from volfit.models.lqd.quadrature import _cumquad

    fwd = _cumquad(-sl.da_dz, dx=sl._step, initial=0.0)
    z_end = float(sl.z[-1])
    if sl.params.alpha_left == 0.0:
        corr = float(np.exp(sl.q_z[0] - z_end)) / (1.0 + sl.a_left)
    else:
        corr = tail_mass_left(float(sl.q_z[0]), sl.a_left, sl.params.alpha_left, z_end)
    return fwd + corr


def put_price(sl: "LQDSlice", k_arr: np.ndarray) -> np.ndarray:
    """Normalized put P(k) = e^k u_k - Lo(z_k) via eq. call_logit's mirror.

    Beyond the grid's quantile range the slice's OWN tail continuations apply,
    at the same seams as call_price: the left (OTM) side prices the put
    directly — never through parity — while the deep-right (ITM) put falls
    back to parity off the right tail call, where the time value is the
    call's and nothing cancels.
    """
    z_k = sl.strike_to_z(k_arr)
    lo_k = hermite_eval(z_k, float(sl.z[0]), sl._step, sl._lower_share, -sl.da_dz)
    # e^k u_k in log space: log u = -softplus(-z), so the deep-left product
    # cannot round through zero (mirror of call_price's right-wing guard).
    p = np.exp(k_arr - np.logaddexp(0.0, -z_k)) - lo_k
    if sl.a_left > 0.0:
        if sl.params.alpha_left == 0.0:
            z_l = sl.z[0] + (k_arr - sl.q_z[0]) / sl.a_left
            tail_l = np.exp(np.minimum(k_arr + z_l, 0.0)) * (
                sl.a_left / (1.0 + sl.a_left))
        else:
            tail_l = left_tail_put(
                k_arr, float(sl.q_z[0]), sl.a_left,
                sl.params.alpha_left, float(sl.z[-1]))
        p = np.where(k_arr < sl.q_z[0], tail_l, p)
    if sl.a_right > 0.0:
        if sl.params.alpha_right == 0.0:
            z_r = sl.z[-1] + (k_arr - sl.q_z[-1]) / sl.a_right
            tail_c = np.exp(np.minimum(k_arr - z_r, 0.0)) * (
                sl.a_right / (1.0 - sl.a_right))
        else:
            tail_c = right_tail_call(
                k_arr, float(sl.q_z[-1]), sl.a_right,
                sl.params.alpha_right, float(sl.z[-1]))
        p = np.where(k_arr > sl.q_z[-1], tail_c + np.expm1(k_arr), p)
    return p
