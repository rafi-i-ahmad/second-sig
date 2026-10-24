"""Sepolia: the public chain the Safe{Wallet} demo runs on, and the anvil fork of it the judge rehearses on.

Two connections:

- ``sepolia_w3()``: the real chain (``SEPOLIA_RPC``). The relayer key signs locally, so
  ``guard.functions.attest(...).transact({"from": relayer})`` in judge/stamp.py works unchanged.
- ``fork_w3()``: anvil forking Sepolia (``SEPOLIA_FORK_RPC``, default http://127.0.0.1:8546). It is
  reset to the latest Sepolia block before every rehearsal, so the stamp's forkBlock is a real,
  recent block that the guard on Sepolia accepts (it rejects a forkBlock ahead of its own chain).

    ~/.foundry/bin/anvil --fork-url $SEPOLIA_RPC --steps-tracing --port 8546

Keys (all in .env, never printed): OWNER1..3_PRIVATE_KEY are the Safe's owners on this demo laptop;
only sepolia/setup.py uses them, to propose and confirm through the Transaction Service. Owners sign
in Safe{Wallet} with MetaMask. SEPOLIA_RELAYER_KEY pays gas for deployments and attest(); it is not
an owner. The judge key stays in judge/stamp.py.

SEPOLIA_RPC carries the provider's API key in its URL, so every error that may reach a log or the
page goes through ``redact()`` first.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.contract import Contract
from web3.middleware import SignAndSendRawMiddlewareBuilder

from contracts.setup import GUARD_ARTIFACT, GUARD_SLOT, ZERO, rpc

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

CHAIN_ID = 11155111
SHORT_NAME = "sep"  # EIP-3770, as Safe{Wallet} and the Transaction Service spell Sepolia
FORK_RPC_DEFAULT = "http://127.0.0.1:8546"
# Safe 1.4.1 L2: same storage and guard support as 1.4.1, and emits the events the Transaction
# Service indexes on every network
SINGLETON_L2 = to_checksum_address("0x29fcB43b46531BcA003ddC8FCB67FFE91900C762")
SALT_NONCE = 20261024
THRESHOLD = 2
# Circle's Sepolia USDC (FiatTokenV2_2); balances at mapping slot 9 like mainnet (checked 24 October)
USDC = to_checksum_address("0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238")
APPROVED_HASHES_SLOT = 8  # Safe 1.4.1: mapping(address => mapping(bytes32 => uint256)) approvedHashes
ADDRESS_BOOK = Path(__file__).resolve().parent / "address_book.json"
LOGS = REPO_ROOT / "logs" / "sepolia"

ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
]
SAFE_READ_ABI = [
    {"type": "function", "name": "nonce", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "getThreshold", "stateMutability": "view", "inputs": [],
     "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "getOwners", "stateMutability": "view", "inputs": [],
     "outputs": [{"type": "address[]"}]},
    {"type": "function", "name": "VERSION", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
    {"type": "function", "name": "approvedHashes", "stateMutability": "view",
     "inputs": [{"name": "o", "type": "address"}, {"name": "h", "type": "bytes32"}], "outputs": [{"type": "uint256"}]},
]


class SepoliaUnavailable(RuntimeError):
    """Sepolia, the fork or a setting is missing. The message is already redacted."""


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, "").strip() or default
    if not value:
        raise SepoliaUnavailable(f"{name} is not set in .env")
    return value


def redact(text: object) -> str:
    """The text with every secret-bearing setting replaced by its name."""
    out = str(text)
    for name in ("SEPOLIA_RPC", "MAINNET_RPC", "SAFE_API_KEY", "ETHERSCAN_API_KEY", "GEMINI_API_KEY"):
        value = os.environ.get(name, "").strip()
        if len(value) >= 8:
            out = out.replace(value, f"<{name}>")
            # a provider key is often the last path segment of the RPC URL; strip it on its own too
            tail = value.rstrip("/").rsplit("/", 1)[-1]
            if len(tail) >= 16:
                out = out.replace(tail, f"<{name}>")
    return out


# --------------------------------------------------------------------------- keys and addresses


def owner_account(i: int) -> LocalAccount:
    """Owner 1, 2 or 3 from .env."""
    return Account.from_key(env(f"OWNER{i}_PRIVATE_KEY"))


def owner_addresses() -> list[str]:
    return [owner_account(i).address for i in (1, 2, 3)]


def relayer() -> LocalAccount:
    return Account.from_key(env("SEPOLIA_RELAYER_KEY"))


def safe_address() -> str:
    return to_checksum_address(env("SEPOLIA_SAFE"))


def address_book() -> dict[str, str]:
    """Names the owners know, for the forward pass and the display. Code-owned, never from the chain."""
    raw = json.loads(ADDRESS_BOOK.read_text(encoding="utf-8"))
    return {k: to_checksum_address(v) for k, v in raw.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- connections


def sepolia_w3(signer: LocalAccount | None = None) -> Web3:
    """The real chain. With ``signer``, transactions from that account are signed locally."""
    w3 = Web3(Web3.HTTPProvider(env("SEPOLIA_RPC"), request_kwargs={"timeout": 30}))
    try:
        chain = w3.eth.chain_id
    except Exception as exc:  # noqa: BLE001 - the provider's error text may carry the URL
        raise SepoliaUnavailable(redact(f"Sepolia RPC unreachable: {type(exc).__name__}: {exc}")) from None
    if chain != CHAIN_ID:
        raise SepoliaUnavailable(f"SEPOLIA_RPC is chain {chain}, expected {CHAIN_ID}")
    if signer is not None:
        w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(signer), layer=0)
    return w3


def fork_w3() -> Web3:
    url = os.environ.get("SEPOLIA_FORK_RPC", "").strip() or FORK_RPC_DEFAULT
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 120}))
    if not w3.is_connected():
        raise SepoliaUnavailable(f"the Sepolia fork is not reachable at {url}; start anvil (NOTES.md, Sepolia)")
    if w3.eth.chain_id != CHAIN_ID:
        raise SepoliaUnavailable(f"the fork at {url} is chain {w3.eth.chain_id}, not a Sepolia fork")
    return w3


def refork(fork: Web3, block: int) -> None:
    """Point the fork at ``block`` of real Sepolia: fresh state, nothing left from earlier rehearsals."""
    try:
        rpc(fork, "anvil_reset", [{"forking": {"jsonRpcUrl": env("SEPOLIA_RPC"), "blockNumber": block}}])
    except RuntimeError as exc:
        raise SepoliaUnavailable(redact(f"anvil_reset failed: {exc}")) from None
    if fork.eth.block_number != block:
        raise SepoliaUnavailable(f"the fork is at block {fork.eth.block_number} after a reset to {block}")


def safe_reader(w3: Web3, address: str | None = None) -> Contract:
    return w3.eth.contract(address=to_checksum_address(address or safe_address()), abi=SAFE_READ_ABI)


def guard_abi() -> list[dict]:
    if not GUARD_ARTIFACT.exists():
        raise SepoliaUnavailable(f"{GUARD_ARTIFACT} missing: run `forge build` in contracts/ first")
    return json.loads(GUARD_ARTIFACT.read_text(encoding="utf-8"))["abi"]


def current_guard(w3: Web3, safe: str) -> str | None:
    """The guard the Safe has set, read from its storage slot (Safe 1.4.1 has no getGuard)."""
    addr = to_checksum_address(w3.eth.get_storage_at(safe, GUARD_SLOT)[-20:])
    return None if addr == ZERO else addr


def guard_contract(w3: Web3, address: str) -> Contract:
    return w3.eth.contract(address=to_checksum_address(address), abi=guard_abi())


# --------------------------------------------------------------------------- rehearsal signatures


def approved_hash_slot(owner: str, safe_tx_hash: str) -> str:
    """Storage slot of approvedHashes[owner][safe_tx_hash]."""
    inner = keccak(bytes.fromhex(to_checksum_address(owner)[2:].rjust(64, "0")) + APPROVED_HASHES_SLOT.to_bytes(32, "big"))
    return "0x" + keccak(bytes.fromhex(safe_tx_hash.removeprefix("0x")) + inner).hex()


def approved_hash_signatures(owners: list[str]) -> bytes:
    """Safe 'approved hash' signatures (v = 1, r = owner, s = 0), sorted by owner as the Safe requires."""
    out = b""
    for o in sorted((to_checksum_address(o) for o in owners), key=lambda a: int(a, 16)):
        out += bytes.fromhex(o[2:].rjust(64, "0")) + bytes(32) + b"\x01"
    return out


def approve_in_fork(fork: Web3, safe: str, safe_tx_hash: str, owners: list[str]) -> bytes:
    """Mark the hash approved by ``owners`` on the fork, without a key and without mining a block,
    and return the signatures that use those approvals. The rehearsal then runs the exact bytes the
    owners will sign, before they have signed. Fork only: never call this on the real chain."""
    if fork.eth.chain_id != CHAIN_ID or not fork.provider.endpoint_uri.startswith(("http://127.0.0.1", "http://localhost")):
        raise SepoliaUnavailable("approve_in_fork runs on the local fork only")
    one = "0x" + (1).to_bytes(32, "big").hex()
    for o in owners:
        rpc(fork, "anvil_setStorageAt", [safe, approved_hash_slot(o, safe_tx_hash), one])
    reader = safe_reader(fork, safe)
    h = bytes.fromhex(safe_tx_hash.removeprefix("0x"))
    if not all(reader.functions.approvedHashes(to_checksum_address(o), h).call() == 1 for o in owners):
        raise SepoliaUnavailable("approvedHashes did not take on the fork; the Safe's storage layout is not 1.4.1")
    return approved_hash_signatures(owners)
