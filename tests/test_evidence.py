"""Layer 1 pipeline, offline: saved fork rehearsals rebuild into the saved bundles exactly,
and the bundles say what the transactions really did.

Regenerate the fixtures on a live fork with `uv run python -m judge.evidence.fork <case.json>`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from judge.evidence import fork, trace
from judge.evidence.fork import AccountState, PrestateDiff, RawFrame, Rehearsal
from judge.schemas import EvidenceBundle, SafeTx

BUNDLES = Path(__file__).resolve().parent.parent / "fixtures" / "bundles"
BENIGN_CASES = [
    "01_send_eth_ops", "02_pay_dana_usdc", "03_move_eth_usdc_hot", "04_add_owner_priya", "05_raise_threshold",
    "06_approve_uniswap_finite", "07_pay_three_contractors", "08_refund_sam", "09_routine_transfer_vague",
    "10_swap_usdc_eth_uniswap", "demo_aave", "demo_auditor",
]
# Floor-clean but the description contradicts the bytes: expected REJECT, from the model, not the floor.
MISMATCH_CASES = [
    "31_revoke_ravi_usdc", "32_pay_dana_wrong_wallet", "33_pay_ravi_but_approve", "34_uniswap_output_diverted",
    "35_add_owner_then_lower_threshold",
]
CASES = ["demo_bybit", *BENIGN_CASES, *MISMATCH_CASES]

SAFE = "0xDFECEf26e5d211b9935cABC9FAD1edB8960aaE47"
SINGLETON = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
A_USDC = "0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c"
MAX = "0x" + "ff" * 32


def load(case: str) -> tuple[Rehearsal, EvidenceBundle]:
    r = Rehearsal.model_validate_json((BUNDLES / f"{case}.rehearsal.json").read_text(encoding="utf-8"))
    b = EvidenceBundle.model_validate_json((BUNDLES / f"{case}.bundle.json").read_text(encoding="utf-8"))
    return r, b


@pytest.mark.parametrize("case", CASES)
def test_rehearsal_rebuilds_into_the_saved_bundle(case: str) -> None:
    r, saved = load(case)
    assert fork.to_bundle(r, saved.description, sources=saved.sources) == saved


@pytest.mark.parametrize("case", CASES)
def test_proxy_implementations_come_from_the_trace(case: str) -> None:
    _, b = load(case)
    assert b.sources[SAFE].implementation == SINGLETON
    assert b.execution_success


def test_bybit() -> None:
    _, b = load("demo_bybit")
    assert sorted((h.rule, tuple(h.cites)) for h in b.floor_hits) == [
        ("delegatecall_not_allowlisted", ("c4",)),
        ("protected_slot_write", ("s0",)),
        ("unverified_code", ("c4",)),
    ]
    c4 = b.entry("c4")
    assert c4.kind == "DELEGATECALL" and c4.storage_context == SAFE
    assert c4.function is None and c4.selector == "0xa9059cbb"  # unverified: never named
    s0 = b.entry("s0")
    assert s0.label == "Safe.singleton" and s0.after.endswith("bdd077f651ebe7f7b3ce16fe5f2b025be2969516")
    assert b.balance_diff == []  # "Transfer 500 ETH" moves no ETH


def test_aave_deposit() -> None:
    _, b = load("demo_aave")
    assert b.floor_hits == []
    deltas = {(x.holder, x.asset): x.delta for x in b.balance_diff}
    assert deltas[(SAFE, USDC)] == -10_000 * 10**6
    assert abs(deltas[(SAFE, A_USDC)] - 10_000 * 10**6) <= 1  # aToken scaled-balance rounding
    assert deltas[(A_USDC, USDC)] == 10_000 * 10**6
    supply = [c for c in b.call_tree if c.function == "supply(address,uint256,address,uint16)"]
    assert supply and {a.name: a.value for a in supply[0].args}["onBehalfOf"] == SAFE


def test_auditor_unlimited_approval_is_visible_but_not_a_floor_hit() -> None:
    _, b = load("demo_auditor")
    assert b.floor_hits == []  # unlimited approval is the model's question, not a hard rule
    allowance = [w for w in b.storage_diff if w.label and w.label.startswith("USDC.allowance[0xDFEC…aE47]")]
    assert len(allowance) == 1 and allowance[0].after == MAX
    approve = next(c for c in b.call_tree if c.function == "approve(address,uint256)" and c.to_address == USDC)
    assert {a.name: a.value for a in approve.args}["value"] == str(2**256 - 1)


def test_eth_transfer_and_no_relayer_gas() -> None:
    r, b = load("01_send_eth_ops")
    assert {x.holder: x.delta for x in b.balance_diff} == {
        SAFE: -5 * 10**18,
        "0xE1D9a0eADCb8082d7989D7304061c017bE296C31": 5 * 10**18,
    }
    assert r.relayer not in {x.holder for x in b.balance_diff}
    assert [w.label for w in b.storage_diff] == ["Safe.nonce"]


# --------------------------------------------------------------------------- trace.py details


def _rehearsal(diff: PrestateDiff, gas: int = 0) -> Rehearsal:
    return Rehearsal(
        safe_address=SAFE, chain_id=1, fork_block=1, executed_block=2,
        safe_tx=SafeTx(to=SAFE, value=0, data="0x", operation=0, nonce=0),
        safe_tx_hash="0x" + "00" * 32, tx_hash="0x" + "00" * 32, relayer=fork.RELAYER, relayer_gas_cost=gas,
        receipt_status=1, execution_success=True,
        frame=RawFrame.model_validate({"type": "CALL", "from": fork.RELAYER, "to": SAFE}), diff=diff,
    )


def test_slot_cleared_to_zero_is_a_write() -> None:
    # prestateTracer diffMode leaves a slot that became zero out of `post`
    diff = PrestateDiff(pre={SAFE.lower(): AccountState(storage={"0x05": "0x07"})},
                        post={SAFE.lower(): AccountState(storage={})})
    (w,) = trace.storage_writes(_rehearsal(diff))
    assert w.slot == "0x" + "00" * 31 + "05" and int(w.before, 16) == 7 and int(w.after, 16) == 0


def test_relayer_gas_is_not_a_balance_change() -> None:
    diff = PrestateDiff(pre={fork.RELAYER.lower(): AccountState(balance=hex(10**18))},
                        post={fork.RELAYER.lower(): AccountState(balance=hex(10**18 - 21000))})
    assert trace.balance_changes(_rehearsal(diff, gas=21000)) == []
