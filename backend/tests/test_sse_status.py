"""SSE calibration-status stream (ROADMAP perf #4).

The stream pushes the same payload as GET /calibration/status, declares
text/event-stream (excluded from GZip so it flushes in real time), and emits an
initial event immediately. Driven directly (not via TestClient.stream, whose
teardown can hang on an infinite generator) with a fake request that disconnects
after the first check — deterministic and fast.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from volfit.api.app import create_app
from volfit.api.routers.workflow import stream_status


class _FakeRequest:
    """Minimal Request stand-in: carries app.state and disconnects after one check."""

    def __init__(self, app) -> None:
        self.app = app
        self._checks = 0

    async def is_disconnected(self) -> bool:
        self._checks += 1
        return self._checks > 1  # connected for the first iteration, then stop


async def _first_event(app) -> str:
    resp = await stream_status(_FakeRequest(app))  # fit_mode None -> last_fit_mode
    assert resp.media_type == "text/event-stream"
    async for chunk in resp.body_iterator:
        return chunk if isinstance(chunk, str) else chunk.decode()
    return ""


def test_stream_first_event_is_status():
    app = create_app(reference_date=date(2026, 6, 20))
    chunk = asyncio.run(_first_event(app))
    assert chunk.startswith("data:")
    payload = json.loads(chunk[len("data:"):].strip())
    # Same shape as GET /calibration/status.
    for key in ("epoch", "spotVersion", "activity", "running", "staleNodes"):
        assert key in payload


def test_stream_payload_matches_status_endpoint():
    from fastapi.testclient import TestClient

    app = create_app(reference_date=date(2026, 6, 20))
    poll = TestClient(app).get("/calibration/status").json()
    chunk = asyncio.run(_first_event(app))
    streamed = json.loads(chunk[len("data:"):].strip())
    assert streamed["epoch"] == poll["epoch"]
    assert streamed["spotVersion"] == poll["spotVersion"]
