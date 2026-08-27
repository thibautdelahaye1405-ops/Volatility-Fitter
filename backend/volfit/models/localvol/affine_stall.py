"""Stall-based early-stop bookkeeping for the affine LV calibration (Stage 8).

``calibrate_affine(stall_window > 0)`` stops a cold fit once the DATA misfit has
not improved by a relative ``stall_rtol`` over ``stall_window`` objective
evaluations and returns the best iterate seen. The misfit it tracks is the RMS
of a leading block of the residual vector, deliberately excluding the
always-changing roughness / convexity / front-tie penalty rows so the criterion
follows quote-fit quality, not the regularizer.

Which rows form that block is what this module pins down. Until 2026-08-27 the
block was the OPTION rows only (``(2 if band else 1) * n_options``). The
var-swap rows and the operator-basket rows — which sit right after the option
block in the residual (affine_calib: ``[res_opt, res_varswap, res_basket,
roughness, ...]``) — were INVISIBLE to the criterion. A warm-started fit whose
option block already sat at its optimum then stalled after ``stall_window``
evaluations without ever having moved toward the var-swap quote, and the
best-option-block iterate it returned was the START POINT: the var-swap row
was inert under ``lvEarlyStop`` (measured on the synthetic app: soft 10 %, soft
50 % and hard pin all returned the model unchanged, basis 500 bp; the same fits
with early stop off closed to 400.7 bp / 0.026 bp). The block is now every
DATA row — options + var-swaps + baskets — so a var-swap (market or prior) or a
basket row that is still improving keeps the fit alive.

Byte-identity: a fit with no var-swap and no basket rows has the same block as
before (``stall_block_size`` returns ``n_opt_rows``), so its trajectory and its
stop point are unchanged. Early-stopped fits that DO carry var-swap / basket
rows change — that is the fix.
"""

from __future__ import annotations

import numpy as np


def stall_block_size(n_opt_rows: int, n_varswaps: int, n_baskets: int) -> int:
    """Number of leading residual rows the stall criterion tracks.

    ``n_opt_rows`` is the option block length as assembled by calibrate_affine
    (``(2 if band_mode else 1) * len(options)``); ``n_varswaps`` / ``n_baskets``
    the var-swap and operator-basket row counts that follow it. The block is the
    whole DATA prefix ``[options | var-swaps | baskets]`` of the residual; the
    penalty rows (roughness, convexity, front tie) come after it and are excluded.
    With no extra rows this is exactly ``n_opt_rows`` — the pre-2026-08-27 block.
    """
    return int(n_opt_rows) + int(n_varswaps) + int(n_baskets)


def stall_metric(residual: np.ndarray, n_rows: int) -> float:
    """RMS of the first ``n_rows`` residual entries (the data misfit the stall
    criterion compares). ``n_rows == 0`` (no data rows at all) falls back to the
    whole vector so the criterion still has something to watch."""
    block = residual[:n_rows] if n_rows else residual
    return float(np.sqrt(np.mean(block * block)))
