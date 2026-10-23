"""Gemini Interactions API adapter.

Every model call in Second Sig goes through this module. It is the only place that
talks to google-genai.

Guarantees:
- Typed output: the model is forced to JSON matching a pydantic schema, parsed with
  ``model_validate_json``. One retry on a validation error, then ``ModelFormError``.
- Timeouts and API errors surface as ``ModelUnavailable``.
- Every call, success or failure, appends one line to ``logs/calls.jsonl``:
  timestamp, model, thinking level, sha256 of system+user, interaction id, parsed
  output or error, latency in ms. The raw prompt and the API key are never logged.
- No tools are offered to the model here. Read-only tool loops, when added, run in
  separate calls (see CLAUDE.md, Gemini notes).

SDK facts (google-genai 2.33.0, confirmed from the installed package):
- ``client.interactions.create(model=, input=, system_instruction=, generation_config=,
  response_format=, response_mime_type=, stream=)``.
- ``generation_config["thinking_level"]`` is one of minimal, low, medium, high.
  ``temperature`` is deprecated on this API.
- ``response_format`` is ``{"type": "text", "mime_type": "application/json",
  "schema": <json schema>}`` and ``response_mime_type`` must also be set.
- Non-streamed responses expose ``.id`` and ``.output_text``.
- Streamed responses yield ``step.delta`` events whose ``delta.type`` is ``text`` or
  ``thought_summary``, then ``interaction.completed`` carrying the interaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, TypeVar

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ThinkingLevel = Literal["low", "medium", "high"]
T = TypeVar("T", bound=BaseModel)

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = REPO_ROOT / "logs" / "calls.jsonl"

DEFAULT_TIMEOUT_S = 120.0
_VALIDATION_RETRIES = 1


class ModelUnavailable(Exception):
    """The API could not be reached or returned an error."""


class ModelFormError(Exception):
    """The model's output did not validate against the schema after the retry."""


@dataclass(frozen=True)
class StreamEvent:
    kind: Literal["thought", "text", "done"]
    delta: str | None = None
    result: BaseModel | None = None
    interaction_id: str | None = None


# --------------------------------------------------------------------------- client


_client: Any | None = None


def get_client() -> Any:
    """Return a cached google-genai client. Tests monkeypatch this function."""
    global _client
    if _client is None:
        load_dotenv(REPO_ROOT / ".env")
        if not os.environ.get("GEMINI_API_KEY"):
            raise ModelUnavailable("GEMINI_API_KEY is not set")
        from google import genai

        _client = genai.Client()
    return _client


# --------------------------------------------------------------------------- schema


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Inline ``$ref`` pointers and drop ``title`` so the schema is self-contained."""
    if isinstance(node, dict):
        if "$ref" in node:
            ref = node["$ref"]
            if not ref.startswith("#/$defs/"):
                raise ValueError(f"unsupported $ref: {ref}")
            target = defs[ref[len("#/$defs/") :]]
            merged = {**target, **{k: v for k, v in node.items() if k != "$ref"}}
            return _inline_refs(merged, defs)
        return {
            k: _inline_refs(v, defs)
            for k, v in node.items()
            if k not in ("$defs", "title")
        }
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def json_schema_for(schema: type[BaseModel]) -> dict[str, Any]:
    raw = schema.model_json_schema()
    return _inline_refs(raw, raw.get("$defs", {}))


# --------------------------------------------------------------------------- request


def _request_kwargs(
    model: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    thinking: ThinkingLevel,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": user,
        "system_instruction": system,
        "generation_config": {
            "thinking_level": thinking,
            "thinking_summaries": "auto",
        },
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": json_schema_for(schema),
        },
        "response_mime_type": "application/json",
        "stream": stream,
    }


def _prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n" + user).encode("utf-8")).hexdigest()


def _is_api_error(exc: BaseException) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError, TimeoutError, ConnectionError)):
        return True
    for cls in type(exc).__mro__:
        if cls.__module__.startswith("google.genai") and cls.__name__.endswith("Error"):
            return True
    return False


def _validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return exc.errors(include_url=False, include_input=False, include_context=False)


def _retry_prompt(user: str, errors: list[dict[str, Any]]) -> str:
    return (
        user
        + "\n\nYour previous reply did not validate against the required JSON schema. "
        + "Errors:\n"
        + json.dumps(errors, indent=2)
        + "\nReply again with JSON that satisfies the schema exactly."
    )


# --------------------------------------------------------------------------- logging


def _log(
    *,
    model: str,
    thinking: str,
    prompt_sha256: str,
    interaction_id: str | None,
    latency_ms: int,
    status: Literal["ok", "form_error", "unavailable"],
    output: dict[str, Any] | None = None,
    error: Any = None,
    attempt: int = 0,
    streamed: bool = False,
) -> None:
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "thinking": thinking,
        "prompt_sha256": prompt_sha256,
        "interaction_id": interaction_id,
        "status": status,
        "attempt": attempt,
        "streamed": streamed,
        "latency_ms": latency_ms,
        "output": output,
        "error": error,
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, default=str) + "\n")


# --------------------------------------------------------------------------- output


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text_from_content(content: Any) -> str:
    """Concatenate the text parts of a content list (or single content block)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    items = content if isinstance(content, list) else [content]
    parts: list[str] = []
    for item in items:
        if _get(item, "type") in (None, "text") and isinstance(_get(item, "text"), str):
            parts.append(_get(item, "text"))
    return "".join(parts)


def _output_text(interaction: Any) -> str:
    text = _get(interaction, "output_text")
    if isinstance(text, str) and text:
        return text
    parts: list[str] = []
    for step in _get(interaction, "steps") or []:
        if _get(step, "type") == "model_output":
            parts.append(_text_from_content(_get(step, "content")))
    return "".join(parts)


# --------------------------------------------------------------------------- public API


def complete(
    model: str,
    system: str,
    user: str,
    schema: type[T],
    thinking: ThinkingLevel = "low",
) -> tuple[T, str]:
    """One typed call. Returns the parsed model instance and the interaction id."""
    client = get_client()
    prompt_sha = _prompt_hash(system, user)
    prompt = user

    for attempt in range(_VALIDATION_RETRIES + 1):
        kwargs = _request_kwargs(model, system, prompt, schema, thinking, stream=False)
        t0 = time.perf_counter()
        try:
            interaction = client.interactions.create(timeout=DEFAULT_TIMEOUT_S, **kwargs)
        except Exception as exc:
            if not _is_api_error(exc):
                raise
            _log(
                model=model, thinking=thinking, prompt_sha256=prompt_sha,
                interaction_id=None, latency_ms=_ms(t0), status="unavailable",
                error=f"{type(exc).__name__}: {exc}", attempt=attempt,
            )
            raise ModelUnavailable(f"{type(exc).__name__}: {exc}") from exc

        latency = _ms(t0)
        interaction_id = _get(interaction, "id") or ""
        try:
            parsed = schema.model_validate_json(_output_text(interaction))
        except ValidationError as exc:
            errors = _validation_errors(exc)
            _log(
                model=model, thinking=thinking, prompt_sha256=prompt_sha,
                interaction_id=interaction_id, latency_ms=latency, status="form_error",
                error=errors, attempt=attempt,
            )
            if attempt < _VALIDATION_RETRIES:
                prompt = _retry_prompt(user, errors)
                continue
            raise ModelFormError(
                f"output failed validation after {attempt + 1} attempts "
                f"(interaction {interaction_id}): {errors}"
            ) from exc

        _log(
            model=model, thinking=thinking, prompt_sha256=prompt_sha,
            interaction_id=interaction_id, latency_ms=latency, status="ok",
            output=parsed.model_dump(mode="json"), attempt=attempt,
        )
        return parsed, interaction_id

    raise AssertionError("unreachable")


def stream(
    model: str,
    system: str,
    user: str,
    schema: type[T],
    thinking: ThinkingLevel = "low",
) -> Iterator[StreamEvent]:
    """Streamed variant. Yields thought and text deltas, then one ``done`` event.

    The streamed path does not retry on a validation error: the caller has already
    seen the partial text, so it raises ``ModelFormError`` directly.
    """
    client = get_client()
    prompt_sha = _prompt_hash(system, user)
    kwargs = _request_kwargs(model, system, user, schema, thinking, stream=True)

    text_parts: list[str] = []
    interaction_id: str | None = None
    completed: Any = None
    t0 = time.perf_counter()

    try:
        events = client.interactions.create(timeout=DEFAULT_TIMEOUT_S, **kwargs)
        for event in events:
            event_type = _get(event, "event_type")
            if event_type == "step.delta":
                delta = _get(event, "delta")
                delta_type = _get(delta, "type")
                if delta_type == "text":
                    piece = _get(delta, "text") or ""
                    text_parts.append(piece)
                    yield StreamEvent(kind="text", delta=piece)
                elif delta_type == "thought_summary":
                    piece = _text_from_content(_get(delta, "content"))
                    if piece:
                        yield StreamEvent(kind="thought", delta=piece)
            elif event_type == "interaction.completed":
                completed = _get(event, "interaction")
                interaction_id = _get(completed, "id")
            elif event_type == "error":
                raise ModelUnavailable(f"stream error event: {_get(event, 'error')}")
            elif event_type == "interaction.created":
                interaction_id = interaction_id or _get(_get(event, "interaction"), "id")
    except ModelUnavailable as exc:
        _log(
            model=model, thinking=thinking, prompt_sha256=prompt_sha,
            interaction_id=interaction_id, latency_ms=_ms(t0), status="unavailable",
            error=str(exc), streamed=True,
        )
        raise
    except Exception as exc:
        if not _is_api_error(exc):
            raise
        _log(
            model=model, thinking=thinking, prompt_sha256=prompt_sha,
            interaction_id=interaction_id, latency_ms=_ms(t0), status="unavailable",
            error=f"{type(exc).__name__}: {exc}", streamed=True,
        )
        raise ModelUnavailable(f"{type(exc).__name__}: {exc}") from exc

    latency = _ms(t0)
    full_text = "".join(text_parts) or (_output_text(completed) if completed is not None else "")
    try:
        parsed = schema.model_validate_json(full_text)
    except ValidationError as exc:
        errors = _validation_errors(exc)
        _log(
            model=model, thinking=thinking, prompt_sha256=prompt_sha,
            interaction_id=interaction_id, latency_ms=latency, status="form_error",
            error=errors, streamed=True,
        )
        raise ModelFormError(
            f"streamed output failed validation (interaction {interaction_id}): {errors}"
        ) from exc

    _log(
        model=model, thinking=thinking, prompt_sha256=prompt_sha,
        interaction_id=interaction_id, latency_ms=latency, status="ok",
        output=parsed.model_dump(mode="json"), streamed=True,
    )
    yield StreamEvent(kind="done", result=parsed, interaction_id=interaction_id)


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
