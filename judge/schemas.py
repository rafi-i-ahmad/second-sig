"""Shared pydantic models.

EvidenceBundle and Stamp are the contract between the AI side and the chain side.
Do not change either without both owners agreeing (see CLAUDE.md).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EvidenceBundle(BaseModel):
    """Layer 1 output: everything the judge knows about a proposal, from the fork."""

    safe_tx_hash: str
    safe_address: str
    chain_id: int
    fork_block: int
    description: str = Field(description="Untrusted text authored by the proposer.")
    # TODO(both): calldata, decoded calls, trace entries, storage diffs, rule hits.


class ExpectedEffects(BaseModel):
    """Forward pass: what the description says should happen. Never sees the trace."""


class Narration(BaseModel):
    """Backward pass: what the trace shows happened. Never sees the description."""


class Classification(BaseModel):
    """Leftovers pass: classification of unexplained effects."""


class ProbeHypothesis(BaseModel):
    """A probe proposed by the model; code runs it and records the result."""


class HumanQuestion(BaseModel):
    """An item the judge could not resolve and must surface to a human."""


class Decision(str, Enum):
    APPROVE = "APPROVE"
    ASK = "ASK"
    REJECT = "REJECT"


class Verdict(BaseModel):
    """Layer 5 output: a pure function of the evidence bundle plus checked model forms."""

    decision: Decision
    reasons: list[str] = Field(default_factory=list)


class Stamp(BaseModel):
    """EIP-712 payload signed by the judge key. Field names match the Solidity struct."""

    safeTxHash: str
    forkBlock: int
    judgeVersion: str
