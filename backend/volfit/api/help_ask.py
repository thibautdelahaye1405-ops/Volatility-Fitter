"""In-app Help Center — the "Ask @Vol-Fitter" assistant (tier 1: Claude).

The Help Center retrieves help cards locally in the browser (command reference,
settings reference, documentation excerpts). Tier 1 sends the question plus
those cards to Claude and streams the answer back as Server-Sent Events; the
model is instructed to answer ONLY from the cards and to cite the card titles
it relies on. It is strictly optional:

* Configuration is server-side env only — the API key from
  ``VOLFIT_ANTHROPIC_KEY`` or ``ANTHROPIC_API_KEY`` (first non-empty), the
  model from ``VOLFIT_ASSISTANT_MODEL`` (default ``claude-opus-5``).
* The ``anthropic`` SDK is an optional dependency; without it (or without a
  key) :func:`ask_status` reports ``tier="local"`` and the router answers 503,
  so the frontend keeps its local tier.

SDK usage follows the bundled Claude API reference (claude-api README +
streaming.md + model-migration.md "Migrating to Claude Opus 5 -> New API
features"): official ``anthropic.Anthropic(api_key=...)`` client, the
``client.beta.messages.stream(...)`` context manager iterated via
``stream.text_stream``, adaptive thinking (no budget), low effort (short help
answers), and the server-side refusal fallback ``fallbacks="default"`` under
beta header ``server-side-fallback-2026-07-01`` (the ``"default"`` scalar form
requires the beta namespace and this exact header). ``stop_reason ==
"refusal"`` on the final message means the whole chain declined.

Streaming contract (one ``data: {json}`` line per event):
``{"type":"delta","text":...}`` per text chunk, then
``{"type":"done","tier":"claude","model":...,"refused":bool}``; on any failure
``{"type":"error","message":...}`` and the stream ends — nothing is raised
mid-stream (the HTTP response is already 200 by then).

Tests inject a stub client through the module-level ``_client_factory``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

try:  # optional dependency — the app runs without it (tier "local")
    import anthropic
except ImportError:  # pragma: no cover - exercised only where the SDK is absent
    anthropic = None  # type: ignore[assignment]

#: Env vars consulted for the API key, first non-empty wins.
KEY_ENV_VARS: tuple[str, ...] = ("VOLFIT_ANTHROPIC_KEY", "ANTHROPIC_API_KEY")
MODEL_ENV_VAR = "VOLFIT_ASSISTANT_MODEL"
DEFAULT_MODEL = "claude-opus-5"
MAX_TOKENS = 2048
#: Beta header gating the ``fallbacks="default"`` scalar form (model-migration.md).
FALLBACK_BETA = "server-side-fallback-2026-07-01"

#: Request clamps — validators truncate rather than reject.
MAX_CARDS = 12
MAX_CARD_TEXT = 4000
MAX_HISTORY = 8
MAX_TURN_TEXT = 4000

SYSTEM_PROMPT = (
    "You are the VolFit in-app help assistant (\"Ask @Vol-Fitter\"). VolFit is an "
    "implied-volatility surface fitter with a graph extrapolator; the user is "
    "inside the app right now.\n\n"
    "Answer ONLY from the help cards supplied in the user's message (excerpts of "
    "VolFit's command reference, settings reference and documentation). Rules:\n"
    "1. Be concrete and short: at most 200 words unless the user explicitly asks "
    "for detail.\n"
    "2. Use the app's own vocabulary exactly as the cards do (lens, node, editor "
    "group, light/dark nodes, prior, calibrate, quote band, ...).\n"
    "3. Cite every card you rely on by its title, each on its own line at the "
    "end, in the form \"— see: <card title>\".\n"
    "4. When the cards do not cover the question, say so plainly and point to "
    "the closest page: Command reference, Settings reference, or Documentation.\n"
    "5. Never invent settings, commands, shortcuts or menu items that do not "
    "appear in the cards.\n"
    "Plain prose, short bullet lists when helpful, no headings."
)


# -- request / response models ------------------------------------------------


class HelpCard(BaseModel):
    """A help card retrieved locally by the frontend (the model's only source)."""

    id: str
    kind: str
    title: str
    text: str
    link: str | None = None

    @field_validator("text")
    @classmethod
    def _clamp_text(cls, value: str) -> str:
        return value[:MAX_CARD_TEXT]


class HelpAskContext(BaseModel):
    """Where the user is in the app when asking (all optional)."""

    lens: str | None = None
    ticker: str | None = None
    expiry: str | None = None
    page: str | None = None


class HelpTurn(BaseModel):
    """A prior conversation turn."""

    role: Literal["user", "assistant"]
    text: str

    @field_validator("text")
    @classmethod
    def _clamp_text(cls, value: str) -> str:
        return value[:MAX_TURN_TEXT]


class HelpAskRequest(BaseModel):
    """``POST /help/ask`` body."""

    question: str = Field(min_length=1, max_length=2000)
    cards: list[HelpCard] = Field(default_factory=list)
    context: HelpAskContext | None = None
    history: list[HelpTurn] = Field(default_factory=list)

    @field_validator("cards")
    @classmethod
    def _cap_cards(cls, value: list[HelpCard]) -> list[HelpCard]:
        return value[:MAX_CARDS]

    @field_validator("history")
    @classmethod
    def _cap_history(cls, value: list[HelpTurn]) -> list[HelpTurn]:
        return value[-MAX_HISTORY:]  # keep the most recent turns


class HelpAskStatus(BaseModel):
    """``GET /help/ask/status`` — which tier the frontend should use."""

    tier: Literal["claude", "local"]
    configured: bool
    sdkInstalled: bool
    model: str | None = None


# -- configuration -----------------------------------------------------------


def _api_key() -> str | None:
    for var in KEY_ENV_VARS:
        value = os.environ.get(var, "").strip()
        if value:
            return value
    return None


def model_name() -> str:
    return os.environ.get(MODEL_ENV_VAR, "").strip() or DEFAULT_MODEL


def ask_status() -> HelpAskStatus:
    """Tier ``"claude"`` only when a key is set AND the SDK imports."""
    configured = _api_key() is not None
    sdk_installed = anthropic is not None
    claude = configured and sdk_installed
    return HelpAskStatus(
        tier="claude" if claude else "local",
        configured=configured,
        sdkInstalled=sdk_installed,
        model=model_name() if claude else None,
    )


def _default_client_factory(api_key: str) -> Any:
    """Build the official client with an injected key (README, Client Initialization)."""
    return anthropic.Anthropic(api_key=api_key)


#: Injectable for tests: a callable ``(api_key) -> client`` whose
#: ``client.beta.messages.stream(**kw)`` returns a context manager exposing an
#: iterable ``text_stream`` and ``get_final_message()``.
_client_factory: Callable[[str], Any] = _default_client_factory


# -- prompt assembly ---------------------------------------------------------


def _context_line(ctx: HelpAskContext | None) -> str:
    if ctx is None:
        return ""
    parts = [f"{k}={v}" for k, v in ctx.model_dump().items() if v]
    return f"Where the user is: {', '.join(parts)}\n\n" if parts else ""


def _cards_block(cards: list[HelpCard]) -> str:
    """The cards as a fenced context block (a 5-backtick fence, so a card whose
    text itself contains a triple-backtick code fence cannot close it)."""
    if not cards:
        return "`````help-cards\n(no help cards matched this question)\n`````\n\n"
    rows = []
    for i, card in enumerate(cards, start=1):
        head = f"[{i}] {card.title}  (kind: {card.kind}"
        head += f", link: {card.link})" if card.link else ")"
        rows.append(f"{head}\n{card.text.strip()}")
    return "`````help-cards\n" + "\n\n".join(rows) + "\n`````\n\n"


def _build_messages(req: HelpAskRequest) -> list[dict[str, str]]:
    """Prior turns as messages (first must be ``user``), then the cards + question."""
    turns = [t for t in req.history if t.text.strip()]
    while turns and turns[0].role != "user":
        turns.pop(0)
    messages = [{"role": t.role, "content": t.text} for t in turns]
    user = _context_line(req.context) + _cards_block(req.cards) + f"Question: {req.question.strip()}"
    messages.append({"role": "user", "content": user})
    return messages


# -- streaming ---------------------------------------------------------------


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _error_message(exc: BaseException) -> str:
    """Short user-facing text for the documented exception chain."""
    if isinstance(exc, anthropic.AuthenticationError):
        return "The assistant's API key was rejected (check VOLFIT_ANTHROPIC_KEY on the server)."
    if isinstance(exc, anthropic.RateLimitError):
        return "The assistant is rate-limited right now — try again in a moment."
    if isinstance(exc, anthropic.APIStatusError):
        if exc.status_code >= 500:
            return f"Assistant service error ({exc.status_code}) — retry later."
        return f"Assistant API error ({exc.status_code}): {exc.message}"
    if isinstance(exc, anthropic.APIConnectionError):
        return "Could not connect to the assistant service (network error)."
    return f"Assistant failed: {type(exc).__name__}."


REFUSAL_NOTE = (
    "\n\n_The assistant declined to answer this question. Try rephrasing it, or "
    "browse the Documentation page._"
)


def stream_answer(req: HelpAskRequest) -> Iterator[str]:
    """Yield SSE lines for one question. Never raises — failures become an
    ``error`` event (the HTTP status is already committed when this runs)."""
    key = _api_key()
    if anthropic is None or key is None:
        yield _sse({"type": "error", "message": "assistant not configured on the server"})
        return

    model = model_name()
    try:
        client = _client_factory(key)
        # Shape: streaming.md Quick Start + README Extended Thinking (adaptive,
        # effort) + model-migration.md New API features (fallbacks "default").
        with client.beta.messages.stream(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=_build_messages(req),
            thinking={"type": "adaptive"},
            output_config={"effort": "low"},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            for text in stream.text_stream:
                if text:
                    yield _sse({"type": "delta", "text": text})
            final = stream.get_final_message()
    except Exception as exc:  # noqa: BLE001 - every failure must become an event
        yield _sse({"type": "error", "message": _error_message(exc)})
        return

    refused = getattr(final, "stop_reason", None) == "refusal"
    if refused:
        yield _sse({"type": "delta", "text": REFUSAL_NOTE})
    served_model = getattr(final, "model", None) or model
    yield _sse({"type": "done", "tier": "claude", "model": served_model, "refused": refused})
