"""EvidenceBundle: the example bundle validates, and the validator catches broken citations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from judge.schemas import EvidenceBundle, SlotWrite

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "examples" / "bybit.bundle.json"


@pytest.fixture
def raw() -> dict:
    return json.loads(EXAMPLE.read_text())


def test_bybit_example_validates(raw: dict) -> None:
    b = EvidenceBundle.model_validate(raw)
    assert {h.rule for h in b.floor_hits} == {
        "delegatecall_not_allowlisted",
        "protected_slot_write",
        "unverified_code",
    }
    hijack = b.entry("s0")
    assert isinstance(hijack, SlotWrite) and hijack.label == "Safe.singleton"
    assert hijack.after.endswith("bdd077f651ebe7f7b3ce16fe5f2b025be2969516")
    assert b.entry("c4").kind == "DELEGATECALL"
    assert b.entry("nope") is None


def test_round_trip(raw: dict) -> None:
    b = EvidenceBundle.model_validate(raw)
    assert EvidenceBundle.model_validate_json(b.model_dump_json()) == b


def test_duplicate_ids_rejected(raw: dict) -> None:
    raw["storage_diff"][1]["id"] = "s0"
    with pytest.raises(ValidationError, match="duplicate evidence ids"):
        EvidenceBundle.model_validate(raw)


def test_floor_hit_must_cite_real_entries(raw: dict) -> None:
    raw["floor_hits"][0]["cites"] = ["c99"]
    with pytest.raises(ValidationError, match="cites unknown entries"):
        EvidenceBundle.model_validate(raw)


def test_floor_hit_needs_a_citation(raw: dict) -> None:
    raw["floor_hits"][0]["cites"] = []
    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(raw)


def test_unknown_floor_rule_rejected(raw: dict) -> None:
    raw["floor_hits"][0]["rule"] = "model_thinks_its_bad"
    with pytest.raises(ValidationError):
        EvidenceBundle.model_validate(raw)


def test_event_must_point_at_a_call(raw: dict) -> None:
    raw["events"][0]["call_id"] = "c99"
    with pytest.raises(ValidationError, match="unknown call"):
        EvidenceBundle.model_validate(raw)
