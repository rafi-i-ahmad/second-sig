"""Execute one fixture case through the test Safe on the anvil fork and show what happened.

Usage:
    uv run python -m judge.run_fixture fixtures/cases/01_send_eth_ops.json

Needs anvil forking mainnet on http://127.0.0.1:8545 (see NOTES.md). Deploys the test Safe
if it is missing (contracts/setup.py), substitutes the Safe's real address for the fixture
placeholder, signs the Safe transaction with two owners, runs execTransaction, then prints
the receipt, the balance changes for every address-book entry, and the call tree from
debug_traceTransaction. This is a rehearsal tool, not the judge: the fork is left as is.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from eth_utils import to_checksum_address
from web3 import Web3
from web3.contract import Contract

from contracts.setup import OWNERS, ZERO, connect, ensure_safe, rpc, sign_safe_tx


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


def run(w3: Web3, safe: Contract, case: dict[str, Any]) -> None:
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
    print(f"  Safe nonce now {safe.functions.nonce().call()}")

    print("\nETH balances:")
    for n, a in watched.items():
        after = w3.eth.get_balance(a)
        delta = after - before[n]
        print(f"  {n:16s} {a}  {fmt_eth(before[n])} -> {fmt_eth(after)}  ({'+' if delta >= 0 else ''}{fmt_eth(delta)})")

    print("\ncall tree (debug_traceTransaction, callTracer):")
    print_call_tree(rpc(w3, "debug_traceTransaction", [tx.hex(), {"tracer": "callTracer"}]))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    case = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    w3 = connect()
    print(f"fork: chain {w3.eth.chain_id}, head block {w3.eth.block_number}")
    safe = ensure_safe(w3)
    run(w3, safe, case)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
