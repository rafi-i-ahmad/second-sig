"""verdict.py: a floor hit forces REJECT whatever the model said, and every other gap fails to ASK."""

from __future__ import annotations

from pathlib import Path

import pytest

from judge import verdict
from judge.schemas import Decision, EvidenceBundle, Verdict
from tests.test_evidence import BENIGN_CASES

BUNDLES = Path(__file__).resolve().parent.parent / "fixtures" / "bundles"


def load(case: str) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json((BUNDLES / f"{case}.bundle.json").read_text(encoding="utf-8"))


def model_says(decision: Decision) -> Verdict:
    return Verdict(reasoning="the model's reasoning", decision=decision, reasons=["model reason"])


# --------------------------------------------------------------------------- floor


def test_bybit_is_rejected_by_the_floor_with_an_explanation() -> None:
    v = verdict.decide(load("demo_bybit"))
    assert v.decision == Decision.REJECT
    assert {h.rule for h in v.floor_hits} == {"delegatecall_not_allowlisted", "protected_slot_write", "unverified_code"}
    assert v.reasoning.startswith("Rejected by the hard floor before any model ran. 3 hard rule hits")
    # each hit gets the rule's paragraph plus what the evidence showed and where
    assert "Bybit attack" in v.reasoning and "master copy" in v.reasoning and "not verified on Etherscan" in v.reasoning
    assert "evidence c4" in v.reasoning and "evidence s0" in v.reasoning
    assert len(v.reasons) == 3 and all(":" in r for r in v.reasons)


def test_floor_beats_a_model_match() -> None:
    v = verdict.decide(load("demo_bybit"), model_says(Decision.MATCH))
    assert v.decision == Decision.REJECT
    assert "the model's reasoning" not in v.reasoning


def test_floor_is_recomputed_not_trusted() -> None:
    """A bundle whose stored floor_hits were emptied still rejects: the table re-runs the rules."""
    scrubbed = load("demo_bybit").model_copy(update={"floor_hits": []})
    assert verdict.decide(scrubbed, model_says(Decision.MATCH)).decision == Decision.REJECT


def test_every_rule_has_an_explanation() -> None:
    from typing import get_args

    from judge.schemas import FloorRule

    assert set(get_args(FloorRule)) == set(verdict.FLOOR_EXPLANATIONS)
    assert all(len(text) > 80 for text in verdict.FLOOR_EXPLANATIONS.values())


# --------------------------------------------------------------------------- fail closed


@pytest.mark.parametrize("case", BENIGN_CASES)
def test_floor_never_rejects_a_benign_case(case: str) -> None:
    """The twelve honest proposals rehearsed on the fork (24 October): owner and threshold changes,
    batches, a finite approval, a Uniswap swap. None may trip the floor; without a model they ASK."""
    v = verdict.decide(load(case))
    assert v.decision == Decision.ASK
    assert v.floor_hits == [] and "no checked model form" in v.reasons


def test_failed_rehearsal_is_ask_even_if_the_model_said_match() -> None:
    failed = load("demo_aave").model_copy(update={"execution_success": False})
    v = verdict.decide(failed, model_says(Decision.MATCH))
    assert v.decision == Decision.ASK
    assert "rehearsal did not succeed" in v.reasons


# --------------------------------------------------------------------------- the model's row


@pytest.mark.parametrize("decision", list(Decision))
def test_clean_floor_and_successful_rehearsal_take_the_model_decision(decision: Decision) -> None:
    v = verdict.decide(load("demo_aave"), model_says(decision))
    assert v.decision == decision
    assert v.reasoning == "the model's reasoning" and v.floor_hits == []
