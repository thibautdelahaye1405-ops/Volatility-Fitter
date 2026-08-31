"""HTTP API tests for the in-app Help Center (/help/*).

Runs in-process over fastapi.testclient against create_app(reference_date=
2026-06-10), like tests/test_api.py. Locks: the documentation catalog + safe
file serving (traversal attempts never 200), the docs-unavailable path
(VOLFIT_DOCS_ROOT -> empty dir), the settings schema vs the pydantic models,
and the Ask assistant (local tier / 503 without a key; SSE deltas, error events
and request clamps with a stubbed SDK client).
"""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from volfit.api import create_app, help_ask, help_docs
from volfit.api.schemas import FitSettings, OptionsSettings
from volfit.api.schemas_market import MarketSettings

REF_DATE = date(2026, 6, 10)


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(reference_date=REF_DATE)) as c:
        yield c


@pytest.fixture
def no_keys(monkeypatch):
    for var in help_ask.KEY_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv(help_ask.MODEL_ENV_VAR, raising=False)


# -- documentation catalog ---------------------------------------------------


def test_docs_catalog_lists_notes_and_pdfs(client):
    data = client.get("/help/docs").json()
    assert data["available"] is True
    assert data["root"]
    entries = data["entries"]
    by_key = {(e["root"], e["id"]): e for e in entries}

    overview = by_key[("notes-md", "00_system_overview")]
    assert overview["kind"] == "md"
    assert overview["name"] == "00_system_overview.md"
    assert overview["title"].startswith("System Overview")
    assert overview["sizeBytes"] > 0

    pdfs = [e for e in entries if e["root"] == "notes-pdf"]
    assert pdfs and all(e["kind"] == "pdf" for e in pdfs)
    assert by_key[("notes-pdf", "00_system_overview")]["name"] == "00_system_overview.pdf"

    names = {(e["root"], e["name"]) for e in entries}
    assert ("book", "ROADMAP.md") not in names
    assert ("book", "NOTATION.md") not in names
    assert not any(e["name"].startswith("_") for e in entries)
    assert {e["kind"] for e in entries} <= {"md", "pdf"}


def test_docs_markdown_by_stem(client):
    data = client.get("/help/docs/00_system_overview").json()
    assert data["id"] == "00_system_overview"
    assert data["root"] == "notes-md"
    assert data["name"] == "00_system_overview.md"
    assert data["markdown"].startswith("# ")
    assert data["title"].startswith("System Overview")

    # Lookup order falls through to the handoff pack for its own documents.
    handoff = client.get("/help/docs/SETTINGS_REFERENCE").json()
    assert handoff["root"] == "handoff"
    assert handoff["markdown"].startswith("# ")


def test_docs_markdown_unknown_404(client):
    assert client.get("/help/docs/no_such_note_xyz").status_code == 404


def test_catalog_scan_rules(tmp_path, monkeypatch):
    """Synthetic tree: non-recursive, '_'/ROADMAP skipped, first '# ' heading = title."""
    notes = tmp_path / "Docs" / "handoff" / "notes"
    notes.mkdir(parents=True)
    (notes / "01_a.md").write_text("intro line\n# A Title\n", encoding="utf-8")
    (notes / "04_notitle.md").write_text("no heading here\n", encoding="utf-8")
    (notes / "_draft.md").write_text("# Draft\n", encoding="utf-8")
    (notes / "ROADMAP.md").write_text("# R\n", encoding="utf-8")
    (notes / "02_b.txt").write_text("x", encoding="utf-8")
    (notes / "sub").mkdir()
    (notes / "sub" / "03_c.md").write_text("# C\n", encoding="utf-8")
    book = tmp_path / "Papers" / "book"
    book.mkdir(parents=True)
    (book / "book.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setenv(help_docs.DOCS_ROOT_ENV, str(tmp_path))

    cat = help_docs.list_docs()
    assert cat.available is True
    assert [(e.root, e.id) for e in cat.entries] == [
        ("notes-md", "01_a"),
        ("notes-md", "04_notitle"),
        ("book", "book"),
    ]
    titles = {e.id: e.title for e in cat.entries}
    assert titles == {"01_a": "A Title", "04_notitle": "04_notitle", "book": "book"}
    assert help_docs.read_markdown("01_a").title == "A Title"


# -- file serving ------------------------------------------------------------


def test_files_markdown_inline(client):
    r = client.get("/help/files/notes-md/00_system_overview.md")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"].startswith("inline")
    assert r.text.startswith("# ")


def test_files_pdf_inline(client):
    r = client.get("/help/files/notes-pdf/00_system_overview.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline")
    assert r.content[:5] == b"%PDF-"


@pytest.mark.parametrize(
    "url",
    [
        "/help/files/notes-md/..%2F..%2Fpyproject.toml",
        "/help/files/notes-md/..%5C..%5Cpyproject.toml",
        "/help/files/notes-md/sub/00_system_overview.md",
        "/help/files/nope/00_system_overview.md",
        "/help/files/notes-md/00_system_overview.py",
        "/help/files/notes-md/00_system_overview",
        "/help/files/book/ROADMAP.md",
        "/help/files/notes-md/_hidden.md",
    ],
)
def test_files_reject_traversal_and_unknown(client, url):
    assert client.get(url).status_code in (400, 404)


def test_files_missing_404(client):
    assert client.get("/help/files/notes-md/does_not_exist_xyz.md").status_code == 404


@pytest.mark.parametrize(
    "name", ["../../pyproject.toml", "..\\..\\pyproject.toml", "a/b.md", "x.py", "", "..md"]
)
def test_resolve_file_rejects_unsafe_names_directly(name):
    with pytest.raises(HTTPException) as info:
        help_docs.resolve_file("notes-md", name)
    assert info.value.status_code == 400


def test_resolve_file_unknown_root_404():
    with pytest.raises(HTTPException) as info:
        help_docs.resolve_file("nope", "00_system_overview.md")
    assert info.value.status_code == 404


# -- docs unavailable --------------------------------------------------------


def test_docs_unavailable_when_root_empty(client, tmp_path, monkeypatch):
    monkeypatch.setenv(help_docs.DOCS_ROOT_ENV, str(tmp_path))
    assert help_docs.find_docs_root() is None
    cat = help_docs.list_docs()
    assert cat.available is False and cat.entries == [] and cat.root is None

    data = client.get("/help/docs").json()
    assert data["available"] is False and data["entries"] == []
    assert client.get("/help/docs/x").status_code == 404
    assert client.get("/help/files/notes-md/00_system_overview.md").status_code == 404


# -- settings schema ---------------------------------------------------------


def test_settings_schema_matches_pydantic_fields(client):
    data = client.get("/help/settings-schema").json()
    assert data["generatedAt"]
    models = data["models"]
    expected = {"fit": FitSettings, "options": OptionsSettings, "market": MarketSettings}
    for key, model in expected.items():
        assert models[key]["title"]
        names = [f["name"] for f in models[key]["fields"]]
        assert len(names) == len(set(names))
        assert set(names) == set(model.model_fields)


# -- ask: unconfigured -------------------------------------------------------


def test_ask_status_local_without_key(client, no_keys):
    status = client.get("/help/ask/status").json()
    assert status["tier"] == "local"
    assert status["configured"] is False
    assert status["sdkInstalled"] == (help_ask.anthropic is not None)
    assert status["model"] is None


def test_ask_503_without_key(client, no_keys):
    r = client.post("/help/ask", json={"question": "what is a lens?"})
    assert r.status_code == 503
    assert "VOLFIT_ANTHROPIC_KEY" in r.json()["detail"]


def test_ask_rejects_overlong_question(client):
    r = client.post("/help/ask", json={"question": "x" * 2001})
    assert r.status_code == 422


# -- ask: stubbed SDK client -------------------------------------------------


class _StubStream:
    """Mimics the SDK's stream context manager: text_stream + get_final_message()."""

    def __init__(self, deltas, stop_reason="end_turn", model="stub-model", raise_on_enter=None):
        self._deltas = list(deltas)
        self._stop_reason = stop_reason
        self._model = model
        self._raise = raise_on_enter

    def __enter__(self):
        if self._raise is not None:
            raise self._raise
        return self

    def __exit__(self, *exc_info):
        return False

    @property
    def text_stream(self):
        yield from self._deltas

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop_reason, model=self._model)


class _StubClient:
    """``client.beta.messages.stream(**kw)`` records kwargs and returns the stub stream."""

    def __init__(self, stream: _StubStream):
        self.calls: list[dict] = []
        self._stream_obj = stream
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._open_stream))

    def _open_stream(self, **kwargs):
        self.calls.append(kwargs)
        return self._stream_obj


def _sse_events(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def stub_env(monkeypatch, no_keys):
    pytest.importorskip("anthropic")  # tier "claude" requires the SDK import
    monkeypatch.setenv("VOLFIT_ANTHROPIC_KEY", "test-key")

    def install(stream):
        stub = _StubClient(stream)
        seen: list[str] = []

        def factory(key: str):
            seen.append(key)
            return stub

        monkeypatch.setattr(help_ask, "_client_factory", factory)
        return stub, seen

    return install


def test_ask_streams_deltas_with_stub(client, stub_env):
    stub, keys_seen = stub_env(_StubStream(["Hello, ", "world."]))
    body = {
        "question": "How do I light a node?",
        "cards": [{"id": "c1", "kind": "command", "title": "Light node", "text": "Drag it."}],
        "context": {"lens": "smile", "ticker": "SPY"},
        "history": [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}],
    }
    r = client.post("/help/ask", json=body)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"

    events = _sse_events(r.text)
    assert [e["text"] for e in events if e["type"] == "delta"] == ["Hello, ", "world."]
    done = events[-1]
    assert done["type"] == "done" and done["tier"] == "claude"
    assert done["model"] == "stub-model" and done["refused"] is False
    assert keys_seen == ["test-key"]

    # The exact documented call shape (streaming.md + README + model-migration.md).
    kw = stub.calls[0]
    assert kw["model"] == help_ask.DEFAULT_MODEL
    assert kw["max_tokens"] == 2048
    assert kw["thinking"] == {"type": "adaptive"}
    assert kw["output_config"] == {"effort": "low"}
    assert kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert "— see:" in kw["system"]
    messages = kw["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    last = messages[-1]["content"]
    assert "Light node" in last and "Drag it." in last
    assert "lens=smile" in last and "ticker=SPY" in last
    assert last.rstrip().endswith("Question: How do I light a node?")


def test_ask_model_env_override_and_leading_assistant_turn_dropped(client, stub_env, monkeypatch):
    monkeypatch.setenv(help_ask.MODEL_ENV_VAR, "claude-sonnet-5")
    stub, _ = stub_env(_StubStream(["ok"]))
    body = {"question": "q", "history": [{"role": "assistant", "text": "stale"}]}
    assert client.get("/help/ask/status").json() == {
        "tier": "claude",
        "configured": True,
        "sdkInstalled": True,
        "model": "claude-sonnet-5",
    }
    r = client.post("/help/ask", json=body)
    assert r.status_code == 200
    kw = stub.calls[0]
    assert kw["model"] == "claude-sonnet-5"
    assert [m["role"] for m in kw["messages"]] == ["user"]  # first message must be user


def test_ask_refusal_note(client, stub_env):
    stub_env(_StubStream([], stop_reason="refusal"))
    events = _sse_events(client.post("/help/ask", json={"question": "q"}).text)
    assert events[-1]["type"] == "done" and events[-1]["refused"] is True
    assert any(e["type"] == "delta" and "declined" in e["text"] for e in events)


def test_ask_error_event_on_connection_error(client, stub_env):
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")  # anthropic 1.x is built on httpx2
    exc = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))
    stub_env(_StubStream([], raise_on_enter=exc))
    r = client.post("/help/ask", json={"question": "q"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "connect" in events[0]["message"].lower()


def test_ask_error_event_on_rate_limit(client, stub_env):
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    request = httpx2.Request("POST", "https://x")
    response = httpx2.Response(429, request=request)
    exc = anthropic.RateLimitError("slow down", response=response, body=None)
    stub_env(_StubStream([], raise_on_enter=exc))
    events = _sse_events(client.post("/help/ask", json={"question": "q"}).text)
    assert len(events) == 1 and events[0]["type"] == "error"
    assert "rate-limited" in events[0]["message"]


def test_ask_unexpected_exception_becomes_error_event(client, stub_env):
    stub_env(_StubStream([], raise_on_enter=RuntimeError("boom")))
    events = _sse_events(client.post("/help/ask", json={"question": "q"}).text)
    assert events[-1]["type"] == "error"
    assert "RuntimeError" in events[-1]["message"]


# -- request clamps ----------------------------------------------------------


def test_request_clamps_truncate_instead_of_reject():
    cards = [
        {"id": f"c{i}", "kind": "k", "title": f"T{i}", "text": "x" * 5000} for i in range(13)
    ]
    history = [{"role": "user", "text": "h" * 9000}] * 10
    req = help_ask.HelpAskRequest(question="q", cards=cards, history=history)
    assert len(req.cards) == 12
    assert all(len(c.text) == 4000 for c in req.cards)
    assert len(req.history) == 8
    assert all(len(t.text) == 4000 for t in req.history)
