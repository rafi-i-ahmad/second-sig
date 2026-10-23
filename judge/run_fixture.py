"""Execute one fixture case through the test Safe on the anvil fork and show what happened.

Usage:
    uv run python -m judge.run_fixture fixtures/cases/01_send_eth_ops.json
    uv run python -m judge.run_fixture fixtures/bybit/case.json --save-trace

Needs anvil forking mainnet on http://127.0.0.1:8545 (see NOTES.md). Deploys the test Safe
if it is missing (contracts/setup.py), substitutes the Safe's real address for the fixture
placeholder, signs the Safe transaction with two owners, runs execTransaction, then prints
the receipt, the balance changes for every address-book entry, and the call tree from
debug_traceTransaction. This is a rehearsal tool, not the judge: the fork is left as is.

With --save-trace it also writes fixtures/traces/<case id>.json: the callTracer tree with
logs, the prestateTracer diff (balances, nonces, code and storage before and after, minus
the block coinbase), and ERC-20 balances before and after for every holder named in a
Transfer log. Bybit-shaped cases overwrite the Safe's singleton slot; reset the fork after.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterator

from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError

from contracts.setup import FORK_BLOCK, OWNERS, ZERO, connect, ensure_safe, rpc, sign_safe_tx

TRACES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "traces"

# Mainnet USDC (FiatTokenV2_2): balances live in mapping slot 9, top bit is the blacklist flag.
USDC = to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
USDC_BALANCE_SLOT = 9
USDC_FUND = 10_000 * 10**6

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ERC20_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
]


def fmt_eth(wei: int) -> str:
    sign = "-" if wei < 0 else ""
    return f"{sign}{abs(wei) / 10**18:.6f} ETH"


def print_call_tree(node: dict[str, Any], depth: int = 0) -> None:
    pad = "  " * depth
    value = int(node.get("value", "0x0"), 16)
    data = node.get("input", "0x")
    sel = data[:10] if len(data) >= 10 else data
    err = f"  ERROR {node['error']}" if node.get("error") else ""
    print(f"{pad}{node['type']:12s} {node['to']}  value={fmt_eth(value)}  input={sel} ({(len(data) - 2) // 2} bytes){err}")
    for child in node.get("calls", []):
        print_call_tree(child, depth + 1)


def load_safe_tx(case: dict[str, Any], safe_addr: str) -> tuple[str, int, bytes, int]:
    """The case's Safe transaction with the placeholder Safe address replaced by the real one."""
    stx = case["safe_tx"]
    placeholder = case["safe"]["address"].lower()
    to = safe_addr if stx["to"].lower() == placeholder else to_checksum_address(stx["to"])
    data_hex = stx["data"].lower().replace(placeholder[2:], safe_addr[2:].lower())
    return to, int(stx["value"]), bytes.fromhex(data_hex[2:]), int(stx["operation"])


def ensure_usdc(w3: Web3, holder: str) -> None:
    """Top the Safe up to 10,000 USDC by writing its balance slot, so USDC cases can execute."""
    token = w3.eth.contract(address=USDC, abi=ERC20_ABI)
    if token.functions.balanceOf(holder).call() >= USDC_FUND:
        return
    slot = Web3.solidity_keccak(["uint256", "uint256"], [int(holder, 16), USDC_BALANCE_SLOT])
    rpc(w3, "anvil_setStorageAt", [USDC, "0x" + slot.hex(), "0x" + USDC_FUND.to_bytes(32, "big").hex()])
    if token.functions.balanceOf(holder).call() != USDC_FUND:
        raise SystemExit("USDC top-up did not take; the balance slot layout is not what we expected")


def _walk(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in node.get("calls", []):
        yield from _walk(child)


def token_balances(w3: Web3, tree: dict[str, Any], block: int) -> list[dict[str, Any]]:
    """ERC-20 balances before and after for every (token, holder) pair in a Transfer log."""
    pairs: set[tuple[str, str]] = set()
    for node in _walk(tree):
        for log in node.get("logs", []):
            topics = log.get("topics", [])
            if len(topics) == 3 and topics[0] == TRANSFER_TOPIC:
                token = to_checksum_address(log["address"])
                for t in topics[1:]:
                    pairs.add((token, to_checksum_address("0x" + t[-40:])))
    out = []
    for token, holder in sorted(pairs):
        c = w3.eth.contract(address=token, abi=ERC20_ABI)
        before = c.functions.balanceOf(holder).call(block_identifier=block - 1)
        after = c.functions.balanceOf(holder).call(block_identifier=block)
        out.append({"token": token, "holder": holder, "before": str(before), "after": str(after),
                    "delta": str(after - before)})
    return out


def state_diff(w3: Web3, tx_hash: str, block: int) -> dict[str, Any]:
    """prestateTracer diff, without the coinbase's fee income and without unchanged bytecode."""
    diff = rpc(w3, "debug_traceTransaction", [tx_hash, {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}}])
    coinbase = w3.eth.get_block(block)["miner"].lower()
    pre, post = diff["pre"], diff["post"]
    for side in (pre, post):
        side.pop(coinbase, None)
    for addr, acct in pre.items():
        if "code" in acct and "code" not in post.get(addr, {}):
            acct.pop("code")
    return {"pre": pre, "post": post}


def run(w3: Web3, safe: Contract, case: dict[str, Any], save_trace: bool = False) -> None:
    ensure_usdc(w3, safe.address)
    to, value, data, op = load_safe_tx(case, safe.address)
    print(f"\ncase {case['id']}: \"{case['description']}\"")
    print(f"  to={to} value={fmt_eth(value)} operation={op} data={'0x' + data[:4].hex()}{'...' if len(data) > 4 else ''} ({len(data)} bytes)")

    watched = {name: to_checksum_address(a) for name, a in case["address_book"].items() if not name.startswith("MultiSend")}
    watched["Safe"] = safe.address
    before = {n: w3.eth.get_balance(a) for n, a in watched.items()}

    nonce = safe.functions.nonce().call()
    safe_tx_hash = safe.functions.getTransactionHash(to, value, data, op, 0, 0, 0, ZERO, ZERO, nonce).call()
    sigs = sign_safe_tx(safe_tx_hash)
    print(f"  safeTxHash=0x{safe_tx_hash.hex()} nonce={nonce}")

    tx = safe.functions.execTransaction(to, value, data, op, 0, 0, 0, ZERO, ZERO, sigs).transact({"from": OWNERS[0].address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx)
    print(f"\nexecTransaction mined in block {rcpt['blockNumber']}: status={rcpt['status']} gasUsed={rcpt['gasUsed']} logs={len(rcpt['logs'])}")
    for ev in safe.events.ExecutionSuccess().process_receipt(rcpt):
        print(f"  ExecutionSuccess(txHash=0x{ev['args']['txHash'].hex()}, payment={ev['args']['payment']})")
    for ev in safe.events.ExecutionFailure().process_receipt(rcpt):
        print(f"  ExecutionFailure(txHash=0x{ev['args']['txHash'].hex()}, payment={ev['args']['payment']})")
    try:
        print(f"  Safe nonce now {safe.functions.nonce().call()}")
    except ContractLogicError:
        print("  Safe nonce() now reverts: the transaction replaced the Safe's singleton")

    print("\nETH balances:")
    for n, a in watched.items():
        after = w3.eth.get_balance(a)
        delta = after - before[n]
        print(f"  {n:16s} {a}  {fmt_eth(before[n])} -> {fmt_eth(after)}  ({'+' if delta >= 0 else ''}{fmt_eth(delta)})")

    tree = rpc(w3, "debug_traceTransaction", [tx.hex(), {"tracer": "callTracer", "tracerConfig": {"withLog": True}}])
    print("\ncall tree (debug_traceTransaction, callTracer):")
    print_call_tree(tree)

    if save_trace:
        block = rcpt["blockNumber"]
        trace = {
            "case_id": case["id"],
            "chain_id": w3.eth.chain_id,
            "fork_block": FORK_BLOCK,
            "executed_block": block,
            "tx_hash": tx.to_0x_hex(),
            "tx_from": OWNERS[0].address,
            "safe_address": safe.address,
            "safe_tx_hash": "0x" + safe_tx_hash.hex(),
            "safe_nonce": nonce,
            "safe_tx": {"to": to, "value": str(value), "data": "0x" + data.hex(), "operation": op},
            "status": rcpt["status"],
            "execution": "success" if safe.events.ExecutionSuccess().process_receipt(rcpt) else "failure",
            "call_tree": tree,
            "state_diff": state_diff(w3, tx.to_0x_hex(), block),
            "token_balances": token_balances(w3, tree, block),
        }
        TRACES_DIR.mkdir(parents=True, exist_ok=True)
        out = TRACES_DIR / f"{case['id']}.json"
        out.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"\ntrace written to {out}")


def main(argv: list[str]) -> int:
    save_trace = "--save-trace" in argv
    argv = [a for a in argv if a != "--save-trace"]
    if len(argv) != 1:
        print(__doc__)
        return 2
    case = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    w3 = connect()
    print(f"fork: chain {w3.eth.chain_id}, head block {w3.eth.block_number}")
    safe = ensure_safe(w3)
    run(w3, safe, case, save_trace)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
