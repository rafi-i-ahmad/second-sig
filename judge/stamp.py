"""EIP-712 signing of Stamp with the judge key.

domain: { name: "SecondSig", version: "1", chainId, verifyingContract: <guard address> }
Stamp:  { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }

This is the only module that touches JUDGE_PRIVATE_KEY, and it is pure code: no model output
reaches it except through a Verdict that verdict.py has already decided (invariants 1 and 3).
The key is read from .env, never logged or printed. The address it derives must match
JUDGE_ADDRESS, which is what contracts/setup.py bakes into the guard.

The digest here must equal SecondSigGuard.stampDigest(); tests/test_stamp.py checks both the
manual EIP-712 construction and, on a fork, the guard's own answer.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.contract import Contract

from contracts.setup import JUDGE_VERSION, SHARED_JUDGE_ADDRESS
from judge.schemas import EvidenceBundle, Stamp

REPO_ROOT = Path(__file__).resolve().parent.parent

DOMAIN_NAME = "SecondSig"
DOMAIN_VERSION = "1"
STAMP_TYPES: dict[str, list[dict[str, str]]] = {
    "Stamp": [
        {"name": "safeTxHash", "type": "bytes32"},
        {"name": "forkBlock", "type": "uint64"},
        {"name": "judgeVersion", "type": "bytes32"},
    ]
}
DOMAIN_TYPEHASH = keccak(text="EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)")
STAMP_TYPEHASH = keccak(text="Stamp(bytes32 safeTxHash,uint64 forkBlock,bytes32 judgeVersion)")

# secp256k1n / 2: the guard rejects signatures with a higher s as malleable copies
HALF_N = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0


class JudgeKeyError(RuntimeError):
    """JUDGE_PRIVATE_KEY is missing or does not belong to JUDGE_ADDRESS."""


# --------------------------------------------------------------------------- the judge key


def judge_version_hex() -> str:
    """The bytes32 the guard was deployed with, as 0x hex."""
    return "0x" + JUDGE_VERSION.hex()


def judge_account() -> Account:
    """The judge key from .env. Raises if it is unset or does not derive to the judge the guard
    was built for: JUDGE_ADDRESS if .env sets one, else the shared judge."""
    load_dotenv(REPO_ROOT / ".env")
    raw = os.environ.get("JUDGE_PRIVATE_KEY", "")
    if not raw:
        raise JudgeKeyError("JUDGE_PRIVATE_KEY is not set in .env")
    acct = Account.from_key(raw)
    override = os.environ.get("JUDGE_ADDRESS", "")
    expected = to_checksum_address(override) if override else SHARED_JUDGE_ADDRESS
    if acct.address != expected:
        which = "JUDGE_ADDRESS in .env" if override else "the shared judge (contracts.setup.SHARED_JUDGE_ADDRESS)"
        raise JudgeKeyError(f"JUDGE_PRIVATE_KEY does not derive to {which}")
    return acct


# --------------------------------------------------------------------------- stamp construction


def make_stamp(bundle: EvidenceBundle) -> Stamp:
    """The stamp for a bundle the verdict passed: binds the hash and the fork block it was judged on."""
    return Stamp(safeTxHash=bundle.safe_tx_hash, forkBlock=bundle.fork_block, judgeVersion=judge_version_hex())


def _b32(value: str) -> bytes:
    b = bytes.fromhex(value.removeprefix("0x"))
    if len(b) != 32:
        raise ValueError(f"expected 32 bytes, got {len(b)}")
    return b


def as_tuple(stamp: Stamp) -> tuple[bytes, int, bytes]:
    """The Solidity struct, for guard.attest(...) and guard.stampDigest(...)."""
    return _b32(stamp.safeTxHash), stamp.forkBlock, _b32(stamp.judgeVersion)


def domain(chain_id: int, guard_address: str) -> dict[str, Any]:
    return {
        "name": DOMAIN_NAME,
        "version": DOMAIN_VERSION,
        "chainId": chain_id,
        "verifyingContract": to_checksum_address(guard_address),
    }


def _message(stamp: Stamp) -> dict[str, Any]:
    h, block, version = as_tuple(stamp)
    return {"safeTxHash": h, "forkBlock": block, "judgeVersion": version}


def digest(stamp: Stamp, chain_id: int, guard_address: str) -> bytes:
    """keccak256("\\x19\\x01" ‖ domainSeparator ‖ structHash), built by hand so it can be checked
    against both eth_account's encoder and the guard's stampDigest()."""
    domain_sep = keccak(
        encode(
            ["bytes32", "bytes32", "bytes32", "uint256", "address"],
            [DOMAIN_TYPEHASH, keccak(text=DOMAIN_NAME), keccak(text=DOMAIN_VERSION), chain_id,
             to_checksum_address(guard_address)],
        )
    )
    struct_hash = keccak(encode(["bytes32", "bytes32", "uint64", "bytes32"], [STAMP_TYPEHASH, *as_tuple(stamp)]))
    return keccak(b"\x19\x01" + domain_sep + struct_hash)


def sign(stamp: Stamp, chain_id: int, guard_address: str, key: Account | None = None) -> bytes:
    """65-byte r ‖ s ‖ v signature over the EIP-712 digest, v in {27, 28}, low s."""
    acct = key or judge_account()
    signable = encode_typed_data(domain(chain_id, guard_address), STAMP_TYPES, _message(stamp))
    signed = acct.sign_message(signable)
    sig = bytes(signed.signature)
    if len(sig) != 65 or sig[64] not in (27, 28) or signed.s > HALF_N:
        raise RuntimeError("eth_account produced a signature the guard would reject")
    return sig


def recover(stamp: Stamp, chain_id: int, guard_address: str, sig: bytes) -> str:
    """The signer the guard will recover for this stamp and signature."""
    return Account._recover_hash(digest(stamp, chain_id, guard_address), signature=sig)  # noqa: SLF001


# --------------------------------------------------------------------------- on-chain


def attest(w3: Web3, guard: Contract, stamp: Stamp, sig: bytes, submitter: str) -> dict[str, Any]:
    """Submit the stamp to the guard. Anyone may submit; only the judge's signature counts."""
    tx = guard.functions.attest(as_tuple(stamp), sig).transact({"from": submitter})
    rcpt = w3.eth.wait_for_transaction_receipt(tx)
    if rcpt["status"] != 1:
        raise RuntimeError("attest reverted")
    return rcpt
