"""canon.py, checker.py, compare.py and the comparison rows of verdict.py, by replay.

Everything here runs on recorded forms in fixtures/outputs/ and saved bundles: no model call.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judge import canon, compare, truth, verdict
from judge.canon import Resolver
from judge.schemas import Decision, EvidenceBundle, ExpectedEffects, Narration, ObservedEffect

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def case(cid: str) -> dict:
    (path,) = (FIXTURES / "cases").glob(f"*/{cid}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def bundle(cid: str) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json((FIXTURES / "bundles" / f"{cid}.bundle.json").read_text(encoding="utf-8"))


def forward(cid: str) -> ExpectedEffects:
    raw = json.loads((FIXTURES / "outputs" / f"{cid}.forward.json").read_text(encoding="utf-8"))
    return ExpectedEffects.model_validate(raw["expected_effects"])


def backward(cid: str) -> Narration:
    raw = json.loads((FIXTURES / "outputs" / f"{cid}.backward.json").read_text(encoding="utf-8"))
    return Narration.model_validate(raw["narration"])


def resolver(cid: str) -> Resolver:
    return Resolver(bundle(cid), case(cid)["address_book"])


def decide(cid: str, fwd: ExpectedEffects | None, bwd: Narration | None):
    return verdict.decide(bundle(cid), expected=fwd, observed=bwd, address_book=case(cid)["address_book"])


# --------------------------------------------------------------------------- canon


def test_parties_resolve_by_address_book_safe_and_address() -> None:
    r = resolver("01_send_eth_ops")
    ops = case("01_send_eth_ops")["address_book"]["ops wallet"]
    assert r.party("ops wallet").address == ops and r.party("the ops wallet").via == "address_book"
    assert r.party("Safe").address == r.safe and r.party(r.safe).label == "Safe"
    assert r.party(ops).label == "ops wallet" and r.party(ops).via == "address"
    assert r.party("0x0000000000000000000000000000000000000000").via == "zero"
    assert not r.party("Dana").resolved


def test_label_resolves_via_sources_as_last_resort() -> None:
    r = resolver("demo_aave")
    p = r.party("FiatTokenProxy")
    assert p.via == "sources" and p.address == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def test_chain_symbol_is_never_identity_but_evidence_is() -> None:
    r = resolver("demo_aave")
    assert not r.asset("aEthUSDC").resolved, "a bare chain symbol must not resolve"
    a = r.asset("aEthUSDC", ["b0"])
    assert a.via == "evidence" and a.address == "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c" and a.decimals == 6
    assert r.asset("USDC").via == "address_book"
    assert r.asset("ETH").address == "ETH" and r.asset("ETH").decimals == 18


def test_upper_bounds_and_unlimited_words() -> None:
    assert canon.parse_amount("at most 1 ETH") == 1 and canon.is_upper_bound("at most 1 ETH")
    assert canon.is_upper_bound("up to 500 USDC") and not canon.is_upper_bound("500 USDC")
    assert canon.parse_amount("a maximum of 2 ETH") == 2, "a number wins over the word maximum"
    assert canon.parse_amount("maximum") == "unlimited" and canon.parse_amount("unlimited") == "unlimited"


def test_at_most_matches_anything_up_to_the_ceiling() -> None:
    """Case 34's words: 'spending at most 1 ETH'. The recorded trace spends 0.35 ETH net, which the
    backward pass reports as ETH Safe -> WETH inside the router call."""
    fwd = ExpectedEffects(
        reasoning="", confidence="high", nothing_else=True,
        movements=[{"asset": "ETH", "amount_human": "at most 1 ETH", "from_name": "Safe", "to_name": "Uniswap",
                    "cites": "spending at most 1 ETH"}],
    )
    r = resolver("34_uniswap_output_diverted")
    e = canon.from_forward(fwd, bundle("34_uniswap_output_diverted").description, r)
    assert e.movements[0].amount_base is None and e.movements[0].amount_max_base == 10**18
    o = canon.from_backward(backward("34_uniswap_output_diverted"), r)
    eth_out = next(m for m in o.movements if m.asset.address == "ETH" and m.direction == "out")
    m = compare.match_movement(e.movements[0], eth_out, r)
    assert m is not None and m.tier in ("amount_unconstrained", "counterparty_via_callee")
    too_much = eth_out.model_copy(update={"amount_base": 2 * 10**18})
    assert compare.match_movement(e.movements[0], too_much, r) is None


def test_amounts_to_base_units_and_allowances() -> None:
    r = resolver("demo_aave")
    assert r.to_base("10,000 USDC", r.asset("USDC")) == 10_000 * 10**6
    assert r.to_base("0.5 ETH", r.asset("ETH")) == 5 * 10**17
    assert r.to_base(None, r.asset("ETH")) is None
    assert canon.parse_amount("unlimited") == "unlimited"
    assert canon.allowance_value(None, 2**256 - 1) == "unlimited"
    assert canon.allowance_value(None, 0) == "zero"
    assert canon.allowance_value("1,000 USDC", 1_000_000_000) == 1_000_000_000


def test_recorded_aave_backward_canonical_shape() -> None:
    r = resolver("demo_aave")
    o = canon.from_backward(backward("demo_aave"), r)
    assert o.uncited == []
    assets = {m.asset.address for m in o.movements}
    assert "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48" in assets  # USDC out
    assert "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c" in assets  # aUSDC in, via evidence
    mint = next(m for m in o.movements if m.direction == "in")
    assert mint.from_party.via == "zero" and mint.amount_base == 10_000 * 10**6
    (perm,) = o.permissions
    assert perm.spender.label == "Aave v3 Pool" and perm.new_allowance == 10_000 * 10**6
    assert {e.severity for e in o.effects} == {"info", "notable"}


def test_recorded_auditor_backward_shows_unlimited_allowance() -> None:
    o = canon.from_backward(backward("demo_auditor"), resolver("demo_auditor"))
    (perm,) = o.permissions
    assert perm.new_allowance == "unlimited" and perm.severity == "notable"


def test_recorded_bybit_backward_has_critical_effects_and_no_movements() -> None:
    o = canon.from_backward(backward("demo_bybit"), resolver("demo_bybit"))
    assert o.movements == [] and [e.severity for e in o.effects].count("critical") == 2


def test_forward_phrase_must_be_in_description() -> None:
    r = resolver("01_send_eth_ops")
    f = forward("01_send_eth_ops")
    assert canon.from_forward(f, bundle("01_send_eth_ops").description, r).unsupported == []
    bad = f.model_copy(update={"movements": [f.movements[0].model_copy(update={"cites": "pay the auditor"})]})
    assert canon.from_forward(bad, bundle("01_send_eth_ops").description, r).unsupported


# --------------------------------------------------------------------------- truth


def test_truth_from_calldata_01_and_aave() -> None:
    r = resolver("01_send_eth_ops")
    t = truth.derive(case("01_send_eth_ops"), r)
    assert [canon.render_movement(m) for m in t.movements] == ["5 ETH Safe -> ops wallet"]
    r = resolver("demo_aave")
    t = truth.derive(case("demo_aave"), r)
    assert {m.asset.address for m in t.movements} == {
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c"}
    assert t.permissions[0].new_allowance == 10_000 * 10**6 and t.notes


def test_truth_config_changes() -> None:
    t = truth.derive(case("35_add_owner_then_lower_threshold"), resolver("35_add_owner_then_lower_threshold"))
    assert [(c.field, c.new) for c in t.configs][-1] == ("threshold", "1")
    assert ("owners_add", case("35_add_owner_then_lower_threshold")["address_book"]["Ravi"]) in [
        (c.field, c.new) for c in t.configs]


# --------------------------------------------------------------------------- compare + verdict by replay


def test_01_replays_to_match() -> None:
    v = decide("01_send_eth_ops", forward("01_send_eth_ops"), backward("01_send_eth_ops"))
    assert v.decision == Decision.MATCH
    assert v.compare is not None and v.compare.tiers == ["exact"] and v.compare.observed_unexplained == []


def test_bybit_replays_to_reject_before_any_form() -> None:
    v = decide("demo_bybit", None, backward("demo_bybit"))
    assert v.decision == Decision.REJECT and len(v.floor_hits) == 3


def test_missing_backward_form_is_ask() -> None:
    v = decide("01_send_eth_ops", forward("01_send_eth_ops"), None)
    assert v.decision == Decision.ASK and "no checked backward form" in v.reasons


def test_none_amount_matches_any_observed_amount() -> None:
    f = forward("01_send_eth_ops")
    loose = f.model_copy(update={"movements": [f.movements[0].model_copy(update={"amount_human": None})]})
    v = decide("01_send_eth_ops", loose, backward("01_send_eth_ops"))
    assert v.decision == Decision.MATCH and v.compare.tiers == ["amount_unconstrained"]


def test_uncited_critical_effect_forces_reject_even_with_matching_lists() -> None:
    b = backward("01_send_eth_ops")
    spiked = b.model_copy(update={"effects": [*b.effects, ObservedEffect(
        sentence="The Safe's singleton was overwritten.", severity="critical", cites=["s99"])]})
    v = decide("01_send_eth_ops", forward("01_send_eth_ops"), spiked)
    assert v.decision == Decision.REJECT
    assert v.compare.uncited and v.compare.observed_unexplained[0].reason.startswith("citations do not resolve")


def test_uncited_notable_effect_forces_ask() -> None:
    b = backward("01_send_eth_ops")
    spiked = b.model_copy(update={"effects": [*b.effects, ObservedEffect(
        sentence="Something notable.", severity="notable", cites=["c42"])]})
    assert decide("01_send_eth_ops", forward("01_send_eth_ops"), spiked).decision == Decision.ASK


def test_unsupported_forward_item_cannot_explain() -> None:
    f = forward("01_send_eth_ops")
    bad = f.model_copy(update={"movements": [f.movements[0].model_copy(update={"cites": "not in the text"})]})
    v = decide("01_send_eth_ops", bad, backward("01_send_eth_ops"))
    assert v.decision == Decision.ASK and v.compare.unsupported and v.compare.observed_unexplained


def test_nothing_else_false_is_ask_with_the_forward_question() -> None:
    f = forward("01_send_eth_ops").model_copy(update={"nothing_else": False, "questions_for_human": ["Which wallet?"]})
    v = decide("01_send_eth_ops", f, backward("01_send_eth_ops"))
    assert v.decision == Decision.ASK and v.question == "Which wallet?"


def test_auditor_backward_against_a_forward_that_promises_only_the_payment() -> None:
    """The recorded auditor narration against a hand-written forward form: the unlimited approval
    is observed, nothing expected explains it, so ASK with a question naming it."""
    fwd = ExpectedEffects(
        reasoning="", confidence="high", nothing_else=True,
        movements=[{"asset": "USDC", "amount_human": "100 USDC", "from_name": "Safe", "to_name": "auditor",
                    "cites": "Pay our auditor 100 USDC"}],
    )
    v = decide("demo_auditor", fwd, backward("demo_auditor"))
    assert v.decision == Decision.ASK
    assert "unlimited" in v.question and any(m.tier == "exact" for m in v.compare.matched)


def aave_checked():
    """The Aave bundle with its eight reserve-accounting writes labelled by corroborated source
    claims (see tests/test_source_reader.py); without them the comparison asks about the writes."""
    from judge import corroborate
    from tests.test_source_reader import aave_claims
    b = bundle("demo_aave")
    c = corroborate.apply(b, aave_claims(b))
    assert c.rejected == []
    return c


def decide_aave(fwd, bwd):
    c = aave_checked()
    return verdict.decide(c.bundle, expected=fwd, observed=bwd, address_book=case("demo_aave")["address_book"],
                          raised=c.raised, explained_slots=c.explained)


def test_aave_backward_against_a_forward_that_promises_the_deposit() -> None:
    """USDC lands in the aToken contract, not the Pool the words name, and the receipt token is
    minted from the zero address: both are inside the Safe's call into the Pool, so they match
    under counterparty_via_callee; 'aUSDC' is not in the address book, so asset_unresolved."""
    fwd = ExpectedEffects(
        reasoning="", confidence="high", nothing_else=True,
        movements=[
            {"asset": "USDC", "amount_human": "10,000 USDC", "from_name": "Safe", "to_name": "Aave v3 Pool",
             "cites": "Deposit 10,000 USDC into Aave v3"},
            {"asset": "aUSDC", "amount_human": "10,000 aUSDC", "from_name": "Aave v3 Pool", "to_name": "Safe",
             "cites": "Deposit 10,000 USDC into Aave v3"},
        ],
        permission_changes=[{"asset": "USDC", "owner_name": "Safe", "spender_name": "Aave v3 Pool",
                             "amount_human": "10,000 USDC", "cites": "Deposit 10,000 USDC into Aave v3"}],
    )
    v = decide_aave(fwd, backward("demo_aave"))
    assert v.decision == Decision.MATCH, v.reasoning
    assert set(v.compare.tiers) >= {"exact", "counterparty_via_callee", "asset_unresolved"}
    assert v.compare.observed_unexplained == [] and v.compare.expected_unobserved == []


def test_aave_recorded_forward_without_the_receipt_token_still_matches() -> None:
    """The recorded Flash forward form read the deposit as USDC out plus the approval, with no
    aUSDC coming back. The mint is received from inside the Safe's call into the Pool, so it is
    explained under inbound_from_callee: receiving an asset cannot drain the Safe."""
    v = decide_aave(forward("demo_aave"), backward("demo_aave"))
    assert v.decision == Decision.MATCH, v.reasoning
    assert "inbound_from_callee" in v.compare.tiers and v.compare.observed_unexplained == []


def test_inbound_tolerance_never_explains_an_outbound_movement() -> None:
    """Same rule, other direction: USDC leaving the Safe to an address the words did not name,
    inside a licensed call, is still unexplained unless the counterparty rule covers it."""
    f = forward("demo_aave").model_copy(update={"movements": []})  # the words license no movement at all
    v = decide("demo_aave", f, backward("demo_aave"))
    assert v.decision == Decision.ASK
    assert any("USDC Safe ->" in u.item for u in v.compare.observed_unexplained)


def test_internal_tolerance_does_not_cover_a_diverted_output() -> None:
    """Case 34's shape on case 10's recorded forms: the swap's output asset (ETH, which the words
    expect the Safe to receive) leaves the router for a plain address inside the router call.
    Neither 'inside a licensed call' nor 'third party' makes that bookkeeping."""
    from judge.schemas import ObservedMovement
    b = backward("10_swap_usdc_eth_uniswap")
    ravi = "0x2C81904f370e7f6490aEa328CA847AEFdc3853D3"
    diverted = ObservedMovement(asset="ETH", amount_human="1.76 ETH", amount_base_units="1761817265430573461",
                                from_name="Uniswap router", to_name=ravi, cites=["c18"])
    spiked = b.model_copy(update={"movements": [m for m in b.movements if m.asset != "ETH"] + [diverted]})
    v = decide("10_swap_usdc_eth_uniswap", forward("10_swap_usdc_eth_uniswap"), spiked)
    assert v.decision == Decision.ASK
    assert any(ravi in u.item for u in v.compare.observed_unexplained)
    assert "internal_to_callee" not in v.compare.tiers


def test_internal_tolerance_covers_contract_to_contract_plumbing() -> None:
    """The WETH leg pair -> router inside the router call: contracts both ends, not an asset the
    words expect the Safe to receive. Bookkeeping."""
    from judge.schemas import ObservedMovement
    b = backward("10_swap_usdc_eth_uniswap")
    leg = ObservedMovement(asset="WETH", amount_human="1.76 WETH", amount_base_units="1761817265430573461",
                           from_name="0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc", to_name="Uniswap router",
                           cites=["e5"])
    spiked = b.model_copy(update={"movements": [*b.movements, leg]})
    v = decide("10_swap_usdc_eth_uniswap", forward("10_swap_usdc_eth_uniswap"), spiked)
    assert v.decision == Decision.MATCH and "internal_to_callee" in v.compare.tiers


@pytest.mark.parametrize("cid", ["demo_bybit"])
def test_floor_still_wins_over_a_perfect_comparison(cid: str) -> None:
    v = decide(cid, ExpectedEffects(reasoning="", confidence="high", nothing_else=True,
                                    movements=[{"asset": "ETH", "amount_human": "500 ETH", "from_name": "Safe",
                                                "to_name": "warm wallet", "cites": "Transfer 500 ETH to the warm wallet"}]),
               backward(cid))
    assert v.decision == Decision.REJECT and v.floor_hits
