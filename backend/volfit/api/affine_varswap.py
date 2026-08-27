"""Var-swap rows of the LV (affine) surface fit: the MARKET quote rows and the
PRIOR companion row under either carrier (absolute / ATM-spread).

Moved out of volfit.api.affine_fit (2026-08-27) when the prior row gained the
``priorVarSwapMode="atm_spread"`` carrier for the LV surface — the row form
lives in volfit.models.localvol.varswap_rows; this module only resolves the
WEIGHTS (the same conventions as the parametric ``service.varswap_target`` /
``service._prior_varswap``) and builds the ``VarSwapQuote`` objects.

Tolerance conventions (mirroring the option rows ``tol = vega·VOL_TOL/√w``):

* absolute row, TOTAL-variance units: ``ζ = 2 σ_vs t VOL_TOL / √u`` — equating
  the squared weightings of a var-swap vol error and a vega-scaled price error;
* spread row, VOL units: ``ζ_σ = VOL_TOL / √u`` — the residual
  ``√u (Δspread) / VOL_TOL`` stacks on the option rows' ``√w Δσ / VOL_TOL``.

``u`` is the row's LSQ weight (a percent of the expiry's summed quote weights
for market rows; the prior builder's budget × unmet coverage for prior rows).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import numpy as np

from volfit.calib.varswap import VARSWAP_PIN_MULT, varswap_total_variance
from volfit.calib.weights import resolve_weights
from volfit.models.localvol import VarSwapQuote

if TYPE_CHECKING:  # the state type only; keep the import chain light (prior_lv)
    from volfit.api.state import AppState

#: Vol tolerance unit (1 vol point) — the option rows' affine_fit._VOL_TOL.
VOL_TOL = 0.01
_W_FLOOR = 1e-12


def market_varswap_quotes(
    state: "AppState", ticker: str, rows, weight_scheme: str
) -> list[VarSwapQuote]:
    """Active var-swap quotes per expiry as affine VarSwapQuote targets.

    Mirrors the parametric weighting (volfit.api.service.varswap_target): the
    var-swap competes with the expiry's option quotes at ``varSwapWeightPct`` of
    their summed weight. The affine objective measures the var-swap residual in
    TOTAL variance ((z - z_mkt)/zeta), while the option residuals are in
    vega-scaled price ((P - y)/tol) ~ vol error in units of VOL_TOL; equating the
    two squared weightings gives zeta = 2 sigma_vs t VOL_TOL / sqrt(u_vs), with
    u_vs = pct% * sum_i w_i (the same w_i that scale the option tolerances).

    ``varSwapHardPin`` escalates u_vs to VARSWAP_PIN_MULT * sum_w — the same
    stiff-row weight the parametric ``service.varswap_target`` applies — so the
    tol shrinks by the equivalent sqrt factor and the LV surface matches the
    quote to solver tolerance. Market rows only, ALWAYS the absolute carrier
    (a quote is the truth, not a shape); the PRIOR companion rows
    (``prior_varswap_quote``) stay soft.
    """
    options = state.options()
    hard_pin = options.varSwapHardPin
    if not options.varSwapEnabled or (options.varSwapWeightPct <= 0.0 and not hard_pin):
        return []
    quotes: list[VarSwapQuote] = []
    for iso, t, k, w, _, _ in rows:
        session = state.varswap_session_if_exists((ticker, iso))
        if session is None or not session.state.is_active:
            continue
        qw = resolve_weights(weight_scheme, k, w)
        sum_w = float(np.sum(qw)) if qw is not None else float(k.size)
        u_vs = (options.varSwapWeightPct / 100.0) * sum_w
        if hard_pin:
            u_vs = VARSWAP_PIN_MULT * sum_w  # equality-to-solver-tolerance idiom
        if u_vs <= 0.0:
            continue
        sigma_vs = float(session.state.level)
        zeta = 2.0 * sigma_vs * t * VOL_TOL / np.sqrt(u_vs)
        quotes.append(VarSwapQuote(t=t, total_var=sigma_vs * sigma_vs * t, tol=float(zeta)))
    return quotes


def prior_varswap_quote(
    total_var: float, tau: float, weight: float, atm_total_var: float | None = None
) -> VarSwapQuote:
    """The PRIOR var-swap companion row of one expiry (``tau``) at LSQ weight
    ``weight``. ``atm_total_var`` None ⇒ the ABSOLUTE carrier (the historical
    construction, byte-identical: total-variance tol ζ = 2 σ_vs τ VOL_TOL / √u).
    Set (the prior's ATM total variance re-expressed at ``tau``) ⇒ the
    ATM-SPREAD carrier: ``atm_spread = σ_vs − σ_atm`` of the prior and a VOL-unit
    tol ζ_σ = VOL_TOL / √u (volfit.models.localvol.varswap_rows)."""
    sigma_vs = float(np.sqrt(max(total_var, _W_FLOOR) / tau))
    if atm_total_var is None:
        zeta = 2.0 * sigma_vs * tau * VOL_TOL / np.sqrt(weight)
        return VarSwapQuote(t=tau, total_var=float(total_var), tol=float(zeta))
    sigma_atm = float(np.sqrt(max(atm_total_var, _W_FLOOR) / tau))
    return VarSwapQuote(
        t=tau,
        total_var=float(total_var),
        tol=float(VOL_TOL / np.sqrt(weight)),
        atm_spread=float(sigma_vs - sigma_atm),
    )


def prior_varswap_quote_from_smile(
    implied_w: Callable[[np.ndarray], np.ndarray],
    prior_tau: float,
    tau: float,
    weight: float,
    mode: str,
) -> VarSwapQuote:
    """``prior_varswap_quote`` from a (transported) prior smile ``implied_w(k)``
    at the prior's ``prior_tau``: the var-swap level is the log-contract
    replication re-expressed at the node ``tau`` (``w · tau/prior_tau``, as the
    strike-gap anchor always did) and, under ``mode == "atm_spread"``, the ATM
    total variance rides along the same way (service._prior_varswap's rescale —
    it cancels in vol space). Any other ``mode`` ⇒ absolute, byte-identical."""
    w_vs = varswap_total_variance(implied_w) * (tau / prior_tau)
    w_atm = None
    if mode == "atm_spread":
        w_atm = float(
            np.maximum(np.asarray(implied_w(np.array([0.0])), dtype=float), _W_FLOOR)[0]
        ) * (tau / prior_tau)
    return prior_varswap_quote(w_vs, tau, weight, w_atm)
