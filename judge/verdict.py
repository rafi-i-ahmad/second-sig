"""Layer 5: decision table.

Pure function of the evidence bundle plus checked model forms (invariant 1). No network, no
model, no key. The order is fixed and nothing later in the table can soften an earlier row:

1. Any hard-floor hit: REJECT, whatever any model said (invariant 2). The floor is recomputed
   from the bundle's evidence here, so a stale or edited ``floor_hits`` list cannot hide a hit.
2. The rehearsal did not succeed (ExecutionFailure or revert): ASK. Nothing happened, so there
   is nothing to approve, and a transaction that fails today may succeed under other state.
3. A missing or invalid form (forward or backward): ASK. Every failure ends in ASK, never MATCH.
4. The comparison (compare.reconcile) of what the words promised with what the bytes did:
   - an observed effect nothing expected explains, severity critical: REJECT
   - an observed effect nothing expected explains, severity notable: ASK
   - an expected effect the trace does not show: ASK
   - the words leave room for more (nothing_else is false), or the forward pass raised a question
     the signers must settle (words that contradict themselves, a wallet the book does not hold):
     ASK, with the forward pass's question
   - otherwise MATCH
   Items matched only by a weaker tier (party or asset the address book lacks) count as
   explained here and are flagged in the CompareResult for the report.

``decide(bundle, model=...)`` is kept for the one-call judge form (eval only): its decision
stands only after rows 1 to 3.

    uv run python -m judge.verdict fixtures/bundles/demo_bybit.bundle.json
"""

from __future__ import annotations

import sys
from pathlib import Path

from judge import canon, compare
from judge.canon import Resolver
from judge.evidence import rules
from judge.schemas import (
    CompareResult, Decision, EvidenceBundle, ExpectedEffects, FloorHit, FloorRule, Narration, Verdict,
)

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


def _ask(reasoning: str, reason: str, question: str | None = None, cmp: CompareResult | None = None) -> Verdict:
    return Verdict(reasoning=reasoning, decision=Decision.ASK, reasons=[reason], question=question, compare=cmp)


def from_compare(cmp: CompareResult) -> Verdict:
    """Rows 4 of the table, from a finished reconciliation."""
    critical = [u for u in cmp.observed_unexplained if u.severity == "critical"]
    notable = [u for u in cmp.observed_unexplained if u.severity != "critical"]
    if critical:
        lines = [f"{len(critical)} critical effect{'s' if len(critical) != 1 else ''} in the trace that nothing in the "
                 "description accounts for:"]
        lines += [f"- {u.item} (evidence {', '.join(u.cites)}; {u.reason})" for u in critical]
        return Verdict(reasoning="\n".join(lines), decision=Decision.REJECT,
                       reasons=[f"unexplained critical: {u.item}" for u in critical], compare=cmp)
    if notable:
        lines = [f"The trace shows {len(notable)} effect{'s' if len(notable) != 1 else ''} the description does not "
                 "mention:"]
        lines += [f"- {u.item} (evidence {', '.join(u.cites)})" for u in notable]
        q = "The transaction also does the following, which the description does not mention. Is that intended? " + \
            "; ".join(u.item for u in notable)
        return _ask("\n".join(lines), f"unexplained: {notable[0].item}", q, cmp)
    if cmp.expected_unobserved:
        lines = ["The description promises effects the rehearsal did not show:"]
        lines += [f"- {x}" for x in cmp.expected_unobserved]
        q = "The description says this should happen but the transaction does not do it: " + \
            "; ".join(cmp.expected_unobserved) + ". Is the description right?"
        return _ask("\n".join(lines), f"expected but not observed: {cmp.expected_unobserved[0]}", q, cmp)
    if cmp.nothing_else is False:
        q = cmp.questions[0] if cmp.questions else "The description leaves open what the transaction may do."
        return _ask("The description does not pin the transaction down: the forward pass could not rule out other "
                    "effects.", "description leaves room", q, cmp)
    if cmp.questions:
        return _ask("Everything matched, but reading the description raised a question the signers must settle "
                    "before anything is approved.", "the description raises a question", cmp.questions[0], cmp)
    tiers = ", ".join(cmp.tiers) if cmp.tiers else "exact"
    return Verdict(
        reasoning=f"Every effect in the trace is accounted for by the description, and everything the description "
                  f"promises is in the trace ({len(cmp.matched)} matched; tiers used: {tiers}).",
        decision=Decision.MATCH, reasons=[f"{m.kind}: {m.observed} [{m.tier}]" for m in cmp.matched], compare=cmp,
    )


def decide(
    bundle: EvidenceBundle,
    model: Verdict | None = None,
    *,
    expected: ExpectedEffects | None = None,
    observed: Narration | None = None,
    address_book: dict[str, str] | None = None,
    raised: dict[str, str] | None = None,
    explained_slots: list[str] | None = None,
) -> Verdict:
    """The decision table. Pass ``expected`` + ``observed`` (+ the address book) for the real
    pipeline, or ``model`` for the one-call judge form. Neither present: ASK. ``raised`` and
    ``explained_slots`` come from judge/corroborate.py; the bundle passed in should already carry
    the labels it produced. Labels code knows on its own (judge/layouts.py) are applied here."""
    from judge import layouts

    bundle = layouts.label_known(bundle)
    hits = rules.evaluate(bundle)
    if hits:
        return floor_verdict(hits)

    if not bundle.execution_success:
        return _ask(
            "The rehearsal did not succeed: the Safe reported ExecutionFailure or the call reverted, so the "
            "transaction did nothing on the fork. There is nothing to approve, and a transaction that fails under "
            "today's state may do something else later.", "rehearsal did not succeed")

    if expected is not None or observed is not None:
        if expected is None or observed is None:
            missing = "forward" if expected is None else "backward"
            return _ask(f"No hard rule was hit, but the {missing} pass produced no checked form (it did not run, "
                        "timed out, or its output failed validation). Without both forms nothing can be approved.",
                        f"no checked {missing} form")
        r = Resolver(bundle, address_book or {})
        cmp = compare.reconcile(canon.from_forward(expected, bundle.description, r), canon.from_backward(observed, r), r,
                                raised=raised, explained_slots=explained_slots)
        v = from_compare(cmp)
        if cmp.ignored_labels:
            v.reasons.append("address-book label ignored (not a plain name) for " + ", ".join(cmp.ignored_labels))
        return v

    if model is None:
        return _ask(
            "No hard rule was hit, but the judge has not produced a checked form (it did not run, timed out, or its "
            "output failed validation). Without one, nothing can be approved: every failure ends in ASK.",
            "no checked model form")

    return Verdict(reasoning=model.reasoning, decision=model.decision, reasons=list(model.reasons), floor_hits=[])


def render(v: Verdict) -> str:
    lines = [f"{v.decision.value}", "", v.reasoning]
    if v.question:
        lines += ["", f"Question for the signers: {v.question}"]
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
