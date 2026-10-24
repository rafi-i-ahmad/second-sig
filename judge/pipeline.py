"""The judge, end to end. Code orchestrates; models fill forms; code decides and signs.

    rehearse ─▶ floor ─▶ forward ‖ backward ─▶ canon/compare ─▶ verdict ─▶ escalate ─▶ stamp ─▶ attest ─▶ execute
                 │                                                  │                      (MATCH only)
                 └── REJECT ────────────────────────────────────────┘

A Proposal is the description plus any amendments owners have added in answer to an ASK. The
effective description is the original followed by each amendment, attributed to the owner who
wrote it. An amendment is untrusted text like the description itself: it reaches the forward
pass through the spotlighter and nothing else (invariant 7). Owners never flip a verdict; they
change the words and the judge runs again on the same bytes (invariant 1). The bytes never
change, so the rehearsal and the backward pass are reused and only the forward pass re-runs.

Replay: with ``recorded`` forms (fixtures/outputs/<id>.forward.json, .backward.json) no model is
called. An amended description has no recorded form, so answering an ASK always calls the
forward pass once; the result is stored in the proposal record for later replays.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eth_utils import to_checksum_address
from pydantic import BaseModel, Field
from web3 import Web3

from judge import canon, compare, stamp as stamping, verdict as verdicting
from judge.canon import Resolver
from judge.evidence import fork
from judge.jobs import backward, escalate, forward
from judge.schemas import Decision, EvidenceBundle, ExpectedEffects, HumanQuestion, Narration, Stamp, Verdict

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "fixtures"
OUTPUTS = FIXTURES / "outputs"
PROPOSALS = REPO / "logs" / "proposals"

IS_OWNER_ABI = [{"type": "function", "name": "isOwner", "stateMutability": "view",
                 "inputs": [{"name": "owner", "type": "address"}], "outputs": [{"type": "bool"}]}]


# --------------------------------------------------------------------------- records


class Amendment(BaseModel):
    owner: str = Field(description="Checksummed owner address; verified against Safe.isOwner at the time.")
    text: str = Field(description="What the owner answered. Untrusted.")
    at: str


class Proposal(BaseModel):
    id: str
    description: str
    amendments: list[Amendment] = Field(default_factory=list)
    address_book: dict[str, str]
    safe: dict[str, Any]
    safe_tx: dict[str, Any]
    expected_verdict: str | None = None
    forward_forms: dict[str, Any] = Field(
        default_factory=dict, description="Recorded forward forms keyed by the sha of the description they read."
    )

    @classmethod
    def from_case(cls, case: dict[str, Any]) -> "Proposal":
        return cls(id=case["id"], description=case["description"], address_book=case["address_book"],
                   safe=case["safe"], safe_tx=case["safe_tx"], expected_verdict=case.get("expected_verdict"))

    def effective_description(self) -> str:
        parts = [self.description]
        for a in self.amendments:
            parts.append(f"Owner {a.owner}: {a.text}")
        return "\n".join(parts)

    def save(self) -> Path:
        PROPOSALS.mkdir(parents=True, exist_ok=True)
        p = PROPOSALS / f"{self.id}.json"
        p.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
        return p

    @classmethod
    def load_or_create(cls, case: dict[str, Any]) -> "Proposal":
        p = PROPOSALS / f"{case['id']}.json"
        if p.exists():
            return cls.model_validate_json(p.read_text(encoding="utf-8"))
        return cls.from_case(case)


class JudgeResult(BaseModel):
    proposal: Proposal
    bundle: EvidenceBundle
    forward: ExpectedEffects | None
    backward: Narration | None
    verdict: Verdict
    question: HumanQuestion | None = None
    note: str = Field(default="", description="What the signers see: the question (ASK) or the statement (REJECT).")
    stamp: Stamp | None = None
    stamp_signature: str | None = None
    calls: list[str] = Field(default_factory=list, description="Model calls made, for the record.")


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- recorded forms


def recorded_forward(case_id: str) -> ExpectedEffects | None:
    p = OUTPUTS / f"{case_id}.forward.json"
    return ExpectedEffects.model_validate(json.loads(p.read_text(encoding="utf-8"))["expected_effects"]) if p.exists() else None


def recorded_backward(case_id: str) -> Narration | None:
    p = OUTPUTS / f"{case_id}.backward.json"
    return Narration.model_validate(json.loads(p.read_text(encoding="utf-8"))["narration"]) if p.exists() else None


def recorded_question(case_id: str) -> HumanQuestion | None:
    p = OUTPUTS / f"{case_id}.question.json"
    return HumanQuestion.model_validate(json.loads(p.read_text(encoding="utf-8"))["question"]) if p.exists() else None


def recorded_bundle(case_id: str) -> EvidenceBundle | None:
    p = FIXTURES / "bundles" / f"{case_id}.bundle.json"
    return EvidenceBundle.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


# --------------------------------------------------------------------------- the judge


def rehearse(case: dict[str, Any], w3: Web3) -> EvidenceBundle:
    """Layer 1 on the live fork: the real Safe, the owners' signatures, a snapshot, a revert."""
    from contracts.setup import ensure_safe, sign_safe_tx
    from judge.run_fixture import ensure_usdc

    safe = ensure_safe(w3, quiet=True)
    ensure_usdc(w3, safe.address)
    tx = fork._case_safe_tx(case, safe.address, safe.functions.nonce().call())
    sigs = sign_safe_tx(bytes.fromhex(fork.safe_tx_hash(w3, safe.address, tx)[2:]))
    return fork.build_bundle(w3, safe.address, tx, sigs, case["description"])


def judge(
    proposal: Proposal, bundle: EvidenceBundle, *, replay: bool, backward_form: Narration | None = None,
    escalate_live: bool = True,
) -> JudgeResult:
    """One pass through the table. ``replay`` uses recorded forms and makes no model call for a
    description that has one; an amended description always needs one forward call."""
    calls: list[str] = []
    description = proposal.effective_description()
    bundle = bundle.model_copy(update={"description": description})

    # 1. the floor, before any model
    v = verdicting.decide(bundle)
    if v.decision == Decision.REJECT and v.floor_hits:
        return _finish(proposal, bundle, None, None, v, calls, escalate_live and not replay,
                       recorded_question(proposal.id) if replay and not proposal.amendments else None)

    # 2. forward (words) and backward (bytes), separate inputs
    fwd = None
    key = _sha(description)
    if key in proposal.forward_forms:
        fwd = ExpectedEffects.model_validate(proposal.forward_forms[key])
    elif replay and not proposal.amendments:
        fwd = recorded_forward(proposal.id)
    if fwd is None:
        fwd, iid, ms = forward.run(description, proposal.address_book, proposal.safe)
        calls.append(f"forward {forward.DEFAULT_MODEL} {ms} ms {iid}")
        proposal.forward_forms[key] = fwd.model_dump(mode="json")
    bwd = backward_form or (recorded_backward(proposal.id) if replay else None)
    if bwd is None:
        bwd, iid, ms = backward.run(bundle, proposal.address_book, proposal.safe)
        calls.append(f"backward {backward.DEFAULT_MODEL} {ms} ms {iid}")

    # 3-5. canon, compare, decide: code
    v = verdicting.decide(bundle, expected=fwd, observed=bwd, address_book=proposal.address_book)
    return _finish(proposal, bundle, fwd, bwd, v, calls, escalate_live and not replay,
                   recorded_question(proposal.id) if replay and not proposal.amendments else None)


def _finish(proposal, bundle, fwd, bwd, v: Verdict, calls, run_escalate: bool,
            recorded: HumanQuestion | None = None) -> JudgeResult:
    res = JudgeResult(proposal=proposal, bundle=bundle, forward=fwd, backward=bwd, verdict=v, calls=calls)
    if v.decision == Decision.MATCH:
        # 7. the stamp: code, the judge key, nothing else
        res.stamp = stamping.make_stamp(bundle)
        res.note = v.reasoning
    else:
        res.note = v.question or v.reasoning
        if recorded is not None:
            res.question = recorded
            res.note = escalate.compose(recorded, v.decision.value)
        elif run_escalate:
            r = Resolver(bundle, proposal.address_book)
            exp = canon.from_forward(fwd, bundle.description, r) if fwd else None
            obs = canon.from_backward(bwd, r) if bwd else None
            try:
                q, iid, ms = escalate.run(bundle.description, proposal.address_book, proposal.safe, v, exp, obs)
                res.question = q
                res.note = escalate.compose(q, v.decision.value)
                calls.append(f"escalate {escalate.DEFAULT_MODEL} {ms} ms {iid}")
            except Exception as exc:  # noqa: BLE001 - the question is a courtesy; the decision stands
                res.note = f"{res.note}\n(escalation unavailable: {type(exc).__name__})"
    return res


# --------------------------------------------------------------------------- answering an ASK


def answer(proposal: Proposal, owner: str, text: str, bundle: EvidenceBundle, w3: Web3 | None, *,
           backward_form: Narration | None, replay: bool) -> JudgeResult:
    """An owner answers the question. Their words become an amendment; the judge runs again on the
    same bytes. Only a current owner may amend; the check is on-chain when a fork is available."""
    owner = to_checksum_address(owner)
    if w3 is not None:
        safe = w3.eth.contract(address=to_checksum_address(bundle.safe_address), abi=IS_OWNER_ABI)
        if not safe.functions.isOwner(owner).call():
            raise PermissionError(f"{owner} is not an owner of the Safe; only owners may answer")
    proposal.amendments.append(Amendment(owner=owner, text=text.strip(), at=datetime.now(timezone.utc).isoformat()))
    res = judge(proposal, bundle, replay=replay, backward_form=backward_form)
    proposal.save()
    return res


# --------------------------------------------------------------------------- the chain


def sign_stamp(res: JudgeResult, w3: Web3, guard_address: str) -> str:
    if res.stamp is None:
        raise ValueError("no stamp: the verdict was not MATCH")
    sig = stamping.sign(res.stamp, w3.eth.chain_id, guard_address)
    res.stamp_signature = "0x" + sig.hex()
    return res.stamp_signature


def attest(res: JudgeResult, w3: Web3, guard, submitter: str) -> dict[str, Any]:
    if res.stamp is None or res.stamp_signature is None:
        raise ValueError("sign the stamp first")
    return stamping.attest(w3, guard, res.stamp, bytes.fromhex(res.stamp_signature[2:]), submitter)


def execute(res: JudgeResult, w3: Web3, safe, sender: str) -> dict[str, Any]:
    """The real execTransaction with the owners' signatures. The guard decides; we just report."""
    from contracts.setup import ZERO, sign_safe_tx

    st = res.bundle.safe_tx
    data = bytes.fromhex(st.data.removeprefix("0x"))
    sigs = sign_safe_tx(bytes.fromhex(res.bundle.safe_tx_hash[2:]))
    args = (st.to, st.value, data, st.operation, st.safe_tx_gas, st.base_gas, st.gas_price, st.gas_token,
            st.refund_receiver, sigs)
    fn = safe.functions.execTransaction(*args)
    try:
        fn.call({"from": sender})  # dry run surfaces the guard's custom error cleanly
    except Exception as exc:  # noqa: BLE001
        return {"executed": False, "error": str(exc)}
    rcpt = w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
    success = any(log["topics"] and log["topics"][0].to_0x_hex() == fork.EXECUTION_SUCCESS_TOPIC for log in rcpt["logs"])
    return {"executed": True, "block": rcpt["blockNumber"], "tx": rcpt["transactionHash"].to_0x_hex(),
            "execution_success": success}
