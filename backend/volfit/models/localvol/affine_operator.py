"""The affine LV calibration's Jacobian as a matrix-free linear operator.

``LinearizedJacobian`` is the operator the matrix-free Gauss-Newton solver
(affine_gn) and its active-set step (affine_activeset) work on: the dense data
block of one sensitivity-carrying PDE solve, optionally over the sparse
regularisation block, exposing the tangent / adjoint matvecs, the Jacobi
column scaling and a dense materialisation for the TRF fallback. Split out of
affine_gn.py (2026-09-09) when the shared-block band form pushed that module
past the file-size policy; affine_gn re-exports the name, so every historical
import path still works. Identity locks: tests/test_affine_gn.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse.linalg import LinearOperator


@dataclass
class LinearizedJacobian:
    """The Jacobian J of one linearisation as a matrix-free linear operator.

    Exposes the products an inexact-Newton step needs without forming JᵀJ or an
    SVD: ``apply_jacobian(v) = J·v`` (tangent), ``apply_jacobian_transpose(w) = Jᵀ·w``
    (adjoint / gradient), and ``column_scale`` (the Jacobi preconditioner 1/‖col‖).

    J is stored as a top **dense data block** ``jac`` (the option/var-swap rows,
    dense in the vertices their expiry touches) optionally stacked over a **sparse
    regularisation block** ``reg`` (the roughness / convex / front-tie rows, 3-nnz
    per row). Keeping ``reg`` sparse makes both the matvec (O(nnz) not O(M_reg·n))
    and the assembly (no dense reg materialisation) cheap — the bulk of the GN
    per-eval cost after the SVD is gone. ``reg=None`` ⇒ ``jac`` IS the whole matrix
    (the legacy dense path; the identity tests cover both).

    ``row_scales`` (2026-09-09, the band objective): the data rows are K row-
    scaled copies of ONE matrix — ``[diag(s_1)·jac; …; diag(s_K)·jac]`` — as the
    bid-ask / haircut block is (violation rows ``sign/η ⊙ jp`` over anchor rows
    ``√a/η ⊙ jp``, the same price sensitivities ``jp``). The operator applies
    ``jac`` ONCE per matvec and scales, never materialising the copies: the
    dense matvec streams a 3 MB block from memory and was the whole lsmr cost.
    ``extra`` is a small dense block of further data rows (the density-
    smoothness rows) stacked after the scaled copies, before ``reg``.
    """

    jac: np.ndarray  # dense (M_data, n) data block (or the whole matrix if reg None)
    reg: object = None  # optional sparse (M_reg, n) regularisation block, stacked below
    row_scales: tuple | None = None  # K row scalings of ``jac`` (the band block)
    extra: np.ndarray | None = None  # dense rows after the scaled copies (density rows)

    def __post_init__(self) -> None:
        # Cache the transposed reg block once: ``self.reg.T`` inside the
        # adjoint matvec constructed a fresh transposed wrapper on every lsmr
        # iteration (~6k CSC constructions per cold SPY fit, ~10% of the
        # solve wall). Same object, same sparse matvec kernel, same floats —
        # pure constructor-overhead removal.
        self._reg_T = self.reg.T if self.reg is not None else None
        self._n_extra = 0 if self.extra is None else int(self.extra.shape[0])

    @property
    def n_data(self) -> int:
        """Rows of the data block (the scaled copies + extra), before ``reg``."""
        k = 1 if self.row_scales is None else len(self.row_scales)
        return k * int(self.jac.shape[0]) + self._n_extra

    @property
    def shape(self) -> tuple[int, int]:
        m = self.n_data + (self.reg.shape[0] if self.reg is not None else 0)
        return (m, self.jac.shape[1])

    def _data_dense(self) -> np.ndarray:
        if self.row_scales is None:
            blocks = [self.jac]
        else:
            blocks = [s[:, None] * self.jac for s in self.row_scales]
        if self.extra is not None:
            blocks.append(self.extra)
        return blocks[0] if len(blocks) == 1 else np.vstack(blocks)

    def to_dense(self) -> np.ndarray:
        """The full dense Jacobian (data over reg) — for a scipy TRF fallback."""
        data = self._data_dense()
        if self.reg is None:
            return data
        return np.vstack([data, np.asarray(self.reg.todense())])

    def apply_jacobian(self, v: np.ndarray) -> np.ndarray:
        """Tangent action J·v (directional derivative of the residual in v)."""
        v = np.asarray(v, dtype=float)
        jv = self.jac @ v
        parts = [jv] if self.row_scales is None else [s * jv for s in self.row_scales]
        if self.extra is not None:
            parts.append(self.extra @ v)
        if self.reg is not None:
            parts.append(self.reg @ v)
        return parts[0] if len(parts) == 1 else np.concatenate(parts)

    def apply_jacobian_transpose(self, w: np.ndarray) -> np.ndarray:
        """Adjoint action Jᵀ·w (e.g. the gradient Jᵀr of ½‖r‖²)."""
        w = np.asarray(w, dtype=float)
        m0 = int(self.jac.shape[0])
        if self.row_scales is None:
            out = self.jac.T @ w[:m0]
            pos = m0
        else:
            acc = np.zeros(m0)
            pos = 0
            for s in self.row_scales:
                acc += s * w[pos:pos + m0]
                pos += m0
            out = self.jac.T @ acc
        if self.extra is not None:
            out = out + self.extra.T @ w[pos:pos + self._n_extra]
            pos += self._n_extra
        if self.reg is not None:
            out = out + self._reg_T @ w[pos:]
        return out

    def column_scale(self, floor: float = 1e-12) -> np.ndarray:
        """Jacobi preconditioner s_j = 1/‖J_·j‖ (equilibrates column norms).

        Columns with a vanishing norm (a vertex no quote/penalty touches) get the
        floor so the scaled column stays finite; the bound projection keeps such a
        parameter pinned anyway.
        """
        if self.row_scales is None:
            col2 = np.einsum("ij,ij->j", self.jac, self.jac)
        else:
            w2 = sum(s * s for s in self.row_scales)
            col2 = np.einsum("i,ij,ij->j", w2, self.jac, self.jac)
        if self.extra is not None:
            col2 = col2 + np.einsum("ij,ij->j", self.extra, self.extra)
        if self.reg is not None:
            col2 = col2 + np.asarray(self.reg.power(2).sum(axis=0)).ravel()
        return 1.0 / np.sqrt(np.maximum(col2, floor))

    def scaled_operator(self, scale: np.ndarray) -> LinearOperator:
        """``A = J·diag(scale)`` as a SciPy LinearOperator (for the lsmr step).

        lsmr sees only the matvec ``J(scale·y)`` and the rmatvec ``scale·(Jᵀw)`` —
        no dense factorisation. Solving in y = θ/scale is the preconditioning.
        """
        m, n = self.shape
        s = np.asarray(scale, dtype=float)
        return LinearOperator(
            (m, n),
            matvec=lambda y: self.apply_jacobian(s * y),
            rmatvec=lambda w: s * self.apply_jacobian_transpose(w),
        )
