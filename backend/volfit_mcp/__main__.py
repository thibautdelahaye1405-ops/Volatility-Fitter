"""``python -m volfit_mcp`` — run the vol-fitter MCP server.

    python -m volfit_mcp                                   # stdio (Claude Desktop)
    python -m volfit_mcp --transport streamable-http --port 8765   # remote connector
    python -m volfit_mcp --api-url http://127.0.0.1:8000   # where the app runs

stdio keeps stdout for the protocol: everything human goes to stderr.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from volfit_mcp.client import DEFAULT_API_URL, VolfitApi
from volfit_mcp.server import build_server


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="volfit_mcp", description=__doc__.split("\n\n")[0])
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--api-url", default=os.environ.get("VOLFIT_API_URL", DEFAULT_API_URL),
                    help="base URL of the running vol-fitter API")
    ap.add_argument("--no-apps", action="store_true", help="disable the inline chart apps")
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args(argv)

    logging.basicConfig(level=args.log_level, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    server = build_server(VolfitApi(args.api_url), with_apps=not args.no_apps)
    print(f"vol-fitter MCP server ({args.transport}) -> API {args.api_url}", file=sys.stderr, flush=True)
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
