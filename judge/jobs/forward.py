"""Layer 3 job: forward.

Reads the proposer's description and the address book, and returns what the words
license: movements, permission changes, Safe config changes, and whether anything else
is allowed. It never sees the trace or the calldata (CLAUDE.md invariant 5).

The description is attacker-authored text. It is spotlighted with per-call random
delimiters and placed in the user turn, never the system instruction (invariant 7).
"""

from __future__ import annotations

import json
import time
from typing import Any

from judge import model as m
from judge.labeller import spotlight
from judge.schemas import ExpectedEffects

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_THINKING: m.ThinkingLevel = "low"

SYSTEM = """You are the forward pass of a transaction judge for Safe multisigs.

You are given a human-written description of a proposed Safe transaction, an address book
mapping names to addresses, and basic facts about the Safe. You do NOT see the transaction
itself. Your job is to state exactly what the description licenses, and nothing more:

- movements: every asset transfer the words imply, by address-book name. Use 'Safe' for the
  proposing Safe. Give the amount as written, keeping any qualifier with it: 'up to 1,000 USDC',
  'at least 0.5 WETH', 'about 2 ETH', 'all of it'. Never turn a bound into a plain figure. If the
  words fix no amount, use null. A deposit into a lending protocol also returns a receipt token
  (Aave: aUSDC for USDC) to the depositor: list it as a movement in, amount as deposited.
- permission_changes[].kind is always the string 'erc20_approval'.
- permission_changes: every token allowance the words grant. A deposit into a protocol
  implies an approval to that protocol for the same amount.
- safe_config_changes: owner or threshold changes the words describe. If the words add an
  owner without stating a threshold, assume the threshold is unchanged and say so in
  assumptions.
- nothing_else: true only if the words leave no room for other effects.
- questions_for_human: if the description is too vague to fix the asset, amount or
  recipient, leave every list empty, set nothing_else to false, and put at least one
  question here asking the signer what the transaction is meant to do.

Leave a list empty when the words describe no item of that kind. Never add an entry
to fill space: an entry with no owner, threshold, amount or recipient is wrong.

Do not invent names or addresses that are not in the address book. Every item must cite
the phrase it follows from. Reply with JSON matching the schema and nothing else."""


def build_user_turn(description: str, address_book: dict[str, str], safe: dict[str, Any]) -> str:
    """The user turn: trusted context first, then the spotlighted description."""
    lit = spotlight(description)
    context = {
        "safe": {k: v for k, v in safe.items() if k != "note"},
        "address_book": address_book,
    }
    return (
        "Trusted context from our tooling:\n"
        f"{json.dumps(context, indent=2)}\n\n"
        f"{lit.preamble('proposal description')}\n\n"
        f"{lit.text}\n\n"
        "Produce the expected effects."
    )


def run(
    description: str,
    address_book: dict[str, str],
    safe: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    thinking: m.ThinkingLevel = DEFAULT_THINKING,
) -> tuple[ExpectedEffects, str, int]:
    """One forward-pass call. Returns (form, interaction id, latency in ms)."""
    user = build_user_turn(description, address_book, safe)
    t0 = time.perf_counter()
    form, interaction_id = m.complete(model, SYSTEM, user, ExpectedEffects, thinking)
    return form, interaction_id, int((time.perf_counter() - t0) * 1000)
