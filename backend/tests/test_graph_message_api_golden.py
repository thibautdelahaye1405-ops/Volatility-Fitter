"""Section-21 golden acceptance contracts locked THROUGH the HTTP API.

Docs/graph_precision_message_framework.md (S21) states the product contracts
of the precision-message operator. They are already locked at the library
level (tests/test_graph_message_golden.py exact reference, tests/
test_graph_message.py operator, tests/test_graph_message_production.py
production assembly). This module is the consolidated S21-through-the-API
lock: every contract travels POST /graph/extrapolate over the real app, so
FastAPI routing, pydantic request parsing (messageEdges /
syntheticObservations / calendarAmplitude), the lit-map state (PUT
/universe/lit) and the response serialization are all on the hook.

Shared mechanics:

* signals are hypothesis-firm syntheticObservations pulses (P5b U3) with an
  explicit near-infinite precision — the S21 "clamped lit informer". A
  pulse's innovation is exactly dAtmVol and the pulsed node is pinned.
* topology is EXPLICIT messageEdges rows: auto calendar betas depend on the
  real expiry T-ratios, so exact-number contracts pin betas by hand. A row
  source->target with betaAtmVol=b is the canonical pairwise factor
  z_target ~ b * z_source (spec S7.2/S7.6) — for a single-source receiver in
  desk mode (amplitude 1 => kappa 0) the transfer is exact.
* with firm pulses the pulsed node is pinned, so receiver transfer is read
  off shiftBp = (postAtmVol - priorAtmVol) * 1e4 — the posterior innovation.
* flatAtm keeps the baselines trivial (0.20 everywhere, no fits triggered);
  every request runs propagationMode="precision_messages" except the S21.10
  byte-identity lock, which exercises the untouched default.

Contracts: S21.1 (full transmission; precision moves bands, never means),
S21.4 (cross-asset average, q_C = 2p), S21.10 (legacy byte identity — also
locked at function level by test_graph_message_production.
test_smooth_field_default_is_unchanged; HERE over the HTTP payloads),
S21.11 (dead informer: zero dilution, broad marginal, proper 200),
S21.12 (shrunk transfer rho*beta*z and corroboration 2rho/(1+rho)),
S21.13 (baseline uncertainty enters exactly once).
"""

from contextlib import contextmanager
from datetime import date

import pytest
from fastapi.testclient import TestClient

from volfit.api import create_app
from volfit.api.graph_message import DISCONNECTED_Z_SD

REF_DATE = date(2026, 6, 10)

#: Firm clamp for pulsed sources (1/vol^2): effectively infinite next to any
#: row precision used here, so the informer is the spec's clamped source.
CLAMP = 1.0e12
P_ROW = 1.0e3  # default explicit-row message precision (1/vol^2)
P_DEAD = 2.5e4  # dead-informer row: 25x MORE precise than the lit row (S21.11)
PULSE = 0.01  # +100bp ATM pulse


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture(scope="module")
def universe(client):
    """ticker -> ascending expiry ladder (3 tickers x 4 expiries)."""
    return client.get("/universe").json()["expiries"]


def _isos(universe, ticker):
    return [e["expiry"] for e in universe[ticker]]


def _row(src, dst, beta=1.0, precision=P_ROW, relation="calendar"):
    """One schema-v2 message row: src (informer) predicts dst (receiver)."""
    return {
        "sourceTicker": src[0], "sourceExpiry": src[1],
        "targetTicker": dst[0], "targetExpiry": dst[1],
        "messagePrecision": precision,
        "betaAtmVol": beta, "betaSkew": beta, "betaCurv": beta,
        "relationClass": relation,
    }


def _pulse(node, d_atm=PULSE, precision=CLAMP):
    return {"ticker": node[0], "expiry": node[1],
            "dAtmVol": d_atm, "precision": precision}


def _solve(client, rows, pulses, **extra):
    """POST /graph/extrapolate in message mode; name -> node dict."""
    body = {
        "propagationMode": "precision_messages",
        "flatAtm": True,
        "messageEdges": rows,
        "syntheticObservations": pulses,
        **extra,
    }
    resp = client.post("/graph/extrapolate", json=body)
    assert resp.status_code == 200, resp.text  # properness — never a crash
    payload = resp.json()
    assert payload["propagationMode"] == "precision_messages"
    return {(n["ticker"], n["expiry"]): n for n in payload["nodes"]}


@contextmanager
def _dark(client, *nodes):
    """Darken nodes over the API; ALWAYS re-light (module-scoped app)."""
    try:
        for tk, iso in nodes:
            r = client.put(f"/universe/lit/{tk}/{iso}", json={"lit": False})
            assert r.status_code == 200, r.text
        yield
    finally:
        for tk, iso in nodes:
            client.put(f"/universe/lit/{tk}/{iso}", json={"lit": True})


# --------------------------------------------------------------- S21.1
def test_full_transmission_and_precision_moves_bands_not_means(client, universe):
    """S21.1 through the API: a +100bp clamped pulse transmits at FULL
    amplitude over explicit betas — +200bp at beta 2, +50bp at beta 0.5
    (desk amplitude 1 => zero anchor). Scaling the row precision 10x moves
    the receiver sd DOWN but leaves the conditional means untouched."""
    isos = _isos(universe, "ALPHA")
    src, near, far = ("ALPHA", isos[2]), ("ALPHA", isos[0]), ("ALPHA", isos[3])
    rows = [_row(src, near, beta=2.0), _row(src, far, beta=0.5)]
    with _dark(client, near, far):
        by = _solve(client, rows, [_pulse(src)])
        # The pulse is hypothesis-firm: pinned, and innovation == dAtmVol.
        assert by[src]["calibrated"] is True
        assert by[src]["innovationBp"] == pytest.approx(100.0, abs=1e-6)
        assert by[src]["shiftBp"] == pytest.approx(100.0, rel=1e-6)
        assert by[near]["shiftBp"] == pytest.approx(200.0, rel=1e-3)
        assert by[far]["shiftBp"] == pytest.approx(50.0, rel=1e-3)
        assert by[near]["noLitPath"] is False and by[far]["noLitPath"] is False
        # S7.6 receiver conditional: a single incident row contributes p.
        assert by[near]["qIncoming"] == pytest.approx(P_ROW, rel=1e-9)

        # Precision x10: sd tightens, the means do not move (S21.1 clause 2).
        # The pulse is firm (r = 1e12) rather than a true clamp, so the means
        # agree to the finite-precision leak (~1e-5 bp), not to machine zero.
        tight = [_row(src, near, beta=2.0, precision=10 * P_ROW),
                 _row(src, far, beta=0.5, precision=10 * P_ROW)]
        by_hi = _solve(client, tight, [_pulse(src)])
        for node in (near, far):
            assert by_hi[node]["shiftBp"] == pytest.approx(
                by[node]["shiftBp"], abs=1e-3
            )
            assert by_hi[node]["sd"] < by[node]["sd"]


# --------------------------------------------------------------- S21.4
def test_cross_asset_average(client, universe):
    """S21.4 through the API: a dark name hearing two equal-precision
    beta-one clamped messages (+100bp and +300bp) posts their average
    (+200bp), with receiver conditional precision q_C = 2p exactly."""
    iso = _isos(universe, "ALPHA")[1]
    a, b, recv = ("ALPHA", iso), ("BETA", iso), ("GAMMA", iso)
    rows = [_row(a, recv, relation="custom"), _row(b, recv, relation="custom")]
    with _dark(client, recv):
        by = _solve(client, rows, [_pulse(a, 0.01), _pulse(b, 0.03)])
        assert by[recv]["shiftBp"] == pytest.approx(200.0, rel=1e-3)
        assert by[recv]["noLitPath"] is False
        assert by[recv]["qIncoming"] == pytest.approx(2 * P_ROW, rel=1e-9)


# --------------------------------------------------------------- S21.11
def test_dead_informer_zero_dilution_via_api(client, universe):
    """S21.11 through the API. Receiver R hears (i) a clamped lit informer L
    at beta 1.5, precision p, and (ii) a DARK informer D that has no lit
    signal of its own and only this one row into R — configured 25x MORE
    precise than the lit row. Pairwise factors give ZERO dilution: R's shift
    is beta * z_lit = +150bp exactly (the rejected row-normalized form would
    dilute to ~ p/(p+p_dead) * 150 ~ 5.8bp). D is informed only through R:
    its posterior marginal is Var(R) + 1/p_dead — broader than R and at
    least the S14.3 disconnected scale — and the component stays proper
    (the 200 asserted inside _solve). NB the wire noLitPath tag rides
    factor-support connectivity (S14.3), so D reads False here — its
    broad sd is the honest signal; the tag is deliberately unasserted."""
    isos = _isos(universe, "ALPHA")
    lit = ("ALPHA", isos[2])
    recv = ("ALPHA", isos[1])
    dead = ("BETA", _isos(universe, "BETA")[3])
    rows = [
        _row(lit, recv, beta=1.5, precision=P_ROW),
        _row(dead, recv, beta=1.0, precision=P_DEAD, relation="custom"),
    ]
    with _dark(client, recv, dead):
        by = _solve(client, rows, [_pulse(lit)])
        # Zero dilution: the lit message arrives whole.
        assert by[recv]["shiftBp"] == pytest.approx(150.0, rel=1e-3)
        # The configured-precise dead row IS counted by the conditional q...
        assert by[recv]["qIncoming"] == pytest.approx(P_ROW + P_DEAD, rel=1e-9)
        # ...and D chases the receiver (informed only through it, beta 1).
        assert by[dead]["calibrated"] is False
        assert by[dead]["shiftBp"] == pytest.approx(150.0, rel=1e-3)
        # D stays broad: sd at least the disconnected per-handle scale, and
        # its posterior marginal (response sd^2 minus the S15.3 baseline
        # term) exceeds the receiver's by EXACTLY 1/p_dead.
        assert by[dead]["sd"] >= DISCONNECTED_Z_SD[0]
        marg_r = by[recv]["sd"] ** 2 - 1.0 / by[recv]["baselinePrecision"][0]
        marg_d = by[dead]["sd"] ** 2 - 1.0 / by[dead]["baselinePrecision"][0]
        assert marg_d - marg_r == pytest.approx(1.0 / P_DEAD, rel=1e-6)


# --------------------------------------------------------------- S21.12
def test_shrunk_mode_transfer(client, universe):
    """S21.12 through the API, single clamped source: calendarAmplitude=0.34
    engages the S14.2 node-linked anchor kappa = p(1-rho)/rho, so the
    receiver transfer is exactly rho * beta * z — +68bp at beta 2, +17bp at
    beta 0.5. calendarAmplitude=1.0 zeroes the anchor and recovers the
    S21.1 full transmission (+200/+50)."""
    isos = _isos(universe, "ALPHA")
    src, near, far = ("ALPHA", isos[2]), ("ALPHA", isos[0]), ("ALPHA", isos[3])
    rows = [_row(src, near, beta=2.0), _row(src, far, beta=0.5)]
    with _dark(client, near, far):
        by = _solve(client, rows, [_pulse(src)], calendarAmplitude=0.34)
        assert by[near]["shiftBp"] == pytest.approx(0.34 * 200.0, rel=1e-3)
        assert by[far]["shiftBp"] == pytest.approx(0.34 * 50.0, rel=1e-3)

        by = _solve(client, rows, [_pulse(src)], calendarAmplitude=1.0)
        assert by[near]["shiftBp"] == pytest.approx(200.0, rel=1e-3)
        assert by[far]["shiftBp"] == pytest.approx(50.0, rel=1e-3)


def test_corroboration_lifts_transfer(client, universe):
    """S21.12 corroboration through the API: the anchor is FIXED from the
    primary relation (kappa = p(1-rho)/rho, never rescaled as edges arrive),
    so with rho = 0.5 one clamped +100bp source transfers +50bp while TWO
    equal agreeing sources lift the receiver to 2rho/(1+rho) * 100bp =
    +66.67bp per unit beta — corroboration raises trust; it never
    double-counts to rho * 200bp nor pins at rho * 100bp."""
    rho = 0.5
    isos = _isos(universe, "ALPHA")
    lo, recv, hi = ("ALPHA", isos[1]), ("ALPHA", isos[2]), ("ALPHA", isos[3])
    with _dark(client, recv):
        one = _solve(
            client, [_row(lo, recv)], [_pulse(lo)], calendarAmplitude=rho
        )
        assert one[recv]["shiftBp"] == pytest.approx(rho * 100.0, rel=1e-3)

        two = _solve(
            client,
            [_row(lo, recv), _row(hi, recv)],
            [_pulse(lo), _pulse(hi)],
            calendarAmplitude=rho,
        )
        expected = 2.0 * rho / (1.0 + rho) * 100.0  # 66.67bp
        assert two[recv]["shiftBp"] == pytest.approx(expected, rel=1e-3)


# --------------------------------------------------------------- S21.13
def test_baseline_uncertainty_enters_once(client, universe):
    """S21.13 through the API. A dark node with NO lit path must carry the
    baseline term exactly once in its band: sd^2 == disconnected variance +
    1/baselinePrecision (S14.3 + S15.3), both fields read off the SAME
    response node. A pulsed (observed) node's baseline noise lives inside
    the S15.2 observation combination, so its sd^2 stays BELOW
    1/baselinePrecision — never re-added at reconstruction."""
    src = ("ALPHA", _isos(universe, "ALPHA")[2])
    near = ("ALPHA", _isos(universe, "ALPHA")[0])
    zed = ("GAMMA", _isos(universe, "GAMMA")[3])  # named in NO row: no lit path
    with _dark(client, near, zed):
        by = _solve(client, [_row(src, near, beta=2.0)], [_pulse(src)])
        assert by[zed]["noLitPath"] is True
        assert by[zed]["shiftBp"] == pytest.approx(0.0, abs=1e-9)  # stays put
        expected_var = (
            DISCONNECTED_Z_SD[0] ** 2 + 1.0 / by[zed]["baselinePrecision"][0]
        )
        assert by[zed]["sd"] ** 2 == pytest.approx(expected_var, rel=1e-6)
        # Observed node: posterior-only sd (baseline entered via r_d once).
        assert by[src]["sd"] ** 2 < 1.0 / by[src]["baselinePrecision"][0]


# --------------------------------------------------------------- S21.10
def test_legacy_smooth_field_byte_identity(client):
    """S21.10 through the API: an untouched request {} and an explicit
    {"propagationMode": "smooth_field"} produce IDENTICAL payloads at the
    current defaults, with the message-mode diagnostic fields inert. (The
    same contract is locked at function level by
    test_graph_message_production.test_smooth_field_default_is_unchanged;
    this is the HTTP-payload edition of the lock.)"""
    a = client.post("/graph/extrapolate", json={})
    b = client.post("/graph/extrapolate", json={"propagationMode": "smooth_field"})
    assert a.status_code == 200 and b.status_code == 200
    pa, pb = a.json(), b.json()
    assert pa == pb
    assert pa["propagationMode"] == "smooth_field"
    assert len(pa["nodes"]) > 0
    assert all(
        n["qIncoming"] is None and n["noLitPath"] is None for n in pa["nodes"]
    )
    assert pa["cycleDiagnostics"] == []
