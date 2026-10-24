"""Schemas: the example bundle validates, the validator catches broken citations, Stamp and Verdict hold their shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from judge.schemas import Decision, EvidenceBundle, SlotWrite, Stamp, Verdict

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "examples" / "bybit.bundle.json"


@pytest.fixture
def raw() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


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


def test_stamp_roundtrip() -> None:
    s = Stamp(safeTxHash="0x" + "00" * 32, forkBlock=21895238, judgeVersion="0x" + "cf" * 32)
    assert Stamp.model_validate(s.model_dump()) == s


def test_verdict_decision_enum() -> None:
    v = Verdict(reasoning="delegatecall to an unverified contract", decision=Decision.REJECT)
    assert v.decision == "REJECT"
    assert list(Verdict.model_fields)[0] == "reasoning"


@pytest.mark.parametrize("reply", ["erc20_approval", "approval", "ERC20", "approve", None])
def test_permission_kind_reads_any_reply_as_the_one_legal_value(reply) -> None:
    """`kind` has one legal value; a model that writes anything else costs no schema retry."""
    from judge.schemas import ObservedPermissionChange, PermissionChange

    fwd = PermissionChange(kind=reply, asset="USDC", owner_name="Safe", spender_name="Uniswap router",
                           amount_human="1,000 USDC", cites="Approve the Uniswap router")
    obs = ObservedPermissionChange(kind=reply, asset="USDC", owner_name="Safe", spender_name="Uniswap router",
                                   amount_human="1,000 USDC", cites=["e1"])
    assert fwd.kind == obs.kind == "erc20_approval"
