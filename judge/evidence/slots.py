"""Layer 1 evidence: slots. Label storage writes we can name from a known layout.

Mapping slots are keccak hashes, so they are matched by trying candidate keys: every address
in the evidence and the safeTxHash. A label is a fact computed by code, not a model's guess;
an unknown slot stays None and the judge sees it as unlabelled.
"""

from __future__ import annotations

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

from judge.schemas import EvidenceBundle, SlotWrite

SENTINEL = "0x0000000000000000000000000000000000000001"

# EIP-1967 proxy slots, used by most upgradeable contracts (USDC uses its own, below)
EIP1967 = {
    "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc": "proxy.implementation (EIP-1967)",
    "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103": "proxy.admin (EIP-1967)",
    "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50": "proxy.beacon (EIP-1967)",
}

# Safe 1.3.0 / 1.4.1 storage layout (SafeStorage.sol, GuardManager.sol, FallbackManager.sol)
SAFE_FIXED = {
    0: "Safe.singleton",
    3: "Safe.ownerCount",
    4: "Safe.threshold",
    5: "Safe.nonce",
    6: "Safe._deprecatedDomainSeparator",
}
SAFE_NAMED = {
    "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8": "Safe.guard",
    "0x6c9a6c4a39284e37ed1cf53d337577d14212a4870fb976a4366c693b939918d5": "Safe.fallbackHandler",
}
SAFE_ADDR_MAPPINGS = {1: "Safe.modules", 2: "Safe.owners"}
SAFE_SIGNED_MESSAGES = 7
SAFE_APPROVED_HASHES = 8

# Mainnet USDC proxy (FiatTokenV2_2): slot 9 packs balance and blacklist flag; slot 10 allowances
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
TOKEN_LAYOUTS = {
    USDC: {"symbol": "USDC", "balances": 9, "allowances": 10, "totalSupply": 11},
}


def _word(n: int) -> str:
    return "0x" + n.to_bytes(32, "big").hex()


def _map(key: str | int, slot: int | bytes, key_type: str = "address") -> str:
    base = slot if isinstance(slot, bytes) else slot.to_bytes(32, "big")
    k = encode([key_type], [key])
    return "0x" + keccak(k + base).hex()


def candidate_keys(bundle: EvidenceBundle) -> list[str]:
    """Every address in the evidence, for mapping lookups."""
    out = {SENTINEL, bundle.safe_address}
    for c in bundle.call_tree:
        out |= {c.from_address, c.to_address, c.storage_context}
        out |= {a.value for a in c.args if a.type == "address"}
    for e in bundle.events:
        out |= {a.value for a in e.args if a.type == "address"}
        out |= {"0x" + t[-40:] for t in e.topics[1:]}
    for b in bundle.balance_diff:
        out.add(b.holder)
    data = bytes.fromhex(bundle.safe_tx.data.removeprefix("0x"))
    for i in range(4, len(data) - 31):
        word = data[i : i + 32]
        if word[:12] == b"\x00" * 12 and word[12:] != b"\x00" * 20:
            out.add("0x" + word[12:].hex())
    return sorted({to_checksum_address(a) for a in out if len(a) == 42})


def _short(a: str) -> str:
    return f"{a[:6]}…{a[-4:]}"


def _safe_label(slot: str, bundle: EvidenceBundle, keys: list[str]) -> str | None:
    for n, name in SAFE_FIXED.items():
        if slot == _word(n):
            return name
    if slot in SAFE_NAMED:
        return SAFE_NAMED[slot]
    for n, name in SAFE_ADDR_MAPPINGS.items():
        for k in keys:
            if slot == _map(k, n):
                return f"{name}[{_short(k)}]"
    h = bytes.fromhex(bundle.safe_tx_hash.removeprefix("0x"))
    if slot == _map(h, SAFE_SIGNED_MESSAGES, "bytes32"):
        return "Safe.signedMessages[safeTxHash]"
    for owner in keys:
        inner = bytes.fromhex(_map(owner, SAFE_APPROVED_HASHES)[2:])
        if slot == _map(h, inner, "bytes32"):
            return f"Safe.approvedHashes[{_short(owner)}][safeTxHash]"
    return None


def _token_label(contract: str, slot: str, keys: list[str]) -> str | None:
    layout = TOKEN_LAYOUTS.get(contract)
    if layout is None:
        return None
    sym = layout["symbol"]
    if slot == _word(layout["totalSupply"]):
        return f"{sym}.totalSupply"
    for k in keys:
        if slot == _map(k, layout["balances"]):
            return f"{sym}.balanceOf[{_short(k)}]"
    for owner in keys:
        inner = bytes.fromhex(_map(owner, layout["allowances"])[2:])
        for spender in keys:
            if slot == _map(spender, inner):
                return f"{sym}.allowance[{_short(owner)}][{_short(spender)}]"
    return None


def label(w: SlotWrite, bundle: EvidenceBundle, keys: list[str]) -> str | None:
    slot = w.slot.lower()
    contract = to_checksum_address(w.contract)
    if contract == to_checksum_address(bundle.safe_address):
        return _safe_label(slot, bundle, keys)
    if slot in EIP1967:
        return EIP1967[slot]
    return _token_label(contract, slot, keys)
