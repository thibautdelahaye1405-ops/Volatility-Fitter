"""Single-origin static serving (volfit.api.frontend).

The desktop ``.exe`` serves both the API and the built React bundle from one
origin: ``mount_frontend`` mounts the bundle at ``/`` *after* the routers, so
API routes still win and the static mount only catches what's left. These tests
use a tiny synthetic ``dist`` (an index.html + an asset) so they need no real
frontend build — they assert the precedence + serving contract only.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from volfit.api.app import create_app
from volfit.api.frontend import find_frontend_dist, mount_frontend

REF = date(2026, 6, 13)


def _fake_dist(tmp_path):
    """Write a minimal built-bundle layout (index.html + /assets/app.js)."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>VolFitter</title>", "utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log('hi')", "utf-8")
    return tmp_path


def test_mount_serves_index_and_assets(tmp_path):
    app = create_app(reference_date=REF)
    assert mount_frontend(app, _fake_dist(tmp_path)) is True
    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert "VolFitter" in root.text
    assert root.headers["content-type"].startswith("text/html")

    asset = client.get("/assets/app.js")
    assert asset.status_code == 200
    assert "console.log" in asset.text


def test_api_routes_take_precedence_over_static_mount(tmp_path):
    """An explicit API route must still resolve after the bundle is mounted."""
    app = create_app(reference_date=REF)
    mount_frontend(app, _fake_dist(tmp_path))
    client = TestClient(app)

    # /universe is a real router endpoint; it must NOT be shadowed by the mount.
    resp = client.get("/universe")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


def test_mount_returns_false_when_no_bundle(tmp_path):
    """No bundle -> no mount (desktop.py then serves API-only with a warning)."""
    app = create_app(reference_date=REF)
    assert mount_frontend(app, tmp_path / "does-not-exist") is False


def test_find_frontend_dist_returns_none_or_real_index():
    """Resolver either finds a built bundle (with index.html) or returns None."""
    found = find_frontend_dist()
    assert found is None or (found / "index.html").is_file()
