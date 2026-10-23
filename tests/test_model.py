"""Tests for judge/model.py.

Unit tests mock the google-genai client. Live tests are marked ``live`` and run only
with ``--live`` and a GEMINI_API_KEY in the environment or .env.
"""

from __future__ import annotations

import json
import time
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import httpx
import pytest
from pydantic import BaseModel, Field

from judge import model as m

# --------------------------------------------------------------------------- schemas


class Colour(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class ThreeField(BaseModel):
    colour: Colour
    count: int
    tags: list[str]


class Finding(BaseModel):
    claim: str
    severity: Literal["low", "high"]


class Judgement(BaseModel):
    reasoning: str = Field(description="Think step by step here first.")
    verdict: Literal["MATCH", "ASK", "REJECT"]
    findings: list[Finding] = Field(default_factory=list)


# --------------------------------------------------------------------------- fakes


class FakeInteractions:
    """Stands in for client.interactions. ``responses`` is a queue of outputs.

    Each queued item is a string (output_text), an Exception (raised), or a list of
    SSE-like events (returned as an iterator for stream=True).
    """

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, list):
            return iter(item)
        return SimpleNamespace(id=f"int-{len(self.calls)}", output_text=item, steps=None)


def fake_client(*responses: Any) -> tuple[SimpleNamespace, FakeInteractions]:
    inter = FakeInteractions(list(responses))
    return SimpleNamespace(interactions=inter), inter


def text_delta(text: str) -> SimpleNamespace:
    return SimpleNamespace(event_type="step.delta", delta=SimpleNamespace(type="text", text=text))


def thought_delta(text: str) -> SimpleNamespace:
    content = [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(
        event_type="step.delta", delta=SimpleNamespace(type="thought_summary", content=content)
    )


def completed(interaction_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        event_type="interaction.completed",
        interaction=SimpleNamespace(id=interaction_id, steps=None, output_text=None),
    )


@pytest.fixture
def log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "calls.jsonl"
    monkeypatch.setattr(m, "LOG_PATH", path)
    return path


@pytest.fixture
def use_client(monkeypatch: pytest.MonkeyPatch):
    def _install(*responses: Any) -> FakeInteractions:
        client, inter = fake_client(*responses)
        monkeypatch.setattr(m, "get_client", lambda: client)
        return inter

    return _install


def read_log(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --------------------------------------------------------------------------- unit tests


def test_valid_json_parses(use_client, log_path: Path) -> None:
    inter = use_client('{"colour": "red", "count": 3, "tags": ["a", "b"]}')
    parsed, interaction_id = m.complete("fake-model", "sys", "user", ThreeField, "low")

    assert parsed == ThreeField(colour=Colour.RED, count=3, tags=["a", "b"])
    assert interaction_id == "int-1"
    assert len(inter.calls) == 1
    kw = inter.calls[0]
    assert kw["model"] == "fake-model"
    assert kw["system_instruction"] == "sys"
    assert kw["input"] == "user"
    assert kw["generation_config"]["thinking_level"] == "low"
    assert kw["response_format"]["type"] == "text"
    assert kw["response_format"]["mime_type"] == "application/json"
    assert kw["response_mime_type"] == "application/json"
    assert kw["stream"] is False
    schema = kw["response_format"]["schema"]
    assert schema["properties"]["colour"]["enum"] == ["red", "green", "blue"]
    assert "$defs" not in schema


def test_invalid_json_retries_once_then_raises(use_client, log_path: Path) -> None:
    inter = use_client("not json at all", '{"colour": "purple", "count": 1, "tags": []}')
    with pytest.raises(m.ModelFormError):
        m.complete("fake-model", "sys", "user", ThreeField)

    assert len(inter.calls) == 2
    retry_input = inter.calls[1]["input"]
    assert retry_input.startswith("user")
    assert "did not validate" in retry_input
    assert "json_invalid" in retry_input or "JSON" in retry_input
    statuses = [line["status"] for line in read_log(log_path)]
    assert statuses == ["form_error", "form_error"]


def test_invalid_then_valid_succeeds_on_retry(use_client, log_path: Path) -> None:
    inter = use_client('{"colour": "red"}', '{"colour": "blue", "count": 0, "tags": []}')
    parsed, interaction_id = m.complete("fake-model", "sys", "user", ThreeField)

    assert parsed.colour == Colour.BLUE
    assert interaction_id == "int-2"
    assert len(inter.calls) == 2
    assert [line["status"] for line in read_log(log_path)] == ["form_error", "ok"]


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("refused"),
        TimeoutError("slow"),
    ],
)
def test_api_exception_raises_model_unavailable(use_client, log_path: Path, exc: Exception) -> None:
    use_client(exc)
    with pytest.raises(m.ModelUnavailable):
        m.complete("fake-model", "sys", "user", ThreeField)
    (line,) = read_log(log_path)
    assert line["status"] == "unavailable"
    assert line["interaction_id"] is None


def test_genai_api_error_raises_model_unavailable(use_client, log_path: Path) -> None:
    from google.genai import errors as genai_errors

    response = httpx.Response(503, request=httpx.Request("POST", "https://x"), json={"error": {"message": "down"}})
    exc = genai_errors.APIError(503, {"error": {"message": "down"}}, response)
    use_client(exc)
    with pytest.raises(m.ModelUnavailable):
        m.complete("fake-model", "sys", "user", ThreeField)


def test_non_api_exception_propagates(use_client, log_path: Path) -> None:
    use_client(KeyError("programming error"))
    with pytest.raises(KeyError):
        m.complete("fake-model", "sys", "user", ThreeField)


def test_log_line_fields_and_no_secrets(use_client, log_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "AIzaSy-FAKE-KEY-0123456789"
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    system = "SYSTEM-SENTINEL-77ab"
    user = "USER-SENTINEL-91cd describe the transfer"
    use_client('{"colour": "green", "count": 2, "tags": ["x"]}')

    parsed, interaction_id = m.complete("fake-model", system, user, ThreeField, "medium")

    raw = log_path.read_text(encoding="utf-8")
    assert raw.count("\n") == 1
    (line,) = read_log(log_path)
    expected_keys = {
        "ts", "model", "thinking", "prompt_sha256", "interaction_id", "status",
        "attempt", "streamed", "latency_ms", "output", "error",
    }
    assert expected_keys <= set(line)
    assert line["model"] == "fake-model"
    assert line["thinking"] == "medium"
    assert line["interaction_id"] == interaction_id
    assert line["status"] == "ok"
    assert isinstance(line["latency_ms"], int)
    assert len(line["prompt_sha256"]) == 64
    assert line["prompt_sha256"] == m._prompt_hash(system, user)
    assert line["output"] == parsed.model_dump(mode="json")
    assert secret not in raw
    assert "SYSTEM-SENTINEL" not in raw
    assert "USER-SENTINEL" not in raw


def test_failure_log_has_no_prompt(use_client, log_path: Path) -> None:
    use_client("garbage", "still garbage")
    with pytest.raises(m.ModelFormError):
        m.complete("fake-model", "SYS-SECRET-TEXT", "USER-SECRET-TEXT", ThreeField)
    raw = log_path.read_text(encoding="utf-8")
    assert "SYS-SECRET-TEXT" not in raw
    assert "USER-SECRET-TEXT" not in raw


def test_stream_yields_text_deltas_then_done(use_client, log_path: Path) -> None:
    payload = '{"reasoning": "the recipient differs", "verdict": "REJECT", "findings": []}'
    half = len(payload) // 2
    inter = use_client(
        [
            thought_delta("Comparing recipient... "),
            text_delta(payload[:half]),
            text_delta(payload[half:]),
            completed("int-stream-1"),
        ]
    )

    events = list(m.stream("fake-model", "sys", "user", Judgement, "high"))

    assert inter.calls[0]["stream"] is True
    assert inter.calls[0]["generation_config"]["thinking_level"] == "high"
    kinds = [e.kind for e in events]
    assert kinds == ["thought", "text", "text", "done"]
    assert "".join(e.delta for e in events if e.kind == "text") == payload
    done = events[-1]
    assert isinstance(done.result, Judgement)
    assert done.result.verdict == "REJECT"
    assert done.interaction_id == "int-stream-1"
    (line,) = read_log(log_path)
    assert line["status"] == "ok" and line["streamed"] is True
    assert line["interaction_id"] == "int-stream-1"


def test_stream_invalid_json_raises_form_error(use_client, log_path: Path) -> None:
    use_client([text_delta("{oops"), completed("int-stream-2")])
    with pytest.raises(m.ModelFormError):
        list(m.stream("fake-model", "sys", "user", Judgement))
    (line,) = read_log(log_path)
    assert line["status"] == "form_error"


def test_stream_api_error_raises_unavailable(use_client, log_path: Path) -> None:
    use_client(httpx.ReadTimeout("slow"))
    with pytest.raises(m.ModelUnavailable):
        list(m.stream("fake-model", "sys", "user", Judgement))


def test_stream_error_event_raises_unavailable(use_client, log_path: Path) -> None:
    use_client([SimpleNamespace(event_type="error", error={"message": "quota"})])
    with pytest.raises(m.ModelUnavailable):
        list(m.stream("fake-model", "sys", "user", Judgement))


def test_json_schema_inlines_nested_models() -> None:
    schema = m.json_schema_for(Judgement)
    assert "$defs" not in json.dumps(schema)
    item = schema["properties"]["findings"]["items"]
    assert item["properties"]["severity"]["enum"] == ["low", "high"]
    assert list(schema["properties"]) == ["reasoning", "verdict", "findings"]


def test_get_client_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(m, "_client", None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(m, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(m.ModelUnavailable):
        m.get_client()


# --------------------------------------------------------------------------- live tests

FLASH = "gemini-3.8-flash"
ARGON = "gemini-4-argon"

MISMATCH_SYSTEM = (
    "You compare a transaction description with the effects observed on a fork. "
    "Fill the reasoning field first, then the verdict. "
    "MATCH if the effects are exactly what the description says, "
    "ASK if you cannot tell, REJECT if the effects contradict the description."
)
MISMATCH_USER = (
    "Description: 'Send 10 USDC from the treasury to our payroll account 0xPAYROLL.'\n"
    "Observed effects on the fork: the Safe's implementation (masterCopy) slot changed "
    "to an unverified contract 0xBAD; no USDC moved; 0xPAYROLL was not touched."
)


def _report(label: str, interaction_id: str | None, t0: float) -> None:
    print(f"\n[{label}] interaction_id={interaction_id} latency_ms={int((time.perf_counter() - t0) * 1000)}")


@pytest.mark.live
def test_live_flash_three_field_schema() -> None:
    t0 = time.perf_counter()
    parsed, interaction_id = m.complete(
        FLASH,
        "Answer the question in the required JSON shape.",
        "Pick your favourite of red, green or blue, give a count of 7, and list three fruit.",
        ThreeField,
        "low",
    )
    _report("flash", interaction_id, t0)
    assert isinstance(parsed, ThreeField)
    assert parsed.colour in set(Colour)
    assert isinstance(parsed.count, int)
    assert all(isinstance(t, str) for t in parsed.tags)
    assert interaction_id


@pytest.mark.live
def test_live_argon_high_thinking_nested_schema_rejects() -> None:
    t0 = time.perf_counter()
    parsed, interaction_id = m.complete(ARGON, MISMATCH_SYSTEM, MISMATCH_USER, Judgement, "high")
    _report("argon", interaction_id, t0)
    assert isinstance(parsed, Judgement)
    assert parsed.reasoning.strip()
    assert parsed.verdict == "REJECT"
    assert interaction_id


@pytest.mark.live
def test_live_argon_stream_yields_text_before_done() -> None:
    t0 = time.perf_counter()
    events = list(m.stream(ARGON, MISMATCH_SYSTEM, MISMATCH_USER, Judgement, "low"))
    done = events[-1]
    _report("argon-stream", done.interaction_id, t0)
    kinds = [e.kind for e in events]
    assert done.kind == "done"
    assert "text" in kinds[:-1]
    assert isinstance(done.result, Judgement)
    text = "".join(e.delta for e in events if e.kind == "text")
    assert json.loads(text)["reasoning"] == done.result.reasoning
    assert done.result.reasoning.strip()
