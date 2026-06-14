"""Fast spot-move transport of a calibrated implied-vol smile / surface / grid.

Implements the no-recalibration transforms of
``Docs/spot_move_vol_surface_note_updated.tex``: when the spot (hence every
forward) moves, a *calibrated* smile is refreshed analytically rather than
refitted. The note's transforms are all expressed on total variance in the NEW
log-forward moneyness ``k = log(K / F_T^1)``, with ``h_T = log(F_T^1 / F_T^0)``:

  * **horizontal SSR transport** (the recommended production rule)

        w~_1^R(T, k) = w_0(T, k + R h_T)                                (note eq SSR)

    which recovers sticky-moneyness exactly at ``R = 0`` (the smile rides with
    the forward), sticky-strike exactly at ``R = 1`` (vol fixed at a fixed
    strike), and the local-vol "double-skew" ATM response at ``R = 2``;

  * **exact sticky-local-vol** (Hagan local-vol expansion, used for the
    ``sticky_local_vol`` / ``sticky_local_vol_grid`` regimes instead of the
    ``R = 2`` linearization)

        w_1^LV(T, k) = w_0(T, ell_T(k, h_T)),
        ell_T(k, h) = log( e^h (e^k + 1) - 1 ) = log( e^{h+k} + (e^h - 1) ),

    with ``ell_T(0, h) ~ 2h`` near the money;

  * an **optional finite-move ATM re-anchor** that forces an exact linear SSR
    target ``sigma_atm -> sigma_0 + R kappa_T h_T`` even for large moves
    (note eq with w_ATM^star); off by default since the plain transport already
    recovers the canonical regimes;

  * the **local-vol-grid node rule**

        K_i^1(t) = K_i^0(t) e^{(1 - R/2) h_t}     <=>     x_i^1 = x_i^0 - (R/2) h_t

    (log-strike barycenter): ``R = 0`` moves the grid fully with moneyness,
    ``R = 1`` is the half-grid sticky-strike proxy, ``R = 2`` leaves the grid
    fixed in absolute strike (``volfit.api.localvol`` reprices it exactly).

All entry points are pure NumPy and take an anchor ``w_0`` callable (any
``SmileModel.implied_w``), so the same engine drives the parametric slices
(``volfit.api.service``) and the affine local-vol surface (``volfit.api.affine_fit``).
``kappa_T`` is the ATM skew d sigma/dk(0); ``sigma_0`` the anchor ATM vol; ``tau``
the (event-weighted) variance years the smile is quoted in.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from volfit.dynamics.ssr import Regime, ssr_of_regime

#: Regimes whose implied transform uses the exact sticky-local-vol ell_T
#: displacement rather than the SSR-linear k + R h. Both pin R = 2; the grid
#: stays fixed in absolute strike for them (beta = 1 - R/2 = 0).
EXACT_LV_REGIMES = frozenset({Regime.STICKY_LOCAL_VOL, Regime.STICKY_LOCAL_VOL_GRID})


def is_exact_lv(regime: Regime | str | float) -> bool:
    """Whether a regime uses the exact sticky-local-vol ell_T displacement.

    A numeric custom SSR is always treated as the SSR-linear transport, never
    the exact local-vol form.
    """
    if isinstance(regime, (int, float)) and not isinstance(regime, bool):
        return False
    try:
        return Regime(regime) in EXACT_LV_REGIMES
    except (ValueError, KeyError):
        return False


def ell_T(k: np.ndarray | float, h: float) -> np.ndarray:
    """Exact sticky-local-vol strike displacement ``ell_T(k, h)`` (note eq ell).

    ``log(e^h (e^k + 1) - 1) = log(e^{h+k} + (e^h - 1))``; the ``expm1`` form is
    accurate for the small ``h`` of a single spot move. Reduces to ``k`` at
    ``h = 0`` and to ``k + (1 + e^{-k}) h + O(h^2)`` for small moves, so
    ``ell_T(0, h) ~ 2h``.
    """
    k = np.asarray(k, dtype=float)
    return np.log(np.exp(h + k) + np.expm1(h))


def transported_w(
    w0: Callable[[np.ndarray], np.ndarray],
    k: np.ndarray | float,
    h: float,
    regime: Regime | str | float,
    *,
    sigma0: float = 0.0,
    kappa: float = 0.0,
    tau: float = 1.0,
    atm_anchor: bool = False,
) -> np.ndarray:
    """Total variance after a spot move, at NEW log-moneyness ``k``.

    ``w0`` is the anchor's ``implied_w`` (old log-moneyness); ``h`` the
    per-maturity forward log-ratio ``h_T``; ``regime`` a named regime or numeric
    SSR. The exact local-vol regimes use ``ell_T``; everything else uses the
    SSR-linear transport ``w0(k + R h)``. With ``atm_anchor`` the ATM total
    variance is re-pinned to ``tau (sigma0 + R kappa h)^2`` so the ATM vol moves
    exactly linearly in ``R`` for finite moves (the rest of the curve shifted by
    the same additive constant).
    """
    k = np.asarray(k, dtype=float)
    if h == 0.0:
        return np.asarray(w0(k), dtype=float)
    if is_exact_lv(regime):
        return np.asarray(w0(ell_T(k, h)), dtype=float)
    r = ssr_of_regime(regime)
    shifted = np.asarray(w0(k + r * h), dtype=float)
    if not atm_anchor:
        return shifted
    sigma_star = sigma0 + r * kappa * h
    w_atm_star = tau * sigma_star * sigma_star
    w_at_offset = float(np.asarray(w0(np.array([r * h]))).reshape(-1)[0])
    return shifted + (w_atm_star - w_at_offset)


class TransportedSlice:
    """A calibrated anchor smile after a spot move, as a ``SmileModel``.

    Wraps the anchor's ``implied_w`` (old log-moneyness) and exposes
    ``implied_w(k)`` / ``implied_vol(k, t)`` in the NEW log-moneyness ``k`` per
    the note's transport for ``regime`` and forward log-ratio ``h``. Every
    smile-derived view (density, var-swap replication, Dupire extraction, term
    ATM handles) therefore moves consistently and without recalibration just by
    reading this slice.
    """

    def __init__(
        self,
        base: object,
        h: float,
        regime: Regime | str | float,
        *,
        sigma0: float = 0.0,
        kappa: float = 0.0,
        tau: float = 1.0,
        atm_anchor: bool = False,
    ) -> None:
        self._base = base  # SmileModel: only .implied_w is used
        self._h = float(h)
        self._regime = regime
        self._sigma0 = float(sigma0)
        self._kappa = float(kappa)
        self._tau = float(tau)
        self._anchor = bool(atm_anchor)

    def implied_w(self, k: np.ndarray | float) -> np.ndarray:
        return transported_w(
            self._base.implied_w,
            k,
            self._h,
            self._regime,
            sigma0=self._sigma0,
            kappa=self._kappa,
            tau=self._tau,
            atm_anchor=self._anchor,
        )

    def implied_vol(self, k: np.ndarray | float, t: float) -> np.ndarray:
        return np.sqrt(np.maximum(self.implied_w(k), 1e-12) / t)


def beta_of(regime: Regime | str | float) -> float:
    """Grid barycenter weight ``beta_t = 1 - R/2`` (note eq beta).

    ``beta = 1`` (R=0) moves the grid fully with the forward, ``beta = 1/2``
    (R=1) is the half-grid sticky-strike proxy, ``beta = 0`` (R=2) keeps the
    grid fixed in absolute strike.
    """
    return 1.0 - 0.5 * ssr_of_regime(regime)


def transport_grid_logk(grid_k: np.ndarray, h: float, regime: Regime | str | float) -> np.ndarray:
    """New normalized log-strike nodes after a spot move (note eq grid).

    A grid stored in normalized log-moneyness ``x = log(K / F_t)`` relabels to
    ``x_i^1 = x_i^0 - (R/2) h_t`` (equivalently ``K_i^1 = K_i^0 e^{(1-R/2) h_t}``);
    the nodal local vols are unchanged, only their coordinates move.
    """
    return np.asarray(grid_k, dtype=float) - 0.5 * ssr_of_regime(regime) * float(h)


def transport_grid_strikes(grid_x: np.ndarray, h: float, regime: Regime | str | float) -> np.ndarray:
    """New normalized strikes ``x = K / F`` after a spot move.

    The linear-strike analogue of ``transport_grid_logk``: ``x_i^1 =
    x_i^0 e^{-(R/2) h_t}`` (so that ``K_i / F`` relabels while the absolute grid
    follows ``K_i^1 = K_i^0 e^{(1-R/2) h_t}``).
    """
    return np.asarray(grid_x, dtype=float) * np.exp(-0.5 * ssr_of_regime(regime) * float(h))
