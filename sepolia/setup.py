"""Set up the Sepolia demo Safe and its guard, the way a customer would, with the real Safe{Wallet} queue.

    uv run python -m sepolia.setup                      # check: balances, Safe, guard, queue (default)
    uv run python -m sepolia.setup create-safe          # Safe 1.4.1 L2, owners OWNER1..3, threshold 2
    uv run python -m sepolia.setup fund --safe 0.05 --owner1 0.02     # ETH from the relayer
    uv run python -m sepolia.setup deploy-guard         # SecondSigGuard via CREATE2, from the relayer
    uv run python -m sepolia.setup verify-guard         # forge verify-contract on Sepolia Etherscan
    uv run python -m sepolia.setup propose-guard        # setGuard(guard) into the queue, signed by owner 1
    uv run python -m sepolia.setup confirm <safeTxHash> --owner 2
    uv run python -m sepolia.setup execute <safeTxHash> # execTransaction with the queue's signatures

The Safe is created here, not in the Safe{Wallet} UI, so its version is pinned to 1.4.1: a newer Safe
batches through a newer MultiSendCallOnly, which the hard floor does not allow. The Transaction
Service indexes it on its own; open it at https://app.safe.global/home?safe=sep:<address>.

Once the guard is set, nothing executes without a stamp, setGuard included. The escape hatch:
every owner calls guard.approveOverride(safeTxHash), then wait OVERRIDE_DELAY blocks. All three
owner keys are on the demo laptop, so the override is always reachable.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

from eth_abi import encode
from eth_utils import keccak, to_checksum_address
from web3 import Web3
from web3.logs import DISCARD

from contracts.setup import (
    CREATE2_DEPLOYER, FACTORY_ABI, FALLBACK_HANDLER, GUARD_SALT, JUDGE_VERSION, OVERRIDE_DELAY, PROXY_FACTORY,
    SAFE_ABI, ZERO, guard_initcode, judge_address,
)
from judge.schemas import SafeTx
from sepolia import chain, txservice
from sepolia.chain import SINGLETON_L2, SALT_NONCE, THRESHOLD, USDC

REPO_ROOT = chain.REPO_ROOT


def initializer(w3: Web3, owners: list[str]) -> bytes:
    singleton = w3.eth.contract(address=SINGLETON_L2, abi=SAFE_ABI)
    data = singleton.encode_abi("setup", [owners, THRESHOLD, ZERO, b"", FALLBACK_HANDLER, ZERO, 0, ZERO])
    return bytes.fromhex(data[2:])


def predicted_safe(w3: Web3, init: bytes) -> str:
    factory = w3.eth.contract(address=PROXY_FACTORY, abi=FACTORY_ABI)
    creation = factory.functions.proxyCreationCode().call()
    salt = keccak(keccak(init) + SALT_NONCE.to_bytes(32, "big"))
    raw = keccak(b"\xff" + bytes.fromhex(PROXY_FACTORY[2:]) + salt + keccak(creation + encode(["address"], [SINGLETON_L2])))
    return to_checksum_address(raw[12:])


def predicted_guard(safe: str) -> tuple[str, bytes]:
    initcode, _ = guard_initcode(None, safe, judge_address())  # type: ignore[arg-type]  # w3 unused
    raw = keccak(b"\xff" + bytes.fromhex(CREATE2_DEPLOYER[2:]) + GUARD_SALT + keccak(initcode))
    return to_checksum_address(raw[12:]), initcode


def _send(w3: Web3, tx: dict) -> dict:
    """Send from the relayer (signed locally by the middleware) and wait for the receipt."""
    h = w3.eth.send_transaction(tx)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=180)
    print(f"  tx {h.to_0x_hex()} block {rcpt['blockNumber']} status {rcpt['status']}")
    if rcpt["status"] != 1:
        raise SystemExit("transaction reverted")
    return rcpt


def _set_env(name: str, value: str) -> None:
    """Fill NAME= in .env if it is empty or absent. Never overwrites a set value."""
    env = REPO_ROOT / ".env"
    text = env.read_text(encoding="utf-8")
    m = re.search(rf"^{name}=(.*)$", text, flags=re.M)
    if m and m.group(1).strip():
        return
    line = f"{name}={value}"
    text = text[:m.start()] + line + text[m.end():] if m else text.rstrip("\n") + f"\n{line}\n"
    env.write_text(text, encoding="utf-8")
    os.environ[name] = value
    print(f"  wrote {name} to .env")


def _safe(w3: Web3) -> str:
    """SEPOLIA_SAFE, or the address create-safe will deploy to."""
    if os.environ.get("SEPOLIA_SAFE", "").strip():
        return chain.safe_address()
    return predicted_safe(w3, initializer(w3, chain.owner_addresses()))


# --------------------------------------------------------------------------- commands


def check(w3: Web3) -> None:
    rel = chain.relayer().address
    owners = chain.owner_addresses()
    print(f"Sepolia head {w3.eth.block_number}; judge {judge_address()}")
    print(f"relayer {rel}: {w3.eth.get_balance(rel) / 1e18:.4f} ETH")
    for i, o in enumerate(owners, 1):
        print(f"owner {i} {o}: {w3.eth.get_balance(o) / 1e18:.4f} ETH")
    safe = _safe(w3)
    if not w3.eth.get_code(safe):
        print(f"Safe not deployed yet; create-safe will put it at {safe}")
        return
    s = chain.safe_reader(w3, safe)
    usdc = w3.eth.contract(address=USDC, abi=chain.ERC20_ABI)
    print(f"Safe {safe}: version {s.functions.VERSION().call()}, owners {s.functions.getOwners().call()}, "
          f"threshold {s.functions.getThreshold().call()}, nonce {s.functions.nonce().call()}")
    print(f"  balance {w3.eth.get_balance(safe) / 1e18:.4f} ETH, {usdc.functions.balanceOf(safe).call() / 1e6:,.2f} USDC")
    guard = chain.current_guard(w3, safe)
    expected, _ = predicted_guard(safe)
    deployed = bool(w3.eth.get_code(expected))
    print(f"  guard set: {guard or 'none'}; SecondSigGuard for this Safe at {expected} "
          f"({'deployed' if deployed else 'not deployed'})")
    if guard and guard != expected:
        print("  warning: the Safe's guard is not the one this repo would deploy (recompiled guard?)")
    print(f"  Safe{{Wallet}}: https://app.safe.global/home?safe={chain.SHORT_NAME}:{safe}")
    try:
        queue = txservice.pending(safe, s.functions.nonce().call())
        print(f"  queue: {len(queue)} pending")
        for t in queue:
            print(f"    nonce {t.nonce} {t.safe_tx_hash[:12]}… {len(t.confirmations)}/{t.confirmations_required} "
                  f"note={t.note()!r}")
    except chain.SepoliaUnavailable as exc:
        print(f"  queue unavailable: {exc}")


def create_safe(w3: Web3) -> None:
    init = initializer(w3, chain.owner_addresses())
    addr = predicted_safe(w3, init)
    if w3.eth.get_code(addr):
        print(f"Safe already deployed at {addr}")
    else:
        factory = w3.eth.contract(address=PROXY_FACTORY, abi=FACTORY_ABI)
        print(f"creating Safe 1.4.1 L2 at {addr}")
        tx = factory.functions.createProxyWithNonce(SINGLETON_L2, init, SALT_NONCE).build_transaction(
            {"from": chain.relayer().address})
        rcpt = _send(w3, tx)
        (ev,) = factory.events.ProxyCreation().process_receipt(rcpt, errors=DISCARD)
        if ev["args"]["proxy"] != addr:
            raise SystemExit(f"factory deployed {ev['args']['proxy']}, predicted {addr}")
    _set_env("SEPOLIA_SAFE", addr)


def fund(w3: Web3, safe_eth: float, owner1_eth: float) -> None:
    for name, to, eth in (("Safe", _safe(w3), safe_eth), ("owner 1", chain.owner_addresses()[0], owner1_eth)):
        if eth > 0:
            print(f"sending {eth} ETH to {name} {to}")
            _send(w3, {"from": chain.relayer().address, "to": to, "value": Web3.to_wei(eth, "ether")})


def deploy_guard(w3: Web3) -> None:
    safe = chain.safe_address()
    addr, initcode = predicted_guard(safe)
    if w3.eth.get_code(addr):
        print(f"guard already deployed at {addr}")
        return
    print(f"deploying SecondSigGuard(safe={safe}, judge={judge_address()}, version=0x{JUDGE_VERSION.hex()[:8]}…, "
          f"overrideDelay={OVERRIDE_DELAY}) to {addr}")
    _send(w3, {"from": chain.relayer().address, "to": CREATE2_DEPLOYER, "data": GUARD_SALT + initcode})
    if not w3.eth.get_code(addr):
        raise SystemExit(f"no code at {addr} after the deployment")
    g = chain.guard_contract(w3, addr)
    assert g.functions.JUDGE().call() == judge_address() and g.functions.SAFE().call() == safe


def verify_guard() -> None:
    safe = chain.safe_address()
    addr, _ = predicted_guard(safe)
    args = "0x" + encode(["address", "address", "bytes32", "uint256"],
                         [safe, judge_address(), JUDGE_VERSION, OVERRIDE_DELAY]).hex()
    forge = os.path.expanduser("~/.foundry/bin/forge")
    cmd = [forge, "verify-contract", "--chain", "sepolia", "--watch", "--constructor-args", args, addr,
           "src/SecondSigGuard.sol:SecondSigGuard"]
    # forge reads ETHERSCAN_API_KEY from the environment; it is never on the command line
    r = subprocess.run(cmd, cwd=REPO_ROOT / "contracts", capture_output=True, text=True, env=os.environ.copy())
    print(chain.redact(r.stdout + r.stderr))


def propose_guard(w3: Web3) -> None:
    safe = chain.safe_address()
    guard, _ = predicted_guard(safe)
    if not w3.eth.get_code(guard):
        raise SystemExit("deploy the guard first (deploy-guard)")
    s = w3.eth.contract(address=safe, abi=SAFE_ABI)
    nonce = s.functions.nonce().call()
    tx = SafeTx(to=safe, value=0, data=s.encode_abi("setGuard", [guard]), operation=0, nonce=nonce)
    h = s.functions.getTransactionHash(tx.to, 0, bytes.fromhex(tx.data[2:]), 0, 0, 0, 0, ZERO, ZERO, nonce).call()
    h = "0x" + h.hex()
    txservice.propose(safe, tx, h, chain.owner_account(1), txservice.origin_with_note(
        f"Install the Second Sig guard {guard}"))
    print(f"proposed setGuard({guard}) at nonce {nonce}: {h}")
    print(f"  confirm it in Safe{{Wallet}} as owner 2, or: uv run python -m sepolia.setup confirm {h} --owner 2")


def confirm(safe_tx_hash: str, owner: int) -> None:
    txservice.confirm(safe_tx_hash, chain.owner_account(owner))
    print(f"owner {owner} confirmed {safe_tx_hash}")


def execute(w3: Web3, safe_tx_hash: str) -> None:
    t = txservice.get(safe_tx_hash)
    if len(t.confirmations) < (t.confirmations_required or THRESHOLD):
        raise SystemExit(f"{len(t.confirmations)} of {t.confirmations_required} confirmations")
    st = t.safe_tx()
    s = w3.eth.contract(address=chain.safe_address(), abi=SAFE_ABI)
    fn = s.functions.execTransaction(st.to, st.value, bytes.fromhex(st.data[2:]), st.operation, st.safe_tx_gas,
                                     st.base_gas, st.gas_price, st.gas_token, st.refund_receiver,
                                     txservice.signatures(t))
    rel = chain.relayer().address
    try:
        fn.call({"from": rel})
    except Exception as exc:  # noqa: BLE001 - show the guard's or the Safe's reason and stop
        raise SystemExit(chain.redact(f"execTransaction would revert: {exc}")) from None
    _send(w3, fn.build_transaction({"from": rel}))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check")
    sub.add_parser("create-safe")
    f = sub.add_parser("fund")
    f.add_argument("--safe", type=float, default=0.0, help="ETH for the Safe")
    f.add_argument("--owner1", type=float, default=0.0, help="ETH for owner 1, the executor in Safe{Wallet}")
    sub.add_parser("deploy-guard")
    sub.add_parser("verify-guard")
    sub.add_parser("propose-guard")
    c = sub.add_parser("confirm")
    c.add_argument("safe_tx_hash")
    c.add_argument("--owner", type=int, choices=(1, 2, 3), required=True)
    e = sub.add_parser("execute")
    e.add_argument("safe_tx_hash")
    args = ap.parse_args(argv)

    try:
        w3 = chain.sepolia_w3(chain.relayer())
        if args.cmd in (None, "check"):
            check(w3)
        elif args.cmd == "create-safe":
            create_safe(w3)
        elif args.cmd == "fund":
            fund(w3, args.safe, args.owner1)
        elif args.cmd == "deploy-guard":
            deploy_guard(w3)
        elif args.cmd == "verify-guard":
            verify_guard()
        elif args.cmd == "propose-guard":
            propose_guard(w3)
        elif args.cmd == "confirm":
            confirm(args.safe_tx_hash, args.owner)
        elif args.cmd == "execute":
            execute(w3, args.safe_tx_hash)
    except chain.SepoliaUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - web3 errors can quote the RPC URL
        print(f"error: {chain.redact(f'{type(exc).__name__}: {exc}')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
