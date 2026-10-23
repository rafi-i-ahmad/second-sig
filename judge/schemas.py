"""Shared pydantic models.

EvidenceBundle and Stamp are the contract between the AI side and the chain side.
Do not change either without both owners agreeing (see CLAUDE.md).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class EvidenceBundle(BaseModel):
    """Layer 1 output: everything the judge knows about a proposal, from the fork."""

    safe_tx_hash: str
    safe_address: str
    chain_id: int
    fork_block: int
    description: str = Field(description="Untrusted text authored by the proposer.")
    # TODO(both): calldata, decoded calls, trace entries, storage diffs, rule hits.


class Movement(BaseModel):
    """One asset moving between two named parties, as the description implies it."""

    asset: str = Field(description="Ticker as written, e.g. 'ETH', 'USDC'.")
    amount_human: str | None = Field(
        description="Amount with unit as written, e.g. '2,500 USDC'. None if the text fixes no amount."
    )
    from_name: str = Field(description="Sender by address-book name; 'Safe' for the proposing Safe.")
    to_name: str = Field(description="Recipient by address-book name; 'Safe' for the proposing Safe.")
    cites: str = Field(description="The phrase in the description this follows from.")


class PermissionChange(BaseModel):
    """A token allowance the description grants to a spender."""

    kind: Literal["erc20_approval"] = "erc20_approval"
    asset: str
    owner_name: str = Field(description="Who grants the allowance; normally 'Safe'.")
    spender_name: str = Field(description="Spender by address-book name.")
    amount_human: str = Field(description="e.g. '1,000 USDC' or 'unlimited'.")
    cites: str


class SafeConfigChange(BaseModel):
    """A change to the Safe's own owners or threshold."""

    kind: Literal["add_owner", "remove_owner", "swap_owner", "change_threshold"]
    owner_name: str | None = Field(default=None, description="The owner added or removed, if any.")
    threshold_after: int | None = Field(default=None, description="Threshold once applied, if stated or implied.")
    cites: str

    @model_validator(mode="after")
    def _not_empty(self) -> "SafeConfigChange":
        """An entry that names no owner and no threshold claims nothing; reject it."""
        if self.kind == "change_threshold" and self.threshold_after is None:
            raise ValueError("change_threshold needs threshold_after")
        if self.kind in ("add_owner", "remove_owner", "swap_owner") and not self.owner_name:
            raise ValueError(f"{self.kind} needs owner_name")
        return self


class ExpectedEffects(BaseModel):
    """Forward pass: what the description says should happen. Never sees the trace."""

    reasoning: str = Field(description="Work through the description step by step first.")
    movements: list[Movement] = Field(default_factory=list)
    permission_changes: list[PermissionChange] = Field(default_factory=list)
    safe_config_changes: list[SafeConfigChange] = Field(default_factory=list)
    nothing_else: bool = Field(
        description="True if the description licenses nothing beyond the items above."
    )
    assumptions: list[str] = Field(default_factory=list)
    questions_for_human: list[str] = Field(
        default_factory=list,
        description="Anything the description leaves open that a signer should settle.",
    )
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def _empty_form_must_ask(self) -> "ExpectedEffects":
        """A description that licenses nothing must raise at least one question."""
        if not (self.movements or self.permission_changes or self.safe_config_changes):
            if not self.questions_for_human:
                raise ValueError(
                    "no movements, permission_changes or safe_config_changes: "
                    "questions_for_human must then contain at least one question for the signer"
                )
        return self


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
