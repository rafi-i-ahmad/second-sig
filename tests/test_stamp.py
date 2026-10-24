"""judge/stamp.py: the Python digest is the guard's digest, and a stamped transaction gets through.

Offline tests use a throwaway key and a made-up guard address. The fork test (``--fork``, anvil
running on the mainnet fork) is the full on-chain loop for case 01 as the real system would run it:
rehearse, floor clean, stamp as if the verdict were MATCH, attest, execute with two owner
signatures. It leaves the guard set on the Safe and reverts everything else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from eth_account import Account
from eth_utils import keccak
from web3.exceptions import ContractLogicError

from judge import stamp as st
from judge.schemas import Stamp

REPO = Path(__file__).resolve().parent.parent
CASE_01 = REPO / "fixtures" / "cases" / "match" / "01_send_eth_ops.json"

GUARD = "0x7ee55531aacf54195D872EbBD1e19a1c725DD8A5"
NO_STAMP_SELECTOR = "66d21dae"  # SecondSig__NoStamp(bytes32)


@pytest.fixture
def key() -> Account:
    return Account.from_key(keccak(text="second-sig test judge, not a real key"))


@pytest.fixture
def stamp() -> Stamp:
    return Stamp(safeTxHash="0x" + "ab" * 32, forkBlock=21_895_239, judgeVersion=st.judge_version_hex())


# --------------------------------------------------------------------------- offline


def test_judge_version_is_keccak_of_label() -> None:
    assert st.judge_version_hex() == "0x" + keccak(text="second-sig/v1").hex()


def test_signature_shape_and_signer(stamp: Stamp, key: Account) -> None:
    sig = st.sign(stamp, 1, GUARD, key)
    assert len(sig) == 65 and sig[64] in (27, 28)
    assert int.from_bytes(sig[32:64], "big") <= st.HALF_N
    assert st.recover(stamp, 1, GUARD, sig) == key.address


def test_eth_account_digest_equals_manual_eip712(stamp: Stamp, key: Account) -> None:
    """sign() goes through eth_account's encoder; digest() is built by hand like the guard does it."""
    sig = st.sign(stamp, 1, GUARD, key)
    assert Account._recover_hash(st.digest(stamp, 1, GUARD), signature=sig) == key.address  # noqa: SLF001


@pytest.mark.parametrize("change", ["chain", "guard", "hash", "block", "version"])
def test_any_field_change_breaks_the_signature(stamp: Stamp, key: Account, change: str) -> None:
    sig = st.sign(stamp, 1, GUARD, key)
    chain, guard, s = 1, GUARD, stamp
    if change == "chain":
        chain = 11155111
    elif change == "guard":
        guard = "0x" + "11" * 20
    elif change == "hash":
        s = stamp.model_copy(update={"safeTxHash": "0x" + "cd" * 32})
    elif change == "block":
        s = stamp.model_copy(update={"forkBlock": stamp.forkBlock + 1})
    else:
        s = stamp.model_copy(update={"judgeVersion": "0x" + keccak(text="second-sig/old").hex()})
    assert st.recover(s, chain, guard, sig) != key.address


def test_bad_lengths_rejected() -> None:
    with pytest.raises(ValueError):
        st.as_tuple(Stamp(safeTxHash="0x1234", forkBlock=1, judgeVersion=st.judge_version_hex()))


# --------------------------------------------------------------------------- fork


@pytest.mark.fork
def test_case01_stamped_executes_through_guard(capsys: pytest.CaptureFixture[str]) -> None:
    from contracts.setup import OWNERS, ZERO, connect, ensure_guard, ensure_safe, rpc, sign_safe_tx
    from judge.evidence import fork

    w3 = connect()
    safe = ensure_safe(w3, quiet=True)
    guard = ensure_guard(w3, safe)  # stays set after the test: that is the demo state
    judge = st.judge_account()
    assert guard.functions.JUDGE().call() == judge.address, "guard was deployed for a different judge key"

    case = json.loads(CASE_01.read_text(encoding="utf-8"))
    snap = rpc(w3, "evm_snapshot", [])
    try:
        nonce0 = safe.functions.nonce().call()
        tx = fork._case_safe_tx(case, safe.address, nonce0)
        h = fork.safe_tx_hash(w3, safe.address, tx)
        owner_sigs = sign_safe_tx(bytes.fromhex(h[2:]))
        exec_args = (tx.to, tx.value, bytes.fromhex(tx.data.removeprefix("0x")), tx.operation, 0, 0, 0, ZERO, ZERO,
                     owner_sigs)
        recipient_before = w3.eth.get_balance(tx.to)

        # 1. rehearse (layer 1): the bundle the judge would see; nothing on the floor
        bundle = fork.build_bundle(w3, safe.address, tx, owner_sigs, case["description"])
        assert bundle.safe_tx_hash == h and bundle.execution_success and not bundle.floor_hits
        assert fork.to_checksum_address(w3.eth.get_storage_at(safe.address, fork.GUARD_SLOT)[-20:]) == guard.address

        # 2. two valid owner signatures, no stamp: the guard refuses
        with pytest.raises(ContractLogicError) as exc:
            safe.functions.execTransaction(*exec_args).call({"from": OWNERS[0].address})
        assert NO_STAMP_SELECTOR in str(exc.value) or NO_STAMP_SELECTOR in str(getattr(exc.value, "data", ""))

        # 3. the verdict would be MATCH: code signs the stamp, anyone submits it
        stamp = st.make_stamp(bundle)
        assert guard.functions.stampDigest(st.as_tuple(stamp)).call() == st.digest(stamp, w3.eth.chain_id, guard.address)
        sig = st.sign(stamp, w3.eth.chain_id, guard.address, judge)
        attest_rcpt = st.attest(w3, guard, stamp, sig, submitter=OWNERS[2].address)
        assert guard.functions.stamps(bytes.fromhex(h[2:])).call() == bundle.fork_block
        (attested,) = guard.events.Attested().process_receipt(attest_rcpt)
        assert attested["args"]["submitter"] == OWNERS[2].address

        # 4. the same transaction now executes through the real Safe and the real guard
        rcpt = w3.eth.wait_for_transaction_receipt(
            safe.functions.execTransaction(*exec_args).transact({"from": OWNERS[0].address})
        )
        assert rcpt["status"] == 1
        assert any(log["topics"][0].to_0x_hex() == fork.EXECUTION_SUCCESS_TOPIC for log in rcpt["logs"])
        assert w3.eth.get_balance(tx.to) - recipient_before == tx.value
        assert safe.functions.nonce().call() == nonce0 + 1

        # 5. the stamp is spent with the nonce: the same bytes at the next nonce have no stamp
        h_next = fork.safe_tx_hash(w3, safe.address, tx.model_copy(update={"nonce": nonce0 + 1}))
        with pytest.raises(ContractLogicError) as exc:
            safe.functions.execTransaction(*exec_args[:-1], sign_safe_tx(bytes.fromhex(h_next[2:]))).call(
                {"from": OWNERS[0].address}
            )
        assert NO_STAMP_SELECTOR in str(exc.value) or NO_STAMP_SELECTOR in str(getattr(exc.value, "data", ""))

        with capsys.disabled():
            print(
                f"\ncase 01 through the guard: safeTxHash {h}\n"
                f"  guard {guard.address}, judge {judge.address}, stamp forkBlock {stamp.forkBlock}\n"
                f"  attest in block {attest_rcpt['blockNumber']} (submitter owner 2), "
                f"execTransaction in block {rcpt['blockNumber']}: ExecutionSuccess, "
                f"{tx.value / 1e18:g} ETH to {tx.to}, nonce {nonce0} -> {nonce0 + 1}\n"
                f"  without the stamp, and again at the next nonce: SecondSig__NoStamp"
            )
    finally:
        assert rpc(w3, "evm_revert", [snap]), "evm_revert failed; the fork holds the test's state"
