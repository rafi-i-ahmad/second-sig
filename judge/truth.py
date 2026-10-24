"""Ground truth for a fixture case, derived by code from the bytes it was built from.

Each case file carries ``calls``: the inner calls build.py encoded, already decoded (target,
function, arguments, value). From those, with no model:
- a plain ETH transfer or an ERC-20 transfer is a movement out of the Safe;
- approve(spender, amount) is an allowance;
- addOwnerWithThreshold / removeOwner / swapOwner / changeThreshold are config changes.

A call into a protocol (Aave's supply, Uniswap's swap) moves assets the calldata does not
spell out. For those the truth adds the Safe's own net balance changes from the bundle,
which the fork recorded deterministically, with the called contract as the counterparty.
A hand-written ``fixtures/truth/<id>.json`` (same shape as the case ``intent`` plus optional
``movements[*].asset_address``) overrides everything when present; none exist today.

The truth is what lets each pass be graded on its own: forward against truth says whether
the words were read right, backward against truth whether the trace was.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_utils import to_checksum_address

from judge import canon
from judge.canon import Resolver, human_amount
from judge.schemas import CanonConfig, CanonEffects, CanonPermission

TRUTH_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "truth"
PLACEHOLDER = "0x5afe5afe5afe5afe5afe5afe5afe5afe5afe5afe"

SIMPLE = {
    "transfer(address,uint256)", "approve(address,uint256)", "addOwnerWithThreshold(address,uint256)",
    "changeThreshold(uint256)", "removeOwner(address,address,uint256)", "swapOwner(address,address,address)",
}


def _addr(value: str, r: Resolver) -> str:
    v = value.lower()
    if v == PLACEHOLDER:
        return r.safe
    return to_checksum_address(value)


def derive(case: dict[str, Any], r: Resolver) -> CanonEffects:
    override = TRUTH_DIR / f"{case['id']}.json"
    if override.exists():
        return _from_override(json.loads(override.read_text(encoding="utf-8")), r)

    out = CanonEffects(source="truth")
    covered: set[tuple[str, str]] = set()  # (asset address, direction) explained by calldata
    protocol_calls: list[str] = []
    for k in case["calls"]:
        to = _addr(k["to"], r)
        fn = k["function"]
        value = int(k["value_wei"])
        cites = [f"call:{k['to_name']} {fn}"]
        if value and (fn.startswith("(plain ETH transfer") or fn in SIMPLE):
            # ETH attached to a plain send is the whole movement. ETH attached to a protocol call
            # is a maximum (a router refunds what it does not spend), so the net comes from the
            # fork's balance changes below instead.
            asset = r.asset("ETH")
            out.movements.append(canon.movement(r, asset, r.safe, to, value, cites, human=human_amount(value, asset)))
            covered.add(("ETH", "out"))
        if fn.startswith("(plain ETH transfer"):
            continue
        if int(k.get("operation", 0)) == 1:
            # A delegatecall runs the target's code as the Safe: whatever it does, it is not an
            # ERC-20 transfer or approval by the Safe. The floor judges it; the truth lists no asset flow.
            out.notes.append(f"delegatecall to {k['to_name']}: no asset flow derivable from calldata")
            continue
        if fn == "transfer(address,uint256)":
            asset = r.asset(to)
            amt = int(k["args"][1])
            out.movements.append(
                canon.movement(r, asset, r.safe, _addr(k["args"][0], r), amt, cites, human=human_amount(amt, asset)))
            covered.add((to, "out"))
        elif fn == "approve(address,uint256)":
            asset = r.asset(to)
            amt = int(k["args"][1])
            out.permissions.append(CanonPermission(
                asset=asset, owner=r.party(r.safe), spender=r.party(_addr(k["args"][0], r)),
                new_allowance=canon.allowance_value(None, amt), cites=cites, source="truth"))
        elif fn == "addOwnerWithThreshold(address,uint256)":
            out.configs.append(CanonConfig(field="owners_add", new=_addr(k["args"][0], r), cites=cites, source="truth"))
            out.configs.append(CanonConfig(field="threshold", new=str(int(k["args"][1])), cites=cites, source="truth"))
        elif fn == "changeThreshold(uint256)":
            out.configs.append(CanonConfig(field="threshold", new=str(int(k["args"][0])), cites=cites, source="truth"))
        elif fn == "removeOwner(address,address,uint256)":
            out.configs.append(CanonConfig(field="owners_remove", new=_addr(k["args"][1], r), cites=cites, source="truth"))
            out.configs.append(CanonConfig(field="threshold", new=str(int(k["args"][2])), cites=cites, source="truth"))
        elif fn == "swapOwner(address,address,address)":
            out.configs.append(CanonConfig(field="owners_remove", new=_addr(k["args"][1], r), cites=cites, source="truth"))
            out.configs.append(CanonConfig(field="owners_add", new=_addr(k["args"][2], r), cites=cites, source="truth"))
        else:
            protocol_calls.append(to)
            out.notes.append(f"protocol call {k['to_name']}.{fn}: asset flows taken from the fork's balance changes")

    if protocol_calls:
        counterparty = protocol_calls[0]
        for b in r.bundle.balance_diff:
            if to_checksum_address(b.holder) != r.safe or b.delta == 0:
                continue
            asset_addr = b.asset if b.asset == "ETH" else to_checksum_address(b.asset)
            direction = "out" if b.delta < 0 else "in"
            if (asset_addr, direction) in covered:
                continue
            asset = r.asset(asset_addr)
            if not asset.resolved:
                asset = asset.model_copy(update={"address": asset_addr, "via": "evidence", "decimals": b.decimals})
            if asset.label == asset_addr and b.symbol:
                asset = asset.model_copy(update={"label": f"{b.symbol} ({asset_addr[:6]}…)"})
            amt = abs(b.delta)
            src, dst = (r.safe, counterparty) if direction == "out" else (counterparty, r.safe)
            out.movements.append(canon.movement(r, asset, src, dst, amt, [b.id], human=human_amount(amt, asset)))
            out.movements[-1].cites.append("from bundle balance_diff")
    out.nothing_else = True
    return out


def _from_override(data: dict[str, Any], r: Resolver) -> CanonEffects:
    out = CanonEffects(source="truth", notes=["hand-written fixtures/truth override"])
    for m in data.get("movements", []):
        asset = r.asset(m.get("asset_address") or m["asset"])
        base = r.to_base(m.get("amount_human"), asset)
        f, t = r.party(m["from_name"]), r.party(m["to_name"])
        out.movements.append(canon.CanonMovement(
            asset=asset, from_party=f, to_party=t, amount_base=base, amount_human=m.get("amount_human"),
            direction=r.direction(f, t), cites=["truth override"], source="truth"))
    for p in data.get("permission_changes", []):
        asset = r.asset(p["asset"])
        out.permissions.append(CanonPermission(
            asset=asset, owner=r.party(p.get("owner_name", "Safe")), spender=r.party(p["spender_name"]),
            new_allowance=canon.allowance_value(p.get("amount_human"), r.to_base(p.get("amount_human"), asset)),
            cites=["truth override"], source="truth"))
    for c in data.get("safe_config_changes", []):
        out.configs.extend(canon._config_items(c["kind"], c.get("owner_name"), c.get("threshold_after"),
                                               ["truth override"], r, "truth"))
    out.nothing_else = data.get("nothing_else", True)
    return out
