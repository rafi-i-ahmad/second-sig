"""Layer 5: decision table.

Pure function of the evidence bundle plus checked model forms (invariant 1). No network, no
model, no key. The order is fixed and nothing later in the table can soften an earlier row:

1. Any hard-floor hit: REJECT, whatever any model said (invariant 2). The floor is recomputed
   from the bundle's evidence here, so a stale or edited ``floor_hits`` list cannot hide a hit.
2. The rehearsal did not succeed (ExecutionFailure or revert): ASK. Nothing happened, so there
   is nothing to approve, and a transaction that fails today may succeed under other state.
3. No checked model form: ASK. The judge has not run, timed out or returned an invalid form;
   every failure ends in ASK, never MATCH.
4. Otherwise the model's decision. A model form can only hold the verdict at MATCH, ASK or
   REJECT; the rows above have already taken REJECT and ASK out of its hands where they apply.

    uv run python -m judge.verdict fixtures/bundles/demo_bybit.bundle.json
"""

from __future__ import annotations

import sys
from pathlib import Path

from judge.evidence import rules
from judge.schemas import Decision, EvidenceBundle, FloorHit, FloorRule, Verdict

# One paragraph per rule, for the signer who has to understand the rejection. Written by us, not
# by a model, so it can be shown without spotlighting. Keep it to what the rule actually proves.
FLOOR_EXPLANATIONS: dict[FloorRule, str] = {
    "delegatecall_not_allowlisted": (
        "The transaction makes the Safe run another contract's code as if it were the Safe's own "
        "(a delegatecall), and that contract is not the standard Safe batching helper "
        "(MultiSendCallOnly). Code run this way can change anything inside the Safe, including "
        "who owns it and which contract it trusts as its master copy. This is the shape of the "
        "Bybit attack. No honest payment, deposit or swap needs it."
    ),
    "protected_slot_write": (
        "The transaction changes one of the Safe's own settings: its master copy (the contract "
        "that holds all of its logic), its guard, its fallback handler, or its list of modules. "
        "Ordinary transactions never touch these. Changing them hands control of the Safe to "
        "whoever wrote the new value, and the owners' signatures would no longer mean anything."
    ),
    "unverified_code": (
        "The transaction calls a contract whose source code is not verified on Etherscan. "
        "Nobody, human or model, can read what that code does, so approving it would mean "
        "trusting it blind. Attackers deploy their contracts unverified for exactly this reason."
    ),
    "refund_drain": (
        "The transaction sets a gas price together with a gas token or a refund receiver. That "
        "makes the Safe pay whoever executes it a refund out of its own funds, at a rate the "
        "proposer chose. Honest proposals leave these three fields at zero."
    ),
}


def explain(hit: FloorHit) -> str:
    """The paragraph for this rule, then what the evidence showed and where."""
    return f"{FLOOR_EXPLANATIONS[hit.rule]} What the rehearsal showed: {hit.reason} (evidence {', '.join(hit.cites)})."


def floor_verdict(hits: list[FloorHit]) -> Verdict:
    """REJECT with one explanation per hit. Called only when ``hits`` is non-empty."""
    if not hits:
        raise ValueError("floor_verdict needs at least one hit")
    rules_hit = sorted({h.rule for h in hits})
    intro = (
        f"Rejected by the hard floor before any model ran. {len(hits)} hard rule hit"
        f"{'s' if len(hits) != 1 else ''} ({', '.join(rules_hit)}). These rules have no honest "
        "counterexample, so the description is irrelevant: whatever it says, this transaction "
        "must not execute."
    )
    reasons = [explain(h) for h in hits]
    return Verdict(
        reasoning="\n\n".join([intro, *reasons]),
        decision=Decision.REJECT,
        reasons=[f"{h.rule}: {h.reason}" for h in hits],
        floor_hits=hits,
    )


def decide(bundle: EvidenceBundle, model: Verdict | None = None) -> Verdict:
    """The decision table. ``model`` is the checked judge form, or None if the judge did not run."""
    hits = rules.evaluate(bundle)
    if hits:
        return floor_verdict(hits)

    if not bundle.execution_success:
        return Verdict(
            reasoning=(
                "The rehearsal did not succeed: the Safe reported ExecutionFailure or the call "
                "reverted, so the transaction did nothing on the fork. There is nothing to approve, "
                "and a transaction that fails under today's state may do something else later."
            ),
            decision=Decision.ASK,
            reasons=["rehearsal did not succeed"],
        )

    if model is None:
        return Verdict(
            reasoning=(
                "No hard rule was hit, but the judge has not produced a checked form (it did not "
                "run, timed out, or its output failed validation). Without one, nothing can be "
                "approved: every failure ends in ASK."
            ),
            decision=Decision.ASK,
            reasons=["no checked model form"],
        )

    return Verdict(
        reasoning=model.reasoning,
        decision=model.decision,
        reasons=list(model.reasons),
        floor_hits=[],
    )


def render(v: Verdict) -> str:
    lines = [f"{v.decision.value}", ""]
    lines.append(v.reasoning)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        bundle = EvidenceBundle.model_validate_json(Path(path).read_text(encoding="utf-8"))
        print(f"== {path}")
        print(render(decide(bundle)))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
