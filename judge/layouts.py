"""Known storage layouts for canonical mainnet contracts, keyed by address.

Pure code, like the Safe and USDC layouts in judge/evidence/slots.py: a label here is a fact,
not a model's guess. Keyed by address on purpose: a contract's *name* comes from whoever
verified it and could say "UniswapV2Pair" about anything. Only canonical deployments appear.
"""

from __future__ import annotations

from eth_utils import to_checksum_address

from judge.evidence import slots
from judge.schemas import EvidenceBundle, SlotWrite

# Uniswap V2 pairs share one layout (UniswapV2Pair.sol): slot 8 packs reserve0, reserve1 and
# blockTimestampLast; 9 and 10 are the cumulative prices; 11 is kLast.
UNISWAP_V2_PAIR_FIXED = {8: "reserves (reserve0, reserve1, blockTimestampLast)", 9: "price0CumulativeLast",
                         10: "price1CumulativeLast", 11: "kLast"}

KNOWN: dict[str, dict] = {
    # https://etherscan.io/address/0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc  (Uniswap V2 USDC/WETH pair)
    "0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc": {"name": "UniswapV2Pair(USDC/WETH)", "fixed": UNISWAP_V2_PAIR_FIXED},
    # https://etherscan.io/address/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2  (WETH9)
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": {"name": "WETH", "balances": 3, "allowances": 4},
}


def _label(w: SlotWrite, keys: list[str]) -> str | None:
    layout = KNOWN.get(to_checksum_address(w.contract))
    if layout is None:
        return None
    slot = w.slot.lower()
    name = layout["name"]
    for n, what in layout.get("fixed", {}).items():
        if slot == slots._word(n):
            return f"{name}.{what}"
    if "balances" in layout:
        for k in keys:
            if slot == slots._map(k, layout["balances"]):
                return f"{name}.balanceOf[{slots._short(k)}]"
    if "allowances" in layout:
        for owner in keys:
            inner = bytes.fromhex(slots._map(owner, layout["allowances"])[2:])
            for spender in keys:
                if slot == slots._map(spender, inner):
                    return f"{name}.allowance[{slots._short(owner)}][{slots._short(spender)}]"
    return None


def label_known(bundle: EvidenceBundle) -> EvidenceBundle:
    """The bundle with every unlabelled write that a known layout explains now labelled."""
    if all(w.label for w in bundle.storage_diff):
        return bundle
    keys = slots.candidate_keys(bundle)
    diff = [w if w.label else w.model_copy(update={"label": _label(w, keys)}) for w in bundle.storage_diff]
    return bundle.model_copy(update={"storage_diff": diff})
