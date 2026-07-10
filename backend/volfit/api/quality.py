"""Universe fit-quality report behind GET /quality (commercial-MVP dashboard).

Aggregates CACHED calibrations into one publish-readiness screen: per lit
node the calibration-consistent RMS, the Lee wing slopes, the adjacent-expiry
calendar check and staleness; per ticker the pooled surface RMS and the
cached LV (affine) surface health; plus universe headline counts. Also
MEASURES (advisory, never gating) arbitrage in the extrapolated strike region
over the time-value envelope — Notes 09/10's softer-enforcement design,
Phase 1: butterfly g, calendar crossings, and asymptotic wing-slope order.

STRICTLY NO FIT ON READ: records are fetched via the calibrated pointer +
fit cache (never ``fit_or_get``, whose ungated branch bootstraps a fit), the
LV response via the affine pointer + cache, and the filter diagnostics via
the memoized read-only accessor. A never-calibrated node simply reports
``hasFit=False`` — exactly the gated-workflow semantics of the smile viewer.
"""

from __future__ import annotations

import numpy as np

from volfit.api import service
from volfit.api.carry import carry_counts
from volfit.api.data_age import format_age, ticker_ages
from volfit.api.filter_mode import resolve_filter_mode
from volfit.api.schemas_quality import (
    LvQuality,
    QualityNode,
    QualityReport,
    QualitySummary,
    QualityTicker,
)
from volfit.api.state import AppState, FitRecord
from volfit.calib.calendar import calendar_violation
from volfit.calib.rms import rms as rms_of_terms
from volfit.models.diagnostics import extrapolated_arb
from volfit.models.lqd.atm import atm_handles
from volfit.models.lqd.basis import lee_slopes

#: Lee moment bound on the total-variance wing slopes (beta <= 2), with a hair
#: of tolerance so a slope pinned AT the bound (SVI's clamp) is not flagged.
_LEE_BOUND = 2.0
_LEE_TOL = 1e-9
#: Calendar convex-order tolerance — matches the surface-fit acceptance tests.
_CAL_TOL = 1e-6
#: Extrapolated-region tolerances (Notes 09/10 Phase 1 — advisory measurement):
#: g may dip infinitesimally negative from the numeric stencil; the calendar
#: crossing tolerance is 1 vol bp (below any tradable edge).
_EXTRAP_G_TOL = 1e-6
_EXTRAP_CAL_TOL_BP = 1.0
_WING_ORDER_TOL = 1e-9
#: Default per-node RMS publish budget (vol bp).
DEFAULT_RMS_BUDGET_BP = 50.0


def _node_handles(record: FitRecord) -> tuple[float, float, float, float, float]:
    """(atm_vol, skew, lee_left, lee_right, max_iv_error) of the DISPLAYED fit."""
    if record.display is not None:  # non-LQD overlay: numeric handles/Lee
        d = record.display
        return d.handles.atm_vol, d.handles.skew, d.lee_left, d.lee_right, d.max_iv_error
    handles = atm_handles(record.result.slice, record.prepared.tau)
    lee_left, lee_right = lee_slopes(record.result.params)
    return handles.sigma0, handles.skew, lee_left, lee_right, record.result.max_iv_error


def _varswap_quoted(state: AppState, ticker: str, iso: str) -> bool:
    """Whether an active var-swap quote participates in this node's fit."""
    if not state.options().varSwapEnabled:
        return False
    session = state.varswap_session_if_exists((ticker, iso))
    return session is not None and session.state.is_active


def _filter_flags(state: AppState, ticker: str, iso: str, fit_mode: str) -> tuple[bool, bool]:
    """(active, contaminated) from the memoized filter diagnostics; advisory."""
    try:
        from volfit.api import observation_filter

        diag = observation_filter.filter_diagnostics(state, ticker, iso, fit_mode)
        return bool(diag.active), bool(diag.contaminated)
    except Exception:  # the filter must never break a status read
        return False, False


def _no_fit_node(ticker: str, iso: str) -> QualityNode:
    return QualityNode(
        ticker=ticker, expiry=iso, tau=0.0, hasFit=False, stale=False, model="",
        nQuotes=0, rmsBp=0.0, maxIvBp=0.0, atmVol=0.0, skew=0.0,
        leeLeft=0.0, leeRight=0.0, leeOk=True,
        calendarViolation=0.0, calendarOk=True, varSwapQuoted=False,
        filterActive=False, filterContaminated=False,
        ready=False, issues=["no fit"],
    )


def _lv_quality(state: AppState, ticker: str, fit_mode: str) -> LvQuality | None:
    """The ticker's cached LV surface health, or None when never calibrated.

    Read via the affine pointer + cache — NEVER ``affine_payload`` (whose
    ungated branch bootstraps the heavy fit)."""
    from volfit.api import affine_fit
    from volfit.api.schemas_affine import AffineFitRequest

    ptr = state.get_affine_ptr(ticker)
    if ptr is None:
        return None
    hit = affine_fit._cache(state).get(ptr)
    if hit is None:  # pointer outlived its cache entry (defensive)
        return None
    try:
        stale = affine_fit.affine_dirty(state, ticker, AffineFitRequest(fitMode=fit_mode))
    except Exception:
        stale = False
    worst_density = float(min(hit.minDensity)) if hit.minDensity else 0.0
    return LvQuality(
        hasFit=True,
        stale=stale,
        rmsIvErrorBp=hit.rmsIvErrorBp,
        maxIvErrorBp=hit.maxIvErrorBp,
        surfaceRmsBp=hit.surfaceRmsError * 1e4,
        rmsConvergedBp=hit.rmsConvergedBp,
        arbitrageFree=hit.arbitrageFree,
        calendarViolations=hit.calendarViolations,
        worstMinDensity=worst_density,
    )


def _node_row(
    state: AppState,
    ticker: str,
    iso: str,
    fit_mode: str,
    record: FitRecord,
    prev_slice,
    prev_display,
    prev_lee: tuple[float, float] | None,
    rms_budget_bp: float,
    filter_on: bool,
    data_age: tuple[float, bool] | None = None,
) -> tuple[QualityNode, tuple[float, float]]:
    """One fitted node's quality row + its pooled (num, den) RMS terms."""
    ptr = state.get_calibrated_ptr(ticker, iso, fit_mode)
    stale = ptr is not None and ptr[0] != service.fit_key(state, ticker, iso, fit_mode)
    num, den = service._node_rms_terms(state, ticker, iso, record, fit_mode)
    rms_bp = rms_of_terms(num, den) * 1e4
    atm_vol, skew, lee_left, lee_right, max_iv = _node_handles(record)
    lee_ok = max(lee_left, lee_right) <= _LEE_BOUND + _LEE_TOL
    # Calendar convex order vs the previous FITTED expiry, on the LQD backbone
    # (always present, shared quadrature grid). Fits committed at different
    # epochs can genuinely cross — exactly what this screen must surface.
    violation = 0.0
    if prev_slice is not None:
        try:
            violation = float(calendar_violation(prev_slice, record.result.slice))
        except Exception:
            violation = 0.0
    cal_ok = violation <= _CAL_TOL

    # Extrapolated-region arb (Notes 09/10 Phase 1): measured on the DISPLAYED
    # slice — the published wing — over the time-value envelope; the calendar
    # crossing compares displayed vs previous displayed (same published family).
    # ADVISORY: reported, never gates readiness (measure first, enforce later).
    disp = record.display.slice if record.display is not None else record.result.slice
    extrap_min_g = extrap_cal = None
    extrap_ok = extrap_cal_ok = True
    kq = record.prepared.k
    if kq.size:
        try:
            ex = extrapolated_arb(
                disp, float(kq.min()), float(kq.max()), float(record.prepared.tau),
                prev_slice=prev_display,
            )
            extrap_min_g, extrap_cal = ex.min_g, ex.cal_bp
            extrap_ok = extrap_min_g is None or extrap_min_g >= -_EXTRAP_G_TOL
            extrap_cal_ok = extrap_cal is None or extrap_cal <= _EXTRAP_CAL_TOL_BP
        except Exception:  # the measurement must never break a status read
            pass
    wing_order: bool | None = None
    if prev_lee is not None:
        wing_order = (
            lee_left >= prev_lee[0] - _WING_ORDER_TOL
            and lee_right >= prev_lee[1] - _WING_ORDER_TOL
        )
    f_active, f_contaminated = (
        _filter_flags(state, ticker, iso, fit_mode) if filter_on else (False, False)
    )

    issues: list[str] = []
    if stale:
        issues.append("stale")
    if rms_bp > rms_budget_bp:
        issues.append(f"RMS {rms_bp:.0f}bp > budget {rms_budget_bp:.0f}bp")
    if not lee_ok:
        issues.append("Lee wing slope > 2")
    if not cal_ok:
        issues.append("calendar arb vs previous expiry")
    # Data-age staleness (volfit.api.data_age): red-stale live data fails
    # readiness — a fit can be perfect and still be a fit of yesterday's book.
    age_min = data_age[0] if data_age is not None else None
    if data_age is not None and data_age[1]:
        issues.append(f"stale data ({format_age(data_age[0])} old)")
    node = QualityNode(
        ticker=ticker,
        expiry=iso,
        tau=float(record.prepared.tau),
        hasFit=True,
        stale=stale,
        model=record.display.model if record.display is not None else "lqd",
        nQuotes=int(record.prepared.k.size),
        rmsBp=rms_bp,
        maxIvBp=max_iv * 1e4,
        atmVol=atm_vol,
        skew=skew,
        leeLeft=lee_left,
        leeRight=lee_right,
        leeOk=lee_ok,
        calendarViolation=violation,
        calendarOk=cal_ok,
        extrapMinG=extrap_min_g,
        extrapOk=extrap_ok,
        extrapCalBp=extrap_cal,
        extrapCalOk=extrap_cal_ok,
        wingOrderOk=wing_order,
        varSwapQuoted=_varswap_quoted(state, ticker, iso),
        filterActive=f_active,
        filterContaminated=f_contaminated,  # advisory — never blocks readiness
        dataAgeMin=age_min,
        screened=_screened_counts(record.prepared),
        vegaFloored=int(getattr(record.prepared, "vega_floored", 0)),
        ready=not issues,
        issues=issues,
    )
    return node, (num, den)


def _screened_counts(prepared) -> dict[str, int]:
    """Quarantined-quote counts by reason (R1 item 6 — advisory observability;
    the drops themselves predate the record and never gate readiness)."""
    counts: dict[str, int] = {}
    for s in getattr(prepared, "screened", ()):
        counts[s.reason] = counts.get(s.reason, 0) + 1
    return counts


def build_quality_report(
    state: AppState,
    fit_mode: str | None = None,
    rms_budget_bp: float = DEFAULT_RMS_BUDGET_BP,
) -> QualityReport:
    """Assemble the universe quality report from cached calibrations only."""
    mode = fit_mode if fit_mode is not None else state.last_fit_mode
    opts = state.options()
    filter_on = resolve_filter_mode(opts).enabled
    # Loaded live-chain ages (volfit.api.data_age): {} when not live / nothing
    # fetched / exact-price chains — every node then reports dataAgeMin=None.
    ages = ticker_ages(state)
    nodes: list[QualityNode] = []
    tickers: list[QualityTicker] = []
    dark_nodes = 0

    for ticker in state.active_tickers():
        age_min = ages.get(ticker)
        data_age = (age_min, age_min >= opts.dataAgeRedMin) if age_min is not None else None
        try:
            forwards = sorted(state.forwards(ticker))
        except Exception:
            continue  # unfetched/unavailable ticker (gated, pre-Fetch): not shown
        rows: list[QualityNode] = []
        num = den = 0.0
        prev_slice = None
        prev_display = None
        prev_lee: tuple[float, float] | None = None
        for expiry in forwards:
            iso = expiry.isoformat()
            if not state.node_lit(ticker, iso):
                dark_nodes += 1  # dark = graph extrapolation target, not fit quality
                continue
            ptr = state.get_calibrated_ptr(ticker, iso, mode)
            record = state.get_fit(ptr[0]) if ptr is not None else None
            if record is None:
                rows.append(_no_fit_node(ticker, iso))
                continue  # calendar chain: compare across the gap, keep prev_slice
            node, (n, d) = _node_row(
                state, ticker, iso, mode, record, prev_slice, prev_display, prev_lee,
                rms_budget_bp, filter_on, data_age,
            )
            rows.append(node)
            num += n
            den += d
            prev_slice = record.result.slice
            prev_display = (
                record.display.slice if record.display is not None else record.result.slice
            )
            prev_lee = (node.leeLeft, node.leeRight)
        if not rows:
            continue
        fitted = [r for r in rows if r.hasFit]
        carry_id, carry_unid = carry_counts(state, ticker)
        tickers.append(
            QualityTicker(
                ticker=ticker,
                nodes=len(rows),
                fitted=len(fitted),
                stale=sum(1 for r in fitted if r.stale),
                surfaceRmsBp=rms_of_terms(num, den) * 1e4,
                worstNodeRmsBp=max((r.rmsBp for r in fitted), default=0.0),
                arbFlags=sum(1 for r in fitted if not (r.leeOk and r.calendarOk)),
                extrapFlags=sum(1 for r in fitted if not (r.extrapOk and r.extrapCalOk)),
                dataAgeMin=age_min,
                carryIdentified=carry_id,
                carryUnidentified=carry_unid,
                ready=sum(1 for r in rows if r.ready),
                lv=_lv_quality(state, ticker, mode),
            )
        )
        nodes.extend(rows)

    fitted = [r for r in nodes if r.hasFit]
    rms_values = [r.rmsBp for r in fitted]
    lv_rollups = [t.lv for t in tickers if t.lv is not None]
    summary = QualitySummary(
        tickers=len(tickers),
        litNodes=len(nodes),
        darkNodes=dark_nodes,
        fitted=len(fitted),
        stale=sum(1 for r in fitted if r.stale),
        noFit=len(nodes) - len(fitted),
        readyNodes=sum(1 for r in nodes if r.ready),
        arbFlags=sum(t.arbFlags for t in tickers),
        extrapFlags=sum(t.extrapFlags for t in tickers),
        medianRmsBp=float(np.median(rms_values)) if rms_values else 0.0,
        worstRmsBp=max(rms_values, default=0.0),
        filterMode=opts.observationFilterMode,
        priorMode=opts.priorPersistenceMode,
        lvTickers=len(lv_rollups),
        lvArbFree=sum(1 for lv in lv_rollups if lv.arbitrageFree),
        staleDataTickers=sum(1 for a in ages.values() if a >= opts.dataAgeRedMin),
    )
    return QualityReport(
        fitMode=mode,
        rmsBudgetBp=rms_budget_bp,
        summary=summary,
        tickers=tickers,
        nodes=nodes,
    )
