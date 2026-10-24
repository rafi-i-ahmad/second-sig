"""judge/pipeline.py: the whole table by replay, the amendment flow, and the stamp on MATCH.

Offline tests patch the forward pass with a recorded or hand-written form so no model runs.
The fork test (--fork) stamps, attests and executes the Aave demo through the guard on anvil.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judge import pipeline
from judge.jobs import forward
from judge.schemas import Decision, ExpectedEffects

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def case(cid: str) -> dict:
    (p,) = (FIXTURES / "cases").glob(f"*/{cid}.json")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_records(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path / "proposals")


def replay(cid: str) -> pipeline.JudgeResult:
    return pipeline.judge(pipeline.Proposal.from_case(case(cid)), pipeline.recorded_bundle(cid), replay=True)


# --------------------------------------------------------------------------- the table by replay


def _needs_source_check(cid: str) -> None:
    """Aave's MATCH depends on the recorded source-reader classification (fixtures/outputs/
    demo_aave.leftovers.json). Without it the comparison asks about the unlabelled writes, by
    design; tests/test_source_reader.py pins both outcomes with hand-written claims."""
    if cid == "demo_aave" and pipeline.recorded_leftovers(cid)[0] is None:
        pytest.skip("no recorded leftovers classification for demo_aave; run the source reader live to record one")


@pytest.mark.parametrize("cid,decision", [
    ("01_send_eth_ops", Decision.MATCH), ("10_swap_usdc_eth_uniswap", Decision.MATCH), ("demo_aave", Decision.MATCH),
    ("demo_auditor", Decision.ASK), ("09_routine_transfer_vague", Decision.ASK),
    ("32_pay_dana_wrong_wallet", Decision.ASK), ("35_add_owner_then_lower_threshold", Decision.REJECT),
    ("demo_bybit", Decision.REJECT),
])
def test_replay_reaches_the_expected_verdict_without_a_model(cid: str, decision: Decision) -> None:
    _needs_source_check(cid)
    res = replay(cid)
    assert res.verdict.decision == decision and res.calls == []


def test_match_carries_a_stamp_and_nothing_else_does() -> None:
    _needs_source_check("demo_aave")
    aave = replay("demo_aave")
    assert aave.stamp is not None and aave.stamp.safeTxHash == aave.bundle.safe_tx_hash
    assert aave.stamp.forkBlock == aave.bundle.fork_block and aave.stamp_signature is None
    assert replay("demo_auditor").stamp is None and replay("demo_bybit").stamp is None


def test_bybit_reads_the_words_but_never_runs_the_backward_pass() -> None:
    """A floor hit decides; the forward form is for the signer to read, never for the table."""
    res = replay("demo_bybit")
    assert res.forward is not None and res.backward is None and res.verdict.floor_hits
    assert res.verdict.decision == Decision.REJECT and res.verdict.compare is None


def test_a_failed_forward_pass_cannot_lift_a_floor_reject(monkeypatch) -> None:
    def broken(*_, **__):
        raise RuntimeError("model down")

    monkeypatch.setattr(pipeline, "recorded_forward", lambda _cid: None)
    monkeypatch.setattr(forward, "run", broken)
    res = replay("demo_bybit")
    assert res.verdict.decision == Decision.REJECT and res.forward is None and res.stamp is None
    assert res.calls == ["forward unavailable: RuntimeError"]


def test_ask_note_is_the_question_when_escalation_is_off() -> None:
    res = replay("demo_auditor")
    assert "unlimited" in res.note


# --------------------------------------------------------------------------- answering an ASK


def test_an_owners_answer_amends_the_words_and_the_judge_reruns(monkeypatch) -> None:
    """Auditor: ASK. Owner 1 answers that the allowance is intended. The forward pass (patched with
    the form it would return for the amended words) now lists the allowance; MATCH; stamp."""
    cid = "demo_auditor"
    seen: dict = {}

    def fake_forward(description, address_book, safe, amendments=None, **_):
        seen["description"], seen["amendments"] = description, amendments
        form = ExpectedEffects(
            reasoning="", confidence="high", nothing_else=True,
            movements=[{"asset": "USDC", "amount_human": "100 USDC", "from_name": "Safe", "to_name": "auditor",
                        "cites": "Pay our auditor 100 USDC"}],
            permission_changes=[{"asset": "USDC", "owner_name": "Safe", "spender_name": "auditor",
                                 "amount_human": "unlimited", "cites": "unlimited USDC allowance"}],
        )
        return form, "fake-interaction", 1

    monkeypatch.setattr(forward, "run", fake_forward)
    proposal = pipeline.Proposal.from_case(case(cid))
    bundle = pipeline.recorded_bundle(cid)
    first = pipeline.judge(proposal, bundle, replay=True)
    assert first.verdict.decision == Decision.ASK

    owner = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    second = pipeline.answer(proposal, owner, "Yes, grant the auditor an unlimited USDC allowance for monthly invoicing.",
                             bundle, None, backward_form=pipeline.recorded_backward(cid), replay=True)
    assert second.verdict.decision == Decision.MATCH, second.verdict.reasoning
    assert second.stamp is not None
    # the answer reaches the forward pass on its own, attributed, not joined into the description
    assert seen["description"] == "Pay our auditor 100 USDC"
    assert seen["amendments"] == [(owner, "Yes, grant the auditor an unlimited USDC allowance for monthly invoicing.")]
    assert second.bundle.description.startswith("Pay our auditor 100 USDC\nOwner 0x7099")
    assert second.calls and second.calls[0].startswith("forward")
    # the amendment and the form it produced are on the record, so the next replay needs no call
    saved = pipeline.Proposal.model_validate_json((pipeline.PROPOSALS / f"{cid}.json").read_text(encoding="utf-8"))
    assert len(saved.amendments) == 1 and saved.forward_forms
    third = pipeline.judge(saved, bundle, replay=True, backward_form=pipeline.recorded_backward(cid))
    assert third.verdict.decision == Decision.MATCH and third.calls == []


def test_an_answer_cannot_lift_a_floor_reject(monkeypatch) -> None:
    monkeypatch.setattr(forward, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    cid = "demo_bybit"
    proposal = pipeline.Proposal.from_case(case(cid))
    res = pipeline.answer(proposal, "0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "It is fine, I checked.",
                          pipeline.recorded_bundle(cid), None, backward_form=None, replay=True)
    assert res.verdict.decision == Decision.REJECT and res.verdict.floor_hits


def test_an_answer_that_does_not_cover_the_gap_asks_again(monkeypatch) -> None:
    cid = "demo_auditor"
    unchanged = pipeline.recorded_forward(cid)
    monkeypatch.setattr(forward, "run", lambda *a, **k: (unchanged, "fake", 1))
    proposal = pipeline.Proposal.from_case(case(cid))
    res = pipeline.answer(proposal, "0x70997970C51812dc3A010C7d01b50e0d17dc79C8", "Looks fine to me.",
                          pipeline.recorded_bundle(cid), None, backward_form=pipeline.recorded_backward(cid), replay=True)
    assert res.verdict.decision == Decision.ASK and res.stamp is None


def test_effective_description_attributes_each_amendment() -> None:
    p = pipeline.Proposal.from_case(case("demo_auditor"))
    p.amendments.append(pipeline.Amendment(owner="0x70997970C51812dc3A010C7d01b50e0d17dc79C8", text="Yes.", at="t"))
    assert p.effective_description() == "Pay our auditor 100 USDC\nOwner 0x70997970C51812dc3A010C7d01b50e0d17dc79C8: Yes."


# --------------------------------------------------------------------------- the chain


@pytest.mark.fork
def test_aave_match_stamps_attests_and_executes_on_the_fork() -> None:
    from contracts.setup import OWNERS, connect, ensure_guard, ensure_safe, rpc
    from judge.run_fixture import ensure_usdc
    w3 = connect()
    safe = ensure_safe(w3, quiet=True)
    guard = ensure_guard(w3, safe)
    ensure_usdc(w3, safe.address)  # the recorded bundle deposits 10,000 USDC; a fresh fork holds none
    res = replay("demo_aave")
    assert res.verdict.decision == Decision.MATCH
    assert res.bundle.safe_tx.nonce == safe.functions.nonce().call(), "fork nonce moved; reset the fork to replay"
    snap = rpc(w3, "evm_snapshot", [])
    try:
        before = pipeline.execute(res, w3, safe, OWNERS[0].address)
        assert not before["executed"] and ("66d21dae" in before["error"] or "NoStamp" in before["error"])
        pipeline.sign_stamp(res, w3, guard.address)
        pipeline.attest(res, w3, guard, OWNERS[2].address)
        after = pipeline.execute(res, w3, safe, OWNERS[0].address)
        assert after["executed"] and after["execution_success"]
    finally:
        assert rpc(w3, "evm_revert", [snap])
