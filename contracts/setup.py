"""Deploy (or find) the test Safe on the anvil fork.

The Safe is a real v1.4.1 proxy created through the real SafeProxyFactory at its mainnet
address, with anvil's three default accounts as owners and a threshold of 2. The factory
uses CREATE2, so the proxy address depends only on the owners, threshold, fallback handler
and salt: rebuilding the fork gives the same address, and a second run on the same fork
finds the proxy already there instead of deploying again.

Usage:
    uv run python contracts/setup.py            # deploy if missing, fund, print the address

Library use:
    from contracts.setup import ensure_safe, OWNERS, SAFE_ABI
    safe = ensure_safe(w3)                      # web3 Contract for the proxy

Owner keys are anvil's published defaults, not secrets.
"""

from __future__ import annotations

import json
import os
import sys

from eth_abi import encode
from eth_account import Account
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.contract import Contract

RPC = os.environ.get("ANVIL_RPC", "http://127.0.0.1:8545")
FORK_BLOCK = 21895238

# Safe 1.4.1 canonical deployments (verified on the fork: code present, VERSION() == "1.4.1")
SINGLETON = to_checksum_address("0x41675C099F32341bf84BFc5382aF534df5C7461a")
PROXY_FACTORY = to_checksum_address("0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67")
FALLBACK_HANDLER = to_checksum_address("0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99")
ZERO = "0x0000000000000000000000000000000000000000"

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
        (ev,) = factory.events.ProxyCreation().process_receipt(rcpt)
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


def main() -> None:
    w3 = connect()
    print(f"fork: chain {w3.eth.chain_id}, head block {w3.eth.block_number} (expected fork block {FORK_BLOCK})")
    ensure_safe(w3)


if __name__ == "__main__":
    sys.exit(main())
