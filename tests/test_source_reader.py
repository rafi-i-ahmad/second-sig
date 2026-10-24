"""The source-reader unit: code layouts, the tightening, corroboration, and the verdict delta.

Offline. Claims are hand-written against the saved Aave bundle; base slots were established by
recomputing keccak(key, base) + offset for every address in the evidence (see NOTES.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judge import corroborate, layouts, pipeline, verdict
from judge.schemas import Classification, Decision, EvidenceBundle, ExpectedEffects, Narration, SlotClaim

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
POOL = "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2"
ATOKEN = "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
SAFE = "0xDFECEf26e5d211b9935cABC9FAD1edB8960aaE47"


def bundle(cid: str) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json((FIXTURES / "bundles" / f"{cid}.bundle.json").read_text(encoding="utf-8"))


def case(cid: str) -> dict:
    (p,) = (FIXTURES / "cases").glob(f"*/{cid}.json")
    return json.loads(p.read_text(encoding="utf-8"))


def forms(cid: str) -> tuple[ExpectedEffects, Narration]:
    return pipeline.recorded_forward(cid), pipeline.recorded_backward(cid)


def cite(b: EvidenceBundle, contract: str, variable: str) -> dict:
    """A real source citation: the first line of the implementation's files that declares ``variable``."""
    src = b.sources[contract]
    files = b.sources[src.implementation].files if src.implementation else src.files
    for path, text in files.items():
        for i, line in enumerate(text.splitlines(), 1):
            if variable in line and ("mapping" in line or ";" in line) and "function" not in line:
                return {"path": path, "line": i}
    raise AssertionError(f"{variable} not declared in {contract}'s source")


def claim(b, cites, contract, variable, base_slot, key=None, offset=0, reading="routine_bookkeeping") -> SlotClaim:
    return SlotClaim(cites=cites, contract=contract, variable=variable, base_slot=base_slot, key=key, offset=offset,
                     source_cites=[cite(b, contract, variable)], reading=reading, sentence=f"{variable} changed",
                     confidence="high")


def aave_claims(b: EvidenceBundle) -> Classification:
    return Classification(reasoning="", items=[
        claim(b, ["s0"], POOL, "_usersConfig", 53, key=SAFE),
        *[claim(b, [sid], POOL, "_reserves", 52, key=USDC, offset=off)
          for sid, off in (("s1", 1), ("s2", 2), ("s3", 3), ("s4", 8), ("s5", 9))],
        claim(b, ["s6"], ATOKEN, "_totalSupply", 54),
        claim(b, ["s7"], ATOKEN, "_userState", 52, key=SAFE),
    ])


# --------------------------------------------------------------------------- code layouts


def test_known_layouts_label_the_uniswap_pair_and_weth() -> None:
    b = layouts.label_known(bundle("10_swap_usdc_eth_uniswap"))
    assert all(w.label for w in b.storage_diff), [w.id for w in b.storage_diff if not w.label]
    labels = {w.id: w.label for w in b.storage_diff}
    assert labels["s2"].startswith("UniswapV2Pair(USDC/WETH).reserves") and "WETH.balanceOf[" in labels["s5"]


def test_known_layouts_leave_aave_alone() -> None:
    b = layouts.label_known(bundle("demo_aave"))
    assert sum(1 for w in b.storage_diff if not w.label) == 8


# --------------------------------------------------------------------------- the tightening


def test_unlabelled_writes_called_info_are_not_explained() -> None:
    """Aave with no source check: the backward pass's 'reserve accounting' info effect cites s0-s6,
    which nothing has labelled. That is a question now, not bookkeeping."""
    b = bundle("demo_aave")
    fwd, bwd = forms("demo_aave")
    v = verdict.decide(b, expected=fwd, observed=bwd, address_book=case("demo_aave")["address_book"])
    assert v.decision == Decision.ASK
    assert any("nobody has labelled" in u.reason for u in v.compare.observed_unexplained)


def test_corroborated_source_claims_restore_the_match() -> None:
    b = bundle("demo_aave")
    c = corroborate.apply(b, aave_claims(b))
    assert c.rejected == [], c.rejected
    assert all(w.label for w in c.bundle.storage_diff)
    assert len(c.explained) == 8 and "_reserves[0xA0b8…eB48]+8" in " ".join(c.explained)
    fwd, bwd = forms("demo_aave")
    v = verdict.decide(c.bundle, expected=fwd, observed=bwd, address_book=case("demo_aave")["address_book"],
                       raised=c.raised, explained_slots=c.explained)
    assert v.decision == Decision.MATCH, v.reasoning
    assert len(v.compare.explained_slots) == 8


# --------------------------------------------------------------------------- corroboration refuses


def test_wrong_base_slot_is_rejected() -> None:
    b = bundle("demo_aave")
    bad = Classification(reasoning="", items=[claim(b, ["s1"], POOL, "_reserves", 51, key=USDC, offset=1)])
    c = corroborate.apply(b, bad)
    assert c.explained == [] and c.rejected and "slot does not equal" in c.rejected[0]
    assert not next(w for w in c.bundle.storage_diff if w.id == "s1").label


def test_missing_or_wrong_source_cite_is_rejected() -> None:
    b = bundle("demo_aave")
    from judge.schemas import SourceCite
    good = claim(b, ["s6"], ATOKEN, "_totalSupply", 54)
    nofile = good.model_copy(update={"source_cites": [SourceCite(path="nowhere/Fake.sol", line=1)]})
    wrongline = good.model_copy(update={"source_cites": [SourceCite(path=good.source_cites[0].path, line=1)]})
    c = corroborate.apply(b, Classification(reasoning="", items=[nofile, wrongline]))
    assert len(c.rejected) == 2 and "not in the verified source" in c.rejected[0]
    assert "mentions" in c.rejected[1]


def test_wrong_contract_and_already_labelled_are_rejected() -> None:
    b = bundle("demo_aave")
    wrong = claim(b, ["s1"], ATOKEN, "_userState", 52, key=USDC, offset=1)
    c = corroborate.apply(b, Classification(reasoning="", items=[wrong]))
    assert c.rejected and "belongs to" in c.rejected[0]
    labelled = claim(b, ["s10"], SAFE, "nonce", 5)  # s10 is Safe.nonce, labelled by code already
    c = corroborate.apply(b, Classification(reasoning="", items=[labelled]))
    assert c.rejected and ("already labelled" in c.rejected[0] or "belongs" in c.rejected[0] or "no verified" in c.rejected[0])


def test_a_control_reading_raises_and_never_labels() -> None:
    """Even a fully corroborated claim lowers nothing unless it reads as bookkeeping; a control
    reading on a write the backward pass called info turns that effect into a question."""
    b = bundle("demo_aave")
    items = aave_claims(b).items
    items[0] = items[0].model_copy(update={"reading": "control", "sentence": "the pool's admin flag flips"})
    c = corroborate.apply(b, Classification(reasoning="", items=items))
    assert "s0" in c.raised and not next(w for w in c.bundle.storage_diff if w.id == "s0").label
    fwd, bwd = forms("demo_aave")
    v = verdict.decide(c.bundle, expected=fwd, observed=bwd, address_book=case("demo_aave")["address_book"],
                       raised=c.raised, explained_slots=c.explained)
    assert v.decision == Decision.ASK and any("source reader read s0" in u.reason for u in v.compare.observed_unexplained)


def test_source_check_cannot_touch_a_notable_item_that_is_not_a_slot() -> None:
    """The auditor's unlimited allowance stays unexplained whatever the source reader says."""
    b = bundle("demo_auditor")
    fwd, bwd = forms("demo_auditor")
    v = verdict.decide(b, expected=fwd, observed=bwd, address_book=case("demo_auditor")["address_book"],
                       explained_slots=["s2 pretend: the allowance is fine"])
    assert v.decision == Decision.ASK


# --------------------------------------------------------------------------- through the pipeline


def test_pipeline_replay_aave_asks_without_a_recorded_classification(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path)
    monkeypatch.setattr(pipeline, "recorded_leftovers", lambda cid: (None, None))
    res = pipeline.judge(pipeline.Proposal.from_case(case("demo_aave")), bundle("demo_aave"), replay=True)
    assert res.verdict.decision == Decision.ASK and res.stamp is None


def test_pipeline_replay_aave_matches_with_a_classification(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path)
    b = bundle("demo_aave")
    monkeypatch.setattr(pipeline, "recorded_leftovers", lambda cid: (aave_claims(b), 123_456))
    res = pipeline.judge(pipeline.Proposal.from_case(case("demo_aave")), b, replay=True)
    assert res.verdict.decision == Decision.MATCH and res.stamp is not None
    assert len(res.source_check) == 8 and res.source_tokens == 123_456 and res.calls == []


@pytest.mark.parametrize("cid", ["10_swap_usdc_eth_uniswap", "01_send_eth_ops", "demo_auditor"])
def test_other_cases_unchanged_by_the_unit(cid: str, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path)
    res = pipeline.judge(pipeline.Proposal.from_case(case(cid)), bundle(cid), replay=True)
    assert res.verdict.decision == Decision(case(cid)["expected_verdict"])
