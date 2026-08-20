"""Accepted-step replay trace of the affine LV calibration (V3.5 item 13).

Post-hoc replay, design path (a): the solver records CHECKPOINTS of its own
trajectory as pure data — a theta copy, the cost, the eval counter and a
per-expiry option-residual RMS vector per accepted step — and the finished
list rides the ``AffineCalibration`` result out of the worker process. Nothing
is fed back into the fit, so tracing can never change a calibrated value; with
``trace_every=None`` (the default) no recorder exists at all and the fit is
byte-identical with zero overhead (the perf rails call the defaults).

ACCEPTED-STEP DEFINITION (documented choice): scipy's ``least_squares`` exposes
no per-iteration callback (portably across the versions in use), so an
"accepted step" is defined as an objective evaluation that sets a NEW BEST
total cost ½‖r‖². Both solvers in play only ever move to iterates that
strictly decrease the cost — TRF accepts a trial step iff it reduces the cost,
and the projected GN line search likewise — so the strictly-improving
subsequence of evaluations coincides with the accepted iterates (plus the seed,
which becomes frame 0). Rejected trial steps never improve the best cost and
are never recorded; the sequence is deterministic for fixed inputs. The hook
lives in the shared ``evaluate`` (memoized: one call per unique iterate), so
the GN path — and its fall-back-to-TRF continuation — is traced by the exact
same mechanism.

Import discipline: consumed by the fit-pool worker, so this module depends on
numpy only — never on volfit.api.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class AffineTraceFrame:
    """One accepted-step checkpoint of the affine LSQ."""

    n_evals: int  # objective evaluations spent when this iterate was accepted
    cost: float  # total LSQ cost ½‖r‖² at the iterate
    theta: np.ndarray  # (n_t, n_x) nodal-variance grid COPY at the iterate
    expiry_rms: np.ndarray  # per-expiry option-residual RMS (weighted price units)


@dataclass(frozen=True)
class AffineTrace:
    """The finished replay: ≤ cap frames, ascending ``n_evals``, the LAST frame
    always the converged surface (theta equals the returned ``surface.theta``)."""

    expiries: list  # tau per ``expiry_rms`` entry (sorted unique option expiries)
    frames: list = field(default_factory=list)  # AffineTraceFrame, ascending n_evals


class TraceRecorder:
    """Collects accepted-step frames during ``calibrate_affine``.

    ``every`` keeps one frame per that many new-best transitions (1 = all);
    ``finish`` appends/overwrites the FINAL frame from the converged iterate and
    uniformly subsamples the interior down to ``cap`` total (final always kept).
    """

    def __init__(
        self,
        every: int,
        cap: int,
        options: list,
        n_opt_rows: int,
        grid_shape: tuple[int, int],
    ) -> None:
        self._every = max(1, int(every))
        self._cap = max(2, int(cap))
        self._shape = grid_shape
        # Per-quote expiry grouping, fixed for the whole fit: the option block is
        # the FIRST len(options) residual rows in quote order (in band mode those
        # are the band violations — the actual fit target; the soft mid anchor
        # rows that follow are excluded).
        self._n_quotes = len(options)
        self._n_opt_rows = n_opt_rows
        taus = np.array([float(o.t) for o in options])
        self.expiries = sorted(set(taus.tolist()))
        self._rows = [np.nonzero(taus == t)[0] for t in self.expiries]
        self._best = np.inf
        self._improved = 0  # new-best transitions seen (for the ``every`` stride)
        self.frames: list[AffineTraceFrame] = []

    def _expiry_rms(self, res: np.ndarray) -> np.ndarray:
        block = res[: self._n_quotes] if self._n_opt_rows else res
        return np.array(
            [
                float(np.sqrt(np.mean(block[idx] ** 2))) if idx.size else 0.0
                for idx in self._rows
            ]
        )

    def _frame(self, theta_flat: np.ndarray, res: np.ndarray, n_evals: int, cost: float):
        return AffineTraceFrame(
            n_evals=int(n_evals),
            cost=float(cost),
            theta=np.array(theta_flat, dtype=float).reshape(self._shape),
            expiry_rms=self._expiry_rms(res),
        )

    def observe(self, theta_flat: np.ndarray, res: np.ndarray, n_evals: int) -> None:
        """Called once per (non-memoized) objective evaluation; records the frame
        iff this iterate sets a new best cost (= an accepted step, see module
        docstring), subject to the ``every`` stride."""
        cost = 0.5 * float(res @ res)
        if not (cost < self._best):
            return
        self._best = cost
        self._improved += 1
        if (self._improved - 1) % self._every == 0:
            self.frames.append(self._frame(theta_flat, res, n_evals, cost))

    def finish(self, theta_flat: np.ndarray, res: np.ndarray, n_evals: int) -> AffineTrace:
        """Seal the trace at the CONVERGED iterate (the solver's returned x).

        The final frame is built explicitly from the returned surface — never
        assumed to be the last new-best eval — so ``frames[-1].theta`` always
        equals the calibrated theta (stall early-stop and best-cost returns
        included). A duplicate of the last recorded frame (same iterate, e.g.
        converged-on-last-step) is replaced, keeping ``n_evals`` strictly
        ascending."""
        final = self._frame(theta_flat, res, n_evals, 0.5 * float(res @ res))
        frames = self.frames
        if frames and frames[-1].n_evals >= final.n_evals:
            frames = frames[:-1]
        if len(frames) + 1 > self._cap:
            # Uniform subsample of the interior, both ends kept, final appended.
            idx = np.unique(
                np.round(np.linspace(0, len(frames) - 1, self._cap - 1)).astype(int)
            )
            frames = [frames[i] for i in idx]
        return AffineTrace(expiries=list(self.expiries), frames=[*frames, final])
