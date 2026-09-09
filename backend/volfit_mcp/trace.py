"""Wire trace: one JSON line per inbound MCP message (and its outcome).

Chat hosts log MCP traffic as metadata only ("method=resources/read id=4"),
which is useless when an inline app fails to show. ``TraceMiddleware`` writes
what the host actually sent — the client capabilities in ``initialize``
(does it advertise MCP Apps?), the ``resources/read`` URI, every
``tools/call`` and its ``_meta`` — plus a compact summary of the reply, to
the file named by ``VOLFIT_MCP_TRACE`` (or ``--trace``). Off by default; the
trace never contains market data beyond what a tool argument carries.
"""

from __future__ import annotations

import json
import time
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerMiddleware, ServerRequestContext

MAX_PARAMS = 4000  # chars of params kept per line


class TraceMiddleware(ServerMiddleware[Any]):
    """Append-only JSONL trace of the session."""

    def __init__(self, path: str) -> None:
        self.path = path

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        t0 = time.perf_counter()
        line: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "method": ctx.method,
            "id": ctx.request_id,
            "protocol": ctx.protocol_version,
            "params": _clip(ctx.params),
        }
        try:
            result = await call_next(ctx)
        except Exception as exc:  # observed, never swallowed
            line["error"] = f"{type(exc).__name__}: {exc}"[:500]
            line["ms"] = round(1000 * (time.perf_counter() - t0), 1)
            self._write(line)
            raise
        line["result"] = _summary(result)
        line["ms"] = round(1000 * (time.perf_counter() - t0), 1)
        self._write(line)
        return result

    def _write(self, line: dict[str, Any]) -> None:
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(line, default=str) + "\n")
        except OSError:  # a trace must never break the server
            pass


def _clip(obj: Any) -> Any:
    s = json.dumps(obj, default=str)
    return json.loads(s) if len(s) <= MAX_PARAMS else s[:MAX_PARAMS] + "…"


def _summary(result: HandlerResult) -> Any:
    """A size-bounded view of a handler result (keys, sizes, mime types)."""
    if result is None:
        return None
    data = result if isinstance(result, dict) else result.model_dump(mode="json", by_alias=True, exclude_none=True)
    out: dict[str, Any] = {"keys": sorted(data)[:12]}
    for key in ("tools", "resources", "prompts", "resourceTemplates"):
        if isinstance(data.get(key), list):
            out[key] = [x.get("name") or x.get("uri") for x in data[key]]
    if "contents" in data:
        out["contents"] = [{"uri": c.get("uri"), "mimeType": c.get("mimeType"),
                            "chars": len(c.get("text") or c.get("blob") or "")} for c in data["contents"]]
    if "content" in data:
        out["content"] = [{"type": c.get("type"), "chars": len(c.get("text") or c.get("data") or "")}
                          for c in data["content"]]
        out["structuredContent"] = sorted((data.get("structuredContent") or {}).keys())[:12]
        out["isError"] = data.get("isError", False)
    if "capabilities" in data:
        out["capabilities"] = data["capabilities"]
        out["protocolVersion"] = data.get("protocolVersion")
    return out
