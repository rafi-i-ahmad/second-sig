"""Shared pydantic models.

EvidenceBundle and Stamp are the contract between the AI side and the chain side.
Do not change either without both owners agreeing (see CLAUDE.md).
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------- evidence (layer 1)
#
# Addresses are EIP-55 checksummed. Bytes and storage words are 0x-prefixed lowercase hex;
# storage words are always 32 bytes. Amounts are integers in base units (wei, 1e-6 USDC).
#
# Every trace entry has an `id` that model forms cite (invariant 6): calls "c0", "c1", ...
# in pre-order, storage writes "s0", ..., balance changes "b0", ..., events "e0", ...
#
# Untrusted (invariant 7): anything an attacker could author. Here that is `description`,
# `revert_reason`, and every name that comes from verified source or token metadata
# (`Source.name`, `Source.files`, `Source.abi_json`, `Call.function`, `DecodedArg.name`,
# `Event.name`, `BalanceChange.symbol`). It reaches a model only through labeller.py.


class SafeTx(BaseModel):
    """The Safe transaction struct exactly as the owners sign it."""

    to: str
    value: int = Field(description="Wei.")
    data: str = Field(description="Calldata, 0x hex.")
    operation: Literal[0, 1] = Field(description="0 = CALL, 1 = DELEGATECALL.")
    safe_tx_gas: int = 0
    base_gas: int = 0
    gas_price: int = 0
    gas_token: str = "0x0000000000000000000000000000000000000000"
    refund_receiver: str = "0x0000000000000000000000000000000000000000"
    nonce: int


class DecodedArg(BaseModel):
    name: str | None = Field(description="Parameter name from the ABI; untrusted.")
    type: str = Field(description="Solidity type, e.g. 'address', 'uint256'.")
    value: str = Field(description="Rendered value: checksummed address, decimal integer, 0x hex.")


class Call(BaseModel):
    """One frame of the call tree, flattened in pre-order. `parent` rebuilds the tree."""

    id: str = Field(pattern=r"^c\d+$")
    parent: str | None = Field(description="Id of the calling frame; None for the top-level call.")
    depth: int
    kind: Literal["CALL", "DELEGATECALL", "STATICCALL", "CALLCODE", "CREATE", "CREATE2", "SELFDESTRUCT"]
    from_address: str
    to_address: str = Field(description="Code that runs. For DELEGATECALL, not whose storage changes.")
    storage_context: str = Field(description="Whose storage and balance this frame acts on.")
    value: int = Field(default=0, description="Wei.")
    input: str = Field(description="Calldata, 0x hex.")
    selector: str | None = Field(default=None, description="First 4 bytes of input; None if shorter.")
    function: str | None = Field(default=None, description="Decoded signature, e.g. 'transfer(address,uint256)'.")
    args: list[DecodedArg] = Field(default_factory=list)
    success: bool
    revert_reason: str | None = Field(default=None, description="Decoded revert string; untrusted.")


class SlotWrite(BaseModel):
    """A storage slot whose value differs after the transaction."""

    id: str = Field(pattern=r"^s\d+$")
    contract: str = Field(description="Whose storage: the proxy for proxied contracts.")
    slot: str = Field(description="32-byte hex.")
    label: str | None = Field(
        default=None,
        description="From slots.py, e.g. 'Safe.singleton', 'USDC.balances[0x…]'. None if unknown.",
    )
    before: str = Field(description="32-byte hex.")
    after: str = Field(description="32-byte hex.")


class BalanceChange(BaseModel):
    """Net change in one holder's balance of one asset. Gas paid by the relayer is excluded."""

    id: str = Field(pattern=r"^b\d+$")
    holder: str
    asset: str = Field(description="'ETH', or the token contract's address.")
    symbol: str | None = Field(default=None, description="Token symbol from the chain; untrusted.")
    decimals: int | None = None
    before: int
    after: int
    delta: int


class Event(BaseModel):
    id: str = Field(pattern=r"^e\d+$")
    call_id: str = Field(description="The frame that emitted it.")
    address: str = Field(description="Emitting contract (the storage context, so the proxy).")
    topic0: str | None
    name: str | None = Field(default=None, description="Decoded event name; untrusted.")
    args: list[DecodedArg] = Field(default_factory=list)
    topics: list[str]
    data: str


class Source(BaseModel):
    """What Etherscan knows about a contract that ran in the trace. Precompiles are not listed."""

    address: str
    has_code: bool = Field(description="False for an EOA. Etherscan says 'not verified' for both.")
    verified: bool
    name: str | None = Field(default=None, description="Contract name; untrusted.")
    implementation: str | None = Field(
        default=None, description="For a proxy, the implementation address (also a key in `sources`)."
    )
    compiler: str | None = None
    abi_json: str | None = Field(default=None, description="ABI as a JSON string; untrusted names.")
    files: dict[str, str] = Field(default_factory=dict, description="Path -> Solidity source; untrusted.")


FloorRule = Literal[
    "delegatecall_not_allowlisted",  # 1. delegatecall from the Safe to anything but MultiSendCallOnly
    "protected_slot_write",  # 2. Safe's singleton, guard, fallback-handler slot or modules mapping
    "unverified_code",  # 3. call or delegatecall into a contract with no verified source
    "refund_drain",  # 4. gasPrice != 0 with a gas token or refund receiver set
]


class FloorHit(BaseModel):
    """A hard-rule hit. Any hit forces REJECT whatever any model says (invariant 2)."""

    rule: FloorRule
    cites: list[str] = Field(min_length=1, description="Ids of the trace entries that triggered it.")
    reason: str = Field(description="One line, written by code, never by a model.")


class EvidenceBundle(BaseModel):
    """Layer 1 output: everything the judge knows about a proposal, from the fork."""

    safe_tx_hash: str
    safe_address: str
    chain_id: int
    fork_block: int = Field(description="Head block whose state the rehearsal ran on; the stamp binds it.")
    description: str = Field(description="Untrusted text authored by the proposer.")
    safe_tx: SafeTx
    execution_success: bool = Field(description="ExecutionSuccess (True) or ExecutionFailure/revert (False).")
    call_tree: list[Call]
    storage_diff: list[SlotWrite] = Field(default_factory=list)
    balance_diff: list[BalanceChange] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    sources: dict[str, Source] = Field(default_factory=dict, description="Address -> Source.")
    floor_hits: list[FloorHit] = Field(default_factory=list)

    def entry(self, entry_id: str) -> Call | SlotWrite | BalanceChange | Event | None:
        """Resolve a citation id; None if it does not exist (checker.py drops the claim)."""
        return self._index().get(entry_id)

    def _index(self) -> dict[str, Call | SlotWrite | BalanceChange | Event]:
        entries: list[Call | SlotWrite | BalanceChange | Event] = [
            *self.call_tree,
            *self.storage_diff,
            *self.balance_diff,
            *self.events,
        ]
        return {e.id: e for e in entries}

    @model_validator(mode="after")
    def _ids_unique_and_citations_resolve(self) -> "EvidenceBundle":
        ids = [e.id for e in (*self.call_tree, *self.storage_diff, *self.balance_diff, *self.events)]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate evidence ids: {sorted(dupes)}")
        known = set(ids)
        call_ids = {c.id for c in self.call_tree}
        for c in self.call_tree:
            if c.parent is not None and c.parent not in call_ids:
                raise ValueError(f"call {c.id} has unknown parent {c.parent}")
        for e in self.events:
            if e.call_id not in call_ids:
                raise ValueError(f"event {e.id} cites unknown call {e.call_id}")
        for h in self.floor_hits:
            missing = [c for c in h.cites if c not in known]
            if missing:
                raise ValueError(f"floor hit {h.rule} cites unknown entries {missing}")
        return self


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


Severity = Literal["info", "notable", "critical"]

class ObservedEffect(BaseModel):
    """One thing the trace shows happening, in one plain-English sentence."""

    sentence: str = Field(description="One plain-English sentence; parties by address-book name or address.")
    severity: Severity = Field(
        description="info: routine bookkeeping. notable: a real effect a signer should know about. "
        "critical: control of the Safe or its funds changes hands, or code nobody vetted runs with its authority."
    )
    cites: list[str] = Field(min_length=1, description="Trace ids this follows from, e.g. ['c3', 's0'].")


class ObservedMovement(BaseModel):
    """One asset moving between two parties, as the trace shows it."""

    asset: str = Field(description="Ticker, e.g. 'ETH', 'USDC'; the token address if it has no symbol.")
    amount_human: str = Field(description="Amount with unit, decimals applied, e.g. '2,500 USDC'.")
    amount_base_units: str = Field(description="Decimal integer in base units, copied from the trace.")
    from_name: str = Field(description="Address-book name, 'Safe' for the Safe, otherwise the checksummed address.")
    to_name: str = Field(description="Address-book name, 'Safe' for the Safe, otherwise the checksummed address.")
    cites: list[str] = Field(min_length=1)


class ObservedPermissionChange(BaseModel):
    """A token allowance the trace shows being set."""

    kind: Literal["erc20_approval"] = "erc20_approval"
    asset: str
    owner_name: str
    spender_name: str
    amount_human: str = Field(description="e.g. '1,000 USDC', or 'unlimited' for 2**256-1.")
    cites: list[str] = Field(min_length=1)


class ObservedSafeConfigChange(BaseModel):
    """A change to the Safe's own owners or threshold, as the trace shows it."""

    kind: Literal["add_owner", "remove_owner", "swap_owner", "change_threshold"]
    owner_name: str | None = None
    threshold_after: int | None = None
    cites: list[str] = Field(min_length=1)


class Narration(BaseModel):
    """Backward pass: what the trace shows happened. Never sees the description.

    `movements`, `permission_changes` and `safe_config_changes` mirror ExpectedEffects so
    verdict.py can match them item by item. `effects` covers everything, including what
    fits none of those lists (storage writes, delegatecalls, upgrades); the leftovers pass
    classifies whatever no expected item explains. Citations are checked by checker.py,
    not here, so that one bad citation drops one claim rather than the whole form.
    """

    reasoning: str = Field(description="Walk the call tree and diffs step by step first.")
    effects: list[ObservedEffect] = Field(min_length=1)
    movements: list[ObservedMovement] = Field(default_factory=list)
    permission_changes: list[ObservedPermissionChange] = Field(default_factory=list)
    safe_config_changes: list[ObservedSafeConfigChange] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"]


class SourceCite(BaseModel):
    path: str = Field(description="A source file path exactly as given in the input.")
    line: int = Field(description="1-based line number in that file, as numbered in the input.")


class SlotClaim(BaseModel):
    """One unlabelled storage write, explained from the verified source. Code checks every field
    before the explanation counts (judge/corroborate.py): the source lines must exist and name the
    variable, and keccak(key, base_slot) + offset (or base_slot + offset) must equal the slot."""

    cites: list[str] = Field(min_length=1, description="The s-ids this claim explains.")
    contract: str = Field(description="The contract whose storage changed (the proxy address, as in the input).")
    variable: str = Field(description="The state variable, e.g. '_reserves' or '_userState'.")
    base_slot: int = Field(description="The variable's own slot from the storage layout, counting inherited contracts first.")
    key: str | None = Field(default=None, description="Mapping key if the variable is a mapping; None for a plain slot.")
    key_type: Literal["address", "uint256", "bytes32"] = "address"
    offset: int = Field(default=0, description="Struct field offset in slots from the mapping value's base.")
    source_cites: list[SourceCite] = Field(min_length=1, description="Declaration lines for the variable and struct field.")
    reading: Literal["routine_bookkeeping", "asset_or_permission", "control", "unknown"] = Field(
        description="routine_bookkeeping: indexes, rates, timestamps, supply counters, a user's own position. "
        "asset_or_permission: a balance or allowance of someone other than the Safe. control: ownership, admin, "
        "implementation, pause or access flags. unknown: cannot tell from the source."
    )
    sentence: str = Field(description="One plain sentence: what this write is.")
    confidence: Literal["high", "medium", "low"]


class Classification(BaseModel):
    """Leftovers pass (jobs/leftovers.py): what the unlabelled storage writes are, from the source.
    Advisory until corroborated by code; it can raise suspicion, never lower it on its own."""

    reasoning: str = Field(description="Work out each contract's storage layout from the source first.")
    items: list[SlotClaim] = Field(default_factory=list)


class ProbeHypothesis(BaseModel):
    """A probe proposed by the model; code runs it and records the result."""


class HumanQuestion(BaseModel):
    """Escalation (jobs/escalate.py): the question a signer should be asked when the table says
    ASK. Advisory text for humans; it never feeds back into the decision (invariant 1)."""

    reasoning: str = Field(description="Work through what the words promise against what the trace shows.")
    gap_kind: Literal["omission", "contradiction", "vague_description", "none"] = Field(
        description="omission: the words leave out something the bytes do. contradiction: the words say "
        "one thing and the bytes do a different thing of the same kind. vague_description: the words fix "
        "nothing to check against. none: no gap."
    )
    would_an_honest_proposer_write_this: Literal["yes", "unlikely", "no"] = Field(
        description="Could someone acting in good faith have written this description for these bytes?"
    )
    question: str | None = Field(
        default=None, description="ASK only: one or two plain sentences a treasurer can answer, naming amounts and parties."
    )
    statement: str | None = Field(
        default=None, description="REJECT only: two or three plain sentences saying why the transaction was refused "
        "and what it would have done. No question; the decision is final."
    )
    what_to_check: list[str] = Field(default_factory=list, description="Concrete things the signer should verify first.")
    confidence: Literal["high", "medium", "low"]

    @model_validator(mode="after")
    def _one_of_question_or_statement(self) -> "HumanQuestion":
        if not (self.question or self.statement):
            raise ValueError("either question (for ASK) or statement (for REJECT) must be filled")
        return self


# --------------------------------------------------------------------------- canonical form (layer 4)
#
# canon.py normalises ExpectedEffects (forward), Narration (backward) and the fixture ground
# truth into these. Identity is the address: labels, chain symbols and contract names are
# display only. compare.py reconciles two CanonEffects and verdict.py reads the result.

PartyVia = Literal["safe", "address_book", "address", "zero", "sources", "unresolved"]
AssetVia = Literal["eth", "address_book", "address", "evidence", "unresolved"]
Direction = Literal["out", "in", "self", "third_party"]
FormSource = Literal["forward", "backward", "truth"]
ConfigField = Literal[
    "owners_add", "owners_remove", "owners_swap", "threshold", "guard", "fallback_handler",
    "module_enable", "module_disable", "singleton",
]
MatchTier = Literal[
    "exact", "amount_unconstrained", "party_unresolved", "asset_unresolved", "counterparty_via_callee",
    "inbound_from_callee", "internal_to_callee", "unmatched",
]


class Party(BaseModel):
    label: str = Field(description="What the form said: an address-book name, 'Safe', or an address.")
    address: str | None = Field(default=None, description="Checksummed; None if the label could not be resolved.")
    via: PartyVia = "unresolved"

    @property
    def resolved(self) -> bool:
        return self.address is not None


class Asset(BaseModel):
    label: str
    address: str | None = Field(default=None, description="Token address, or 'ETH'. None if unresolved.")
    via: AssetVia = "unresolved"
    decimals: int | None = None

    @property
    def resolved(self) -> bool:
        return self.address is not None


class CanonMovement(BaseModel):
    asset: Asset
    from_party: Party
    to_party: Party
    amount_base: int | None = Field(default=None, description="Base units; None if the form fixed no amount.")
    amount_max_base: int | None = Field(default=None, description="Upper bound in base units ('at most 1 ETH').")
    amount_human: str | None = None
    direction: Direction
    implied: bool = False
    severity: Severity | None = None
    cites: list[str] = Field(default_factory=list)
    cited_ok: bool = True
    source: FormSource


class CanonPermission(BaseModel):
    asset: Asset
    owner: Party
    spender: Party
    new_allowance: int | Literal["unlimited", "zero"] | None = None
    implied: bool = False
    severity: Severity | None = None
    cites: list[str] = Field(default_factory=list)
    cited_ok: bool = True
    source: FormSource


class CanonConfig(BaseModel):
    field: ConfigField
    old: str | None = None
    new: str | None = None
    severity: Severity | None = None
    cites: list[str] = Field(default_factory=list)
    cited_ok: bool = True
    source: FormSource


class CanonEffect(BaseModel):
    """A backward-pass sentence, kept so unexplained critical findings can still force a verdict."""

    sentence: str
    severity: Severity
    cites: list[str]
    cited_ok: bool = True


class CanonEffects(BaseModel):
    source: FormSource
    movements: list[CanonMovement] = Field(default_factory=list)
    permissions: list[CanonPermission] = Field(default_factory=list)
    configs: list[CanonConfig] = Field(default_factory=list)
    effects: list[CanonEffect] = Field(default_factory=list)
    nothing_else: bool | None = None
    questions: list[str] = Field(default_factory=list)
    uncited: list[str] = Field(default_factory=list, description="Items whose evidence ids do not resolve.")
    unsupported: list[str] = Field(default_factory=list, description="Forward items whose phrase is not in the text.")
    notes: list[str] = Field(default_factory=list)


class Match(BaseModel):
    kind: Literal["movement", "permission", "config"]
    expected: str
    observed: str
    tier: MatchTier
    notes: list[str] = Field(default_factory=list)


class Unexplained(BaseModel):
    kind: Literal["movement", "permission", "config", "effect"]
    item: str
    severity: Severity
    cites: list[str] = Field(default_factory=list)
    reason: str


class CompareResult(BaseModel):
    """What compare.reconcile found. The verdict reads only this and the floor."""

    matched: list[Match] = Field(default_factory=list)
    observed_unexplained: list[Unexplained] = Field(default_factory=list)
    expected_unobserved: list[str] = Field(default_factory=list)
    info_effects: list[str] = Field(default_factory=list)
    uncited: list[str] = Field(default_factory=list)
    unsupported: list[str] = Field(default_factory=list)
    tiers: list[MatchTier] = Field(default_factory=list)
    nothing_else: bool | None = None
    questions: list[str] = Field(default_factory=list)
    explained_slots: list[str] = Field(
        default_factory=list, description="Storage writes labelled from the source and corroborated by code."
    )


class Decision(str, Enum):
    MATCH = "MATCH"
    ASK = "ASK"
    REJECT = "REJECT"


class Verdict(BaseModel):
    """Layer 5 output: a pure function of the evidence bundle plus checked model forms."""

    reasoning: str = Field(description="Why the decision follows; written before the decision.")
    decision: Decision
    reasons: list[str] = Field(default_factory=list)
    floor_hits: list[FloorHit] = Field(
        default_factory=list, description="The hard-rule hits that forced REJECT, if any (invariant 2)."
    )
    question: str | None = Field(default=None, description="ASK only: what the signer must settle.")
    compare: CompareResult | None = Field(default=None, description="The reconciliation, for the per-effect table.")


class Stamp(BaseModel):
    """EIP-712 payload signed by the judge key. Field names match the Solidity struct."""

    safeTxHash: str
    forkBlock: int
    judgeVersion: str
