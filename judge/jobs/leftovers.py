"""Layer 3 job: leftovers. Explain the storage writes no code layout labels, from the source.

Input, built by code: the unlabelled writes, the frames that ran in each written contract, a list
of addresses seen in the evidence (candidate mapping keys), and the verified source of the
implementation behind each written contract with line numbers. Never the description, never the
amendments (invariant 5), never the floor's findings. Everything from the chain or Etherscan is
spotlighted (invariant 7): identifiers and comments are written by whoever deployed the contract.

Output: Classification, one SlotClaim per write: variable, base slot, key, offset, source lines,
and a reading. The model has no tools and decides nothing. judge/corroborate.py recomputes each
slot and checks each cited line before any claim counts; an uncorroborated claim changes nothing.

Model: gemini-4-argon, thinking high. This is the call that reads the Aave source.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from eth_utils import to_checksum_address

from judge import model as m
from judge.evidence import slots
from judge.labeller import spotlight
from judge.schemas import Classification, EvidenceBundle

DEFAULT_MODEL = "gemini-4-argon"
DEFAULT_THINKING: m.ThinkingLevel = "high"
# Above this the prompt is trimmed to files that declare storage or define a frame's function.
# Aave's full source is ~182k tokens, trimmed ~98k. The hackathon billing account refuses large
# Argon requests with a 429 after ~90 s (a spend-rate window, by the look of it), so trim early.
TOKEN_BUDGET = 120_000

SYSTEM = """You are the source reader of a transaction judge for Safe multisigs.

A Safe transaction was rehearsed on a fork of mainnet. Code labelled every storage write it could
from known layouts. The writes below are the ones it could not. You are given, for each contract
written, the call frames that ran in it, the addresses that appear anywhere in the evidence (the
only plausible mapping keys), and the verified Solidity source of its implementation, with line
numbers. Work out what each write is.

Solidity storage layout, which you must apply exactly:
- State variables take slots in declaration order, inherited contracts first, most-base first
  (C3 linearisation). Each variable that does not pack into the previous slot starts a new one.
  Reserved gaps such as `uint256[50] private __gap;` take their full length.
- Values narrower than 32 bytes pack into one slot, lowest declared at the lowest bytes.
- A mapping or dynamic array occupies one slot (its base) and stores nothing there. The value
  for key k of a mapping at base b lives at keccak256(abi.encode(k, b)): the key left-padded to
  32 bytes, then b as 32 bytes. A struct value spreads from that address: field i at +offset_i.
- Nested mappings apply the rule twice: inner base is the outer value address.

For every write, produce one SlotClaim: `contract` (the proxy address as given), `variable`,
`base_slot` (the integer slot of the variable itself), `key` (one of the listed addresses, or null
for a plain slot), `key_type`, `offset` (struct field offset from the value address, 0 if none),
`source_cites` (the exact file paths and line numbers of the variable's declaration and, for a
struct field, of that field), `reading`, `sentence`, `confidence`.

Readings: routine_bookkeeping for indexes, rates, timestamps, supply counters, fee accumulators,
and the Safe's own position or configuration bits; asset_or_permission when a balance or
allowance of anyone other than the Safe changes; control for owner, admin, implementation,
pause, role or access changes; unknown if the source does not settle it.

Cite only lines that are in the input. Do not guess a base slot: count it from the declarations.
If several writes share a base and key, give each its own claim with its own offset. Reply with
JSON matching the schema and nothing else."""


def _numbered(text: str) -> str:
    return "\n".join(f"{i:5d}  {line}" for i, line in enumerate(text.splitlines(), 1))


def _source_files(bundle: EvidenceBundle, contract: str) -> tuple[str, dict[str, str]]:
    src = bundle.sources.get(contract)
    if src is None:
        return contract, {}
    files = dict(src.files)
    name = src.name or contract
    if src.implementation and src.implementation in bundle.sources:
        impl = bundle.sources[src.implementation]
        files = {**files, **impl.files}
        name = f"{src.name or 'proxy'} -> {impl.name or src.implementation}"
    return name, files


def _storage_relevant(text: str, functions: set[str]) -> bool:
    """Files that declare state (mappings, structs, state variables) or define a frame's function."""
    if re.search(r"^\s*(mapping\s*\(|struct\s+\w+|uint\d*\[\d+\]\s+(private|internal)\s+_*gap)", text, re.M):
        return True
    return any(re.search(rf"\bfunction\s+{re.escape(f)}\b", text) for f in functions)


def build_user_turn(bundle: EvidenceBundle, *, trimmed: bool = False) -> tuple[str, dict[str, Any]]:
    """The user turn and a small summary (contracts, files kept and dropped)."""
    unlabelled = [w for w in bundle.storage_diff if not w.label]
    contracts = sorted({to_checksum_address(w.contract) for w in unlabelled})
    keys = slots.candidate_keys(bundle)
    summary: dict[str, Any] = {"contracts": contracts, "writes": [w.id for w in unlabelled], "dropped": []}

    sections = []
    for contract in contracts:
        frames = [c for c in bundle.call_tree if to_checksum_address(c.storage_context) == contract
                  and c.kind in ("CALL", "DELEGATECALL")]
        functions = {c.function.split("(")[0] for c in frames if c.function}
        writes = [{"id": w.id, "slot": w.slot, "before": w.before, "after": w.after}
                  for w in unlabelled if to_checksum_address(w.contract) == contract]
        name, files = _source_files(bundle, contract)
        shown = []
        for path, text in files.items():
            if trimmed and not _storage_relevant(text, functions):
                summary["dropped"].append(f"{contract[:10]} {path}")
                continue
            shown.append(f"--- {path} ---\n{_numbered(text)}")
        header = json.dumps({
            "contract": contract, "source": name,
            "frames_that_ran_here": [{"id": c.id, "kind": c.kind, "code": c.to_address, "function": c.function}
                                     for c in frames],
            "unlabelled_writes": writes,
        }, indent=1)
        sections.append(f"=== {contract} ===\n{header}\n\n" + "\n\n".join(shown))
    lit = spotlight("\n\n".join(sections))
    user = (
        "Trusted context from our tooling:\n"
        + json.dumps({"safe": bundle.safe_address, "chain_id": bundle.chain_id,
                      "addresses_in_the_evidence (the only plausible mapping keys)": keys}, indent=2)
        + "\n\nThe contracts, their unlabelled writes and their verified source. "
        + lit.preamble("contract source and trace data")
        + f"\n\n{lit.text}\n\nProduce one claim per write."
    )
    return user, summary


def run(bundle: EvidenceBundle, *, model: str = DEFAULT_MODEL, thinking: m.ThinkingLevel = DEFAULT_THINKING,
        ) -> tuple[Classification, str, int, dict[str, Any]]:
    """One typed call. Returns (form, interaction id, latency ms, summary incl. token count)."""
    user, summary = build_user_turn(bundle)
    tokens = m.count_tokens(model, SYSTEM, user)
    if tokens > TOKEN_BUDGET:
        user, summary = build_user_turn(bundle, trimmed=True)
        summary["tokens_before_trim"] = tokens
        tokens = m.count_tokens(model, SYSTEM, user)
    summary["tokens"] = tokens
    t0 = time.perf_counter()
    form, interaction_id = m.complete(model, SYSTEM, user, Classification, thinking, timeout_s=900.0)
    return form, interaction_id, int((time.perf_counter() - t0) * 1000), summary
