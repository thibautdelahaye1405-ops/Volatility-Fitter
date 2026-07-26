"""Committee revision R3: the structural SVI chart (β_L, β_R, k*, w*, κ*)
and the belly-repair refit (the R2 acceptance rule's leg 2).

The structural chart parameterizes the slice by the quantities the
guarantees are about, lifted so every finite optimizer vector is strictly
positive-floor and strictly Lee-clean — the penalty rows become inert and
the trial-w clip never fires. Opt-in (FitSettings.sviChart, default "raw"
until the benchmark adjudication — the Note 01 R1 precedent); these locks
pin the chart algebra, the clean-fit equivalence, the structural guarantees,
and the certified repair path on Axel Vogt's slice.
"""

from __future__ import annotations

import numpy as np
import pytest

from volfit.calib.fit_task import OverlaySettings
from volfit.models.diagnostics import belly_certificate
from volfit.models.display import build_display_fit
from volfit.models.svi_jw.calibrate import _LEE_SLOPE_MAX, calibrate_svi
from volfit.models.svi_jw.structural import pack_structural, unpack_structural
from volfit.models.svi_jw.svi import RawSVI, durrleman_g_raw

#: The note's laboratory slice (clean, well inside every screen).
LAB = RawSVI(a=0.010625, b=0.07289, rho=-0.5, m=0.05831, sigma=0.10100)
#: Axel Vogt's classical slice: wing screens pass, belly density negative.
VOGT = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
#: The R1 boundary slice: both wings exactly at Lee's bound.
BOUNDARY = RawSVI(a=0.04, b=2.0, rho=0.0, m=0.0, sigma=0.2)


def _settings(**over) -> OverlaySettings:
    base = dict(
        sviPenaltyWeight=1e3, leeSlopeMax=_LEE_SLOPE_MAX, midAnchorWeight=0.05,
        nCores=2, sigmoidRidge=1e-2,
    )
    base.update(over)
    return OverlaySettings(**base)


def test_structural_is_the_ratified_default():
    """The benchmark adjudication (FINDINGS_svi_chart.md, ratified
    2026-07-26): sviChart defaults to the structural chart everywhere a
    default is declared; raw stays available as explicit configuration."""
    from volfit.api.schemas import FitSettings

    assert FitSettings().sviChart == "structural"


def test_chart_round_trip_and_identities():
    """pack ∘ unpack is the identity, and the chart's coordinates ARE the
    guaranteed quantities: w* equals the slice's minimum total variance and
    the wings live strictly inside (0, cap)."""
    rng = np.random.default_rng(7)
    for _ in range(25):
        theta = rng.normal(scale=1.5, size=5)
        raw = unpack_structural(theta, _LEE_SLOPE_MAX)
        # Structural guarantees at ANY finite theta.
        w_min = raw.a + raw.b * raw.sigma * np.sqrt(1.0 - raw.rho**2)
        assert w_min > 0.0
        assert raw.b * (1.0 + abs(raw.rho)) < _LEE_SLOPE_MAX
        assert raw.sigma > 0.0 and raw.b > 0.0 and abs(raw.rho) < 1.0
        # w* is exactly the total variance AT the vertex k* = m − sρ/√(1−ρ²),
        # and no grid point anywhere dips below it.
        k_star = raw.m - raw.sigma * raw.rho / np.sqrt(1.0 - raw.rho**2)
        assert float(raw.total_variance(k_star)) == pytest.approx(w_min, rel=1e-9)
        k = np.linspace(raw.m - 3.0, raw.m + 3.0, 2001)
        assert float(raw.total_variance(k).min()) >= w_min - 1e-12
        # Round trip back through the pack.
        back = unpack_structural(pack_structural(raw, _LEE_SLOPE_MAX), _LEE_SLOPE_MAX)
        for f in ("a", "b", "rho", "m", "sigma"):
            assert getattr(back, f) == pytest.approx(getattr(raw, f), rel=1e-9, abs=1e-12)
    # Saturation lock (round-1 sweep bug): an LM trial ANYWHERE in R^5 —
    # including exp/logistic under/overflow territory — must map to a finite
    # admissible slice, never a ZeroDivisionError from a lift hitting 0/inf.
    for extreme in (1e6, -1e6):
        raw = unpack_structural(np.full(5, extreme), _LEE_SLOPE_MAX)
        for f in ("a", "b", "rho", "m", "sigma"):
            assert np.isfinite(getattr(raw, f))
        assert raw.sigma > 0.0 and raw.b > 0.0 and abs(raw.rho) < 1.0


def test_asymmetric_wing_saturation_stays_admissible():
    """Jacobian-lock discovery (2026-07-26): ONE wing saturated against an
    O(1) other rounds the rho quotient to an exact ±1.0 in float64 — the old
    1 − rho² then collapsed to 0 (sigma = 0, breaking the chart's σ > 0, and
    m = k* + 0·(1/0) = NaN). The product identity 4·β_L·β_R/S² keeps every
    finite theta admissible; the rho FIELD stays strictly interior."""
    for theta in (
        np.array([-200.0, 0.3, 0.1, -0.5, 0.0]),
        np.array([0.3, -200.0, -0.1, 0.5, 3.0]),
        np.array([-85.0, 40.0, 0.0, 0.0, -40.0]),
    ):
        raw = unpack_structural(theta, _LEE_SLOPE_MAX)
        for f in ("a", "b", "rho", "m", "sigma"):
            assert np.isfinite(getattr(raw, f))
        assert raw.sigma > 0.0 and raw.b > 0.0 and abs(raw.rho) < 1.0
        assert raw.b * (1.0 + abs(raw.rho)) < _LEE_SLOPE_MAX


def test_charts_agree_on_clean_quotes():
    """Chart equivalence (the Note 01 R1 lock pattern): on clean quotes the
    optimum is chart-independent — both fits reproduce the same smile to
    solver tolerance."""
    t = 0.5
    k = np.linspace(-0.35, 0.30, 25)
    w = LAB.total_variance(k)
    raw_fit = calibrate_svi(k, w, t)
    struct_fit = calibrate_svi(k, w, t, chart="structural")
    iv_raw = raw_fit.raw.implied_vol(k, t)
    iv_struct = struct_fit.raw.implied_vol(k, t)
    # Worst disagreement in vol bp between the two charts' fitted smiles.
    assert float(np.max(np.abs(iv_struct - iv_raw))) * 1e4 < 0.01
    assert struct_fit.max_iv_error * 1e4 < 0.01  # and both nail the quotes


def test_structural_chart_is_fenced_without_penalties():
    """Quotes pulling toward beta = 2: the structural fit lands strictly
    inside the cap with the penalty rows EXACTLY zero — the fence is the
    chart, not the objective."""
    t = 0.25
    k = np.linspace(-1.5, 1.5, 25)
    w = BOUNDARY.total_variance(k)
    fit = calibrate_svi(k, w, t, chart="structural")
    wing = fit.raw.b * (1.0 + abs(fit.raw.rho))
    assert wing < _LEE_SLOPE_MAX  # strictly inside — the lift cannot touch it
    min_var = fit.raw.a + fit.raw.b * fit.raw.sigma * np.sqrt(1.0 - fit.raw.rho**2)
    assert min_var > 0.0
    # The two penalty rows are structurally zero at the optimum.
    from volfit.models.svi_jw.calibrate import _penalties

    assert np.all(_penalties(fit.raw, 1e3, _LEE_SLOPE_MAX) == 0.0)
    # And the fitted smile matches the raw-chart fit of the same quotes.
    raw_fit = calibrate_svi(k, w, t)
    iv_gap = np.abs(fit.raw.implied_vol(k, t) - raw_fit.raw.implied_vol(k, t))
    assert float(np.max(iv_gap)) * 1e4 < 1.0  # both fenced at the buffer


def test_vogt_quotes_are_repaired_and_certified():
    """The acceptance rule's leg 2, end to end: quotes sampled FROM Vogt's
    slice reproduce its negative belly (SVI can represent it exactly);
    the display path detects the failed certificate, refits with the belly
    hinge, and returns a CERTIFIED repair at modest quote cost."""
    t = 0.25
    k = np.linspace(-0.6, 1.2, 31)
    w = VOGT.total_variance(k)

    # Without repair: the fit reproduces the arbitrage (certificate fails).
    unrepaired = build_display_fit(
        "svi", k, w, t, None, _settings(bellyRepair=False)
    )
    assert unrepaired is not None and not unrepaired.belly_repaired
    cert = belly_certificate(unrepaired.slice, float(k.min()), float(k.max()))
    assert cert is not None and not cert.certified

    # With repair (the default): certified, flagged, and still a good fit.
    repaired = build_display_fit("svi", k, w, t, None, _settings())
    assert repaired is not None and repaired.belly_repaired
    re_cert = belly_certificate(repaired.slice, float(k.min()), float(k.max()))
    assert re_cert is not None and re_cert.certified
    assert min(durrleman_g_raw(repaired.slice, np.linspace(k.min(), k.max(), 801))) >= -1e-4
    # The repair trades quote fidelity for a clean density. Vogt's belly is
    # PATHOLOGICALLY deep (g ~ -0.033 over a wide region), so its nearest
    # certified slice is genuinely far — the lock is that the cost is bounded
    # (~460bp worst quote on ~50-vol quotes), not exploding.
    assert repaired.max_iv_error * 1e4 < 600.0
    # A clean slice never triggers the repair path (byte-identical route).
    k2 = np.linspace(-0.35, 0.30, 25)
    clean = build_display_fit("svi", k2, LAB.total_variance(k2), 0.5, None, _settings())
    assert clean is not None and not clean.belly_repaired
