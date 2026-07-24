"""Committee revision R2 (Note 02 review): the belly butterfly certificate
and the publish acceptance rule — an uncertified slice cannot become a mark.

The cheap screens fence the wings (floor + strict Lee cap, R1); the belly is
where they cannot certify anything — Axel Vogt's classical slice passes both
yet carries negative density in its interior. The certificate closes that
gap: dense Durrleman g from the MODEL's own curve over the traded range,
turned into (1) a quality-readiness issue and (2) a hard publish blocker,
with the wing projection's calendar audit proving the published family
stays ordered. Certification case ``belly_certificate``.
"""

from __future__ import annotations

import time
from datetime import date

import numpy as np
import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.models.diagnostics import CERT_G_TOL, belly_certificate
from volfit.models.svi_jw.svi import RawSVI

REF_DATE = date(2026, 6, 10)

#: Axel Vogt's classical counterexample (the note's fig:belly): positive
#: minimum variance, harmless Lee wings (~0.25 tail g), negative belly.
VOGT = RawSVI(a=-0.0410, b=0.1331, rho=0.3060, m=0.3586, sigma=0.4153)
#: A mild, clean slice (well under every screen and butterfly-free).
CLEAN = RawSVI(a=0.02, b=0.10, rho=-0.20, m=0.0, sigma=0.25)


def test_vogt_slice_fails_certificate_where_screens_pass():
    """The certificate catches exactly what the wing screens miss."""
    # Wing screens pass: positive floor, Lee coefficient far under the cap.
    min_var = VOGT.a + VOGT.b * VOGT.sigma * np.sqrt(1.0 - VOGT.rho**2)
    assert min_var > 0.0
    assert VOGT.b * (1.0 + abs(VOGT.rho)) < 0.5
    # The belly certificate fails, at the note's documented dip.
    cert = belly_certificate(VOGT, -0.5, 1.2)
    assert cert is not None and not cert.certified
    assert cert.min_g == pytest.approx(-0.033, abs=5e-3)
    assert 0.5 < cert.argmin_k < 1.0  # the dip sits between the clean tails
    assert cert.neg_share > 0.0


def test_clean_slice_certifies_and_cost_is_negligible():
    """A clean slice certifies; the certificate costs microseconds, not
    milliseconds (the committee's affordability challenge, vs a ~1.8ms fit)."""
    cert = belly_certificate(CLEAN, -0.6, 0.6)
    assert cert is not None and cert.certified
    assert cert.min_g >= -CERT_G_TOL
    assert cert.neg_share == 0.0
    # Degenerate range: nothing to certify (None, treated as pass upstream).
    assert belly_certificate(CLEAN, 0.1, 0.1) is None
    start = time.perf_counter()
    for _ in range(100):
        belly_certificate(CLEAN, -0.6, 0.6)
    per_call_ms = (time.perf_counter() - start) * 10.0
    assert per_call_ms < 5.0  # loose rail; measured ~0.05ms per certificate


def test_quality_certifies_and_publish_passes_end_to_end():
    """Happy path on the synthetic universe: calibrated nodes certify, the
    quality rows carry the verdict, export publishes, and the projection
    calendar audit reads ~0 (the projection introduces no crossings)."""
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = client.get("/universe").json()["tickers"][0]
        isos = [e["expiry"] for e in client.get("/universe").json()["expiries"][tk]][:2]
        for iso in isos:
            assert client.post(f"/calibrate/{tk}/{iso}").status_code == 200
        rows = [
            n for n in client.get("/quality").json()["nodes"]
            if n["ticker"] == tk and n["hasFit"]
        ]
        assert rows, "calibrated nodes expected in the quality report"
        for n in rows:
            assert n["butterflyCertified"] is True
            assert n["bellyMinG"] is None or n["bellyMinG"] >= -CERT_G_TOL
        export = client.get("/export/surfaces", params={"tickers": tk})
        assert export.status_code == 200
        manifest = export.json()["manifest"]
        assert manifest["projectionCalendarWorstBp"] <= 1.0


def test_uncertified_belly_blocks_publish(monkeypatch):
    """The acceptance rule has teeth: force one node's certificate to fail —
    readiness drops, publish raises 409, allow_dirty exports a DRAFT."""
    from volfit.api import quality as quality_mod
    from volfit.models.diagnostics import BellyCertificate

    monkeypatch.setattr(
        quality_mod,
        "belly_certificate",
        lambda *a, **k: BellyCertificate(
            certified=False, min_g=-0.0485, argmin_k=0.3, neg_share=0.2, n_grid=801
        ),
    )
    with TestClient(create_app(reference_date=REF_DATE, gated=True)) as client:
        tk = client.get("/universe").json()["tickers"][0]
        iso = client.get("/universe").json()["expiries"][tk][0]["expiry"]
        assert client.post(f"/calibrate/{tk}/{iso}").status_code == 200
        row = next(
            n for n in client.get("/quality").json()["nodes"]
            if n["ticker"] == tk and n["expiry"] == iso
        )
        assert row["butterflyCertified"] is False
        assert row["ready"] is False
        assert any("belly butterfly arb" in i for i in row["issues"])
        # Publish: blocked hard, with the node and its min g named.
        blocked = client.get("/export/surfaces", params={"tickers": tk})
        assert blocked.status_code == 409
        assert "uncertified belly butterfly (min g -0.0485)" in blocked.text
        # The draft escape hatch stays: clearly a draft, never a publish.
        draft = client.get(
            "/export/surfaces", params={"tickers": tk, "allow_dirty": "true"}
        )
        assert draft.status_code == 200
