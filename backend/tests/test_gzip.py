"""GZip middleware (ROADMAP perf #5): dense JSON payloads are compressed.

Verifies the middleware is wired (large responses come back gzip-encoded when the
client accepts it) and that the response body is still intact after the round trip.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from volfit.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app(reference_date=date(2026, 6, 20)))


def test_large_response_is_gzipped():
    client = _client()
    # /openapi.json is reliably large (> the 1024-byte floor) and needs no data.
    r = client.get("/openapi.json", headers={"accept-encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"
    assert r.json()["info"]["title"] == "volfit"  # body intact after decompress


def test_small_response_not_gzipped():
    client = _client()
    # A tiny/!found response stays below the floor → not compressed.
    r = client.get("/does-not-exist", headers={"accept-encoding": "gzip"})
    assert r.headers.get("content-encoding") != "gzip"


def test_no_accept_encoding_means_plain():
    client = _client()
    r = client.get("/openapi.json", headers={"accept-encoding": "identity"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") != "gzip"
    assert r.json()["info"]["title"] == "volfit"
