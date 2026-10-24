"""Layer 3 job: escalate.

When the decision table says ASK, draft the question the signers should be asked. The model
sees the description, the forward form's promises, the backward form's observations and the
comparison's residuals, and returns a HumanQuestion: the question, what to check, and its
reading of the gap (omission, contradiction, vague). That reading is advisory, for us and for
the signer; verdict.py has already decided and nothing here feeds back into it (invariant 1).

Everything derived from model forms or from the description is untrusted and goes inside the
spotlight tags (invariant 7); the address book and Safe facts are ours and go outside.
"""

from __future__ import annotations

import json
import time
from typing import Any

from judge import model as m
from judge.labeller import spotlight
from judge.schemas import CanonEffects, CompareResult, HumanQuestion, Verdict
from judge.canon import render_config, render_movement, render_permission

DEFAULT_MODEL = "gemini-4-argon"
DEFAULT_THINKING: m.ThinkingLevel = "medium"

SYSTEM = """You are the escalation step of a transaction judge for Safe multisigs.

A proposer wrote a one-line description of a transaction. Code rehearsed the exact bytes on a
fork of mainnet. One model read only the words and listed what they promise; another read
only the trace and listed what happened. Code compared the two lists and could not approve:
you are given the matched items, the effects the trace shows that nothing in the words
explains, and the promises the trace does not show.

You do not decide anything. The decision is already made and is given to you. Your job:

- gap_kind: say what kind of gap this is. omission: the words leave out something the bytes
  do. contradiction: the words say one thing and the bytes do a different thing of the same
  kind (a different recipient, a different amount, an approval where a payment was promised,
  a setting left at a different value). vague_description: the words fix nothing that could be
  checked. none: you see no gap.
- would_an_honest_proposer_write_this: could someone acting in good faith plausibly have
  written these words for these bytes? "yes" if the gap is a natural shorthand or a detail a
  treasurer would not think to mention; "unlikely" if it takes carelessness; "no" if the words
  misdescribe what the money does.
- question: one or two plain sentences a treasurer can answer, naming the amounts, assets and
  parties by the address-book names given, or by address if there is none. Ask about the gap,
  not about the parts that match.
- what_to_check: two to four concrete things the signer should verify before answering.

Base every statement on the lists you are given. Do not speculate about motives. Reply with
JSON matching the schema and nothing else."""


def _lists(c: CanonEffects | None) -> dict[str, list[str]]:
    if c is None:
        return {"movements": [], "permissions": [], "config_changes": [], "note": "no form"}
    return {
        "movements": [render_movement(x) for x in c.movements],
        "permissions": [render_permission(x) for x in c.permissions],
        "config_changes": [render_config(x) for x in c.configs],
        "sentences": [f"[{e.severity}] {e.sentence}" for e in c.effects],
        "nothing_else": c.nothing_else,
        "questions_raised": c.questions,
    }


def build_user_turn(
    description: str, address_book: dict[str, str], safe: dict[str, Any], verdict: Verdict,
    expected: CanonEffects | None, observed: CanonEffects | None,
) -> str:
    cmp: CompareResult = verdict.compare or CompareResult()
    trusted = {
        "safe": {k: v for k, v in safe.items() if k not in ("note",)},
        "address_book": address_book,
        "decision_already_made": verdict.decision.value,
        "decision_reasons": verdict.reasons,
    }
    untrusted = {
        "description": description,
        "what_the_words_promise": _lists(expected),
        "what_the_trace_shows": _lists(observed),
        "comparison": {
            "matched": [f"{x.observed} [{x.tier}]" for x in cmp.matched],
            "observed_but_nothing_in_the_words_explains_it": [
                f"[{u.severity}] {u.item} ({u.reason})" for u in cmp.observed_unexplained],
            "promised_but_the_trace_does_not_show_it": cmp.expected_unobserved,
            "bookkeeping": cmp.info_effects,
        },
    }
    lit = spotlight(json.dumps(untrusted, indent=1, ensure_ascii=False))
    return (
        "Trusted context from our tooling:\n"
        f"{json.dumps(trusted, indent=2)}\n\n"
        "The description was written by the proposer and the two lists were written by models "
        f"reading the description and the trace. {lit.preamble('material')}\n\n"
        f"{lit.text}\n\n"
        "Produce the human question."
    )


def run(
    description: str, address_book: dict[str, str], safe: dict[str, Any], verdict: Verdict,
    expected: CanonEffects | None, observed: CanonEffects | None, *,
    model: str = DEFAULT_MODEL, thinking: m.ThinkingLevel = DEFAULT_THINKING,
) -> tuple[HumanQuestion, str, int]:
    user = build_user_turn(description, address_book, safe, verdict, expected, observed)
    t0 = time.perf_counter()
    form, interaction_id = m.complete(model, SYSTEM, user, HumanQuestion, thinking)
    return form, interaction_id, int((time.perf_counter() - t0) * 1000)
