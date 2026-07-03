"""Observation Kalman filter — the numerical core (Note 15, Docs/kalman_filtering.tex).

A per-node temporal state estimator over the smile handles (ATM vol, ATM skew,
ATM curvature). The prediction is the SSR-transported previous filtered state
plus process noise (note eq. Q); the measurement is a data-only fit's handles
with an explicit covariance (built in Phase 2); the update is the covariance-
form Kalman step in Joseph form (note eq. kalman, Appendix C).

This module is deliberately pure: numpy only, no app state, no provider calls,
no calibration side effects. The app layer (volfit.api.observation_filter)
owns node keys, transport, storage and reset policy; the measurement builders
own z/R. Distinct from prior persistence (volfit.calib.prior/operators): the
Kalman prior carries a COVARIANCE and is always on at that weight; persistence
carries a GAP gate and turns off where data speaks (note §2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Canonical handle order, shared with the graph layer (graph/precision.py)
#: and api/filter_mode.FILTER_HANDLES.
HANDLE_NAMES: tuple[str, ...] = ("ATM", "skew", "curvature")

#: Typical per-handle one-day move scales (ATM vol, skew, curvature) — the same
#: units convention as the graph layer's move scales (Note 14 §5). Used to give
#: the dimensionless transport-noise knob a per-handle magnitude.
HANDLE_MOVE_SCALES: tuple[float, ...] = (0.03, 0.05, 0.5)

#: Cap on the residual-inflation factor rho (note eq. resid-inflation) so one
#: broken chain cannot poison the state during the pilot (note App. A).
RESID_INFLATION_CAP = 25.0

#: Base jitter for the whitening Cholesky (note App. C: "adding jitter is a
#: diagnostic event, not a silent repair" — callers must surface it).
CHOL_JITTER = 1e-12


# ------------------------------------------------------------------ containers
@dataclass(frozen=True)
class FilterState:
    """Posterior handle law of one node, persisted between snapshots (note §7.1).

    ``timestamp`` is the SNAPSHOT epoch (seconds), never wall clock; the node
    key / provenance semantics live in the app layer."""

    node_key: tuple
    handle_names: tuple[str, ...]
    mean: np.ndarray  # m^+
    cov: np.ndarray  # P^+
    timestamp: float
    provenance: str  # "seed:<source>" on (re)seed, "update" after a Kalman step
    reset_reason: str | None = None  # why the state was (re)seeded, else None


@dataclass(frozen=True)
class FilterPrediction:
    """Transported prediction law (m^-, P^-) with its process-noise audit."""

    mean: np.ndarray  # m^- (handles re-extracted AFTER transport, note §5: A_t = I)
    cov: np.ndarray  # P^- = P^+ + Q_t
    transport_distance: float  # |log(F_now / F_prev)|
    q_breakdown: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass(frozen=True)
class FilterMeasurement:
    """Noisy handle observation (z, R) extracted from prepared quotes (note §4).

    ``breakdown`` audits how R was built (route, rms, chi2, rho, quote counts);
    ``contaminated`` flags a z taken from a persistence-anchored fit (§5.1)."""

    handles: np.ndarray  # z
    cov: np.ndarray  # R (after residual inflation)
    breakdown: dict[str, float] = field(default_factory=dict)
    contaminated: bool = False


@dataclass(frozen=True)
class FilterUpdate:
    """One Kalman step: everything the note's invariant 5 says must be reported."""

    innovation: np.ndarray  # z - H m^-
    innovation_cov: np.ndarray  # S
    gain: np.ndarray  # K (after the pilot cap)
    mean: np.ndarray  # m^+
    cov: np.ndarray  # P^+ (Joseph form)
    jitter: float = 0.0  # whitening jitter actually added (diagnostic, usually 0)


# ---------------------------------------------------------------- Kalman step
def kalman_update(
    mean_pred: np.ndarray,
    cov_pred: np.ndarray,
    obs: np.ndarray,
    obs_cov: np.ndarray,
    H: np.ndarray | None = None,
    max_gain: float = 1.0,
) -> FilterUpdate:
    """Covariance-form update with Joseph posterior covariance (note eq. kalman).

    The Joseph form ``(I-KH) P (I-KH)^T + K R K^T`` preserves symmetry/PSD for
    ANY gain, which is what makes the ``max_gain`` pilot cap safe: the capped K
    is still a valid (suboptimal) linear gain. The cap scales each row of K so
    no handle's own-gain ``diag(K H)`` exceeds ``max_gain``; at the default 1.0
    it never binds (own-gains are in (0, 1) by construction).
    """
    m = np.asarray(mean_pred, dtype=float)
    P = np.asarray(cov_pred, dtype=float)
    z = np.asarray(obs, dtype=float)
    R = np.asarray(obs_cov, dtype=float)
    H = np.eye(m.size) if H is None else np.asarray(H, dtype=float)
    # Joseph is robust enough to swallow garbage inputs, so validate them here
    # (the graph layer's "precisions must be strictly positive" convention).
    if np.any(np.linalg.eigvalsh(R) < 0):
        raise ValueError("measurement covariance must be PSD")

    innovation = z - H @ m
    S = H @ P @ H.T + R
    K = np.linalg.solve(S.T, (P @ H.T).T).T

    if max_gain < 1.0:
        own = np.abs(np.diag(K @ H))
        scale = np.minimum(1.0, max_gain / np.maximum(own, 1e-300))
        K = K * scale[:, None]

    out_mean = m + K @ innovation
    i_kh = np.eye(m.size) - K @ H
    out_cov = i_kh @ P @ i_kh.T + K @ R @ K.T
    out_cov = 0.5 * (out_cov + out_cov.T)
    if np.any(np.linalg.eigvalsh(out_cov) < -1e-12):
        raise FloatingPointError("posterior covariance lost PSD")
    return FilterUpdate(
        innovation=innovation, innovation_cov=S, gain=K, mean=out_mean, cov=out_cov
    )


# ------------------------------------------------------------- process noise
def process_noise(
    dt_days: float,
    transport_h: float,
    *,
    vol_bp_sqrt_day: float = 10.0,
    skew_sqrt_day: float = 0.02,
    curv_sqrt_day: float = 0.05,
    transport_scale: float = 0.10,
    event_var: np.ndarray | float = 0.0,
    source_var: np.ndarray | float = 0.0,
    model_var: np.ndarray | float = 0.0,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Diagonal process-noise VARIANCES per handle (note eq. Q).

    Q = Q_clock(dt) + Q_spot(|h|) + Q_event + Q_source + Q_model, with the
    sqrt-time clock baseline (std = q_h * sqrt(dt)) and a spot-transport term
    whose std is ``transport_scale * |h|`` in each handle's typical move scale
    (HANDLE_MOVE_SCALES). Event/source/model widenings are pre-computed extra
    variances supplied by the app layer (per-handle or scalar); zero when the
    prediction crosses no event / source / model boundary.

    Returns the (3,) total variance diagonal plus the per-component breakdown
    (each a (3,) variance vector) for the diagnostics payload.
    """
    dt = max(float(dt_days), 0.0)
    clock_std = np.array(
        [vol_bp_sqrt_day * 1e-4, skew_sqrt_day, curv_sqrt_day], dtype=float
    )
    breakdown = {
        "clock": clock_std**2 * dt,
        "spot": (transport_scale * abs(float(transport_h)) * np.asarray(
            HANDLE_MOVE_SCALES, dtype=float
        ))
        ** 2,
        "event": np.broadcast_to(np.asarray(event_var, dtype=float), (3,)).copy(),
        "source": np.broadcast_to(np.asarray(source_var, dtype=float), (3,)).copy(),
        "model": np.broadcast_to(np.asarray(model_var, dtype=float), (3,)).copy(),
    }
    total = np.sum(list(breakdown.values()), axis=0)
    return total, breakdown


def predict(
    transported_mean: np.ndarray,
    prev_cov: np.ndarray,
    q_diag: np.ndarray,
    transport_distance: float = 0.0,
    q_breakdown: dict[str, np.ndarray] | None = None,
) -> FilterPrediction:
    """Prediction law from the transported previous posterior (note eq. transport).

    v1 uses A_t = I: the handle state is RE-EXTRACTED from the transported
    smile (the app layer transports the backbone under the SSR regime and reads
    handles off it), so the transport Jacobian is deferred; the uncertainty
    growth is carried entirely by Q."""
    mean = np.asarray(transported_mean, dtype=float)
    cov = np.asarray(prev_cov, dtype=float) + np.diag(np.asarray(q_diag, dtype=float))
    return FilterPrediction(
        mean=mean,
        cov=cov,
        transport_distance=float(transport_distance),
        q_breakdown=dict(q_breakdown or {}),
    )


# ----------------------------------------------------------------- reset rule
def should_reset(
    dt_hours: float,
    reset_hours: float,
    *,
    source_changed: bool = False,
    as_of_changed: bool = False,
    fit_mode_changed: bool = False,
    quotes_edited: bool = False,
) -> str | None:
    """Reset-vs-predict decision (note §7.2): the reason string, or None.

    Ordered by severity — a source switch dominates everything (a live stream
    and a prior-close snapshot are not the same stochastic clock, note §5);
    a calendar gap beyond ``reset_hours`` means predicting is worse than
    reseeding from the transported prior."""
    if source_changed:
        return "source_changed"
    if as_of_changed:
        return "as_of_changed"
    if fit_mode_changed:
        return "fit_mode_changed"
    if quotes_edited:
        return "quotes_edited"
    if dt_hours > reset_hours:
        return "stale"
    return None


# -------------------------------------------------- active-MAP residual rows
def prediction_prior_residual(
    model_handles: np.ndarray,
    mean_pred: np.ndarray,
    cov_pred: np.ndarray,
) -> tuple[np.ndarray, float]:
    """Whitened residual rows for the one-stage MAP objective (note eq. active-map).

    Returns ``L^{-1} (H(theta) - m^-)`` with ``L = chol(P^-)`` — one row per
    handle, ready to stack onto the quote-loss residuals — plus the jitter that
    was needed to make the Cholesky succeed (0.0 normally; a nonzero value is a
    diagnostic event the caller must report, note App. C)."""
    cov = np.asarray(cov_pred, dtype=float)
    diff = np.asarray(model_handles, dtype=float) - np.asarray(mean_pred, dtype=float)
    jitter = 0.0
    for _ in range(8):
        try:
            chol = np.linalg.cholesky(cov + jitter * np.eye(cov.shape[0]))
            return np.linalg.solve(chol, diff), jitter
        except np.linalg.LinAlgError:
            jitter = CHOL_JITTER if jitter == 0.0 else jitter * 100.0
    raise FloatingPointError("prediction covariance is not positive definite")
