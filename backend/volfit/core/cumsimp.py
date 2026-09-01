"""Uniform-step cumulative Simpson — the LQD quadrature's compiled inner loop.

``scipy.integrate.cumulative_simpson`` dominated the LQD slice fit (~65% of
the wall before the 2-D row batching, and still roughly half of what remained
through its array-API wrapper: every ``build_slice`` makes two 1-D calls and
every analytic-Jacobian iterate two (P, M) batched calls). On the fitter's
grids the step is always uniform and ``initial`` is always 0, so this module
reimplements EXACTLY scipy's equal-interval arithmetic
(``_cumulative_simpson_equal_intervals`` + the h1/h2 interleave of
``_cumulatively_sum_simpson_integrals``, scipy >= 1.12) as one Numba kernel.

Bit-identity, not closeness: the algorithm involves only ``+ - * /`` on the
same doubles in the same order (no transcendentals, and the prefix sum is a
sequential accumulation both here and in numpy's ``cumulative_sum``), so the
compiled result equals scipy's to the last bit. That contract is locked by
``tests/test_batched_kernels.py`` against scipy on random data, and end-to-end
by the golden fit suites. Without numba (or for shapes/arguments outside the
fast path) the call simply falls through to scipy itself.
"""

from __future__ import annotations

import numpy as np

try:  # optional dependency — graceful scipy fallback, as for the LV march
    from numba import njit

    _HAVE_NUMBA = True
except ImportError:  # pragma: no cover - exercised via the fallback test
    _HAVE_NUMBA = False

    def njit(*args, **kwargs):  # type: ignore
        def deco(fn):
            return fn

        return deco


@njit(cache=True, nogil=True)
def _kernel(y: np.ndarray, dx: float, out: np.ndarray) -> None:  # pragma: no cover
    """Row-wise cumulative Simpson over uniform intervals, scipy's float ops.

    scipy forms, per interval ``j -> j+1`` (h1 = forward quadratic through
    ``(j, j+1, j+2)``, h2 = the reversed-array mirror through
    ``(j-1, j, j+1)``), the sub-integrals

        h1[j] = dx/3 * (5 y[j]/4 + 2 y[j+1] - y[j+2]/4)
        h2[j] = dx/3 * (5 y[j+1]/4 + 2 y[j] - y[j-1]/4)

    interleaved as h1 on even ``j`` (except the last interval, which only h2
    can integrate), h2 on odd ``j`` — then a sequential prefix sum with the
    0.0 initial. The expressions below keep scipy's operation ORDER so the
    doubles agree bit-for-bit.
    """
    p, m = y.shape
    for r in range(p):
        acc = 0.0
        out[r, 0] = 0.0
        for j in range(m - 1):
            if (j % 2) == 0 and j != m - 2:
                v = dx / 3.0 * (5.0 * y[r, j] / 4.0 + 2.0 * y[r, j + 1] - y[r, j + 2] / 4.0)
            else:
                v = dx / 3.0 * (5.0 * y[r, j + 1] / 4.0 + 2.0 * y[r, j] - y[r, j - 1] / 4.0)
            acc += v
            out[r, j + 1] = acc


def cumulative_simpson_uniform(
    y: np.ndarray, dx: float = 1.0, initial: float = 0.0
) -> np.ndarray:
    """Drop-in for ``scipy.integrate.cumulative_simpson(y, dx=dx, initial=0.0)``
    on 1-D or row-stacked 2-D input with a uniform step.

    Anything outside the compiled fast path (no numba, fewer than 3 samples —
    where scipy falls back to cumulative_trapezoid — a non-zero ``initial``,
    or an unexpected rank) delegates to scipy itself, so behaviour is the
    reference behaviour everywhere by construction.
    """
    y = np.asarray(y, dtype=float)
    if not _HAVE_NUMBA or y.ndim not in (1, 2) or y.shape[-1] < 3 or initial != 0.0:
        from scipy.integrate import cumulative_simpson

        return cumulative_simpson(y, dx=dx, initial=initial)
    y2 = y[None, :] if y.ndim == 1 else y
    out = np.empty(y2.shape)
    _kernel(y2, float(dx), out)
    return out[0] if y.ndim == 1 else out
