"""GET/POST /help/* — the in-app Help Center backend.

Thin router over three helpers:

* ``volfit.api.help_docs`` — the documentation catalog (``/help/docs``), one
  Markdown document by stem (``/help/docs/{doc_id}``) and inline file serving
  (``/help/files/{root}/{name}``) through the allow-listed, traversal-safe
  resolver. All of it degrades to ``available=False`` / 404 when the checkout
  ships without ``Docs/`` (the desktop bundle).
* ``volfit.api.help_schema`` — the settings reference (``/help/settings-schema``),
  generated from the pydantic settings models so it can never drift from them.
* ``volfit.api.help_ask`` — the optional Claude-backed "Ask @Vol-Fitter"
  assistant (``/help/ask/status`` + streaming ``POST /help/ask``); 503 when no
  server-side key is configured, so the frontend keeps its local tier.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from volfit.api import help_ask, help_docs
from volfit.api.help_ask import HelpAskRequest, HelpAskStatus
from volfit.api.help_docs import HelpDocMarkdown, HelpDocsCatalog
from volfit.api.help_schema import build_schema

router = APIRouter()

ASSISTANT_UNCONFIGURED = "assistant not configured (set VOLFIT_ANTHROPIC_KEY on the server)"


@router.get("/help/docs", response_model=HelpDocsCatalog)
def get_docs_catalog() -> HelpDocsCatalog:
    return help_docs.list_docs()


@router.get("/help/docs/{doc_id}", response_model=HelpDocMarkdown)
def get_doc_markdown(doc_id: str) -> HelpDocMarkdown:
    return help_docs.read_markdown(doc_id)


@router.get("/help/files/{root}/{name}")
def get_doc_file(root: str, name: str) -> FileResponse:
    """Serve one allow-listed Markdown/PDF file inline (viewer-friendly)."""
    path = help_docs.resolve_file(root, name)
    return FileResponse(
        path,
        media_type=help_docs.media_type_for(path),
        filename=path.name,
        content_disposition_type="inline",
    )


@router.get("/help/settings-schema")
def get_settings_schema() -> dict:
    return build_schema()


@router.get("/help/ask/status", response_model=HelpAskStatus)
def get_ask_status() -> HelpAskStatus:
    return help_ask.ask_status()


@router.post("/help/ask")
def post_ask(body: HelpAskRequest) -> StreamingResponse:
    """Stream the assistant's answer as Server-Sent Events (see help_ask)."""
    if help_ask.ask_status().tier != "claude":
        raise HTTPException(status_code=503, detail=ASSISTANT_UNCONFIGURED)
    return StreamingResponse(
        help_ask.stream_answer(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
