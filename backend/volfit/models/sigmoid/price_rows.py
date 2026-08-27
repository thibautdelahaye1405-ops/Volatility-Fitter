"""Price-space data rows of the Multi-Core SIV analytic Jacobian
(FitSettings.overlayPriceResiduals — the LQD convention on the MCS fit).

The MCS analogue of ``svi_jw.jacobian._fit_row_pieces``: ``calibrate._fit``
switches its data block from vol space to vega-normalized call prices when
``price_rows`` is given, and this module differentiates THAT block so the
toggle rides the same analytic gate (~2 residual evals per trust-region step,
FINDINGS R5) instead of scipy's ``6 + 4R + 1``-eval finite differences.

Row-wise chain (Docs/Multi_Core_SIV_Technical_Note.tex, "Calibration
methodology"; targets per calib.band.price_targets): with the model variance
``v_R(z)`` of ``jacobian._model_v_grad`` and the total variance
``w = max(v, _V_FLOOR) * t``,

    model      = C(k, w)                      (core.black.black_call)
    d model/dθ = dC/dw · t · dv/dθ            (dC/dw = core.black.black_vega_w)

and the residual rows are ``scale · (model − target)`` (mid mode) or the band
hinge ``scale · violation`` followed by the anchor ``sqrt(maw) · scale ·
(model − target)`` (calib.band.band_residuals), with ``scale = sqrt_w ·
inv_vega`` FROZEN at the quote's mid vega. The variance floor (and the Black
intrinsic switch ``W_MIN``) flatten the gradient on the clamped rows — the
same clamp the vol-space rows apply.
"""

from __future__ import annotations

import numpy as np

from volfit.calib.band import band_violation_sign
from volfit.core.black import W_MIN, black_call, black_vega_w
from volfit.models.sigmoid.seeding import _V_FLOOR


def price_row_blocks(
    v: np.ndarray,
    dv: np.ndarray,
    t: float,
    price_rows: tuple,
    sqrt_w: np.ndarray,
    mid_anchor_weight: float,
) -> list[np.ndarray]:
    """Jacobian blocks (rows x (6+4R)) of the price-space data term.

    ``v``/``dv`` are the model variance and its (N, 6+4R) gradient on the
    quote z-grid; ``price_rows`` is the calibrator's frozen ``(k,
    target_price, inv_vega, price_lo, price_hi)`` tuple. Returns one block
    (mid mode, N rows) or two (band mode: the N hinge rows via the
    ``band_violation_sign`` subgradient, then the N mid-anchor rows) — the
    exact row order of ``calibrate._fit.residuals``' price branch.
    """
    pk, _target_price, inv_vega, price_lo, price_hi = price_rows
    w = np.maximum(v, _V_FLOOR) * t
    dmodel = black_vega_w(pk, w)[:, None] * (t * dv)
    dmodel[(v <= _V_FLOOR) | (w <= W_MIN)] = 0.0  # floored / intrinsic rows are flat
    scale = np.asarray(sqrt_w, float) * np.asarray(inv_vega, float)
    if price_lo is None:  # mid mode (price_targets leaves the edges None)
        return [scale[:, None] * dmodel]
    sign = band_violation_sign(black_call(pk, w), price_lo, price_hi)
    return [
        (scale * sign)[:, None] * dmodel,  # band violation rows
        (np.sqrt(mid_anchor_weight) * scale)[:, None] * dmodel,  # mid anchor rows
    ]
