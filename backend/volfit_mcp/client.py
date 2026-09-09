"""Async HTTP client of the vol-fitter API used by every MCP tool.

One ``VolfitApi`` per server process. It knows the base URL (``VOLFIT_API_URL``,
default ``http://127.0.0.1:8000``), turns HTTP failures into ``ApiError`` with
the app's own ``detail`` text (so the model reads "Cboe lists no options for
'SX5E'" rather than a bare 404), and turns a refused connection into the one
actionable message a desk user needs: start the app.

Tests inject an ``httpx.ASGITransport`` bound to ``create_app(...)`` so the
whole connector runs in-process against the synthetic provider, no sockets.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

DEFAULT_API_URL = "http://127.0.0.1:8000"
#: Generous default: the LV fit of a wide universe can take tens of seconds
#: per ticker; the calibrate tool polls, but /fit/affine is a synchronous read
#: of a cached fit and only slow when a stale ticker is re-fitted on demand.
DEFAULT_TIMEOUT_S = 300.0

NOT_RUNNING_HINT = (
    "The vol-fitter backend is not reachable at {url}. Start it from the repo "
    "root with `.\\restart.ps1` (or `.venv\\Scripts\\python backend\\serve.py`) "
    "and retry; set VOLFIT_API_URL if it runs elsewhere."
)


class ApiError(ToolError):
    """An API call failed; ``str(exc)`` is the message the model should see.

    A ``ToolError`` subclass so the MCP server reports it as a tool result with
    ``isError`` (the model reads the text and adapts) instead of a protocol
    failure — the one place the client module leans on the server SDK."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class VolfitApi:
    """Minimal async JSON client: ``get`` / ``post`` / ``put`` / ``delete``."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self.base_url = (base_url or os.environ.get("VOLFIT_API_URL") or DEFAULT_API_URL).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url, transport=transport, timeout=timeout
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------- verbs
    async def get(self, path: str, **params: Any) -> Any:
        return await self._call("GET", path, params=_clean(params))

    async def post(self, path: str, json: Any | None = None, **params: Any) -> Any:
        return await self._call("POST", path, json=json, params=_clean(params))

    async def put(self, path: str, json: Any | None = None, **params: Any) -> Any:
        return await self._call("PUT", path, json=json, params=_clean(params))

    async def delete(self, path: str, **params: Any) -> Any:
        return await self._call("DELETE", path, params=_clean(params))

    async def get_text(self, path: str, **params: Any) -> str:
        """A non-JSON GET (HTML report, CSV)."""
        resp = await self._request("GET", path, params=_clean(params))
        return resp.text

    # ---------------------------------------------------------- plumbing
    async def _call(self, method: str, path: str, **kw: Any) -> Any:
        resp = await self._request(method, path, **kw)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:  # pragma: no cover — the API always speaks JSON
            raise ApiError(f"{method} {path}: non-JSON reply ({exc})", resp.status_code) from None

    async def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            resp = await self._client.request(method, path, **kw)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Refused OR silently dropped (Windows firewalls time a closed port out).
            raise ApiError(NOT_RUNNING_HINT.format(url=self.base_url)) from exc
        except httpx.TimeoutException as exc:
            raise ApiError(f"{method} {path} timed out after {self._client.timeout}") from exc
        if resp.status_code >= 400:
            raise ApiError(f"{method} {path} -> {resp.status_code}: {_detail(resp)}", resp.status_code)
        return resp


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` query params so tools can pass optional arguments through."""
    return {k: v for k, v in params.items() if v is not None}


def _detail(resp: httpx.Response) -> str:
    """The FastAPI ``detail`` (string or validation list) or the raw body."""
    try:
        body = resp.json()
    except ValueError:
        return resp.text[:300]
    detail = body.get("detail") if isinstance(body, dict) else body
    if isinstance(detail, list):  # pydantic validation errors
        return "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg', '')}" for e in detail
        )
    return str(detail)
