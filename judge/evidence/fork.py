"""Layer 1 evidence: fork. Rehearse a Safe transaction on the anvil fork and build its EvidenceBundle.

Rehearsal (build spec v2, step 0): evm_snapshot; zero the guard slot so our own guard does not
block the rehearsal; run the real execTransaction with the owners' signatures from a throwaway
relayer; trace it (callTracer with logs, prestateTracer in diff mode); read token balances and
code while the state still exists; evm_revert. The fork is left exactly as it was.

    uv run python -m judge.evidence.fork fixtures/cases/demo/demo_bybit.json
    uv run python -m judge.evidence.fork fixtures/cases/match/01_send_eth_ops.json --out fixtures/bundles

The CLI signs with the test owners (anvil's public keys) and writes <out>/<case id>.bundle.json,
plus <case id>.rehearsal.json, the raw traces the bundle was built from.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from eth_utils import to_checksum_address
from pydantic import BaseModel, ConfigDict, Field
from web3 import Web3

from judge.evidence import decode, rules, slots, trace
from judge.schemas import EvidenceBundle, SafeTx, Source

GUARD_SLOT = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
# Impersonated on the fork only; owns nothing on mainnet, so its gas never mixes with real balances.
RELAYER = to_checksum_address("0x5ec0516000000000000000000000000000000001")
REHEARSAL_GAS = 15_000_000
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BUNDLES_DIR = Path(__file__).resolve().parent.parent.parent / "fixtures" / "bundles"

SAFE_ABI = [
    {"type": "function", "name": "nonce", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "getTransactionHash", "stateMutability": "view", "inputs": [
        {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}, {"name": "data", "type": "bytes"},
        {"name": "operation", "type": "uint8"}, {"name": "safeTxGas", "type": "uint256"},
        {"name": "baseGas", "type": "uint256"}, {"name": "gasPrice", "type": "uint256"},
        {"name": "gasToken", "type": "address"}, {"name": "refundReceiver", "type": "address"},
        {"name": "_nonce", "type": "uint256"}], "outputs": [{"type": "bytes32"}]},
    {"type": "function", "name": "execTransaction", "stateMutability": "payable", "inputs": [
        {"name": "to", "type": "address"}, {"name": "value", "type": "uint256"}, {"name": "data", "type": "bytes"},
        {"name": "operation", "type": "uint8"}, {"name": "safeTxGas", "type": "uint256"},
        {"name": "baseGas", "type": "uint256"}, {"name": "gasPrice", "type": "uint256"},
        {"name": "gasToken", "type": "address"}, {"name": "refundReceiver", "type": "address"},
        {"name": "signatures", "type": "bytes"}], "outputs": [{"type": "bool"}]},
]
EXECUTION_SUCCESS_TOPIC = "0x442e715f626346e8c54381002da614f62bee8d27386535b2521ec8540898556e"
ERC20_META_ABI = [
    {"type": "function", "name": "balanceOf", "stateMutability": "view",
     "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]},
    {"type": "function", "name": "decimals", "stateMutability": "view", "inputs": [], "outputs": [{"type": "uint8"}]},
    {"type": "function", "name": "symbol", "stateMutability": "view", "inputs": [], "outputs": [{"type": "string"}]},
]


# --------------------------------------------------------------------------- raw rehearsal output


class RawLog(BaseModel):
    address: str
    topics: list[str] = Field(default_factory=list)
    data: str = "0x"


class RawFrame(BaseModel):
    """One callTracer frame, as anvil returns it."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    type: str
    from_: str = Field(alias="from")
    to: str = "0x0000000000000000000000000000000000000000"
    value: str | None = None
    input: str = "0x"
    output: str | None = None
    error: str | None = None
    revert_reason: str | None = Field(default=None, alias="revertReason")
    logs: list[RawLog] = Field(default_factory=list)
    calls: list[RawFrame] = Field(default_factory=list)


RawFrame.model_rebuild()


class AccountState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    balance: str | None = None
    nonce: int | None = None
    code: str | None = None
    storage: dict[str, str] = Field(default_factory=dict)


class PrestateDiff(BaseModel):
    """prestateTracer diffMode: `pre` holds changed fields before, `post` the same fields after."""

    pre: dict[str, AccountState] = Field(default_factory=dict)
    post: dict[str, AccountState] = Field(default_factory=dict)


class TokenBalance(BaseModel):
    token: str
    holder: str
    before: int
    after: int
    symbol: str | None = None
    decimals: int | None = None


class Rehearsal(BaseModel):
    """Everything read from the fork before evm_revert. Input to trace.py."""

    safe_address: str
    chain_id: int
    fork_block: int
    executed_block: int
    safe_tx: SafeTx
    safe_tx_hash: str
    tx_hash: str
    relayer: str
    relayer_gas_cost: int
    receipt_status: int
    execution_success: bool
    frame: RawFrame
    diff: PrestateDiff
    token_balances: list[TokenBalance] = Field(default_factory=list)
    has_code: dict[str, bool] = Field(default_factory=dict, description="Every address the trace touched.")


# --------------------------------------------------------------------------- rehearsal


def _rpc(w3: Web3, method: str, params: list) -> object:
    r = w3.provider.make_request(method, params)
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def _walk(f: RawFrame):
    yield f
    for c in f.calls:
        yield from _walk(c)


def safe_tx_hash(w3: Web3, safe_address: str, tx: SafeTx) -> str:
    safe = w3.eth.contract(address=to_checksum_address(safe_address), abi=SAFE_ABI)
    h = safe.functions.getTransactionHash(
        tx.to, tx.value, bytes.fromhex(tx.data.removeprefix("0x")), tx.operation, tx.safe_tx_gas,
        tx.base_gas, tx.gas_price, tx.gas_token, tx.refund_receiver, tx.nonce,
    ).call()
    return "0x" + h.hex()


def _token_balances(w3: Web3, frame: RawFrame, block: int) -> list[TokenBalance]:
    pairs: set[tuple[str, str]] = set()
    for f in _walk(frame):
        for log in f.logs:
            if log.address.lower() == trace.ETH_TRANSFER_LOG_ADDRESS:
                continue  # EIP-7708 ETH-transfer log, not a token
            if len(log.topics) == 3 and log.topics[0] == TRANSFER_TOPIC:
                token = to_checksum_address(log.address)
                pairs |= {(token, to_checksum_address("0x" + t[-40:])) for t in log.topics[1:]}
    out = []
    for token, holder in sorted(pairs):
        c = w3.eth.contract(address=token, abi=ERC20_META_ABI)
        meta: dict[str, object] = {}
        for name in ("symbol", "decimals"):
            try:
                meta[name] = getattr(c.functions, name)().call(block_identifier=block)
            except Exception:  # noqa: BLE001 - optional metadata; a token may not implement it
                meta[name] = None
        out.append(TokenBalance(
            token=token, holder=holder,
            before=c.functions.balanceOf(holder).call(block_identifier=block - 1),
            after=c.functions.balanceOf(holder).call(block_identifier=block),
            symbol=meta["symbol"] if isinstance(meta["symbol"], str) else None,
            decimals=meta["decimals"] if isinstance(meta["decimals"], int) else None,
        ))
    return out


def rehearse(w3: Web3, safe_address: str, tx: SafeTx, signatures: bytes) -> Rehearsal:
    """Run the transaction on a snapshot of the fork, read everything, then revert."""
    safe_address = to_checksum_address(safe_address)
    safe = w3.eth.contract(address=safe_address, abi=SAFE_ABI)
    current = safe.functions.nonce().call()
    if tx.nonce != current:
        raise ValueError(f"safe_tx.nonce is {tx.nonce} but the Safe is at nonce {current}")
    h = safe_tx_hash(w3, safe_address, tx)
    fork_block = w3.eth.block_number

    snap = _rpc(w3, "evm_snapshot", [])
    try:
        _rpc(w3, "anvil_setStorageAt", [safe_address, GUARD_SLOT, "0x" + "00" * 32])
        _rpc(w3, "anvil_impersonateAccount", [RELAYER])
        _rpc(w3, "anvil_setBalance", [RELAYER, hex(10**18)])
        txh = safe.functions.execTransaction(
            tx.to, tx.value, bytes.fromhex(tx.data.removeprefix("0x")), tx.operation, tx.safe_tx_gas,
            tx.base_gas, tx.gas_price, tx.gas_token, tx.refund_receiver, signatures,
        ).transact({"from": RELAYER, "gas": REHEARSAL_GAS})
        rcpt = w3.eth.wait_for_transaction_receipt(txh)
        block = rcpt["blockNumber"]

        frame = RawFrame.model_validate(_rpc(
            w3, "debug_traceTransaction", [txh.to_0x_hex(), {"tracer": "callTracer", "tracerConfig": {"withLog": True}}]
        ))
        diff = PrestateDiff.model_validate(_rpc(
            w3, "debug_traceTransaction",
            [txh.to_0x_hex(), {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}}],
        ))
        coinbase = w3.eth.get_block(block)["miner"].lower()
        diff.pre.pop(coinbase, None)
        diff.post.pop(coinbase, None)

        touched = {to_checksum_address(a) for f in _walk(frame) for a in (f.from_, f.to)}
        has_code = {a: len(w3.eth.get_code(a, block_identifier=block)) > 0 for a in sorted(touched)}
        success = any(
            log["topics"] and log["topics"][0].to_0x_hex() == EXECUTION_SUCCESS_TOPIC
            and to_checksum_address(log["address"]) == safe_address
            for log in rcpt["logs"]
        )
        return Rehearsal(
            safe_address=safe_address, chain_id=w3.eth.chain_id, fork_block=fork_block, executed_block=block,
            safe_tx=tx, safe_tx_hash=h, tx_hash=txh.to_0x_hex(), relayer=RELAYER,
            relayer_gas_cost=rcpt["gasUsed"] * rcpt["effectiveGasPrice"], receipt_status=rcpt["status"],
            execution_success=success, frame=frame, diff=diff,
            token_balances=_token_balances(w3, frame, block), has_code=has_code,
        )
    finally:
        _rpc(w3, "anvil_stopImpersonatingAccount", [RELAYER])
        if not _rpc(w3, "evm_revert", [snap]):
            raise RuntimeError("evm_revert failed: the fork now holds the rehearsal's state")


# --------------------------------------------------------------------------- bundle


def collect_sources(r: Rehearsal, ev: trace.TraceEvidence, chain_id: int) -> dict[str, Source]:
    """Etherscan source for every address with code that ran; implementations from the trace."""
    from judge.stages import sources as etherscan

    out: dict[str, Source] = {}
    for addr, code in r.has_code.items():
        if int(addr, 16) < rules.PRECOMPILE_MAX:
            continue
        if not code:
            out[addr] = Source(address=addr, has_code=False, verified=False)
            continue
        c = etherscan.load(addr, chain_id)
        out[addr] = Source(
            address=addr, has_code=True, verified=c.verified, name=c.name or None,
            implementation=ev.implementations.get(addr), compiler=c.compiler or None,
            abi_json=json.dumps(c.abi) if c.verified else None, files=c.files,
        )
    return out


def to_bundle(r: Rehearsal, description: str, sources: dict[str, Source] | None = None) -> EvidenceBundle:
    """Rehearsal -> EvidenceBundle with decoded calls, labelled slots and floor hits."""
    ev = trace.to_evidence(r)
    srcs = sources if sources is not None else collect_sources(r, ev, r.chain_id)
    calls, events = decode.decode(ev.calls, ev.events, srcs, ev.implementations)
    bundle = EvidenceBundle(
        safe_tx_hash=r.safe_tx_hash, safe_address=r.safe_address, chain_id=r.chain_id, fork_block=r.fork_block,
        description=description, safe_tx=r.safe_tx, execution_success=r.execution_success,
        call_tree=calls, storage_diff=ev.storage_diff, balance_diff=ev.balance_diff, events=events, sources=srcs,
    )
    keys = slots.candidate_keys(bundle)
    labelled = [w.model_copy(update={"label": slots.label(w, bundle, keys)}) for w in bundle.storage_diff]
    return rules.with_floor(bundle.model_copy(update={"storage_diff": labelled}))


def build_bundle(w3: Web3, safe_address: str, tx: SafeTx, signatures: bytes, description: str) -> EvidenceBundle:
    return to_bundle(rehearse(w3, safe_address, tx, signatures), description)


# --------------------------------------------------------------------------- CLI


def _case_safe_tx(case: dict, safe_address: str, nonce: int) -> SafeTx:
    """The fixture's transaction with the placeholder Safe address replaced by the real one."""
    st = case["safe_tx"]
    placeholder = case["safe"]["address"].lower()
    to = safe_address if st["to"].lower() == placeholder else to_checksum_address(st["to"])
    data = st["data"].lower().replace(placeholder[2:], safe_address[2:].lower())
    return SafeTx(to=to, value=int(st["value"]), data=data, operation=int(st["operation"]), nonce=nonce)


def main(argv: list[str]) -> int:
    from contracts.setup import connect, ensure_safe, sign_safe_tx
    from judge.run_fixture import ensure_usdc

    ap = argparse.ArgumentParser(description="Rehearse a fixture case on the fork and write its EvidenceBundle.")
    ap.add_argument("case", type=Path)
    ap.add_argument("--out", type=Path, default=BUNDLES_DIR)
    args = ap.parse_args(argv)

    case = json.loads(args.case.read_text(encoding="utf-8"))
    w3 = connect()
    safe = ensure_safe(w3, quiet=True)
    ensure_usdc(w3, safe.address)
    tx = _case_safe_tx(case, safe.address, safe.functions.nonce().call())
    sigs = sign_safe_tx(bytes.fromhex(safe_tx_hash(w3, safe.address, tx)[2:]))
    rehearsal = rehearse(w3, safe.address, tx, sigs)
    bundle = to_bundle(rehearsal, case["description"])

    args.out.mkdir(parents=True, exist_ok=True)
    # The raw rehearsal lets tests rebuild the bundle offline: to_bundle(rehearsal, description, sources)
    (args.out / f"{case['id']}.rehearsal.json").write_text(
        rehearsal.model_dump_json(indent=2, by_alias=True) + "\n", encoding="utf-8", newline="\n"
    )
    out = args.out / f"{case['id']}.bundle.json"
    out.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    print(summary(bundle))
    print(f"\nwritten to {out}")
    return 0


def summary(b: EvidenceBundle) -> str:
    lines = [f"safeTxHash {b.safe_tx_hash}  fork block {b.fork_block}  "
             f"{'ExecutionSuccess' if b.execution_success else 'FAILED'}"]
    for c in b.call_tree:
        name = c.function or c.selector or ("(no data)" if c.input == "0x" else c.input[:10])
        val = f" {c.value / 1e18:g} ETH" if c.value else ""
        lines.append(f"  {c.id:4s}{'  ' * c.depth}{c.kind:12s} {c.to_address} {name}{val}{'' if c.success else ' REVERTED'}")
    for w in b.storage_diff:
        lines.append(f"  {w.id:4s}{w.contract} {w.label or w.slot}: {w.before} -> {w.after}")
    for x in b.balance_diff:
        lines.append(f"  {x.id:4s}{x.holder} {x.symbol or x.asset}: {x.delta:+d}")
    for e in b.events:
        lines.append(f"  {e.id:4s}{e.address} {e.name or e.topic0}")
    lines.append("floor: " + ("; ".join(f"{h.rule} {h.cites}: {h.reason}" for h in b.floor_hits) or "no hits"))
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
