"""Deploy (or find) the test Safe on the anvil fork.

The Safe is a real v1.4.1 proxy created through the real SafeProxyFactory at its mainnet
address, with anvil's three default accounts as owners and a threshold of 2. The factory
uses CREATE2, so the proxy address depends only on the owners, threshold, fallback handler
and salt: rebuilding the fork gives the same address, and a second run on the same fork
finds the proxy already there instead of deploying again.

Usage:
    uv run python contracts/setup.py            # deploy if missing, fund, print the address
    uv run python contracts/setup.py --guard    # also deploy SecondSigGuard and setGuard on the Safe

With --guard, every later execTransaction needs a judge stamp (or an override), including
the ones judge/run_fixture.py sends; rehearsals must zero the guard slot first.

Library use:
    from contracts.setup import ensure_safe, OWNERS, SAFE_ABI
    safe = ensure_safe(w3)                      # web3 Contract for the proxy

Owner keys are anvil's published defaults, not secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

from eth_abi import encode
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.contract import Contract
from web3.logs import DISCARD

RPC = os.environ.get("ANVIL_RPC", "http://127.0.0.1:8545")
FORK_BLOCK = 21895238

# Safe 1.4.1 canonical deployments (verified on the fork: code present, VERSION() == "1.4.1")
SINGLETON = to_checksum_address("0x41675C099F32341bf84BFc5382aF534df5C7461a")
PROXY_FACTORY = to_checksum_address("0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67")
FALLBACK_HANDLER = to_checksum_address("0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99")
ZERO = "0x0000000000000000000000000000000000000000"

# Guard: deployed through the CREATE2 deployer that is already on mainnet, so with the same
# constructor arguments it lands at the same address on every fresh fork. The address is in
# the stamp's EIP-712 domain, so a stable address keeps stamps and docs valid across rebuilds.
CREATE2_DEPLOYER = to_checksum_address("0x4e59b44847b379578588920cA78FbF26c0B4956C")
GUARD_SALT = keccak(text="second-sig/guard")
GUARD_ARTIFACT = pathlib.Path(__file__).parent / "out" / "SecondSigGuard.sol" / "SecondSigGuard.json"
# keccak256("guard_manager.guard.address"), where Safe 1.4.1 keeps the guard
GUARD_SLOT = 0x4A204F620C8C5CCDCA3FD54D003BADD85BA500436A431F0CBDA4F558C93C34C8
JUDGE_VERSION_LABEL = os.environ.get("JUDGE_VERSION", "second-sig/v1")
JUDGE_VERSION = keccak(text=JUDGE_VERSION_LABEL)  # bytes32; judge/stamp.py must sign the same value
OVERRIDE_DELAY = 50  # blocks; the guard rejects 0

# The one judge the demo uses (24 October). Its public address is below; the private key is in
# each developer's .env as JUDGE_PRIVATE_KEY, shared privately, never committed. With this judge,
# the guard's CREATE2 address is SHARED_GUARD_ADDRESS on every fresh fork, as long as the compiled
# bytecode, the salt and the other constructor arguments stay the same. JUDGE_ADDRESS in .env
# overrides the judge for local experiments; the guard then lands somewhere else and ensure_guard
# says so.
SHARED_JUDGE_ADDRESS = to_checksum_address("0x7bAc29915313CC27a39163fD82595C6A355b40B9")
SHARED_GUARD_ADDRESS = to_checksum_address("0xf4932401784c5D8435890C226729a87B6464BBC0")

THRESHOLD = 2
SALT_NONCE = 20251023
FUND_WEI = 1000 * 10**18

# anvil default accounts 0..2 (public test keys)
OWNER_KEYS = [
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
]
OWNERS = [Account.from_key(k) for k in OWNER_KEYS]

SAFE_ABI = json.loads("""[
 {"type":"function","name":"VERSION","stateMutability":"view","inputs":[],"outputs":[{"type":"string"}]},
 {"type":"function","name":"nonce","stateMutability":"view","inputs":[],"outputs":[{"type":"uint256"}]},
 {"type":"function","name":"getThreshold","stateMutability":"view","inputs":[],"outputs":[{"type":"uint256"}]},
 {"type":"function","name":"setGuard","stateMutability":"nonpayable","inputs":[{"name":"guard","type":"address"}],"outputs":[]},
 {"type":"function","name":"getOwners","stateMutability":"view","inputs":[],"outputs":[{"type":"address[]"}]},
 {"type":"function","name":"setup","stateMutability":"nonpayable","inputs":[
   {"name":"_owners","type":"address[]"},{"name":"_threshold","type":"uint256"},{"name":"to","type":"address"},
   {"name":"data","type":"bytes"},{"name":"fallbackHandler","type":"address"},{"name":"paymentToken","type":"address"},
   {"name":"payment","type":"uint256"},{"name":"paymentReceiver","type":"address"}],"outputs":[]},
 {"type":"function","name":"getTransactionHash","stateMutability":"view","inputs":[
   {"name":"to","type":"address"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"},
   {"name":"operation","type":"uint8"},{"name":"safeTxGas","type":"uint256"},{"name":"baseGas","type":"uint256"},
   {"name":"gasPrice","type":"uint256"},{"name":"gasToken","type":"address"},{"name":"refundReceiver","type":"address"},
   {"name":"_nonce","type":"uint256"}],"outputs":[{"type":"bytes32"}]},
 {"type":"function","name":"execTransaction","stateMutability":"payable","inputs":[
   {"name":"to","type":"address"},{"name":"value","type":"uint256"},{"name":"data","type":"bytes"},
   {"name":"operation","type":"uint8"},{"name":"safeTxGas","type":"uint256"},{"name":"baseGas","type":"uint256"},
   {"name":"gasPrice","type":"uint256"},{"name":"gasToken","type":"address"},{"name":"refundReceiver","type":"address"},
   {"name":"signatures","type":"bytes"}],"outputs":[{"type":"bool"}]},
 {"type":"event","name":"ExecutionSuccess","anonymous":false,"inputs":[
   {"name":"txHash","type":"bytes32","indexed":true},{"name":"payment","type":"uint256","indexed":false}]},
 {"type":"event","name":"ExecutionFailure","anonymous":false,"inputs":[
   {"name":"txHash","type":"bytes32","indexed":true},{"name":"payment","type":"uint256","indexed":false}]}
]""")

FACTORY_ABI = json.loads("""[
 {"type":"function","name":"proxyCreationCode","stateMutability":"pure","inputs":[],"outputs":[{"type":"bytes"}]},
 {"type":"function","name":"createProxyWithNonce","stateMutability":"nonpayable","inputs":[
   {"name":"_singleton","type":"address"},{"name":"initializer","type":"bytes"},{"name":"saltNonce","type":"uint256"}],
   "outputs":[{"type":"address"}]},
 {"type":"event","name":"ProxyCreation","anonymous":false,"inputs":[
   {"name":"proxy","type":"address","indexed":true},{"name":"singleton","type":"address","indexed":false}]}
]""")


def rpc(w3: Web3, method: str, params: list) -> object:
    """Raw JSON-RPC call for anvil_* and debug_* methods."""
    r = w3.provider.make_request(method, params)
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def connect() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        raise SystemExit(f"anvil not reachable at {RPC}; see NOTES.md for the start command")
    if w3.eth.chain_id != 1:
        raise SystemExit(f"expected a mainnet fork (chain 1), got chain {w3.eth.chain_id}")
    return w3


def initializer(w3: Web3) -> bytes:
    """The setup() calldata the proxy runs once: owners, threshold, fallback handler."""
    singleton = w3.eth.contract(address=SINGLETON, abi=SAFE_ABI)
    owners = [o.address for o in OWNERS]
    data = singleton.encode_abi("setup", [owners, THRESHOLD, ZERO, b"", FALLBACK_HANDLER, ZERO, 0, ZERO])
    return bytes.fromhex(data[2:])


def predicted_address(w3: Web3, init: bytes) -> str:
    """CREATE2 address the factory will use: depends on initializer, salt and singleton only."""
    factory = w3.eth.contract(address=PROXY_FACTORY, abi=FACTORY_ABI)
    creation_code = factory.functions.proxyCreationCode().call()
    salt = keccak(keccak(init) + SALT_NONCE.to_bytes(32, "big"))
    initcode = creation_code + encode(["address"], [SINGLETON])
    raw = keccak(b"\xff" + bytes.fromhex(PROXY_FACTORY[2:]) + salt + keccak(initcode))
    return to_checksum_address(raw[12:])


def ensure_safe(w3: Web3, fund_wei: int = FUND_WEI, quiet: bool = False) -> Contract:
    """Return the test Safe, deploying it through the real factory if it is not there yet."""
    singleton = w3.eth.contract(address=SINGLETON, abi=SAFE_ABI)
    version = singleton.functions.VERSION().call()
    if version != "1.4.1":
        raise SystemExit(f"singleton at {SINGLETON} reports VERSION {version!r}, expected 1.4.1")
    for name, addr in (("proxy factory", PROXY_FACTORY), ("fallback handler", FALLBACK_HANDLER)):
        if not w3.eth.get_code(addr):
            raise SystemExit(f"no code at the {name} {addr}; is the fork on mainnet?")

    init = initializer(w3)
    addr = predicted_address(w3, init)
    if w3.eth.get_code(addr):
        action = "found"
    else:
        factory = w3.eth.contract(address=PROXY_FACTORY, abi=FACTORY_ABI)
        tx = factory.functions.createProxyWithNonce(SINGLETON, init, SALT_NONCE).transact(
            {"from": OWNERS[0].address}
        )
        rcpt = w3.eth.wait_for_transaction_receipt(tx)
        (ev,) = factory.events.ProxyCreation().process_receipt(rcpt, errors=DISCARD)
        if ev["args"]["proxy"] != addr:
            raise SystemExit(f"factory deployed {ev['args']['proxy']}, predicted {addr}")
        action = "deployed"

    if w3.eth.get_balance(addr) < fund_wei:
        rpc(w3, "anvil_setBalance", [addr, hex(fund_wei)])

    safe = w3.eth.contract(address=addr, abi=SAFE_ABI)
    if not quiet:
        print(
            f"Safe {action} at {addr}: version {safe.functions.VERSION().call()}, "
            f"{len(safe.functions.getOwners().call())} owners, threshold "
            f"{safe.functions.getThreshold().call()}, nonce {safe.functions.nonce().call()}, "
            f"balance {w3.eth.get_balance(addr) / 10**18:.0f} ETH"
        )
    return safe


def sign_safe_tx(safe_tx_hash: bytes, signers: list[Account] | None = None) -> bytes:
    """Owner signatures in the Safe's packed format: r, s, v per signer, signers sorted by address."""
    signers = sorted(signers or OWNERS[:THRESHOLD], key=lambda a: int(a.address, 16))
    out = b""
    for acct in signers:
        s = acct.unsafe_sign_hash(safe_tx_hash)
        out += s.r.to_bytes(32, "big") + s.s.to_bytes(32, "big") + bytes([s.v])
    return out


def judge_address() -> str:
    """The judge's public address: JUDGE_ADDRESS from .env if set, else the shared judge.
    The key itself is never read here."""
    from dotenv import load_dotenv

    load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")
    addr = os.environ.get("JUDGE_ADDRESS", "")
    return to_checksum_address(addr) if addr else SHARED_JUDGE_ADDRESS


def guard_initcode(w3: Web3, safe_addr: str, judge: str) -> tuple[bytes, list]:
    if not GUARD_ARTIFACT.exists():
        raise SystemExit(f"{GUARD_ARTIFACT} missing: run `forge build` in contracts/ first")
    art = json.loads(GUARD_ARTIFACT.read_text())
    bytecode = bytes.fromhex(art["bytecode"]["object"].removeprefix("0x"))
    args = encode(["address", "address", "bytes32", "uint256"], [safe_addr, judge, JUDGE_VERSION, OVERRIDE_DELAY])
    return bytecode + args, art["abi"]


def current_guard(w3: Web3, safe_addr: str) -> str:
    """Safe 1.4.1 has no public getGuard(); read its storage slot."""
    return to_checksum_address(w3.eth.get_storage_at(safe_addr, GUARD_SLOT)[-20:])


def ensure_guard(w3: Web3, safe: Contract) -> Contract:
    """Deploy SecondSigGuard for this Safe if missing, then setGuard through a real execTransaction."""
    if not w3.eth.get_code(CREATE2_DEPLOYER):
        raise SystemExit(f"no CREATE2 deployer at {CREATE2_DEPLOYER}; is the fork on mainnet?")
    judge = judge_address()
    initcode, abi = guard_initcode(w3, safe.address, judge)
    raw = keccak(b"\xff" + bytes.fromhex(CREATE2_DEPLOYER[2:]) + GUARD_SALT + keccak(initcode))
    guard_addr = to_checksum_address(raw[12:])
    if guard_addr != SHARED_GUARD_ADDRESS:
        why = "JUDGE_ADDRESS in .env is not the shared judge" if judge != SHARED_JUDGE_ADDRESS else (
            "the guard bytecode or constructor arguments changed; update SHARED_GUARD_ADDRESS")
        print(f"warning: this guard is at {guard_addr}, not the shared {SHARED_GUARD_ADDRESS}: {why}", file=sys.stderr)

    if w3.eth.get_code(guard_addr):
        action = "found"
    else:
        tx = w3.eth.send_transaction({"from": OWNERS[0].address, "to": CREATE2_DEPLOYER, "data": GUARD_SALT + initcode})
        if w3.eth.wait_for_transaction_receipt(tx)["status"] != 1 or not w3.eth.get_code(guard_addr):
            raise SystemExit(f"guard deployment failed; expected code at {guard_addr}")
        action = "deployed"
    guard = w3.eth.contract(address=guard_addr, abi=abi)

    current = current_guard(w3, safe.address)
    if current == guard_addr:
        state = "already set"
    elif current != ZERO:
        raise SystemExit(f"Safe already has a different guard {current}; restart the fork or remove it first")
    else:
        data = safe.encode_abi("setGuard", [guard_addr])
        nonce = safe.functions.nonce().call()
        h = safe.functions.getTransactionHash(safe.address, 0, data, 0, 0, 0, 0, ZERO, ZERO, nonce).call()
        sigs = sign_safe_tx(h)
        tx = safe.functions.execTransaction(safe.address, 0, data, 0, 0, 0, 0, ZERO, ZERO, sigs).transact(
            {"from": OWNERS[0].address}
        )
        rcpt = w3.eth.wait_for_transaction_receipt(tx)
        if not safe.events.ExecutionSuccess().process_receipt(rcpt, errors=DISCARD):
            raise SystemExit("execTransaction(setGuard) did not emit ExecutionSuccess")
        state = f"set by execTransaction in block {rcpt['blockNumber']}"

    assert current_guard(w3, safe.address) == guard_addr, "guard slot does not hold the guard"
    assert guard.functions.JUDGE().call() == judge
    print(
        f"Guard {action} at {guard_addr}, {state}: judge {judge}, "
        f"judgeVersion {JUDGE_VERSION_LABEL!r} = 0x{JUDGE_VERSION.hex()}, "
        f"override delay {guard.functions.OVERRIDE_DELAY().call()} blocks, "
        f"max stamp age {guard.functions.MAX_STAMP_AGE().call()} blocks"
    )
    return guard


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--guard", action="store_true", help="deploy SecondSigGuard and set it on the Safe")
    args = ap.parse_args()
    w3 = connect()
    print(f"fork: chain {w3.eth.chain_id}, head block {w3.eth.block_number} (expected fork block {FORK_BLOCK})")
    safe = ensure_safe(w3)
    if args.guard:
        ensure_guard(w3, safe)


if __name__ == "__main__":
    sys.exit(main())
