"""The Sepolia / Safe{Wallet} integration, offline: the Transaction Service's shapes, the fork-only
approval signatures, the refusal to judge bytes whose hash the service misreports, redaction, the
EIP-7708 log, and the Safe App manifest. Nothing here touches a network.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from eth_abi import encode
from eth_utils import keccak, to_checksum_address

from judge.evidence import trace
from judge.evidence.fork import RawFrame
from sepolia import chain, txservice
from sepolia.txservice import ServiceTx

SAFE = "0x2df08CD8691F7f99131d19068f6f363b7627c287"
OWNER_A = "0x72b013E3B82eD9A82d773176c3dA404872bc0dE5"
OWNER_B = "0x0694fc4D629C5261bF2873f7784809698035236D"
HASH = "0x" + "ab" * 32

# One queued ETH send, as GET /v1/multisig-transactions/{hash}/ returns it (trimmed)
SERVICE_TX = {
    "safe": SAFE, "to": "0xE1D9a0eADCb8082d7989D7304061c017bE296C31", "value": "10000000000000000",
    "data": None, "operation": 0, "gasToken": "0x0000000000000000000000000000000000000000",
    "safeTxGas": "0", "baseGas": "0", "gasPrice": "0", "refundReceiver": None, "nonce": "3",
    "safeTxHash": HASH, "isExecuted": False, "confirmationsRequired": 2,
    "confirmations": [{"owner": OWNER_B, "signature": "0x" + "11" * 65, "submissionDate": "2026-10-24T20:00:00Z"}],
    "origin": json.dumps({"url": "https://app.safe.global", "note": "Send 0.01 ETH to the ops wallet"}),
    "dataDecoded": None, "unknownField": 1,
}


# --------------------------------------------------------------------------- the note


@pytest.mark.parametrize("origin, expected", [
    (json.dumps({"note": "Pay our auditor 5 USDC"}), "Pay our auditor 5 USDC"),
    (json.dumps({"url": "https://x", "name": "Transaction Builder", "note": "  Pay Ravi  "}), "Pay Ravi"),
    ({"note": "already parsed"}, "already parsed"),
    (json.dumps({"url": "https://app", "name": "WalletConnect"}), None),  # an app origin, no note
    ("https://some-dapp.example", None),                                  # a plain origin string is not a note
    (json.dumps({"note": ""}), None),
    (json.dumps({"note": 5}), None),
    (None, None),
])
def test_note_reads_only_safe_wallets_note(origin, expected):
    assert txservice.note(origin) == expected


def test_origin_with_note_is_capped_like_the_service():
    assert json.loads(txservice.origin_with_note("Install the guard")) == {"note": "Install the guard"}
    with pytest.raises(ValueError):
        txservice.origin_with_note("x" * 200)


# --------------------------------------------------------------------------- the service's transaction


def test_service_tx_becomes_the_struct_the_owners_sign():
    t = ServiceTx.model_validate(SERVICE_TX)
    st = t.safe_tx()
    assert st.data == "0x" and st.value == 10**16 and st.nonce == 3 and st.operation == 0
    assert st.refund_receiver == "0x0000000000000000000000000000000000000000"
    assert t.note() == "Send 0.01 ETH to the ops wallet"
    assert t.confirmations_required == 2 and t.confirmations[0].owner == OWNER_B


def test_unknown_operation_is_refused():
    with pytest.raises(ValueError):
        ServiceTx.model_validate(SERVICE_TX | {"operation": 2}).safe_tx()


def test_confirmations_pack_sorted_by_owner():
    sig_a, sig_b = "0x" + "aa" * 65, "0x" + "bb" * 65
    t = ServiceTx.model_validate(SERVICE_TX | {"confirmations": [
        {"owner": OWNER_A, "signature": sig_a}, {"owner": OWNER_B, "signature": sig_b}]})
    assert txservice.signatures(t) == bytes.fromhex("bb" * 65 + "aa" * 65)  # OWNER_B < OWNER_A


# --------------------------------------------------------------------------- fork-only approvals


def test_approved_hash_signatures_are_v1_sorted_by_owner():
    sigs = chain.approved_hash_signatures([OWNER_A, OWNER_B])
    assert len(sigs) == 130
    first, second = sigs[:65], sigs[65:]
    assert to_checksum_address(first[12:32]) == OWNER_B and to_checksum_address(second[12:32]) == OWNER_A
    for s in (first, second):
        assert s[32:64] == bytes(32) and s[64] == 1


def test_approved_hash_slot_is_safe_141_slot_8():
    inner = keccak(encode(["address", "uint256"], [OWNER_A, 8]))
    expected = "0x" + keccak(bytes.fromhex(HASH[2:]) + inner).hex()
    assert chain.approved_hash_slot(OWNER_A, HASH) == expected


def test_approve_in_fork_refuses_a_remote_chain():
    remote = SimpleNamespace(eth=SimpleNamespace(chain_id=chain.CHAIN_ID),
                             provider=SimpleNamespace(endpoint_uri="https://eth-sepolia.example/v2/key"))
    with pytest.raises(chain.SepoliaUnavailable):
        chain.approve_in_fork(remote, SAFE, HASH, [OWNER_A])


# --------------------------------------------------------------------------- refusal on a hash mismatch


def test_watcher_refuses_bytes_whose_hash_the_service_misreports(monkeypatch, tmp_path):
    from sepolia import watcher as watcher_mod

    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setenv("SEPOLIA_SAFE", SAFE)
    monkeypatch.setattr(chain, "refork", lambda fork, block: None)
    reader = SimpleNamespace(functions=SimpleNamespace(nonce=lambda: SimpleNamespace(call=lambda: 3)))
    monkeypatch.setattr(chain, "safe_reader", lambda w3, safe=None: reader)
    monkeypatch.setattr(watcher_mod.evidence_fork, "safe_tx_hash", lambda w3, safe, tx: "0x" + "cd" * 32)
    built = []
    monkeypatch.setattr(watcher_mod.evidence_fork, "build_bundle", lambda *a: built.append(a))

    w = watcher_mod.Watcher()
    w._live = SimpleNamespace(eth=SimpleNamespace(block_number=100))
    w._fork = object()
    got = w._rehearse(ServiceTx.model_validate(SERVICE_TX), "Send 0.01 ETH to the ops wallet", lambda e, p: None)
    assert isinstance(got, watcher_mod.Entry) and got.status == "refused"
    assert not built, "nothing may be rehearsed when the hash does not match"


def test_watcher_waits_for_an_earlier_nonce(monkeypatch, tmp_path):
    from sepolia import watcher as watcher_mod

    monkeypatch.setattr(chain, "LOGS", tmp_path)
    monkeypatch.setenv("SEPOLIA_SAFE", SAFE)
    monkeypatch.setattr(chain, "refork", lambda fork, block: None)
    reader = SimpleNamespace(functions=SimpleNamespace(nonce=lambda: SimpleNamespace(call=lambda: 2)))
    monkeypatch.setattr(chain, "safe_reader", lambda w3, safe=None: reader)
    w = watcher_mod.Watcher()
    w._live = SimpleNamespace(eth=SimpleNamespace(block_number=100))
    w._fork = object()
    got = w._rehearse(ServiceTx.model_validate(SERVICE_TX), "x", lambda e, p: None)
    assert got.status == "waiting" and "nonce 2" in got.detail


# --------------------------------------------------------------------------- redaction


def test_redact_strips_rpc_url_and_its_key(monkeypatch):
    url = "https://eth-sepolia.g.alchemy.com/v2/alch_SECRETSECRETSECRET123"
    monkeypatch.setenv("SEPOLIA_RPC", url)
    assert "SECRET" not in chain.redact(f"400 Client Error for url: {url}")
    assert "SECRET" not in chain.redact("key alch_SECRETSECRETSECRET123 in a message")


# --------------------------------------------------------------------------- EIP-7708


def test_eip7708_eth_transfer_logs_are_not_events():
    transfer = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    frame = RawFrame.model_validate({
        "type": "CALL", "from": SAFE, "to": OWNER_A, "value": "0x1", "input": "0x",
        "logs": [{"address": "0xfffffffffffffffffffffffffffffffffffffffe",
                  "topics": [transfer, "0x" + "00" * 12 + SAFE[2:].lower(), "0x" + "00" * 12 + OWNER_A[2:].lower()],
                  "data": "0x" + "00" * 31 + "01"}],
    })
    calls, events, _ = trace.flatten(frame)
    assert len(calls) == 1 and calls[0].value == 1
    assert events == []


# --------------------------------------------------------------------------- the Safe App


def test_manifest_is_what_safe_wallet_needs():
    from fastapi.testclient import TestClient

    from web.server import app

    c = TestClient(app)
    r = c.get("/safe-app/manifest.json")
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "*"
    m = r.json()
    assert m["name"] and m["description"] and m["iconPath"] == "icon.svg"
    assert c.get("/safe-app/icon.svg").status_code == 200
    assert "safe-app.js" in c.get("/safe-app").text
