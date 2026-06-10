"""FastAPI layer serving the smile-fitting workflow (ROADMAP Phase 5).

The package wraps the volfit engine behind a frozen JSON contract shared
with the React frontend (see volfit.api.schemas): universe listing, per-node
smile payloads, calendar-constrained surface fits (HTTP and streaming
WebSocket), graph extrapolation of sparse observations, and SSR scenarios.
"""

from volfit.api.app import create_app

__all__ = ["create_app"]
