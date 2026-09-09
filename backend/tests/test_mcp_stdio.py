"""The real launch path: ``python -m volfit_mcp`` over stdio, as Claude Desktop
runs it, against a live uvicorn serving the synthetic app on a free port.

Locks the two things the in-process test cannot: the module is importable from
an arbitrary working directory (the editable install exposes ``volfit_mcp``),
and nothing but JSON-RPC reaches stdout (a stray print would break the pipe).
"""

from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from datetime import date

import httpx
import pytest
import uvicorn
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters

from volfit.api.app import create_app

REF_DATE = date(2026, 6, 10)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def api_url():
    port = _free_port()
    app = create_app(reference_date=REF_DATE)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(url + "/universe", timeout=1.0).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:  # pragma: no cover
        raise RuntimeError("uvicorn did not come up")
    yield url
    server.should_exit = True
    thread.join(timeout=5)


def test_stdio_launch_lists_tools_and_reads_the_app(api_url, tmp_path):
    env = {**os.environ, "VOLFIT_API_URL": api_url, "PYTHONIOENCODING": "utf-8"}
    params = StdioServerParameters(command=sys.executable, args=["-m", "volfit_mcp"], env=env, cwd=str(tmp_path))

    async def go():
        async with Client(params) as c:
            tools = {t.name for t in (await c.list_tools()).tools}
            uni = await c.call_tool("get_universe", {})
            ui = await c.read_resource("ui://volfit/lv-compare.html")
            return tools, uni, ui

    tools, uni, ui = asyncio.run(go())
    assert {"calibrate", "chart_lv_compare", "get_smile"} <= tools
    assert uni.is_error is False and uni.structured_content["tickers"]
    assert ui.contents[0].mime_type == "text/html;profile=mcp-app"
